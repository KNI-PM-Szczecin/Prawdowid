# rag

Python (FastAPI). Korpus źródeł, indeksowanie i wyszukiwanie z metadanymi. Osobny serwis, `agent/` woła go przez HTTP (kontrakt: `../CONTRACT.md`). Zasady: `../AGENTS.md`. Najpierw przeczytaj `../spec`.

## Uruchomienie

Wymaga tylko Dockera. Zależności są w `pyproject.toml` i `uv.lock`, a obraz instaluje je przez `uv sync --frozen`.

W `../.env` ustaw `DATABASE_URL` (Supabase) albo, dla lokalnej bazy, `RAG_POSTGRES_PASSWORD` (bez niego profil `local-db` nie wystartuje). Ustaw też `RAG_ADMIN_TOKEN` (bez niego endpointy administracyjne są wyłączone). Hasło i token wygenerujesz poleceniem `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

```
cd rag
docker compose --env-file ../.env up -d --build                      # baza w Supabase (DATABASE_URL w ../.env)
docker compose --env-file ../.env --profile local-db up -d --build   # lokalny Postgres, DATABASE_URL puste
```

Baza: `DATABASE_URL` z `../.env`, wspólna z `backend/` (Supabase, Session pooler, opis w `../README.md`). `RAG_POSTGRES_DSN` nadpisuje ją tylko dla `rag/`. Limit połączeń: `RAG_POSTGRES_POOL_MAX_SIZE` (5).

Lokalnie bez Dockera (Qdrant i ewentualnie Postgres nadal z compose): `uv sync`, potem `uv run uvicorn app.main:app --port 8001`. Ustawienia czyta z `../.env` i `rag/.env` (`DATABASE_URL`, `RAG_QDRANT_URL`, `RAG_MODEL_CACHE_DIR`). Nową paczkę dodajesz przez `uv add <paczka>`.

Serwis: `http://127.0.0.1:8001` (OpenAPI: `/docs`). Słucha tylko na localhost. Qdrant nie jest wystawiony na hosta, a lokalny Postgres (profil `local-db`) tylko na `127.0.0.1:5432` dla `backend/` w trybie offline. Pierwszy start pobiera modele (ok. 3 GB) do wolumenu `model_cache`, kolejne starty trwają kilka sekund.

Test dymny na fikcyjnych danych:
```
curl -X POST localhost:8001/ingest -H "X-Admin-Token: $RAG_ADMIN_TOKEN" -H "Content-Type: application/json" --data-binary @tests/smoke_documents.json
```
Polskie znaki w `curl -d '...'` w Git Bash na Windows psują kodowanie, więc ciało zapytania wysyłaj z pliku UTF-8 (`--data-binary @plik.json`).

## Testy i lint

```
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest
```
Testy nie wymagają Dockera ani modeli: czyste funkcje (chunking, stemmer, ekspansja, eviction, wykrywanie prompt injection) oraz kształt `/search` na atrapach (wyniki, pusta lista, 503, 422, token). Zestaw prób prompt injection w `tests/test_injection.py` napisaliśmy sami, więc to test regresji, a nie niezależna miara skuteczności.

## Budżet czasu

Kontrakt daje rag 8 s na wywołanie. Reranker (cross-encoder na CPU) jest najdroższy i rośnie liniowo z długością tekstu, dlatego fragmenty mają 450 znaków, pula kandydatów 12, fact-checków jest maks. 10, a z katalogu kampanii rerankowanych jest 5 spraw po pierwszych 400 znakach. Metadane z Postgresa są pobierane równolegle z rerankingiem. Zmierzone na korpusie 104 stron (1504 fragmenty) i katalogu 201 spraw: mediana 3,3 s, przed strojeniem 6,0 s. To samo zapytanie (z filtrami i `topK`) w ciągu 10 min i przy tej samej wersji korpusu wraca z pamięci podręcznej w RAM, więc powtórzenia i drugi kanał dostają identyczną odpowiedź bez kosztu rerankera. Ekspansja przez LLM ma limit 3 s, Qdrant i Postgres po 5 s. `GET /health` sprawdza bazę, Qdrant i katalog incydentów i zwraca `503 degraded`, gdy któreś nie odpowiada; kontenery mają `restart: unless-stopped`.

## Bezpieczeństwo

- `POST /ingest`, `DELETE /sources/{documentId}` i `POST /admin/eviction` wymagają nagłówka `X-Admin-Token` równego `RAG_ADMIN_TOKEN`. Bez tokena zwracają 401, a gdy token nie jest skonfigurowany, 403.
- `POST /search`, `GET /sources` i `GET /health` są otwarte, bo służą do odczytu.
- Każdy nieobsłużony błąd zwraca `503 index_unavailable`, nigdy pustą listę udającą brak dowodów.

