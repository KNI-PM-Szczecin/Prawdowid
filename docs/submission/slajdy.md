# Prezentacja PDF: plan 12 slajdów i instrukcja dla wykonawcy

Ten plik wystarcza, by zbudować prezentację bez dodatkowych pytań. Najpierw jest instrukcja (część A), potem treść slajdów (część B).

---

# Część A. Instrukcja dla wykonawcy (Claude)

## Cel i wynik
Przygotuj prezentację projektu **Prawdowid** na hackathon HackNation 2026 (zadanie Ministerstwa Spraw Zagranicznych). Wynik to **jeden plik PDF**:
- **maksymalnie 12 slajdów** (wymóg z `spec/brief.md`, rozdział 4),
- **maksymalnie 10 MB** (wymóg platformy HackTribe),
- format 16:9, język polski,
- czytelna dla jurorów, którzy mają realnie tylko kilka minut na ocenę całego zgłoszenia.

## Co przeczytać przed pracą
1. `spec/requirements.md`: streszczenie wymagań, miar i kryteriów oceny.
2. `spec/brief.md`, rozdziały 3, 4, 6 i 8: pełny tekst zadania.
3. Część B tego pliku: treść slajdów.
4. `docs/submission/opis.md` i `README.md`: spójność z opisem zgłoszenia.
5. `CONTRACT.md` §1, §3 i §4: kształt odpowiedzi i reguły werdyktów (do slajdu 4).

## Kryteria oceny jury (od nich zależy układ)
Jakość weryfikacji i dowodów 30%, bezpieczeństwo i transparentność 20%, potencjał wdrożeniowy 20%, użyteczność i dostępność 15%, innowacyjność i kompletność 15%. Slajdy mają wprost pokazywać każdy z tych punktów.

## Wygląd (zgodnie z aplikacją)
- **Font:** Prompt (Google Fonts). Zapasowy: system-ui, sans-serif.
- **Kolory** (tokeny z `src/frontend/src/styles/_tokens.scss`): tło `#ffffff`, tekst `#111111`, tekst pomocniczy `#3a3a3a`, link `#0b4fc2`. Pastelowe plamy: pozytywna `#defccc` (linia `#8ccc6a`, akcent `#1c7a30`), negatywna `#ffd3d3` (linia `#e08f8f`, akcent `#b3261e`), ostrzeżenie `#fff6b5` (linia `#d9b700`, akcent `#845c00`), neutralna `#eceef2` (linia `#9aa1ab`, akcent `#374050`).
- **Logo MSZ:** `src/frontend/public/msz-logo.png` (czarne na przezroczystym tle, zawsze na białym tle).
- Styl: oszczędny, dużo białej przestrzeni, kontrast zgodny z WCAG AA (projekt promuje dostępność, więc prezentacja musi być czytelna). Bez ozdobników i stockowych zdjęć.

## Zasady treści (obowiązkowe)
- **Pisz po polsku**, poprawnie i naturalnie. Bez kalk z angielskiego. **Nie używaj zwrotu „sędzia prawdy”** ani jego odpowiedników.
- **Pilnuj powtórzeń.** Kolejne zdania i punkty nie mogą zaczynać się od tego samego słowa, a to samo słowo nie powinno wracać w sąsiednich zdaniach.
- Jedna myśl na slajd. Tytuł jest wnioskiem, a nie nazwą działu. Najwyżej około 40 słów tekstu na slajd, resztę niosą schemat i zrzuty ekranu.
- **Niczego nie wymyślaj.** Nie wpisuj liczb, wyników testów, kosztów ani nazw, których nie ma w tym pliku lub repozytorium. Pola `[DO UZUPEŁNIENIA]` zostaw w widocznym miejscu (np. szara ramka z napisem) i **wypisz je w podsumowaniu**; nie zgaduj ich zawartości.
- Nazwy technologii (RAG, Go, Python, Qdrant itd.) mają być widoczne na slajdach 5 i 6, ale drugoplanowo.
- Zrzuty ekranu dostarczy zespół. Do czasu ich dostarczenia wstaw **ramkę zastępczą** w odpowiednich proporcjach z opisem, co ma się w niej znaleźć.
- Dane osobowe i klucze nie mogą pojawić się w żadnym miejscu.

