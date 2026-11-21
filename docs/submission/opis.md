# Opis do oddania (limit: 4000 znaków)

Szkic roboczy (pliki w `docs/submission/`: `opis.md`, `slajdy.md`, `film.md`). Wymagania: nazwa zespołu, tytuł i opis do 4000 znaków (`spec/brief.md` §4). Znaczniki `[WDROŻONE]`, `[ZAPLANOWANE]` i `[DO UZUPEŁNIENIA]` służą zespołowi i **przed oddaniem trzeba je usunąć**. Nie wolno opisywać jako działającej funkcji, której nie ma w kodzie (brief: brak sfabrykowanych wyników, uczciwe ograniczenia). Zliczanie znaków: `python3 docs/submission/count.py`.

**Nazwa zespołu:** [DO UZUPEŁNIENIA]
**Tytuł:** Prawdowid: sprawdź doniesienie tak łatwo, jak wysłać wiadomość

<!-- OPIS-START -->
Prawdowid to narzędzie dla obywatela, które sprawdza doniesienie (tekst lub link) na podstawie wiarygodnych źródeł i pokazuje, skąd wie to, co mówi. Nie jest „sędzią prawdy”: gdy dowodów brakuje, uczciwie wstrzymuje się od oceny.

Jak działa. Zgłoszenie trafia przez stronę WWW albo drugi kanał (Discord) do tej samej logiki weryfikacji. [ZAPLANOWANE] System wyodrębnia twierdzenia i dla każdego zwraca: werdykt (potwierdzone, fałszywe, wprowadzające w błąd, brak wystarczających dowodów, nie podlega weryfikacji), krótkie uzasadnienie po polsku, siłę podstawy z jawnymi przesłankami oraz źródła (tytuł, wydawca, data, link, cytat) pokazane osobno od interpretacji modelu. Awaria techniczna, brak klucza API i niejasne pytanie to osobne statusy, nigdy werdykty.

Źródła i wyszukiwanie. [WDROŻONE] Wyszukiwanie hybrydowe (wektory BGE-M3 i BM25 z fuzją RRF), reranking cross-encoderem, próg trafności 0,5, filtry po typie źródła i dacie. Metadane są wymuszone w schemacie bazy: fragment bez tytułu, wydawcy, dat publikacji i pobrania oraz linku nie jest zwracany. Korpus opiera się na źródłach urzędowych (domeny rządowe) i wtórnych, z katalogiem zaufanych źródeł i uzasadnieniem kwalifikacji. [WDROŻONE] Oceny weryfikatorów faktów (Google Fact Check API) pobieramy na żywo. Wygaszanie starych dokumentów nigdy nie schodzi poniżej 100 dokumentów i 10 domen. [DO UZUPEŁNIENIA] Liczba dokumentów i domen w korpusie demo.

Bezpieczeństwo. [WDROŻONE] Treść stron i źródeł jest danymi, nie instrukcjami: wykrywamy próby prompt injection po normalizacji tekstu, oznaczamy je flagą i nigdy nie wstawiamy do promptu systemowego. Endpointy zapisu są chronione tokenem. Dopasowanie do katalogu kampanii dezinformacyjnych (m.in. EUvsDisinfo) daje wyłącznie neutralne ostrzeżenie, nigdy podstawę werdyktu; podobnie status źródła czy domena. [ZAPLANOWANE] Maskowanie danych osobowych przed zapisem przebiegu, usuwanie sesji demo, limit żądań, log czasu, modelu, błędów, wstrzymań i kosztu.

Architektura. React (front), Go (backend i agent), Python z FastAPI (wyszukiwanie), PostgreSQL i Qdrant. Kanały są oddzielone od logiki weryfikacji, a model i dostawca są wymienne przez jeden interfejs. [DO UZUPEŁNIENIA] Użyty model językowy, dostawca i miejsce przetwarzania danych.

Testy. [WDROŻONE] Własny zestaw 44 przypadków według scenariuszy A–J i skrypt liczący miary z zadania (trafność werdyktu, pokrycie i poprawność cytowań, wstrzymanie się, odporność na injection, czas, koszt). [DO UZUPEŁNIENIA] Wyniki przebiegu.

Ograniczenia. Google Fact Check API jest w wersji v1alpha1, bez opublikowanych limitów, a treść twierdzenia trafia do Google (dostawca spoza EOG). [DO UZUPEŁNIENIA] Pozostałe ograniczenia po wdrożeniu. Szacowany koszt 1000 zapytań: [DO UZUPEŁNIENIA]. Dostęp jest bezpłatny po stronie usługi.
<!-- OPIS-END -->
