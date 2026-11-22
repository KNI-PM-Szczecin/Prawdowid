import logging

from app import db
from app.config import settings
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

FOREIGN_DATABASE_MESSAGE = (
    "This database belongs to another Qdrant (owner {owner}, this Qdrant {own}). Sharing it would make every "
    "re-ingest here invalidate the other environment's vectors and empty its search results. Point rag/ at its own "
    "database (docker compose profile local-db, or RAG_POSTGRES_DSN). If this Qdrant should own the database, for "
    "example after its volume was wiped, start once with RAG_CLAIM_DATABASE=true."
)


class ForeignDatabaseError(RuntimeError):
    """The database is owned by a different Qdrant; starting would corrupt that environment's corpus."""


async def ensure_database_owner(store: VectorStore) -> None:
    """
    Refuses to start when PostgreSQL is owned by another Qdrant. The first Qdrant to start on a database claims it;
    RAG_CLAIM_DATABASE=true hands it over explicitly.
    """
    own = await store.instance_id()
    owner = await db.claim_database(own, take_over=settings.claim_database)
    if owner != own:
        raise ForeignDatabaseError(FOREIGN_DATABASE_MESSAGE.format(owner=owner, own=own))
    logger.info("Database owned by this Qdrant (%s)%s", own, ", claimed on request" if settings.claim_database else "")
