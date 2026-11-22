from pydantic import BaseModel

from prawdowid_benchmark.dataset import BenchmarkClaim
from prawdowid_benchmark.judge import (
    JudgeAssessment,
    JudgeError,
    PairPreference,
    compare_runs,
    judge_records,
    render_judge_user,
    render_system_answer,
)
from prawdowid_eval.runner import RunRecord

CLAIM = BenchmarkClaim(
    id="c1",
    claim_text="Szczepionki powodują autyzm.",
    gold="false",
    gold_rating="Fałsz",
    reviewer="Demagog",
    review_url="https://demagog.org.pl/x",
    review_title="Nie, szczepionki nie powodują autyzmu",
    topic="szczepionki",
)
SOURCE = {
    "role": "refutes",
    "title": "Analiza",
    "publisher": "Demagog",
    "sourceType": "factcheck",
    "url": "https://demagog.org.pl/x",
    "quote": "Badania nie wykazały związku.",
}
RECORD_A = RunRecord(
    case_id="c1",
    repeat=0,
    http_status=200,
    elapsed_ms=900,
    error=None,
    body={
        "status": "ok",
        "claims": [
            {
                "text": "Szczepionki powodują autyzm.",
                "verdict": "false",
                "justification": "Źródło zaprzecza.",
                "missing": None,
                "evidenceStrength": "strong",
                "strengthReasons": ["ocena weryfikatora"],
                "sources": [SOURCE],
            }
        ],
        "limitations": [],
        "meta": {},
    },
)
RECORD_B = RunRecord(
    case_id="c1",
    repeat=0,
    http_status=503,
    elapsed_ms=100,
    error=None,
    body={"status": "technical_error", "message": "awaria", "claims": [], "meta": {}},
)


class ScriptedJudge:
    """Answers from a queue; a None entry raises like a failed API call. Records what it was asked."""

    model = "fake-judge"

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts: list[str] = []

    def ask(self, system: str, user: str, output_model: type[BaseModel]):
        self.prompts.append(user)
        answer = self.answers.pop(0)
        if answer is None:
            raise JudgeError("no answer")
        return output_model.model_validate(answer), 10, 5


def test_prompt_contains_claim_gold_and_system_answer_as_data_blocks():
    user = render_judge_user(CLAIM, RECORD_A)
    assert "<twierdzenie>\nSzczepionki powodują autyzm." in user
    assert "etykieta: false" in user and "ocena weryfikatora: Fałsz" in user
    assert 'cytat: "Badania nie wykazały związku."' in user and "werdykt: false" in user
    assert render_system_answer(RECORD_B).startswith("status: technical_error")


def test_judge_records_retry_once_and_record_errors():
    good = {
        "verdictAssessment": "correct",
        "harmful": False,
        "citationSupport": "supports",
        "explanationQuality": 2,
        "rationale": "ok",
    }
    judge = ScriptedJudge([None, good, None, None])
    results = judge_records([CLAIM], [RECORD_A], judge, repeats=2)
    assert results[0].assessment == JudgeAssessment.model_validate(good) and results[0].input_tokens == 10
    assert results[1].assessment is None and "no answer" in results[1].error
    assert len(judge.prompts) == 4


def test_compare_runs_asks_both_orders_and_maps_preference_back_to_runs():
    judge = ScriptedJudge([{"preferred": "A", "rationale": "x"}, {"preferred": "B", "rationale": "y"}])
    results = compare_runs([CLAIM], [RECORD_A], [RECORD_B], judge)
    assert [(r.order, r.preferred) for r in results] == [("AB", "a"), ("BA", "a")]
    assert (
        "<odpowiedz_A>\nstatus: ok" in judge.prompts[0] and "<odpowiedz_A>\nstatus: technical_error" in judge.prompts[1]
    )
    assert PairPreference(preferred="tie", rationale="r").preferred == "tie"
