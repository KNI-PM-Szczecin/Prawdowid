import asyncio
import json
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from app.config import settings
from app.embeddings import EmbeddingModels
from app.models import CAMPAIGN_CATEGORY, CampaignAlert, IncidentIn, IncidentMatch
from app.vector_store import RawPoint, RetrievedChunk, VectorStore

CATALOG_STATUS_NAME = "incident_catalog"
SEED_INCIDENTS_PATH = Path(__file__).parent / "data" / "seed_incidents.json"
SOURCE_LABELS = {"euvsdisinfo": "EUvsDisinfo"}
CAMPAIGN_MESSAGE = (
    "Podobne twierdzenie pojawiło się w znanej kampanii dezinformacyjnej ({sources}). "
    "To informacja o kontekście, a nie ocena prawdziwości zgłoszenia."
)


def load_seed_incidents() -> list[IncidentIn]:
    """Small starter catalog (real EUvsDisinfo cases) so scenario I works without a token or a background sync."""
    payload = json.loads(SEED_INCIDENTS_PATH.read_text(encoding="utf-8"))
    return [IncidentIn.model_validate(item) for item in payload["incidents"]]


async def ensure_seed_incidents(models: EmbeddingModels, store: VectorStore) -> int:
    """
    Upserts the seed catalog entries at every startup (idempotent: a case always keeps the same point id).
    Seeding only an empty catalog is not enough: an EUvsDisinfo import can run before the first seed load
    and then the demo-critical cases would never arrive, because they fall outside the newest-N window.
    """
    seeded = await index_incidents(load_seed_incidents(), models, store)
    return seeded


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


def rerank_texts(hit: RetrievedChunk) -> tuple[str, str]:
    """
    Two variants of one catalog entry for the cross-encoder; the caller keeps the better score.
    EUvsDisinfo claims are long paragraphs; the cross-encoder cost grows with length (10 long texts ≈ 2 s on CPU),
    and the campaign thesis is in the opening sentences, so only the head is scored. The thesis alone suits imported
    titles that read like labels ("campaign about X"); title + thesis suits titles that state the claim, where the
    thesis alone is worded differently (the Ust-Ługa case: 0.65 without the title, 0.93 with it).
    """
    limit = settings.incident_summary_max_chars
    head = hit.text[:limit]
    title = (hit.payload.get("title") or "").strip()
    with_title = f"{title}. {hit.text}"[:limit] if title else head
    return head, with_title


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
