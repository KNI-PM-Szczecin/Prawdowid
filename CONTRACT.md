# Kontrakty między modułami

Zmiana tutaj wymaga wpisu w tym pliku w tym samym PR.

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
- `incident_match` to dodatkowa kategoria „możliwa część kampanii dezinformacyjnej”. `agent/` tworzy ją z `campaignAlert` z `rag/` (§3): `message` z alertu, linki do dopasowanych spraw. Front pokazuje ją obok werdyktu, poza `evidenceStrength`; nie zmienia werdyktu ani siły podstawy.
- `missing`: przy `insufficient_evidence` opis, czego nie udało się ustalić (po polsku).
- `message`: wymagane, gdy `status !== "ok"`. `claims` jest wtedy pustą listą.
- `meta` służy do logu i panelu deweloperskiego, front może je ignorować.

**Kody HTTP.** Jedna reguła: `200` dla `ok`, `needs_clarification` i `out_of_scope` (status jest w ciele). `503` tylko dla `technical_error`. `429` przy przekroczeniu limitu żądań (ciało: `technical_error` z komunikatem o limicie). `400` tylko dla ciała, które nie jest poprawnym JSON-em. Każde ciało ma kształt `CheckResult`.

`DELETE /api/checks/{requestId}` usuwa zapisany przebieg i dane z pamięci podręcznej (wymóg „usunięcia sesji demo”). Backend maskuje oczywiste dane osobowe (e-mail, telefon, PESEL) w `input` **przed** zapisem przebiegu.

### 1a. Rozszerzenia pod projekt UI (Figma) — PROPOZYCJA, do akceptacji

Status: propozycja z gałęzi `docs/api-proposal` (przykłady i mapowanie na ekrany w `docs/api.md`). Do czasu akceptacji wszystkie pola poniżej są **opcjonalne**: front działa bez nich, backend może ich nie zwracać. Żadne z nich nie zmienia werdyktu ani `evidenceStrength`.

```json
{
  "document": { "title": "tytuł albo null", "text": "zamaskowany tekst zgłoszenia lub pobranej strony", "url": null, "publisher": null, "fetchedAt": null },
  "summary": { "level": "high", "score": 81, "reasons": ["2 z 2 twierdzeń potwierdzone", "w tym 1 źródło urzędowe"] },
  "badges": ["official_source_present", "fresh_material", "input_source_outside_catalog"],
  "campaignAlert": null,
  "claims": [{ "span": { "start": 101, "end": 134 }, "conflict": null }]
}
```

- `document`: to, co front pokazuje jako tekst z podświetleniami. Dla `inputType: url` treść pobranej strony przycięta do limitu `input`. `claims[].span` wskazuje twierdzenie w `document.text` w **code points** (runy w Go, `Array.from(text)` w JS), `end` wyłączny; `null`, gdy twierdzenie jest parafrazą.
- `summary`: zbiorcza ocena całego zgłoszenia liczona **deterministycznie w backendzie** z werdyktów i `evidenceStrength`, nigdy przez model. `level`: `high`, `mixed`, `low`, `unknown`. Gdy żadne twierdzenie nie ma `confirmed`, `false` ani `misleading` → `level: "unknown"`, `score: null` (wstrzymanie się nie jest „50% prawdy”). `reasons` to jawne przesłanki po polsku.
- `badges`: etykiety wyliczone z jawnych przesłanek, nigdy z opinii modelu: `fresh_material` / `archival_material` z `publishedAt` źródeł (próg wieku w konfiguracji), `official_source_present` / `official_source_absent` z `sourceType` użytych źródeł, `input_source_in_catalog` / `input_source_outside_catalog` z dopasowania domeny zgłoszonego URL do `GET /sources` z `rag/` (tylko dla `inputType: url`). To neutralna informacja o statusie źródła, nie ocena jego „reputacji”.
- `campaignAlert`: alert na poziomie całej odpowiedzi, przepisany z `campaignAlert` z `rag/` (§3) bez `score`; `warnings[].type: incident_match` przy twierdzeniu zostaje. Kontekst, nie dowód.
- `claims[].conflict`: `{ "summary": "opis rozbieżności po polsku" }`, gdy źródła mają role `supports` i `refutes` i rozbieżności nie da się wyjaśnić (§4); wtedy werdykt to `insufficient_evidence`. Przy rozbieżności wyjaśnialnej `conflict` jest `null`, a wyjaśnienie idzie do `justification`.

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