## Sposób wykonania
1. Zaproponuj układ i **pokaż go** (np. jeden plik HTML z 12 sekcjami lub zrzuty podglądu), zanim zaczniesz dopracowywać szczegóły.
2. Zbuduj prezentację jako stronę HTML (jedna sekcja na slajd, stały rozmiar 1920×1080) i wyeksportuj do PDF przeglądarką (np. Playwright, `page.pdf` z `width: 1920px`, `height: 1080px`, `printBackground: true`). Dopuszczalny jest też inny sposób, który daje PDF o tych samych parametrach.
3. **Sprawdź wynik** (nie zakładaj): liczba stron ≤ 12 (`pdfinfo plik.pdf`), rozmiar ≤ 10 MB (`ls -l`), żaden tekst nie wychodzi poza slajd, kontrast i rozmiar tekstu są czytelne z odległości (minimum około 24 px na slajdzie 1920×1080). Obejrzyj każdy slajd jako obraz.
4. Zwróć: plik PDF, źródło (HTML i zasoby), listę pozostałych pól `[DO UZUPEŁNIENIA]` i listę wszystkiego, co zmieniłeś względem tego planu.
5. Dopiero po akceptacji układu przygotuj notatki prelegenta (krótkie, po 1–2 zdania na slajd).

## Kontekst projektu (do zrozumienia, nie do przepisywania)
Prawdowid to narzędzie dla obywatela do szybkiego sprawdzania doniesień (tekst, link, zrzut ekranu) w oparciu o wiarygodne źródła. Dla każdego twierdzenia zwraca werdykt, uzasadnienie po polsku, siłę dowodów i źródła z cytatem, a gdy dowodów brakuje, wstrzymuje się od oceny. O dopuszczalności odpowiedzi decydują reguły w kodzie (`agent/rules.go`), nie model językowy. Stos: Preact (front), Go (backend i agent), Python z FastAPI (wyszukiwanie), PostgreSQL, Qdrant, Docker. Repozytorium: <https://github.com/KNI-PM-Szczecin/prawdowid>.

---

# Część B. Treść slajdów

Oznaczenia: `[DO UZUPEŁNIENIA]` to dane, których jeszcze nie mamy. `[ZRZUT]` to miejsce na zrzut ekranu dostarczony przez zespół.

## 1. Tytuł
Najprostszy slajd, bez ozdobników i bez zrzutu ekranu.
- **Prawdowid**
- Ministerstwo Spraw Zagranicznych (z logo MSZ)
- KNIPM

## 2. Problem i użytkownicy
- **Tytuł:** Płynna odpowiedź to jeszcze nie dowód
- Fałsz rozchodzi się szybciej, niż da się go sprawdzić. Treść bywa nieaktualna, wyjęta z kontekstu albo dotyczy zdarzenia bez publikacji.
- Model językowy brzmi pewnie nawet wtedy, gdy się myli.
- **Dla kogo:** obywatel bez wiedzy technicznej oraz analityk, który chce widzieć powtarzające się pytania bez odpowiedzi.
- **Grafika:** dwie ikony użytkowników. Opcjonalnie jedna liczba ze źródłem [DO UZUPEŁNIENIA albo pominąć].

## 3. Rozwiązanie: szybka weryfikacja
Slajd ma podkreślać, że to **szybkie sprawdzenie** w jednym kroku.
- **Tytuł:** Szybka weryfikacja w jednym kroku
- **Schemat w czterech krokach:** zgłoszenie (tekst, link, link ukryty w tekście, zrzut ekranu odczytany przez OCR) → twierdzenia (opinie i prognozy trafiają do „nie podlega weryfikacji”) → wyszukane źródła → werdykt z cytatem
- **Grafika:** poziomy diagram z czterema polami i przykładem zgłoszenia. Duży napis lub oznaczenie czasu: sprawdzenie trwa kilka sekund (limit 25 s na całe sprawdzenie, cel z briefu: mediana do 30 s). Konkretny czas wpisać tylko z pomiaru [DO UZUPEŁNIENIA].

