import json

import httpx

from prawdowid_eval.cases import Case
from prawdowid_eval.runner import RATE_LIMIT_RETRIES, run_case, run_cases

BASE_URL = "http://backend.test"
REPEATS = 2


def _case() -> Case:
    return Case.model_validate(
        {"id": "A01", "scenario": "A", "input": "Kadencja Sejmu trwa 4 lata.", "expected": {"verdict": "confirmed"}}
    )


def test_run_cases_posts_contract_body_and_records_responses():
    received = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"requestId": "r1", "status": "ok", "claims": [], "meta": {}})

    records = run_cases(BASE_URL, [_case()], REPEATS, transport=httpx.MockTransport(handler))

    assert received == [("/api/check", {"input": "Kadencja Sejmu trwa 4 lata.", "inputType": "text"})] * REPEATS
    assert [record.repeat for record in records] == [0, 1]
    assert all(record.http_status == 200 and record.error is None for record in records)


def test_transport_error_is_recorded_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    records = run_cases(BASE_URL, [_case()], 1, transport=httpx.MockTransport(handler))

    assert records[0].body is None
    assert records[0].http_status is None
    assert "ConnectError" in records[0].error


RATE_LIMITED = {"requestId": "r0", "status": "technical_error", "message": "Zbyt wiele zapytań.", "claims": []}


def test_rate_limited_case_waits_retry_after_and_is_sent_again():
    answers = [
        httpx.Response(429, headers={"Retry-After": "7"}, json=RATE_LIMITED),
        httpx.Response(200, json={"requestId": "r1", "status": "ok", "claims": [], "meta": {}}),
    ]
    waits: list[float] = []
    with httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(lambda request: answers.pop(0))) as client:
        record = run_case(client, _case(), 0, sleep=waits.append)

    assert waits == [7.0]
    assert record.http_status == 200


def test_rate_limit_retries_are_bounded():
    waits: list[float] = []
    transport = httpx.MockTransport(lambda request: httpx.Response(429, json=RATE_LIMITED))
    with httpx.Client(base_url=BASE_URL, transport=transport) as client:
        record = run_case(client, _case(), 0, sleep=waits.append)

    assert len(waits) == RATE_LIMIT_RETRIES
    assert record.http_status == 429


def test_non_json_response_is_recorded_as_error():
    records = run_cases(
        BASE_URL, [_case()], 1, transport=httpx.MockTransport(lambda request: httpx.Response(502, text="Bad Gateway"))
    )
    assert records[0].http_status == 502
    assert records[0].body is None
