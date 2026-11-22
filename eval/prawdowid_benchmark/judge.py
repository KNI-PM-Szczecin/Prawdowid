import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol

import anthropic
from pydantic import BaseModel, Field

from prawdowid_benchmark.dataset import BenchmarkClaim, BenchmarkModel
from prawdowid_eval.runner import RunRecord

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "benchmark" / "prompts"
JUDGE_SYSTEM_PROMPT = PROMPTS_DIR / "judge.system.md"
COMPARE_SYSTEM_PROMPT = PROMPTS_DIR / "compare.system.md"
DEFAULT_JUDGE_MODEL = "claude-opus-5-5"
JUDGE_MODEL_ENV = "JUDGE_MODEL"
# Grading a short answer against a known label is routine work; medium effort keeps the judge fast and cheap.
JUDGE_EFFORT = "medium"
JUDGE_MAX_TOKENS = 4000
JUDGE_ATTEMPTS = 2
QUOTE_MAX_CHARS = 400
ORDER_AB = "AB"
ORDER_BA = "BA"

VerdictAssessment = Literal["correct", "incorrect", "abstainedJustified", "abstainedUnjustified", "error"]
CitationSupport = Literal["supports", "contradicts", "unrelated", "none"]
Preference = Literal["A", "B", "tie"]
RunName = Literal["a", "b", "tie"]


class JudgeAssessment(BaseModel):
    verdictAssessment: VerdictAssessment
    harmful: bool
    citationSupport: CitationSupport
    explanationQuality: int = Field(ge=0, le=2)
    rationale: str


class PairPreference(BaseModel):
    preferred: Preference
    rationale: str


class JudgeRecord(BenchmarkModel):
    claim_id: str
    repeat: int
    assessment: JudgeAssessment | None
    error: str | None
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class CompareRecord(BenchmarkModel):
    claim_id: str
    order: Literal["AB", "BA"]
    preferred: RunName | None
    rationale: str | None
    error: str | None
    model: str


class JudgeError(Exception):
    """The judge gave no usable answer; the record keeps the reason and nothing is guessed."""


class JudgeClient(Protocol):
    model: str

    def ask[T: BaseModel](self, system: str, user: str, output_model: type[T]) -> tuple[T, int, int]: ...


class AnthropicJudge:
    """Claude through the official SDK with structured output; a different vendor than the system under test."""

    def __init__(self, model: str | None = None, client: anthropic.Anthropic | None = None) -> None:
        self.model = model or os.environ.get(JUDGE_MODEL_ENV) or DEFAULT_JUDGE_MODEL
        self._client = client or anthropic.Anthropic()

    def ask[T: BaseModel](self, system: str, user: str, output_model: type[T]) -> tuple[T, int, int]:
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=JUDGE_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=output_model,
            output_config={"effort": JUDGE_EFFORT},
        )
        if response.stop_reason == "refusal":
            raise JudgeError("judge refused the request")
        if response.parsed_output is None:
            raise JudgeError(f"judge returned no structured output (stop_reason={response.stop_reason})")
        return response.parsed_output, response.usage.input_tokens, response.usage.output_tokens


def _first_claim(body: dict | None) -> dict | None:
    if not body or body.get("status") != "ok" or not body.get("claims"):
        return None
    return body["claims"][0]


def render_system_answer(record: RunRecord) -> str:
    """The system's answer as the judge sees it; sources are listed verbatim, quotes cut at QUOTE_MAX_CHARS."""
    if record.body is None:
        return f"brak odpowiedzi: {record.error}"
    body = record.body
    claim = _first_claim(body)
    if claim is None:
        return f"status: {body.get('status')}\nkomunikat: {body.get('message')}"
    lines = [
        f"status: {body.get('status')}",
        f"twierdzenie wyodrębnione przez system: {claim.get('text')}",
        f"werdykt: {claim.get('verdict')}",
        f"uzasadnienie: {claim.get('justification')}",
        f"czego nie ustalono: {claim.get('missing')}",
        f"siła podstawy: {claim.get('evidenceStrength')} ({', '.join(claim.get('strengthReasons', []))})",
        f"liczba twierdzeń w odpowiedzi: {len(body.get('claims', []))}",
        f"ograniczenia: {'; '.join(body.get('limitations', [])) or 'brak'}",
        "źródła:",
    ]
    for index, source in enumerate(claim.get("sources", []), start=1):
        quote = (source.get("quote") or "")[:QUOTE_MAX_CHARS]
        lines.append(
            f"  {index}. [{source.get('role')}] {source.get('title')} ({source.get('publisher')}, "
            f"{source.get('sourceType')}, {source.get('publishedAt') or 'bez daty'}) {source.get('url')}\n"
            f'     cytat: "{quote}"'
        )
    if not claim.get("sources"):
        lines.append("  brak")
    return "\n".join(lines)


def render_gold(claim: BenchmarkClaim) -> str:
    return (
        f"etykieta: {claim.gold}\nocena weryfikatora: {claim.gold_rating}\nweryfikator: {claim.reviewer}\n"
        f"tytuł weryfikacji: {claim.review_title}\ndata weryfikacji: {claim.review_date}\nlink: {claim.review_url}"
    )


