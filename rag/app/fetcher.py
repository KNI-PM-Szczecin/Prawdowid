import re
from dataclasses import dataclass
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


class FetchError(Exception):
    """The page could not be fetched or is not HTML; the URL is skipped and counted, never half-indexed."""


@dataclass(frozen=True)
class FetchedPage:
    url: str
    title: str
    text: str


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
    return FetchedPage(url=str(response.url), title=title, text=text)
