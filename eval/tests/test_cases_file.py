from collections import Counter

from prawdowid_eval.__main__ import DEFAULT_CASES
from prawdowid_eval.cases import load_cases, select_cases

BRIEF_MINIMUM_CASES = 30
REQUIRED_SCENARIOS = set("ABCDEFGHIJ")


def test_case_file_is_valid_and_covers_every_scenario():
    cases = load_cases(DEFAULT_CASES)
    assert len(cases) >= BRIEF_MINIMUM_CASES
    assert {case.scenario for case in cases} == REQUIRED_SCENARIOS


def test_every_verdict_class_has_runnable_cases():
    runnable, _ = select_cases(load_cases(DEFAULT_CASES), set())
    verdicts = Counter(case.expected.verdict for case in runnable)
    for verdict in ("confirmed", "false", "misleading", "insufficient_evidence", "not_verifiable"):
        assert verdicts[verdict] >= 2, verdict


def test_fault_mode_runs_only_fault_cases():
    cases = load_cases(DEFAULT_CASES)
    selected, _ = select_cases(cases, {"fault:no_llm_key"})
    assert [case.id for case in selected] == ["J01"]


def test_ids_spot_check_runs_only_the_named_cases():
    cases = load_cases(DEFAULT_CASES)
    selected, skipped = select_cases(cases, set(), {"A01", "I01"})
    assert [case.id for case in selected] == ["A01", "I01"]
    reasons = {case.id: reason for case, reason in skipped}
    outside = [case.id for case in cases if case.id not in {"A01", "I01"} and case.input is not None]
    assert all(reasons[case_id] == "poza wybranym zestawem --ids" for case_id in outside)
    assert len(skipped) == len(cases) - 2


def test_ids_spot_check_leaves_unrunnable_and_required_cases_skipped():
    cases = load_cases(DEFAULT_CASES)
    spot = {"A01", "G01"}  # G01 wymaga channel:discord
    selected, _ = select_cases(cases, set(), spot)
    assert [case.id for case in selected] == ["A01"]
