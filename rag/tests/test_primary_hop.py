import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app import corpus_sync, db, fetcher, primary_hop
from app.catalog import qualify
from app.config import settings
from app.primary_hop import PrimaryHopClient, catalog_candidates, hop_document_id, rank_by_overlap

PREMIER = "https://www.gov.pl/web/premier/premier-w-obliczu-tragedii-w-krakowie-zobaczylismy-to-co-najlepsze"
PROSECUTOR = "https://www.gov.pl/web/prokuratura-krajowa/sledztwo-w-sprawie-zamachu-w-krakowie"
POLICE = "https://www.policja.pl/pol/aktualnosci/283825,Podsumowanie-przebiegu-tragicznych-wydarzen-w-Krakowie.html"
MEDIA = "https://www.rp.pl/policja/art45468241-prezydent-odznaczyl-policjantow"
ARCHIVE = f"https://web.archive.org/web/20261111025114/{PREMIER}"
UNRELATED = "https://www.gov.pl/web/gov/sprawdz-norme-euro"
LINKS = [MEDIA, ARCHIVE, PREMIER, f"{PREMIER}#komentarze", PROSECUTOR, POLICE, UNRELATED, "ftp://gov.pl/x", "not a url"]


def test_candidates_keep_only_catalog_pages_without_archives_fragments_and_duplicates():
    assert catalog_candidates(LINKS, 10) == [PREMIER, PROSECUTOR, POLICE, UNRELATED]
    assert catalog_candidates(LINKS, 2) == [PREMIER, PROSECUTOR]


def test_without_a_model_pages_are_ranked_by_word_overlap_and_unrelated_ones_dropped():
    ranked = rank_by_overlap([UNRELATED, PROSECUTOR, PREMIER], "zamach Kraków sprawca", 3)
    # inflected forms match (zamach/zamachu, Kraków/krakowie); the unrelated page shares no word with the claim
    assert ranked == [PROSECUTOR, PREMIER]


class Wikipedia:
    def __init__(self, titles=("Strzelanina w Krakowie (2026)",), links=None):
        self.titles, self.links = titles, LINKS if links is None else links
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "pl.wikipedia.org":
            params = dict(request.url.params)
            self.requests.append(params)
            if params.get("list") == "search":
                return httpx.Response(200, json={"query": {"search": [{"title": title} for title in self.titles]}})
            return httpx.Response(
                200, json={"query": {"pages": {"1": {"extlinks": [{"*": link} for link in self.links]}}}}
            )
        body = (
            "<html><head><title>Komunikat</title></head>"
            f"<body><p>Sprawca był obywatelem Polski {request.url.path}.</p></body></html>"
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})


@pytest.fixture
def indexed(monkeypatch):
    documents = {}

    async def ingest_document(document, models, store):
        qualify(document.source)
        documents[document.source.document_id] = document

    async def no_copy(document_id, *args):
        return None

    async def no_chunks(document_id):
        return []

    async def allow(url):
        return None

    async def date_of(url):
        return None

    async def fetch_page(client, url):
        page = await original_fetch(client, url)
        published = None if "policja.pl" in url else datetime(2026, 11, 8, tzinfo=UTC)
        return page.__class__(**{**page.__dict__, "published_at": published}) if hasattr(page, "__dict__") else page

    original_fetch = fetcher.fetch_page
    monkeypatch.setattr(primary_hop, "ingest_document", ingest_document)
    monkeypatch.setattr(db, "document_fetched_at", no_copy)
    monkeypatch.setattr(db, "active_chunk_ids_for_document", no_chunks)
    monkeypatch.setattr(fetcher, "assert_public_url", allow)
    monkeypatch.setattr(primary_hop, "fetch_page", fetch_page)
    monkeypatch.setattr(settings, "corpus_fetch_delay_seconds", 0)
    monkeypatch.setattr(corpus_sync, "ingest_document", ingest_document)
    return documents


def _client(wikipedia: Wikipedia) -> PrimaryHopClient:
    return PrimaryHopClient(transport=httpx.MockTransport(wikipedia.handler))


