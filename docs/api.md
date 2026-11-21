# API backendu — PROPOZYCJA

> **Status: propozycja, wersja wstępna.** Ten dokument ma być aktualizowany w trakcie budowy API przez osobę, która implementuje dany endpoint. Gdy kod i ten plik się rozjadą, poprawiamy plik w tym samym PR.
>
> Źródłem prawdy jest `CONTRACT.md`. Elementy oznaczone **[NOWE]** wynikają z projektu w Figmie i są wpisane do `CONTRACT.md` §1a jako propozycja do akceptacji (do tego czasu są opcjonalne). Reguły werdyktów (ocena weryfikatora faktów, rozbieżność wyjaśnialna, wydarzenia bieżące, awaria źródła zewnętrznego) są w `CONTRACT.md` §4 po PR #23 i w `spec/mentor-test-scenarios.md`.
>
> Wszystkie dane w przykładach są fikcyjne (adresy `przyklad.*`, wymyślone cytaty).

## 1. Co wynika z projektu w Figmie

| Ekran / element | Potrzebne dane z API | Jest w kontrakcie? |
|---|---|---|
| Nagłówek i pełny tekst artykułu | tytuł i treść sprawdzanego dokumentu (dla URL: pobrana treść) | nie → `document` **[NOWE]** |
| Podświetlony fragment w tekście (stan normal / hover), klik otwiera panel boczny | pozycja twierdzenia w tekście | nie → `claims[].span` **[NOWE]** |
| Box zbiorczy (Figma v2: „Tekst prawdopodobnie prawdziwy” / „Brak pewnego wyniku prawdy” / „Tekst prawdopodobnie jest dezinformacją”, zielony / żółty / czerwony, z pierścieniem) | zbiorcza ocena całego zgłoszenia: `summary.level` → etykieta, `summary.score` → pierścień | nie → `summary` **[NOWE]**, zob. §6 |
| Chipy (Figma v2: „Świeży”, „Archiwalny”, „Oficjalna informacja”, „Brak oficjalnej informacji”; „reputacja” została tylko na starym ekranie Sidebar) | etykiety wyliczone z przesłanek; „reputacja” zastąpiona neutralnym „źródło w katalogu / spoza katalogu” (domena URL vs `GET /sources`) | częściowo (`warnings`) → `badges` **[NOWE]** |
| Czarny box „Ten tekst może być częścią kampanii dezinformacyjnej” + „Więcej informacji” | alert kampanii z linkami do spraw, na poziomie całego tekstu | częściowo (`warnings[].type = incident_match` bez linków) → `campaignAlert` **[NOWE]** |
| Panel boczny: nagłówek = fragment, badge „Fakt”, wyjaśnienie, „Źródła:” | `claims[].text`, `verdict`, `justification`, `sources` | tak |
| Panel „Sprzeczne źródła” (Figma v2: ikona ostrzeżenia, karty z tytułem, wydawcą, datą i linkiem) | informacja o rozbieżności + źródła z obu stron (`title`, `publisher`, `publishedAt`, `url`, `quote`) | częściowo (`missing`, `role`) → `claims[].conflict` **[NOWE]** |
| Ustawienia dostępności (kontrast, rozmiar tekstu, animacje) | nic, tylko front (`localStorage`) | — |
| Strona główna (Figma v2 „Landing”: jedno pole „Wklej link do artykułu bądź tekst…”, notka o AI) | front sam rozpoznaje `inputType` (`http://`/`https://` → `url`), woła `POST /api/check` | tak |

## 2. Lista endpointów

Bazowy adres lokalnie: `http://localhost:3001` (`PORT` w `backend/config.go`). Wszystkie odpowiedzi to JSON (`Content-Type: application/json`), pola w camelCase, daty ISO 8601 UTC.

