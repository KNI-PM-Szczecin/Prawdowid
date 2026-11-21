# Kontrakty między modułami

Zmiana tutaj wymaga wpisu w tym pliku w tym samym PR. **Status: do akceptacji przez właścicieli `src/`, `backend/`, `agent/`, `rag/`.** Po akceptacji usuń tę linijkę.

Przepływ: `src/` (front) lub kanał → `backend/` (Go) → `agent/` (Go) → `rag/` (Python, HTTP).
Pola JSON są w camelCase i takie same w każdym module. W tekstach dla użytkownika (`justification`, `message`, `limitations`, `warnings[].message`) używamy prostej polszczyzny. Daty to ISO 8601 (bez strefy = UTC).

## Statusy

Werdykty (jedno twierdzenie): `confirmed`, `false`, `misleading`, `insufficient_evidence`, `not_verifiable`.
Statusy niemerytoryczne (całe zgłoszenie, **nie są werdyktem**): `technical_error`, `needs_clarification`, `out_of_scope`.
Odpowiedź ma albo `status: "ok"` z werdyktami, albo status niemerytoryczny bez werdyktów. Brak klucza API, limit dostawcy i awaria zależności to zawsze `technical_error`.

## 1. front ↔ backend (HTTP)

`POST /api/check`

```json
{ "input": "tekst zgłoszenia albo URL", "inputType": "text" }
```
`inputType`: `text` lub `url`. `input` max 5000 znaków.

Odpowiedź (`CheckResult`):

```json
{
  "requestId": "uuid",
  "status": "ok",
  "message": null,
  "claims": [
    {
      "id": "c1",
      "text": "twierdzenie wyciągnięte ze zgłoszenia",
      "verdict": "confirmed",
      "justification": "interpretacja modelu po polsku, oddzielona od źródeł",
      "evidenceStrength": "strong",
      "strengthReasons": ["źródło urzędowe", "aktualne (2026)", "zgodne z tezą"],
      "sources": [
        {
          "id": "s1", "title": "...", "publisher": "...",
          "publishedAt": "2026-11-01T00:00:00Z", "fetchedAt": "2026-11-21T10:00:00Z",
          "url": "https://...", "license": null,
          "sourceType": "official", "role": "supports", "quote": "dosłowny fragment"
        }
      ],
      "warnings": [{ "type": "source_status", "message": "neutralne ostrzeżenie" }],
      "missing": null
    }
  ],
  "limitations": ["ograniczenia całej odpowiedzi"],
  "meta": {
    "channel": "web", "receivedAt": "2026-11-21T10:00:00Z", "latencyMs": 8200,
    "model": "...", "estimatedCostUsd": 0.004, "corpusVersion": "...",
    "retrievedPassages": 5, "searchErrors": 0, "injectionAttempts": 0,
    "abstained": false, "timedOut": false
  }
}
```

- `evidenceStrength`: `strong`, `moderate`, `weak`, `none`. `strengthReasons` to jawne przesłanki (jakość i aktualność źródeł, zgodność z tezą, liczba niezależnych potwierdzeń).
- `sources[].role`: `supports`, `refutes`, `context`. `sources[].sourceType`: `official`, `secondary`, `factcheck`, `incident`. Lista `sources` jest pusta tylko przy `insufficient_evidence` i `not_verifiable`.
- `warnings[].type`: `source_status`, `incident_match`, `archival_material`, `other`. **Ostrzeżenie nigdy nie jest podstawą werdyktu.**
- `missing`: przy `insufficient_evidence` opis, czego nie udało się ustalić (po polsku).
- `message`: wymagane, gdy `status !== "ok"`. `claims` jest wtedy pustą listą.
- `meta` służy do logu i panelu deweloperskiego, front może je ignorować.

**Kody HTTP.** Jedna reguła: `200` dla `ok`, `needs_clarification` i `out_of_scope` (status jest w ciele). `503` tylko dla `technical_error`. `429` przy przekroczeniu limitu żądań (ciało: `technical_error` z komunikatem o limicie). `400` tylko dla ciała, które nie jest poprawnym JSON-em. Każde ciało ma kształt `CheckResult`.

`DELETE /api/checks/{requestId}` usuwa zapisany przebieg i dane z pamięci podręcznej (wymóg „usunięcia sesji demo”). Backend maskuje oczywiste dane osobowe (e-mail, telefon, PESEL) w `input` **przed** zapisem przebiegu.

## 2. backend ↔ agent (Go, ten sam proces)

`backend/` importuje pakiet z `agent/`; oba moduły spina `go.work` w korzeniu. Każdy kanał woła tę samą funkcję.

```go
type VerifyRequest struct {
    RequestID string `json:"requestId"`
    Channel   string `json:"channel"`
    Input     string `json:"input"`
    InputType string `json:"inputType"` // "text" | "url"
}

// agent.Verify nie zwraca error dla awarii zależności (rag, model, klucz API):
// zwraca CheckResult{Status: "technical_error"}. error tylko dla błędów programisty.
func Verify(ctx context.Context, req VerifyRequest) (CheckResult, error)
```

