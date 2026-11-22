import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

Scenario = Literal["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
Verdict = Literal["confirmed", "false", "misleading", "insufficient_evidence", "not_verifiable"]
NonMeritStatus = Literal["technical_error", "needs_clarification", "out_of_scope"]

VERDICTS: tuple[str, ...] = ("confirmed", "false", "misleading", "insufficient_evidence", "not_verifiable")

# A case runs by default only when `requires` is empty; otherwise the matching CLI flag must be passed.
FAULT_PREFIX = "fault:"


class CaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class Expected(CaseModel):
    verdict: Verdict | None = None
    status: NonMeritStatus | None = None
    injection: bool = False
    incident_warning: bool = False
    # Partial answer (CONTRACT.md §4, current events): abstain, but show the sources that were established.
    sources_required: bool = False


class Case(CaseModel):
    id: str = Field(pattern=r"^[A-J]\d{2}$")
    scenario: Scenario
    input: str | None
    input_type: Literal["text", "url"] = "text"
    expected: Expected
    evidence_needed: str | None = None
    requires: str | None = None
    reviewed: bool = False
    note: str | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> "Case":
        if self.id[0] != self.scenario:
            raise ValueError(f"{self.id}: id prefix must match scenario {self.scenario}")
        if self.input is not None and self.expected.verdict is None and self.expected.status is None:
            raise ValueError(f"{self.id}: a runnable case needs expected.verdict or expected.status")
        return self

    @property
    def runnable(self) -> bool:
        return self.input is not None


def load_cases(path: Path) -> list[Case]:
    """Loads and validates the case file; duplicate ids are rejected so results stay traceable."""
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases = [Case.model_validate(raw) for raw in raw_cases]
    ids = [case.id for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"Duplicate case ids: {duplicates}")
    return cases


def select_cases(
    cases: list[Case], enabled: set[str], only_ids: set[str] | None = None
) -> tuple[list[Case], list[tuple[Case, str]]]:
    """Splits cases into those to run now and skipped ones with a reason for the report.
    `only_ids` limits the run to the named cases (spot checks: a few real calls instead of the full set)."""
    selected: list[Case] = []
    skipped: list[tuple[Case, str]] = []
    fault_mode = any(flag.startswith(FAULT_PREFIX) for flag in enabled)
    for case in cases:
        if not case.runnable:
            skipped.append((case, "brak wejścia: przypadek do uzupełnienia przez zespół"))
        elif only_ids is not None and case.id not in only_ids:
            skipped.append((case, "poza wybranym zestawem --ids"))
        elif case.requires is None and fault_mode:
            skipped.append((case, "pominięty w trybie awarii"))
        elif case.requires is not None and case.requires not in enabled:
            skipped.append((case, f"wymaga: {case.requires}"))
        else:
            selected.append(case)
    return selected, skipped
