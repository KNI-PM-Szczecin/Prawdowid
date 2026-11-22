import asyncio
from uuid import uuid4

from app.config import settings
from app.incidents import build_campaign_alert, ensure_seed_incidents, incident_point_id, load_seed_incidents
from app.vector_store import RetrievedChunk

LONG_SUMMARY_FACTOR = 3


def _hit(incident_id: str, summary: str = "Twierdzenie kampanii.") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        text="tekst",
        fusion_score=1.0,
        payload={
            "incident_id": incident_id,
            "source": "organizer",
            "title": f"Incydent {incident_id}",
            "summary": summary,
            "url": f"https://example.org/{incident_id}",
            "published_at": None,
        },
    )


def test_point_id_is_stable_per_source_and_id():
    assert incident_point_id("euvsdisinfo", "1") == incident_point_id("euvsdisinfo", "1")
    assert incident_point_id("euvsdisinfo", "1") != incident_point_id("organizer", "1")


def test_alert_keeps_strongest_matches_up_to_limit():
    hits = [(_hit(str(index)), 0.71 + index / 100) for index in range(settings.incident_max_matches + 2)]
    alert = build_campaign_alert(hits)
    scores = [match.score for match in alert.matches]
    assert len(alert.matches) == settings.incident_max_matches
    assert scores == sorted(scores, reverse=True)
    assert "(organizer)" in alert.message


def test_no_alert_below_threshold_and_summary_is_trimmed():
    assert build_campaign_alert([(_hit("1"), settings.incident_min_score - 0.01)]) is None
    long_summary = "x" * settings.incident_summary_max_chars * LONG_SUMMARY_FACTOR
    alert = build_campaign_alert([(_hit("1", long_summary), 0.9)])
    assert len(alert.matches[0].summary) == settings.incident_summary_max_chars


CASE_SUMMARY = "Kampania twierdzi, że ZSP i agencja K7 zorganizowały sabotaż w porcie Nowy-Gród."
MEDIUM_SCORE = 0.62


def test_paraphrase_with_shared_names_gets_an_alert_at_a_medium_score():
    claim = "Wojsko ZSP i agencja K7 miały zorganizować sabotaż w porcie Nowy-Gród."
    alert = build_campaign_alert([(_hit("1", CASE_SUMMARY), MEDIUM_SCORE)], claim)
    assert alert is not None and alert.matches[0].incident_id == "1"


def test_true_claim_on_the_topic_gets_no_alert_at_a_medium_score():
    # Only "ZSP" is shared ("Borowo" starts the sentence and is not in the case): one name is too few.
    claim = "Borowo należy do ZSP od 1999 roku."
    assert build_campaign_alert([(_hit("1", CASE_SUMMARY), MEDIUM_SCORE)], claim) is None


def test_sentence_start_word_is_not_counted_as_a_name():
    claim = "Nowy-Gród ma nowy port. Agencja K7 go chwali."
    assert build_campaign_alert([(_hit("1", CASE_SUMMARY), MEDIUM_SCORE)], claim) is None


def test_low_score_never_gets_an_alert_even_with_shared_names():
    claim = "Wojsko ZSP i agencja K7 miały zorganizować sabotaż w porcie Nowy-Gród."
    assert build_campaign_alert([(_hit("1", CASE_SUMMARY), settings.incident_named_min_score - 0.01)], claim) is None


class FakeCatalog:
    def __init__(self):
        self.upserts: list[int] = []

    async def upsert_raw(self, points):
        self.upserts.append(len(points))


class FakeModels:
    def embed_documents(self, texts):
        return [[0.0]] * len(texts), [None] * len(texts)


def test_seed_incidents_are_upserted_even_into_a_filled_catalog():
    catalog = FakeCatalog()

    first = asyncio.run(ensure_seed_incidents(FakeModels(), catalog))
    second = asyncio.run(ensure_seed_incidents(FakeModels(), catalog))

    # A daily EUvsDisinfo import may fill the catalog before the seeds ever load; upserts are idempotent
    # (same point ids), so re-running them at startup costs three embeddings and keeps demo anchors present.
    assert catalog.upserts == [first, second]
    assert first == second == len(load_seed_incidents())
