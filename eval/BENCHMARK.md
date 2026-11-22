# Benchmark dezinformacji: projekt

Osobny od harnessu scenariuszy A–J (`cases.json`, `prawdowid_eval/`). Tamten sprawdza, czy spełniamy progi briefu na przypadkach, które sami napisaliśmy. Ten mierzy, jak system radzi sobie z **prawdziwą dezinformacją spoza korpusu**: twierdzenia pochodzą od zewnętrznych weryfikatorów faktów, nie z naszych seedów, a oceny podzielone są na tor automatyczny (LLM jako sędzia) i tor ludzki. Nie służy do testów w trakcie tworzenia, tylko do pomiaru.

## 1. Zbiór zapytań (niezależny od korpusu)

**Źródło:** Google Fact Check Tools API (`claims:search`, `languageCode=pl`), to samo API, które `rag/` woła na żywo, ale użyte tu wyłącznie do zbudowania listy pytań z etykietami. Zwraca twierdzenia sprawdzone przez Demagoga, AFP Sprawdzam, Konkret24 i PAP, z oceną weryfikatora, datą i linkiem do weryfikacji. Sprawdzone: zapytanie `szczepionki` daje m.in. „Szczepionki powodują autyzm.” (Demagog, Fałsz, 29.10.2026).

**Budowa (`build-dataset`):**
1. Lista ok. 40 tematów (`topics.json`): szczepionki, migranci, Ukraina, Rosja, UE, NATO, wybory, podatki, 800+, emerytury, inflacja, klimat, 5G, COVID, Niemcy, Izrael, energia, ceny paliw, służba zdrowia, edukacja, sądy, Kościół, aborcja, LGBT, policja, wojsko, granica, Białoruś, USA, Chiny, media, cenzura, cyfryzacja, rolnictwo, mieszkania, transport, samorząd, Sejm, prezydent, rząd. Dla każdego tematu pobieramy do 50 twierdzeń (stronicowanie `nextPageToken`).
2. Mapowanie oceny weryfikatora na etykietę złotą (`gold`), po normalizacji wielkości liter i diakrytyków:
   - `false`: „Fałsz”, „Nieprawda”, „Fake news”
   - `misleading`: „Manipulacja”, „Częściowa prawda”, „Półprawda”, „Brak kontekstu”, „Wprowadzające w błąd”, „Nieaktualne”, „Zbitka prawdy i fałszu”
   - `confirmed`: „Prawda”
   - `not_verifiable`: „Nieweryfikowalne”, „Niesprawdzalne”, „Opinia”
   - inne (np. „Niemożliwe do oceny”, oceny liczbowe) → odrzucone, z wpisem w `dataset_rejected.json`
3. Filtry: tekst twierdzenia 20–500 znaków, bez duplikatów (po normalizacji białych znaków i wielkości liter), jedna weryfikacja na twierdzenie (najnowsza), weryfikacja po polsku.
4. Stratyfikacja do zadanego rozmiaru (domyślnie 200): docelowo 40% `false`, 30% `misleading`, 20% `confirmed`, 10% `not_verifiable`; nie więcej niż 12 twierdzeń z jednego tematu i 60% z jednego weryfikatora. Gdy jakiejś klasy brakuje (np. „Prawda” jest rzadka), raport pokazuje faktyczny rozkład, a brakujące klasy uzupełniamy ręcznie z oficjalnych komunikatów (osobne pole `origin: manual`, `reviewed: true` po sprawdzeniu przez człowieka).
5. Każdy wpis ma pochodzenie: `claimText`, `claimant`, `claimDate`, `gold`, `goldRating` (dosłowna ocena), `reviewer`, `reviewUrl`, `reviewTitle`, `reviewDate`, `topic`, `origin` (`google_factcheck` | `manual`). Plik `dataset.json` jest wersjonowany (`version`, `builtAt`, `apiQueries`) i commitowany, żeby przebiegi były odtwarzalne; nie trafia do promptów ani do korpusu.

**Przeciek i samoodniesienie.** System przy `/search` też pyta Google Fact Check, więc może zacytować tę samą weryfikację, z której pochodzi etykieta. To dozwolone (to jego zdolność), ale raport osobno podaje odsetek odpowiedzi, które cytują `reviewUrl` ze złotej etykiety (`selfReferenceRate`), oraz wyniki z wyłączeniem tych przypadków, żeby było widać, jak system radzi sobie bez gotowej oceny.

