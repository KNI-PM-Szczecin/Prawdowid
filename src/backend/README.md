# backend

Go (`net/http`). API i adaptery kanałów (bez logiki weryfikacji), importuje `agent/` przez `go.work`. Zasady: ../AGENTS.md Najpierw przeczytaj ../spec.

## Uruchomienie
```
go run .
```
Konfiguracja z `../.env` (opcjonalnie `backend/.env`, zmienne środowiska mają pierwszeństwo):
- `DATABASE_URL` (wymagane): PostgreSQL w Supabase, Session pooler. Opis w `../README.md`, sekcja Baza danych.
- `DATABASE_MAX_CONNS` (domyślnie 5), `PORT` (domyślnie 3001).

Bez `DATABASE_URL` albo bez połączenia z bazą backend kończy działanie z jawnym błędem w logu.
`GET /health` zwraca `{"status":"ok","database":"ok"}` albo 503 z `"database":"unavailable"`.

## API
- `POST /api/check`: `{"input": "...", "inputType": "text|url"}` → `CheckResult` (CONTRACT.md §1). Wejście jest walidowane, dane osobowe (e-mail, PESEL, telefon) maskowane przed `agent/` i przed zapisem, potem `agent.Verify`. Przebieg trafia do tabeli `check_runs` (tworzona przy starcie, RLS włączony). Błąd zapisu nie psuje odpowiedzi.
- `DELETE /api/checks/{requestId}`: usuwa zapisany przebieg (`204`, `404`, `400`).
- Limit żądań na adres klienta (`CHECK_RATE_LIMIT_PER_MINUTE`, 20), retencja przebiegów (`CHECK_RETENTION_DAYS`, 30). Zmienne agenta: `RAG_URL`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.