def render_judge_user(claim: BenchmarkClaim, record: RunRecord) -> str:
    return (
        f"<twierdzenie>\n{claim.claim_text}\n</twierdzenie>\n\n<etykieta_zlota>\n{render_gold(claim)}\n</etykieta_zlota>\n\n"
        f"<odpowiedz_systemu>\n{render_system_answer(record)}\n</odpowiedz_systemu>"
    )


def render_compare_user(claim: BenchmarkClaim, first: RunRecord, second: RunRecord) -> str:
    return (
        f"<twierdzenie>\n{claim.claim_text}\n</twierdzenie>\n\n<etykieta_zlota>\n{render_gold(claim)}\n</etykieta_zlota>\n\n"
        f"<odpowiedz_A>\n{render_system_answer(first)}\n</odpowiedz_A>\n\n"
        f"<odpowiedz_B>\n{render_system_answer(second)}\n</odpowiedz_B>"
    )


def _ask_with_retry[T: BaseModel](
    judge: JudgeClient, system: str, user: str, output_model: type[T]
) -> tuple[T, int, int]:
    last_error: Exception | None = None
    input_tokens = output_tokens = 0
    for _ in range(JUDGE_ATTEMPTS):
        try:
            parsed, used_in, used_out = judge.ask(system, user, output_model)
        except (JudgeError, anthropic.APIError, ValueError) as error:
            last_error = error
            continue
        return parsed, input_tokens + used_in, output_tokens + used_out
    raise JudgeError(f"{type(last_error).__name__}: {last_error}")


def judge_records(
    claims: list[BenchmarkClaim],
    records: list[RunRecord],
    judge: JudgeClient,
    repeats: int,
    progress: Callable[[int, int], None] | None = None,
) -> list[JudgeRecord]:
    """Grades the first run of every claim `repeats` times; each grading is independent (no shared context)."""
    system = JUDGE_SYSTEM_PROMPT.read_text(encoding="utf-8")
    first_runs = {record.case_id: record for record in records if record.repeat == 0}
    results: list[JudgeRecord] = []
    total = len(claims) * repeats
    for claim in claims:
        record = first_runs.get(claim.id)
        if record is None:
            continue
        user = render_judge_user(claim, record)
        for repeat in range(repeats):
            try:
                assessment, used_in, used_out = _ask_with_retry(judge, system, user, JudgeAssessment)
                results.append(
                    JudgeRecord(
                        claim_id=claim.id,
                        repeat=repeat,
                        assessment=assessment,
                        error=None,
                        model=judge.model,
                        input_tokens=used_in,
                        output_tokens=used_out,
                    )
                )
            except JudgeError as error:
                results.append(
                    JudgeRecord(claim_id=claim.id, repeat=repeat, assessment=None, error=str(error), model=judge.model)
                )
            if progress:
                progress(len(results), total)
    return results


def _to_run_name(preferred: Preference, order: str) -> RunName:
    if preferred == "tie":
        return "tie"
    first_is_a = order == ORDER_AB
    return "a" if (preferred == "A") == first_is_a else "b"


def compare_runs(
    claims: list[BenchmarkClaim],
    records_a: list[RunRecord],
    records_b: list[RunRecord],
    judge: JudgeClient,
    progress: Callable[[int, int], None] | None = None,
) -> list[CompareRecord]:
    """
    Pairwise A/B judgement with both orders (A/B and B/A) for every claim, so a preference that depends on
    position shows up as an inconsistency instead of a win. `preferred` is already mapped back to run names.
    """
    system = COMPARE_SYSTEM_PROMPT.read_text(encoding="utf-8")
    first_a = {record.case_id: record for record in records_a if record.repeat == 0}
    first_b = {record.case_id: record for record in records_b if record.repeat == 0}
    results: list[CompareRecord] = []
    total = 2 * sum(1 for claim in claims if claim.id in first_a and claim.id in first_b)
    for claim in claims:
        if claim.id not in first_a or claim.id not in first_b:
            continue
        for order, first, second in (
            (ORDER_AB, first_a[claim.id], first_b[claim.id]),
            (ORDER_BA, first_b[claim.id], first_a[claim.id]),
        ):
            user = render_compare_user(claim, first, second)
            try:
                preference, _, _ = _ask_with_retry(judge, system, user, PairPreference)
                results.append(
                    CompareRecord(
                        claim_id=claim.id,
                        order=order,
                        preferred=_to_run_name(preference.preferred, order),
                        rationale=preference.rationale,
                        error=None,
                        model=judge.model,
                    )
                )
            except JudgeError as error:
                results.append(
                    CompareRecord(
                        claim_id=claim.id,
                        order=order,
                        preferred=None,
                        rationale=None,
                        error=str(error),
                        model=judge.model,
                    )
                )
            if progress:
                progress(len(results), total)
    return results


def load_judge_records(path: Path) -> list[JudgeRecord]:
    return [JudgeRecord.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def load_compare_records(path: Path) -> list[CompareRecord]:
    return [CompareRecord.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