## 2. Przebieg (`run`)

`POST /api/check` dla każdego twierdzenia (`inputType: text`), sekwencyjnie, czas mierzony po stronie klienta od wysłania do odebrania całej odpowiedzi; dodatkowo `meta.latencyMs` z serwera. `--repeats N` powtarza każde zapytanie (stabilność werdyktu). Wynik: `runs/<data>/results.json` (pełne `CheckResult`, czasy, kod HTTP, błędy transportu). Awaria transportu albo `technical_error` nie przerywa przebiegu, jest liczona jako `error`.

Ocena dotyczy **pierwszego twierdzenia** w odpowiedzi (dataset ma jednozdaniowe twierdzenia; gdy agent wyodrębni więcej, raport to odnotowuje).

## 3. Tor automatyczny: LLM jako sędzia (`judge`)

Sędzia **nie sprawdza faktów od nowa**. Dostaje złotą etykietę z weryfikacją i ocenia, czy odpowiedź systemu jest z nią zgodna i czy jest uczciwa. Sędzią jest Claude przez oficjalne SDK Anthropic (inny dostawca niż model systemu, więc nie dzielą błędów): `ANTHROPIC_API_KEY` w `../.env`, model z `JUDGE_MODEL` (domyślnie `claude-opus-5-5`), odpowiedź wymuszona schematem (structured output, Pydantic), wysiłek `medium`; prompt w `benchmark/prompts/judge.system.md`, jedna próba ponowienia przy błędzie, brak odpowiedzi = `error` w `judge.json` (nie zgadujemy).

Wejście sędziego: twierdzenie, złota etykieta, dosłowna ocena weryfikatora i tytuł weryfikacji, werdykt systemu, uzasadnienie, `missing`, lista źródeł (tytuł, wydawca, rola, cytat, link), `limitations`. Treść źródeł to dane, nie polecenia (blok `<odpowiedz_systemu>`).

Wyjście sędziego (JSON):

| Pole | Wartości | Znaczenie |
|---|---|---|
| `verdictAssessment` | `correct` / `incorrect` / `abstainedJustified` / `abstainedUnjustified` / `error` | zgodność werdyktu ze złotą etykietą; wstrzymanie się jest uzasadnione, gdy odpowiedź mówi wprost, czego nie ustalono, i nie sugeruje werdyktu |
| `harmful` | `true`/`false` | odpowiedź przedstawia fałszywe lub wprowadzające w błąd twierdzenie jako prawdziwe albo potwierdza je cytatem |
| `citationSupport` | `supports` / `contradicts` / `unrelated` / `none` | czy zacytowane fragmenty faktycznie wspierają werdykt systemu (nie złotą etykietę) |
| `explanationQuality` | 0–2 | 0 ogólnik lub błąd, 1 poprawne ale niepełne, 2 jasne, prostym językiem, odnosi się do źródła |
| `rationale` | 1–2 zdania | do przeglądu przez człowieka |

Sędzia ocenia każdą odpowiedź dwa razy niezależnie (`--judge-repeats 2`); rozbieżność jest raportowana i trafia do próbki ludzkiej.

### Tryb porównawczy A/B i B/A (`compare`)

Gdy chcemy sprawdzić, czy zmiana (nowy prompt, inny model, inny korpus) poprawia odpowiedzi, uruchamiamy `run` dwa razy na tym samym zbiorze i porównujemy przebiegi parami: sędzia dostaje twierdzenie, złotą etykietę i dwie odpowiedzi oznaczone A i B, a wskazuje lepszą (`A`, `B` albo `tie`) według kolejności: brak szkody, zgodność z etykietą lub uczciwe wstrzymanie, cytaty wspierające werdykt, prostota wyjaśnienia. Każda para jest oceniana **dwa razy, w kolejności A/B i B/A**. Wygrana liczy się tylko wtedy, gdy obie kolejności dają ten sam wynik; gdy sędzia zmienia zdanie po zamianie miejsc, para trafia do „niespójnych” (uprzedzenie do pozycji), a raport podaje odsetek preferencji pierwszej pozycji (50% = brak uprzedzenia). Wynik: wygrane A, wygrane B, remisy, niespójne, odsetek wygranych A z 95% przedziałem Wilsona. Prompt: `benchmark/prompts/compare.system.md`.