## Architektura

| Element | Rola |
|---|---|
| Qdrant | Statyczny tekst fragmentu i wektory: dense (BGE-M3, 1024) + sparse (BM25 z IDF). Payload: `chunk_id`, `source_id`, `text`, `topic_tag`, `source_type`, `published_at` (dwa ostatnie z indeksem do filtrów). |
| PostgreSQL (Supabase albo lokalny) | `sources` (tytuł, wydawca, link, daty `TIMESTAMPTZ`, licencja, typ) i `document_metadata` (tier, wiarygodność, ochrona, `read_count`, soft delete). Stan zmienny jest tu, nie w Qdrancie. Tabele mają włączone RLS bez polityk, więc REST API Supabase ich nie wystawia. |
| FastEmbed (ONNX, CPU) | BGE-M3 dense, BM25 sparse, `bge-reranker-v2-m3` (int8). Wszystko w kontenerze, bez GPU. |
| APScheduler | Eviction codziennie o 3:00, optymalizacja segmentów Qdranta o 4:00. |

Przepływ `POST /search`: ekspansja zapytania (oryginał, negacja, neutralne) → 3 równoległe zapytania hybrydowe (RRF, po 30, z filtrami `sourceTypes` i `publishedAfter` wewnątrz Qdranta) → pula 15 unikalnych → reranking cross-encoderem względem oryginału → `score = sigmoid(logit / 4)` w skali 0..1, odcięcie poniżej 0,5 → `topK` wyników (domyślnie 5, maksymalnie 7, więcej daje 422) → złączenie z metadanymi z Postgresa → blok `<dostepne_zrodla>` → w tle `read_count + 1`.

Pola API są w camelCase zgodnie z `../CONTRACT.md` (sekcja 3). Daty są znacznikami czasu ISO 8601; wartość bez strefy jest traktowana jako UTC. Poza kontraktem odpowiedź ma dodatkowo `contextXml`, `expandedQueries`, `elapsedMs`, a każdy `Passage` ma też `chunkId`, `tier` i `reliability`.

Katalog kampanii dezinformacyjnych: osobna kolekcja Qdranta (`disinfo_incidents`) zasilana przez `POST /incidents` z tokenem admina (format: `IncidentIn` w `app/models.py`, przykład w `tests/smoke_incidents.json`). Każde `/search` szuka też w katalogu (wektory zapytania oryginalnego) i ocenia kandydatów rerankerem względem samej tezy kampanii (`summary`), z progiem 0,7. Przy dopasowaniu odpowiedź ma `campaignAlert` z kategorią `possible_disinformation_campaign`, komunikatem i maks. 3 sprawami. Sprawy nigdy nie trafiają do `results` ani `contextXml`. Ponowny import tej samej sprawy (`source` + `incidentId`) ją aktualizuje, `DELETE /incidents/{source}/{incidentId}` usuwa. Sprawy są oceniane rerankerem po pierwszych 400 znakach tezy, bo pełne akapity EUvsDisinfo kosztowały ok. 2 s na zapytanie.

Import z EUvsDisinfo: przy ustawionym `EUVSDISINFO_TOKEN` (token w nagłówku `Authorization: Bearer`, nigdy w URL) `POST /admin/incidents/sync?maxCases=1000` z tokenem admina uruchamia w tle pobieranie najnowszych spraw z serwera MCP (`https://mcp.euvsd.info/mcp`, tryb bezstanowy, narzędzie `cases`, strony po 100). Postęp i błędy widać w `GET /incidents` (`euvsdisinfo.running`, `lastIndexed`, `lastError`, `available`). Raz na dobę o 2:00 dociąga 200 najnowszych spraw. Import jest idempotentny (ta sama sprawa = ten sam punkt), a przerwany zostawia to, co już zaindeksował. Na CPU 100 spraw to ok. 2 min, cały rejestr (19 800+) kilka godzin. Testy używają atrap HTTP, serwera nie wołają.

Google Fact Check Tools API: przy ustawionym `FACTCHECK_API_KEY` każde `/search` pyta też na żywo `claims:search` (język `pl`, limit czasu 4 s, cache 1 h z hashem zapytania jako kluczem). Oceny weryfikatorów przechodzą przez ten sam reranker i próg co korpus i wracają jako `Passage` z `sourceType: "factcheck"`. Klucz idzie w nagłówku `X-Goog-Api-Key`, nie w URL. Brak klucza, limit albo awaria Google nie psują wyszukiwania: odpowiedź ma wtedy `externalSources[].status` równe `disabled` lub `error`, a log zawiera tylko kod HTTP, bez treści zgłoszenia. Filtr `sourceTypes` bez `factcheck` w ogóle pomija to API.

