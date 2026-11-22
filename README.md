# Prawdowid

Narzędzie dla obywatela do sprawdzania doniesień (tekst, URL) na podstawie wiarygodnych źródeł. HackNation 2026, zadanie MSZ.
Pokazuje werdykt, źródła i granice wiedzy. Przy braku dowodów wstrzymuje się od oceny.

## Struktura
- `spec/` — brief zadania, regulamin, wymagania (przeczytaj najpierw)
- `src/frontend/` — Preact + TypeScript + Vite + SCSS (interfejs WWW)
- `src/backend/` — Go (API, kanały: WWW i adapter demonstracyjny)
- `agent/` — Go (logika weryfikacji)
- `rag/` — korpus i wyszukiwanie źródeł (Python)
- `eval/` — testy scenariuszy A–J i benchmark dezinformacji
- `front/` i `backend/` w korzeniu — pozostałości, nieużywane

Zasady pracy dla ludzi i agentów AI: `AGENTS.md`. Kontrakty między modułami: `CONTRACT.md`.

## Wymagania
Narzędzia do zainstalowania przed startem: Git, Go (`src/backend/`, `agent/`), Node.js 20.19+ lub 22.12+ i `pnpm` (`src/frontend/`), Python 3.12 i `uv` (`rag/`, `eval/`).

ArchLinux:
```
sudo pacman -S go nodejs pnpm python uv
```

Windows (PowerShell):
```
winget install Git.Git
winget install GoLang.Go
winget install OpenJS.NodeJS.LTS
winget install pnpm.pnpm
winget install Python.Python.3.12
winget install astral-sh.uv
```
Po instalacji uruchom terminal ponownie.

## Start zespołu
```
cp .env.example .env
```

## Baza danych (Supabase)
`src/backend/` i `rag/` korzystają z jednej bazy PostgreSQL w Supabase. Wystarczy wpisać `DATABASE_URL` w `.env`, kod nie wymaga zmian.

1. Załóż projekt na supabase.com w regionie UE (np. Frankfurt, `eu-central-1`), żeby dane były przetwarzane w EOG.
2. Project Settings → Database → Connection string → **Session pooler**. Skopiuj URI, wstaw hasło bazy, dopisz `?sslmode=require`.
3. Wklej jako `DATABASE_URL` w `.env`. Nie używaj Direct connection (tylko IPv6, nie działa z Dockera) ani Transaction pooler (port 6543).

Łączymy się bezpośrednio przez PostgreSQL, a nie przez API Supabase (`anon`/`service_role` nie są potrzebne). Front nigdy nie łączy się z bazą, tylko z `src/backend/`.
`rag/` tworzy swoje tabele sam przy starcie (`rag/app/schema.sql`) i włącza na nich RLS bez polityk, więc publiczne REST API Supabase ich nie odczyta.
Bez Supabase (offline, demo bez sieci): w `.env` zostaw `DATABASE_URL` puste, ustaw `RAG_POSTGRES_PASSWORD` i uruchom lokalny Postgres z `rag/` przez `docker compose --env-file ../.env --profile local-db up -d`. Postgres słucha wtedy tylko na `127.0.0.1:5432`. Backendowi wpisz w `src/backend/.env` (ma pierwszeństwo przed wspólnym `.env`): `DATABASE_URL=postgresql://rag:<RAG_POSTGRES_PASSWORD>@localhost:5432/rag`.

## Uruchomienie
Cały zestaw w Dockerze: `docker compose --profile local-db up -d --build` (szczegóły, tryb z Supabase, zasilanie korpusu i testy: `docs/docker.md`). Strona: <http://localhost:8080>. Bez `LLM_API_KEY` w `.env` każde sprawdzenie kończy się statusem `technical_error` (brak dostawcy modelu), nigdy werdyktem.

Drugi kanał (adapter demonstracyjny, ta sama logika weryfikacji co WWW, wymóg briefu):
```
curl -X POST http://localhost:8080/api/channels/demo -H "Content-Type: application/json" --data-binary @wiadomosc.json
```
gdzie `wiadomosc.json` to `{"text": "treść do sprawdzenia"}` w UTF-8. Odpowiedź jest zwykłym tekstem z werdyktem, siłą podstawy, uzasadnieniem i źródłami, jak w komunikatorze. To samo zgłoszenie przez WWW i ten adapter daje ten sam wynik merytoryczny (scenariusz G). Bot Discord nie jest zaimplementowany.

## Zespół
KNIPM (Koło Naukowe Informatyków Politechniki Morskiej w Szczecinie).

## Wdrożenie (Railway)
Jeden publiczny adres obsługuje usługa `front` (Caddy): serwuje zbudowany `src/frontend/` i przekazuje `/api/*` do `src/backend/` przez sieć prywatną. `src/backend/`, `rag/` i Qdrant nie mają publicznych domen. Dockerfile'e są w `deploy/` (kontekst budowania to korzeń repo). Sekrety tylko w zmiennych Railwaya.
Usługa `rag` musi mieć zmienną `PORT=8000`: Railway używa jej do healthchecku, a obraz słucha na 8000. Bez niej deploy kończy się błędem `service unavailable`, mimo że aplikacja wystartowała. Objawy i tło: `docs/docker.md`.
