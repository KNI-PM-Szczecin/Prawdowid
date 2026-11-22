# Prompty agenta

Pliki w tym folderze to konfiguracja modelu, nie kod (`AGENTS.md`: konfiguracja w plikach danych). Go wczytuje je przez `embed` i podstawia `{{...}}`. Zmiana promptu nie wymaga zmiany kodu, ale wymaga przebiegu `eval/`.

| Plik | Rola | Wiadomość |
|---|---|---|
| `extract.system.md` | wyodrębnia twierdzenia z wejścia i oznacza, które są faktem, a które opinią | system |
| `extract.user.md` | wejście użytkownika w bloku `<tekst>` | user |
| `judge.system.md` | ocenia jedno twierdzenie na podstawie źródeł | system |
| `judge.user.md` | twierdzenie, dzisiejsza data, data publikacji sprawdzanego materiału (albo „nieznana”) i `contextXml` z `rag/` | user |

## Dlaczego tak

- **Prompty piszemy pod najmniejszy obsługiwany model** (domyślnie Qwen3 0.6B przez FastFlowLM; ten sam prompt działa z hostowanym `gpt-6-luna`). Prompty są krótkie, numerowane, z jednym wzorem JSON. Nie ma w nich logiki, którą da się policzyć w Go. Model robi dwie rzeczy, w których jest niezastąpiony: zamienia tekst na twierdzenia i wybiera cytat z uzasadnieniem. Wszystko inne jest deterministyczne (niżej).
- **Źródła i tekst użytkownika nigdy nie trafiają do promptu systemowego** (`AGENTS.md` §4, `CONTRACT.md` §3: `contextXml` to dane). Idą do wiadomości użytkownika w blokach `<dostepne_zrodla>` i `<tekst>`; `rag/` escapuje treść, więc źródło nie może zamknąć bloku ani podrobić atrybutów.
- **Polskie etykiety w JSON modelu** (`potwierdzone`, `falszywe`, …) są celowe: mały model trzyma się języka promptu. Go mapuje je na werdykty z kontraktu (`confirmed`, `false`, `misleading`, `insufficient_evidence`, `not_verifiable`).
- **Wynik nie może zależeć od wpisania odpowiedzi testowej** (brief): w promptach nie ma przypadków z `eval/` ani scenariuszy mentora, tylko jeden fikcyjny wzór formatu.

## Parametry wywołania (FastFlowLM, `/v1/chat/completions`)

Serwery lokalne (FastFlowLM, Ollama): `temperature: 0`, `think: false` (Qwen3 ma przełączalne myślenie; wyłączone, bo wydłuża odpowiedź i psuje JSON), `max_tokens: 400` dla obu promptów. Hostowany OpenAI (`api.openai.com`): `max_completion_tokens: 800`, `reasoning_effort` z `LLM_REASONING_EFFORT` (domyślnie `none`), `temperature: 0` tylko przy `none`. Jedna próba ponowienia przy niepoprawnym JSON. Budżet z kontraktu: 45 s na całe `Verify`, 30 s na `rag/`, 15 s na wywołanie modelu.

## Co sprawdza Go po odpowiedzi modelu (twarde reguły, `CONTRACT.md` §4)

Model proponuje, Go rozstrzyga. Odpowiedź modelu jest odrzucana albo obniżana, gdy:

