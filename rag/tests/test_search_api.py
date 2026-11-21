from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.embeddings import SparseVector
from app.factcheck import FactCheckResult, FactCheckReview
from app.main import app
from app.vector_store import RetrievedChunk

RELEVANT_LOGIT = 8.0
IRRELEVANT_LOGIT = -6.0
CORPUS_VERSION = "test-corpus"
ADMIN_TOKEN = "test-admin-token"
QUERY = {"query": "Czy poseł X poparł ustawę Y?"}


class FakeModels:
    def __init__(self, logits: dict[str, float]):
        self._logits = logits

    def embed_queries(self, queries):
        return [[0.0]] * len(queries), [SparseVector(indices=[], values=[])] * len(queries)

    def rerank(self, query, documents):
        return [self._logits[document] for document in documents]


class FakeStore:
    def __init__(self, chunks: list[RetrievedChunk], failure: Exception | None = None):
        self._chunks = chunks
        self._failure = failure

    async def hybrid_search(self, dense, sparse, limit, payload_filter):
        if self._failure is not None:
            raise self._failure
        return self._chunks

    async def count(self):
        return len(self._chunks)


class FakeFactCheck:
    def __init__(self, result: FactCheckResult):
        self.result = result
        self.calls = 0

    async def search(self, query):
        self.calls += 1
        return self.result


FACTCHECK_REVIEW = FactCheckReview(
    review_id=uuid4(),
    claim_text="Poseł X poparł ustawę Y.",
    claimant="Portal Z",
    publisher="Weryfikator A",
    url="https://weryfikator-a.example/x-y",
    title="Poseł X nie poparł ustawy Y",
    rating="Fałsz",
    review_date=datetime(2026, 10, 3, tzinfo=UTC),
)
UNRELATED_REVIEW = FactCheckReview(
    review_id=uuid4(),
    claim_text="Szczepionki zawierają mikroczipy.",
    claimant=None,
    publisher="Weryfikator B",
    url="https://weryfikator-b.example/czipy",
    title=None,
    rating="Fałsz",
    review_date=datetime(2025, 1, 1, tzinfo=UTC),
)
FACTCHECK_LOGIT = 6.0
CAMPAIGN_LOGIT = 8.0
WEAK_CAMPAIGN_LOGIT = 2.0


def _incident(text: str, incident_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        text=text,
        fusion_score=0.8,
        payload={
            "incident_id": incident_id,
            "source": "euvsdisinfo",
            "title": text,
            "summary": "Twierdzenie rozpowszechniane w kampanii.",
            "url": f"https://euvsdisinfo.eu/report/{incident_id}",
            "published_at": "2024-05-01T00:00:00+00:00",
        },
    )


CAMPAIGN_INCIDENT = _incident("Poseł X poparł ustawę Y na polecenie obcego państwa.", "12345")
WEAK_INCIDENT = _incident("Zachód planuje wojnę.", "67890")


def _metadata_row(chunk_id):
    return {
        "chunk_id": chunk_id,
        "tier": 1,
        "reliability": "high",
        "document_id": "doc-1",
        "title": "Ustawa",
        "publisher": "Dziennik Ustaw",
        "url": "https://example.org/ustawa",
        "published_at": None,
        "fetched_at": datetime(2026, 11, 20, tzinfo=UTC),
        "license": "CC0",
        "source_type": "official",
    }


@pytest.fixture
def client(monkeypatch):
    relevant = RetrievedChunk(chunk_id=uuid4(), text="Poseł X głosował przeciw ustawie Y.", fusion_score=0.9)
    irrelevant = RetrievedChunk(chunk_id=uuid4(), text="Prognoza pogody na weekend.", fusion_score=0.5)

    async def fetch_metadata(chunk_ids):
        return {chunk_id: _metadata_row(chunk_id) for chunk_id in chunk_ids}

    async def corpus_version():
        return CORPUS_VERSION

    async def register_reads(chunk_ids):
        return None

    monkeypatch.setattr(db, "fetch_passage_metadata", fetch_metadata)
    monkeypatch.setattr(db, "corpus_version", corpus_version)
    monkeypatch.setattr(db, "register_reads", register_reads)
    monkeypatch.setattr(settings, "expansion_llm_url", "")
    app.state.models = FakeModels(
        {
            relevant.text: RELEVANT_LOGIT,
            irrelevant.text: IRRELEVANT_LOGIT,
            FACTCHECK_REVIEW.rerank_text: FACTCHECK_LOGIT,
            UNRELATED_REVIEW.rerank_text: IRRELEVANT_LOGIT,
            CAMPAIGN_INCIDENT.text: CAMPAIGN_LOGIT,
            WEAK_INCIDENT.text: WEAK_CAMPAIGN_LOGIT,
        }
    )
    app.state.store = FakeStore([relevant, irrelevant])
    app.state.factcheck = FakeFactCheck(FactCheckResult(status="disabled", reviews=[]))
    app.state.incidents = FakeStore([])
    return TestClient(app, raise_server_exceptions=False)


