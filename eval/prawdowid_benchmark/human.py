import csv
import random
from pathlib import Path

from prawdowid_benchmark.judge import JudgeRecord
from prawdowid_benchmark.metrics import LABEL_ABSTAIN, BenchmarkMetrics, ClaimOutcome, cohen_kappa

RANDOM_PER_GOLD = 10
COLUMNS = [
    "id",
    "claimText",
    "gold",
    "goldRating",
    "reviewer",
    "reviewUrl",
    "systemVerdict",
    "justification",
    "missing",
    "sources",
    "latencyMs",
    "judgeAssessment",
    "judgeRationale",
    "whySampled",
    "reviewerName",
    "verdictCorrect",
    "abstentionJustified",
    "citationSupports",
    "explanationClear",
    "harmful",
    "notes",
]
YES = {"tak", "t", "yes", "y", "1"}
NO = {"nie", "n", "no", "0"}
PARTIAL = {"częściowo", "czesciowo", "partial"}
HUMAN_OK = "ok"
HUMAN_WRONG = "wrong"


def _sources_text(outcome: ClaimOutcome) -> str:
    body = outcome.record.body or {}
    claims = body.get("claims") or []
    if not claims:
        return ""
    return " || ".join(
        f"[{source.get('role')}] {source.get('title')} ({source.get('publisher')}) {source.get('url')} "
        f"cytat: {source.get('quote')}"
        for source in claims[0].get("sources", [])
    )


def select_sample(
    metrics: BenchmarkMetrics, judge_records: list[JudgeRecord], seed: int
) -> list[tuple[ClaimOutcome, str]]:
    """
    Every disagreement between judge and rules, every judge instability, every harmful answer, plus a random
    RANDOM_PER_GOLD per gold class. The reason stays in the sheet so reviewers know why they see a row.
    """
    reasons: dict[str, list[str]] = {}
    for claim_id in metrics.judge_disagreements:
        reasons.setdefault(claim_id, []).append("sędzia i reguły się nie zgadzają")
    for claim_id in metrics.judge_unstable:
        reasons.setdefault(claim_id, []).append("sędzia niestabilny")
    for outcome in metrics.outcomes:
        if outcome.harmful:
            reasons.setdefault(outcome.claim.id, []).append("szkodliwa odpowiedź")
    shuffler = random.Random(seed)
    by_gold: dict[str, list[ClaimOutcome]] = {}
    for outcome in metrics.outcomes:
        by_gold.setdefault(outcome.claim.gold, []).append(outcome)
    for gold, outcomes in by_gold.items():
        ordered = sorted(outcomes, key=lambda o: o.claim.id)
        shuffler.shuffle(ordered)
        for outcome in [o for o in ordered if o.claim.id not in reasons][:RANDOM_PER_GOLD]:
            reasons.setdefault(outcome.claim.id, []).append(f"losowo z klasy {gold}")
    by_id = {outcome.claim.id: outcome for outcome in metrics.outcomes}
    return [(by_id[claim_id], "; ".join(why)) for claim_id, why in sorted(reasons.items()) if claim_id in by_id]


def write_sample(path: Path, sample: list[tuple[ClaimOutcome, str]], judge_records: list[JudgeRecord]) -> None:
    first_judgement = {}
    for record in judge_records:
        if record.assessment is not None and record.claim_id not in first_judgement:
            first_judgement[record.claim_id] = record.assessment
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for outcome, why in sample:
            body = outcome.record.body or {}
            first = (body.get("claims") or [{}])[0] if body.get("status") == "ok" else {}
            judged = first_judgement.get(outcome.claim.id)
            writer.writerow(
                {
                    "id": outcome.claim.id,
                    "claimText": outcome.claim.claim_text,
                    "gold": outcome.claim.gold,
                    "goldRating": outcome.claim.gold_rating,
                    "reviewer": outcome.claim.reviewer,
                    "reviewUrl": outcome.claim.review_url,
                    "systemVerdict": outcome.verdict or f"status: {body.get('status', 'brak odpowiedzi')}",
                    "justification": first.get("justification") or body.get("message") or "",
                    "missing": first.get("missing") or "",
                    "sources": _sources_text(outcome),
                    "latencyMs": outcome.record.elapsed_ms,
                    "judgeAssessment": judged.verdictAssessment if judged else "",
                    "judgeRationale": judged.rationale if judged else "",
                    "whySampled": why,
                }
            )


def read_sample(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _human_verdict(row: dict) -> str | None:
    answer = row.get("verdictCorrect", "").strip().casefold()
    if answer in YES:
        return HUMAN_OK
    if answer in NO:
        return HUMAN_WRONG
    if answer in PARTIAL:
        return HUMAN_OK
    return None


def _judge_verdict(row: dict) -> str | None:
    judged = row.get("judgeAssessment", "")
    if not judged:
        return None
    return HUMAN_OK if judged in ("correct", "abstainedJustified") else HUMAN_WRONG


def _yes_rate(rows: list[dict], column: str) -> float | None:
    answers = [row.get(column, "").strip().casefold() for row in rows]
    counted = [answer in YES for answer in answers if answer in YES | NO]
    return sum(counted) / len(counted) if counted else None


def human_metrics(rows: list[dict]) -> dict:
    """Human results and how far the LLM judge is from them; rows without a verdictCorrect answer are unreviewed."""
    reviewed = [row for row in rows if _human_verdict(row) is not None]
    pairs = [(_human_verdict(row), _judge_verdict(row)) for row in reviewed if _judge_verdict(row) is not None]
    scores = [int(row["explanationClear"]) for row in reviewed if row.get("explanationClear", "").strip().isdigit()]
    disagreements = [
        row["id"] for row in reviewed if _judge_verdict(row) and _human_verdict(row) != _judge_verdict(row)
    ]
    return {
        "rows": len(rows),
        "reviewed": len(reviewed),
        "verdictCorrect": sum(1 for row in reviewed if _human_verdict(row) == HUMAN_OK) / len(reviewed)
        if reviewed
        else None,
        "abstentionJustified": _yes_rate(reviewed, "abstentionJustified"),
        "citationSupports": _yes_rate(reviewed, "citationSupports"),
        "explanationClear": sum(scores) / len(scores) if scores else None,
        "harmful": _yes_rate(reviewed, "harmful"),
        "agreementWithJudge": sum(1 for first, second in pairs if first == second) / len(pairs) if pairs else None,
        "kappaWithJudge": cohen_kappa(pairs),
        "disagreements": disagreements,
        "abstainRows": sum(
            1 for row in reviewed if row.get("systemVerdict") in ("insufficient_evidence", "not_verifiable")
        ),
        "abstainLabel": LABEL_ABSTAIN,
    }
