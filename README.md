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
gdzie `wiadomosc.json` to `{"text": "treść do sprawdzenia"}` w UTF-8. Odpowiedź jest zwykłym tekstem z werdyktem, siłą podstawy, uzasadnieniem i źródłami, jak w komunikatorze. To samo zgłoszenie przez WWW i ten adapter daje ten sam wynik merytoryczny (scenariusz G).

### Bot Discord (drugi kanał)
Slash komenda `/factcheck` w bocie Discord przyjmuje to samo co strona (tekst albo URL) i woła tę samą ścieżkę weryfikacji, więc wynik jest zgodny z WWW (scenariusz G). Odpowiedź jest krótka: werdykt, uzasadnienie i do 4 źródeł; kliknięcie reakcji dodanej przez bota rozwija pełne uzasadnienie ze wskazaniem siły podstawy i wszystkie źródła. Szczegóły konfiguracji: `src/backend/README.md`.

Włączenie: w [Discord Developer Portal](https://discord.com/developers/applications) załóż aplikację z botem, skopiuj token do `DISCORD_BOT_TOKEN` w `.env` (nigdy do repo) i opcjonalnie ustaw `DISCORD_GUILD_ID` na identyfikator serwera testowego (komenda rejestruje się wtedy od razu na tym serwerze). Zaproś bota na serwer z zakresem `applications.commands` i uprawnieniem `Add Reactions`. Bot uruchamia się razem z backendem (`src/backend/`) i łączy przez Gateway, więc nie potrzebuje publicznego adresu ani weryfikacji podpisu żądań.

Jakie linki obsługujemy (`rag/app/fetcher.py`, lista serwisów w `rag/app/data/fetch_rules.json`):

| Adres | Co się dzieje |
|---|---|
| Strona HTML z tekstem (portale, gov.pl, Dziennik Ustaw, EUR-Lex, GUS, weryfikatorzy faktów) | pobieramy główną treść (`<article>`/`<main>`), tytuł i datę publikacji z metadanych albo elementu oznaczonego jako data, sprawdzamy twierdzenia |
| Sam adres w polu tekstowym | traktowany jako link |
| Tekst z jednym adresem w środku („sprawdź też tę stronę: …”) | sprawdzamy tekst razem z pobraną stroną; polecenia ukryte w stronie są ignorowane i liczone |
| Tekst z kilkoma adresami | sprawdzamy sam tekst, stron nie pobieramy (informacja w ograniczeniach) |
| YouTube, TikTok, Vimeo, Facebook, Instagram, X/Twitter, Threads, LinkedIn | nie odczytujemy wideo ani wpisów: odpowiedź `out_of_scope` z prośbą o wklejenie treści, bez żadnego żądania do serwisu |
| PDF, obraz, dokument pod adresem | `needs_clarification`: prośba o wklejenie tekstu albo dodanie zrzutu ekranu |
| Zapora antybotowa (Cloudflare, Incapsula: np. `isap.sejm.gov.pl`, `ulc.gov.pl`) albo strona tylko ze skryptem (np. listy depesz `pap.pl`) | `needs_clarification` z informacją o blokadzie; zabezpieczeń nie obchodzimy |
| Adres prywatny, błąd HTTP, przekierowania w pętli, strona ponad 2 MB | `needs_clarification`: nie udało się odczytać strony |
| Strona „nie znaleziono” zwracana z kodem 200 (np. gov.pl) | tekst portalu bez twierdzeń → `needs_clarification` o braku twierdzeń |

Sprawdzone 22.11.2026 na lokalnym rag (`scratchpad/fetch_probe.py` w sesji): 18 adresów, każdy z powyższych rodzajów dał oczekiwany wynik. Data publikacji z metadanych bywa datą utworzenia (Wikipedia podaje 2002 r.), a strony bez metadanych i elementu z datą (Dziennik Ustaw, EUR-Lex, GUS) nie mają daty przy sprawdzaniu przez URL; w korpusie te same dokumenty mają datę z importu.

Lista źródeł do audytu (wymóg briefu): `GET /api/sources` (dokumenty korpusu z tytułem, wydawcą, datami, licencją i linkiem), `GET /api/sources/catalog` (katalog zaufanych źródeł z zasadami kwalifikacji), `GET /api/sources/external` (usługi zewnętrzne i co dostają). Linki są w stopce strony.

Zrzut ekranu albo zdjęcie z tekstem (scenariusz F; przycisk na stronie albo):
```
curl -X POST http://localhost:8080/api/check/image -F "image=@zrzut.png"
```
Tekst odczytuje lokalnie Tesseract w kontenerze `rag` (PNG, JPEG, WEBP do 5 MB; obraz nie jest zapisywany), potem jest sprawdzany jak tekst wpisany ręcznie. Odpowiedź mówi wprost, że tekst pochodzi z OCR, a data widoczna na obrazie nie potwierdza daty publikacji. Nie ma wyszukiwania odwrotnego obrazu ani oceny autentyczności zdjęcia.

## Ograniczenia
Gdy w korpusie jest mało zweryfikowanych źródeł albo wydarzenie jest zbyt świeże, by miało rzetelne publikacje, system może nie rozstrzygnąć twierdzenia. Wtedy odpowiada „brak wystarczających dowodów”, wyjaśnia, czego nie udało się ustalić, i podaje to, co jest znane.

## Zespół
KNIPM (Koło Naukowe Informatyków Politechniki Morskiej w Szczecinie).

## Wdrożenie (Railway)
Jeden publiczny adres obsługuje usługa `front` (Caddy): serwuje zbudowany `src/frontend/` i przekazuje `/api/*` do `src/backend/` przez sieć prywatną. `src/backend/` i `rag/` nie mają publicznych domen. Dockerfile'e są w `deploy/` (kontekst budowania to korzeń repo). Sekrety tylko w zmiennych Railwaya.
Usługa `rag` musi mieć zmienną `PORT=8000`: Railway używa jej do healthchecku, a obraz słucha na 8000. Bez niej deploy kończy się błędem `service unavailable`, mimo że aplikacja wystartowała. Objawy i tło: `docs/docker.md`.
