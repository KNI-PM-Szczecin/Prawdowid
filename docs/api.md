# API backendu — PROPOZYCJA (częściowo wdrożona)

> **Status: częściowo wdrożone.** Wdrożone w `src/backend/`: `POST /api/check`, `DELETE /api/checks/{requestId}`, `POST /api/channels/demo`, `GET /api/admin/cases`, `GET /health`, `GET /livez`. Pozostałe elementy **[NOWE]** są nadal propozycją. Gdy kod i ten plik się rozjadą, poprawiamy plik w tym samym PR.
>
> Źródłem prawdy jest `CONTRACT.md`. Elementy oznaczone **[NOWE]** wynikają z projektu w Figmie i są wpisane do `CONTRACT.md` §1a jako propozycja do akceptacji (do tego czasu są opcjonalne). Reguły werdyktów (ocena weryfikatora faktów, rozbieżność wyjaśnialna, wydarzenia bieżące, awaria źródła zewnętrznego) są w `CONTRACT.md` §4 i w `spec/mentor-test-scenarios.md`.
>
> Stan projektu UI: **Figma v3** (`Untitled (1).zip`, 21.11, 20:06). Kod: API w `src/backend/`, logika w `agent/` (`agent.NewFromEnv`, `Verify`, od PR #46), źródła w `rag/`. Plan implementacji backendu krok po kroku jest w §8, dostępność w §6a.
>
> Wszystkie dane w przykładach są fikcyjne (adresy `przyklad.*`, wymyślone cytaty).

## 1. Co wynika z projektu w Figmie

| Ekran / element | Potrzebne dane z API | Jest w kontrakcie? |
|---|---|---|
| Nagłówek i pełny tekst artykułu | `document` (tytuł, treść, adres). Zwraca go `agent/` dla URL i dla tekstu (dla tekstu: `title: null`, `text` = zamaskowane wejście) | `CONTRACT.md` §1a, `agent/` zwraca |
| Podświetlony fragment w tekście (stan normal / hover), klik otwiera panel boczny | pozycja twierdzenia w tekście: `claims[].span` | §1a, **`agent/` zwraca** (`agent/span.go`); `span: null` dla parafrazy, wtedy front pokazuje twierdzenie tylko na liście pod tekstem |
| Box zbiorczy (v3: ikona ✓ / ⚠ / ✕ w pełnym kole, etykieta, opis; pierścień z „81%” został tylko na starym ekranie Sidebar) | `summary.level` → ikona, etykieta i opis. Poziom z reguł kontraktu (§8), **bez pola `score`**, UI nie pokazuje procentu | §1a, **liczy backend** (reguły w §8) |
| Chipy (v3: „Świeży” / „Archiwalny”, „Oficjalna informacja” / „Brak oficjalnej informacji”) | `badges` z czterema wartościami. Dla `inputType: url` backend dodaje chip katalogu `input_source_in_catalog` / `input_source_outside_catalog` z `rag/ GET /sources/catalog` (`src/backend/catalog.go`); gdy katalog niedostępny, chipa nie ma. UI v3 chipów katalogu nie pokazuje | §1a, **liczy backend** (reguły w §8) |
| Czarny box „Ten tekst może być częścią kampanii dezinformacyjnej” + „Więcej informacji” | `campaignAlert` (komunikat + linki do spraw), na poziomie całego tekstu | §1a, `agent/` już zwraca |
| Box „Znamy ten materiał” (tylko dla URL): komunikat z nazwaną podstawą, lista dopasowań z linkiem, wydawcą, datą i podstawą („zgodny adres” albo „zgodny tytuł, zgodna data publikacji”) | `materialMatch` z `POST /match` w rag (dokument korpusu po adresie albo tytule i dacie; wpis katalogu kampanii po adresie materiału). Bez dopasowania `limitations` mówi, że strony nie znaleziono i sama domena o niczym nie przesądza. `document.publishedAt` pokazywane pod adresem | §1a, **`agent/` zwraca** (`agent/agent.go` `matchMaterial`, `src/frontend/src/components/MaterialMatchBox.tsx`) |
| Panel boczny: nagłówek = fragment, badge „Fakt”, wyjaśnienie, „Źródła:” | `claims[].text`, `verdict`, `justification`, `evidenceStrength`, `strengthReasons`, `sources` | tak |
| Panel „Sprzeczne źródła” (ikona ostrzeżenia, karty z tytułem, wydawcą, datą i linkiem) | `claims[].conflict` + źródła z obu stron (`role`: `supports` / `refutes`, `quote`) | §1a, **`agent/` jeszcze nie zwraca** → front do czasu wnioskuje z ról źródeł |
| Panel ustawień dostępności (v3, zrzut wzorcowy: kontrast domyślny / wysoki jasny / wysoki ciemny, rozmiar tekstu 100–200%, „ogranicz animacje”, „przywróć domyślne”) | nic z API; front, `localStorage` + `prefers-contrast` / `prefers-reduced-motion`, zob. §6a | — |
| Strona główna („Landing”: jedno pole „Wklej link do artykułu bądź tekst…”, notka o AI) | front sam rozpoznaje `inputType` (`http://`/`https://` → `url`), woła `POST /api/check` | tak |

## 2. Lista endpointów

Bazowy adres lokalnie: `http://localhost:3001` (`PORT` w `src/backend/config.go`). Wszystkie odpowiedzi to JSON (`Content-Type: application/json`), pola w camelCase, daty ISO 8601 UTC.

| Metoda i ścieżka | Po co | Priorytet |
|---|---|---|
| `POST /api/check` | sprawdzenie tekstu lub URL (WWW). Tekst z jednym linkiem w środku sprawdza też tę stronę; link do wideo/serwisu społecznościowego → `out_of_scope`, plik → `needs_clarification` (tabela w `README.md`, kody w `CONTRACT.md` §3) | **MVP, pionowy przekrój** |
| `POST /api/check/image` (wdrożone, `src/backend/check_image.go`) | zrzut ekranu lub zdjęcie z tekstem (scenariusz F): `multipart/form-data`, pole `image` (PNG/JPEG/WEBP do 5 MB). OCR lokalnie w rag (`POST /ocr`, Tesseract), odczytany tekst idzie tą samą ścieżką `runCheck` co tekst; odpowiedź jak `POST /api/check` plus ograniczenia o OCR i o dacie widocznej na obrazie | funkcja premiowana |
| `GET /api/checks/{requestId}` **[NOWE, niezaimplementowane]** | odczyt zapisanego wyniku: odświeżenie strony wyniku, link z drugiego kanału do pełnego widoku | MVP |
| `DELETE /api/checks/{requestId}` (wdrożone) | usunięcie sesji demo (wymóg prywatności) | MVP |
| `GET /health`, `GET /livez` | stan backendu i bazy (już działa) | jest |
| `GET /api/sources`, `GET /api/sources/catalog`, `GET /api/sources/external` (wdrożone, `src/backend/sources.go`) | lista źródeł korpusu do audytu, katalog z zasadami kwalifikacji i źródła zewnętrzne: odpowiedzi `rag/` przekazane bez zmian (rag nie ma publicznego adresu). Linki w stopce strony | MVP (wymóg „lista źródeł dostępna do audytu”) |
| `POST /api/channels/demo` (wdrożone, `src/backend/demo_channel.go`) | drugi kanał: adapter demonstracyjny. Przyjmuje `{"text": "..."}`, odpowiada `text/plain` jak w komunikatorze, ta sama ścieżka `runCheck` co WWW. Bot Discord **niezaimplementowany** | MVP |
| `GET /api/admin/checks` **[NOWE]** | log sprawdzeń + eksport CSV/JSON | po podstawie (funkcja premiowana) |
| `GET /api/admin/cases` (wdrożone, `X-Admin-Token` = `MODERATOR_TOKEN`) | pętla moderatora: lista spraw. Sprawy tworzy automatycznie `POST /api/check` dla twierdzeń `insufficient_evidence`; **nie ma** `POST /api/admin/cases` | po podstawie (funkcja premiowana) |

Celowo **nie** proponujemy: logowania obywatela, kolejki asynchronicznej (budżet 45 s z kontraktu mieści się w jednym żądaniu), osobnego endpointu na tłumaczenia (teksty są w `src/frontend/src/lib/texts.ts`).

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

Nieznane pola → odrzucenie (`DisallowUnknownFields`). Backend maskuje e-mail, IBAN, PESEL, numer dowodu osobistego, numer paszportu i telefon (zamiennik `[ukryto]`, `src/backend/mask.go`; PESEL, dowód i paszport tylko z poprawną sumą kontrolną, kwoty i daty chronione) **przed** zapisem przebiegu, a wejście tekstowe także przed wysłaniem do `agent/`. Imion i nazwisk nie maskujemy nigdy, w szczególności osób publicznych (zasada mentorów: nie maskować niczego, bez czego zmienia się sens zapytania albo nie da się znaleźć dowodu). URL idzie do `agent/` bez maskowania (maskowana jest tylko kopia zapisana w bazie); treść pobranej strony nie jest maskowana.

### Kody HTTP (z kontraktu)

| Kod | Kiedy | `status` w ciele |
|---|---|---|
| `200` | wynik merytoryczny | `ok` |
| `200` | pytanie niejasne / poza zakresem | `needs_clarification`, `out_of_scope` |
| `200` | ciało większe niż 64 KB | `needs_clarification` |
| `400` | ciało nie jest poprawnym JSON-em albo ma nieznane pola | `technical_error` |
| `429` | przekroczony limit żądań (bez nagłówka `Retry-After`) | `technical_error` („Zbyt wiele zapytań…”) |
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
    "reasons": ["2 z 2 twierdzeń potwierdzone", "w tym źródeł urzędowych: 1"]
  },
  "badges": ["fresh_material", "official_source_present"],
  "campaignAlert": null,
  "cases": [],
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
  "summary": { "level": "low", "reasons": ["0 z 1 twierdzeń potwierdzone", "fałszywe: 1", "w tym źródeł urzędowych: 1"] },
  "badges": ["fresh_material", "official_source_present"],
  "cases": [],
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

