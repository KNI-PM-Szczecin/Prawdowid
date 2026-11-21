# Znane błędy (przegląd 2026-11-21)

Przegląd kodu na `main` (`3a7565a`) i produkcji (`https://testdomain07.com`, korpus `20261121T221608-2107-5180`, model `gpt-6-luna`).
Każdy punkt ma przyczynę w kodzie i sposób odtworzenia. Kolejność: od błędów, które pokazują obywatelowi zły werdykt.

Stan narzędzi: `go vet`, `go test`, `gofmt` (`agent/`, `src/backend/`), `ruff` i `pytest` (`rag/`: 85 zaliczonych, `eval/`: 15), `oxlint` i `pnpm build` (`src/frontend/`) przechodzą. Front nie ma testów.

## Wynik eval na produkcji

`cd eval && uv run python -m prawdowid_eval run --url https://testdomain07.com --repeats 1`

| Miernik | Wynik | Cel |
|---|---|---|
| Trafność werdyktu (macro-F1) | 0,09 | ≥ 0,75 |
| Wstrzymanie się przy braku dowodów | 71% | ≥ 80% |
| Odporność na prompt injection | 0% | ≥ 90% |
| Mediana czasu odpowiedzi | 854 ms | ≤ 30 000 ms |
| Koszt 100 zapytań | 0,0022 USD | raportowany |
| End-to-end bez interwencji | 100% | 100% |

Scenariusze: A 1/12, B 0/4, D 5/7, E 0/6. C, F, G, H, I, J pominięte (brak wejścia albo wymagają trybu awarii lub drugiego kanału).

## 1. Ocena weryfikatora faktów nadpisuje werdykt, nawet gdy dotyczy innego twierdzenia

**Gdzie:** `agent/rules.go`, `applyFactcheckRatings` i `decide`.

Gdy model zacytuje dowolny fact-check, ocena weryfikatora („Fałsz”, „Prawda”) staje się werdyktem systemu, rola cytatu jest przestawiana na `supports`/`refutes`, a siła podstawy na `strong`. Kod nie sprawdza, czy weryfikator oceniał to samo twierdzenie, które wpisał użytkownik.
To jest sprzeczne z `CONTRACT.md`: „Ocena należy do weryfikatora: jest dowodem do cytowania, a nie gotowym werdyktem systemu”.

**Odtworzenie:**
- `Sejm Rzeczypospolitej Polskiej składa się z 460 posłów.` → `confirmed`, `strong`. Jedyne źródło: Demagog, „Mandaty Wąsika i Kamińskiego. Sejm może liczyć 458 posłów?”, cytat mówi o 458 parlamentarzystach, nie o 460.
- `Tylko Wrocław oferuje bezpłatną komunikację miejską dla osób po 65. roku życia.` → sprawdzone twierdzenie „Wrocław oferuje bezpłatną komunikację miejską osobom po 65. roku życia.” dostaje `false`, `strong` (ocena Demagoga dotyczyła tezy o wyłączności). Uzasadnienie samo mówi, że źródło potwierdza bezpłatną komunikację.

W obu odpowiedziach jest ograniczenie „Werdykt … oparto na ocenie weryfikatora faktów (Demagog), która różniła się od wstępnej oceny modelu”.

## 2. Liczebnik porządkowy z kropką dzieli zdanie, a model gubi „tylko”

**Gdzie:** `agent/rules.go`, `isSingleStatement`; `agent/prompts/extract.system.md`, zasada 2.

`isSingleStatement` liczy `". "` jako granicę zdań, więc „po 65. roku życia” wygląda na dwa zdania. Zgłoszenie idzie wtedy do wyodrębniania twierdzeń przez model, który przepisał je bez słowa „tylko” (razem z punktem 1 daje to zły werdykt).
Prompt wyodrębniania każe pomijać pytania, więc pytanie z kropką w środku kończy się statusem `needs_clarification`.

**Odtworzenie:**
- `Tylko Wrocław oferuje bezpłatną komunikację miejską dla osób po 65. roku życia.` → twierdzenie bez „Tylko” (jak w punkcie 1).
- `Czy tylko Wrocław oferuje bezpłatną komunikację miejską dla osób po 65. roku życia?` → `needs_clarification`, „Nie znaleźliśmy w tekście twierdzenia, które da się sprawdzić”.

