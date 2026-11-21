import asyncio

from app import seed
from app.catalog import resolve_entry
from app.config import settings
from app.incidents import load_seed_incidents
from app.ingest import DuplicateDocumentError, chunk_text
from app.seed import load_seed_documents


def test_seed_documents_have_complete_metadata_and_catalog_sources():
    documents = load_seed_documents()
    assert len(documents) >= 12
    ids = [document.source.document_id for document in documents]
    assert len(ids) == len(set(ids))
    for document in documents:
        source = document.source
        assert source.title and source.publisher and source.url and source.fetched_at and source.published_at
        assert source.license
        assert document.text.strip()
        assert resolve_entry(str(source.url)) is not None, source.url


def test_seed_chunks_contain_the_facts_the_eval_expects():
    chunks = [
        chunk
        for document in load_seed_documents()
        for chunk in chunk_text(document.text, settings.chunk_max_chars, settings.chunk_overlap_chars)
    ]
    for phrase in (
        "1 maja 2004",
        "12 marca 1999",
        "2 kwietnia 1997 r. Zgromadzenie Narodowe uchwaliło Konstytucję",
        "Sejm składa się z 460 posłów",
        "Senat składa się ze 100 senatorów",
        "wybierany na pięcioletnią kadencję",
        "wybierane na czteroletnie kadencje",
        "Stolicą Rzeczypospolitej Polskiej jest Warszawa",
        "wzrosły o 6,2%",
        "wyniósł 111,4",
        "700 mln zł",
        "650 mln zł",
        "24 lutego 2022 r. Federacja Rosyjska dokonała napaści",
        "5G mobile networks DO NOT spread COVID-19",
        "Od dnia 1 stycznia 2035 r.",
        "60 lat dla kobiet",
        "16 województw",
        "złoty nie został włączony do mechanizmu ERM II",
        "Polish złoty remains Poland",
    ):
        assert any(phrase in chunk for chunk in chunks), phrase


def test_seed_incidents_are_real_euvsdisinfo_cases_with_links_and_dates():
    incidents = load_seed_incidents()
    assert len(incidents) >= 3
    ids = [(incident.source, incident.incident_id) for incident in incidents]
    assert len(ids) == len(set(ids))
    for incident in incidents:
        assert incident.source == "euvsdisinfo"
        assert incident.title and incident.summary and incident.published_at and incident.license
        assert str(incident.url).startswith("https://euvsdisinfo.eu/report/")


def test_ensure_seed_corpus_skips_existing_and_duplicates(monkeypatch):
    documents = load_seed_documents()[:3]
    existing_id = documents[0].source.document_id
    duplicate_id = documents[2].source.document_id
    ingested: list[str] = []

    async def active_chunk_ids(document_id):
        return ["chunk"] if document_id == existing_id else []

    async def fake_ingest(document, models, store, allow_near_duplicate=False):
        assert allow_near_duplicate is True
        if document.source.document_id == duplicate_id:
            raise DuplicateDocumentError(document.source.document_id, "other-document")
        ingested.append(document.source.document_id)

    monkeypatch.setattr(seed, "load_seed_documents", lambda: documents)
    monkeypatch.setattr(seed.db, "active_chunk_ids_for_document", active_chunk_ids)
    monkeypatch.setattr(seed, "ingest_document", fake_ingest)

    report = asyncio.run(seed.ensure_seed_corpus(models=None, store=None))

    assert report.indexed == 1
    assert report.already_present == 1
    assert report.skipped_duplicates == 1
    assert report.failed == 0
    assert ingested == [documents[1].source.document_id]
