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

Kontrakt daje rag 12 s na wywołanie. Reranker (cross-encoder na CPU) jest najdroższy i rośnie liniowo z długością tekstu, dlatego fragmenty mają 450 znaków, pula kandydatów 12, fact-checków jest maks. 10, a z katalogu kampanii rerankowanych jest 5 spraw po pierwszych 400 znakach. Metadane z Postgresa są pobierane równolegle z rerankingiem. Zmierzone na korpusie 104 stron (1504 fragmenty) i katalogu 201 spraw: mediana 3,3 s, przed strojeniem 6,0 s. To samo zapytanie (z filtrami i `topK`) w ciągu 10 min i przy tej samej wersji korpusu wraca z pamięci podręcznej w RAM, więc powtórzenia i drugi kanał dostają identyczną odpowiedź bez kosztu rerankera. Ekspansja przez LLM ma limit 3 s, Qdrant i Postgres po 5 s. `GET /health` sprawdza bazę, Qdrant i katalog incydentów i zwraca `503 degraded`, gdy któreś nie odpowiada; kontenery mają `restart: unless-stopped`.

Rozgrzewka: przy starcie, przed przyjęciem pierwszego żądania (`app/warmup.py`), rag wykonuje pełną ścieżkę wyszukiwania na tekście spoza korpusu — trzy zapytania do modeli, trzy wyszukiwania hybrydowe w Qdrancie i rerank całej puli kandydatów. Zimny start po deployu kosztował 12,6 s i przekraczał limit `agent/`, więc pierwsze zapytanie kończyło się `technical_error`; po rozgrzewce ten koszt jest płacony przed otwarciem portu, a nie w żądaniu obywatela. Błąd rozgrzewki jest logowany i nie blokuje startu.

## Bezpieczeństwo

- `POST /ingest`, `DELETE /sources/{documentId}` i `POST /admin/eviction` wymagają nagłówka `X-Admin-Token` równego `RAG_ADMIN_TOKEN`. Bez tokena zwracają 401, a gdy token nie jest skonfigurowany, 403.
- `POST /search`, `GET /sources` i `GET /health` są otwarte, bo służą do odczytu.
- Każdy nieobsłużony błąd zwraca `503 index_unavailable`, nigdy pustą listę udającą brak dowodów.
- Guard URL (`app/url_guard.py`): URL podany przez obywatela (i każdy cel przekierowania, bo redirecty są robione ręcznie) musi wskazywać wyłącznie publiczne adresy — http/https, porty 80/443, wszystkie wyniki DNS poza loopback, sieciami prywatnymi i link-local (w tym metadanymi chmury `169.254.169.254`). Pobieranie strumieniowe z limitem 2 MB w trakcie pobierania. Atrapy i usługi lokalne (np. `host.docker.internal` dla ekspansji LLM) tym guardem nie przechodzą i nie muszą — dotyczy on tylko URL-i od użytkownika i listy zasilania korpusu.

## Architektura

| Element | Rola |
|---|---|
| Qdrant | Statyczny tekst fragmentu i wektory: dense (BGE-M3, 1024) + sparse (BM25 z IDF). Payload: `chunk_id`, `source_id`, `text`, `topic_tag`, `source_type`, `published_at` (dwa ostatnie z indeksem do filtrów). |
| PostgreSQL (Supabase albo lokalny) | `sources` (tytuł, wydawca, link, daty `TIMESTAMPTZ`, licencja, typ) i `document_metadata` (tier, wiarygodność, ochrona, `read_count`, soft delete). Stan zmienny jest tu, nie w Qdrancie. Tabele mają włączone RLS bez polityk, więc REST API Supabase ich nie wystawia. |
| FastEmbed (ONNX, CPU) | BGE-M3 dense, BM25 sparse, `bge-reranker-v2-m3` (int8). Wszystko w kontenerze, bez GPU. |
| APScheduler | Eviction codziennie o 3:00, optymalizacja segmentów Qdranta o 4:00. |

