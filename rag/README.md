# rag

Python (FastAPI). Korpus źródeł, indeksowanie i wyszukiwanie z metadanymi. Osobny serwis, `agent/` woła go przez HTTP (kontrakt: `../CONTRACT.md`). Zasady: `../AGENTS.md`. Najpierw przeczytaj `../spec`.

## Uruchomienie

Wymaga tylko Dockera.

```
cd rag
docker compose --env-file ../.env up -d --build
```

Serwis: `http://localhost:8001` (OpenAPI: `/docs`). Pierwszy start pobiera modele (ok. 3 GB) do wolumenu `model_cache`, kolejne starty trwają kilka sekund.

Test dymny na fikcyjnych danych:
```
curl -X POST localhost:8001/ingest -H "Content-Type: application/json" --data-binary @tests/smoke_documents.json
```
Polskie znaki w `curl -d '...'` w Git Bash na Windows psują kodowanie, więc ciało zapytania wysyłaj z pliku UTF-8 (`--data-binary @plik.json`).

## Architektura

| Element | Rola |
|---|---|
| Qdrant | Statyczny tekst fragmentu i wektory: dense (BGE-M3, 1024) + sparse (BM25 z IDF). Payload: `chunk_id`, `source_id`, `text`, `topic_tag`. |
| PostgreSQL | `sources` (tytuł, wydawca, link, daty, licencja, typ) i `document_metadata` (tier, wiarygodność, ochrona, `read_count`, soft delete). Stan zmienny jest tu, nie w Qdrancie. |
| FastEmbed (ONNX, CPU) | BGE-M3 dense, BM25 sparse, `bge-reranker-v2-m3` (int8). Wszystko w kontenerze, bez GPU. |
| APScheduler | Eviction codziennie o 3:00, optymalizacja segmentów Qdranta o 4:00. |

Przepływ `POST /search`: ekspansja zapytania (oryginał, negacja, neutralne) → 3 równoległe zapytania hybrydowe (RRF, po 30) → pula 30 unikalnych → reranking cross-encoderem względem oryginału → odcięcie `score < 0` → top 5 (max 7) → złączenie z metadanymi z Postgresa → blok `<dostepne_zrodla>` → w tle `read_count + 1`.

Ekspansja zapytań: domyślnie regułowa. Gdy ustawione jest `RAG_EXPANSION_LLM_URL` (np. FastFlowLM: `http://host.docker.internal:52625/v1`), używa modelu. Przy błędzie wraca do reguł i loguje WARNING.

## Język

Korpus domyślnie po polsku (`RAG_CORPUS_LANGUAGE=pl`). BM25 z FastEmbed nie ma polskiego stemmera, dlatego profil języka (stopwords i lekki stemmer sufiksowy) jest w `app/languages/pl.json`. Nowy język to nowy plik `<kod>.json`. BGE-M3 jest wielojęzyczny i dopasowuje polskie zapytania do źródeł obcojęzycznych.

## Zasilanie korpusu

`POST /ingest` z listą `{ source: {...}, text }` (pola w `app/models.py`: `SourceIn`). Ponowne wysłanie tego samego `source_id` podmienia fragmenty. Tier 1 nigdy nie jest usuwany przez eviction. Nowe fragmenty mają ochronę przez `RAG_PROTECTION_DAYS` (7).

## Eviction

Usuwa tylko wtedy, gdy liczba aktywnych fragmentów przekracza `RAG_EVICTION_MAX_ACTIVE_CHUNKS`, i tylko nadwyżkę. Kandydaci: `tier > 1` i po upływie ochrony.
`score = wiek_dni × (2.0 dla tier 3) × 0.4 − read_count × 0.6 (+30, gdy temat zajmuje > 30% bazy)`.
Soft delete w Postgresie i hard delete w Qdrancie są w jednej transakcji: gdy Qdrant zawiedzie, Postgres się wycofuje.

Konfiguracja: zmienne `RAG_*` (pełna lista w `app/config.py`).