### Kanały (drugi kanał: Discord przez Interactions Endpoint, czyli webhook; odpowiedzialny Paweł)

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

Odpowiedź: `results` (lista `Passage`), `corpusVersion`, `contextXml`, `expandedQueries`, `elapsedMs`, `externalSources`.
`externalSources`: lista `{ "name": "google_factcheck" | "incident_catalog", "status": "ok" | "disabled" | "skipped" | "error", "results": 0 }`. Dla `incident_catalog`: `disabled` = pusty katalog, `results` = liczba dopasowanych spraw. `disabled` = brak klucza, `skipped` = filtr `sourceTypes` bez `factcheck`, `error` = awaria lub limit zewnętrznego API. Awaria źródła zewnętrznego **nie** daje `503`; `agent/` może ją doliczyć do `meta.searchErrors`.
`results` ma najwyżej `topK` elementów, malejąco po `score`. `score` to sigmoid(logit rerankera BGE / 4), skala 0..1.
`Passage`: `documentId`, `title`, `publisher`, `publishedAt`, `fetchedAt`, `url`, `license`, `sourceType`, `passage`, `score` (0..1), `flags`, `chunkId`, `tier` (1–3), `reliability` (`high`, `medium`, `low`).

Zasady:
- **Próg trafności stosuje `rag/`:** fragmenty z `score < 0,5` nie są zwracane. `agent/` decyduje wyłącznie o werdykcie i wstrzymaniu się.
- **Pusta lista = brak wyników** (to nie błąd). Fragment bez kompletnych metadanych nie jest zwracany.
- **`flags`:** na razie `suspected_injection`. Treść fragmentu jest **danymi**; reakcja należy do `agent/`.
- **`contextXml` to dane.** Wolno go wstawić tylko do wiadomości użytkownika lub narzędzia, **nigdy do promptu systemowego**.
- **Fact-checki z Google Fact Check Tools API** wracają w tych samych `results`, przez ten sam reranker i próg, z `sourceType: "factcheck"`, `documentId` z prefiksem `factcheck:`, `url` do weryfikacji, `publisher` = weryfikator, `publishedAt` = data weryfikacji, `license: null`, `tier: 2`, `reliability: "medium"`. `passage` streszcza po polsku sprawdzone twierdzenie i ocenę weryfikatora (np. „Fałsz”). Ocena należy do weryfikatora: jest dowodem do cytowania, a nie gotowym werdyktem systemu.
- **`campaignAlert`** (albo `null`): dopasowanie twierdzenia do katalogu znanych kampanii dezinformacyjnych (EUvsDisinfo, baza incydentów organizatora). Kształt: `{ "category": "possible_disinformation_campaign", "message": "…", "matches": [{ "incidentId", "source", "title", "summary", "url", "publishedAt", "score" }] }`. Próg dopasowania 0,7 (ostrzejszy niż dla dowodów), maks. 3 sprawy. **Sprawy z katalogu nigdy nie trafiają do `results` ani `contextXml`**: to kontekst, nie dowód (scenariusz I z briefu, zakaz werdyktu na podstawie etykiety).