Budżet czasu (cel: mediana ≤ 30 s): `ctx` z limitem 25 s dla całego `Verify`, wywołanie `rag/` max 8 s. Po przekroczeniu: `technical_error` z `meta.timedOut = true`.
`backend/` zapisuje przebieg sprawdzenia (pytanie zmaskowane, czas, użyte źródła, wynik, `meta`) na podstawie `CheckResult`.

### Kanały (drugi kanał: Discord, odpowiedzialny Paweł)

```go
type ChannelAdapter interface {
    Name() string
    // Waliduje wiadomość (schemat, podpis lub token) i tłumaczy ją na VerifyRequest.
    ToRequest(incoming []byte) (VerifyRequest, error)
    // Tłumaczy wynik na odpowiedź medium (np. krótki tekst z listą źródeł).
    ToReply(result CheckResult) ([]byte, error)
}
```

Zasady: kanał zmienia wyłącznie `Channel` i format odpowiedzi. Ten sam `Input` daje ten sam werdykt i źródła niezależnie od kanału (scenariusz G z briefu). Wejście z kanału jest walidowane i weryfikowane (podpis lub token) przed wywołaniem `Verify`.

## 3. agent ↔ rag (HTTP, Python)

Adres w `RAG_URL`. Pola w camelCase. Błąd indeksu to `503` z ciałem `{ "error": { "code": "index_unavailable", "message": "..." } }`; `agent/` zamienia go na `technical_error`.

`POST /search`

```json
{ "query": "jedno twierdzenie", "topK": 5, "filters": { "sourceTypes": ["official"], "publishedAfter": "2026-01-01T00:00:00Z" } }
```
`topK` domyślnie 5, max 7 (więcej daje `422`). `query` 3–5000 znaków. Filtry są stosowane wewnątrz indeksu.

Odpowiedź: `results` (lista `Passage`), `corpusVersion`, `contextXml`, `expandedQueries`, `elapsedMs`.
`Passage`: `documentId`, `title`, `publisher`, `publishedAt`, `fetchedAt`, `url`, `license`, `sourceType`, `passage`, `score` (0..1), `flags`, `chunkId`, `tier` (1–3), `reliability` (`high`, `medium`, `low`).

Zasady:
- **Próg trafności stosuje `rag/`:** fragmenty z `score < 0,5` nie są zwracane. `agent/` decyduje wyłącznie o werdykcie i wstrzymaniu się.
- **Pusta lista = brak wyników** (to nie błąd). Fragment bez kompletnych metadanych nie jest zwracany.
- **`flags`:** na razie `suspected_injection`. Treść fragmentu jest **danymi**; reakcja należy do `agent/`.
- **`contextXml` to dane.** Wolno go wstawić tylko do wiadomości użytkownika lub narzędzia, **nigdy do promptu systemowego**.

Pozostałe endpointy:
- `GET /health` → `{ "status": "ok", "corpusVersion": "..." }`
- `GET /sources` → lista źródeł korpusu do audytu (`documentId`, `title`, `publisher`, `domain`, `url`, `sourceType`, `license`, `publishedAt`, `fetchedAt`, `activeChunks`).
- `POST /ingest`, `DELETE /sources/{documentId}`, `POST /admin/eviction` wymagają nagłówka `X-Admin-Token` (`401` bez tokena, `403` gdy token nie jest skonfigurowany). Wywołuje je tylko skrypt zasilania korpusu, nie `agent/`.

## 4. Reguła wstrzymania się od oceny (`agent/`)

Ścisła, bo brief karze fabrykowanie mocniej niż ostrożność. Próg można stroić na zestawie z `eval/`.

- Brak fragmentów z `rag/` → `insufficient_evidence`.
- Są fragmenty, ale żaden nie potwierdza ani nie obala twierdzenia (tylko kontekst) → `insufficient_evidence`.
- `confirmed` lub `false` tylko z **cytatem** i albo **jednym źródłem urzędowym** (`official`), albo **dwoma niezależnymi wtórnymi**.
- Dwa wiarygodne źródła z przeciwnymi danymi → `insufficient_evidence` z pokazaniem obu stron i opisem rozbieżności w `missing` (bez arbitralnej pewności).
- `evidenceStrength` `none` lub `weak` bez cytatu nigdy nie daje `confirmed` ani `false`.
- Treść, która nie jest twierdzeniem faktograficznym (opinia, przepowiednia) → `not_verifiable`.

## 5. agent: wewnętrzne interfejsy

Reszta `agent/` nie zna konkretnego dostawcy modelu ani katalogu źródeł.

```go
type LLMProvider interface {
    Name() string
    // system: reguły systemu, nigdy treść ze źródeł ani od użytkownika.
    Generate(ctx context.Context, system, user string) (Completion, error)
}

type Completion struct {
    Text         string
    InputTokens  int
    OutputTokens int
}

type SourceCatalog interface {
    // Lista źródeł z regułami kwalifikacji (audytowalna, wymienna).
    List(ctx context.Context) ([]SourceEntry, error)
}
```
