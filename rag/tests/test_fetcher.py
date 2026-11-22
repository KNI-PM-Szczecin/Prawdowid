import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app import fetcher as fetcher_module
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


PAGE = httpx.Response(200, text="<html><head><title>Strona</title></head><body><p>Treść.</p></body></html>",
                      headers={"content-type": "text/html"})  # fmt: skip


def _recording_client(responses: dict[str, httpx.Response]) -> tuple[httpx.AsyncClient, list[str]]:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return responses.get(str(request.url), PAGE)

    return _client(handler), requested


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:80/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://100.64.0.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[fd12:3456::1]/",
        "http://0.0.0.0/",
    ],
)
def test_fetch_page_never_requests_private_addresses(url):
    client, requested = _recording_client({})
    with pytest.raises(FetchError, match="not allowed"):
        asyncio.run(fetch_page(client, url))
    assert requested == []


def test_fetch_page_rejects_host_that_resolves_to_private_network(monkeypatch):
    async def internal(host: str) -> list[str]:
        return ["fd12:3456::7"] if host.endswith(".railway.internal") else ["93.184.216.34"]

    monkeypatch.setattr(fetcher_module, "resolve_host", internal)
    client, requested = _recording_client({})
    with pytest.raises(FetchError, match="not allowed"):
        asyncio.run(fetch_page(client, "http://rag.railway.internal/sources"))
    assert requested == []


@pytest.mark.parametrize(
    "url", ["http://example.org:6333/", "https://example.org:8000/docs", "ftp://example.org/x", "file:///etc/passwd"]
)
def test_fetch_page_rejects_other_ports_and_schemes(url):
    client, requested = _recording_client({})
    with pytest.raises(FetchError):
        asyncio.run(fetch_page(client, url))
    assert requested == []


def test_fetch_page_stops_redirect_into_private_network():
    redirect = httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
    client, requested = _recording_client({"https://example.org/short": redirect})
    with pytest.raises(FetchError, match="not allowed"):
        asyncio.run(fetch_page(client, "https://example.org/short"))
    assert requested == ["https://example.org/short"]


def test_fetch_page_follows_public_redirect_and_reports_final_url():
    redirect = httpx.Response(301, headers={"location": "/article"})
    client, requested = _recording_client({"https://example.org/old": redirect})
    page = asyncio.run(fetch_page(client, "https://example.org/old"))
    assert requested == ["https://example.org/old", "https://example.org/article"]
    assert page.url == "https://example.org/article"


def test_fetch_page_gives_up_on_redirect_loop():
    loop = httpx.Response(302, headers={"location": "https://example.org/loop"})
    client, requested = _recording_client({"https://example.org/loop": loop})
    with pytest.raises(FetchError, match="too many redirects"):
        asyncio.run(fetch_page(client, "https://example.org/loop"))
    assert len(requested) == fetcher_module.MAX_REDIRECTS + 1


def test_fetch_page_rejects_unresolvable_host(monkeypatch):
    async def missing(host: str) -> list[str]:
        raise OSError("no such host")

    monkeypatch.setattr(fetcher_module, "resolve_host", missing)
    with pytest.raises(FetchError, match="DNS"):
        asyncio.run(fetch_page(_recording_client({})[0], "https://nie-ma-takiej-domeny.example/"))


def test_slow_page_ends_as_fetch_error_before_agent_timeout(monkeypatch):
    monkeypatch.setattr(fetcher_module, "PAGE_FETCH_DEADLINE_SECONDS", 0.05)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return PAGE

    client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    with pytest.raises(FetchError, match="in time"):
        asyncio.run(fetch_page(client, "https://example.org/slow"))
