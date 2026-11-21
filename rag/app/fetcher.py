import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

import httpx

from app.config import settings

HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
SKIPPED_ELEMENTS = {"script", "style", "noscript", "svg", "template", "iframe", "head"}
BLOCK_ELEMENTS = {
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "td", "th", "table",
    "section", "article", "header", "footer", "nav", "main", "aside", "blockquote", "pre", "dd", "dt", "dl",
    "form", "option", "label", "button", "figcaption", "summary", "details", "hr",
}  # fmt: skip
# Any Unicode whitespace except newline (newlines separate blocks).
WHITESPACE = re.compile(r"[^\S\n]+")


# Titles of anti-bot interstitials (Incapsula, Cloudflare, Akamai): HTTP 200 with no page content behind them.
BOT_WALL_TITLES = ("pardon our interruption", "just a moment", "access denied", "attention required", "請稍候")


class FetchError(Exception):
    """The page could not be fetched or is not HTML; the URL is skipped and counted, never half-indexed."""


@dataclass(frozen=True)
class FetchedPage:
    url: str
    title: str
    text: str
    published_at: datetime | None


# Metadata keys publishers use for the publication date, most specific first. Values are matched case-insensitively.
PUBLISHED_META_KEYS = (
    "article:published_time",
    "og:published_time",
    "datepublished",
    "publish-date",
    "publish_date",
    "pubdate",
    "dc.date.issued",
    "dc.date",
    "dcterms.created",
    "date",
)
META_TAG = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
HTML_ATTRIBUTE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*([\"'])(.*?)\2", re.DOTALL)
JSON_LD_DATE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.IGNORECASE)
TIME_DATE = re.compile(r"<time\b[^>]*\bdatetime\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
EARLIEST_PUBLISHED_YEAR = 1989
FUTURE_DATE_TOLERANCE = timedelta(days=1)


def _parse_published(value: str) -> datetime | None:
    """Accepts ISO 8601 and RFC 2822 dates; anything else is unknown rather than guessed."""
    cleaned = value.strip()
    if not cleaned:
        return None
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(cleaned)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    if parsed.year < EARLIEST_PUBLISHED_YEAR or parsed > datetime.now(UTC) + FUTURE_DATE_TOLERANCE:
        return None
    return parsed


def extract_published_at(html: str) -> datetime | None:
    """
    Publication date from machine-readable metadata only: OpenGraph/HTML meta, JSON-LD or <time datetime>.
    A visible date in prose is not used because its meaning (publication, update, event) is ambiguous.
    """
    meta_values: dict[str, str] = {}
    for tag in META_TAG.findall(html):
        attributes = {name.lower(): value for name, _, value in HTML_ATTRIBUTE.findall(tag)}
        key = (attributes.get("property") or attributes.get("name") or attributes.get("itemprop") or "").lower()
        content = attributes.get("content", "")
        if key and content and key not in meta_values:
            meta_values[key] = content
    for key in PUBLISHED_META_KEYS:
        if (parsed := _parse_published(meta_values.get(key, ""))) is not None:
            return parsed
    for match in JSON_LD_DATE.findall(html):
        if (parsed := _parse_published(match)) is not None:
            return parsed
    for match in TIME_DATE.findall(html):
        if (parsed := _parse_published(match)) is not None:
            return parsed
    return None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in SKIPPED_ELEMENTS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in BLOCK_ELEMENTS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED_ELEMENTS and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in BLOCK_ELEMENTS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip_depth:
            self.parts.append(data)


def extract_text(html: str) -> tuple[str, str]:
    """Title and visible text, one line per block element; scripts, styles and the head are dropped."""
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    lines = [WHITESPACE.sub(" ", line).strip() for line in "".join(extractor.parts).splitlines()]
    text = "\n".join(line for line in lines if line)
    title = WHITESPACE.sub(" ", " ".join(extractor.title_parts)).strip()
    return title, text


async def fetch_page(client: httpx.AsyncClient, url: str) -> FetchedPage:
    try:
        response = await client.get(url, headers={"User-Agent": settings.corpus_fetch_user_agent})
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise FetchError(f"HTTP {error.response.status_code}") from error
    except httpx.HTTPError as error:
        raise FetchError(type(error).__name__) from error
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith(HTML_CONTENT_TYPES):
        raise FetchError(f"not HTML: {content_type.split(';')[0] or 'unknown'}")
    if len(response.content) > settings.corpus_fetch_max_bytes:
        raise FetchError(f"page larger than {settings.corpus_fetch_max_bytes} bytes")
    title, text = extract_text(response.text)
    if not text:
        raise FetchError("no visible text (JavaScript-only page?)")
    if title.casefold().startswith(BOT_WALL_TITLES):
        raise FetchError(f"anti-bot wall: {title}")
    return FetchedPage(url=str(response.url), title=title, text=text, published_at=extract_published_at(response.text))