| Metoda i ścieżka | Po co | Priorytet |
|---|---|---|
| `POST /api/check` | sprawdzenie tekstu lub URL (WWW) | **MVP, pionowy przekrój** |
| `GET /api/checks/{requestId}` **[NOWE]** | odczyt zapisanego wyniku: odświeżenie strony wyniku, link z Discorda do pełnego widoku | MVP |
| `DELETE /api/checks/{requestId}` | usunięcie sesji demo (wymóg prywatności) | MVP |
| `GET /health` | stan backendu i bazy (już działa) | jest |
| `GET /api/sources` **[NOWE]** | lista źródeł korpusu do audytu (proxy do `rag/ GET /sources`) | MVP (wymóg „lista źródeł dostępna do audytu”) |
| bot Discord (Gateway), bez endpointu HTTP | drugi kanał: proces backendu łączy się z Discordem i woła `agent.Verify` bezpośrednio, decyzja zespołu | MVP |
| `GET /api/admin/checks` **[NOWE]** | log sprawdzeń + eksport CSV/JSON | po podstawie (funkcja premiowana) |
| `POST /api/admin/cases`, `GET /api/admin/cases` **[NOWE]** | pętla moderatora | po podstawie (funkcja premiowana) |

Celowo **nie** proponujemy: logowania obywatela, kolejki asynchronicznej (budżet 25 s z kontraktu mieści się w jednym żądaniu), osobnego endpointu na tłumaczenia (teksty są w `src/app/lib/texts.ts`).

## 3. `POST /api/check`

### Żądanie

```json
{ "input": "„Krwawy piątek” 9 października. Policja zatrzymała 59 osób…", "inputType": "text" }
```

```json
{ "input": "https://przyklad-portal.pl/krwawy-piatek-bilans", "inputType": "url" }
```

| Pole | Typ | Zasady |
|---|---|---|
| `input` | string | wymagane, 1–5000 znaków po przycięciu spacji |
| `inputType` | `"text"` \| `"url"` | wymagane; front wykrywa URL sam (zaczyna się od `http://` lub `https://`) |

Nieznane pola → odrzucenie (`DisallowUnknownFields`). Backend maskuje e-mail, telefon i PESEL **przed** zapisem przebiegu i przed wysłaniem do modelu.

### Kody HTTP (z kontraktu)

| Kod | Kiedy | `status` w ciele |
|---|---|---|
| `200` | wynik merytoryczny | `ok` |
| `200` | pytanie niejasne / poza zakresem | `needs_clarification`, `out_of_scope` |
| `400` | ciało nie jest poprawnym JSON-em | zob. pytanie otwarte w §7 |
| `429` | przekroczony limit żądań; nagłówek `Retry-After` w sekundach | `technical_error` |
| `503` | awaria modelu, `rag/`, brak klucza, timeout | `technical_error` |

Każde ciało ma kształt `CheckResult`.

### Przykład A — wynik pozytywny (ekran „Good”)

