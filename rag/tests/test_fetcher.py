import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app.config import settings
from app.fetcher import FetchError, extract_published_at, extract_text, fetch_page

HTML = """<html><head><title> Komunikat  RCB </title><style>p{}</style><script>var x=1;</script></head>
<body><nav><a>Menu</a></nav><h1>Alert RCB</h1><p>Trening syren <b>21.11</b>.</p>
<div>Drugi akapit&nbsp;tekstu.</div><script>alert(1)</script><noscript>Włącz JS</noscript></body></html>"""


def test_extract_text_keeps_visible_blocks_and_title():
    title, text = extract_text(HTML)
    assert title == "Komunikat RCB"
    assert text.splitlines() == ["Menu", "Alert RCB", "Trening syren 21.11.", "Drugi akapit tekstu."]


def test_extract_published_at_prefers_opengraph_then_json_ld_then_time():
    og = '<meta property="article:published_time" content="2024-03-12T10:00:00+01:00">'
    json_ld = '<script type="application/ld+json">{"datePublished":"2024-04-05T09:24:13+00:00"}</script>'
    time_tag = '<time datetime="2020-05-04">4 May 2020</time>'
    assert extract_published_at(og + json_ld + time_tag) == datetime(2024, 3, 12, 9, 0, tzinfo=UTC)
    assert extract_published_at(json_ld + time_tag) == datetime(2024, 4, 5, 9, 24, 13, tzinfo=UTC)
    assert extract_published_at(time_tag) == datetime(2020, 5, 4, tzinfo=UTC)


def test_extract_published_at_rejects_missing_implausible_and_prose_dates():
    assert extract_published_at("<p>Opublikowano 12.03.2024</p>") is None
    assert extract_published_at('<meta name="date" content="2024-13-40">') is None
    assert extract_published_at('<meta name="date" content="2099-01-01">') is None


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_fetch_page_returns_text_and_sends_generic_user_agent():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})

    page = asyncio.run(fetch_page(_client(handler), "https://www.gov.pl/web/rcb/x"))
    assert page.title == "Komunikat RCB" and "Alert RCB" in page.text
    assert page.published_at is None
    assert seen == [settings.corpus_fetch_user_agent]


def test_fetch_page_reads_publication_date_from_metadata():
    body = HTML.replace(
        "</head>",
        '<meta property="article:published_time" content="2026-11-21T08:30:00Z"></head>',
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})

    page = asyncio.run(fetch_page(_client(handler), "https://www.gov.pl/web/rcb/x"))
    assert page.published_at == datetime(2026, 11, 21, 8, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, text="nie ma"),
        httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"}),
        httpx.Response(
            200, text="<html><body><script>app()</script></body></html>", headers={"content-type": "text/html"}
        ),
        httpx.Response(200, text="<p>" + "x" * 3_000_000 + "</p>", headers={"content-type": "text/html"}),
        httpx.Response(
            200,
            text="<html><head><title>Pardon Our Interruption</title></head><body><p>Please verify.</p></body></html>",
            headers={"content-type": "text/html"},
        ),
    ],
)
def test_fetch_page_rejects_errors_non_html_empty_and_oversized(response):
    with pytest.raises(FetchError):
        asyncio.run(fetch_page(_client(lambda request: response), "https://www.gov.pl/x"))
