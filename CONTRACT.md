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
    "abstained": false, "timedOut": false, "cached": false
  }
}
```

- `evidenceStrength`: `strong`, `moderate`, `weak`, `none`. `strengthReasons` to jawne przesłanki (jakość i aktualność źródeł, zgodność z tezą, liczba niezależnych potwierdzeń).
- `sources[].role`: `supports`, `refutes`, `context`. `sources[].sourceType`: `official`, `secondary`, `factcheck`, `incident`, `reference` (dane encyklopedyczne o osobie z Wikidaty: opis, data urodzenia i śmierci, przynależność partyjna i pełnione funkcje z latami; jako podstawa liczy się jak `official`). Lista `sources` jest pusta tylko przy `insufficient_evidence` i `not_verifiable`.
- `warnings[].type`: `source_status`, `incident_match`, `archival_material`, `other`. **Ostrzeżenie nigdy nie jest podstawą werdyktu.**
- `archival_material` (scenariusz B): `agent/` dodaje je do każdego twierdzenia, gdy sprawdzana strona (`inputType: url`) ma `document.publishedAt` starsze niż rok; treść mówi, kiedy stronę opublikowano. Do `limitations` trafia ta sama informacja, a przy braku daty publikacji zdanie, że nie wiadomo, czy treść jest aktualna. Data publikacji materiału idzie też do promptu sędziego (`judge.user.md`, „Data publikacji sprawdzanego materiału”), żeby prawdziwy materiał podany w złym czasie dostał `misleading` z cytatem pokazującym właściwy czas.
- `incident_match` to dodatkowa kategoria „możliwa część kampanii dezinformacyjnej”. `agent/` tworzy ją z `campaignAlert` z `rag/` (§3): `message` z alertu, linki do dopasowanych spraw. Front pokazuje ją obok werdyktu, poza `evidenceStrength`; nie zmienia werdyktu ani siły podstawy.
- `missing`: przy `insufficient_evidence` opis, czego nie udało się ustalić (po polsku).
- `message`: wymagane, gdy `status !== "ok"`. `claims` jest wtedy pustą listą.
- `meta` służy do logu i panelu deweloperskiego, front może je ignorować.

Walidacja wejścia: nieznany `inputType`, pusty albo za długi `input` daje `200` ze statusem `needs_clarification` (bez wołania `agent/` i bez zapisu). Limit żądań: `CHECK_RATE_LIMIT_PER_MINUTE` na adres klienta (domyślnie 20).

**Adresy.** Dla `inputType: url` `agent/` pobiera stronę przez `POST /fetch` w `rag/` (§3) i odpowiada według powodu odmowy: serwis wideo albo społecznościowy (YouTube, TikTok, Facebook, Instagram, X i inne z `rag/app/data/fetch_rules.json`) → `out_of_scope` z prośbą o wklejenie treści wpisu; plik zamiast strony (PDF, obraz, dokument) → `needs_clarification` z komunikatem o pliku; zapora antybotowa albo strona bez tekstu w HTML → `needs_clarification` z komunikatem o blokadzie; błąd HTTP, sieć, adres niepubliczny → `needs_clarification` „nie udało się odczytać”. Żaden z tych statusów nie jest werdyktem. Dla `inputType: text` z **dokładnie jednym** adresem w treści (np. „sprawdź też tę stronę: …”) `agent/` pobiera tę stronę i sprawdza ją razem z tekstem: `document.text` to tekst zgłoszenia, pusta linia i tytuł z treścią strony, `document.url` i `document.publishedAt` z pobrania, a polecenia ukryte w stronie są wykrywane i liczone jak w zgłoszeniu (scenariusz E). Nieudane pobranie takiego linku daje tylko wpis w `limitations` (sprawdzony sam tekst), kilka adresów w tekście nie jest pobieranych (wpis w `limitations`). Front klasyfikuje jako `url` tylko wejście będące samym adresem.

`POST /api/check/image` (scenariusz F): `multipart/form-data` z polem `image` (PNG, JPEG albo WEBP do 5 MB, typ sprawdzany po zawartości, nie po deklaracji). Backend wysyła obraz do `POST /ocr` w `rag/` (Tesseract lokalnie, bez zewnętrznego API obrazu; obraz nie jest zapisywany po żadnej stronie), odczytany tekst maskuje i sprawdza tą samą ścieżką co tekst wpisany ręcznie. Odpowiedź ma kształt `CheckResult` jak w `POST /api/check` (`document.text` to odczytany tekst, przebieg zapisany z `inputType: "image"`), a `limitations` zaczyna się od zdania, że tekst pochodzi z OCR i może mieć błędy odczytu, oraz, gdy na obrazie widać datę, że to data w treści obrazu, a nie potwierdzona data publikacji. Brak pliku, zły format albo za duży plik → `200 needs_clarification`; obraz bez czytelnego tekstu → `200 needs_clarification` z prośbą o wpisanie treści; niedostępny OCR → `503 technical_error`. Tekst dłuższy niż 5000 znaków jest ucinany z wpisem w `limitations`. Nie robimy wyszukiwania odwrotnego obrazu ani oceny autentyczności zdjęcia.

**Kody HTTP.** Jedna reguła: `200` dla `ok`, `needs_clarification` i `out_of_scope` (status jest w ciele). `503` tylko dla `technical_error`. `429` przy przekroczeniu limitu żądań (`CHECK_RATE_LIMIT_PER_MINUTE`, domyślnie 60 na adres; ciało: `technical_error` z komunikatem o limicie, nagłówek `Retry-After` w sekundach). `400` tylko dla ciała, które nie jest poprawnym JSON-em. Każde ciało ma kształt `CheckResult`.

`DELETE /api/checks/{requestId}` usuwa zapisany przebieg i dane z pamięci podręcznej (wymóg „usunięcia sesji demo”). Odpowiedź: `204` po usunięciu, `404` gdy takiego przebiegu nie ma, `400` dla identyfikatora, który nie jest UUID v4 (ciało błędu ma kształt `CheckResult` ze statusem `technical_error`). Przebiegi starsze niż `CHECK_RETENTION_DAYS` (domyślnie 30) backend usuwa sam. Backend maskuje identyfikatory osobowe (e-mail, telefon, PESEL, numer dowodu osobistego i paszportu, numer konta) w `input` **przed** zapisem przebiegu i przed wysłaniem tekstu do `agent/`; w zapisanym wyniku maskuje też `document` (tytuł i tekst, przycięty do 5000 znaków), twierdzenia, uzasadnienia, tytuły i cytaty źródeł. Odpowiedź dla użytkownika zostaje pełna. Zasada mentorów (Discord, 22.11.2026): nie maskujemy niczego, bez czego zmienia się sens zapytania albo nie da się znaleźć dowodu, w szczególności nigdy imion i nazwisk osób publicznych; daty, kwoty i miejsca zostają.

`GET /api/sources`, `GET /api/sources/catalog`, `GET /api/sources/external` → odpowiedzi `rag/` `GET /sources`, `GET /sources/catalog`, `GET /sources/external` (§3) przekazane bez zmian (lista źródeł korpusu do audytu, katalog z zasadami kwalifikacji, źródła zewnętrzne). `rag/` nie ma publicznego adresu, więc to jedyna publiczna droga do audytu źródeł (wymóg briefu). Awaria `rag/` → `503 { "error": { "code": "sources_unavailable", "message": "..." } }`, nigdy pusta lista.

`GET /livez` → `200 {"status":"ok"}` bez zapytania do bazy (sonda żywotności, np. dla Railway; `GET /health` zostaje sondą gotowości i daje `503` przy awarii bazy). Limit żądań liczy adres klienta z wpisu `X-Forwarded-For` o numerze `TRUSTED_PROXY_HOPS` liczonym od prawej (domyślnie 1), z powrotem do adresu połączenia. Treść za duża (ponad 64 KB) daje `200 needs_clarification`, a dane po obiekcie JSON dają `400`.

### 1a. Rozszerzenia pod projekt UI (Figma) — PROPOZYCJA, do akceptacji

Status: wdrożone poza `conflict` (przykłady i mapowanie na ekrany Figma v3 w `docs/api.md`). Żadne z tych pól nie zmienia werdyktu ani `evidenceStrength`. Stan: `document` (dla URL i dla tekstu: `document.text` to sprawdzony, zamaskowany tekst), `campaignAlert` i `claims[].span` zwraca `agent/`; `summary`, `badges` i `cases` dokłada backend w `POST /api/check` (nie w odpowiedziach odrzuconych przed `agent/`, np. walidacja i `429`, ani w kanale demo); `conflict` nie jest jeszcze zwracany (pole nie występuje w JSON, front traktuje brak jak `null`). `span` to pozycja dosłownego fragmentu (pole `fragment` z ekstrakcji, a w zapasie samo zdanie twierdzenia) w `document.text`, bez rozróżniania wielkości liter; parafraza daje `null`. Opinie, oceny i przewidywania z tekstu wielozdaniowego ekstrakcja oznacza `rodzaj: opinia`: trafiają do `claims` jako `not_verifiable` bez wyszukiwania i bez źródeł, z stałym uzasadnieniem.

```json
{
  "document": { "title": "tytuł albo null", "text": "zamaskowany tekst zgłoszenia lub pobranej strony", "url": null, "publisher": null, "publishedAt": null, "fetchedAt": null },
  "materialMatch": null,
  "summary": { "level": "high", "reasons": ["2 z 2 twierdzeń potwierdzone", "w tym 1 źródło urzędowe"] },
  "badges": ["official_source_present", "fresh_material"],
  "campaignAlert": null,
  "claims": [{ "span": { "start": 101, "end": 134 }, "conflict": null }]
}
```

- `document`: to, co front pokazuje jako tekst z podświetleniami. Dla `inputType: url` tekst pobranej strony (główny `<article>`/`<main>`, do 20 000 znaków z `POST /fetch` w rag), `title`, `url`, `publishedAt` i `fetchedAt` z pobrania, `publisher` na razie zawsze `null`. `claims[].span` wskazuje twierdzenie w `document.text` w **code points** (runy w Go, `Array.from(text)` w JS), `end` wyłączny; `null`, gdy twierdzenie jest parafrazą.
- `summary`: zbiorcza ocena całego zgłoszenia liczona **deterministycznie w backendzie** z werdyktów, nigdy przez model. `level`: `high` (wszystkie rozstrzygnięte twierdzenia `confirmed`), `low` (wszystkie `false`), `mixed` (mieszanka albo `misleading`), `unknown` (żadne twierdzenie nie ma `confirmed`, `false` ani `misleading`; wstrzymanie się nie jest „50% prawdy”). Bez procentu: pole `score` usunięte, UI v3 pokazuje ikonę i etykietę. `reasons` to jawne przesłanki po polsku. Przy statusie innym niż `ok` → `null`.
- `badges`: etykiety wyliczone z jawnych przesłanek, nigdy z opinii modelu: `fresh_material` / `archival_material` z najnowszego `publishedAt` użytych źródeł (próg wieku w konfiguracji, brak dat → bez chipa), `official_source_present` / `official_source_absent` z `sourceType` użytych źródeł. Odłożone, bo UI v3 ich nie pokazuje: `input_source_in_catalog` / `input_source_outside_catalog` z dopasowania domeny zgłoszonego URL do `GET /sources/catalog` (tylko dla `inputType: url`); to neutralna informacja o statusie źródła, nie ocena jego „reputacji”.
- `cases` (zawsze lista, pusta gdy nic nie zapisano): zamknięta pętla informacji (scenariusz H). Dla każdego twierdzenia z werdyktem `insufficient_evidence` backend zapisuje zgłoszenie w sprawie `{ "claimId", "caseId", "reports", "status" }`. Parafrazy trafiają do tej samej sprawy (`POST /reports/match` w rag). `status`: `logged` (zapisane), `recommended` (co najmniej `MODERATOR_REPEAT_THRESHOLD` zgłoszeń, domyślnie 3, albo dopasowanie do znanej kampanii; reguła w kodzie, nie w modelu), `forwarded` (webhook moderatora `MODERATOR_WEBHOOK_URL` przyjął sprawę, odpowiedź 2xx). Bez webhooka albo po jego błędzie sprawa zostaje `recommended`: rekomendacja przekazania nigdy nie jest pokazywana jako przekazanie. Awaria pętli nie zmienia odpowiedzi poza pustą listą `cases`. Treść twierdzenia w sprawie jest maskowana jak `input`, retencja jak dla przebiegów (`CHECK_RETENTION_DAYS` od ostatniego zgłoszenia).
- `GET /api/admin/cases` z nagłówkiem `X-Admin-Token` = `MODERATOR_TOKEN` → `{ "cases": [{ "caseId", "claim", "reports", "campaign", "status", "createdAt", "updatedAt", "forwardedAt" }] }`, najczęściej zgłaszane pierwsze (do 200). Lista dla analityka i eksport JSON. Bez skonfigurowanego tokena `403`, zły token `401`.
- `campaignAlert`: alert na poziomie całej odpowiedzi, przepisany z `campaignAlert` z `rag/` (§3) bez `score`; `warnings[].type: incident_match` przy twierdzeniu zostaje. Kontekst, nie dowód.
- `materialMatch` (tylko dla `inputType: url`, inaczej `null`): dopasowanie **samej strony** do znanego materiału (scenariusz I), `{ "message": "po polsku, z nazwaną podstawą", "matches": [{ "kind": "corpus_document" | "incident", "basis": ["url"] | ["title", "date"], "title", "publisher", "url", "publishedAt", "sourceType", "incidentId", "source" }] }` z `POST /match` w `rag/` (§3). Podstawa jest jawna: zgodny adres (po normalizacji: bez `www.`, parametrów śledzących i fragmentu) albo zgodny tytuł **i** data publikacji (±1 dzień). Podobny temat ani sama domena nie są dopasowaniem; bez dopasowania `agent/` dodaje ograniczenie, że strony nie znaleziono w źródłach ani w katalogu i że sama domena o niczym nie przesądza. Awaria `/match` daje tylko ograniczenie, nigdy `technical_error`. `materialMatch` nie wpływa na werdykt, `summary` ani `evidenceStrength`. `document.publishedAt` to data publikacji pobranej strony z jej metadanych (`null`, gdy brak).
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

Budżet czasu (cel: mediana ≤ 30 s): `ctx` z limitem 45 s dla całego `Verify`, wywołanie `rag/` max 30 s, jedno wywołanie modelu max 15 s (`rag/` podniesione z 8 s do 12 s po pomiarach na Railway, gdzie rerank na współdzielonym CPU trwa 6–9 s, potem do 18 s, a teraz do 30 s, bo uzupełnianie korpusu z gov.pl, przeskok na źródła pierwotne i pobranie na żądanie komunikatu Odyseusza potrzebują czasu przy pierwszym pytaniu o temat; mediana zostaje ≤ 30 s, bo kolejne pytania trafiają w gotowy korpus i cache; `RAG_TIMEOUT_SECONDS` nadpisuje wartość). Jedno `/search` w `rag/` trwa najwyżej `RAG_SEARCH_TOTAL_BUDGET_SECONDS` (14 s) razem z uzupełnianiem korpusu (gov.pl i Odyseusz 6 s, przeskok 6 s, ponowienia Fact Check 4 s), więc mieści się w każdym limicie agenta (także w starszym 18 s); po budżecie odpowiedź idzie bez uzupełnienia (`gov_search` ze statusem `skipped`), a uzupełnianie kończy się w tle. Druga runda agenta rusza tylko, gdy do końca `Verify` zostało co najmniej 20 s. Backend: `WriteTimeout` 60 s, limit sprawdzenia z kanału Discord 50 s; front przerywa żądanie po 55 s. Po przekroczeniu: `technical_error` z `meta.timedOut = true`.

**Spójność wyników (cache backendu).** Gotowy wynik sprawdzenia jest zapamiętywany na `CHECK_RESULT_CACHE_MINUTES` (30 min; 0 wyłącza) pod skrótem SHA-256 z rodzaju wejścia i treści po maskowaniu danych osobowych (małe litery, pojedyncze spacje); treść zgłoszenia nie jest kluczem. To samo pytanie na WWW, w kanale demonstracyjnym i w bocie Discord dostaje wtedy ten sam wynik (werdykty, źródła, uzasadnienie) z własnym `requestId`, kanałem, `receivedAt` i `meta.cached = true`; przebieg jest zapisywany jak każdy inny. `technical_error` nigdy nie trafia do cache. Nagłówek `Cache-Control: no-cache` na `POST /api/check` liczy wynik od nowa i nadpisuje zapamiętany. Cache jest w pamięci procesu, więc każdy deploy go czyści.
`backend/` zapisuje przebieg sprawdzenia (pytanie zmaskowane, czas, użyte źródła, wynik, `meta`) na podstawie `CheckResult`.

### Kanały (drugi kanał: adapter demonstracyjny `POST /api/channels/demo` z ciałem `{ "text": "..." }` i odpowiedzią tekstową jak w komunikatorze, albo bot Discord `/factcheck` w `src/backend/discord.go`; oba używają tej samej ścieżki weryfikacji co WWW)

```go
type ChannelAdapter interface {
    Name() string
    // Waliduje wiadomość (schemat, podpis lub token) i tłumaczy ją na VerifyRequest.
    ToRequest(incoming []byte) (VerifyRequest, error)
    // Tłumaczy wynik na odpowiedź medium (np. krótki tekst z listą źródeł).
    ToReply(result CheckResult) ([]byte, error)
}
```

Zasady: kanał zmienia wyłącznie `Channel` i format odpowiedzi. Ten sam `Input` daje ten sam werdykt i źródła niezależnie od kanału (scenariusz G z briefu). Wejście z kanału jest walidowane (schemat, ten sam limit długości i ten sam limit żądań co `/api/check`) przed wywołaniem `Verify`. Adapter demonstracyjny nie ma podpisu ani tokena i nie zakłada spraw pętli informacji. Bot Discord weryfikuje tożsamość sesją Gateway (`discordgo`), więc nie wymaga podpisu ani tokenu per żądanie; po przejściu na endpoint HTTP interactions wymagany jest podpis na kluczu `DISCORD_BOT_PUBLIC_KEY`.

## 3. agent ↔ rag (HTTP, Python)

Adres w `RAG_URL`. Pola w camelCase. Błąd indeksu to `503` z ciałem `{ "error": { "code": "index_unavailable", "message": "..." } }`; `agent/` zamienia go na `technical_error`.

`POST /search`

```json
{ "query": "jedno twierdzenie", "topK": 5, "filters": { "sourceTypes": ["official"], "publishedAfter": "2026-01-01T00:00:00Z" } }
```
`topK` domyślnie 5, max 7 (więcej daje `422`). `query` 3–5000 znaków. Filtry są stosowane wewnątrz indeksu.

Odpowiedź: `results` (lista `Passage`), `corpusVersion`, `contextXml`, `expandedQueries` (`original`, `negative`, `neutral`, `keywords`, `method`; `keywords` to 2–6 słów kluczowych, którymi `rag` pyta wyszukiwarkę gov.pl, bo ta działa słowo-kluczowo, a całe zdanie tezy tonie w szumie), `elapsedMs`, `externalSources`, `campaignAlert` (albo `null`, opis niżej).
`externalSources`: lista `{ "name": "google_factcheck" | "incident_catalog" | "gov_search" | "primary_hop" | "wikidata", "status": "ok" | "disabled" | "skipped" | "error", "results": 0 }`. Dla `incident_catalog`: `disabled` = pusty katalog, `results` = liczba dopasowanych spraw. `disabled` = brak klucza, `skipped` = filtr `sourceTypes` bez `factcheck`, `error` = awaria lub limit zewnętrznego API. Awaria źródła zewnętrznego **nie** daje `503`; `agent/` może ją doliczyć do `meta.searchErrors`. Dla `gov_search` (uzupełnianie korpusu z wyszukiwarki gov.pl): wpis jest tylko wtedy, gdy korpus dał mniej niż `RAG_GOV_SEARCH_MIN_RESULTS` trafnych fragmentów i filtr dopuszcza `official`; `results` = liczba stron wgranych do korpusu przed ponownym wyszukiwaniem, `ok` z `results: 0` = nic nowego albo uzupełnianie dokończy się w tle (strony trafią do korpusu dla kolejnych pytań), `disabled` = `RAG_GOV_SEARCH_ENABLED=false`, `error` = awaria wyszukiwarki gov.pl. Ponieważ korpus rośnie, to samo pytanie zadane drugi raz może dostać więcej źródeł niż za pierwszym razem. `primary_hop` (przeskok ze źródła wtórnego na pierwotne): gdy uzupełnienie z gov.pl nie dało wyraźnie trafnego fragmentu (najlepszy `score` poniżej `RAG_GOV_SEARCH_SUFFICIENT_SCORE`), `rag/` szuka w polskiej Wikipedii artykułu o zdarzeniu (po słowach kluczowych) i czyta z niego **wyłącznie adresy przypisów**. Artykuł nie jest indeksowany i nigdy nie jest dowodem; do korpusu wchodzą tylko strony z domen katalogu źródeł (bez kopii archiwalnych), wybrane przez model pomocniczy z listy kandydatów albo, bez modelu, po zgodności słów adresu z tezą, i tylko z datą publikacji. Dokumenty mają identyfikator `hop:<skrót>`. Wikipedia dostaje tylko słowa kluczowe tezy. `status`: `ok` (`results` = liczba zaindeksowanych stron), `disabled` (`RAG_HOP_ENABLED=false`), `error` (awaria API Wikipedii).
`results` ma najwyżej `topK` elementów, malejąco po `score`, plus najwyżej `RAG_WIKIDATA_MAX_PEOPLE` (2) fragmenty `reference` z Wikidaty o osobach wymienionych w twierdzeniu (wyszukiwane po nazwach pisanych wielką literą, tylko ludzie; dopasowane po nazwie, więc dołączane niezależnie od progu rerankera, ze swoim `score`), plus najwyżej jeden fragment na każdy artykuł weryfikatora faktów (`factcheck`) z wyników, którego żaden zwrócony fragment nie podaje oceny: `rag/` dokłada wtedy fragment tego samego artykułu z oceną (frazy z `rating_phrases` w `rag/app/languages/pl.json`), żeby model widział werdykt weryfikatora. Google Fact Check jest pytany pełnym twierdzeniem i jego słowami kluczowymi równolegle; gdy nic nie pasuje do twierdzenia (co najmniej 2 wspólne słowa tematyczne), `rag/` próbuje kolejno krótszych sformułowań, łącznie najwyżej `RAG_FACTCHECK_MAX_ATTEMPTS` (5) w `RAG_FACTCHECK_RETRY_BUDGET_SECONDS` (8 s); błąd HTTP przerywa ponowienia. `score` to sigmoid(logit rerankera BGE / 4), skala 0..1.
`Passage`: `documentId`, `title`, `publisher`, `publishedAt`, `fetchedAt`, `url`, `license`, `sourceType`, `passage`, `score` (0..1), `flags`, `chunkId`, `tier` (1–3), `reliability` (`high`, `medium`, `low`).

Zasady:
- **Próg trafności stosuje `rag/`:** fragmenty z `score < 0,5` nie są zwracane. `agent/` decyduje wyłącznie o werdykcie i wstrzymaniu się.
- **Pusta lista = brak wyników** (to nie błąd). Fragment bez kompletnych metadanych nie jest zwracany: `title`, `publisher`, `url`, `fetchedAt` i `publishedAt` są obowiązkowe w `results`. Fragmenty bez daty publikacji (np. część stron ze scrapera) pozostają w audycie `GET /sources`, ale nie są dowodem. Fact-check bez daty weryfikacji również nie wraca w `results`.
- **`flags`:** na razie `suspected_injection`. Treść fragmentu jest **danymi**; reakcja należy do `agent/`.
- **`contextXml` to dane.** Wolno go wstawić tylko do wiadomości użytkownika lub narzędzia, **nigdy do promptu systemowego**.
- **Fact-checki z Google Fact Check Tools API** wracają w tych samych `results`, przez ten sam reranker i próg, z `sourceType: "factcheck"`, `documentId` z prefiksem `factcheck:`, `url` do weryfikacji, `publisher` = weryfikator, `publishedAt` = data weryfikacji, `license: null`, `tier: 2`, `reliability: "medium"`. `passage` streszcza po polsku sprawdzone twierdzenie i ocenę weryfikatora (np. „Fałsz”). Ocena należy do weryfikatora: jest dowodem do cytowania, a nie gotowym werdyktem systemu.
- **`campaignAlert`** (albo `null`): dopasowanie twierdzenia do katalogu znanych kampanii dezinformacyjnych (EUvsDisinfo, baza incydentów organizatora). Kształt: `{ "category": "possible_disinformation_campaign", "message": "…", "matches": [{ "incidentId", "source", "title", "summary", "url", "publishedAt", "score" }] }`. Próg dopasowania 0,7 (ostrzejszy niż dla dowodów), maks. 3 sprawy. **Sprawy z katalogu nigdy nie trafiają do `results` ani `contextXml`**: to kontekst, nie dowód (scenariusz I z briefu, zakaz werdyktu na podstawie etykiety).
- **Katalog kampanii przy starcie `rag/` dostaje upsert `app/data/seed_incidents.json` (trzy publiczne sprawy EUvsDisinfo, tylko kontekst) — przy każdym starcie, nie tylko gdy katalog jest pusty, bo import EUvsDisinfo może wcisnąć się przed seed i sprawy demo wypadłyby z okna najnowszych N. Upsert jest idempotentny (ta sama sprawa = ten sam punkt). `RAG_SEED_INCIDENTS_ENABLED=false` wyłącza to zachowanie; import z EUvsDisinfo nadal działa po ustawieniu tokena.
Pozostałe endpointy:
- `POST /reports/match` z `{ "claim": "zamaskowane twierdzenie bez rozstrzygnięcia" }` → `{ "caseId", "matched", "score" }`. Woła tylko backend (pętla informacji); endpoint nie wymaga tokena, bo rag słucha tylko w sieci wewnętrznej, a każde wywołanie zapisuje zgłoszenie. Twierdzenie jest porównywane cross-encoderem z wcześniejszymi zgłoszeniami w kolekcji `unresolved_reports` w obu kierunkach; mniejszy wynik ≥ 0,65 oznacza tę samą sprawę, inaczej powstaje nowa. Każde zgłoszenie jest zapisywane (tekst i `caseId`), żeby kolejne parafrazy mogły trafić w którekolwiek z nich. Zgłoszeń w Qdrant nie usuwa jeszcze retencja: to znane ograniczenie.
- `POST /ocr` (`multipart/form-data`, pole `image`: PNG, JPEG, WEBP do 5 MB i 25 Mpx) → `{ "text", "confidence", "dates", "engine" }`: tekst odczytany lokalnie przez Tesseract (`pol+eng`, do 5000 znaków), średnia pewność słów 0–1, daty widoczne w tekście (dd.mm.rrrr, rrrr-mm-dd, „12 marca 2024”) i nazwa silnika. Obraz jest przetwarzany w pamięci i nie jest zapisywany. Nie-obraz, za duży plik, za dużo pikseli albo brak tekstu → `422` z powodem; brak silnika → `503`. Woła tylko backend (`POST /api/check/image`).
- `POST /match` z `{ "url", "title", "publishedAt" }` (dane pobranej strony) → `{ "matches": [{ "kind": "corpus_document" | "incident", "basis": ["url"] | ["title", "date"], "title", "publisher", "url", "publishedAt", "sourceType", "incidentId", "source" }] }`: czy zgłoszona strona jest znanym materiałem. Dokumenty korpusu po znormalizowanym adresie (bez `www.`/`m.`, parametrów `utm_*`, `fbclid` itp., fragmentu i końcowego `/`) albo po tytule (pokrycie słów ≥ 0,6) **i** dacie publikacji (±1 dzień); wpisy katalogu kampanii po adresach materiału, który rozpowszechniał treść (`links`, z EUvsDisinfo `linksToDisinformation`). Maks. 5 dopasowań, pusta lista to brak dopasowania. Kontekst o materiale, nigdy ocena treści; sama domena nie jest dopasowaniem.
- `POST /fetch` z `{ "url": "https://..." }` → `{ "url", "title", "text", "truncated", "publishedAt" }` (`publishedAt` z metadanych strony: `article:published_time`, JSON-LD `datePublished`, `<time datetime>`; `null`, gdy brak): tekst publicznej strony dla `agent/`, gdy zgłoszenie jest adresem URL (ten sam parser co przy zasilaniu korpusu, tekst do 20 000 znaków, strona nie jest zapisywana). Błąd pobrania, nie-HTML albo brak tekstu w HTML → `422` z `{ "detail": { "message": "po polsku z powodem", "code": "unsupported_host" | "not_html" | "no_text" | "bot_wall" | "http_error" | "network" | "blocked" | "redirect" | "too_large" } }`; `agent/` dobiera po `code` status i komunikat (§1). Adresy serwisów wideo i społecznościowych z `rag/app/data/fetch_rules.json` (host i poddomeny) są odrzucane bez żadnego żądania do serwisu (`unsupported_host`): nie odczytujemy wideo ani dźwięku, a wpisy tych serwisów wymagają skryptu albo logowania; zabezpieczeń nie obchodzimy. **Guard URL:** podany adres i każdy cel przekierowania (redirecty robione ręcznie, maks. 5) są sprawdzane przed pobraniem: tylko http/https, porty 80/443, wszystkie adresy DNS muszą być publiczne (loopback, sieci prywatne, link-local z metadanymi chmury 169.254.169.254 — odrzucane, SSRF). Treść pobierana strumieniowo z limitem 2 MB liczonym w trakcie pobierania.
- `GET /health` → `{ "status": "ok" | "degraded", "corpusVersion", "database", "vectorIndex", "incidentCatalog" }` (każda zależność `ok` albo `unavailable`; `degraded` daje `503`). `GET /livez` nie istnieje w rag (jest w backendzie).
- `GET /sources` → lista źródeł korpusu do audytu (`documentId`, `title`, `publisher`, `domain`, `url`, `sourceType`, `license`, `publishedAt`, `fetchedAt`, `activeChunks`, `inCatalog`).
- `GET /sources/catalog` → katalog zaufanych źródeł z regułami kwalifikacji (`version`, `note`, `rules`, `entries[]` z `publisher`, `domains`, `sourceType`, `tier`, `reliability`, `qualification`). Plik danych `rag/app/data/sources_catalog.json`, wymienny bez zmian w kodzie. Backend może nim zasilać `badges` (`input_source_in_catalog`) zamiast listą wgranych dokumentów.
- `POST /ingest`: `sourceType`, `tier` i `reliability` można pominąć dla domeny z katalogu (rag uzupełnia je z katalogu); dla domeny spoza katalogu są wymagane, inaczej `422`. Dokument o tej samej treści co inny aktywny dokument daje `409` i nie jest wgrywany; tak samo parafraza (fragmenty niemal identyczne wektorowo z innym dokumentem, komunikat z dopiskiem „parafraza”). Ochrona przed zalewaniem korpusu kopiami.
- **Startowy korpus demo:** przy starcie `rag/` indeksuje brakujące dokumenty z `app/data/seed_documents.json` (dosłowne fragmenty publicznych źródeł z kompletem metadanych: tytuł, wydawca, `publishedAt`, `fetchedAt`, link, licencja). Dzięki temu demo nie zależy od dostępności stron i od ręcznego `POST /admin/corpus/fetch`. `RAG_SEED_CORPUS_ENABLED=false` wyłącza uzupełnianie; istniejące `documentId` są pomijane, a błąd jednego dokumentu nie blokuje startu.
- `GET /sources/external` → źródła spoza korpusu używane przy wyszukiwaniu (`google_factcheck`, `gov_search`, `euvsdisinfo`): `name`, `provider`, `url`, `role`, `dataSent` (co dostaje dostawca), `terms`, `env`, `enabled`, a dla katalogu kampanii `catalogSize`, `lastSyncFinishedAt`, `lastSyncIndexed`. Do audytu źródeł razem z `GET /sources` i `GET /sources/catalog`.
- `GET /incidents` → `{ "catalogSize": 0, "euvsdisinfo": { "enabled", "running", "lastFinishedAt", "lastIndexed", "lastSkipped", "lastError", "available" } }` (audyt katalogu kampanii i stan importu z EUvsDisinfo).
- `POST /admin/incidents/sync?maxCases=1000` → `202` i stan jak wyżej; uruchamia w tle import najnowszych spraw z serwera MCP EUvsDisinfo do katalogu (`403`, gdy brak `EUVSDISINFO_TOKEN`). Ten sam import działa automatycznie raz na dobę.
- `POST /admin/corpus/sync?maxDocuments=5000` → `202`; w tle wgrywa do korpusu strony z tabeli scrapera we wspólnej bazie (`ScrappedData`: `id`, `date` RRRRMMDD, `site`, `title`, `content`) przez zwykłą ścieżkę `ingest` (katalog, duplikaty, chunking). `GET /corpus/sync` → `{ "running", "lastFinishedAt", "available", "indexed", "alreadyPresent", "skippedDuplicates", "skippedExcluded", "skippedOutsideCatalog", "failed", "lastError" }` (ten sam kształt mają `GET /corpus/fetch` i `GET /corpus/law`). `documentId` ma prefiks `scrapped:`, `fetchedAt` = data ze scrapera, `publishedAt` = `null`.
- `POST /admin/corpus/fetch` z ciałem `{ "urls": [...] }` (maks. 100) albo bez ciała (lista startowa `rag/app/data/seed_urls.json`) → `202`; w tle pobiera publiczne strony HTML, wyciąga tekst i wgrywa je jak strony scrapera (`documentId` z prefiksem `web:`). Strony bez tekstu w HTML, nie-HTML i błędy HTTP liczą się jako `failed`. `publishedAt` pochodzi z metadanych strony (`article:published_time`, JSON-LD `datePublished`, `<time datetime>`); gdy ich brak, wolno użyć daty przypiętej w `seed_urls.json` tylko wtedy, gdy jest widoczna w treści lub w akcie prawnym. Strona bez ustalonej daty pozostaje w audycie, ale nie jest dowodem. `GET /corpus/fetch` → stan jak w `GET /corpus/sync`.
- Odświeżanie źródeł urzędowych bez ręcznej ingerencji: `rag/` pobiera ponownie listę startową stron codziennie (`RAG_CORPUS_REFRESH_CRON_HOUR`, 5:00) i importuje ponownie akty z Dziennika Ustaw raz w tygodniu (`RAG_LAW_REFRESH_CRON_DAY_OF_WEEK` `mon`, 6:00); zmieniona strona podmienia swoje fragmenty, nowy tekst jednolity zastępuje stary `law:<id>`. `RAG_CORPUS_REFRESH_ENABLED=false` wyłącza. Ręczne `POST /admin/corpus/fetch` i `POST /admin/corpus/law` zostają.
- **Kanały RSS (świeże komunikaty):** `rag/app/data/feeds.json` wymienia kanały RSS źródeł z katalogu (dziś komunikaty policji: Komenda Główna i Małopolska). `rag/` czyta je co `RAG_FEEDS_REFRESH_INTERVAL_MINUTES` (60) i indeksuje tylko wpisy, których korpus jeszcze nie ma, zwykłą ścieżką wchłaniania (katalog, duplikaty, cytat). Data publikacji pochodzi z kanału. Wpisy z kanału mają identyfikator `feed:<skrót>` i dla wskazanych hostów (`exemptHosts`) nie obowiązuje reguła wykluczania hosta z `corpus_rules.json` (kroniki policyjne są wykluczone z importów zbiorczych, ale świeży komunikat policji potrafi rozstrzygnąć twierdzenie); reguły adresów i tytułów (listy, strony główne) nadal obowiązują. `POST /admin/corpus/feeds` (token admina, `202`) uruchamia czytanie od razu, `GET /corpus/feeds` pokazuje postęp w kształcie `CorpusSyncStatus`; `POST /admin/corpus/prune` takich dokumentów nie usuwa.
- **Odyseusz MSZ (komunikaty dla podróżnych):** `rag/` czyta publiczne, nieuwierzytelnione API JSON serwisu odyseusz.gov.pl, z którego korzysta sama strona (`GET /api/v1/informacje/profile-panstw/mini` — lista państw z kodami ISO, `GET /api/v1/informacje/profile-panstw/{ISO}` — profil państwa, `GET /api/v1/informacje/{ISO}/ostrzezenia` — poziom ostrzeżenia). Jeden dokument na komunikat państwa (`sourceType: official`, wydawca MSZ), `publishedAt` = `dataAktualizacji` z profilu. Tekst komunikatu (`trescPowiadomieniaDluga`) nie zawiera nazwy państwa, więc nazwa (`nazwa` z profilu) trafia do tytułu dokumentu, żeby wyszukiwanie po nazwie państwa trafiało. Komunikaty są odświeżane co godzinę i pobierane na żądanie podczas `/search`, gdy twierdzenie wymienia państwo z listy (w budżecie wywołania `rag/`). Odyseusz dostaje tylko kod ISO państwa. Pierwszy pełny import rusza `RAG_ODYSEUSZ_FIRST_RUN_DELAY_MINUTES` (45) po starcie, żeby liczenie wektorów nie spowalniało pierwszych sprawdzeń po wdrożeniu; do tego czasu działa pobieranie na żądanie. `RAG_ODYSEUSZ_ENABLED=false` wyłącza. `GET /corpus/odyseusz` pokazuje postęp importu w kształcie `CorpusSyncStatus`, `POST /admin/corpus/odyseusz` (token admina, `202`) uruchamia import od razu.
- Pamięć podręczna `/search`: to samo `query` + `filters` + `topK` w ciągu 10 min i przy tej samej `corpusVersion` zwraca identyczną odpowiedź (spójność kanałów, scenariusz G). Tylko w RAM rag.
- **Powtarzalność:** ekspansja zapytań ma `temperature: 0` i cache po hashu twierdzenia (domyślnie 1 h). Hosted OpenAI dostaje temperaturę tylko przy `reasoning_effort=none` (dokumentacja API zabrania jej dla innych wartości); przy innym wysiłku rozumowania `rag/` używa reguł zamiast modelu, żeby to samo wejście dawało te same zapytania pomocnicze. To nie zastępuje cache `/search`.
- `POST /ingest`, `DELETE /sources/{documentId}`, `POST /incidents`, `DELETE /incidents/{source}/{incidentId}`, `POST /admin/incidents/sync`, `POST /admin/corpus/sync`, `POST /admin/corpus/fetch`, `POST /admin/corpus/law`, `POST /admin/corpus/odyseusz`, `POST /admin/corpus/prune`, `POST /admin/corpus/reconcile`, `POST /admin/eviction` wymagają nagłówka `X-Admin-Token` (`401` bez tokena, `403` gdy token nie jest skonfigurowany). Wywołuje je tylko skrypt zasilania korpusu, nie `agent/`.
- Reguły korpusu (`rag/app/data/corpus_rules.json`): strony-listy, strony główne i lokalne kroniki policyjne nie wchodzą do korpusu przy żadnym imporcie zbiorczym, a `POST /admin/corpus/prune[?dryRun=true]` usuwa te już wgrane z importów zbiorczych (`scrapped:`, `web:`, `law:`; dokumentów z `POST /ingest` nie rusza) i zwraca `{ "dryRun", "documentsDeleted", "chunksDeleted", "documentIds" }`. `POST /admin/corpus/reconcile[?includeUnknown=true]` usuwa z tabeli wektorów wiersze oznaczone w metadanych jako usunięte, oznacza jako usunięte aktywne metadane bez wektora (sieroty blokowałyby ponowny import) i zwraca `{ "staleDeleted", "unknown", "unknownDeleted", "orphanMetadataDeleted", "activeChunks" }`; `includeUnknown` tylko gdy nie trwa import (kod tego nie sprawdza). `POST /admin/corpus/law?maxChars=` importuje z tabeli `Law` scrapera akty z `rag/app/data/law_acts.json` (najnowszy tekst jednolity, `documentId` = `law:<id>`, URL pozycji w Dzienniku Ustaw, data ogłoszenia jako `publishedAt`); postęp w `GET /corpus/law`.

## 4. Reguła wstrzymania się od oceny (`agent/`)

Ścisła, bo brief karze fabrykowanie mocniej niż ostrożność. Próg można stroić na zestawie z `eval/`.

- Brak fragmentów z `rag/` → `insufficient_evidence`.
- Są fragmenty, ale żaden nie potwierdza ani nie obala twierdzenia (tylko kontekst) → `insufficient_evidence`.
- `confirmed` lub `false` tylko z **cytatem** i albo **jednym źródłem urzędowym** (`official`), albo **dwoma niezależnymi wtórnymi**, albo **oceną weryfikatora faktów** (patrz niżej).
- **Polecenia w zgłoszeniu** (próba sterowania modelem, prośba nie na temat) są liczone w `meta.injectionAttempts`, opisane w `limitations` i wycinane z tekstu, który `agent/` sprawdza, od miejsca wykrycia do końca zdania. Nie trafiają do twierdzenia, zapytania do `rag/` ani do modelu; `document.text` pokazuje pełne zgłoszenie. Samo polecenie bez treści do sprawdzenia → `needs_clarification`.
- **Brak publikacji o dużym zdarzeniu.** Gdy twierdzenie dotyczy zdarzenia o znaczeniu ogólnokrajowym, które według dzisiejszej daty powinno już się wydarzyć (model oznacza to polem `szeroko_opisane`), a nic go nie potwierdza, werdykt zostaje `insufficient_evidence` (brief: bez dowodu nie ma werdyktu), ale twierdzenie dostaje ostrzeżenie (`warnings[].type = other`), że milczenie mediów i instytucji to silny sygnał nieprawdziwości. Przy sprawach lokalnych i zapowiedziach ostrzeżenia nie ma. `false` tylko wtedy, gdy źródło obala twierdzenie, także opisując aktualny stan nie do pogodzenia z nim (np. komunikaty o wsparciu zamiast wojny, przepis o innych kompetencjach organu).
- **Etykiety.** Front, kanał demonstracyjny i bot Discord pokazują `insufficient_evidence` jako „Niepewne” (brak źródeł, jedno słabe źródło albo tylko część faktów; czego nie ustalono, mówi `missing`), a źródła `supports` i `refutes` naraz jako „Sprzeczne źródła”.
- **Druga runda przy jednym źródle.** Gdy model rozstrzyga twierdzenie na jednym źródle wtórnym, `agent/` szuka drugi raz przeformułowaniem z `rag/` (`expandedQueries.keywords`, w zapasie `negative`), dokłada nowe fragmenty i ocenia ponownie. Drugie niezależne źródło zgodne z pierwszym daje werdykt (podstawa `strong`), sprzeczne daje `insufficient_evidence` z obiema stronami w `sources` (front pokazuje sprzeczność). Gdy nadal jest jedno źródło, zostaje `insufficient_evidence`. Błąd drugiej rundy nie psuje odpowiedzi.
- **Rozbieżność źródeł.** Najpierw ustal, czy dane naprawdę sobie przeczą, czy opisują coś innego (przybliżenie a konkretna pozycja, inny rok, inny zakres). Jeśli da się to wyjaśnić, napisz wyjaśnienie w `justification`, pokaż oba źródła, a werdykt weź z oceny weryfikatora (np. „częściowa prawda” → `misleading`). Jeśli rozbieżności nie da się wyjaśnić → `insufficient_evidence` z obiema stronami w `sources` i opisem w `missing` (bez arbitralnej pewności).
- **Ocena weryfikatora faktów** (`factcheck`, np. Demagog) dotycząca **tego samego twierdzenia** wystarcza jako podstawa `confirmed`, `false` albo `misleading` (prawda → `confirmed`, fałsz → `false`, częściowa prawda, manipulacja, brak kontekstu → `misleading`). Odpowiedź mówi, kto to ocenił („według Demagoga”) i linkuje publikację. Samo podobieństwo tematu nie wystarcza.
- **Wydarzenia bieżące i niepełne dane.** Gdy część faktów jest ustalona, a część nie (np. zapowiedź strajku jest, a wyniku nie ma), podaj to, co ustalono, wskaż źródła i napisz wprost, czego nie wiadomo → `insufficient_evidence` z niepustym `sources` i opisem w `missing`. Nie pisz, że zdarzenie się nie odbyło.
- **Źródła kontekstowe przy wstrzymaniu się.** Gdy werdykt to `insufficient_evidence`, a model oceniający nie podał dosłownego cytatu, `agent/` dołącza do `sources` najlepsze zwrócone fragmenty z rolą `context` (prawdziwe fragmenty z `rag/`, z pełnymi metadanymi), żeby obywatel widział, na czym oparto ostrożność. Źródło o innym miejscu lub czasie niż twierdzenie jest kontekstem, nie obaleniem: nie daje `false`.
- **Awaria zewnętrznego źródła** (np. Google Fact Check) nigdy nie znaczy „nie ma takiej publikacji”. Odpowiedź ujawnia ograniczenie w `limitations` („nie mogę teraz sprawdzić…”); gdy przy tym korpus nie dał żadnego fragmentu dla twierdzenia (awaria usługi była jedyną możliwą podstawą) → `technical_error` z komunikatem o błędzie dostępu do weryfikatorów (scenariusz J mentora).
- `evidenceStrength` `none` lub `weak` bez cytatu nigdy nie daje `confirmed` ani `false`.
- Treść, która nie jest twierdzeniem faktograficznym (opinia, przepowiednia) → `not_verifiable`.
- **Czas i miejsce (scenariusz B).** Sędzia dostaje dzisiejszą datę i datę publikacji sprawdzanego materiału (dla tekstu: „nieznana”). Prawdziwy materiał przedstawiony jako bieżący, choć źródła umieszczają go w innym czasie lub miejscu (stary stan prawny, dawne wydarzenie, inne miasto) → `misleading` z cytatem pokazującym właściwy czas lub miejsce. Sam wiek strony nie zmienia werdyktu: daje ostrzeżenie `archival_material` i wpis w `limitations`.

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
