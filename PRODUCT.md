# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Obywatel w Polsce, także z niskimi kompetencjami cyfrowymi, który trafił na doniesienie (wiadomość, wpis, artykuł) i chce szybko sprawdzić, czy jest wiarygodne. Robi to na telefonie lub komputerze, w chwili wątpliwości, bez wiedzy technicznej. Drugi odbiorca: jury hackathonu i analitycy, którzy audytują źródła i przebieg sprawdzenia. (Źródło: `spec/brief.md`, `spec/requirements.md`.)

## Product Purpose

Prawdowid pozwala sprawdzić doniesienie tak łatwo jak wysłać wiadomość: przez WWW i drugi kanał (Discord). Wskazuje twierdzenia do sprawdzenia, porównuje je z korpusem wiarygodnych źródeł i zwraca ocenę z dowodami, albo uczciwie wstrzymuje się od oceny. Sukces: obywatel rozumie, na czym opiera się ocena, i może sam sprawdzić źródła. Produkt nie jest „automatycznym sędzią prawdy”, wspiera świadomą ocenę.

## Positioning

Każda ocena prowadzi do konkretnego źródła z tytułem, wydawcą, datą, linkiem i cytatem. Brak dowodów daje jawne wstrzymanie się, nigdy pozorną odpowiedź. Ocena nigdy nie wynika z domeny, autora, kanału ani popularności.

## Operating Context

Zadanie Ministerstwa Spraw Zagranicznych na HackNation 2026 (24 h). Jury uruchamia demo samodzielnie z instrukcji i testuje scenariusze A–J (fakt prosty, brak kontekstu, sprzeczne źródła, brak dowodów, prompt injection, spójność kanałów, awaria). Korpus: źródła urzędowe (dane.gov.pl, BIP, ISAP, EUR-Lex), weryfikatorzy faktów (IFCN/EFCSN, Demagog), rzetelne media, katalog incydentów (EUvsDisinfo).

## Capabilities and Constraints

- Werdykty: `confirmed`, `false`, `misleading`, `insufficient_evidence`, `not_verifiable`. Statusy niemerytoryczne: `technical_error`, `needs_clarification`, `out_of_scope`, pokazywane inaczej niż werdykt.
- Wynik zawsze zawiera: ocenę, uzasadnienie, siłę podstawy, źródła osobno od interpretacji modelu, ograniczenia.
- Kontrakt danych w `CONTRACT.md`; front w `src/frontend/` (Preact, SCSS), backend Go, agent Go, rag Python.
- Stan na 21.11.2026: backend nie ma jeszcze `POST /api/check`; front ma tryb demonstracyjny z fikcyjnymi danymi (`pnpm dev:mock`).
- Żadnych sfabrykowanych źródeł, cytatów, liczb ani wyników testów w interfejsie. Dane demo są fikcyjne i oznaczone.
- Nie podszywamy się pod serwis administracji publicznej: to prototyp hackathonowy, co interfejs mówi wprost.

## Brand Commitments

Nazwa „Prawdowid”. Projekt graficzny w Figmie (v3, 21.11): font Prompt, białe tło z miękkimi, rozmytymi plamami koloru (bloby) w barwie wyniku (zielony / żółty / czerwony), zielony na stronie głównej; boks zbiorczy z ikoną w kole; chipy; panel boczny twierdzenia z plamą koloru w prawym górnym rogu. Teksty po polsku, prostym językiem, rejestr formalny.

## Evidence on Hand

- `spec/brief.md`, `spec/requirements.md`, `spec/mentor-test-scenarios.md`: wymagania i scenariusze jury.
- `docs/api.md`: kontrakt API i mapowanie na ekrany.
- Brak: nazwa zespołu w materiałach, prawdziwe wyniki testów, prawdziwy korpus w interfejsie demo. Nie wymyślać.

## Product Principles

1. Dowód przed werdyktem: nic nie jest „ustaleniem systemu” bez źródła, które użytkownik może otworzyć.
2. Niepewność mówimy wprost, osobno od oceny.
3. Prosty język i dostępność (WCAG 2.1 AA) są warunkiem, nie dodatkiem.
4. Interfejs pokazuje, co system naprawdę robi, bez obietnic ponad implementację.

## Accessibility & Inclusion

Cel WCAG 2.1 AA. Każdy stan ma tekst, nie tylko kolor. Trzy tryby kontrastu, rozmiar tekstu do 200%, ograniczenie animacji, obsługa klawiaturą, czytniki ekranu.