Przepływ `POST /search`: ekspansja zapytania (oryginał, negacja, neutralne) → 3 równoległe zapytania hybrydowe (RRF, po 30, z filtrami `sourceTypes` i `publishedAfter` wewnątrz Qdranta) → pula 12 unikalnych → reranking cross-encoderem względem oryginału → `score = sigmoid(logit / 4)` w skali 0..1, odcięcie poniżej 0,5 → `topK` wyników (domyślnie 5, maksymalnie 7, więcej daje 422) → złączenie z metadanymi z Postgresa → **odrzucenie fragmentów bez tytułu, wydawcy, linku, daty pobrania lub daty publikacji** → blok `<dostepne_zrodla>` → w tle `read_count + 1`. Fact-check bez daty weryfikacji też nie wraca w `results`.

Pola API są w camelCase zgodnie z `../CONTRACT.md` (sekcja 3). Daty są znacznikami czasu ISO 8601; wartość bez strefy jest traktowana jako UTC. Poza kontraktem odpowiedź ma dodatkowo `contextXml`, `expandedQueries`, `elapsedMs`, a każdy `Passage` ma też `chunkId`, `tier` i `reliability`.

Katalog kampanii dezinformacyjnych: osobna kolekcja Qdranta (`disinfo_incidents`) zasilana przez `POST /incidents` z tokenem admina (format: `IncidentIn` w `app/models.py`, przykład w `tests/smoke_incidents.json`). Pusty katalog przy starcie uzupełnia `RAG_SEED_INCIDENTS_ENABLED=true` (domyślnie) z `app/data/seed_incidents.json`: trzy publiczne sprawy EUvsDisinfo z linkiem, datą i licencją. To nadal wyłącznie kontekst (`campaignAlert`), nigdy dowód; import z EUvsDisinfo i `POST /incidents` działają bez zmian. Każde `/search` szuka też w katalogu (wektory zapytania oryginalnego) i ocenia kandydatów rerankerem względem samej tezy kampanii (`summary`), z progiem 0,7. Przy dopasowaniu odpowiedź ma `campaignAlert` z kategorią `possible_disinformation_campaign`, komunikatem i maks. 3 sprawami. Sprawy nigdy nie trafiają do `results` ani `contextXml`. Ponowny import tej samej sprawy (`source` + `incidentId`) ją aktualizuje, `DELETE /incidents/{source}/{incidentId}` usuwa. Sprawy są oceniane rerankerem po pierwszych 400 znakach tezy, bo pełne akapity EUvsDisinfo kosztowały ok. 2 s na zapytanie.

Import z EUvsDisinfo: przy ustawionym `EUVSDISINFO_TOKEN` (token w nagłówku `Authorization: Bearer`, nigdy w URL) `POST /admin/incidents/sync?maxCases=1000` z tokenem admina uruchamia w tle pobieranie najnowszych spraw z serwera MCP (`https://mcp.euvsd.info/mcp`, tryb bezstanowy, narzędzie `cases`, strony po 100). Postęp i błędy widać w `GET /incidents` (`euvsdisinfo.running`, `lastIndexed`, `lastError`, `available`). Raz na dobę o 2:00 dociąga 200 najnowszych spraw. Import jest idempotentny (ta sama sprawa = ten sam punkt), a przerwany zostawia to, co już zaindeksował. Na CPU 100 spraw to ok. 2 min, cały rejestr (19 800+) kilka godzin. Testy używają atrap HTTP, serwera nie wołają.

Google Fact Check Tools API: przy ustawionym `FACTCHECK_API_KEY` każde `/search` pyta też na żywo `claims:search` (język `pl`, limit czasu 4 s, cache 1 h z hashem zapytania jako kluczem). Oceny weryfikatorów przechodzą przez ten sam reranker i próg co korpus i wracają jako `Passage` z `sourceType: "factcheck"`. Klucz idzie w nagłówku `X-Goog-Api-Key`, nie w URL. Brak klucza, limit albo awaria Google nie psują wyszukiwania: odpowiedź ma wtedy `externalSources[].status` równe `disabled` lub `error`, a log zawiera tylko kod HTTP, bez treści zgłoszenia. Filtr `sourceTypes` bez `factcheck` w ogóle pomija to API.