1. **Cytat nie występuje dosłownie** w fragmencie o podanym `id` (porównanie po normalizacji białych znaków, wielkości liter, cudzysłowów, myślników i wielokropka; cytat krótszy niż 10 znaków jest odrzucany). Cytat jest usuwany; bez cytatu werdykt `confirmed`/`false` spada do `insufficient_evidence`. Dwa cytaty z jednego dokumentu to jedno źródło; rola rozstrzygająca wygrywa z kontekstem.
2. **`id` nie istnieje** w `results` z `rag/`. Cytat usuwany.
3. **Za słaba podstawa**: `confirmed` lub `false` wymaga cytatu i albo jednego źródła `official`, albo dwóch niezależnych `secondary` (różni wydawcy), albo oceny `factcheck`. Inaczej `insufficient_evidence` z `missing`.
4. **Ocena weryfikatora** (`factcheck`): Go mapuje ocenę z fragmentu (np. „Fałsz” → `false`, „Prawda” → `confirmed`, „Częściowa prawda”, „Półprawda”, „Manipulacja”, „Brak kontekstu”, „Nieaktualne” → `misleading`, „Nieweryfikowalne” → `not_verifiable`) i sprawdza zgodność z werdyktem modelu. Zgodna ocena ustawia rolę cytatu i daje mocną podstawę. Niezgodna nie nadpisuje werdyktu: weryfikator mógł oceniać inne, podobne twierdzenie, więc wynik to `insufficient_evidence` z notą w `limitations`.
4a. **Inne liczby w cytacie**: cytat potwierdzający (i każdy cytowany `factcheck`, porównywany po sprawdzonym przez weryfikatora twierdzeniu) musi zawierać każdą liczbę zapisaną cyframi w twierdzeniu, jeśli sam podaje jakieś liczby cyframi. Inaczej rola spada do `context`, a werdykt bez innej podstawy do `insufficient_evidence` z notą w `limitations` (źródło o 458 posłach nie potwierdza twierdzenia o 460). Liczebniki porządkowe („65.”) i numery przepisów („art. 98”) się nie liczą; liczby słowne („czteroletnie”) nie blokują reguły. Wyjątek: cytat bez własnych liczb przechodzi, gdy brakujące liczby są w tym samym fragmencie źródła.
4b. **Twierdzenie o samym sprawdzeniu** („X sprawdzał, czy …”, nazwa weryfikatora z cytowanego źródła `factcheck` albo słowo „weryfikator” plus czasownik sprawdzania): ocena weryfikatora nie jest porównywana z werdyktem, bo twierdzenie dotyczy istnienia sprawdzenia. `confirmed` z cytowanym `factcheck` ustawia mu rolę `supports`.
4c. **`misleading` wymaga cytatu rozstrzygającego** (`supports` albo `refutes`) albo zgodnej oceny weryfikatora. Sam kontekst (np. źródło o innym mieście lub okresie) daje `insufficient_evidence`; `false` wymaga cytatu `refutes`.
4d. **Wstrzymanie bez ważnych cytatów, gdy `rag/` zwrócił fragmenty**: do `sources` trafiają maks. 2 fragmenty z najwyższym `score` i pełnymi metadanymi (tytuł, wydawca, data publikacji, link), bez flagi injection, z rolą `context` i cytatem będącym dosłownym początkiem fragmentu (do 280 znaków, cięcie po zdaniu albo słowie). Siła podstawy zostaje `weak`. Nie dotyczy `confirmed`, `false`, `misleading`.
5. **`campaignAlert`** z `rag/` nigdy nie zmienia werdyktu: trafia do `warnings[].type = incident_match` i do `campaignAlert` odpowiedzi.
6. **`suspected_injection`** na fragmencie albo `podejrzane: true` od modelu → `meta.injectionAttempts + 1`, wpis w logu; fragment zostaje danymi.
7. **Brak wyników z `rag/`** → model dostaje pustą listę źródeł i może tylko uznać treść za opinię lub przewidywanie (`not_verifiable`). Zasada 2 w `judge.system.md` wprost na to pozwala, bo samo rozpoznanie opinii nie wymaga źródeł. Przewidywanie to domysł o przyszłości; zapowiedziana zmiana, decyzja, przepis albo termin to fakt, więc bez źródeł daje `brak_dowodow`. Każdy werdykt inny niż `not_verifiable` staje się `insufficient_evidence`: `justification` to stały tekst „Nie znaleziono publikacji na ten temat w dostępnych źródłach.”, a `missing` to zdanie modelu z pola `brakuje` o rodzaju źródła, które by to rozstrzygnęło (np. „komunikat urzędu miasta”, do 300 znaków; gdy puste, ten sam stały tekst), zawsze z dopiskiem „Brak wyniku w naszych źródłach nie oznacza, że to prawda ani że to nieprawda.”
8. **Awaria `rag/`, modelu lub brak klucza** → `technical_error`, nigdy werdykt. Awaria źródła zewnętrznego (`externalSources[].status = error`) → `limitations` („Nie mogę teraz sprawdzić ocen weryfikatorów faktów.”) i `meta.searchErrors + 1`; gdy przy tym korpus nie dał żadnego fragmentu (awaria była jedyną możliwą podstawą) → `technical_error` z komunikatem o błędzie dostępu do weryfikatorów, nigdy „nie ma takiej publikacji”.
9. **`evidenceStrength`** liczone w Go z przesłanek: typ i liczba niezależnych źródeł, wiek (`publishedAt`), zgodność ról z werdyktem. `strengthReasons` to te przesłanki po polsku.
10. **Spójność kanałów**: ten sam `input` daje ten sam wynik; `rag/` ma cache, a `temperature: 0` ogranicza losowość modelu. Przy rozjeździe wygrywają reguły powyżej, nie model.

