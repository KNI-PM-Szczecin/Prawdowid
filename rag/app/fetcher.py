import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

import httpx

from app.config import settings
from app.url_guard import BlockedURLError, assert_public_url

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
# An element the publisher itself labels as the publication date (gov.pl uses <p class="event-date">12.03.2024</p>
# and no metadata at all). Only class names that mean "date of publication"; prose dates stay ignored.
DATED_ELEMENT = re.compile(
    r"<(?:p|span|div|time|small|li)\b[^>]*\bclass\s*=\s*[\"'][^\"']*\b"
    r"(?:event-date|article-date|article__date|publish(?:ed)?-date|date-published|post-date|entry-date|news-date)"
    r"\b[^\"']*[\"'][^>]*>\s*(?:<[^>]+>\s*)*([^<]{6,40})<",
    re.IGNORECASE,
)
VISIBLE_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
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


def _parse_visible_date(text: str) -> datetime | None:
    """dd.mm.yyyy or yyyy-mm-dd inside an element labelled as the publication date; prose dates never get here."""
    match = VISIBLE_DATE.search(text)
    if match is None:
        return None
    day, month, year = (
        (match.group(1), match.group(2), match.group(3))
        if match.group(1)
        else (
            match.group(6),
            match.group(5),
            match.group(4),
        )
    )
    return _parse_published(f"{year}-{int(month):02d}-{int(day):02d}")


def extract_published_at(html: str) -> datetime | None:
    """
    Publication date from machine-readable metadata: OpenGraph/HTML meta, JSON-LD, <time datetime>, and last an
    element whose class names it as the publication date (gov.pl `event-date`). A date in prose is not used
    because its meaning (publication, update, event) is ambiguous.
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
    for match in DATED_ELEMENT.findall(html):
        if (parsed := _parse_visible_date(match)) is not None:
            return parsed
    return None


# Page chrome that is never the material to check: menus, side panels, footers, forms (and the same roles in ARIA).
BOILERPLATE_ELEMENTS = {"nav", "aside", "footer", "form"}
BOILERPLATE_ROLES = {"navigation", "banner", "contentinfo", "complementary", "search"}
# The main content of a page; the longest one wins (a news page also has <article> teasers of other stories).
CONTENT_ELEMENTS = {"article", "main"}
CONTENT_ROLES = {"main", "article"}
# A content region shorter than this is a teaser or an empty shell; the page minus its chrome is used instead.
MIN_CONTENT_CHARS = 400
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr",
}  # fmt: skip


class _TextExtractor(HTMLParser):
    """Collects visible text pieces and remembers, for each piece, the content region and chrome it sits in."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        # (text, content region ids, inside chrome)
        self.pieces: list[tuple[str, tuple[int, ...], bool]] = []
        self._skip_depth = 0
        self._svg_depth = 0
        self._in_title = False
        self._open: dict[str, int] = {}
        # (tag, open count of that tag when it started, kind, region id)
        self._tracked: list[tuple[str, int, str, int]] = []
        self._next_region = 0

    def _context(self) -> tuple[tuple[int, ...], bool]:
        regions = tuple(region for _, _, kind, region in self._tracked if kind == "content")
        chrome = any(kind == "chrome" for _, _, kind, _ in self._tracked)
        return regions, chrome

    def _append(self, text: str) -> None:
        regions, chrome = self._context()
        self.pieces.append((text, regions, chrome))

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag not in VOID_ELEMENTS:
            self._open[tag] = self._open.get(tag, 0) + 1
            role = (dict(attrs).get("role") or "").strip().lower()
            in_content = any(kind == "content" for _, _, kind, _ in self._tracked)
            if tag in CONTENT_ELEMENTS or role in CONTENT_ROLES:
                self._tracked.append((tag, self._open[tag], "content", self._next_region))
                self._next_region += 1
            elif tag in BOILERPLATE_ELEMENTS or role in BOILERPLATE_ROLES or (tag == "header" and not in_content):
                self._tracked.append((tag, self._open[tag], "chrome", -1))
        if tag in SKIPPED_ELEMENTS:
            self._skip_depth += 1
            self._svg_depth += tag == "svg"
        elif tag == "title" and not self._svg_depth:
            # Only the document title: <title> inside inline SVG icons (accessibility widgets) is not the page title.
            self._in_title = True
        elif tag in BLOCK_ELEMENTS:
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED_ELEMENTS and self._skip_depth:
            self._skip_depth -= 1
            self._svg_depth -= tag == "svg" and self._svg_depth > 0
        elif tag == "title" and not self._svg_depth:
            self._in_title = False
        elif tag in BLOCK_ELEMENTS:
            self._append("\n")
        if self._open.get(tag):
            level = self._open[tag]
            self._open[tag] = level - 1
            while self._tracked and any(name == tag and start >= level for name, start, _, _ in self._tracked):
                self._tracked.pop()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip_depth:
            self._append(data)