Ekspansja zapytań: domyślnie regułowa. Gdy ustawione jest `RAG_EXPANSION_LLM_URL` (np. FastFlowLM: `http://host.docker.internal:52625/v1`), używa modelu. Dla hosta `api.openai.com` zapytanie wysyła `max_completion_tokens`, `reasoning_effort` z `RAG_EXPANSION_LLM_REASONING_EFFORT` (domyślnie `none`) oraz `temperature: 0` **tylko przy `none`**; dokumentacja OpenAI zabrania temperatury przy innym wysiłku rozumowania, więc wtedy `rag/` używa reguł, zamiast dopuszczać zmienne zapytania. Inne serwery dostają `temperature: 0`. Wynik ekspansji jest cache'owany po hashu twierdzenia (`RAG_EXPANSION_CACHE_TTL_SECONDS`, domyślnie 3600 s), więc powtórzone sprawdzenie ma te same zapytania pomocnicze. Przy błędzie wraca do reguł i loguje WARNING.

Prompt injection: przed dopasowaniem tekst jest normalizowany (NFKC, usunięcie znaków niewidocznych, małe litery, bez diakrytyków). Wzorce PL i EN są w `app/context.py`. Wykryty fragment ma flagę `suspected_injection` i trafia do logu, ale nadal jest zwracany jako dane.

## Język

Korpus domyślnie po polsku (`RAG_CORPUS_LANGUAGE=pl`). BM25 z FastEmbed nie ma polskiego stemmera, dlatego profil języka (stopwords i lekki stemmer sufiksowy) jest w `app/languages/pl.json`. Nowy język to nowy plik `<kod>.json`. BGE-M3 jest wielojęzyczny i dopasowuje polskie zapytania do źródeł obcojęzycznych.

## Zasilanie korpusu

Startowy korpus demo: `app/data/seed_documents.json` zawiera 16 dosłownych fragmentów publicznych źródeł z kompletem metadanych (tytuł, wydawca, data publikacji i pobrania, link, licencja). Przy starcie `rag/` indeksuje brakujące `documentId` przez zwykłą ścieżkę `ingest` (katalog, chunking, duplikaty). Dzięki temu fakty z `eval/cases.json` i scenariusza C są w korpusie nawet bez dostępu do stron; `RAG_SEED_CORPUS_ENABLED=false` wyłącza uzupełnianie, a błąd jednego dokumentu nie blokuje startu. Istniejące dokumenty są pomijane, więc restart nie powiela treści.

Katalog zaufanych źródeł jest w `app/data/sources_catalog.json` (`GET /sources/catalog`): wydawca, domeny, typ, tier, wiarygodność i uzasadnienie kwalifikacji, plus reguły dla typów, źródeł spoza katalogu i wykluczania. Dopasowanie po domenie URL (najdłuższa pasująca domena wygrywa, więc `isap.sejm.gov.pl` ma własny wpis mimo ogólnego `gov.pl`). Przy `POST /ingest` dla domeny z katalogu `sourceType`, `tier` i `reliability` można pominąć; dla domeny spoza katalogu trzeba je podać jawnie (inaczej `422`), a dokument jest w audycie oznaczony `inCatalog: false`. Obecność w katalogu nigdy nie wpływa na werdykt, tylko na metadane i neutralną informację o statusie źródła. Nowe źródło to nowy wpis w pliku, bez zmian w kodzie.

Import ze scrapera zespołu: scraper zapisuje strony do tabeli `ScrappedData` (`id`, `date` jako RRRRMMDD, `site`, `title`, `content`) we wspólnej bazie. `POST /admin/corpus/sync?maxDocuments=5000` (token admina, `202`) wgrywa je w tle przez zwykłą ścieżkę `ingest`: katalog nadaje typ i tier po domenie, kopie treści są pomijane, a linie powtarzające się w co najmniej 30% stron (menu, stopki) są usuwane przed podziałem na fragmenty. Postęp w `GET /corpus/sync`. Import jest idempotentny (`documentId` = `scrapped:<id>`, ponowne wgranie podmienia fragmenty). Na CPU 111 stron to ok. 8 min. Tabela `Law` (polskie prawo) czeka na dane i ustalenie adresu URL dla aktów.

