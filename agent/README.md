# agent

Go, biblioteka standardowa. Logika weryfikacji: twierdzenia, werdykt, uzasadnienie, ochrona przed prompt injection, wymienny dostawca modelu. Zasady: ../AGENTS.md. Najpierw przeczytaj ../spec i `prompts/README.md`.

## Użycie z backendu

```go
import "prawdowid/agent"

// RAG_URL, RAG_TIMEOUT_SECONDS, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_REASONING_EFFORT,
// LLM_PRICE_INPUT_PER_M, LLM_PRICE_OUTPUT_PER_M, AGENT_MAX_CLAIMS
verifier, err := agent.NewFromEnv(logger)
result, err := verifier.Verify(ctx, agent.VerifyRequest{RequestID: id, Channel: "web", Input: text, InputType: "text"})
```

`Verify` zwraca `CheckResult` z `CONTRACT.md` §1. Awaria `rag/`, modelu albo brak klucza to `Status: "technical_error"` z komunikatem po polsku; `error` wraca tylko przy błędzie programisty (np. brak promptów). Nie trzeba niczego owijać: `result` można od razu zakodować do JSON.

Model: dowolny serwer zgodny z OpenAI `/v1/chat/completions` (FastFlowLM, Ollama, hostowany OpenAI). Własny dostawca to implementacja `LLMProvider` i `agent.New(config, provider, logger)`.

## Przepływ

1. Pusty input albo mniej niż 2 słowa → `needs_clarification` bez wywołań. URL → `POST /fetch` w `rag/` (422 → `needs_clarification`, „nie da się odczytać strony”). Dla tekstu `document.text` to sprawdzany (zamaskowany przez backend) tekst, dla URL tekst strony.
2. Jedno zdanie (nie pytanie) → to jest twierdzenie, bez modelu. Dłuższy tekst (do 6000 znaków) → prompt `extract` → maks. 3 najważniejsze twierdzenia, każde z `rodzaj` (`fakt` albo `opinia`) i dosłownym `fragment`; pominięte trafiają do `limitations`. Pytanie „Czy …?”, z którego model nic nie wyciągnął, staje się zdaniem oznajmującym; niepoprawny JSON z ekstrakcji → cały tekst jako jedno twierdzenie.
3. Opinia (`rodzaj: opinia`) → od razu `not_verifiable` ze stałym uzasadnieniem, bez wyszukiwania i bez źródeł. Dla każdego faktu `POST /search` (`topK` 5), maks. 3 twierdzenia równolegle; wyniki są scalane w kolejności ekstrakcji, więc równoległość nie zmienia treści ani kolejności odpowiedzi. Brak wyników → model może tylko uznać treść za opinię lub przewidywanie (`not_verifiable`); zapowiedziana zmiana, decyzja albo termin to fakt, więc `insufficient_evidence`, a `missing` mówi, jakie źródło by to rozstrzygnęło, z dopiskiem „Brak wyniku w naszych źródłach nie oznacza, że to prawda ani że to nieprawda.” Gdy przy tym padła usługa weryfikatorów faktów (Google Fact Check), odpowiedź to `technical_error` z komunikatem o błędzie dostępu, nigdy „nie ma takiej publikacji” (scenariusz J).
4. Prompt `judge` dostaje twierdzenie i `contextXml` w wiadomości użytkownika; prompt systemowy nigdy nie zawiera treści źródeł.
5. Reguły (`rules.go`, `numbers.go`, `CONTRACT.md` §4) rozstrzygają: cytat musi być dosłownie we fragmencie o podanym `id`, `confirmed`/`false` wymaga mocnej podstawy (źródło urzędowe, ocena weryfikatora albo dwa niezależne wtórne) i cytatu o pasującej roli, cytat potwierdzający z innymi liczbami niż twierdzenie spada do roli `context`, dwa fragmenty jednego dokumentu to jedno źródło, ocena weryfikatora faktów w cytowanym fragmencie wzmacnia zgodny werdykt modelu, a niezgodna daje wstrzymanie się (mogła dotyczyć innego twierdzenia), polecenia w samym zgłoszeniu lub pobranej stronie są liczone w `meta.injectionAttempts` i logowane, alert kampanii z `rag/` i flagi injection idą do `warnings`/`meta`, nigdy do werdyktu.
6. `evidenceStrength` i `strengthReasons` liczone z przesłanek (typ i niezależność źródeł, wiek), nie z opinii modelu.
7. Każde twierdzenie dostaje `span`: pozycję `fragment` (w zapasie samego twierdzenia) w `document.text`, w code points, bez rozróżniania wielkości liter; parafraza → `null`.

Budżet: 25 s na `Verify`, 12 s na wywołanie `rag/` (`RAG_TIMEOUT_SECONDS`), 10 s na wywołanie modelu, temperatura 0 (dla hostowanego OpenAI tylko przy `reasoning_effort=none`), myślenie Qwen3 wyłączone.

## Koszt

`meta.estimatedCostUsd` liczy się z tokenów zwróconych przez dostawcę (`usage.prompt_tokens` i `usage.completion_tokens`) przez wszystkie wywołania w jednym sprawdzeniu: ekstrakcję twierdzeń i ocenę każdego twierdzenia, razem z ponowieniem po błędnym JSON. Ceny to USD za 1M tokenów w `LLM_PRICE_INPUT_PER_M` i `LLM_PRICE_OUTPUT_PER_M`, domyślnie 0,10/0,50 dla `gpt-6-luna` (lista OpenAI). Dla serwera spoza `api.openai.com` obie ceny są zerowane, bo lokalny model nic nie kosztuje. Tokeny z pamięci podręcznej OpenAI nie są rozróżniane, więc koszt jest szacunkiem górnym.

## Testy

```
cd agent
go vet ./... && go test ./...
```
Testy używają atrapy modelu i serwera `rag/` z `httptest`: potwierdzenie ze źródłem urzędowym, zmyślony cytat odrzucony, jedno źródło wtórne za mało na `false`, niezgodna ocena weryfikatora daje wstrzymanie się, brak wyników bez werdyktu merytorycznego, `missing` z rodzajem rozstrzygającego źródła, awaria weryfikatorów bez wyników jako `technical_error`, opinia bez źródeł i opinia z ekstrakcji jako `not_verifiable`, `span` w code points (także dla URL), cytat z inną liczbą bez potwierdzenia, dwa fragmenty jednego dokumentu jako jedno źródło, liczebnik z kropką bez ekstrakcji, polecenia w zgłoszeniu (E01–E06), awarie jako `technical_error`, niepoprawny JSON z ponowieniem i wstrzymaniem, injection i alert kampanii jako kontekst, ekstrakcja z długiego tekstu, wejście URL.

`go test -tags live -run TestLiveRag` sprawdza klienta i reguły na żywym `rag/` z atrapą modelu. Jakość na prawdziwym modelu mierzy `eval/` (scenariusze A–J i benchmark dezinformacji).
