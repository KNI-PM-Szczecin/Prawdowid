# agent

Go, biblioteka standardowa. Logika weryfikacji: twierdzenia, werdykt, uzasadnienie, ochrona przed prompt injection, wymienny dostawca modelu. Zasady: ../AGENTS.md. Najpierw przeczytaj ../spec i `prompts/README.md`.

## Użycie z backendu

```go
import "prawdowid/agent"

verifier, err := agent.NewFromEnv(logger)        // RAG_URL, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, AGENT_MAX_CLAIMS
result, err := verifier.Verify(ctx, agent.VerifyRequest{RequestID: id, Channel: "web", Input: text, InputType: "text"})
```

`Verify` zwraca `CheckResult` z `CONTRACT.md` §1. Awaria `rag/`, modelu albo brak klucza to `Status: "technical_error"` z komunikatem po polsku; `error` wraca tylko przy błędzie programisty (np. brak promptów). Nie trzeba niczego owijać: `result` można od razu zakodować do JSON.

Model: dowolny serwer zgodny z OpenAI `/v1/chat/completions` (FastFlowLM, Ollama, OpenAI). Własny dostawca to implementacja `LLMProvider` i `agent.New(config, provider, logger)`.

## Przepływ

1. Pusty input → `needs_clarification`. URL → `POST /fetch` w `rag/` (422 → `needs_clarification`, „nie da się odczytać strony”).
2. Jedno zdanie → to jest twierdzenie, bez modelu. Dłuższy tekst → prompt `extract` → maks. 3 najważniejsze twierdzenia; pominięte trafiają do `limitations`.
3. Dla każdego twierdzenia `POST /search` (`topK` 5), maks. 3 twierdzenia równolegle. Wyniki są scalane w kolejności ekstrakcji, więc równoległość nie zmienia treści ani kolejności odpowiedzi. Brak wyników → `insufficient_evidence` bez wołania modelu.
4. Prompt `judge` dostaje twierdzenie i `contextXml` w wiadomości użytkownika; prompt systemowy nigdy nie zawiera treści źródeł.
5. Reguły (`rules.go`, `CONTRACT.md` §4) rozstrzygają: cytat musi być dosłownie we fragmencie o podanym `id`, `confirmed`/`false` wymaga mocnej podstawy (źródło urzędowe, ocena weryfikatora albo dwa niezależne wtórne) i cytatu o pasującej roli, ocena weryfikatora faktów w cytowanym fragmencie wygrywa z modelem, alert kampanii z `rag/` i flagi injection idą do `warnings`/`meta`, nigdy do werdyktu.
6. `evidenceStrength` i `strengthReasons` liczone z przesłanek (typ i niezależność źródeł, wiek), nie z opinii modelu.

Budżet: 25 s na `Verify`, 12 s na wywołanie `rag/` (`RAG_TIMEOUT_SECONDS`), 10 s na wywołanie modelu, temperatura 0, myślenie Qwen3 wyłączone.

## Koszt

`meta.estimatedCostUsd` liczy się z tokenów zwróconych przez dostawcę (`usage.prompt_tokens` i `usage.completion_tokens`) przez wszystkie wywołania w jednym sprawdzeniu: ekstrakcję twierdzeń i ocenę każdego twierdzenia, razem z ponowieniem po błędnym JSON. Ceny to USD za 1M tokenów w `LLM_PRICE_INPUT_PER_M` i `LLM_PRICE_OUTPUT_PER_M`, domyślnie 0,10/0,50 dla `gpt-6-luna` (lista OpenAI). Dla serwera spoza `api.openai.com` obie ceny są zerowane, bo lokalny model nic nie kosztuje. Tokeny z pamięci podręcznej OpenAI nie są rozróżniane, więc koszt jest szacunkiem górnym.

## Testy

```
cd agent
go vet ./... && go test ./...
```
Testy używają atrapy modelu i serwera `rag/` z `httptest`: potwierdzenie ze źródłem urzędowym, zmyślony cytat odrzucony, jedno źródło wtórne za mało na `false`, ocena weryfikatora wygrywa z modelem, brak wyników bez wołania modelu, awarie jako `technical_error`, niepoprawny JSON z ponowieniem i wstrzymaniem, injection i alert kampanii jako kontekst, ekstrakcja z długiego tekstu, wejście URL.

Nie ma jeszcze testu z prawdziwym modelem: FastFlowLM działa na maszynie kolegi. Pierwszy przebieg `eval/` pokaże, czy Qwen3 0.6B trzyma format JSON i wybiera trafne cytaty.
