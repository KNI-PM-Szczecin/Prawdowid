import asyncio

import httpx
import pytest

from app.config import settings
from app.fetcher import FetchError, extract_text, fetch_page

HTML = """<html><head><title> Komunikat  RCB </title><style>p{}</style><script>var x=1;</script></head>
<body><nav><a>Menu</a></nav><h1>Alert RCB</h1><p>Trening syren <b>21.11</b>.</p>
<div>Drugi akapit&nbsp;tekstu.</div><script>alert(1)</script><noscript>Włącz JS</noscript></body></html>"""


def test_extract_text_keeps_visible_blocks_and_title():
    title, text = extract_text(HTML)
    assert title == "Komunikat RCB"
    assert text.splitlines() == ["Menu", "Alert RCB", "Trening syren 21.11.", "Drugi akapit tekstu."]


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_fetch_page_returns_text_and_sends_generic_user_agent():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})

    page = asyncio.run(fetch_page(_client(handler), "https://www.gov.pl/web/rcb/x"))
    assert page.title == "Komunikat RCB" and "Alert RCB" in page.text
    assert seen == [settings.corpus_fetch_user_agent]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, text="nie ma"),
        httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"}),
        httpx.Response(
            200, text="<html><body><script>app()</script></body></html>", headers={"content-type": "text/html"}
        ),
        httpx.Response(200, text="<p>" + "x" * 3_000_000 + "</p>", headers={"content-type": "text/html"}),
    ],
)
def test_fetch_page_rejects_errors_non_html_empty_and_oversized(response):
    with pytest.raises(FetchError):
        asyncio.run(fetch_page(_client(lambda request: response), "https://www.gov.pl/x"))