```json
{
  "requestId": "6f1c2a9e-1b7d-4c55-9a0e-2f3b8c1d4e5a",
  "status": "ok",
  "message": null,
  "document": {
    "title": "„Krwawy piątek” w szkołach. Policja podsumowała bilans działań i zatrzymań.",
    "text": "„Krwawy piątek” to określenie rozpowszechnianych w internecie pogłosek o rzekomych atakach na szkoły zaplanowanych na 9 października. Wiadomości krążą po tragediach na Mazowszu, lecz służby dotąd nie potwierdzają istnienia skoordynowanej akcji.\n\n„Krwawy piątek” 9 października. Policja zatrzymała 59 osób…",
    "url": "https://przyklad-portal.pl/krwawy-piatek-bilans",
    "publisher": "przyklad-portal.pl",
    "fetchedAt": "2026-11-21T10:00:02Z"
  },
  "summary": {
    "level": "high",
    "score": 81,
    "reasons": ["2 z 2 twierdzeń potwierdzone", "w tym 1 źródło urzędowe"]
  },
  "badges": ["official_source_present", "fresh_material", "input_source_in_catalog"],
  "campaignAlert": null,
  "claims": [
    {
      "id": "c1",
      "text": "Ataki na szkoły były zapowiadane na 9 października.",
      "span": { "start": 101, "end": 134 },
      "verdict": "confirmed",
      "justification": "Komunikat policji potwierdza, że pogłoski wskazywały datę 9 października. Policja nie potwierdziła jednak, że ataki były faktycznie planowane.",
      "evidenceStrength": "strong",
      "strengthReasons": ["źródło urzędowe", "aktualne (październik 2026)", "dosłownie zgodne z tezą"],
      "sources": [
        {
          "id": "s1",
          "title": "Komunikat w sprawie pogłosek o zagrożeniu w szkołach",
          "publisher": "Komenda Główna Policji (przykład)",
          "publishedAt": "2026-10-08T00:00:00Z",
          "fetchedAt": "2026-11-20T08:00:00Z",
          "url": "https://przyklad.policja.gov.pl/komunikat-9-pazdziernika",
          "license": "CC BY 4.0",
          "sourceType": "official",
          "role": "supports",
          "quote": "W sieci pojawiły się wpisy zapowiadające ataki na szkoły 9 października."
        }
      ],
      "warnings": [],
      "conflict": null,
      "missing": null
    }
  ],
  "limitations": ["Korpus obejmuje źródła do 20 listopada 2026. Nowsze informacje mogą nie być uwzględnione."],
  "meta": {
    "channel": "web", "receivedAt": "2026-11-21T10:00:00Z", "latencyMs": 8200,
    "model": "example-model", "estimatedCostUsd": 0.004, "corpusVersion": "2026-11-20.1",
    "retrievedPassages": 5, "searchErrors": 0, "injectionAttempts": 0,
    "abstained": false, "timedOut": false
  }
}
```

### Przykład B — fałsz + alert kampanii (ekran „Bad”)

Tylko pola, które się różnią od przykładu A:

```json
{
  "summary": { "level": "low", "score": 12, "reasons": ["1 z 1 twierdzeń obalone przez źródło urzędowe"] },
  "badges": ["fresh_material", "official_source_absent", "input_source_outside_catalog"],
  "campaignAlert": {
    "category": "possible_disinformation_campaign",
    "message": "Treść jest podobna do znanych przypadków dezinformacji. To informacja dodatkowa, nie ocena tego tekstu.",
    "matches": [
      {
        "incidentId": "inc-0042",
        "source": "euvsdisinfo",
        "title": "Fałszywe zapowiedzi ataków na szkoły (przykład)",
        "summary": "Seria wpisów o rzekomo planowanych atakach w wielu krajach UE.",
        "url": "https://przyklad-euvsdisinfo.eu/report/inc-0042",
        "publishedAt": "2026-10-10T00:00:00Z"
      }
    ]
  },
  "claims": [
    {
      "id": "c1",
      "text": "Policja potwierdziła skoordynowaną akcję ataków na szkoły.",
      "span": { "start": 180, "end": 245 },
      "verdict": "false",
      "justification": "Policja w komunikacie wprost zaprzecza, by miała informacje o skoordynowanej akcji.",
      "evidenceStrength": "strong",
      "strengthReasons": ["źródło urzędowe", "aktualne", "wprost przeczy tezie"],
      "sources": [{ "id": "s1", "role": "refutes", "sourceType": "official", "quote": "Nie mamy potwierdzonych informacji o skoordynowanej akcji.", "...": "pozostałe pola jak w A" }],
      "warnings": [{ "type": "incident_match", "message": "Podobne do znanej sprawy dezinformacji." }],
      "conflict": null,
      "missing": null
    }
  ]
}
```

`campaignAlert` i chip `input_source_outside_catalog` **nigdy nie wpływają** na `verdict`, `summary` ani `evidenceStrength` (zakaz z briefu, scenariusz I). Front pokazuje je obok, jako kontekst.

### Przykład C — sprzeczne źródła (panel „Sprzeczne źródła”)

