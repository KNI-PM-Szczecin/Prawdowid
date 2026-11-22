import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app import fetcher
from app.config import settings
from app.fetcher import FetchError, extract_published_at, extract_text, fetch_page

HTML = """<html><head><title> Komunikat  RCB </title><style>p{}</style><script>var x=1;</script></head>
<body><nav><a>Menu</a></nav><h1>Alert RCB</h1><p>Trening syren <b>21.11</b>.</p>
<div>Drugi akapit&nbsp;tekstu.</div><script>alert(1)</script><noscript>Włącz JS</noscript></body></html>"""


def test_extract_text_keeps_visible_blocks_and_title():
    title, text = extract_text(HTML)
    assert title == "Komunikat RCB"
    assert text.splitlines() == ["Alert RCB", "Trening syren 21.11.", "Drugi akapit tekstu."]


def test_extract_text_ignores_svg_titles_of_inline_icons():
    html = (
        "<html><head><title>Nie, szczepionki nie powodują autyzmu</title></head><body>"
        "<div><svg><title>Narzędzie dostępności</title></svg>Zwiększ tekst</div><p>Treść.</p></body></html>"
    )
    title, text = extract_text(html)
    assert title == "Nie, szczepionki nie powodują autyzmu"
    assert "Narzędzie dostępności" not in text


def test_extract_published_at_prefers_opengraph_then_json_ld_then_time():
    og = '<meta property="article:published_time" content="2024-03-12T10:00:00+01:00">'
    json_ld = '<script type="application/ld+json">{"datePublished":"2024-04-05T09:24:13+00:00"}</script>'
    time_tag = '<time datetime="2020-05-04">4 May 2020</time>'
    assert extract_published_at(og + json_ld + time_tag) == datetime(2024, 3, 12, 9, 0, tzinfo=UTC)
    assert extract_published_at(json_ld + time_tag) == datetime(2024, 4, 5, 9, 24, 13, tzinfo=UTC)
    assert extract_published_at(time_tag) == datetime(2020, 5, 4, tzinfo=UTC)


def test_extract_published_at_reads_elements_labelled_as_publication_date():
    govpl = '<div class="article-header"><p class="event-date">12.03.2024</p><h2>Tytuł</h2></div>'
    assert extract_published_at(govpl) == datetime(2024, 3, 12, tzinfo=UTC)
    nested = '<span class="post-date"><i></i> 2026-11-20 </span>'
    assert extract_published_at(nested) == datetime(2026, 11, 20, tzinfo=UTC)
    assert extract_published_at('<p class="event-date">wkrótce</p>') is None
    assert extract_published_at('<p class="date-of-birth">12.03.2024</p>') is None


def test_extract_published_at_rejects_missing_implausible_and_prose_dates():
    assert extract_published_at("<p>Opublikowano 12.03.2024</p>") is None
    assert extract_published_at('<meta name="date" content="2024-13-40">') is None
    assert extract_published_at('<meta name="date" content="2099-01-01">') is None


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


@pytest.fixture(autouse=True)
def allow_any_host(monkeypatch):
    """The URL guard is stubbed here; it has its own tests with stubbed DNS in test_url_guard.py."""

    async def allow(url):
        return None

    monkeypatch.setattr(fetcher, "assert_public_url", allow)


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


def test_fetch_page_follows_redirects_and_checks_every_hop(monkeypatch):
    checked = []

    async def guard(url):
        checked.append(url)

    monkeypatch.setattr(fetcher, "assert_public_url", guard)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://www.gov.pl/next"})
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})

    page = asyncio.run(fetch_page(_client(handler), "https://www.gov.pl/start"))
    assert checked == ["https://www.gov.pl/start", "https://www.gov.pl/next"]
    assert page.url == "https://www.gov.pl/next"
    assert "Alert RCB" in page.text


def test_fetch_page_rejects_redirect_to_internal_address(monkeypatch):
    from app.url_guard import BlockedURLError

    async def guard(url):
        if "next.example" in url:
            raise BlockedURLError("next.example resolves to a non-public address")

    monkeypatch.setattr(fetcher, "assert_public_url", guard)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "http://next.example/panel"})
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

    with pytest.raises(FetchError, match="blocked"):
        asyncio.run(fetch_page(_client(handler), "https://www.gov.pl/start"))


def test_fetch_page_stops_after_too_many_redirects():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": f"{request.url}/loop"})

    with pytest.raises(FetchError, match="too many redirects"):
        asyncio.run(fetch_page(_client(handler), "https://www.gov.pl/start"))


LONG_PARAGRAPH = "Sondaż przeprowadzono na próbie 1227 osób. " * 15


def test_longest_article_wins_over_teasers_and_chrome():
    html = (
        "<html><body><nav>Pogoda Kraków</nav><header>Onet</header>"
        "<article><h2>Inny tekst</h2><p>Zapowiedź.</p></article>"
        f"<article><header><h1>Właściwy tytuł</h1></header><p>{LONG_PARAGRAPH}</p><aside>Reklama</aside></article>"
        "<footer>Regulamin</footer></body></html>"
    )
    _, text = extract_text(html)
    assert text.startswith("Właściwy tytuł") and "1227 osób" in text
    assert not any(word in text for word in ("Pogoda", "Onet", "Zapowiedź", "Reklama", "Regulamin"))


def test_short_article_falls_back_to_page_without_chrome():
    html = "<body><nav>Menu</nav><article><p>Krótko.</p></article><div><p>Treść poza artykułem.</p></div></body>"
    _, text = extract_text(html)
    assert text.splitlines() == ["Krótko.", "Treść poza artykułem."]


def test_role_navigation_with_nested_divs_is_dropped_but_following_text_kept():
    html = (
        '<body><div role="navigation"><div><div>Link 1</div></div><div>Link 2</div></div>'
        "<div><p>Komunikat RCB.</p></div></body>"
    )
    _, text = extract_text(html)
    assert text == "Komunikat RCB."


def test_unclosed_article_still_counts_as_content():
    html = f"<body><nav>Menu</nav><article><h1>Tytuł</h1><p>{LONG_PARAGRAPH}</p></body>"
    _, text = extract_text(html)
    assert text.startswith("Tytuł") and "Menu" not in text


def test_page_that_is_only_chrome_keeps_its_text():
    _, text = extract_text("<body><nav><a>Jedyna treść strony</a></nav></body>")
    assert text == "Jedyna treść strony"