`campaignAlert` **nigdy nie wpływa** na `verdict`, `summary` ani `evidenceStrength` (zakaz z briefu, scenariusz I). Front pokazuje go obok, jako kontekst, z tekstem dokładnie z `message`.

To samo dotyczy `materialMatch` (scenariusz I, wariant „URL podobny do znanego incydentu”): rag porównuje zgłoszony adres po normalizacji z adresami dokumentów korpusu i z adresami materiałów zapisanych przy sprawach katalogu kampanii (`links`), a tytuł z datą publikacji (±1 dzień, pokrycie słów ≥ 0,6) z dokumentami korpusu. Podobny temat albo sama domena (np. `pap.pl`) nie dają dopasowania; wtedy odpowiedź ma ograniczenie „Nie znaleźliśmy tej strony w naszych źródłach ani w katalogu znanych kampanii (…). Sama domena o niczym nie przesądza.” Kanał demo wypisuje blok „Znamy ten materiał” z podstawą przed twierdzeniami.

### Przykład C — sprzeczne źródła (panel „Sprzeczne źródła”)

Dwa warianty (`CONTRACT.md` §4, scenariusz C mentora):

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

Przy samych wstrzymaniach `summary` = `{ "level": "unknown", "reasons": ["0 z 1 twierdzeń potwierdzone", "bez oceny z powodu braku dowodów lub możliwości sprawdzenia: 1"] }`, a odpowiedź ma `"cases": [{ "claimId": "c1", "caseId": "…", "reports": 1, "status": "logged" }]` (pętla moderatora, §4). Front pokazuje wtedy ikonę „?” i etykietę „Nie udało się ocenić”, nigdy „50% prawdy”.

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

