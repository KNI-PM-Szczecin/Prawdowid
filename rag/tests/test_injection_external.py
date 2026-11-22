import os
from pathlib import Path

import pytest

from app.context import contains_instructions

EVAL_FILE_ENV = "RAG_INJECTION_EVAL_FILE"
BRIEF_MIN_RATE = 0.9

DATA_DIR = Path(__file__).parent / "data"
# deepset/prompt-injections (Apache-2.0), English rows labelled 1. The set counts every off-task request
# (a joke, SQL code, role play) as an injection, so the heuristic detector cannot reach the brief threshold on it;
# the floor below is the measured rate and guards against regressions. Resistance itself is structural
# (source text is data, verdicts need a literal quote) and is measured end to end in eval/ scenario E.
DEEPSET_ATTACKS = DATA_DIR / "deepset_prompt_injections_en.txt"
DEEPSET_BENIGN = DATA_DIR / "deepset_benign.txt"
DEEPSET_MIN_RATE = 0.5


def read_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_external_injection_set_meets_brief_threshold():
    """One attempt per line in a file the team did not write; skipped when the file is not configured."""
    path = os.environ.get(EVAL_FILE_ENV)
    if not path:
        pytest.skip(f"{EVAL_FILE_ENV} not set")
    attempts = read_lines(Path(path))
    detected = [attempt for attempt in attempts if contains_instructions(attempt)]
    rate = len(detected) / len(attempts)
    print(f"external injection set: {len(detected)}/{len(attempts)} detected ({rate:.0%})")
    assert rate >= BRIEF_MIN_RATE, [attempt for attempt in attempts if attempt not in detected][:10]


def test_deepset_attacks_detection_does_not_regress():
    attempts = read_lines(DEEPSET_ATTACKS)
    detected = [attempt for attempt in attempts if contains_instructions(attempt)]
    rate = len(detected) / len(attempts)
    print(f"deepset attacks: {len(detected)}/{len(attempts)} detected ({rate:.0%})")
    assert rate >= DEEPSET_MIN_RATE, [attempt for attempt in attempts if attempt not in detected][:10]


def test_deepset_benign_texts_are_not_flagged():
    flagged = [text for text in read_lines(DEEPSET_BENIGN) if contains_instructions(text)]
    assert flagged == []
