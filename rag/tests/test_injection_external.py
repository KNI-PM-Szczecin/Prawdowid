import os
from pathlib import Path

import pytest

from app.context import contains_instructions

EVAL_FILE_ENV = "RAG_INJECTION_EVAL_FILE"
BRIEF_MIN_RATE = 0.9


def test_external_injection_set_meets_brief_threshold():
    """One attempt per line in a file the team did not write; skipped when the file is not configured."""
    path = os.environ.get(EVAL_FILE_ENV)
    if not path:
        pytest.skip(f"{EVAL_FILE_ENV} not set")
    attempts = [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    detected = [attempt for attempt in attempts if contains_instructions(attempt)]
    rate = len(detected) / len(attempts)
    print(f"external injection set: {len(detected)}/{len(attempts)} detected ({rate:.0%})")
    assert rate >= BRIEF_MIN_RATE, [attempt for attempt in attempts if attempt not in detected][:10]