## Przepływ `Verify`

1. Wejście: `text` albo `url`. Dla `url` agent woła `POST /fetch` w `rag/` (ten sam parser co przy zasilaniu korpusu; decyzja zespołu: pobieranie zostaje w rag), dostaje tytuł, tekst i datę publikacji strony, a potem `POST /match`. Odmowa pobrania ma kod: serwis wideo/społecznościowy → `out_of_scope`, plik → `needs_clarification` o pliku, zapora albo brak tekstu → `needs_clarification` o blokadzie, reszta → „nie udało się odczytać”. Tekst z dokładnie jednym linkiem w środku też pobiera tę stronę i sprawdza ją razem z tekstem (nieudane pobranie to tylko wpis w `limitations`); kilka linków nie jest pobieranych. (czy strona jest znanym materiałem: `materialMatch`, kontekst). Strona starsza niż rok daje każdemu twierdzeniu ostrzeżenie `archival_material` i wpis w `limitations`; brak daty publikacji to osobny wpis w `limitations`. Maskowanie danych osobowych robi backend przed `Verify`.
2. **Ekstrakcja**: wejście krótsze niż 2 słowa → `needs_clarification` bez modelu. Gdy wejście ma jedno zdanie (≤ 300 znaków, bez nowej linii, bez granicy zdania „. Wielka litera”, nie jest pytaniem), twierdzeniem jest samo wejście, bez modelu. Liczebnik porządkowy („po 65. roku”) nie dzieli zdania. Pytania idą do `extract`, który zamienia je na zdania oznajmujące i zachowuje słowa zakresu („tylko”, „wyłącznie”); pytanie „Czy …?”, z którego model nic nie wyciągnął, staje się zdaniem oznajmującym. Inaczej `extract` (tekst do 6000 znaków) → maks. 3 najważniejsze twierdzenia (najpierw fakty: główna teza i te z liczbami, datami, nazwami; opinie na końcu), każde z `rodzaj` (`fakt` albo `opinia`) i `fragment` (dosłowny kawałek tekstu); gdy model zgłosi `pominiete > 0`, do `limitations` trafia „Sprawdzono K najważniejsze twierdzenia z około N w tekście.” (K = liczba wyodrębnionych, N = K + `pominiete`). Niepoprawny JSON z ekstrakcji → cały tekst jako jedno twierdzenie. Pusta lista → `needs_clarification`.
3. Dla każdego faktu: `POST /search` w `rag/` (`topK` 5) → reguła 7 albo `judge` → walidacja 1–6 → `Claim`. Opinia (`rodzaj: opinia`) nie jest wyszukiwana ani oceniana przez `judge`: dostaje `not_verifiable` ze stałym uzasadnieniem i bez źródeł (CONTRACT.md §4). Każdy `Claim` dostaje `span` (pozycja `fragment`, a w zapasie zdania twierdzenia, w `document.text`; parafraza → `null`), dzięki czemu front podświetla twierdzenie w tekście.
4. Złożenie `CheckResult`: `limitations`, `meta` (model, czas, `corpusVersion`, `injectionAttempts`, `abstained`).

## Znane słabości (do pomiaru w `eval/`)

- 0.6B może mieszać role cytatów („potwierdza” vs „obala”) i wybierać luźno związany fragment. Reguły 1–4 zamieniają to w `insufficient_evidence`, nie w fałszywy werdykt, ale obniżą macro-F1. Jeśli pomiar pokaże, że ekstrakcja albo wybór cytatu zawodzą, pierwszym ruchem jest większy model w tym samym promptcie, nie dłuższy prompt.
- Ekstrakcja z długich tekstów (artykuł z URL) może pomijać kluczowe tezy. `max_claims` = 3 to limit czasu (3 wyszukiwania + 3 oceny w 45 s), nie jakości.