def _lines(pieces: list[str]) -> str:
    lines = [WHITESPACE.sub(" ", line).strip() for line in "".join(pieces).splitlines()]
    return "\n".join(line for line in lines if line)


def extract_text(html: str) -> tuple[str, str]:
    """
    Title and the main text, one line per block element; scripts, styles and the head are dropped.
    The longest <article>/<main> region is used when it holds real content, otherwise the page without its
    navigation, side panels, footers and forms; the whole visible text only when nothing else is left.
    """
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    title = WHITESPACE.sub(" ", " ".join(extractor.title_parts)).strip()
    regions: dict[int, list[str]] = {}
    for text, region_ids, chrome in extractor.pieces:
        if not chrome:
            for region in region_ids:
                regions.setdefault(region, []).append(text)
    region_texts = [_lines(parts) for parts in regions.values()]
    best = max(region_texts, key=len, default="")
    if len(best) >= MIN_CONTENT_CHARS:
        return title, best
    without_chrome = _lines([text for text, _, chrome in extractor.pieces if not chrome])
    if without_chrome:
        return title, without_chrome
    return title, _lines([text for text, _, _ in extractor.pieces])


async def _read_limited(response: httpx.Response) -> bytes:
    """Reads the body enforcing the size limit mid-stream, so an oversized page is rejected before
    it is fully downloaded and held in memory."""
    received = 0
    chunks: list[bytes] = []
    async for chunk in response.aiter_bytes():
        received += len(chunk)
        if received > settings.corpus_fetch_max_bytes:
            raise FetchError(f"page larger than {settings.corpus_fetch_max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


async def fetch_page(client: httpx.AsyncClient, url: str) -> FetchedPage:
    """
    Fetches one public page. The URL and every redirect target are resolved and checked against
    non-public address ranges first, so a citizen-supplied URL cannot reach internal services or the
    cloud metadata endpoint; redirects are followed manually for exactly that reason. The body is read
    with a mid-stream size limit.
    """
    current = url
    for _hop in range(settings.corpus_fetch_max_redirects + 1):
        try:
            await assert_public_url(current)
        except BlockedURLError as error:
            raise FetchError(f"blocked: {error}") from error
        try:
            async with client.stream(
                "GET", current, headers={"User-Agent": settings.corpus_fetch_user_agent}, follow_redirects=False
            ) as response:
                # Redirects first: httpx raise_for_status treats an unfollowed 3xx as an error.
                if response.is_redirect:
                    if response.next_request is None:
                        raise FetchError("redirect without a target")
                    current = str(response.next_request.url)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                charset = response.charset_encoding or "utf-8"
                body = await _read_limited(response)
                page_url = str(response.url)
        except httpx.HTTPStatusError as error:
            raise FetchError(f"HTTP {error.response.status_code}") from error
        except httpx.HTTPError as error:
            raise FetchError(type(error).__name__) from error
        if not content_type.startswith(HTML_CONTENT_TYPES):
            raise FetchError(f"not HTML: {content_type.split(';')[0] or 'unknown'}")
        html = body.decode(charset, errors="replace")
        title, text = extract_text(html)
        if not text:
            raise FetchError("no visible text (JavaScript-only page?)")
        if title.casefold().startswith(BOT_WALL_TITLES):
            raise FetchError(f"anti-bot wall: {title}")
        return FetchedPage(url=page_url, title=title, text=text, published_at=extract_published_at(html))
    raise FetchError("too many redirects")