def test_the_model_chooses_pages_and_only_listed_addresses_are_used(indexed, monkeypatch):
    async def ask(system, user):
        return {"urls": [PROSECUTOR, "https://www.gov.pl/web/not-in-the-list", MEDIA]}

    monkeypatch.setattr(primary_hop, "model_configured", lambda: True)
    monkeypatch.setattr(primary_hop, "ask_model_json", ask)
    wikipedia = Wikipedia()
    result = asyncio.run(_client(wikipedia).fill("Sprawcą był obcokrajowiec", "zamach Kraków sprawca", None, None))
    assert result.status == "ok" and result.indexed == 1
    assert list(indexed) == [hop_document_id(PROSECUTOR)]
    assert indexed[hop_document_id(PROSECUTOR)].source.published_at == datetime(2026, 11, 8, tzinfo=UTC)
    assert wikipedia.requests[0]["srsearch"] == "zamach Kraków sprawca"


def test_without_a_model_the_overlap_ranking_chooses(indexed, monkeypatch):
    monkeypatch.setattr(primary_hop, "model_configured", lambda: False)
    result = asyncio.run(_client(Wikipedia()).fill("Sprawcą był obcokrajowiec", "zamach Kraków sprawca", None, None))
    assert result.indexed == 2  # premier and prosecutor pages; the police page has no date, the rest is unrelated
    assert set(indexed) == {hop_document_id(PREMIER), hop_document_id(PROSECUTOR)}


def test_a_failing_model_falls_back_to_the_overlap_ranking(indexed, monkeypatch):
    async def broken(system, user):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(primary_hop, "model_configured", lambda: True)
    monkeypatch.setattr(primary_hop, "ask_model_json", broken)
    result = asyncio.run(_client(Wikipedia()).fill("Sprawcą był obcokrajowiec", "zamach Kraków sprawca", None, None))
    assert result.indexed == 2


def test_a_page_without_a_publication_date_is_not_indexed(indexed, monkeypatch):
    async def ask(system, user):
        return {"urls": [POLICE]}

    monkeypatch.setattr(primary_hop, "model_configured", lambda: True)
    monkeypatch.setattr(primary_hop, "ask_model_json", ask)
    result = asyncio.run(_client(Wikipedia()).fill("Sprawcą był obcokrajowiec", "zamach Kraków sprawca", None, None))
    assert result.indexed == 0 and indexed == {}


def test_nothing_is_fetched_when_wikipedia_has_no_article_or_no_catalog_links(indexed):
    assert asyncio.run(_client(Wikipedia(titles=())).fill("x y z", "x y z", None, None)).indexed == 0
    assert asyncio.run(_client(Wikipedia(links=[MEDIA, ARCHIVE])).fill("x y z", "x y z", None, None)).indexed == 0
    assert indexed == {}


def test_disabled_hop_does_nothing(monkeypatch):
    monkeypatch.setattr(settings, "hop_enabled", False)
    result = asyncio.run(PrimaryHopClient().fill("x y z", "x y z", None, None))
    assert result.status == "disabled" and result.indexed == 0


def test_the_same_keywords_do_not_ask_wikipedia_twice_and_the_agent_names_the_project(indexed, monkeypatch):
    monkeypatch.setattr(primary_hop, "model_configured", lambda: False)
    agents = []
    wikipedia = Wikipedia()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "pl.wikipedia.org":
            agents.append(request.headers["user-agent"])
        return wikipedia.handler(request)

    client = PrimaryHopClient(transport=httpx.MockTransport(handler))
    asyncio.run(client.fill("Sprawcą był obcokrajowiec", "zamach Kraków sprawca", None, None))
    asyncio.run(client.fill("Sprawcą był obcokrajowiec", "zamach Kraków sprawca", None, None))
    assert len(agents) == 2  # one search and one link request, the second claim is served from the cache
    assert all(agent.startswith("Prawdowid/") and "github.com/KNI-PM-Szczecin/prawdowid" in agent for agent in agents)
