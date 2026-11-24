# backend

Go (`net/http`). API i adaptery kanałów (bez logiki weryfikacji), importuje `agent/` przez `go.work`. Zasady: `../../AGENTS.md`. Najpierw przeczytaj `../../spec`.

## Uruchomienie
```
go run .
```
Konfiguracja ze wspólnego `../../.env` w korzeniu repo (opcjonalnie `src/backend/.env`, zmienne środowiska mają pierwszeństwo):
- `DATABASE_URL` (wymagane): PostgreSQL w Supabase, Session pooler. Opis w `../../README.md`, sekcja Baza danych.
- `DATABASE_MAX_CONNS` (domyślnie 5), `PORT` (domyślnie 3001).
- Zmienne agenta: `RAG_URL`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_REASONING_EFFORT`, `LLM_PRICE_INPUT_PER_M`, `LLM_PRICE_OUTPUT_PER_M`, `RAG_TIMEOUT_SECONDS`, `AGENT_MAX_CLAIMS`.
- Limity i retencja: `CHECK_RATE_LIMIT_PER_MINUTE` (20, na adres klienta), `CHECK_RETENTION_DAYS` (30), `TRUSTED_PROXY_HOPS` (1, który wpis `X-Forwarded-For` liczony od prawej jest adresem klienta), `BADGE_ARCHIVAL_DAYS` (365, po ilu dniach najnowsze źródło jest materiałem archiwalnym).
- Pętla informacji: `MODERATOR_REPEAT_THRESHOLD` (3), `MODERATOR_WEBHOOK_URL` (tylko `https`, pusty = sprawy są tylko rekomendowane), `MODERATOR_TOKEN` (pusty = lista spraw zamknięta).

Bez `DATABASE_URL` albo bez połączenia z bazą backend kończy działanie z jawnym błędem w logu. Bez `LLM_API_KEY` każde sprawdzenie zwraca `technical_error`, nigdy werdykt.

- `GET /livez` → `{"status":"ok"}` bez zapytania do bazy (sonda żywotności, Railway).
- `GET /health` → `{"status":"ok","database":"ok"}` albo 503 z `"database":"unavailable"` (sonda gotowości).

## API
- `POST /api/check`: `{"input": "...", "inputType": "text|url"}` → `CheckResult` (CONTRACT.md §1 i §1a: backend dolicza `summary` i `badges`). Wejście jest walidowane, identyfikatory osobowe (e-mail, PESEL, numer dowodu i paszportu, telefon, IBAN; nigdy imiona i nazwiska, zob. `mask.go`) maskowane przed `agent/` i przed zapisem, potem `agent.Verify`. Przebieg trafia do tabeli `check_runs` (tworzona przy starcie, RLS włączony). Obok niej tabela `prompt_log` (czas, kanał, zamaskowane pytanie, status): historia dla zespołu, żeby sprawdzić, czy jury faktycznie testowało. Usunięcie przebiegu kasuje w niej tylko tekst pytania (czas i kanał zostają), retencja jak dla `check_runs`. Podgląd: `SELECT asked_at AT TIME ZONE 'Europe/Warsaw', channel, status, input_masked FROM prompt_log ORDER BY asked_at DESC;`. Błąd zapisu nie psuje odpowiedzi.
- `POST /api/channels/demo`: drugi kanał (adapter demonstracyjny z briefu), `{"text": "..."}` → odpowiedź tekstowa z werdyktem, siłą podstawy, uzasadnieniem i źródłami; ta sama ścieżka weryfikacji co WWW, więc ten sam wynik merytoryczny.
- `DELETE /api/checks/{requestId}`: usuwa zapisany przebieg (`204`, `404`, `400` dla złego identyfikatora, `503` przy awarii bazy).
- `GET /api/admin/cases`: lista spraw dla analityka (pętla informacji), wymaga `MODERATOR_TOKEN`.
- Kody HTTP: `200` dla `ok`, `needs_clarification`, `out_of_scope`; `503` dla `technical_error`; `429` przy przekroczeniu limitu (ciało też ma kształt `CheckResult`).

## Bot Discord (drugi kanał)
Komenda slash `/factcheck` przyjmuje to samo co strona — tekst albo adres URL — i woła tę samą ścieżkę `runCheck`, więc wynik (werdykt i źródła) jest taki sam jak na WWW (scenariusz G). Odpowiedź jest krótka: powtórzone twierdzenie, werdykt, uzasadnienie i do 4 linków; kliknięcie dodanej przez bota reakcji rozwija pełne uzasadnienie ze wskazaniem siły podstawy i wszystkie źródła (dalej w limicie 2000 znaków).

- `DISCORD_BOT_TOKEN` (pusty = bot wyłączony): token z Discord Developer Portal, nigdy w repo.
- `DISCORD_GUILD_ID` (opcjonalny): identyfikator serwera testowego. Podany = komenda rejestruje się od razu na tym serwerze; pusty = rejestracja globalna (może zająć do godziny).
- Wymagane uprawnienia bota: `applications.commands` (do slash commands) i `Add Reactions` (reakcja rozwija/zwija pełną odpowiedź). Odczyt treści wiadomości (Message Content Intent) nie jest potrzebny przy slash commands.
- Bot łączy się z Gateway Discorda (biblioteka `discordgo`) w procesie backendu i startuje razem z nim.

Testy: `go vet ./... && go test ./...`.
