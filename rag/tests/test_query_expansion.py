import asyncio
import json
from typing import ClassVar

import httpx

from app import query_expansion
from app.config import settings

EXPANSION_ANSWER = json.dumps(
    {
        "negative": "Nieprawda, że strefa buforowa działa.",
        "neutral": "strefa buforowa granica",
        "keywords": "strefa buforowa",
    }
)
OPENAI_URL = "https://api.openai.com/v1"
LOCAL_URL = "http://127.0.0.1:52625/v1"


class FakeResponse:
    def __init__(self, content: str, status_code: int = 200) -> None:
        self._content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


class FakeAsyncClient:
    """Records the request body instead of calling the model."""

    calls: ClassVar[list[dict]] = []
    status_code = 200
    content = EXPANSION_ANSWER

    def __init__(self, timeout: float | None = None) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def post(self, url: str, headers: dict | None = None, json: dict | None = None) -> FakeResponse:
        FakeAsyncClient.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(FakeAsyncClient.content, FakeAsyncClient.status_code)


def configure(monkeypatch, url: str) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.status_code = 200
    FakeAsyncClient.content = EXPANSION_ANSWER
    query_expansion._cache.clear()
    monkeypatch.setattr(query_expansion.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(settings, "expansion_llm_url", url)
    monkeypatch.setattr(settings, "expansion_llm_model", "gpt-6-luna")
    monkeypatch.setattr(settings, "expansion_llm_api_key", "test-key")
    monkeypatch.setattr(settings, "expansion_llm_reasoning_effort", "none")


def test_hosted_openai_with_reasoning_effort_none_pins_temperature(monkeypatch):
    configure(monkeypatch, OPENAI_URL)

    result = asyncio.run(query_expansion.expand("Strefa buforowa działa."))

    body = FakeAsyncClient.calls[0]["json"]
    assert result.method == "llm"
    assert body["temperature"] == 0.0
    assert "max_tokens" not in body
    assert body["max_completion_tokens"] == settings.expansion_llm_max_completion_tokens
    assert body["reasoning_effort"] == settings.expansion_llm_reasoning_effort
    assert body["model"] == "gpt-6-luna"
    assert FakeAsyncClient.calls[0]["headers"] == {"Authorization": "Bearer test-key"}


def test_local_server_still_gets_temperature(monkeypatch):
    configure(monkeypatch, LOCAL_URL)

    asyncio.run(query_expansion.expand("Strefa buforowa działa."))

    body = FakeAsyncClient.calls[0]["json"]
    assert body["temperature"] == 0.0
    assert "max_completion_tokens" not in body
    assert "reasoning_effort" not in body


def test_hosted_openai_with_unpinned_temperature_uses_rules(monkeypatch):
    configure(monkeypatch, OPENAI_URL)
    monkeypatch.setattr(settings, "expansion_llm_reasoning_effort", "low")

    result = asyncio.run(query_expansion.expand("Strefa buforowa działa."))

    assert result.method == "rules"
    assert FakeAsyncClient.calls == []


def test_repeated_claim_reuses_cached_expansion(monkeypatch):
    configure(monkeypatch, OPENAI_URL)

    first = asyncio.run(query_expansion.expand("Strefa buforowa działa."))
    FakeAsyncClient.content = json.dumps({"negative": "inna negacja", "neutral": "inne zapytanie"})
    second = asyncio.run(query_expansion.expand("Strefa buforowa działa."))

    assert second == first
    assert len(FakeAsyncClient.calls) == 1


def test_model_error_falls_back_to_rules(monkeypatch):
    configure(monkeypatch, OPENAI_URL)
    FakeAsyncClient.status_code = 400

    result = asyncio.run(query_expansion.expand("Strefa buforowa działa."))

    assert result.method == "rules"
    assert result.negative.startswith("Nieprawda")


def test_broken_json_falls_back_to_rules(monkeypatch):
    configure(monkeypatch, OPENAI_URL)
    FakeAsyncClient.content = "nie JSON"

    result = asyncio.run(query_expansion.expand("Strefa buforowa działa."))

    assert result.method == "rules"


def test_empty_url_uses_rules_without_calling_a_model(monkeypatch):
    configure(monkeypatch, "")
    monkeypatch.setattr(query_expansion.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(query_expansion.expand("Czy strefa buforowa działa?"))

    assert result.method == "rules"
    assert result.neutral == "Strefa buforowa działa"
    assert FakeAsyncClient.calls == []


def test_is_hosted_openai_only_for_exact_host():
    assert query_expansion.is_hosted_openai("https://api.openai.com/v1")
    assert not query_expansion.is_hosted_openai("https://api.openai.com.evil.example/v1")
    assert not query_expansion.is_hosted_openai("http://127.0.0.1:52625/v1")


def test_keywords_come_from_the_model_and_fall_back_to_content_words(monkeypatch):
    configure(monkeypatch, OPENAI_URL)
    assert asyncio.run(query_expansion.expand("Strefa buforowa działa.")).keywords == "strefa buforowa"

    configure(monkeypatch, OPENAI_URL)
    FakeAsyncClient.content = json.dumps({"negative": "n", "neutral": "m"})
    assert asyncio.run(query_expansion.expand("Czy w Krakowie była strefa buforowa?")).keywords == (
        "krakowie strefa buforowa"
    )


def test_rules_keywords_drop_function_words_and_cap_the_length(monkeypatch):
    monkeypatch.setattr(settings, "expansion_llm_url", "")
    query_expansion._cache.clear()
    result = asyncio.run(
        query_expansion.expand(
            "Za zbrodnie w Krakowie w zeszłym roku odpowiada obcokrajowiec według policji i prokuratury"
        )
    )
    assert result.method == "rules"
    assert result.keywords == "zbrodnie krakowie zeszłym roku odpowiada obcokrajowiec"
    assert len(result.keywords.split()) <= query_expansion.RULES_KEYWORDS_MAX_WORDS


def test_rules_keywords_drop_time_adverbs_and_auxiliary_verbs_and_name_countries_in_the_nominative(monkeypatch):
    monkeypatch.setattr(settings, "expansion_llm_url", "")
    query_expansion._cache.clear()
    result = asyncio.run(query_expansion.expand("Czy w Portugalii ostatnio odbywał się festiwal latawców?"))
    assert result.keywords == "Portugalia festiwal latawców"

    query_expansion._cache.clear()
    result = asyncio.run(query_expansion.expand("Czy wczoraj była dzisiaj obecnie teraz zamknięta granica?"))
    assert result.keywords == "zamknięta granica"