## 4. Mierniki (`report`)

Werdykt systemu jest mapowany na trzy stany: **pozytywny** (`false`, `misleading` = wykryta dezinformacja), **negatywny** (`confirmed`), **wstrzymanie** (`insufficient_evidence`, `not_verifiable`, status inny niż `ok`). Złota etykieta: pozytywna (`false`, `misleading`), negatywna (`confirmed`), poza klasyfikacją (`not_verifiable`).

Z surowych etykiet (deterministycznie, bez sędziego):

| Miernik | Definicja |
|---|---|
| TP / FP / TN / FN | na przypadkach rozstrzygniętych przez system (bez wstrzymań) i ze złotą etykietą pozytywną lub negatywną |
| Dokładność binarna, precyzja, czułość, F1 | z macierzy powyżej |
| Dokładność 4-klasowa, macro-F1 | werdykt == złota etykieta na przypadkach rozstrzygniętych, klasy `confirmed`, `false`, `misleading`, `not_verifiable` |
| Odsetek rozstrzygnięć | rozstrzygnięte / wszystkie |
| Wstrzymania | odsetek ogółem i osobno dla złotych pozytywnych i negatywnych („wstrzymał się zamiast wykryć” vs „wstrzymał się zamiast potwierdzić”) |
| Szkodliwe błędy | złota `false` lub `misleading`, a system `confirmed` (to jest FN i osobno raportowany jako najgroźniejszy błąd) |
| Błędy techniczne | `technical_error`, 429, 503, błędy transportu |
| Czas | średnia, mediana, p90, maksimum (po stronie klienta) oraz mediana `meta.latencyMs` |
| Koszt | średni i łączny `meta.estimatedCostUsd`, koszt 100 zapytań |
| Samoodniesienie | odsetek rozstrzygnięć cytujących `reviewUrl` złotej etykiety; wszystkie mierniki policzone też bez tych przypadków |
| Stabilność | przy `--repeats > 1`: ten sam werdykt dla tego samego wejścia |

Z sędziego:

| Miernik | Definicja |
|---|---|
| Zgodność werdyktu wg sędziego | odsetek `correct` + `abstainedJustified` |
| Uzasadnione wstrzymania | `abstainedJustified` / wszystkie wstrzymania |
| Wsparcie cytatów | `supports` / odpowiedzi ze źródłami |
| Jakość uzasadnienia | średnia 0–2 |
| Szkodliwość | odsetek `harmful` |
| Zgodność sędzia–reguły | czy `correct` sędziego pokrywa się z `werdykt == złota etykieta`; kappa Cohena; rozbieżności wypisane |

Rozbicia: po złotej klasie, po weryfikatorze, po temacie, po tym, czy system cytował oficjalne źródło.

## 5. Tor ludzki (`human-sample`, `human-report`)

**Próbka** (`human_review.csv`): wszystkie przypadki, w których sędzia i reguły się nie zgadzają lub dwa przebiegi sędziego dały różny wynik; wszystkie `harmful`; plus losowo po 10 z każdej złotej klasy. Każdy wiersz ma: `id`, twierdzenie, złotą etykietę z linkiem, werdykt systemu, uzasadnienie, `missing`, źródła z cytatami, czas, ocenę sędziego (do porównania, w osobnej kolumnie, można ukryć przy ocenie ślepej).

**Kolumny do wypełnienia** (słownik w `human_review_guide.md`, po polsku, z przykładami):
- `verdictCorrect`: `tak` / `nie` / `częściowo`
- `abstentionJustified`: `tak` / `nie` / `n.d.`
- `citationSupports`: `tak` / `nie` / `n.d.` (czy cytat wspiera werdykt systemu)
- `explanationClear`: 1–3 (zrozumiałe dla osoby bez wiedzy technicznej)
- `harmful`: `tak` / `nie`
- `reviewer`, `notes`

