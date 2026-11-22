from pathlib import Path

from prawdowid_benchmark.dataset import BenchmarkClaim
from prawdowid_benchmark.human import RANDOM_PER_GOLD, human_metrics, read_sample, select_sample, write_sample
from prawdowid_benchmark.judge import JudgeAssessment, JudgeRecord
from prawdowid_benchmark.metrics import compute_metrics
from prawdowid_eval.runner import RunRecord


def _claim(index: int, gold: str) -> BenchmarkClaim:
    return BenchmarkClaim(
        id=f"c{index}",
        claim_text=f"Twierdzenie {index}.",
        gold=gold,
        gold_rating=gold,
        reviewer="Demagog",
        review_url="https://d.pl/x",
        topic="t",
    )


def _record(claim_id: str, verdict: str) -> RunRecord:
    body = {
        "status": "ok",
        "claims": [
            {
                "text": "x",
                "verdict": verdict,
                "justification": "j",
                "missing": None,
                "sources": [],
                "evidenceStrength": "none",
                "strengthReasons": [],
            }
        ],
        "meta": {},
        "limitations": [],
    }
    return RunRecord(case_id=claim_id, repeat=0, http_status=200, elapsed_ms=10, body=body, error=None)


def _judged(claim_id: str, assessment: str) -> JudgeRecord:
    return JudgeRecord(
        claim_id=claim_id,
        repeat=0,
        model="m",
        error=None,
        assessment=JudgeAssessment(
            verdictAssessment=assessment, harmful=False, citationSupport="none", explanationQuality=1, rationale="r"
        ),
    )


def test_sample_takes_disagreements_harmful_and_random_per_gold(tmp_path: Path):
    claims = [_claim(index, "false") for index in range(30)] + [_claim(100 + index, "confirmed") for index in range(5)]
    records = [_record(claim.id, "false") for claim in claims[:29]] + [_record("c29", "confirmed")]  # c29 harmful
    records += [_record(claim.id, "confirmed") for claim in claims[30:]]
    judged = [_judged("c0", "incorrect")]  # disagrees with rules
    metrics = compute_metrics(claims, records, judged)
    sample = select_sample(metrics, judged, seed=3)
    reasons = dict((outcome.claim.id, why) for outcome, why in sample)
    assert "sędzia i reguły się nie zgadzają" in reasons["c0"] and "szkodliwa odpowiedź" in reasons["c29"]
    assert sum(1 for why in reasons.values() if why.startswith("losowo z klasy false")) == RANDOM_PER_GOLD
    assert sum(1 for why in reasons.values() if why.startswith("losowo z klasy confirmed")) == 5

    path = tmp_path / "human_review.csv"
    write_sample(path, sample, judged)
    rows = read_sample(path)
    assert len(rows) == len(sample) and rows[0]["judgeAssessment"] == "incorrect"


def test_human_metrics_and_agreement_with_judge():
    rows = [
        {
            "id": "c0",
            "systemVerdict": "false",
            "judgeAssessment": "correct",
            "verdictCorrect": "tak",
            "citationSupports": "tak",
            "explanationClear": "3",
            "harmful": "nie",
            "abstentionJustified": "n.d.",
        },
        {
            "id": "c1",
            "systemVerdict": "confirmed",
            "judgeAssessment": "correct",
            "verdictCorrect": "nie",
            "citationSupports": "nie",
            "explanationClear": "1",
            "harmful": "tak",
            "abstentionJustified": "n.d.",
        },
        {
            "id": "c2",
            "systemVerdict": "insufficient_evidence",
            "judgeAssessment": "abstainedJustified",
            "verdictCorrect": "częściowo",
            "abstentionJustified": "tak",
            "citationSupports": "n.d.",
            "explanationClear": "2",
            "harmful": "nie",
        },
        {
            "id": "c3",
            "systemVerdict": "false",
            "judgeAssessment": "incorrect",
            "verdictCorrect": "",
            "citationSupports": "",
            "explanationClear": "",
            "harmful": "",
        },
    ]
    results = human_metrics(rows)
    assert results["reviewed"] == 3 and results["verdictCorrect"] == 2 / 3
    assert results["citationSupports"] == 0.5 and results["harmful"] == 1 / 3 and results["explanationClear"] == 2
    assert results["abstentionJustified"] == 1.0
    assert results["agreementWithJudge"] == 2 / 3 and results["disagreements"] == ["c1"]