Pozostałe endpointy:
- `GET /health` → `{ "status": "ok", "corpusVersion": "..." }`
- `GET /sources` → lista źródeł korpusu do audytu (`documentId`, `title`, `publisher`, `domain`, `url`, `sourceType`, `license`, `publishedAt`, `fetchedAt`, `activeChunks`, `inCatalog`).
- `GET /sources/catalog` → katalog zaufanych źródeł z regułami kwalifikacji (`version`, `note`, `rules`, `entries[]` z `publisher`, `domains`, `sourceType`, `tier`, `reliability`, `qualification`). Plik danych `rag/app/data/sources_catalog.json`, wymienny bez zmian w kodzie. Backend może nim zasilać `badges` (`input_source_in_catalog`) zamiast listą wgranych dokumentów.
- `POST /ingest`: `sourceType`, `tier` i `reliability` można pominąć dla domeny z katalogu (rag uzupełnia je z katalogu); dla domeny spoza katalogu są wymagane, inaczej `422`. Dokument o tej samej treści co inny aktywny dokument daje `409` i nie jest wgrywany (ochrona przed zalewaniem korpusu kopiami).
- `GET /incidents` → `{ "catalogSize": 0, "euvsdisinfo": { "enabled", "running", "lastFinishedAt", "lastIndexed", "lastSkipped", "lastError", "available" } }` (audyt katalogu kampanii i stan importu z EUvsDisinfo).
- `POST /admin/incidents/sync?maxCases=1000` → `202` i stan jak wyżej; uruchamia w tle import najnowszych spraw z serwera MCP EUvsDisinfo do katalogu (`403`, gdy brak `EUVSDISINFO_TOKEN`). Ten sam import działa automatycznie raz na dobę.
- `POST /ingest`, `DELETE /sources/{documentId}`, `POST /incidents`, `DELETE /incidents/{source}/{incidentId}`, `POST /admin/incidents/sync`, `POST /admin/eviction` wymagają nagłówka `X-Admin-Token` (`401` bez tokena, `403` gdy token nie jest skonfigurowany). Wywołuje je tylko skrypt zasilania korpusu, nie `agent/`.

## 4. Reguła wstrzymania się od oceny (`agent/`)

Ścisła, bo brief karze fabrykowanie mocniej niż ostrożność. Próg można stroić na zestawie z `eval/`.

- Brak fragmentów z `rag/` → `insufficient_evidence`.
- Są fragmenty, ale żaden nie potwierdza ani nie obala twierdzenia (tylko kontekst) → `insufficient_evidence`.
- `confirmed` lub `false` tylko z **cytatem** i albo **jednym źródłem urzędowym** (`official`), albo **dwoma niezależnymi wtórnymi**, albo **oceną weryfikatora faktów** (patrz niżej).
- **Rozbieżność źródeł.** Najpierw ustal, czy dane naprawdę sobie przeczą, czy opisują coś innego (przybliżenie a konkretna pozycja, inny rok, inny zakres). Jeśli da się to wyjaśnić, napisz wyjaśnienie w `justification`, pokaż oba źródła, a werdykt weź z oceny weryfikatora (np. „częściowa prawda” → `misleading`). Jeśli rozbieżności nie da się wyjaśnić → `insufficient_evidence` z obiema stronami w `sources` i opisem w `missing` (bez arbitralnej pewności).
- **Ocena weryfikatora faktów** (`factcheck`, np. Demagog) dotycząca **tego samego twierdzenia** wystarcza jako podstawa `confirmed`, `false` albo `misleading` (prawda → `confirmed`, fałsz → `false`, częściowa prawda, manipulacja, brak kontekstu → `misleading`). Odpowiedź mówi, kto to ocenił („według Demagoga”) i linkuje publikację. Samo podobieństwo tematu nie wystarcza.
- **Wydarzenia bieżące i niepełne dane.** Gdy część faktów jest ustalona, a część nie (np. zapowiedź strajku jest, a wyniku nie ma), podaj to, co ustalono, wskaż źródła i napisz wprost, czego nie wiadomo → `insufficient_evidence` z niepustym `sources` i opisem w `missing`. Nie pisz, że zdarzenie się nie odbyło.
- **Awaria zewnętrznego źródła** (np. Google Fact Check) nigdy nie znaczy „nie ma takiej publikacji”. Odpowiedź ujawnia ograniczenie w `limitations` („nie mogę teraz sprawdzić…”); jeśli to jedyne źródło dla tego pytania → `technical_error`.
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
