import asyncio
import math
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.config import settings
from app.embeddings import EmbeddingModels
from app.vector_store import RawPoint, VectorStore

# Unresolved citizen questions, grouped into cases for the moderator (closed information loop from the brief).
REPORTS_COLLECTION_NAME = "unresolved_reports"
# Nearest earlier reports compared with the cross-encoder; a paraphrase is among the top few in hybrid search.
REPORT_CANDIDATES = 5
# The cross-encoder is not symmetric, so the lower of both directions is used. Measured on paraphrases of the mentor's
# scenario H (lowest 0.68) and same-topic questions about something else (highest 0.56, e.g. Pcim vs Kraków).
REPORT_MATCH_MIN_SCORE = 0.65


def _relevance(logit: float) -> float:
    return 1.0 / (1.0 + math.exp(-logit / settings.rerank_score_temperature))


def _symmetric_scores(models: EmbeddingModels, claim: str, texts: list[str]) -> list[float]:
    forward = [_relevance(logit) for logit in models.rerank(claim, texts)]
    backward = [_relevance(models.rerank(text, [claim])[0]) for text in texts]
    return [min(one, other) for one, other in zip(forward, backward, strict=True)]


async def match_report(claim: str, models: EmbeddingModels, reports: VectorStore) -> tuple[UUID, bool, float | None]:
    """
    Assigns the claim to the case of the most similar earlier report, or opens a new case.
    Every report is stored, so later paraphrases can match any of them. Returns (case id, matched, score).
    The claim arrives masked by the backend; only the claim text and the case id are kept.
    """
    dense, lexical = await asyncio.to_thread(models.embed_queries, [claim])
    candidates = await reports.hybrid_search(dense[0], lexical[0], REPORT_CANDIDATES, None)
    case_id, matched, best = uuid4(), False, None
    if candidates:
        scores = await asyncio.to_thread(_symmetric_scores, models, claim, [hit.text for hit in candidates])
        best_index = max(range(len(scores)), key=scores.__getitem__)
        best = scores[best_index]
        if best >= REPORT_MATCH_MIN_SCORE:
            case_id, matched = UUID(candidates[best_index].payload["case_id"]), True
    stored_dense, stored_lexical = await asyncio.to_thread(models.embed_documents, [claim])
    await reports.upsert_raw(
        [
            RawPoint(
                point_id=uuid4(),
                dense=stored_dense[0],
                lexical=stored_lexical[0],
                payload={"text": claim, "case_id": str(case_id), "created_at": datetime.now(UTC).isoformat()},
            )
        ]
    )
    return case_id, matched, best