Reguły wykluczania: `app/data/corpus_rules.json` (hosty, wzorce adresów i tytułów) odrzuca przy każdym imporcie strony-listy (aktualności, komunikaty, ostrzeżenia jako listy), strony główne portali i ministerstw oraz lokalne kroniki Policji i SOK: to same nagłówki bez daty albo treści, o które obywatel nie pyta. Takie strony liczą się w statusie jako `skippedExcluded`. `POST /admin/corpus/prune` (token admina) usuwa z indeksu już wgrane dokumenty pasujące do reguł i zwraca listę usuniętych `documentId`. Zmiana reguły to zmiana pliku, bez kodu; pojedynczą stronę z wykluczonego serwisu nadal można wgrać przez `POST /ingest`.

Akty prawne: scraper zespołu zapisuje Dziennik Ustaw 2025–2026 do tabeli `Law` (`docid` = pozycja w roku, `date` RRRRMMDD, `doctitle`, `rule` = jeden artykuł). `POST /admin/corpus/law?maxChars=4000000` (token admina, `202`, postęp w `GET /corpus/law`) importuje akty z `app/data/law_acts.json` w kolejności z listy: dla każdego wpisu najnowszy akt pasujący do `titlePattern` (np. najnowszy tekst jednolity Kodeksu pracy), jako dokument `law:<id>` z adresem pozycji w Dzienniku Ustaw (`https://dziennikustaw.gov.pl/DU/<rok>/<pozycja>`), datą ogłoszenia jako datą publikacji i adnotacją o licencji (akt normatywny, art. 4 pkt 1 prawa autorskiego). Łamania wierszy z PDF są sklejane, akt dłuższy niż `RAG_LAW_PART_MAX_CHARS` (450 000) jest dzielony na części na granicach artykułów (`law:<id>:2`). Budżet `maxChars` ogranicza jedno uruchomienie (CPU: ok. 8 min na 500 000 znaków); kolejne uruchomienie pomija akty już wgrane z tej samej pozycji i idzie dalej. Lista to ok. 45 aktów, o które obywatele pytają najczęściej (praca, świadczenia, dokumenty, wybory, podatki, obronność, migracja, zdrowie, szkoła), nie wszystkie 1900 aktów z tabeli. Pełny zrzut (122 tys. wierszy, 137 mln znaków) nie mieści się w darmowym planie bazy, więc `PYTHONPATH=. uv run python scripts/trim_law_table.py` (dry run; `--apply` kasuje i robi `VACUUM`) zostawia w tabeli tylko akty z listy: 44 akty, 11,8 tys. wierszy, 9,4 mln znaków. Nowy akt na liście wymaga ponownego wgrania go przez scraper.

Pobieranie stron z sieci: `POST /admin/corpus/fetch` (token admina, `202`) z ciałem `{"urls": [...]}` albo bez ciała, wtedy bierze listę startową `app/data/seed_urls.json` (konkretne strony z faktami z eval, dokumenty trwałe: Konstytucja, członkostwo w UE i NATO, transfery UE–Polska, oraz analizy weryfikatorów faktów o powracających mitach: 5G, szczepionki i autyzm, chemtrails, bilans składki do UE). Tekst wyciąga parser HTML ze standardowej biblioteki (bez skryptów, stylów i nagłówka dokumentu), a dalej strony idą tą samą ścieżką co ze scrapera. Data publikacji pochodzi z metadanych strony (`article:published_time`, OpenGraph, JSON-LD `datePublished`, `<time datetime>`); gdy ich brak, `seed_urls.json` może przypiąć datę widoczną w treści lub w akcie prawnym. Strona bez ustalonej daty nie jest zwracana jako dowód. Strony bez tekstu w HTML (aplikacje JS, zapory anty-botowe jak Incapsula na `ulc.gov.pl` i `sar.gov.pl`), nie-HTML i błędy HTTP są pomijane i liczone jako `failed` w `GET /corpus/fetch`; zabezpieczeń serwisów nie obchodzimy. Klient przedstawia się jako `Prawdowid/0.1`, pobiera po jednej stronie z odstępem 0,5 s i limitem 2 MB. Pierwszy przebieg listy startowej: 27 z 40 stron wgranych, korpus razem ze scraperem ma 131 dokumentów z 22 domen i 3 typów źródeł (minimum z briefu: 100, 10, 2).