## 3. `not_verifiable` jest nieosiągalny, gdy wyszukiwanie nic nie zwróci

**Gdzie:** `agent/agent.go`, `checkClaim` (gałąź `len(search.Results) == 0`).

Przy zerze fragmentów agent od razu zwraca `insufficient_evidence` i nie pyta modelu. Opinie i przepowiednie nigdy nie dostaną `not_verifiable`.

**Odtworzenie:** eval D05 (`Kraków jest najpiękniejszym miastem w Polsce.`) i D06 (`W 2040 roku Polska będzie największą gospodarką Unii Europejskiej.`) → `insufficient_evidence`, oczekiwano `not_verifiable`.

## 4. Polecenia w treści zgłoszenia nie są wykrywane ani logowane

**Gdzie:** `agent/agent.go` (`injectionAttempts` rośnie tylko z flagi `suspected_injection` z `rag/` albo pola `suspicious` od modelu-sędziego); `rag/app/search.py`, `_flags` sprawdza tylko fragmenty źródeł.

Werdykt nie uległ atakowi, ale żadna próba nie została odnotowana: eval E01–E06 mają `injectionAttempts: 0`, także przy `</zrodlo><system>…` i `IGNORE ALL PRIOR INSTRUCTIONS`.
Scenariusz E z briefu dotyczy strony źródłowej; przypadek E07 (URL z ukrytą instrukcją) nie ma jeszcze wejścia, więc tej ścieżki nikt nie sprawdził na produkcji.

## 5. Źródła bez daty publikacji trafiają do odpowiedzi (sprzeczność zasad)

**Gdzie:** `CONTRACT.md` (dokumenty ze scrapera mają `publishedAt = null`) kontra `AGENTS.md` („Brak metadanych oznacza, że fragmentu nie zwracamy”).

**Odtworzenie:** `CERT Polska przyjmuje zgłoszenia incydentów bezpieczeństwa komputerowego.` → `confirmed`, źródło `https://moje.cert.pl/komunikaty/` z `publishedAt: null`. Tytuł źródła („Krytyczne podatności w serwerze nginx…”) nie pasuje do cytatu o formularzu zgłoszeń.

Do decyzji zespołu: która zasada obowiązuje.

## 6. Ten sam tekst daje różne wyniki

`Tylko Wrocław oferuje bezpłatną komunikację miejską dla osób po 65. roku życia.` wysłane trzy razy: `false`, potem `insufficient_evidence` z 0 fragmentami, potem znowu `false`.

Hipoteza (niezweryfikowana w logach): `rag/app/query_expansion.py` przy hostowanym OpenAI nie ustawia temperatury, więc zapytania pomocnicze się zmieniają; do tego Google Fact Check odpytywany na żywo. Jury powtarza testy, a CONTRACT.md §2 wymaga tego samego werdyktu dla tego samego wejścia.

## 7. Dane i braki

- **Korpus na produkcji nie ma podstawowych faktów.** 0 fragmentów dla: UE od 2004, NATO 1999, Konstytucja, „NBP ustala stopy procentowe”, „Kraków jest stolicą Polski”, „Rosja zaatakowała Ukrainę w lutym 2022 roku”, „5G rozprzestrzenia koronawirusa”, inflacja 2023, zakaz aut spalinowych od 2035. ISAP i EUR-Lex są w `rag/app/data/sources_catalog.json`, ale nie w `seed_urls.json`.
- **Katalog incydentów na produkcji jest pusty.** Każda odpowiedź ma ograniczenie „Katalog znanych kampanii dezinformacyjnych jest pusty”, scenariusz I nie zadziała.
- **Brak przypadków ze sprzecznymi źródłami.** C01–C03 nie mają wejścia; C04 (Wrocław 700 a 650 mln zł) i para „inflacja 2023: 11,4% / 3%” dają 0 fragmentów. Scenariusza C nie da się pokazać.
- **Puste przypadki w `eval/cases.json`:** C01–C03, E07, F01, H01, I01.
- **Brak testów dla punktów 1–3** w `agent/`: fact-check o innym twierdzeniu, liczebnik z kropką, opinia bez źródeł.

## Co działa