`429` ma to samo ciało z komunikatem o limicie („Zbyt wiele zapytań. Spróbuj ponownie za chwilę.”); backend **nie** wysyła nagłówka `Retry-After`.

## 4. Pozostałe endpointy

### `GET /api/checks/{requestId}` [NOWE]

**Niezaimplementowane.**

Zwraca zapisany `CheckResult` (ten sam kształt co `POST /api/check`, z zamaskowanym `document.text`). `404`, gdy przebieg nie istnieje albo został usunięty:

```json
{ "error": { "code": "not_found", "message": "Nie znaleziono tego sprawdzenia. Mogło zostać usunięte." } }
```

Pozwala na adres strony wyniku `/wynik/{requestId}` we froncie i na link z odpowiedzi na Discordzie.

### `DELETE /api/checks/{requestId}` (wdrożone)

`204 No Content` po usunięciu wiersza z `check_runs`. `404` (brak przebiegu) i `400` (niepoprawny UUID) zwracają `CheckResult` ze `status: technical_error` i `message`. Sprawy moderatora (`moderation_cases`) zostają do końca retencji. Bez logowania: kto zna `requestId` (UUID), ten może usunąć (wystarczy na demo, opisać w ryzykach).

### `GET /health`

Już działa: `200 {"status":"ok","database":"ok"}` albo `503 {"status":"degraded","database":"unavailable"}`. Propozycja: dodać `"rag": "ok" | "unavailable"` i `"model": "ok" | "missing_key"`.

