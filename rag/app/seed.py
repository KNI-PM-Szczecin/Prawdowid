import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app import db
from app.ingest import DuplicateDocumentError, ingest_document
from app.models import DocumentIn

logger = logging.getLogger(__name__)

SEED_DOCUMENTS_PATH = Path(__file__).parent / "data" / "seed_documents.json"


@dataclass
class SeedCorpusReport:
    indexed: int = 0
    already_present: int = 0
    skipped_duplicates: int = 0
    failed: int = 0


def load_seed_documents() -> list[DocumentIn]:
    """Curated demo documents with verbatim excerpts and complete metadata (title, publisher, dates, link, license)."""
    payload = json.loads(SEED_DOCUMENTS_PATH.read_text(encoding="utf-8"))
    return [DocumentIn.model_validate(item) for item in payload["documents"]]


async def ensure_seed_corpus(models, store) -> SeedCorpusReport:
    """
    Indexes missing seed documents one by one after startup. Existing ids are skipped, a bad document never stops
    the rest, and every failure is logged. This keeps the demo corpus stable without fetching live pages at runtime.
    """
    report = SeedCorpusReport()
    for document in load_seed_documents():
        document_id = document.source.document_id
        try:
            existing_chunks = await db.active_chunk_ids_for_document(document_id)
        except Exception:
            report.failed += 1
            logger.exception("Seed document %s could not be checked, skipped", document_id)
            continue
        if existing_chunks:
            report.already_present += 1
            continue
        try:
            # A dated seed excerpt must not lose to an undated page from the scraper (issue #5).
            await ingest_document(document, models, store, allow_near_duplicate=True)
            report.indexed += 1
        except DuplicateDocumentError as error:
            report.skipped_duplicates += 1
            logger.info("Seed document %s duplicates %s, skipped", document_id, error.duplicate_of)
        except Exception:
            report.failed += 1
            logger.exception("Seed document %s failed", document_id)
    return report