Duplikaty: rag liczy skrót znormalizowanej treści (`content_hash`) i odrzuca `409` dokument o tej samej treści co inny aktywny dokument. Kopie z drobnymi zmianami łapie drugi próg: dla każdego fragmentu nowego dokumentu rag szuka najbliższego fragmentu innego dokumentu; gdy co najmniej 70% fragmentów wskazuje ten sam dokument i średnie podobieństwo kosinusowe wynosi ≥ 0,87, dokument dostaje `409` z dopiskiem „parafraza” (`RAG_NEAR_DUPLICATE_MIN_MEAN_COSINE`, `RAG_NEAR_DUPLICATE_MIN_SHARE`). Progi zmierzone na korpusie demo: ta sama strona pobrana w różnych dniach, nawet z inaczej pociętymi fragmentami, daje średnią 0,89–0,95 przy udziale 0,75–1,0; różne strony tego samego serwisu (raporty dobowe RCB, aktualności policji) albo mają średnią poniżej 0,88, albo rozpraszają dopasowania po wielu dokumentach. To zabezpieczenie celuje w kopie całych stron, nie w każdą przeróbkę: krótki tekst z edycją w połowie fragmentów przejdzie. Ponowne wgranie pod tym samym `documentId` nadal podmienia fragmenty.

Audyt źródeł zewnętrznych: `GET /sources/external` opisuje Google Fact Check i EUvsDisinfo (rola, co dostaje dostawca, warunki, zmienna z kluczem) i pokazuje, czy są włączone oraz stan katalogu kampanii. Razem z `GET /sources` i `GET /sources/catalog` daje pełną listę źródeł do audytu.

Zewnętrzny zestaw prób prompt injection: `RAG_INJECTION_EVAL_FILE=<ścieżka>` (jedna próba na linię) włącza test `tests/test_injection_external.py`, który liczy odsetek wykrytych prób i wymaga ≥ 90% (próg z briefu). Bez pliku test jest pomijany. Wbudowany zestaw w `tests/test_injection.py` pisaliśmy sami, więc jest tylko regresją.

`POST /ingest` z listą `{ source: {...}, text }` (pola w `app/models.py`: `SourceIn`, przykład w `tests/smoke_documents.json`). `sourceType`: `official`, `secondary`, `factcheck`, `incident`. `reliability`: `high`, `medium`, `low`. Ponowne wysłanie tego samego `documentId` podmienia fragmenty. `DELETE /sources/{documentId}` usuwa dokument z indeksu (procedura usunięcia). Tier 1 nigdy nie jest usuwany przez eviction. Nowe fragmenty mają ochronę przez `RAG_PROTECTION_DAYS` (7).

## Eviction

Usuwa tylko wtedy, gdy liczba aktywnych fragmentów przekracza `RAG_EVICTION_MAX_ACTIVE_CHUNKS`, i tylko nadwyżkę. Kandydaci: `tier > 1` i po upływie ochrony.
`score = wiek_dni × (2.0 dla tier 3) × 0.4 − read_count × 0.6 (+30, gdy temat zajmuje > 30% bazy)`.
Nigdy nie schodzi poniżej `RAG_EVICTION_MIN_DOCUMENTS` (100) dokumentów ani `RAG_EVICTION_MIN_DOMAINS` (10) domen, czyli minimum korpusu z briefu.
Soft delete w Postgresie i hard delete w Qdrancie są w jednej transakcji: gdy Qdrant zawiedzie, Postgres się wycofuje.

Konfiguracja: zmienne `RAG_*` (pełna lista w `app/config.py`).
