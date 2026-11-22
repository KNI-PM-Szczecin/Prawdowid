import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from prawdowid_benchmark.dataset import BenchmarkClaim
from prawdowid_benchmark.judge import CompareRecord, JudgeRecord
from prawdowid_eval.metrics import macro_f1
from prawdowid_eval.runner import RunRecord

POSITIVE_VERDICTS = {"false", "misleading"}
NEGATIVE_VERDICTS = {"confirmed"}
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
NOT_VERIFIABLE = "not_verifiable"
ABSTAIN_VERDICTS = {INSUFFICIENT_EVIDENCE, NOT_VERIFIABLE}
FOUR_CLASS = ("confirmed", "false", "misleading", "not_verifiable")
OK_STATUS = "ok"
LABEL_POSITIVE = "positive"
LABEL_NEGATIVE = "negative"
LABEL_ABSTAIN = "abstain"
LABEL_ERROR = "error"
P90 = 0.9
PER_HUNDRED = 100
Z_95 = 1.96
JUDGE_OK = {"correct", "abstainedJustified"}


@dataclass(frozen=True)
class Confusion:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def decided(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def accuracy(self) -> float | None:
        return (self.tp + self.tn) / self.decided if self.decided else None

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        if self.precision is None or self.recall is None or self.precision + self.recall == 0:
            return None
        return 2 * self.precision * self.recall / (self.precision + self.recall)


@dataclass(frozen=True)
class ClaimOutcome:
    claim: BenchmarkClaim
    record: RunRecord
    verdict: str | None
    system_label: str
    gold_label: str | None
    self_reference: bool

    @property
    def correct_4class(self) -> bool | None:
        """Four-class correctness; None for errors and for insufficient_evidence, which is no class but a pass."""
        if self.verdict is None or self.verdict == INSUFFICIENT_EVIDENCE:
            return None
        return self.verdict == self.claim.gold

    @property
    def harmful(self) -> bool:
        return self.gold_label == LABEL_POSITIVE and self.system_label == LABEL_NEGATIVE

    @property
    def abstained(self) -> bool:
        """insufficient_evidence always; not_verifiable only when the gold label is a factual class."""
        if self.verdict == INSUFFICIENT_EVIDENCE:
            return True
        return self.verdict == NOT_VERIFIABLE and self.claim.gold != NOT_VERIFIABLE


@dataclass
class BenchmarkMetrics:
    claims_total: int
    outcomes: list[ClaimOutcome]
    confusion: Confusion
    confusion_without_self_reference: Confusion
    accuracy_4class: float | None
    macro_f1_4class: float | None
    decided_share: float | None
    abstain_rate: float | None
    abstain_on_positive: float | None
    abstain_on_negative: float | None
    harmful_count: int
    error_count: int
    latency: dict[str, float | None]
    server_latency_median_ms: float | None
    cost_mean_usd: float | None
    cost_per_100_usd: float | None
    self_reference_rate: float | None
    stability: float | None
    by_gold: dict[str, dict[str, int]] = field(default_factory=dict)
    by_reviewer: dict[str, dict[str, int]] = field(default_factory=dict)
    by_topic: dict[str, dict[str, int]] = field(default_factory=dict)
    judge: dict[str, float | None] | None = None
    judge_disagreements: list[str] = field(default_factory=list)
    judge_unstable: list[str] = field(default_factory=list)


def _first_claim(body: dict | None) -> dict | None:
    if not body or body.get("status") != OK_STATUS or not body.get("claims"):
        return None
    return body["claims"][0]


def system_label(record: RunRecord) -> tuple[str | None, str]:
    """The system's verdict for the first claim and its three-state reading (positive, negative, abstain, error)."""
    claim = _first_claim(record.body)
    if claim is None:
        return None, LABEL_ERROR
    verdict = claim.get("verdict")
    if verdict in POSITIVE_VERDICTS:
        return verdict, LABEL_POSITIVE
    if verdict in NEGATIVE_VERDICTS:
        return verdict, LABEL_NEGATIVE
    if verdict in ABSTAIN_VERDICTS:
        return verdict, LABEL_ABSTAIN
    return verdict, LABEL_ERROR


def gold_label(gold: str) -> str | None:
    if gold in POSITIVE_VERDICTS:
        return LABEL_POSITIVE
    if gold in NEGATIVE_VERDICTS:
        return LABEL_NEGATIVE
    return None


def _same_page(url_a: str, url_b: str) -> bool:
    first, second = urlsplit(url_a), urlsplit(url_b)
    return (first.netloc.removeprefix("www."), first.path.rstrip("/")) == (
        second.netloc.removeprefix("www."),
        second.path.rstrip("/"),
    )


def self_reference(record: RunRecord, claim: BenchmarkClaim) -> bool:
    """True when the system cited the very fact-check the gold label comes from."""
    first = _first_claim(record.body)
    if first is None:
        return False
    return any(_same_page(source.get("url") or "", claim.review_url) for source in first.get("sources", []))


def evaluate(claims: list[BenchmarkClaim], records: list[RunRecord]) -> list[ClaimOutcome]:
    first_runs = {record.case_id: record for record in records if record.repeat == 0}
    outcomes = []
    for claim in claims:
        record = first_runs.get(claim.id)
        if record is None:
            continue
        verdict, label = system_label(record)
        outcomes.append(
            ClaimOutcome(claim, record, verdict, label, gold_label(claim.gold), self_reference(record, claim))
        )
    return outcomes


def confusion(outcomes: list[ClaimOutcome]) -> Confusion:
    counts = Counter()
    for outcome in outcomes:
        if outcome.gold_label is None or outcome.system_label in (LABEL_ABSTAIN, LABEL_ERROR):
            continue
        key = {
            (LABEL_POSITIVE, LABEL_POSITIVE): "tp",
            (LABEL_NEGATIVE, LABEL_POSITIVE): "fp",
            (LABEL_NEGATIVE, LABEL_NEGATIVE): "tn",
            (LABEL_POSITIVE, LABEL_NEGATIVE): "fn",
        }[(outcome.gold_label, outcome.system_label)]
        counts[key] += 1
    return Confusion(**counts)


def _rate(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def latency_stats(values: list[int]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "p90": None, "max": None}
    ordered = sorted(values)
    return {
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p90": ordered[min(len(ordered) - 1, math.ceil(P90 * len(ordered)) - 1)],
        "max": ordered[-1],
    }


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Agreement between two raters beyond chance; None without pairs, 1.0 when both never vary and agree."""
    if not pairs:
        return None
    observed = sum(1 for first, second in pairs if first == second) / len(pairs)
    labels = {label for pair in pairs for label in pair}
    expected = sum(
        (sum(1 for first, _ in pairs if first == label) / len(pairs))
        * (sum(1 for _, second in pairs if second == label) / len(pairs))
        for label in labels
    )
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return (observed - expected) / (1 - expected)


def _breakdown(outcomes: list[ClaimOutcome], key) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter] = defaultdict(Counter)
    for outcome in outcomes:
        bucket = grouped[key(outcome)]
        bucket["n"] += 1
        bucket["correct"] += outcome.correct_4class is True
        bucket["abstain"] += outcome.abstained
        bucket["harmful"] += outcome.harmful
        bucket["error"] += outcome.system_label == LABEL_ERROR
    return {name: dict(counter) for name, counter in sorted(grouped.items())}


def _fingerprint(record: RunRecord) -> tuple:
    claim = _first_claim(record.body)
    status = record.body.get("status") if record.body else None
    return (status, claim.get("verdict") if claim else None)


def judge_summary(outcomes: list[ClaimOutcome], judge_records: list[JudgeRecord]) -> tuple[dict, list[str], list[str]]:
    """Aggregates the judge and compares it with the rule-based reading of the same answers."""
    by_claim: dict[str, list[JudgeRecord]] = defaultdict(list)
    for record in judge_records:
        by_claim[record.claim_id].append(record)
    assessments = [record.assessment for record in judge_records if record.assessment is not None]
    unstable = sorted(
        claim_id
        for claim_id, records in by_claim.items()
        if len({record.assessment.verdictAssessment for record in records if record.assessment}) > 1
    )
    kappa_pairs: list[tuple[str, str]] = []
    disagreements: list[str] = []
    for outcome in outcomes:
        first = next((record.assessment for record in by_claim.get(outcome.claim.id, []) if record.assessment), None)
        if first is None or outcome.correct_4class is None:
            continue
        rule = "ok" if outcome.correct_4class else "wrong"
        judged = "ok" if first.verdictAssessment in JUDGE_OK else "wrong"
        kappa_pairs.append((rule, judged))
        if rule != judged:
            disagreements.append(outcome.claim.id)
    with_sources = [a for a in assessments if a.citationSupport != "none"]
    abstentions = [a for a in assessments if a.verdictAssessment.startswith("abstained")]
    summary = {
        "graded": len(assessments),
        "errors": sum(1 for record in judge_records if record.assessment is None),
        "verdictOk": _rate([a.verdictAssessment in JUDGE_OK for a in assessments]),
        "abstainedJustified": _rate([a.verdictAssessment == "abstainedJustified" for a in abstentions]),
        "citationSupports": _rate([a.citationSupport == "supports" for a in with_sources]),
        "explanationQuality": statistics.fmean(a.explanationQuality for a in assessments) if assessments else None,
        "harmful": _rate([a.harmful for a in assessments]),
        "agreementWithRules": _rate([first == second for first, second in kappa_pairs]),
        "kappaWithRules": cohen_kappa(kappa_pairs),
        "inputTokens": sum(record.input_tokens for record in judge_records),
        "outputTokens": sum(record.output_tokens for record in judge_records),
    }
    return summary, disagreements, unstable


def compute_metrics(
    claims: list[BenchmarkClaim], records: list[RunRecord], judge_records: list[JudgeRecord] | None = None
) -> BenchmarkMetrics:
    outcomes = evaluate(claims, records)
    decided = [o for o in outcomes if o.correct_4class is not None]
    positives = [o for o in outcomes if o.gold_label == LABEL_POSITIVE]
    negatives = [o for o in outcomes if o.gold_label == LABEL_NEGATIVE]
    latencies = [record.elapsed_ms for record in records if record.body is not None]
    server_latencies = [
        record.body["meta"]["latencyMs"]
        for record in records
        if record.body and record.body.get("meta", {}).get("latencyMs") is not None
    ]
    costs = [
        outcome.record.body["meta"]["estimatedCostUsd"]
        for outcome in outcomes
        if outcome.record.body and outcome.record.body.get("meta", {}).get("estimatedCostUsd") is not None
    ]
    repeats: dict[str, list[tuple]] = defaultdict(list)
    for record in records:
        repeats[record.case_id].append(_fingerprint(record))
    stability = [len(set(prints)) == 1 for prints in repeats.values() if len(prints) > 1]
    judge, disagreements, unstable = judge_summary(outcomes, judge_records) if judge_records else (None, [], [])
    return BenchmarkMetrics(
        claims_total=len(claims),
        outcomes=outcomes,
        confusion=confusion(outcomes),
        confusion_without_self_reference=confusion([o for o in outcomes if not o.self_reference]),
        accuracy_4class=_rate([o.correct_4class for o in decided]),
        macro_f1_4class=macro_f1([(o.claim.gold, o.verdict) for o in decided]),
        decided_share=_rate([o.correct_4class is not None for o in outcomes]),
        abstain_rate=_rate([o.abstained for o in outcomes]),
        abstain_on_positive=_rate([o.abstained for o in positives]),
        abstain_on_negative=_rate([o.abstained for o in negatives]),
        harmful_count=sum(o.harmful for o in outcomes),
        error_count=sum(o.system_label == LABEL_ERROR for o in outcomes),
        latency=latency_stats(latencies),
        server_latency_median_ms=statistics.median(server_latencies) if server_latencies else None,
        cost_mean_usd=statistics.fmean(costs) if costs else None,
        cost_per_100_usd=statistics.fmean(costs) * PER_HUNDRED if costs else None,
        self_reference_rate=_rate([o.self_reference for o in decided]),
        stability=_rate(stability),
        by_gold=_breakdown(outcomes, lambda o: o.claim.gold),
        by_reviewer=_breakdown(outcomes, lambda o: o.claim.reviewer),
        by_topic=_breakdown(outcomes, lambda o: o.claim.topic),
        judge=judge,
        judge_disagreements=disagreements,
        judge_unstable=unstable,
    )


@dataclass(frozen=True)
class CompareMetrics:
    pairs: int
    wins_a: int
    wins_b: int
    ties: int
    inconsistent: int
    errors: int
    win_rate_a: float | None
    win_rate_ci: tuple[float, float] | None
    position_bias: float | None


def wilson_interval(successes: int, trials: int) -> tuple[float, float] | None:
    if trials == 0:
        return None
    proportion = successes / trials
    denominator = 1 + Z_95**2 / trials
    centre = (proportion + Z_95**2 / (2 * trials)) / denominator
    half_width = Z_95 * math.sqrt(proportion * (1 - proportion) / trials + Z_95**2 / (4 * trials**2)) / denominator
    return max(0.0, centre - half_width), min(1.0, centre + half_width)


def compare_metrics(records: list[CompareRecord]) -> CompareMetrics:
    """
    A claim counts as a win only when both orders agree; disagreement between A/B and B/A is position bias,
    reported separately. The win rate is wins_a / (wins_a + wins_b) with a 95% Wilson interval.
    """
    by_claim: dict[str, dict[str, CompareRecord]] = defaultdict(dict)
    for record in records:
        by_claim[record.claim_id][record.order] = record
    wins_a = wins_b = ties = inconsistent = errors = 0
    first_order_prefers_first = 0
    judged_orders = 0
    for orders in by_claim.values():
        ab, ba = orders.get("AB"), orders.get("BA")
        if ab is None or ba is None or ab.preferred is None or ba.preferred is None:
            errors += 1
            continue
        judged_orders += 2
        first_order_prefers_first += (ab.preferred == "a") + (ba.preferred == "b")
        if ab.preferred != ba.preferred:
            inconsistent += 1
        elif ab.preferred == "a":
            wins_a += 1
        elif ab.preferred == "b":
            wins_b += 1
        else:
            ties += 1
    decided = wins_a + wins_b
    return CompareMetrics(
        pairs=len(by_claim),
        wins_a=wins_a,
        wins_b=wins_b,
        ties=ties,
        inconsistent=inconsistent,
        errors=errors,
        win_rate_a=wins_a / decided if decided else None,
        win_rate_ci=wilson_interval(wins_a, decided),
        position_bias=first_order_prefers_first / judged_orders if judged_orders else None,
    )
