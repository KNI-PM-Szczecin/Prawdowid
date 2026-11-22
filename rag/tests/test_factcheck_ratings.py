import asyncio
import math
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg
import pytest

from app import db
from app.config import settings
from app.models import Passage
from app.search import add_factcheck_ratings
from app.vector_store import RetrievedChunk

ARTICLE = "fc-article-1"
OTHER_ARTICLE = "fc-article-2"
RATING_TEXT = "Wypowiedź oceniamy jako fałszywą. Fikcyjny raport nie istnieje."
WEAK_RATING_TEXT = "Prawda jest taka, że raport opisano w kilku miejscach."
RATING_LOGIT = 1.0


def _passage(document_id: str, text: str, score: float, source_type: str = "factcheck") -> Passage:
    return Passage(
        document_id=document_id,
        title="Fikcyjna analiza",
        publisher="Weryfikator Przykładowy",
        published_at=datetime(2026, 10, 1, tzinfo=UTC),
        fetched_at=datetime(2026, 11, 1, tzinfo=UTC),
        url=f"https://weryfikator.example/{document_id}",
        license=None,
        source_type=source_type,
        passage=text,
        score=score,
        flags=[],
        chunk_id=uuid4(),
        tier=2,
        reliability="high",
    )


def _row(chunk_id, document_id: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "tier": 2,
        "reliability": "high",
        "document_id": document_id,
        "title": "Fikcyjna analiza",
        "publisher": "Weryfikator Przykładowy",
        "url": f"https://weryfikator.example/{document_id}",
        "published_at": datetime(2026, 10, 1, tzinfo=UTC),
        "fetched_at": datetime(2026, 11, 1, tzinfo=UTC),
        "license": None,
        "source_type": "factcheck",
    }


class FakeStore:
    def __init__(self, chunks_by_document: dict[str, list[RetrievedChunk]], failure: Exception | None = None):
        self._chunks = chunks_by_document
        self._failure = failure
        self.asked: list[str] = []

    async def chunks_containing(self, source_id, phrases, limit):
        if self._failure is not None:
            raise self._failure
        self.asked.append(source_id)
        return self._chunks.get(source_id, [])


class FakeModels:
    def rerank(self, query, documents):
        return [RATING_LOGIT for _ in documents]


@pytest.fixture
def metadata(monkeypatch):
    documents: dict = {}

    async def fetch_passage_metadata(chunk_ids):
        return {chunk_id: _row(chunk_id, documents[chunk_id]) for chunk_id in chunk_ids if chunk_id in documents}

    monkeypatch.setattr(db, "fetch_passage_metadata", fetch_passage_metadata)
    return documents


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=uuid4(), text=text, fusion_score=0.0)


def test_the_rating_chunk_of_a_cited_factcheck_article_is_added(metadata):
    best = _passage(ARTICLE, "Fikcyjny raport rzekomo opisuje nowe przepisy.", 0.9)
    official = _passage("gov-1", "Przepisy nie zmieniły się.", 0.8, source_type="official")
    weak, strong = _chunk(WEAK_RATING_TEXT), _chunk(RATING_TEXT)
    metadata.update({weak.chunk_id: ARTICLE, strong.chunk_id: ARTICLE})
    store = FakeStore({ARTICLE: [weak, strong]})

    results = asyncio.run(add_factcheck_ratings([best, official], "claim", FakeModels(), store))

    assert [result.passage for result in results[:2]] == [best.passage, official.passage]
    assert [result.passage for result in results[2:]] == [RATING_TEXT]
    assert results[2].document_id == ARTICLE
    assert results[2].score == pytest.approx(1 / (1 + math.exp(-RATING_LOGIT / settings.rerank_score_temperature)))
    assert store.asked == [ARTICLE]


def test_an_article_whose_passage_already_states_the_rating_is_left_alone(metadata):
    rated = _passage(ARTICLE, RATING_TEXT, 0.9)
    store = FakeStore({ARTICLE: [_chunk(RATING_TEXT)]})
    assert asyncio.run(add_factcheck_ratings([rated], "claim", FakeModels(), store)) == [rated]
    assert store.asked == []


def test_at_most_one_rating_chunk_per_article_and_none_without_one(metadata):
    first = _passage(ARTICLE, "Opis twierdzenia A.", 0.9)
    second = _passage(OTHER_ARTICLE, "Opis twierdzenia B.", 0.7)
    rating_a, rating_a_again = _chunk(RATING_TEXT), _chunk("Ocena: fałsz. Powtórzenie oceny.")
    metadata.update({rating_a.chunk_id: ARTICLE, rating_a_again.chunk_id: ARTICLE})
    store = FakeStore({ARTICLE: [rating_a_again, rating_a], OTHER_ARTICLE: []})

    results = asyncio.run(add_factcheck_ratings([first, second], "claim", FakeModels(), store))

    assert len(results) == 3
    assert [result.document_id for result in results].count(ARTICLE) == 2


def test_a_database_failure_keeps_the_results_unchanged(metadata):
    passages = [_passage(ARTICLE, "Opis twierdzenia.", 0.9)]
    store = FakeStore({}, failure=asyncpg.PostgresError("down"))
    assert asyncio.run(add_factcheck_ratings(passages, "claim", FakeModels(), store)) == passages
