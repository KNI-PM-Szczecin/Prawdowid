# Prompty agenta

Pliki w tym folderze to konfiguracja modelu, nie kod (`AGENTS.md`: konfiguracja w plikach danych). Go wczytuje je przez `embed` i podstawia `{{...}}`. Zmiana promptu nie wymaga zmiany kodu, ale wymaga przebiegu `eval/`.

| Plik | Rola | Wiadomość |
|---|---|---|
| `extract.system.md` | wyodrębnia twierdzenia faktograficzne z wejścia | system |
| `extract.user.md` | wejście użytkownika w bloku `<tekst>` | user |
| `judge.system.md` | ocenia jedno twierdzenie na podstawie źródeł | system |
| `judge.user.md` | twierdzenie, data i `contextXml` z `rag/` | user |

## Dlaczego tak

- **Model jest mały (Qwen3 0.6B przez FastFlowLM).** Prompty są krótkie, numerowane, z jednym wzorem JSON. Nie ma w nich logiki, którą da się policzyć w Go. Model robi dwie rzeczy, w których jest niezastąpiony: zamienia tekst na twierdzenia i wybiera cytat z uzasadnieniem. Wszystko inne jest deterministyczne (niżej).
- **Źródła i tekst użytkownika nigdy nie trafiają do promptu systemowego** (`AGENTS.md` §4, `CONTRACT.md` §3: `contextXml` to dane). Idą do wiadomości użytkownika w blokach `<dostepne_zrodla>` i `<tekst>`; `rag/` escapuje treść, więc źródło nie może zamknąć bloku ani podrobić atrybutów.
- **Polskie etykiety w JSON modelu** (`potwierdzone`, `falszywe`, …) są celowe: mały model trzyma się języka promptu. Go mapuje je na werdykty z kontraktu (`confirmed`, `false`, `misleading`, `insufficient_evidence`, `not_verifiable`).
- **Nieaktualne ≠ fałszywe** (zasada 5 w `judge.system.md`): `misleading` tylko wtedy, gdy źródło samo mówi o zmianie stanu (wcześniejszy stan, „do [data]”, „zmieniono”, „od [data] wynosi”). Sama data publikacji lub „według stanu na” nie wystarcza; bez informacji o zmianie inna wartość to `false`. Model nie może uzupełniać historii z własnej wiedzy (zasada 2).
- **Wynik nie może zależeć od wpisania odpowiedzi testowej** (brief): w promptach nie ma przypadków z `eval/` ani scenariuszy mentora, tylko jeden fikcyjny wzór formatu.

## Parametry wywołania (FastFlowLM, `/v1/chat/completions`)

`temperature: 0`, `think: false` (Qwen3 ma przełączalne myślenie; wyłączone, bo wydłuża odpowiedź i psuje JSON), `max_tokens: 400` dla `judge`, `300` dla `extract`. Jedna próba ponowienia przy niepoprawnym JSON. Budżet z kontraktu: 25 s na całe `Verify`, 8 s na `rag/`.

## Co sprawdza Go po odpowiedzi modelu (twarde reguły, `CONTRACT.md` §4)

Model proponuje, Go rozstrzyga. Odpowiedź modelu jest odrzucana albo obniżana, gdy:

1. **Cytat nie występuje dosłownie** w fragmencie o podanym `id` (porównanie po normalizacji białych znaków i cudzysłowów). Cytat jest usuwany; bez cytatu werdykt `confirmed`/`false` spada do `insufficient_evidence`.
2. **`id` nie istnieje** w `results` z `rag/`. Cytat usuwany.
3. **Za słaba podstawa**: `confirmed` lub `false` wymaga cytatu i albo jednego źródła `official`, albo dwóch niezależnych `secondary` (różni wydawcy), albo oceny `factcheck`. Inaczej `insufficient_evidence` z `missing`.
4. **Ocena weryfikatora** (`factcheck`): Go mapuje ocenę z fragmentu (np. „Fałsz” → `false`, „Prawda” → `confirmed`, „Częściowa prawda”, „Manipulacja”, „Brak kontekstu” → `misleading`) i sprawdza zgodność z werdyktem modelu. Zgodna ocena ustawia rolę cytatu i daje mocną podstawę. Niezgodna nie nadpisuje werdyktu: weryfikator mógł oceniać inne, podobne twierdzenie, więc wynik to `insufficient_evidence` z notą w `limitations`.
4a. **Inne liczby w cytacie**: cytat potwierdzający (i każdy cytowany `factcheck`, porównywany po sprawdzonym przez weryfikatora twierdzeniu) musi zawierać każdą liczbę zapisaną cyframi w twierdzeniu, jeśli sam podaje jakieś liczby cyframi. Inaczej rola spada do `context`, a werdykt bez innej podstawy do `insufficient_evidence` z notą w `limitations` (źródło o 458 posłach nie potwierdza twierdzenia o 460). Liczebniki porządkowe („65.”) i numery przepisów („art. 98”) się nie liczą; liczby słowne („czteroletnie”) nie blokują reguły.
5. **`campaignAlert`** z `rag/` nigdy nie zmienia werdyktu: trafia do `warnings[].type = incident_match` i do `campaignAlert` odpowiedzi.
6. **`suspected_injection`** na fragmencie albo `podejrzane: true` od modelu → `meta.injectionAttempts + 1`, wpis w logu; fragment zostaje danymi.
7. **Brak wyników z `rag/`** → model dostaje pustą listę źródeł i może tylko uznać treść za opinię lub przewidywanie (`not_verifiable`). Zasada 2 w `judge.system.md` wprost na to pozwala, bo samo rozpoznanie opinii nie wymaga źródeł. Każdy inny werdykt staje się `insufficient_evidence` (szablon `missing`: „Nie znaleziono publikacji na ten temat w dostępnych źródłach.”), a uzasadnienie modelu nie jest pokazywane.
8. **Awaria `rag/`, modelu lub brak klucza** → `technical_error`, nigdy werdykt. Awaria źródła zewnętrznego (`externalSources[].status = error`) → `limitations` („Nie mogę teraz sprawdzić ocen weryfikatorów faktów.”); gdy to jedyna podstawa → `technical_error`.
9. **`evidenceStrength`** liczone w Go z przesłanek: typ i liczba niezależnych źródeł, wiek (`publishedAt`), zgodność ról z werdyktem. `strengthReasons` to te przesłanki po polsku.
10. **Spójność kanałów**: ten sam `input` daje ten sam wynik; `rag/` ma cache, a `temperature: 0` ogranicza losowość modelu. Przy rozjeździe wygrywają reguły powyżej, nie model.

## Przepływ `Verify`

1. Wejście: `text` albo `url`. Dla `url` agent woła `POST /fetch` w `rag/` (ten sam parser co przy zasilaniu korpusu; decyzja zespołu: pobieranie zostaje w rag), dostaje tytuł i tekst strony. Maskowanie danych osobowych robi backend przed `Verify`.
2. **Ekstrakcja**: gdy wejście ma jedno zdanie (≤ 300 znaków, bez nowej linii, bez granicy zdania „. Wielka litera”, nie jest pytaniem), twierdzeniem jest samo wejście, bez modelu. Liczebnik porządkowy („po 65. roku”) nie dzieli zdania. Pytania idą do `extract`, który zamienia je na zdania oznajmujące i zachowuje słowa zakresu („tylko”, „wyłącznie”). Inaczej `extract` → maks. 3 najważniejsze twierdzenia (główna teza i te z liczbami, datami, nazwami); gdy model zgłosi `pominiete > 0`, do `limitations` trafia „Sprawdzono 3 najważniejsze twierdzenia z N w tekście.” Pusta lista → `needs_clarification`.
3. Dla każdego twierdzenia: `POST /search` w `rag/` (`topK` 5) → reguła 7 albo `judge` → walidacja 1–6 → `Claim`.
4. Złożenie `CheckResult`: `limitations`, `meta` (model, czas, `corpusVersion`, `injectionAttempts`, `abstained`).

## Znane słabości (do pomiaru w `eval/`)

- 0.6B może mieszać role cytatów („potwierdza” vs „obala”) i wybierać luźno związany fragment. Reguły 1–4 zamieniają to w `insufficient_evidence`, nie w fałszywy werdykt, ale obniżą macro-F1. Jeśli pomiar pokaże, że ekstrakcja albo wybór cytatu zawodzą, pierwszym ruchem jest większy model w tym samym promptcie, nie dłuższy prompt.
- Ekstrakcja z długich tekstów (artykuł z URL) może pomijać kluczowe tezy. `max_claims` = 3 to limit czasu (3 wyszukiwania + 3 oceny w 25 s), nie jakości.
