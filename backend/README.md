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
