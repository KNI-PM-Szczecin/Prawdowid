from prawdowid_benchmark.dataset import BenchmarkClaim
from prawdowid_benchmark.judge import CompareRecord, JudgeAssessment, JudgeRecord
from prawdowid_benchmark.metrics import cohen_kappa, compare_metrics, compute_metrics, latency_stats
from prawdowid_eval.runner import RunRecord

REVIEW = "https://demagog.org.pl/fake_news/x/"


def _claim(claim_id: str, gold: str) -> BenchmarkClaim:
    return BenchmarkClaim(
        id=claim_id,
        claim_text=f"Twierdzenie {claim_id} o czymś.",
        gold=gold,
        gold_rating=gold,
        reviewer="Demagog",
        review_url=REVIEW,
        topic="t",
    )


def _record(
    claim_id: str, verdict: str | None, elapsed: int = 1000, sources: list | None = None, repeat: int = 0
) -> RunRecord:
    if verdict is None:
        return RunRecord(
            case_id=claim_id,
            repeat=repeat,
            http_status=503,
            elapsed_ms=elapsed,
            body={"status": "technical_error", "claims": [], "meta": {}},
            error=None,
        )
    body = {
        "status": "ok",
        "claims": [
            {
                "text": "x",
                "verdict": verdict,
                "justification": "j",
                "missing": None,
                "sources": sources or [],
                "evidenceStrength": "strong",
                "strengthReasons": [],
            }
        ],
        "meta": {"latencyMs": elapsed - 100, "estimatedCostUsd": 0.001},
        "limitations": [],
    }
    return RunRecord(case_id=claim_id, repeat=repeat, http_status=200, elapsed_ms=elapsed, body=body, error=None)


CLAIMS = [
    _claim("c1", "false"),
    _claim("c2", "false"),
    _claim("c3", "confirmed"),
    _claim("c4", "misleading"),
    _claim("c5", "not_verifiable"),
    _claim("c6", "confirmed"),
]
RECORDS = [
    _record("c1", "false", 1000, sources=[{"url": "https://www.demagog.org.pl/fake_news/x"}]),  # TP, self-reference
    _record("c2", "confirmed", 2000),  # FN, harmful
    _record("c3", "confirmed", 3000),  # TN
    _record("c4", "insufficient_evidence", 4000),  # abstain on positive
    _record("c5", "not_verifiable", 5000),  # correct 4-class, outside binary
    _record("c6", None, 6000),  # error
]


def test_confusion_abstentions_harm_latency_and_self_reference():
    metrics = compute_metrics(CLAIMS, RECORDS)
    assert vars(metrics.confusion) == {"tp": 1, "fp": 0, "tn": 1, "fn": 1}
    assert vars(metrics.confusion_without_self_reference) == {"tp": 0, "fp": 0, "tn": 1, "fn": 1}
    assert metrics.confusion.accuracy == 2 / 3 and metrics.confusion.recall == 0.5
    assert metrics.harmful_count == 1 and metrics.error_count == 1
    assert metrics.accuracy_4class == 3 / 4  # c1, c3, c5 correct; c2 wrong; c4 abstained; c6 error
    assert metrics.abstain_rate == 1 / 6 and metrics.abstain_on_positive == 1 / 3 and metrics.abstain_on_negative == 0
    assert metrics.self_reference_rate == 1 / 4
    assert metrics.latency == {"mean": 3500, "median": 3500, "p90": 6000, "max": 6000}
    assert metrics.server_latency_median_ms == 2900
    assert metrics.cost_per_100_usd == 0.1
    assert metrics.by_gold["false"] == {"n": 2, "correct": 1, "abstain": 0, "harmful": 1, "error": 0}


def test_stability_uses_repeats_of_the_same_claim():
    records = [*RECORDS, _record("c1", "false", repeat=1), _record("c2", "false", repeat=1)]
    assert compute_metrics(CLAIMS, records).stability == 0.5


def test_judge_summary_agreement_with_rules():
    def judged(claim_id: str, assessment: str, repeat: int = 0, harmful: bool = False) -> JudgeRecord:
        return JudgeRecord(
            claim_id=claim_id,
            repeat=repeat,
            model="m",
            error=None,
            assessment=JudgeAssessment(
                verdictAssessment=assessment,
                harmful=harmful,
                citationSupport="none",
                explanationQuality=1,
                rationale="r",
            ),
        )

    judge_records = [
        judged("c1", "correct"),
        judged("c1", "incorrect", repeat=1),  # unstable
        judged("c2", "incorrect", harmful=True),
        judged("c3", "incorrect"),  # disagrees with rules (rules: correct)
        judged("c4", "abstainedJustified"),
        JudgeRecord(claim_id="c5", repeat=0, model="m", error="timeout", assessment=None),
    ]
    metrics = compute_metrics(CLAIMS, RECORDS, judge_records)
    assert metrics.judge["graded"] == 5 and metrics.judge["errors"] == 1
    assert metrics.judge["harmful"] == 0.2
    assert metrics.judge_unstable == ["c1"] and metrics.judge_disagreements == ["c3"]
    assert metrics.judge["agreementWithRules"] == 2 / 3


def test_latency_stats_and_kappa():
    assert latency_stats([]) == {"mean": None, "median": None, "p90": None, "max": None}
    assert latency_stats([100, 200, 300, 400, 500, 600, 700, 800, 900, 1000])["p90"] == 900
    assert cohen_kappa([("ok", "ok"), ("wrong", "wrong")]) == 1.0
    assert cohen_kappa([("ok", "wrong"), ("wrong", "ok")]) < 0
    assert cohen_kappa([]) is None


def test_compare_counts_only_order_consistent_wins():
    def rec(claim_id: str, order: str, preferred: str | None) -> CompareRecord:
        return CompareRecord(
            claim_id=claim_id,
            order=order,
            preferred=preferred,
            rationale=None,
            error=None if preferred else "x",
            model="m",
        )

    records = [
        rec("c1", "AB", "a"),
        rec("c1", "BA", "a"),  # A wins
        rec("c2", "AB", "b"),
        rec("c2", "BA", "b"),  # B wins
        rec("c3", "AB", "a"),
        rec("c3", "BA", "b"),  # position-dependent
        rec("c4", "AB", "tie"),
        rec("c4", "BA", "tie"),
        rec("c5", "AB", "a"),
        rec("c5", "BA", None),  # judge error
    ]
    metrics = compare_metrics(records)
    assert (metrics.pairs, metrics.wins_a, metrics.wins_b, metrics.ties, metrics.inconsistent, metrics.errors) == (
        5,
        1,
        1,
        1,
        1,
        1,
    )
    assert metrics.win_rate_a == 0.5 and metrics.win_rate_ci is not None
    assert metrics.position_bias == 0.5
