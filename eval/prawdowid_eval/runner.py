import json
import time

import httpx
from pydantic import BaseModel

from prawdowid_eval.cases import Case

CHECK_PATH = "/api/check"
# Contract budget for agent.Verify is 25 s; the margin covers backend overhead and slow first requests.
REQUEST_TIMEOUT_SECONDS = 60.0
MILLISECONDS_PER_SECOND = 1000


class RunRecord(BaseModel):
    case_id: str
    repeat: int
    http_status: int | None
    elapsed_ms: int
    body: dict | None
    error: str | None


def run_case(client: httpx.Client, case: Case, repeat: int) -> RunRecord:
    """Sends one case to POST /api/check; transport errors are recorded, not raised, so a run never stops midway."""
    started_at = time.perf_counter()
    try:
        response = client.post(CHECK_PATH, json={"input": case.input, "inputType": case.input_type})
    except httpx.HTTPError as error:
        return RunRecord(
            case_id=case.id,
            repeat=repeat,
            http_status=None,
            body=None,
            error=f"{type(error).__name__}: {error}",
            elapsed_ms=round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND),
        )
    elapsed_ms = round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND)
    try:
        body = response.json()
    except json.JSONDecodeError:
        return RunRecord(
            case_id=case.id,
            repeat=repeat,
            http_status=response.status_code,
            body=None,
            error="Odpowiedź nie jest JSON-em",
            elapsed_ms=elapsed_ms,
        )
    return RunRecord(
        case_id=case.id, repeat=repeat, http_status=response.status_code, body=body, error=None, elapsed_ms=elapsed_ms
    )


def run_cases(
    base_url: str, cases: list[Case], repeats: int, transport: httpx.BaseTransport | None = None
) -> list[RunRecord]:
    """Runs every case `repeats` times in order; repeats measure verdict stability for the same input."""
    with httpx.Client(base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS, transport=transport) as client:
        return [run_case(client, case, repeat) for case in cases for repeat in range(repeats)]
