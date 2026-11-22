from dataclasses import dataclass

import httpx

from prawdowid_benchmark.dataset import BenchmarkClaim
from prawdowid_eval.runner import REQUEST_TIMEOUT_SECONDS, RunRecord, run_case

INPUT_TYPE_TEXT = "text"


@dataclass(frozen=True)
class _Submission:
    """What prawdowid_eval.runner.run_case needs from a case: the benchmark sends every claim as plain text."""

    id: str
    input: str
    input_type: str = INPUT_TYPE_TEXT


def run_claims(
    base_url: str, claims: list[BenchmarkClaim], repeats: int, transport: httpx.BaseTransport | None = None
) -> list[RunRecord]:
    """Sends every claim to POST /api/check `repeats` times, in dataset order; timing is measured per request."""
    with httpx.Client(base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS, transport=transport) as client:
        return [
            run_case(client, _Submission(id=claim.id, input=claim.claim_text), repeat)
            for claim in claims
            for repeat in range(repeats)
        ]
