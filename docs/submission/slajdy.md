# Prezentacja PDF: propozycja 12 slajdów

Limity: **12 slajdów** (`spec/brief.md`, rozdział 4) i **10 MB** (instrukcja HackTribe). Kolejność wymagana przez brief: problem, użytkownicy, architektura, demonstracja, wyniki testów, ryzyka, dalsze kroki.

Znaczniki w nawiasach kwadratowych oznaczają dane do uzupełnienia i **trzeba je usunąć przed oddaniem**. Liczb z testów nie wpisujemy ręcznie ani nie poprawiamy: biorą się wyłącznie z prawdziwego przebiegu `eval/`.

## Zasady redakcyjne
- Jedna myśl na slajd, tytuł jest wnioskiem, a nie nazwą działu.
- Na slajdzie najwyżej około 40 słów tekstu, reszta to schemat, tabela lub zrzut ekranu.
- Bez powtórzeń słów na początku kolejnych zdań i punktów.
- Nic, czego nie ma w kodzie. Czego nie obsługujemy, mówimy wprost (wymóg briefu).
- Zrzuty ekranu bez danych osobowych i kluczy.

## Slajdy

### 1. Tytuł
- **Tytuł:** Prawdowid
- **Podtytuł:** Sprawdź doniesienie. Zobacz dowody.
- Hackathon HackNation 2026, zadanie Ministerstwa Spraw Zagranicznych
- Nazwa zespołu: [DO UZUPEŁNIENIA], skład: pięć osób
- **Grafika:** logo i zrzut strony głównej

### 2. Problem i użytkownicy
- **Tytuł:** Płynna odpowiedź to jeszcze nie dowód
- Fałsz rozchodzi się szybciej, niż da się go sprawdzić. Treść bywa nieaktualna, wyjęta z kontekstu albo dotyczy zdarzenia bez publikacji.
- Model językowy brzmi pewnie nawet wtedy, gdy się myli.
- **Dla kogo:** obywatel bez wiedzy technicznej oraz analityk, który chce widzieć powtarzające się pytania bez odpowiedzi.
- **Grafika:** jedna liczba ze źródłem [DO UZUPEŁNIENIA albo pominąć], dwie ikony użytkowników

### 3. Rozwiązanie: od zgłoszenia do werdyktu
- **Tytuł:** Wklejasz, a my pokazujemy dowody
- **Schemat w czterech krokach:** zgłoszenie (tekst, link, link ukryty w tekście, zrzut ekranu odczytany przez OCR) → twierdzenia (opinie i prognozy trafiają do „nie podlega weryfikacji”) → wyszukane źródła → werdykt z cytatem
- **Grafika:** poziomy diagram z czterema polami i przykładem zgłoszenia

### 4. Jak decydujemy
- **Tytuł:** Reguły w kodzie, a nie opinia modelu
- **Pięć werdyktów:** potwierdzone, fałszywe, wprowadzające w błąd, brak wystarczających dowodów, nie podlega weryfikacji. Awaria techniczna ma osobny status i nigdy nie jest werdyktem.
- **Warunki:** cytat musi stać w źródle słowo w słowo. „Potwierdzone” i „fałszywe” wymagają źródła urzędowego, oceny weryfikatora faktów albo dwóch niezależnych wydawców wtórnych.
- Gdy źródła się różnią, najpierw wyjaśniamy różnicę. Gdy dowodów brak, mówimy, czego nie ustalono. Sama domena, autor czy popularność nigdy nie przesądzają o werdykcie.
- **Grafika:** tabela „sytuacja → odpowiedź systemu”

### 5. Źródła i korpus
- **Tytuł:** Każdy dowód ma datę, wydawcę i uzasadnienie wyboru
- **Trzy rodzaje:** źródła urzędowe (gov.pl, akty prawne), weryfikatorzy faktów (Google Fact Check, zapytanie na żywo) i źródła wtórne
- Katalog zaufanych źródeł z regułami kwalifikowania i wykluczania, ocena wieku materiału, lista źródeł do audytu
- Znane kampanie dezinformacyjne (EUvsDisinfo) dają ostrzeżenie, a nie werdykt
- **Liczby korpusu demonstracyjnego:** [DOKUMENTÓW], [DOMEN], [TYPÓW] (minimum z briefu: 100, 10 i 2)
- **Grafika:** tabela z podziałem na rodzaje źródeł

### 6. Architektura
- **Tytuł:** Kanały oddzielone od logiki, model do wymiany
- **Diagram:** strona WWW, bot Discord i adapter demonstracyjny → backend (Go) → agent (Go) → wyszukiwanie (Python) → Qdrant i PostgreSQL. Model językowy za jednym interfejsem. Całość w Dockerze, wdrożenie na Railway.
- **Podpis pod diagramem:** zmiana modelu lub dostawcy nie wymaga przebudowy systemu
- **Grafika:** schemat z `CONTRACT.md`