def test_search_returns_contract_shape_and_drops_irrelevant(client):
    response = client.post("/search", json=QUERY)
    assert response.status_code == 200
    body = response.json()
    assert body["corpusVersion"] == CORPUS_VERSION
    assert len(body["results"]) == 1
    passage = body["results"][0]
    assert {"documentId", "title", "publisher", "fetchedAt", "url", "sourceType", "passage", "score", "flags"} <= set(
        passage
    )
    assert 0.5 <= passage["score"] <= 1.0


def test_search_returns_empty_list_when_nothing_is_relevant(client):
    app.state.store = FakeStore([])
    response = client.post("/search", json=QUERY)
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_index_failure_is_503_index_unavailable(client):
    app.state.store = FakeStore([], failure=RuntimeError("qdrant down"))
    response = client.post("/search", json=QUERY)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "index_unavailable"


def test_top_k_above_limit_is_rejected(client):
    response = client.post("/search", json={**QUERY, "topK": settings.rerank_top_k_max + 1})
    assert response.status_code == 422


def test_admin_endpoints_disabled_without_configured_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "")
    assert client.post("/admin/eviction").status_code == 403


def test_admin_endpoints_reject_wrong_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", ADMIN_TOKEN)
    assert client.post("/admin/eviction").status_code == 401
    assert client.post("/admin/eviction", headers={"X-Admin-Token": "wrong"}).status_code == 401


def test_factcheck_reviews_are_reranked_with_corpus(client):
    app.state.factcheck = FakeFactCheck(FactCheckResult(status="ok", reviews=[FACTCHECK_REVIEW, UNRELATED_REVIEW]))
    body = client.post("/search", json=QUERY).json()
    assert [item["sourceType"] for item in body["results"]] == ["official", "factcheck"]
    factcheck = body["results"][1]
    assert factcheck["url"] == FACTCHECK_REVIEW.url
    assert factcheck["publisher"] == "Weryfikator A"
    assert "Fałsz" in factcheck["passage"]
    assert {"name": "google_factcheck", "status": "ok", "results": 2} in body["externalSources"]


def test_factcheck_failure_does_not_fail_search(client):
    app.state.factcheck = FakeFactCheck(FactCheckResult(status="error", reviews=[]))
    response = client.post("/search", json=QUERY)
    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert response.json()["externalSources"][0]["status"] == "error"


def test_source_type_filter_without_factcheck_skips_the_api(client):
    fake = FakeFactCheck(FactCheckResult(status="ok", reviews=[FACTCHECK_REVIEW]))
    app.state.factcheck = fake
    body = client.post("/search", json={**QUERY, "filters": {"sourceTypes": ["official"]}}).json()
    assert fake.calls == 0
    assert body["externalSources"][0]["status"] == "skipped"
    assert all(item["sourceType"] != "factcheck" for item in body["results"])


def test_published_after_filters_factcheck_reviews(client):
    app.state.factcheck = FakeFactCheck(FactCheckResult(status="ok", reviews=[FACTCHECK_REVIEW]))
    body = client.post("/search", json={**QUERY, "filters": {"publishedAfter": "2026-11-01"}}).json()
    assert all(item["sourceType"] != "factcheck" for item in body["results"])


def test_campaign_match_adds_category_outside_results_and_context(client):
    app.state.incidents = FakeStore([CAMPAIGN_INCIDENT, WEAK_INCIDENT])
    body = client.post("/search", json=QUERY).json()
    alert = body["campaignAlert"]
    assert alert["category"] == "possible_disinformation_campaign"
    assert "kampanii dezinformacyjnej (EUvsDisinfo)" in alert["message"]
    assert [match["incidentId"] for match in alert["matches"]] == ["12345"]
    assert alert["matches"][0]["score"] >= settings.incident_min_score
    assert all("euvsdisinfo" not in item["url"] for item in body["results"])
    assert "euvsdisinfo" not in body["contextXml"]
    assert {"name": "incident_catalog", "status": "ok", "results": 1} in body["externalSources"]


def test_no_alert_for_weak_match_or_empty_catalog(client):
    app.state.incidents = FakeStore([WEAK_INCIDENT])
    assert client.post("/search", json=QUERY).json()["campaignAlert"] is None
    app.state.incidents = FakeStore([])
    body = client.post("/search", json=QUERY).json()
    assert body["campaignAlert"] is None
    assert {"name": "incident_catalog", "status": "disabled", "results": 0} in body["externalSources"]


def test_incident_endpoints_require_admin_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", ADMIN_TOKEN)
    incident = {
        "incidentId": "1",
        "source": "euvsdisinfo",
        "title": "t",
        "summary": "s",
        "url": "https://euvsdisinfo.eu/report/1",
    }
    assert client.post("/incidents", json={"incidents": [incident]}).status_code == 401
    assert client.delete("/incidents/euvsdisinfo/1").status_code == 401
    assert client.get("/incidents").json() == {"catalogSize": 0}
