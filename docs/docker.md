# Docker: pełny zestaw MVP

Cały system uruchamia się jednym `docker compose`. Jury i zespół nie muszą instalować Go, Node.js, Pythona ani `uv`, wystarczy Docker. Pliki: `docker-compose.yml` (korzeń repo), `deploy/` (Dockerfile'e i Caddyfile), `rag/Dockerfile`.

## Co jest w kontenerach

| Usługa | Obraz / budowa | Co robi | Port na hoście |
|---|---|---|---|
| `front` | `deploy/front.Dockerfile` (build Vite, serwuje Caddy) | Strona WWW. Przekazuje `/api/*` do `backend` | **8080** (publiczny punkt wejścia) |
| `backend` | `deploy/backend.Dockerfile` (Go) | API i kanały (WWW oraz adapter demonstracyjny `POST /api/channels/demo`). **Agent jest pakietem Go w tym samym obrazie**, osobnego kontenera nie ma | `127.0.0.1:3001` (tylko do debugowania) |
| `rag` | `rag/Dockerfile` (Python, FastAPI) | Wyszukiwanie, korpus, Google Fact Check, katalog kampanii | `127.0.0.1:8001` |
| `qdrant` | `qdrant/qdrant` | Baza wektorowa | brak (tylko sieć wewnętrzna) |
| `postgres` | `postgres:17-alpine`, profil `local-db` | Lokalna baza (zamiast Supabase) | brak (tylko sieć wewnętrzna) |
| `eval` | `deploy/eval.Dockerfile`, profil `tools` | Zestaw testów i miary, uruchamiany na żądanie | brak |

Przepływ: przeglądarka → `front:8080` → `backend:3001` → `rag:8000` → `qdrant` + baza. Tylko `front` jest otwarty dla sieci. Pozostałe usługi słuchają na `127.0.0.1` albo wcale (nie wystawiaj ich na zewnątrz: `rag` ma endpointy administracyjne, a Qdrant nie ma uwierzytelnienia).

## Wymagania
- Docker z wtyczką Compose (`docker compose version`), około 8 GB wolnego miejsca (obrazy i modele).
- Linux: użytkownik w grupie `docker` (`sudo usermod -aG docker $USER`, potem ponowne logowanie). Błąd `permission denied ... docker.sock` oznacza brak tej grupy.
- Windows: Docker Desktop z włączonym WSL2. Repo trzymaj w systemie plików WSL albo poza OneDrive.

## Szybki start (lokalna baza, działa offline po pierwszym starcie)

```
cp .env.example .env
```
W `.env` ustaw:
- `RAG_POSTGRES_PASSWORD`: hasło lokalnej bazy, wygeneruj np. `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. **Bez niego Postgres nie wystartuje.**
- `RAG_ADMIN_TOKEN`: token do endpointów administracyjnych `rag` (pusty = są wyłączone, nie będzie można zasilić korpusu).
- `DATABASE_URL`: **zostaw puste** w trybie lokalnym.
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`: dostawca modelu; bez klucza każde sprawdzenie zwraca `technical_error`.
- opcjonalnie `FACTCHECK_API_KEY`, `EUVSDISINFO_TOKEN`, `MODERATOR_*`, `CHECK_*` (patrz `.env.example`). `docker-compose.yml` przekazuje do kontenerów tylko zmienne wymienione w jego sekcjach `environment`; `.env` nie jest kopiowany do obrazów. Nową zmienną trzeba dopisać do compose, inaczej w kontenerze obowiązuje wartość domyślna.

```
docker compose --profile local-db up -d --build
```

Pierwszy start trwa długo: `rag` pobiera modele (ok. 3 GB) do wolumenu `model_cache`, a jego healthcheck ma 10 minut na start. `backend` czeka na zdrowy `rag`, a `front` na `backend`. Kolejne starty trwają kilkadziesiąt sekund.

Sprawdzenie:
```
docker compose ps                       # wszystkie usługi powinny być healthy / running
curl http://127.0.0.1:3001/health       # backend (tylko /health, bez prefiksu /api)
curl http://127.0.0.1:8001/health       # rag
curl -I http://localhost:8080           # front (Caddy)
```
Strona: <http://localhost:8080>.

## Tryb z Supabase (wspólna baza zespołu)

Wpisz `DATABASE_URL` (Session pooler, `?sslmode=require`, instrukcja w `README.md`) i uruchom **bez** profilu lokalnej bazy:
```
docker compose up -d --build
```
`postgres` się wtedy nie startuje, a `backend` i `rag` łączą się z Supabase.

**Uwaga: lokalny `rag` nie może używać bazy produkcji.** Teksty i wektory korpusu są w Qdrancie, a stan fragmentów (aktywny czy usunięty) w PostgreSQL. Gdy kilka środowisk ma wspólną bazę, ale każde własny Qdrant, każda ponowna indeksacja (seed przy starcie, `fetch_corpus`, `import_law`) zapisuje nowe fragmenty tylko do swojego Qdranta i oznacza stare jako usunięte we wspólnej bazie. Inne środowiska tracą wtedy swoje fragmenty i wyszukiwanie zwraca pustą listę, więc każde twierdzenie dostaje `insufficient_evidence`. Objaw w logu `rag`: `Seed document ... has no vectors in this Qdrant` albo `Skipped N of M retrieved chunks without active metadata`. Lokalnie używaj profilu `local-db`, a jeśli `backend` ma zostać na Supabase, ustaw `rag/` osobną bazę przez `RAG_POSTGRES_DSN`.

## Zasilanie korpusu

`rag` przy starcie sam uzupełnia korpus z `rag/app/data/seed_documents.json` (dosłowne fragmenty źródeł z datami i linkami, liczba w pliku) i katalog kampanii z `rag/app/data/seed_incidents.json`, więc podstawowe fakty i scenariusz I działają bez ręcznego zasilania. Strony-listy i strony główne są wykluczane regułami z `rag/app/data/corpus_rules.json`, a ustawy wchodzą z tabeli `Law` przez `POST /admin/corpus/law` (opis w `rag/README.md`). Endpointy administracyjne wymagają nagłówka `X-Admin-Token` z wartością `RAG_ADMIN_TOKEN`.
```
# test dymny na fikcyjnych danych
curl -X POST http://127.0.0.1:8001/ingest -H "X-Admin-Token: $RAG_ADMIN_TOKEN" -H "Content-Type: application/json" --data-binary @rag/tests/smoke_documents.json

# lista startowa stron (katalog domen mentora, weryfikatorzy, urzędy), działa w tle (202)
curl -X POST http://127.0.0.1:8001/admin/corpus/fetch -H "X-Admin-Token: $RAG_ADMIN_TOKEN"

# import ze scrapera ze wspólnej bazy (tabela ScrappedData)
curl -X POST "http://127.0.0.1:8001/admin/corpus/sync?maxDocuments=5000" -H "X-Admin-Token: $RAG_ADMIN_TOKEN"
```
Szczegóły i pozostałe endpointy: `rag/README.md`. Korpus leży w wolumenach (`qdrant_data`, `postgres_data`), więc przeżywa restart. Przed pokazem sprawdź listę: `curl http://127.0.0.1:8001/sources`.

## Testy w kontenerze

```
docker compose --profile local-db --profile tools run --rm eval
```
Uruchamia 44 przypadki z `eval/cases.json` przeciw `backend:3001` i zapisuje raport w `eval/reports/` (katalog jest wspólny z hostem). Przypadki z flagami `requires` (kanał, awaria) uruchamiasz dopisując argumenty, np. `run --rm eval run --url http://backend:3001 --cases /srv/cases.json --out /srv/reports --enable fault:rag_down`. Dla awarii zatrzymaj `rag`: `docker compose stop rag`.

## Codzienna praca

| Co | Polecenie |
|---|---|
| Logi usługi | `docker compose logs -f backend` |
| Przebudowa jednej usługi po zmianie kodu | `docker compose up -d --build backend` |
| Zatrzymanie | `docker compose --profile local-db down` |
| **Pełny reset (kasuje bazę, korpus i modele!)** | `docker compose --profile local-db down -v` |
| Wejście do kontenera | `docker compose exec rag sh` |

Do pracy nad kodem uruchom infrastrukturę z `rag/` (`cd rag && docker compose --env-file ../.env --profile local-db up -d`; Postgres na `127.0.0.1:5432`, rag na `127.0.0.1:8001`), a `backend` (`go run .` w `src/backend/`) i front (`pnpm dev` w `src/frontend/`) lokalnie. Compose w korzeniu nie wystawia Postgresa na hosta, więc lokalny backend nie połączy się z jego bazą.

## Bezpieczeństwo

- Sekrety tylko w `.env` (poza gitem) i zmiennych środowiska. **Nie wpisuj ich do Dockerfile'i ani `docker-compose.yml`, nie kopiuj `.env` do obrazu** (`.dockerignore` go wyklucza).
- `backend` działa jako użytkownik bez uprawnień (`app`). Obraz `front` (Caddy) i `rag` działają obecnie jako root: do poprawy, jeśli starczy czasu.
- Porty `rag` i `backend` są związane z `127.0.0.1`. Nie zmieniaj tego na `0.0.0.0`.
- Obrazów z kluczami nie wypychamy do publicznych rejestrów.

## Rozwiązywanie problemów

| Objaw | Przyczyna i rozwiązanie |
|---|---|
| `permission denied ... docker.sock` | Użytkownik nie jest w grupie `docker` (Linux), zob. wymagania. |
| `postgres` nie startuje | Brak `RAG_POSTGRES_PASSWORD` w `.env`. |
| `backend` ciągle czeka | Czeka na zdrowy `rag`. Pierwszy start pobiera modele: `docker compose logs -f rag`. |
| `rag` unhealthy po 10 minutach | Wolna sieć przy pobieraniu modeli albo za mało pamięci. Zobacz logi, zwiększ pamięć Dockera (≥ 6 GB). |
| `401` / `403` z `rag` | Zły albo pusty `RAG_ADMIN_TOKEN`. |
| Port 8080 zajęty | Zmień wpis `"8080:8080"` w `docker-compose.yml` na wolny port. |
| Windows: znaki polskie w `curl -d` | Wysyłaj ciało z pliku UTF-8 (`--data-binary @plik.json`). |
| Brak internetu na pokazie | Po pierwszym starcie obrazy i modele są lokalne, a kolekcje w wolumenach. Wyłączone zostaną tylko źródła zewnętrzne (Google Fact Check), co `rag` zgłasza w `externalSources`. |

## Railway: port usługi rag

`rag` słucha na stałym porcie 8000, bo pod tym adresem woła go `backend/` (`http://rag.railway.internal:8000`). Railway do healthchecku używa zmiennej `PORT`, a nie `EXPOSE` z Dockerfile'a, więc usługa `rag` musi mieć ustawione `PORT=8000` w Variables. Bez tego Railway sprawdza inny port: aplikacja startuje poprawnie, ale w jej logach nie ma żadnego `GET /health`, a log deployu pokazuje `Attempt #N failed with service unavailable` i `1/1 replicas never became healthy`. Deploy kończy się statusem failed, a `backend` zwraca `technical_error`. Tej zmiennej nie da się zapisać w repo, ustawia się ją w dashboardzie Railway.

## Czego ten zestaw nie obejmuje

- **Obrazy z `deploy/` budują się na Railway** (wdrożenie działa pod jednym publicznym adresem, zob. `README.md`, sekcja Wdrożenie). Błąd lokalnego `docker compose build` zgłoś w PR.
- **Drugi kanał** to adapter demonstracyjny `POST /api/channels/demo` w procesie `backend` (dopuszczony przez brief zamiast komunikatora). Bot Discord nie jest zaimplementowany, a `DISCORD_BOT_TOKEN` nie jest przez kod czytany.
- **Rag i Qdrant nie mają publicznych adresów**, więc endpointów administracyjnych na Railway nie wywołasz z zewnątrz: użyj `railway ssh` do usługi `rag` albo `backend` (`http://rag.railway.internal:8000`).