### 7. Bezpieczeństwo i prywatność
- **Tytuł:** Treść ze źródeł to dane, a nie polecenia
- Wykrywanie poleceń ukrytych w zgłoszeniu i w pobranych stronach, próby są zliczane i zapisywane
- Maskowanie e-maila, numeru PESEL, telefonu i IBAN przed zapisem. Przebieg można usunąć, a po 30 dniach znika sam.
- Limit zapytań z jednego adresu, sekrety wyłącznie w zmiennych środowiska, log czasu, modelu, błędów, wstrzymań i kosztu
- **Miejsce przetwarzania danych:** [DO UZUPEŁNIENIA: dostawca modelu, Google, baza]
- **Grafika:** schemat „zgłoszenie → maskowanie → agent”

### 8. Interfejs i dostępność
- **Tytuł:** Prosta odpowiedź, dostępna dla każdego
- Twierdzenia podświetlone w tekście, kliknięcie otwiera panel ze źródłami, siłą dowodów i ograniczeniami
- Panel dostępności: kontrast (domyślny, wysoki jasny i ciemny), rozmiar tekstu od 100 do 200%, ograniczenie animacji
- **Grafika:** dwa zrzuty ekranu, wynik i panel ustawień

### 9. Kanały i pętla informacji
- **Tytuł:** Ten sam wynik w każdym kanale, a pytania bez odpowiedzi trafiają do analityka
- **Kanały:** strona WWW, bot Discord (komenda `/factcheck`) i adapter demonstracyjny. Wszystkie korzystają z jednej ścieżki weryfikacji.
- **Pętla informacji:** pytania bez dowodów łączymy w sprawy razem z parafrazami. Sprawa jest „zalecona” po spełnieniu reguły, a „przekazana” dopiero wtedy, gdy webhook moderatora to potwierdzi.
- **Grafika:** ta sama odpowiedź na stronie i na Discordzie obok siebie

### 10. Demonstracja
- **Tytuł:** Cztery sceny z działającego systemu
- Potwierdzone ze źródłem i cytatem
- Brak dowodów: system wstrzymuje się i mówi, czego nie ustalił
- Zrzut ekranu odczytany przez OCR, z jawną uwagą o ograniczeniach
- To samo pytanie na Discordzie z tym samym wynikiem
- **Grafika:** cztery zrzuty z działającej instancji [DO UZUPEŁNIENIA]

### 11. Wyniki testów
- **Tytuł:** Mierzymy się według miar z zadania
- **Tabela:** miara, cel, nasz wynik: trafność werdyktu (macro-F1 ≥ 0,75), pokrycie cytowań (≥ 95%), poprawność cytowań (≥ 85%), wstrzymanie się bez dowodów (≥ 80%), odporność na polecenia w treści (≥ 90%), czas (mediana ≤ 30 s), koszt 100 testów
- **Zestawy:** własne 44 przypadki według scenariuszy A–J z briefu oraz osobny test na twierdzeniach ocenionych przez zewnętrznych weryfikatorów faktów
- **Wyniki:** [DO UZUPEŁNIENIA z prawdziwego przebiegu `eval/`]. Pod tabelą: dane i polecenie do odtworzenia.

### 12. Ryzyka, ograniczenia i dalsze kroki
- **Tytuł:** Uczciwie o tym, czego jeszcze nie robimy
- **Ryzyka z briefu:** halucynacje, stronniczość źródeł, prywatność, polecenia w treści, dostępność, nadużycia. Każde ma jedno zdanie o zabezpieczeniu.
- **Czego nie obsługujemy:** wideo i dźwięku, odwrotnego wyszukiwania obrazu, eksportu danych (CSV, JSON, OpenCTI), wpisów z serwisów społecznościowych (jawna odmowa)
- **Koszt 1000 zapytań:** [DO UZUPEŁNIENIA]. Zależności poza EOG: [DO UZUPEŁNIENIA].
- **Dalsze kroki:** pilotaż z MSZ przez 4–6 tygodni na zamkniętym korpusie z kolejką ekspercką, potem kolejne kanały i języki
- **Grafika:** oś czasu z briefu (rozdział 9)

## Przed oddaniem
- [ ] Usunięte wszystkie znaczniki `[DO UZUPEŁNIENIA]`
- [ ] Liczby ze slajdów 5, 11 i 12 pochodzą z prawdziwych przebiegów
- [ ] PDF ma najwyżej 12 slajdów i najwyżej 10 MB
- [ ] Zrzuty ekranu bez danych osobowych i kluczy
- [ ] Spis ograniczeń na slajdzie 12 zgadza się ze stanem kodu