### `GET /api/sources` [NOWE]

**Niezaimplementowane w backendzie.** Dziś lista źródeł do audytu to `rag/ GET /sources`. Propozycja: proxy do `rag/ GET /sources`, bez zmian kształtu (tylko odczyt, bez tokena):

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

**Stan: bot niezaimplementowany.** Warunek briefu (kanał + adapter demonstracyjny) spełnia `POST /api/channels/demo` (`src/backend/demo_channel.go`, `channel.go`): ciało `{"text": "..."}`, odpowiedź `text/plain` w formacie wiadomości z komunikatora (twierdzenie, werdykt, siła podstawy, uzasadnienie, źródła, ograniczenia), ta sama ścieżka `runCheck` co WWW (ten sam limit żądań, maskowanie, zapis przebiegu). Niepoprawna wiadomość → `400` z tekstem. Poniżej pierwotny plan bota.

Drugi kanał to **bot na Discordzie** (połączenie wychodzące przez Gateway), nie webhook i nie Interactions Endpoint. Decyzja zespołu, odpowiedzialny Paweł. Konsekwencje:

> **Stan implementacji (22.11, PR `feat/discord-bot`):** kanał zrealizowany jako **slash command `/factcheck`** przez bibliotekę `discordgo` (Gateway). To zmiana wcześniejszej decyzji „tylko stdlib + czytanie wiadomości w kanale/DM” — stdlib Go nie ma klienta WebSocket, a slash command jest wygodniejszy dla jury i nie wymaga Message Content Intent. Kod: `src/backend/discord.go`; bot woła wspólną ścieżkę `runCheck` (maska → `agent.Verify` → zapis → log), więc wynik jest identyczny jak na WWW.

- **Nie ma endpointu HTTP** dla kanału i nie trzeba publicznego adresu ani tunelu. Bot działa w procesie `backend/` i woła `agent.Verify` bezpośrednio (`ChannelAdapter` z `CONTRACT.md`).
- Token bota w `.env` (`DISCORD_BOT_TOKEN`), nigdy w repo. Bot musi być zaproszony na serwer demo.
- Proponowany sposób użycia: wiadomość w wydzielonym kanale (np. `#prawdowid`) albo wzmianka bota. Odczyt treści wiadomości wymaga włączenia w Discord Developer Portal opcji **Message Content Intent**. Alternatywa bez tej opcji: komenda `/sprawdz`, ale wtedy trzeba w ciągu 3 s potwierdzić odebranie (odpowiedź „deferred”) i dopiero potem wysłać wynik.
- Odpowiedź w jednej wiadomości do 2000 znaków (limit Discorda). Dłuższe wyniki skracamy i dajemy link do pełnego widoku. Podczas sprawdzania bot pokazuje „pisze…”.
- Z kanału wolno zmienić tylko pole `Channel` i format odpowiedzi. Ten sam `Input` daje ten sam wynik co WWW (scenariusz G).
- **Decyzje Pawła (21.11):** (1) bot czyta wiadomości **w kanale lub w wiadomości prywatnej (DM)**, nie przez `/sprawdz`; (2) **tylko stdlib Go**, to ma być MVP; (3) ~~`agent.Verify` jeszcze nie istnieje, więc kanał powstaje na mocku~~ — od PR #46 istnieje (`agent.NewFromEnv(logger)` i `verifier.Verify(ctx, req)`, zob. `agent/README.md`), mock niepotrzebny.
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
- `GET /api/admin/cases` (wdrożone, `src/backend/cases.go`, nagłówek `X-Admin-Token` = `MODERATOR_TOKEN`; bez skonfigurowanego tokena `403`) → `{ "cases": [{ "caseId", "claim", "reports", "campaign", "status", "createdAt", "updatedAt", "forwardedAt" }] }`. Sprawy tworzy automatycznie `POST /api/check` dla każdego twierdzenia `insufficient_evidence` (parafrazy grupuje `rag/ POST /reports/match`); nie ma `POST /api/admin/cases`. `status`: `logged` → `recommended` (co najmniej `MODERATOR_REPEAT_THRESHOLD` zgłoszeń, domyślnie 3, albo dopasowanie do katalogu kampanii) → `forwarded` (tylko gdy webhook `MODERATOR_WEBHOOK_URL` odpowiedział 2xx; bez webhooka sprawa zostaje `recommended`). To rozróżnia rekomendację przekazania od faktycznego przekazania (wymóg briefu). Odpowiedź `POST /api/check` ma pole `cases` z powiadomieniem dla obywatela (zob. typy w §5).

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
  cases: CaseNotice[];                // wdrożone: pusta lista, gdy żadne twierdzenie nie trafiło do pętli moderatora
  claims: Claim[];
  limitations: string[];
  meta: Meta;
}