## 4. Jak decydujemy
Cały slajd to **zrzut ekranu wyniku** z opisanymi elementami (odnośnikami w formie numerowanych znaczników).
- **Tytuł:** Reguły w kodzie, a nie opinia modelu
- **Zrzut:** [ZRZUT] wynik sprawdzenia z werdyktem „potwierdzone”, uzasadnieniem, siłą dowodów, źródłem z cytatem i ograniczeniami.
- **Opisy znaczników (jedna linia każdy):**
  1. Werdykt z pięciu możliwych: potwierdzone, fałszywe, wprowadzające w błąd, brak wystarczających dowodów, nie podlega weryfikacji. Awaria techniczna ma osobny status i nigdy nie jest werdyktem.
  2. Siła dowodów z jawnymi przesłankami.
  3. Cytat stoi w źródle słowo w słowo. „Potwierdzone” i „fałszywe” wymagają źródła urzędowego, oceny weryfikatora faktów albo dwóch niezależnych wydawców wtórnych.
  4. Źródła pokazane osobno od interpretacji modelu, z datą i odnośnikiem.
  5. Gdy dowodów brak, system mówi, czego nie ustalił. Sama domena, autor czy popularność nigdy nie przesądzają o werdykcie.

## 5. Źródła i korpus
- **Tytuł:** Każdy dowód ma datę, wydawcę i uzasadnienie wyboru
- **Trzy rodzaje:** źródła urzędowe (gov.pl, akty prawne), weryfikatorzy faktów (Google Fact Check, zapytanie na żywo) i źródła wtórne
- **Wyszukiwanie dowodów (RAG):** system pobiera dowody z korpusu zamiast odpowiadać z pamięci modelu. Dopasowanie semantyczne (BGE-M3) łączy się ze słownikowym (BM25), a wyniki są ponownie szeregowane rerankerem.
- Katalog zaufanych źródeł z regułami kwalifikowania i wykluczania, ocena wieku materiału, lista źródeł do audytu
- Znane kampanie dezinformacyjne (EUvsDisinfo) dają ostrzeżenie, a nie werdykt
- **Liczby korpusu demonstracyjnego:** [DO UZUPEŁNIENIA: dokumentów, domen, typów źródeł]
- **Grafika:** tabela lub diagram z podziałem na rodzaje źródeł

## 6. Architektura
- **Tytuł:** Kanały oddzielone od logiki, model do wymiany
- **Diagram:** strona WWW (Preact), bot Discord i adapter demonstracyjny → backend (Go) → agent (Go) → moduł RAG (Python, FastAPI; wektory BGE-M3, BM25, reranker; Qdrant i PostgreSQL) → model językowy (OpenAI, wymienny na lokalny) za jednym interfejsem. Całość w Dockerze, wdrożenie na Railway.
- **Podpis pod diagramem:** zmiana modelu lub dostawcy nie wymaga przebudowy systemu
- Nazwy technologii widoczne, ale małą czcionką pod diagramem, żeby nie zasłaniały głównej myśli.
- **Grafika:** schemat (źródło: `CONTRACT.md`)

## 7. Bezpieczeństwo, prywatność i ryzyka
Ten slajd pokrywa wymóg briefu dotyczący ryzyk, pokazując je razem z zabezpieczeniami.
- **Tytuł:** Siedem ryzyk, siedem zabezpieczeń
- **Tabela:**
  - Halucynacje → odpowiedź opiera się na pobranych dowodach, a nie na pamięci modelu; cytat musi stać w źródle, a awaria nie jest werdyktem
  - Stronniczość źródeł → katalog zaufanych źródeł, lista do audytu, zakaz werdyktu z samej domeny
  - Prywatność → maskowanie e-maila, PESEL, telefonu i IBAN, usuwanie przebiegu, retencja 30 dni
  - Polecenia ukryte w treści → treść źródeł to dane, wykrywanie i zapis prób
  - Dostępność → panel ustawień, prosty język, status zamiast zgadywania przy awarii
  - Nadużycia → limit zapytań z jednego adresu, tokeny w zmiennych środowiska
  - Mało danych lub świeże wydarzenie → system się wstrzymuje, mówi, czego nie ustalił, i podaje to, co jest znane
- Pod tabelą jedna linia: log czasu, modelu, błędów, wstrzymań i kosztu. **Miejsce przetwarzania danych:** treść twierdzeń trafia do OpenAI (model językowy) i do Google (Fact Check), czyli do dostawców spoza EOG. Embeddingi i reranker działają lokalnie. [DO UZUPEŁNIENIA: lokalizacja bazy].

