# Docker: pełny zestaw MVP

Cały system uruchamia się jednym `docker compose`. Jury i zespół nie muszą instalować Go, Node.js, Pythona ani `uv`, wystarczy Docker. Pliki: `docker-compose.yml` (korzeń repo), `deploy/` (Dockerfile'e i Caddyfile), `rag/Dockerfile`.

## Co jest w kontenerach

| Usługa | Obraz / budowa | Co robi | Port na hoście |
|---|---|---|---|
| `front` | `deploy/front.Dockerfile` (build Vite, serwuje Caddy) | Strona WWW. Przekazuje `/api/*` do `backend` | **8080** (publiczny punkt wejścia) |
| `backend` | `deploy/backend.Dockerfile` (Go) | API i kanały. **Agent jest pakietem Go w tym samym obrazie**, osobnego kontenera nie ma. Bot Discord (gdy powstanie) działa w tym samym procesie | `127.0.0.1:3001` (tylko do debugowania) |
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
- opcjonalnie `FACTCHECK_API_KEY`, `EUVSDISINFO_TOKEN`, `LLM_*`, `DISCORD_BOT_TOKEN` (patrz `.env.example`).

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

## Zasilanie korpusu

`rag` startuje pusty. Endpointy administracyjne wymagają nagłówka `X-Admin-Token` z wartością `RAG_ADMIN_TOKEN`.
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

Do pracy nad kodem możesz uruchomić samą infrastrukturę (`docker compose --profile local-db up -d postgres qdrant rag`), a `backend` (`go run`) i front (`pnpm dev`) uruchamiać lokalnie.

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

## Czego ten zestaw nie obejmuje

- **Brak końcowych testów budowy obrazów.** Pliki zostały sprawdzone składniowo (`docker compose config`), a front zbudowany poza Dockerem (`pnpm build`), ale **obrazy nie były budowane w Dockerze**: autorka plików nie miała dostępu do demona. Pierwsze `docker compose build` może wykazać błędy, np. nieistniejący tag `golang:1.27-alpine`. Zgłoś je w PR.
- **`backend` ma na razie tylko `GET /health`.** `POST /api/check`, agent i front są w trakcie, więc żadne zapytanie `/api/*` przez `front` jeszcze niczego nie zwróci (404 z backendu).
- **Wdrożenie na Railway:** gałąź `chore/railway-deploy` ma własne Dockerfile'e dla Railway. Te z `deploy/` mają te same nazwy, ale nowe ścieżki (`src/backend`, `src/frontend`); przy scalaniu zostaw wersje z `deploy/`.
- **Bot Discord** (ostatnia rzecz do zrobienia) nie ma własnego kontenera: działa w procesie `backend`, a token podajemy jako `DISCORD_BOT_TOKEN`.