Ekspansja zapytań: domyślnie regułowa. Gdy ustawione jest `RAG_EXPANSION_LLM_URL` (np. FastFlowLM: `http://host.docker.internal:52625/v1`), używa modelu. Przy błędzie wraca do reguł i loguje WARNING.

Prompt injection: przed dopasowaniem tekst jest normalizowany (NFKC, usunięcie znaków niewidocznych, małe litery, bez diakrytyków). Wzorce PL i EN są w `app/context.py`. Wykryty fragment ma flagę `suspected_injection` i trafia do logu, ale nadal jest zwracany jako dane.

## Język

Korpus domyślnie po polsku (`RAG_CORPUS_LANGUAGE=pl`). BM25 z FastEmbed nie ma polskiego stemmera, dlatego profil języka (stopwords i lekki stemmer sufiksowy) jest w `app/languages/pl.json`. Nowy język to nowy plik `<kod>.json`. BGE-M3 jest wielojęzyczny i dopasowuje polskie zapytania do źródeł obcojęzycznych.

## Zasilanie korpusu

Katalog zaufanych źródeł jest w `app/data/sources_catalog.json` (`GET /sources/catalog`): wydawca, domeny, typ, tier, wiarygodność i uzasadnienie kwalifikacji, plus reguły dla typów, źródeł spoza katalogu i wykluczania. Dopasowanie po domenie URL (najdłuższa pasująca domena wygrywa, więc `isap.sejm.gov.pl` ma własny wpis mimo ogólnego `gov.pl`). Przy `POST /ingest` dla domeny z katalogu `sourceType`, `tier` i `reliability` można pominąć; dla domeny spoza katalogu trzeba je podać jawnie (inaczej `422`), a dokument jest w audycie oznaczony `inCatalog: false`. Obecność w katalogu nigdy nie wpływa na werdykt, tylko na metadane i neutralną informację o statusie źródła. Nowe źródło to nowy wpis w pliku, bez zmian w kodzie.

Import ze scrapera zespołu: scraper zapisuje strony do tabeli `ScrappedData` (`id`, `date` jako RRRRMMDD, `site`, `title`, `content`) we wspólnej bazie. `POST /admin/corpus/sync?maxDocuments=5000` (token admina, `202`) wgrywa je w tle przez zwykłą ścieżkę `ingest`: katalog nadaje typ i tier po domenie, kopie treści są pomijane, a linie powtarzające się w co najmniej 30% stron (menu, stopki) są usuwane przed podziałem na fragmenty. Postęp w `GET /corpus/sync`. Import jest idempotentny (`documentId` = `scrapped:<id>`, ponowne wgranie podmienia fragmenty). Na CPU 111 stron to ok. 8 min. Tabela `Law` (polskie prawo) czeka na dane i ustalenie adresu URL dla aktów.

Duplikaty: rag liczy skrót znormalizowanej treści (`content_hash`) i odrzuca `409` dokument o tej samej treści co inny aktywny dokument. Ponowne wgranie pod tym samym `documentId` nadal podmienia fragmenty. Niemal identyczne teksty (parafrazy) nie są wykrywane.

`POST /ingest` z listą `{ source: {...}, text }` (pola w `app/models.py`: `SourceIn`, przykład w `tests/smoke_documents.json`). `sourceType`: `official`, `secondary`, `factcheck`, `incident`. `reliability`: `high`, `medium`, `low`. Ponowne wysłanie tego samego `documentId` podmienia fragmenty. `DELETE /sources/{documentId}` usuwa dokument z indeksu (procedura usunięcia). Tier 1 nigdy nie jest usuwany przez eviction. Nowe fragmenty mają ochronę przez `RAG_PROTECTION_DAYS` (7).

## Eviction

Usuwa tylko wtedy, gdy liczba aktywnych fragmentów przekracza `RAG_EVICTION_MAX_ACTIVE_CHUNKS`, i tylko nadwyżkę. Kandydaci: `tier > 1` i po upływie ochrony.
`score = wiek_dni × (2.0 dla tier 3) × 0.4 − read_count × 0.6 (+30, gdy temat zajmuje > 30% bazy)`.
Nigdy nie schodzi poniżej `RAG_EVICTION_MIN_DOCUMENTS` (100) dokumentów ani `RAG_EVICTION_MIN_DOMAINS` (10) domen, czyli minimum korpusu z briefu.
Soft delete w Postgresie i hard delete w Qdrancie są w jednej transakcji: gdy Qdrant zawiedzie, Postgres się wycofuje.

Konfiguracja: zmienne `RAG_*` (pełna lista w `app/config.py`).