## 8. Interfejs i dostępność
- **Tytuł:** Prosta odpowiedź, dostępna dla każdego
- Twierdzenia podświetlone w tekście, kliknięcie otwiera panel ze źródłami, siłą dowodów i ograniczeniami
- Panel dostępności: kontrast (domyślny, wysoki jasny i ciemny), rozmiar tekstu od 100 do 200%, ograniczenie animacji
- **Grafika:** [ZRZUT] wynik z podświetleniem oraz [ZRZUT] panel ustawień (zrzuty są gotowe)

## 9. Kanały i pętla informacji
- **Tytuł:** Ten sam wynik w każdym kanale, a pytania bez odpowiedzi trafiają do analityka
- **Kanały:** strona WWW, bot Discord (komenda `/factcheck`) i adapter demonstracyjny. Wszystkie korzystają z jednej ścieżki weryfikacji.
- **Pętla informacji:** pytania bez dowodów łączymy w sprawy razem z parafrazami. Sprawa jest „zalecona” po spełnieniu reguły, a „przekazana” dopiero wtedy, gdy webhook moderatora to potwierdzi.
- **Grafika:** [ZRZUT] ta sama odpowiedź na stronie i w bocie Discord obok siebie. **Zrzuty z bota będą dostarczone później**, do tego czasu ramka zastępcza.

## 10. Demonstracja
- **Tytuł:** Cztery sceny z działającego systemu
- Potwierdzone ze źródłem i cytatem
- Brak dowodów: system wstrzymuje się i mówi, czego nie ustalił
- Zrzut ekranu odczytany przez OCR
- To samo pytanie w bocie Discord z tym samym wynikiem
- **Grafika:** cztery [ZRZUT] z działającej instancji. Zrzuty dostarczy zespół.

## 11. Wyniki testów
- **Tytuł:** Mierzymy się według miar z zadania
- **Tabela:** miara, cel, nasz wynik: trafność werdyktu (macro-F1 ≥ 0,75), pokrycie cytowań (≥ 95%), poprawność cytowań (≥ 85%), wstrzymanie się bez dowodów (≥ 80%), odporność na polecenia w treści (≥ 90%), czas (mediana ≤ 30 s), koszt 100 testów
- **Zestawy:** własne 44 przypadki według scenariuszy A–J z briefu oraz osobny test na twierdzeniach ocenionych przez zewnętrznych weryfikatorów faktów
- **Wyniki:** [DO UZUPEŁNIENIA z prawdziwego przebiegu `eval/`]. Pod tabelą: dane i polecenie do odtworzenia. Nie wolno wpisywać liczb, których zespół nie dostarczył.

## 12. Gotowe do pilotażu
Ten slajd mówi o wartości wdrożeniowej (20% oceny), bez listy tego, czego system nie robi.
- **Tytuł:** Od prototypu do pilotażu w MSZ
- **Dlaczego da się wdrożyć:** moduły są niezależne (kanały, wyszukiwanie, model), każdy dowód można sprawdzić, całość startuje jednym poleceniem w Dockerze
- **Koszt:** [DO UZUPEŁNIENIA: szacunek kosztu 1000 zapytań i zależności zewnętrzne]
- **Plan:** pilotaż na 4–6 tygodni na zamkniętym korpusie z kolejką ekspercką, potem ograniczone wdrożenie publiczne z monitoringiem jakości, następnie kolejne kanały, języki i źródła
- **Grafika:** oś czasu z czterema przystankami (źródło: `spec/brief.md`, rozdział 9)

---

## Przed oddaniem
- [ ] Usunięte wszystkie znaczniki `[DO UZUPEŁNIENIA]` i ramki zastępcze
- [ ] Liczby ze slajdów 3, 5, 11 i 12 pochodzą z prawdziwych pomiarów
- [ ] PDF ma najwyżej 12 slajdów i najwyżej 10 MB
- [ ] Zrzuty ekranu bez danych osobowych i kluczy
- [ ] Ograniczenia systemu (czego nie obsługujemy) są opisane w opisie zgłoszenia i README, bo wymaga tego brief
