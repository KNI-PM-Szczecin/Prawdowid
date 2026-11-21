# Prawdowid

Narzędzie dla obywatela do sprawdzania doniesień (tekst, URL) na podstawie wiarygodnych źródeł. HackNation 2026, zadanie MSZ.
Pokazuje werdykt, źródła i granice wiedzy. Przy braku dowodów wstrzymuje się od oceny.

## Struktura
- `spec/` — brief zadania, regulamin, wymagania (przeczytaj najpierw)
- `src/` — React + Vite (interfejs WWW, frontend)
- `front/` — nieużywany, frontend jest w `src/`
- `backend/` — Go (API, kanały)
- `agent/` — Go (logika weryfikacji)
- `rag/` — korpus i wyszukiwanie źródeł

Zasady pracy dla ludzi i agentów AI: `AGENTS.md`. Kontrakty między modułami: `CONTRACT.md`.

## Wymagania
Narzędzia do zainstalowania przed startem: Git, Go (`backend/`, `agent/`), Node.js i `pnpm` (`src/`), Python 3.12 i `uv` (`rag/`).

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
`backend/` i `rag/` korzystają z jednej bazy PostgreSQL w Supabase. Wystarczy wpisać `DATABASE_URL` w `.env`, kod nie wymaga zmian.

1. Załóż projekt na supabase.com w regionie UE (np. Frankfurt, `eu-central-1`), żeby dane były przetwarzane w EOG.
2. Project Settings → Database → Connection string → **Session pooler**. Skopiuj URI, wstaw hasło bazy, dopisz `?sslmode=require`.
3. Wklej jako `DATABASE_URL` w `.env`. Nie używaj Direct connection (tylko IPv6, nie działa z Dockera) ani Transaction pooler (port 6543).

Łączymy się bezpośrednio przez PostgreSQL, a nie przez API Supabase (`anon`/`service_role` nie są potrzebne). Front nigdy nie łączy się z bazą, tylko z `backend/`.
`rag/` tworzy swoje tabele sam przy starcie (`rag/app/schema.sql`) i włącza na nich RLS bez polityk, więc publiczne REST API Supabase ich nie odczyta.
Bez Supabase (offline, demo bez sieci): w `.env` zostaw `DATABASE_URL` puste, ustaw `RAG_POSTGRES_PASSWORD` i uruchom lokalny Postgres z `rag/` przez `docker compose --env-file ../.env --profile local-db up -d`. Postgres słucha wtedy tylko na `127.0.0.1:5432`. Backendowi wpisz w `backend/.env` (ma pierwszeństwo przed wspólnym `.env`): `DATABASE_URL=postgresql://rag:<RAG_POSTGRES_PASSWORD>@localhost:5432/rag`.

## Uruchomienie
Cały zestaw w Dockerze: `docker compose --profile local-db up -d --build` (szczegóły, tryb z Supabase, zasilanie korpusu i testy: `docs/docker.md`).

## Zespół
Uzupełnić.