interface CaseNotice {                // wdrożone, src/backend/cases.go
  claimId: string;
  caseId: string;
  reports: number;
  status: "logged" | "recommended" | "forwarded";
}

interface CheckedDocument {           // [NOWE]
  title: string | null;               // null dla zwykłego tekstu bez nagłówka
  text: string;                       // zamaskowany tekst, do którego odnoszą się claims[].span
  url: string | null;
  publisher: string | null;
  fetchedAt: string | null;
}

interface Summary {                   // liczy backend (src/backend/summary.go), reguły w §8; bez pola score
  level: "high" | "mixed" | "low" | "unknown";
  reasons: string[];                  // jawne przesłanki po polsku, np. "2 z 3 twierdzeń potwierdzone"
}

type Badge =                          // [NOWE] etykiety po polsku w texts.ts; wyliczane z przesłanek, nie przez model
  | "fresh_material" | "archival_material"
  | "official_source_present" | "official_source_absent";
// Odłożone (UI v3 ich nie pokazuje): "input_source_in_catalog" | "input_source_outside_catalog" dla inputType: url.

interface Claim {
  id: string;
  text: string;
  span: { start: number; end: number } | null; // wdrożone w agent/span.go: pozycje w document.text, w znakach Unicode (code points), end wyłączny
  verdict: Verdict;
  justification: string;
  evidenceStrength: "strong" | "moderate" | "weak" | "none";
  strengthReasons: string[];
  sources: Source[];
  warnings: { type: "source_status" | "incident_match" | "archival_material" | "other"; message: string }[];
  conflict: { summary: string } | null; // [NOWE] nie zwraca go ani agent/, ani backend (pola nie ma w JSON); front wnioskuje rozbieżność z ról źródeł
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

Stan po Figmie v3 (`Untitled (1).zip`, 21.11, 20:06). **Rozwiązane względem v2:** pełne ekrany mają ikonę statusu w pełnym kole zamiast pierścienia z procentem (więc `summary.score` wypada z propozycji); zielony opis nie mówi już o „większości źródeł” (popularność); chipy mają cztery jasne stany (świeży / archiwalny, oficjalna informacja / brak); chip reputacji zniknął. **Do decyzji z osobą od designu:**

1. **„Tekst prawdopodobnie jest dezinformacją”** (czerwony) — werdykt z briefu to „fałszywe”; „dezinformacja” zakłada intencję, której system nie bada. Propozycja: „Tekst prawdopodobnie fałszywy”, opis „Źródła przeczą sprawdzonym twierdzeniom”. Fragment opisu „bądź jeszcze nie mieć oficjalnego źródła potwierdzającego” usunąć: brak źródła to stan `unknown` (żółty), nie fałsz.
2. **Żółty box** — opis miesza „może nie istnieć wystarczająco zweryfikowanych informacji” (`level: unknown`) z „częściowo prawdziwe oraz fałszywe informacje” (`level: mixed`). To dwa stany i potrzebują dwóch etykiet: `mixed` → „Część twierdzeń prawdziwa, część nie” z ikoną ⚠; `unknown` → „Nie udało się ocenić” z ikoną „?” i opisem „Nie znaleźliśmy wystarczających źródeł. To nie znaczy, że informacja jest fałszywa”.
3. **Czarny box kampanii** — nadal stwierdza, że tekst „zawiera nieprawdziwe informacje powiązane z… kampaniami”. Dopasowanie do katalogu to kontekst, nie werdykt (brief, scenariusz I). Treść ma być dokładnie `campaignAlert.message` („Treść jest podobna do znanych przypadków dezinformacji. To informacja dodatkowa, nie ocena tego tekstu.”), a „Więcej informacji” prowadzi do `matches[].url`.
4. **Panel „Fakt”** (Sidebar, bez zmian od v1) — „Źródła:” to same domeny (`google.com`), a box ma jeszcze „81% Pewności prawdy”. Potrzebne: tytuł, wydawca, data, link i cytat (`quote`) każdego źródła, siła podstawy (`evidenceStrength` + `strengthReasons`) i ograniczenia (`limitations`), które `AGENTS.md` każe pokazywać zawsze. Procent zastąpić tą samą ikoną z etykietą co na pełnym ekranie.
5. **Panel „Sprzeczne źródła”** — karty mają tytuł, wydawcę, datę i link; brakuje cytatu i roli (`supports` / `refutes`), żeby obywatel widział, która strona co mówi, oraz `missing` („czego nie ustalono”).
6. **Brakujące ekrany** — stan ładowania (do 45 s, z informacją, co się dzieje), `technical_error` (503), `needs_clarification`, `out_of_scope`, wynik bez dowodów (scenariusz D) i odpowiedź częściowa (A13). Brief: awaria i niejasne pytanie muszą wyglądać **inaczej** niż werdykt (bez koloru werdyktu i bez boksu zbiorczego).
7. **Landing** — „Wyniki wygenerowane przez Sztuczną Inteligencję” zamienić na „Odpowiedź opiera się na źródłach z naszego katalogu. Sprawdź je sam”; zdanie „Zawsze weryfikuj wszystkie informacje” zostaje. Sekcja „Nagłówek następnej części tekstu” to dobre miejsce na „Jak to działa” i link do listy źródeł (`GET /api/sources`).
8. **Zielony opis** „można zweryfikować poprzez oficjalne źródła” — `high` daje też ocena weryfikatora faktów albo dwa niezależne źródła wtórne (`agent/rules.go`). Propozycja: „potwierdzają to wiarygodne źródła”; które dokładnie, mówią chipy i `summary.reasons`.

### 6a. Dostępność (priorytet zespołu)

Decyzja z 21.11: dostępność jest priorytetem. Cel: WCAG 2.1 AA. Co z tego wynika dla API i frontu:

- **Każdy stan ma tekst, nie tylko kolor i ikonę.** `verdict`, `summary.level`, `badges`, `warnings[].type` to enumy; etykiety po polsku w jednym pliku tekstów frontu (`texts.ts`), z nich też `aria-label` ikon. Backend wysyła do wyświetlenia tylko `message`, `justification`, `missing`, `limitations`, `summary.reasons`, `strengthReasons` i `campaignAlert.message`, zawsze po polsku, prostym językiem, bez pojęć technicznych.
- **`message` jest niepuste dla każdego statusu innego niż `ok`** (czytnik ekranu dostaje komunikat zamiast pustej strony). `eval/` to sprawdza.
- **Podświetlenia w tekście nie są jedyną drogą do werdyktu:** pod tekstem lista twierdzeń z werdyktami, dostępna klawiaturą, działa przy `span: null` i przy 200% rozmiaru tekstu. Panel boczny otwierany przyciskiem (`aria-expanded`), nie samym hoverem.
- **Kontrast:** tekst na pastelowych boksach jest czarny, to dobrze. Do poprawy: niebieski link „Więcej informacji” na czarnym boksie (za niski kontrast, zrobić biały z podkreśleniem) i jasnoszara linia „Wydawca, 01.01.2020” na kartach źródeł (`AGENTS.md`: bez szarego tekstu dla ważnych treści).
- **Panel ustawień dostępności** (zrzut wzorcowy w v3, styl serwisów gov.pl): kontrast (domyślny / wysoki jasny / wysoki ciemny), rozmiar tekstu (100 / 125 / 150 / 200%), „ogranicz animacje”, „przywróć domyślne”. Front: `localStorage`, wartości startowe z `prefers-contrast` i `prefers-reduced-motion`. W trybach wysokiego kontrastu werdykty muszą pozostać rozróżnialne bez koloru (ikona + etykieta). Bez żadnego pola w API.
- **Drugi kanał (adapter demonstracyjny):** te same etykiety słowne co w WWW (werdykt nigdy samym emoji), zob. `ToReply` w `src/backend/demo_channel.go`.

## 7. Pytania otwarte

- ~~`400` dla złego JSON-a: jaki `status` w ciele?~~ Rozstrzygnięte w kodzie: `400` + `technical_error` dla złego JSON-a; pusty lub za długi `input` → `200` + `needs_clarification`.
- ~~Discord: Interactions Endpoint czy bot przez Gateway?~~ Bot nie powstał. Drugi kanał to adapter demonstracyjny `POST /api/channels/demo` (§4).
- `document.text` w bazie: `check_runs.result` trzyma dokument przycięty do 5000 znaków i zamaskowany (także tytuł i dla URL), retencja 30 dni (`CHECK_RETENTION_DAYS`). Odpowiedź dla użytkownika nie jest przycinana ani zmieniana (`maskResultForStorage` w `src/backend/check.go`).
- CORS: front na `localhost:5173`, backend na `3001`. Proponujemy proxy w `vite.config.ts` (`/api` → `3001`) zamiast nagłówków CORS w Go. Na Railway front i backend mogą być pod jednym adresem (backend serwuje `dist/`), wtedy CORS znika.
- ~~Limit żądań: proponujemy 10 żądań na minutę na IP.~~ Wdrożone: 20 żądań na minutę na IP (`CHECK_RATE_LIMIT_PER_MINUTE`), wspólne dla WWW i adaptera demonstracyjnego; IP z `X-Forwarded-For` według `TRUSTED_PROXY_HOPS`.
- `claims[].span` zwraca `agent/` (PR #67). `claims[].conflict` nadal otwarte: pola nie ma w JSON, front wnioskuje rozbieżność z ról źródeł.

## 8. Plan implementacji backendu (`src/backend/`)

**Stan (po #51–#75):** kroki 1–4, 5 (tylko `DELETE`), 6 i 9 są wdrożone w `check.go`, `mask.go`, `summary.go`, `store.go`, `ratelimit.go`. Tabela nazywa się `check_runs` (nie `checks`). Zmienne środowiska: `CHECK_RATE_LIMIT_PER_MINUTE=20`, `CHECK_RETENTION_DAYS=30`, `BADGE_ARCHIVAL_DAYS=365`, `TRUSTED_PROXY_HOPS=1` (zamiast `RATE_LIMIT_PER_MINUTE`, `CHECK_RETENTION_HOURS`, `TRUST_PROXY` z planu). Niezaimplementowane: `GET /api/checks/{id}` (krok 5), `GET /api/sources` (krok 7), rozszerzony `/health` (krok 8). Krok 10 (Discord) zastąpił adapter demonstracyjny `POST /api/channels/demo`. Dodatkowo poza planem: pętla moderatora (`cases.go`) i chip katalogu (`catalog.go`). Poniżej pierwotny plan.

Kolejność: pionowy przekrój najpierw. Każdy krok kończy się działającym `curl` i commitem.

1. **`POST /api/check`** (`handlers.go`): dekodowanie JSON z `DisallowUnknownFields` i `http.MaxBytesReader` (np. 64 KB); `validateCheckRequest` (`input` 1–5000 znaków po `TrimSpace`, `inputType` ∈ {`text`, `url`}; pusty albo za długi → `200` + `needs_clarification`); maskowanie e-mail / telefon / PESEL (`privacy.go`, regexy → `[e-mail]`, `[telefon]`, `[PESEL]`); `requestId` z `crypto/rand` (16 bajtów sformatowane jak UUID v4, bez biblioteki); `context.WithTimeout(ctx, 45 s)`; `verifier.Verify(ctx, agent.VerifyRequest{RequestID, Channel: "web", Input: zamaskowany, InputType})`.
2. **Uzupełnienia po `Verify`** (`enrich.go`, czyste funkcje z testami tabelarycznymi): dla `inputType: text` i `status: ok` `document = { title: null, text: <zamaskowany input> }` (dla URL `document` daje `agent/`); `summary` i `badges` według reguł niżej; `span: null`, `conflict: null`, dopóki nie da ich `agent/`.
3. **Kod HTTP ze statusu:** `ok`, `needs_clarification`, `out_of_scope` → `200`; `technical_error` → `503`. Ciało zawsze pełny `CheckResult`.
4. **Zapis przebiegu** (`store.go`, pgx): tabela `checks` (DDL niżej), `CREATE TABLE IF NOT EXISTS` przy starcie. Błąd zapisu idzie do logu, odpowiedź do użytkownika i tak wychodzi (`AGENTS.md`: audyt nie wywala operacji).
5. **`GET /api/checks/{requestId}`** i **`DELETE /api/checks/{requestId}`**: odczyt / usunięcie wiersza; `404` z `{ "error": { "code": "not_found", "message": "…" } }`.
6. **Limit żądań** (`ratelimit.go`): mapa IP → licznik w oknie minutowym, w pamięci; `RATE_LIMIT_PER_MINUTE` (domyślnie 10); `429` + `Retry-After` i ciało `technical_error` z komunikatem o limicie. IP z `X-Forwarded-For` tylko przy `TRUST_PROXY=true` (Railway).
7. **`GET /api/sources`**: proxy `GET {RAG_URL}/sources` (timeout 8 s); awaria → `503` z `{ "error": { "code": "rag_unavailable", "message": "…" } }`.
8. **`GET /health`**: dodać `"rag"` (`GET {RAG_URL}/health`) i `"model"` (`LLM_BASE_URL` ustawiony).
9. **Logi** (`log/slog`, jeden wpis na sprawdzenie). Wdrożone: wpis `check finished` ma `requestId`, `status`, `latencyMs`, `abstained`, `retrievedPassages`, `searchErrors`, `injectionAttempts`, `timedOut`; model i koszt są w `check_runs` (kolumna `model`, `result.meta.estimatedCostUsd`). To pokrywa obserwowalność z briefu.
10. **Discord** na końcu (§4), po działającym WWW end-to-end.

**Reguły `summary.level`** (deterministyczne, `summary.go`, bez pola `score` i bez ważenia). `substantive` = twierdzenia z werdyktem `confirmed`, `false` lub `misleading`:

| Warunek | `level` |
|---|---|
| `substantive` puste (same `insufficient_evidence` / `not_verifiable`) | `unknown` |
| wszystkie `substantive` = `confirmed` | `high` |
| wszystkie `substantive` = `false` | `low` |
| inaczej (mieszanka albo jakiekolwiek `misleading`) | `mixed` |

`reasons` po polsku z liczb (tak, jak produkuje je kod): „2 z 2 twierdzeń potwierdzone”, „fałszywe: 1”, „wprowadzające w błąd: 1”, „bez oceny z powodu braku dowodów lub możliwości sprawdzenia: 1”, „w tym źródeł urzędowych: 1” (wydawcy liczeni bez powtórzeń). Status inny niż `ok` → `summary: null`.

**Reguły `badges`** (tylko przy `status: ok`, z sumy `claims[].sources`): jest `sourceType: official` → `official_source_present`, inaczej `official_source_absent`. Świeżość liczona per twierdzenie: gdy najnowsze datowane źródło **któregokolwiek** twierdzenia jest starsze niż `BADGE_ARCHIVAL_DAYS` (domyślnie 365) → `archival_material`, inaczej `fresh_material`; brak dat → bez chipa świeżości. Dla `inputType: url` dochodzi `input_source_in_catalog` / `input_source_outside_catalog` z `rag/ GET /sources/catalog` (brak chipa, gdy katalog niedostępny). Nic z opinii modelu.

**DDL tabeli `checks`:**

```sql
CREATE TABLE IF NOT EXISTS checks (
  id UUID PRIMARY KEY,
  channel TEXT NOT NULL,
  input_type TEXT NOT NULL,
  input_masked TEXT NOT NULL,
  status TEXT NOT NULL,
  result JSONB NOT NULL,
  latency_ms INTEGER NOT NULL,
  model TEXT,
  estimated_cost_usd DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`result` to pełny `CheckResult` po maskowaniu (dla URL `document.text` przycięte do 5000 znaków). Retencja: `DELETE FROM checks WHERE created_at < now() - interval '24 hours'` przy starcie i co godzinę (`CHECK_RETENTION_HOURS`, domyślnie 24).

**Nowe zmienne w `.env.example`:** `RATE_LIMIT_PER_MINUTE=10`, `BADGE_ARCHIVAL_DAYS=365`, `CHECK_RETENTION_HOURS=24`, `TRUST_PROXY=false`. `RAG_URL` i `LLM_*` już są, czyta je `agent.NewFromEnv`.

**Test tekstowy na koniec kroku 1–4:**

```
curl -s -X POST localhost:3001/api/check -H "Content-Type: application/json" -d "{\"input\":\"Policja zatrzymała 59 osób.\",\"inputType\":\"text\"}"
```