Dwa warianty (`CONTRACT.md` §4 po PR #23, scenariusz C mentora):

**C1, rozbieżność wyjaśnialna** (700 mln zł to przybliżenie z wypowiedzi, 650 mln zł to konkretna pozycja z 2023 r.): werdykt z oceny weryfikatora, oba źródła pokazane, wyjaśnienie w `justification`, `conflict: null`. W `justification` mówimy, kto ocenił („według Demagoga”).

```json
{
  "id": "c1",
  "text": "Wrocław wydaje na komunikację miejską około 700 mln zł.",
  "verdict": "misleading",
  "justification": "Według Demagoga 700 mln zł to przybliżenie z wypowiedzi polityka, a 650 mln zł to wydatki na transport zbiorowy w 2023 r. To nie są dwa sprzeczne pomiary. Demagog ocenił całą wypowiedź jako częściową prawdę.",
  "evidenceStrength": "moderate",
  "strengthReasons": ["ocena weryfikatora faktów tego samego twierdzenia", "liczby dotyczą innego zakresu i roku"],
  "sources": [
    { "id": "s1", "sourceType": "factcheck", "role": "context", "publisher": "Demagog (przykład)", "quote": "Wydatki na transport zbiorowy w 2023 r. wyniosły 650 mln zł. Ocena: częściowa prawda.", "...": "…" },
    { "id": "s2", "sourceType": "secondary", "role": "supports", "quote": "Miasto wydaje na komunikację około 700 mln zł rocznie.", "...": "…" }
  ],
  "warnings": [],
  "conflict": null,
  "missing": null
}
```

**C2, rozbieżność niewyjaśnialna** (panel „Sprzeczne źródła” w Figmie):

```json
{
  "id": "c2",
  "text": "Policja zatrzymała 59 osób.",
  "span": { "start": 260, "end": 287 },
  "verdict": "insufficient_evidence",
  "justification": "Dwa wiarygodne źródła podają różne liczby zatrzymanych. Nie da się ustalić, która jest właściwa.",
  "evidenceStrength": "moderate",
  "strengthReasons": ["źródło urzędowe i wtórne", "sprzeczne dane"],
  "sources": [
    { "id": "s2", "role": "supports", "sourceType": "secondary", "quote": "Do godz. 17:00 zatrzymano 59 osób.", "...": "…" },
    { "id": "s3", "role": "refutes", "sourceType": "official", "quote": "Łącznie zatrzymano 47 osób.", "...": "…" }
  ],
  "warnings": [],
  "conflict": {
    "summary": "Komunikat policji podaje 47 zatrzymanych, artykuł prasowy 59. Możliwe, że dotyczą innych godzin."
  },
  "missing": "Nie ustalono, która liczba jest ostateczna."
}
```

### Przykład D — brak dowodów (scenariusz D)

```json
{
  "id": "c1",
  "text": "Dziś rano minister X podał się do dymisji.",
  "span": { "start": 0, "end": 42 },
  "verdict": "insufficient_evidence",
  "justification": "W dostępnych źródłach nie ma informacji na ten temat.",
  "evidenceStrength": "none",
  "strengthReasons": ["brak pasujących źródeł"],
  "sources": [],
  "warnings": [],
  "conflict": null,
  "missing": "Nie znaleziono żadnej publikacji o dymisji. To może być bardzo świeża informacja. Sprawdź ponownie później."
}
```

Przy samych wstrzymaniach `summary` = `{ "level": "unknown", "score": null, ... }`, a nie 50%.

**Odpowiedź częściowa** (wydarzenie bieżące, scenariusz A mentora „strajk we Włoszech”, przypadek A13): też `insufficient_evidence`, ale z **niepustym** `sources` (to, co ustalono: zapowiedź strajku) i `missing` mówiącym wprost, czego nie wiadomo („Nie mam informacji, czy strajk się odbył”). Nie piszemy, że zdarzenie się nie odbyło.

### Przykład J — awaria źródła zewnętrznego (Google Fact Check)

`rag/` przy błędzie klucza lub limicie **nie** zwraca 503: odpowiada normalnie z `externalSources: [{ "name": "google_factcheck", "status": "error" }]` i wynikami z korpusu. Decyzja należy do `agent/`:

- gdy korpus coś zwrócił → `status: "ok"` z werdyktem z korpusu i wpisem w `limitations`: „Nie mogłem teraz sprawdzić bazy weryfikatorów faktów z powodu błędu dostępu. To nie znaczy, że takiej weryfikacji nie ma.”;
- gdy pytanie dotyczy wyłącznie tego, czy weryfikatorzy coś sprawdzali, a korpus milczy (J03) → `503` + `technical_error` z tym samym komunikatem. Nigdy „nie ma takiego artykułu”.

### Przykład E — status niemerytoryczny

```json
{
  "requestId": "…",
  "status": "needs_clarification",
  "message": "Nie znaleźliśmy w tekście twierdzenia, które da się sprawdzić. Wklej konkretną informację, np. „Rząd podniósł płacę minimalną do 5000 zł”.",
  "document": null, "summary": null, "badges": [], "campaignAlert": null,
  "claims": [],
  "limitations": [],
  "meta": { "...": "…" }
}
```

`503`, gdy model nie odpowiada:

```json
{
  "requestId": "…",
  "status": "technical_error",
  "message": "Nie udało się teraz sprawdzić tej informacji z powodu problemu technicznego. To nie jest ocena treści. Spróbuj ponownie za kilka minut.",
  "document": null, "summary": null, "badges": [], "campaignAlert": null,
  "claims": [], "limitations": [],
  "meta": { "...": "…", "timedOut": true }
}
```

`429` ma to samo ciało z komunikatem o limicie i nagłówek `Retry-After: 30`.

## 4. Pozostałe endpointy

### `GET /api/checks/{requestId}` [NOWE]

Zwraca zapisany `CheckResult` (ten sam kształt co `POST /api/check`, z zamaskowanym `document.text`). `404`, gdy przebieg nie istnieje albo został usunięty:

```json
{ "error": { "code": "not_found", "message": "Nie znaleziono tego sprawdzenia. Mogło zostać usunięte." } }
```

Pozwala na adres strony wyniku `/wynik/{requestId}` we froncie i na link z odpowiedzi na Discordzie.

### `DELETE /api/checks/{requestId}`

`204 No Content` po usunięciu przebiegu i wpisu w pamięci podręcznej. `404` jak wyżej. Bez logowania: kto zna `requestId` (UUID), ten może usunąć (wystarczy na demo, opisać w ryzykach).

### `GET /health`

Już działa: `200 {"status":"ok","database":"ok"}` albo `503 {"status":"degraded","database":"unavailable"}`. Propozycja: dodać `"rag": "ok" | "unavailable"` i `"model": "ok" | "missing_key"`.

### `GET /api/sources` [NOWE]

Proxy do `rag/ GET /sources`, bez zmian kształtu (tylko odczyt, bez tokena):

```json
{
  "corpusVersion": "2026-11-20.1",
  "sources": [
    {
      "documentId": "policja-2026-10-08-szkoly",
      "title": "Komunikat w sprawie pogłosek o zagrożeniu w szkołach",
      "publisher": "Komenda Główna Policji (przykład)",
      "domain": "przyklad.policja.gov.pl",
      "url": "https://przyklad.policja.gov.pl/komunikat-9-pazdziernika",
      "sourceType": "official",
      "license": "CC BY 4.0",
      "publishedAt": "2026-10-08T00:00:00Z",
      "fetchedAt": "2026-11-20T08:00:00Z",
      "activeChunks": 4
    }
  ]
}
```

### Drugi kanał: bot Discord (Gateway) [NOWE, decyzja: bot]

Drugi kanał to **bot na Discordzie** (połączenie wychodzące przez Gateway), nie webhook i nie Interactions Endpoint. Decyzja zespołu, odpowiedzialny Paweł. Konsekwencje:
- **Nie ma endpointu HTTP** dla kanału i nie trzeba publicznego adresu ani tunelu. Bot działa w procesie `backend/` i woła `agent.Verify` bezpośrednio (`ChannelAdapter` z `CONTRACT.md`).
- Token bota w `.env` (`DISCORD_BOT_TOKEN`), nigdy w repo. Bot musi być zaproszony na serwer demo.
- Proponowany sposób użycia: wiadomość w wydzielonym kanale (np. `#prawdowid`) albo wzmianka bota. Odczyt treści wiadomości wymaga włączenia w Discord Developer Portal opcji **Message Content Intent**. Alternatywa bez tej opcji: komenda `/sprawdz`, ale wtedy trzeba w ciągu 3 s potwierdzić odebranie (odpowiedź „deferred”) i dopiero potem wysłać wynik.
- Odpowiedź w jednej wiadomości do 2000 znaków (limit Discorda). Dłuższe wyniki skracamy i dajemy link do pełnego widoku. Podczas sprawdzania bot pokazuje „pisze…”.
- Z kanału wolno zmienić tylko pole `Channel` i format odpowiedzi. Ten sam `Input` daje ten sam wynik co WWW (scenariusz G).
- **Decyzje Pawła (21.11):** (1) bot czyta wiadomości **w kanale lub w wiadomości prywatnej (DM)**, nie przez `/sprawdz`; (2) **tylko stdlib Go**, to ma być MVP; (3) `agent.Verify` jeszcze nie istnieje, więc kanał powstaje na **mocku** zwracającym `CheckResult`.
- **Uwaga techniczna (do potwierdzenia przez Pawła):** stdlib Go **nie ma klienta WebSocket**, a Gateway Discorda go wymaga. Przy samej stdlib realny MVP to odpytywanie REST (`GET /channels/{id}/messages` co 1–2 s dla jednego, wskazanego kanału, odpowiedź przez `POST /channels/{id}/messages`, z uwzględnieniem limitów Discorda). DM są tą drogą trudniejsze, bo bot nie ma prostego sposobu na wylistowanie cudzych DM; wtedy kanał jest drogą podstawową, a DM dopiero przy małej zależności od biblioteki WebSocket. Zmiana na bibliotekę wymaga wpisu w PR (`AGENTS.md`: najpierw stdlib).
- **Kolejność i serwer (decyzja Vanessy, 21.11):** bot Discord jest **ostatnią rzeczą, jaką implementujemy**, po działającym end-to-end (agent, backend, front). Działa na **testowym serwerze** Discorda zakładanym przez nas (jedyny kanał np. `#sprawdz`). Uwaga: brief wymaga **dwóch kanałów albo jednego kanału i adaptera demonstracyjnego** jako warunku podstawowego (bez tego funkcje premiowane nie są punktowane). Jeśli bot nie będzie gotowy, **adapter demonstracyjny musi być gotowy wcześniej**, bo to on spełnia ten warunek. Dla jury potrzebny jest link zaproszenia na serwer w README (token bota nigdy w repo).
- Plan B na brak sieci lub kont: adapter demonstracyjny z tą samą ścieżką `agent.Verify` (brief dopuszcza adapter, gdy organizator nie zapewnia kont).

Odpowiedź w kanale (`ToReply`), przykład:

```
Twierdzenie: Policja potwierdziła skoordynowaną akcję ataków na szkoły.
Ocena: FAŁSZ (podstawa: mocna)
Dlaczego: Policja w komunikacie wprost zaprzecza…
Źródło: Komenda Główna Policji, 08.10.2026, https://…
Pełny wynik: http://localhost:5173/wynik/6f1c2a9e-…
```

### Po podstawie (funkcje premiowane)

- `GET /api/admin/checks?format=json|csv&from=…&to=…` — log sprawdzeń (zamaskowane pytanie, czas, źródła, wynik, `meta`). Wymaga `X-Admin-Token`.
- `POST /api/admin/cases` / `GET /api/admin/cases` — sprawy moderatora dla `insufficient_evidence`, grupowanie podobnych zgłoszeń. Odpowiedź musi rozróżniać `"handoff": "recommended"` od `"handoff": "sent"` (wymóg briefu). Kształt do ustalenia, gdy podstawa działa.

## 5. Proponowane typy (TypeScript, dla frontu)

Pola **[NOWE]** oznaczone komentarzem. Reszta 1:1 z `CONTRACT.md` §1.

```ts
type Verdict = "confirmed" | "false" | "misleading" | "insufficient_evidence" | "not_verifiable";
type Status = "ok" | "technical_error" | "needs_clarification" | "out_of_scope";

interface CheckResult {
  requestId: string;
  status: Status;
  message: string | null;
  document: CheckedDocument | null;   // [NOWE]
  summary: Summary | null;            // [NOWE]
  badges: Badge[];                    // [NOWE]
  campaignAlert: CampaignAlert | null; // [NOWE]
  claims: Claim[];
  limitations: string[];
  meta: Meta;
}

interface CheckedDocument {           // [NOWE]
  title: string | null;               // null dla zwykłego tekstu bez nagłówka
  text: string;                       // zamaskowany tekst, do którego odnoszą się claims[].span
  url: string | null;
  publisher: string | null;
  fetchedAt: string | null;
}

interface Summary {                   // [NOWE]
  level: "high" | "mixed" | "low" | "unknown";
  score: number | null;               // 0–100, null gdy same wstrzymania
  reasons: string[];
}

type Badge =                          // [NOWE] etykiety po polsku w texts.ts; wyliczane z przesłanek, nie przez model
  | "fresh_material" | "archival_material"
  | "official_source_present" | "official_source_absent"
  | "input_source_in_catalog" | "input_source_outside_catalog"; // tylko dla inputType: url

interface Claim {
  id: string;
  text: string;
  span: { start: number; end: number } | null; // [NOWE] pozycje w document.text, w znakach Unicode (code points), end wyłączny
  verdict: Verdict;
  justification: string;
  evidenceStrength: "strong" | "moderate" | "weak" | "none";
  strengthReasons: string[];
  sources: Source[];
  warnings: { type: "source_status" | "incident_match" | "archival_material" | "other"; message: string }[];
  conflict: { summary: string } | null; // [NOWE]
  missing: string | null;
}

interface Source {
  id: string; title: string; publisher: string;
  publishedAt: string | null; fetchedAt: string;
  url: string; license: string | null;
  sourceType: "official" | "secondary" | "factcheck" | "incident";
  role: "supports" | "refutes" | "context";
  quote: string;
}

interface CampaignAlert {             // [NOWE] na poziomie odpowiedzi; kształt z rag/ (CONTRACT.md §3) bez score
  category: "possible_disinformation_campaign";
  message: string;
  matches: { incidentId: string; source: string; title: string; summary: string; url: string; publishedAt: string | null }[];
}
```

Uwaga do `span`: Go liczy w bajtach, JS w jednostkach UTF-16. Proponujemy code points (runy w Go, `Array.from(text)` w JS), żeby polskie znaki i emoji się nie rozjeżdżały. `span: null`, gdy twierdzenie jest parafrazą i nie da się go wskazać w tekście (front pokazuje je wtedy na liście pod tekstem).

## 6. Mapowanie na UI i uwagi do projektu

| `verdict` | Badge w panelu (propozycja) | Kolor |
|---|---|---|
| `confirmed` | Prawda / „Fakt” | zielony |
| `false` | Fałsz | czerwony |
| `misleading` | Wprowadza w błąd | żółty |
| `insufficient_evidence` | Brak wystarczających dowodów; „Sprzeczne źródła”, gdy `conflict != null`; „Ustalono częściowo”, gdy `sources` niepuste | szary / żółty |
| `not_verifiable` | Nie da się sprawdzić (opinia, przewidywanie) | szary |

Rzeczy do decyzji z osobą od designu (stan po Figmie v2, `Untitled (2).zip`):

1. **Procent prawdy** — v2 zastąpiła „81% Pewności prawdy” etykietami („Tekst prawdopodobnie prawdziwy” / „Brak pewnego wyniku prawdy” / „Tekst prawdopodobnie jest dezinformacją”), co zgadza się z `summary.level`. Zostaje pierścień z wypełnieniem (ok. 80 / 50 / 15%): przy `score: null` (same wstrzymania) pierścień ma być pusty albo ukryty, nie „50%”. Opisy wciąż mówią „duży / niski wynik prawdy”; propozycja: „mocna / słaba podstawa”. `summary.score` liczony **deterministycznie w backendzie**, nigdy przez model. Stare ekrany Sidebar nadal mają „81%” — do ujednolicenia.
2. **„Dezinformacja” w czerwonym boksie** — werdykt z briefu to „fałszywe”; „dezinformacja” zakłada intencję, której system nie bada. Propozycja: „Tekst prawdopodobnie fałszywy”. Żółty opis miesza brak dowodów z „częściowo prawdziwe, częściowo fałszywe” (to `misleading`); to dwa różne stany.
3. **Czarny box kampanii** — nadal stwierdza, że tekst „zawiera nieprawdziwe informacje powiązane z… kampaniami”. Dopasowanie do katalogu to kontekst, nie werdykt (brief, scenariusz I). Treść ma być warunkowa: „Treść jest podobna do znanej sprawy dezinformacji. To informacja dodatkowa, nie ocena tego tekstu.” (dokładnie `campaignAlert.message` z `rag/`).
4. **„Sprzeczne źródła”** — v2 naprawiła ikonę (ostrzeżenie zamiast ptaszka) i karty źródeł (tytuł, wydawca, data, link). Brakuje cytatu (`quote`) i roli (`supports` / `refutes`), żeby obywatel widział, która strona co mówi.
5. **Chip reputacji** — w v2 zniknął z ekranów pełnych, został na Sidebar. Zostaje zasada: tylko neutralne „Źródło z naszego katalogu / spoza naszego katalogu” (`input_source_in_catalog` / `input_source_outside_catalog`), bez wpływu na werdykt.
6. **Ekrany** — v2 dodała stronę główną (Landing) i chip „Archiwalny”. Nadal brakuje: stanu ładowania (do 25 s), błędu technicznego, `needs_clarification`, wyniku bez dowodów i odpowiedzi częściowej. Brief: awaria i niejasne pytanie muszą wyglądać **inaczej** niż werdykt. Na Landing notka „Zawsze weryfikuj wszystkie informacje” jest dobra; tekst „Wyniki wygenerowane przez Sztuczną Inteligencję” lepiej zamienić na „Odpowiedź opiera się na źródłach z naszego katalogu; sprawdź je sam”, bo brief każe pokazywać podstawy, nie model.
7. **Panel „Fakt”** — lista „Źródła:” to nadal same domeny (`google.com`). Kontrakt wymaga tytułu, wydawcy, daty i linku, najlepiej z cytatem; brakuje siły podstawy (`evidenceStrength` + `strengthReasons`) i ograniczeń (`limitations`), które `AGENTS.md` każe pokazywać zawsze.
8. **Opis zielonego boksu** „znaczna większość źródeł podaje tą samą informację” — brief zakazuje oceniania po popularności; dozwolona przesłanka to „liczba niezależnych potwierdzeń”. Propozycja: „potwierdzają to niezależne źródła”.

## 7. Pytania otwarte

- `400` dla złego JSON-a: jaki `status` w ciele? Propozycja: `technical_error` z komunikatem „Nieprawidłowe zapytanie”. Za długi lub pusty `input` → `200` + `needs_clarification`.
- ~~Discord: Interactions Endpoint czy bot przez Gateway?~~ Rozstrzygnięte: bot przez Gateway. Zostaje wybór sposobu użycia (kanał z Message Content Intent czy `/sprawdz`) i adapter demonstracyjny jako plan B.
- Czy `document.text` zapisujemy w bazie (potrzebne do `GET /api/checks/{id}`), skoro to pełna treść cudzego artykułu? Propozycja: dla URL przechowujemy tylko zamaskowany fragment do 5000 znaków z retencją 24 h, opisaną w README.
- CORS: front na `localhost:5173`, backend na `3001`. Proponujemy proxy w `vite.config.ts` (`/api` → `3001`) zamiast nagłówków CORS w Go.
- Limit żądań: proponujemy 10 żądań na minutę na IP dla `POST /api/check`, wartość w `.env`.
