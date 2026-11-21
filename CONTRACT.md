# Kontrakty między modułami

Zmiana tutaj wymaga wpisu w tym pliku w tym samym PR.

## front ↔ backend (HTTP)
TODO: `POST /api/check` — wejście (tekst lub URL), wyjście (lista twierdzeń z werdyktem, uzasadnieniem, siłą podstawy, źródłami, ograniczeniami albo osobny status błędu).

## backend ↔ agent
TODO: jedna funkcja Go `agent.Verify(ctx, input)` wywoływana tak samo przez każdy kanał (import pakietu, nie HTTP).

## agent ↔ rag
TODO: `agent/` (Go) woła serwis `rag/` (Python) przez HTTP: `POST /search` z twierdzeniem, odpowiedź to lista fragmentów z metadanymi (tytuł, wydawca, data publikacji, data pobrania, licencja, link). Pusta lista oznacza brak wyników. Adres serwisu w `RAG_URL`.

## Statusy
Werdykty: `confirmed`, `false`, `misleading`, `insufficient_evidence`, `not_verifiable`.
Statusy niemerytoryczne (nie są werdyktem): `technical_error`, `needs_clarification`, `out_of_scope`.
