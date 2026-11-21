from uuid import uuid4

from app.config import settings
from app.incidents import build_campaign_alert, incident_point_id
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