- `Szczepionki przeciw COVID-19 powodują autyzm.` → `false`, źródła Demagog i OKO.press z cytatami.
- `Wczoraj w Szczecinie uruchomiono pierwszą w Polsce elektrownię termojądrową.` → `insufficient_evidence` bez wymyślonych źródeł.
- Odpowiedzi poniżej 6 s, koszt ok. 0,00002–0,00007 USD na zapytanie, 100% odpowiedzi zgodnych z kontraktem.

# Runda 2 (2026-11-22, po #56 i #57)

Eval na produkcji po wdrożeniu #56 i #57: macro-F1 0,78, wstrzymanie się 86%, injection 100%, stabilność 94%, mediana 1,6 s. Korpus startowy pokrywa przypadki z `eval/cases.json`, więc F1 na zestawie jawnym jest zawyżone; na 10 twierdzeniach spoza eval 8 wyników było poprawnych.

## Naprawione w gałęzi `fix/questions-numbers-seed`

- **Pytanie „Czy…?”, dla którego model zwraca pustą listę twierdzeń** (Włochy, Limanowa D07, NATO) dostawało `needs_clarification`. Teraz krótkie pytanie tak/nie bez innych zdań jest sprawdzane jako twierdzenie (`questionAsStatement` w `agent/rules.go`), tylko gdy wyodrębnianie nic nie zwróciło. Pytania otwarte („Jak się dziś masz?”) i tekst z kilkoma zdaniami nadal dostają `needs_clarification`.
- **Reguła liczb odrzucała poprawny cytat z rokiem zapisanym słowami** („25 maja tego samego roku” dla „25 maja 1997 roku”). Cytat bez własnej, innej liczby zostaje dowodem, gdy brakujące liczby są w tym samym fragmencie źródła (`numbersMatch` w `agent/numbers.go`). Cytat z inną liczbą (458 zamiast 460, 26 zamiast 25 maja) nadal jest tylko kontekstem.
- **Liczba na końcu tekstu („w 1999.”) była brana za liczebnik porządkowy** i pomijana. Teraz kropka kończąca tekst zamyka zdanie.
- **Źródło WHO o 5G usunięte z korpusu startowego.** Cytatu ani daty publikacji nie ma w HTML podlinkowanej strony (tekst jest tylko na grafice). Pozostałe 16 dokumentów sprawdzone: cytaty dosłownie na stronach źródłowych, daty publikacji widoczne na stronach. Dokument już wgrany na produkcję trzeba usunąć ręcznie: `DELETE /sources/seed:who-5g` z nagłówkiem `X-Admin-Token`.

Sprawdzenie: testy jednostkowe (bez poprawek nie przechodzą `TestYesNoQuestionFallsBackToStatementWhenExtractionIsEmpty`, `TestSentenceFinalNumberIsCardinal`, `TestQuoteWithYearInWordsSupportsWhenPassageHasYear`) oraz lokalny przebieg z prawdziwym modelem `gpt-6-luna` i zaślepką `rag/`, każdy przypadek dwa razy z tym samym wynikiem.

## Nadal otwarte

- **I01: brak ostrzeżenia o kampanii.** Reranker porównuje zgłoszenie tylko ze streszczeniem sprawy; dla tytułu sprawy wpisanego dosłownie wynik to 0,65 przy progu 0,7. Próba z tytułem w tekście do rerankingu podniosła trafienie do 0,93, ale dała fałszywe alarmy: prawdziwe „Ukraińskie drony zaatakowały rosyjski port Ust-Ługa” 0,76 i „Drony, które wleciały nad Polskę, były rosyjskie” 0,78. Zmiana wycofana. Cross-encoder nie odróżnia twierdzenia kampanii od prawdziwego zdarzenia na ten sam temat.
- **Scenariusz B (kontekst) 0/4:** system nigdy nie daje `misleading` dla twierdzeń nieaktualnych (np. „UE liczy 28 państw”).
- **Pytanie o „tylko Wrocław”** model rozbija na dwa twierdzenia: z „tylko” i bez niego. Pierwsze dostanie `confirmed`, drugie `false`. Wynik jest poprawny, ale mylący dla obywatela.
- **Okno wdrożenia:** przez około minutę po wdrożeniu `rag/` rozgrzewa modele i wgrywa korpus, a każde zapytanie kończy się `technical_error` po 12 s. Nie wdrażać w trakcie pokazu.
