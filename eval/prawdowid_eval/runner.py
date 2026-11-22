import json
import time

import httpx
from pydantic import BaseModel

from prawdowid_eval.cases import Case

CHECK_PATH = "/api/check"
# Contract budget for agent.Verify is 45 s; the margin covers backend overhead and slow first requests.
REQUEST_TIMEOUT_SECONDS = 60.0
MILLISECONDS_PER_SECOND = 1000
# The backend limits checks per client and minute. A rate-limited answer says nothing about verification quality, so
# the run waits (Retry-After, capped) and sends the case again instead of recording a technical_error.
HTTP_TOO_MANY_REQUESTS = 429
RATE_LIMIT_RETRIES = 2
RATE_LIMIT_DEFAULT_WAIT_SECONDS = 60.0
RATE_LIMIT_MAX_WAIT_SECONDS = 60.0


def _retry_after_seconds(response: httpx.Response) -> float:
    try:
        wait = float(response.headers.get("Retry-After", RATE_LIMIT_DEFAULT_WAIT_SECONDS))
    except ValueError:
        wait = RATE_LIMIT_DEFAULT_WAIT_SECONDS
    return min(max(wait, 0.0), RATE_LIMIT_MAX_WAIT_SECONDS)


class RunRecord(BaseModel):
    case_id: str
    repeat: int
    http_status: int | None
    elapsed_ms: int
    body: dict | None
    error: str | None


def run_case(client: httpx.Client, case: Case, repeat: int, sleep=time.sleep) -> RunRecord:
    """
    Sends one case to POST /api/check; transport errors are recorded, not raised, so a run never stops midway.
    A 429 is retried up to RATE_LIMIT_RETRIES times after Retry-After; the time spent waiting is not counted.
    """
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        record, response = _send(client, case, repeat)
        if response is None or response.status_code != HTTP_TOO_MANY_REQUESTS or attempt == RATE_LIMIT_RETRIES:
            return record
        sleep(_retry_after_seconds(response))
    return record


def _send(client: httpx.Client, case: Case, repeat: int) -> tuple[RunRecord, httpx.Response | None]:
    started_at = time.perf_counter()
    try:
        response = client.post(CHECK_PATH, json={"input": case.input, "inputType": case.input_type})
    except httpx.HTTPError as error:
        record = RunRecord(
            case_id=case.id,
            repeat=repeat,
            http_status=None,
            body=None,
            error=f"{type(error).__name__}: {error}",
            elapsed_ms=round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND),
        )
        return record, None
    elapsed_ms = round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND)
    try:
        body = response.json()
    except json.JSONDecodeError:
        record = RunRecord(
            case_id=case.id,
            repeat=repeat,
            http_status=response.status_code,
            body=None,
            error="Odpowiedź nie jest JSON-em",
            elapsed_ms=elapsed_ms,
        )
        return record, response
    record = RunRecord(
        case_id=case.id, repeat=repeat, http_status=response.status_code, body=body, error=None, elapsed_ms=elapsed_ms
    )
    return record, response


def run_cases(
    base_url: str, cases: list[Case], repeats: int, transport: httpx.BaseTransport | None = None
) -> list[RunRecord]:
    """Runs every case `repeats` times in order; repeats measure verdict stability for the same input."""
    with httpx.Client(base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS, transport=transport) as client:
        return [run_case(client, case, repeat) for case in cases for repeat in range(repeats)]