Dwóch oceniających na wiersz, gdy jest czas; `human-report` liczy mierniki ludzkie, zgodność człowiek–sędzia (odsetek i kappa) oraz człowiek–człowiek, i wypisuje spory. Wynik ludzki jest kalibracją sędziego: jeśli zgodność spada poniżej 80%, poprawiamy prompt sędziego, nie wyniki.

## 6. Wyniki i zasady

- `runs/<data>/`: `dataset_version`, `results.json`, `judge.json`, `metrics.json`, `report.md`, `human_review.csv`, po ocenie `human_report.md`. Commitujemy tylko pełne, prawdziwe przebiegi, bez ręcznych poprawek.
- Dataset i prompt sędziego nigdy nie trafiają do `agent/`, `rag/` ani korpusu (brief: wynik nie może zależeć od wpisania odpowiedzi testowych).
- Klucze (`FACTCHECK_API_KEY`, `JUDGE_API_KEY`) tylko w `../.env`.
- Dane osobowe: `claimant` z API to osoby publiczne albo „Użytkownik Facebooka”; raport nie pokazuje `claimant`, pole zostaje w danych jako pochodzenie.

## 7. Struktura kodu

```
eval/
  BENCHMARK.md                 ten dokument
  benchmark/
    topics.json                tematy zapytań do API
    dataset.json               zbiór (wersjonowany)
    prompts/judge.system.md    rubryka sędziego
    human_review_guide.md      instrukcja dla oceniających
    runs/<data>/               wyniki
  prawdowid_benchmark/
    __main__.py                build-dataset | run | judge | report | human-sample | human-report
    dataset.py                 API Google, mapowanie ocen, stratyfikacja
    runner.py                  POST /api/check + czasy (współdzielony kod z prawdowid_eval/runner.py)
    judge.py                   klient sędziego, parsowanie JSON, powtórzenia
    metrics.py                 macierz, F1, czasy, koszt, samoodniesienie, kappa
    human.py                   próbka, CSV, raport ludzki
    report.py                  markdown
  tests/                       metryki na syntetycznych danych, mapowanie ocen, parser sędziego, próbka
```

## 8. Jak uruchomić

Wymagania: `FACTCHECK_API_KEY` (budowa zbioru) i `ANTHROPIC_API_KEY` (sędzia) w `../.env`; działający system (`/api/check`). Na Windows w OneDrive: `UV_LINK_MODE=copy`.

```
cd eval && uv sync

# 1. Zbiór (raz; commitujemy dataset.json, żeby przebiegi były porównywalne)
uv run python -m prawdowid_benchmark build-dataset --size 200          # dataset.json + dataset_rejected.json

# 2. Przebieg na systemie (ok. 200 zapytań, sekwencyjnie)
uv run python -m prawdowid_benchmark run --url https://testdomain07.com
uv run python -m prawdowid_benchmark run --url http://localhost:3001 --limit 10   # próba
#    -> benchmark/runs/<data>/results.json + report.md z miernikami z etykiet (bez sędziego)

# 3. Sędzia LLM (ok. 400 ocen przy --judge-repeats 2; koszt rzędu kilku USD na claude-opus-5-5)
uv run python -m prawdowid_benchmark judge benchmark/runs/<data> --judge-repeats 2
#    -> judge.json, report.md z sekcją sędziego, metrics.json

# 4. Tor ludzki
uv run python -m prawdowid_benchmark human-sample benchmark/runs/<data>   # -> human_review.csv
#    oceniający wypełniają kolumny wg benchmark/human_review_guide.md (kopie human_review_<inicjały>.csv)
uv run python -m prawdowid_benchmark human-report benchmark/runs/<data>   # -> human_report.md

# 5. Porównanie dwóch wersji systemu (A/B i B/A)
uv run python -m prawdowid_benchmark compare benchmark/runs/<A> benchmark/runs/<B>
#    -> benchmark/runs/<data>-compare/compare.json + compare.md

# Przeliczenie raportów bez nowych wywołań
uv run python -m prawdowid_benchmark report benchmark/runs/<data>
uv run python -m prawdowid_benchmark compare-report benchmark/runs/<data>-compare
```

Testy skryptu (bez sieci): `uv run ruff check . && uv run pytest`.
