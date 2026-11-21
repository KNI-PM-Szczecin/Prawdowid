import asyncio
from uuid import NAMESPACE_URL, UUID, uuid5

from app.config import settings
from app.embeddings import EmbeddingModels
from app.models import CAMPAIGN_CATEGORY, CampaignAlert, IncidentIn, IncidentMatch
from app.vector_store import RawPoint, RetrievedChunk, VectorStore

CATALOG_STATUS_NAME = "incident_catalog"
SOURCE_LABELS = {"euvsdisinfo": "EUvsDisinfo"}
CAMPAIGN_MESSAGE = (
    "Podobne twierdzenie pojawiło się w znanej kampanii dezinformacyjnej ({sources}). "
    "To informacja o kontekście, a nie ocena prawdziwości zgłoszenia."
)


def incident_point_id(source: str, incident_id: str) -> UUID:
    """Stable id per catalog entry, so re-importing the same catalog updates points instead of duplicating them."""
    return uuid5(NAMESPACE_URL, f"incident:{source}:{incident_id}")


def incident_text(incident: IncidentIn) -> str:
    """Title + claim for retrieval; the reranker sees only the claim (payload `text`), since meta titles such as
    'campaign about X' lowered the score of a true paraphrase from 0.85 to 0.64 in tests."""
    return f"{incident.title}. {incident.summary}"


async def index_incidents(incidents: list[IncidentIn], models: EmbeddingModels, store: VectorStore) -> int:
    """Embeds and upserts catalog entries; their text is the claim spread by the campaign, used only for matching."""
    texts = [incident_text(incident) for incident in incidents]
    dense_vectors, sparse_vectors = await asyncio.to_thread(models.embed_documents, texts)
    await store.upsert_raw(
        [
            RawPoint(
                point_id=incident_point_id(incident.source, incident.incident_id),
                dense=dense,
                sparse=sparse,
                payload={
                    "text": incident.summary,
                    "incident_id": incident.incident_id,
                    "source": incident.source,
                    "title": incident.title,
                    "summary": incident.summary,
                    "url": str(incident.url),
                    "published_at": incident.published_at.isoformat() if incident.published_at else None,
                    "countries": incident.countries,
                    "languages": incident.languages,
                    "license": incident.license,
                },
            )
            for incident, dense, sparse in zip(incidents, dense_vectors, sparse_vectors, strict=True)
        ]
    )
    return len(incidents)


def _trim(text: str) -> str:
    limit = settings.incident_summary_max_chars
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_campaign_alert(scored: list[tuple[RetrievedChunk, float]]) -> CampaignAlert | None:
    """Keeps only strong matches; None means the claim resembles no known campaign closely enough."""
    strong = sorted((pair for pair in scored if pair[1] >= settings.incident_min_score), key=lambda pair: -pair[1])
    if not strong:
        return None
    matches = [
        IncidentMatch(
            incident_id=chunk.payload["incident_id"],
            source=chunk.payload["source"],
            title=chunk.payload["title"],
            summary=_trim(chunk.payload["summary"]),
            url=chunk.payload["url"],
            published_at=chunk.payload.get("published_at"),
            score=score,
        )
        for chunk, score in strong[: settings.incident_max_matches]
    ]
    sources = ", ".join(sorted({SOURCE_LABELS.get(match.source, match.source) for match in matches}))
    return CampaignAlert(category=CAMPAIGN_CATEGORY, message=CAMPAIGN_MESSAGE.format(sources=sources), matches=matches)
