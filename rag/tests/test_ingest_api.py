from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.main import app

ADMIN_TOKEN = "test-admin-token"
HEADERS = {"X-Admin-Token": ADMIN_TOKEN}
DOCUMENT = {
    "source": {
        "documentId": "gov-1",
        "title": "Komunikat",
        "publisher": "MSWiA",
        "url": "https://www.gov.pl/web/mswia/k",
        "fetchedAt": "2026-11-20",
        "topicTag": "bezpieczenstwo",
    },
    "text": "Treść komunikatu o bezpieczeństwie.",
}


class FakeStore:
    def __init__(self, near_duplicate_of: str | None = None):
        self.near_duplicate_of = near_duplicate_of

    async def near_duplicate_document(self, dense_vectors, source_id):
        return self.near_duplicate_of

    async def upsert(self, points):
        return None

    async def delete(self, chunk_ids):
        return None


class FakeModels:
    def embed_documents(self, texts):
        return [[0.0]] * len(texts), [None] * len(texts)


@pytest.fixture
def client(monkeypatch):
    stored: dict[str, str] = {}

    async def find_duplicate(content_hash, document_id):
        return next(
            (other for other, stored_hash in stored.items() if stored_hash == content_hash and other != document_id),
            None,
        )

    async def upsert(source, content_hash, chunk_ids):
        stored[source.document_id] = content_hash

    async def active_ids(document_id):
        return [uuid4()] if document_id in stored else []

    async def mark_deleted(chunk_ids):
        return None

    monkeypatch.setattr(db, "find_duplicate_document", find_duplicate)
    monkeypatch.setattr(db, "upsert_source_with_chunks", upsert)
    monkeypatch.setattr(db, "active_chunk_ids_for_document", active_ids)
    monkeypatch.setattr(db, "mark_chunks_deleted", mark_deleted)
    monkeypatch.setattr(settings, "admin_token", ADMIN_TOKEN)
    app.state.store = FakeStore()
    app.state.models = FakeModels()
    return TestClient(app, raise_server_exceptions=False)


def test_catalog_domain_gets_metadata_and_reingest_replaces(client):
    first = client.post("/ingest", json={"documents": [DOCUMENT]}, headers=HEADERS)
    assert first.status_code == 200
    assert first.json()[0]["inCatalog"] is True
    second = client.post("/ingest", json={"documents": [DOCUMENT]}, headers=HEADERS)
    assert second.json()[0]["chunksReplaced"] == 1


def test_same_text_under_other_id_is_rejected_409(client):
    client.post("/ingest", json={"documents": [DOCUMENT]}, headers=HEADERS)
    copy = {
        **DOCUMENT,
        "source": {**DOCUMENT["source"], "documentId": "gov-2"},
        "text": "  treść KOMUNIKATU o bezpieczeństwie. ",
    }
    response = client.post("/ingest", json={"documents": [copy]}, headers=HEADERS)
    assert response.status_code == 409
    assert "gov-1" in response.json()["detail"]


def test_outside_catalog_without_metadata_is_422(client):
    outside = {**DOCUMENT, "source": {**DOCUMENT["source"], "url": "https://example.org/x"}}
    response = client.post("/ingest", json={"documents": [outside]}, headers=HEADERS)
    assert response.status_code == 422
    assert "example.org" in response.json()["detail"]


def test_catalog_endpoint_is_public(client):
    body = client.get("/sources/catalog").json()
    assert body["rules"]["official"]
    assert any(entry["domains"] == ["demagog.org.pl"] for entry in body["entries"])


def test_paraphrased_copy_is_rejected_409_with_near_message(client):
    app.state.store = FakeStore(near_duplicate_of="gov-1")
    copy = {**DOCUMENT, "source": {**DOCUMENT["source"], "documentId": "gov-3"}, "text": "Inne słowa, ta sama treść."}
    response = client.post("/ingest", json={"documents": [copy]}, headers=HEADERS)
    assert response.status_code == 409
    assert "parafraza" in response.json()["detail"] and "gov-1" in response.json()["detail"]


def test_external_sources_describe_data_sent_and_state(client):
    from app.euvsdisinfo import EuvsDisinfoClient
    from app.factcheck import FactCheckClient

    class EmptyCatalog:
        async def count(self):
            return 0

    app.state.factcheck = FactCheckClient()
    app.state.euvsdisinfo = EuvsDisinfoClient()
    app.state.incidents = EmptyCatalog()
    body = client.get("/sources/external").json()
    assert [entry["name"] for entry in body] == ["google_factcheck", "euvsdisinfo"]
    assert all(entry["dataSent"] and entry["terms"] and entry["env"] for entry in body)
    assert body[1]["catalogSize"] == 0
