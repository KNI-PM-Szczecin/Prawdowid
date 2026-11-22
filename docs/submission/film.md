# Film demonstracyjny: skrypt na 2 minuty 50 sekund

Limit z briefu: **3 minuty**, film pod linkiem (`spec/brief.md`, rozdział 4). Skrypt mieści się w 2:50, żeby zostawić zapas na montaż. Film jest też zapasowym pokazem na scenie, gdyby zawiodła sieć. Dane w filmie są fikcyjne albo publiczne, bez danych osobowych i kluczy.

Kolumna „Oczekiwany wynik” opisuje, co system **powinien** zwrócić według korpusu i testów. Nie uruchamialiśmy jeszcze wszystkich scen na działającej instancji. Każdą trzeba przejść przed nagraniem, a jeśli wynik będzie inny, zmieniamy przykład albo tekst lektora. Lektor nigdy nie obiecuje więcej, niż pokazuje ekran.

## Przebieg

| Czas | Co widać | Co mówimy | Oczekiwany wynik |
|---|---|---|---|
| 0:00–0:10 | Krótki zrzut podejrzanej wiadomości, od razu wklejanie jej do pola na stronie głównej | „Dostajesz wiadomość i nie wiesz, czy to prawda. Wklejasz ją do Prawdowida i dostajesz ocenę z dowodami.” | Strona główna z jednym polem |
| 0:10–0:40 | Pytanie: „Czy tylko Wrocław oferuje bezpłatną komunikację miejską dla osób po 65. roku życia?” Wynik: werdykt, siła podstawy, cytat, odnośnik. Kursor na podświetlonym twierdzeniu, na źródle, na trzy sekundy na panelu dostępności | „Dla każdego twierdzenia widać werdykt i siłę podstawy. Tutaj werdykt opiera się na ocenie weryfikatora faktów i na dosłownym cytacie. Cytat ze źródła jest oddzielony od interpretacji modelu. Ustawienia dostępności zmieniają kontrast i rozmiar tekstu.” | `false`; w korpusie jest wpis Demagoga (nie obiecujemy w narracji konkretnego źródła ponad to, co pokazuje ekran) |
| 0:40–0:58 | Twierdzenie: „Unia Europejska liczy 28 państw członkowskich.” Wynik i cytat o 27 państwach | „Zdanie bywało prawdziwe, ale dziś jest nieaktualne. Prawdowid odróżnia to od zwykłego fałszu i pokazuje, co się zmieniło.” | `misleading`; źródło: Ministerstwo Infrastruktury o wyjściu Wielkiej Brytanii |
| 0:58–1:23 | Pytanie bez publikacji: „Czy od przyszłego miesiąca w Limanowej parkowanie w centrum będzie możliwe wyłącznie przez aplikację?” Wynik z opisem braków | „Gdy dowodów brakuje albo sprawa jest zbyt nowa, nie zgadujemy. Mówimy wprost, czego nie udało się ustalić.” | `insufficient_evidence` z opisem, czego brakuje |
| 1:23–1:48 | Przesłanie zrzutu ekranu z tekstem doniesienia. Widać odczytany tekst i wynik | „Można też wysłać zrzut ekranu. Tekst odczytujemy z obrazu u siebie, a samego obrazu nie zapisujemy. Dalej sprawdzamy go tak jak wklejone zdanie.” | Poprawnie odczytany tekst i wynik; uwaga o ograniczeniach odczytu |
| 1:48–2:05 | Wklejony adres strony demonstracyjnej z ukrytą instrukcją (`/demo/injection.html`) na **publicznym wdrożeniu**. W kadrze panel szczegółów technicznych z liczbą wykrytych prób | „Jeśli strona ukrywa instrukcje dla modelu, czytamy je jak zwykłą treść, a nie jak polecenie. Taką próbę liczymy i zapisujemy w logu.” | Poprawny werdykt (`confirmed` dla twierdzenia o UE), `injectionAttempts` ≥ 1 |
| 2:05–2:30 | Serwer Discord: komenda `/factcheck` z pytaniem o Wrocław. Odpowiedź bota, kliknięcie reakcji rozwija pełne uzasadnienie | „Teraz to samo pytanie na Discordzie. Werdykt i publikacja są identyczne, bo oba kanały przechodzą tę samą ścieżkę sprawdzania.” | Ten sam werdykt i źródło co na stronie |
| 2:30–2:50 | Plansza z nazwą projektu. W kadrze widać publiczny adres wdrożenia | „Dowodów szukamy w korpusie wiarygodnych źródeł, a o werdykcie decydują reguły w kodzie. Bez opłat i prostym językiem. Prawdowid: dowody zamiast zgadywania.” | |

Narracja ma około 150 słów na 170 sekund. To spokojne tempo, a czas oczekiwania na odpowiedź systemu (kilkanaście sekund, zależnie od pytania) wycinamy w montażu.

## Zasady lektora
- Jedno zdanie opisuje to, co widać, drugie mówi, dlaczego tak jest. Bez żargonu: zamiast „reranker” mówimy „wyszukiwanie dowodów”.
- Nazwy zgodne z ekranem: „werdykt”, „siła podstawy”, „źródła”.
- Unikamy kalk z angielskiego. Opowiadamy o tym, co system robi, a nie o tym, czego nie robi.
- Pilnujemy, żeby nie było powtórzeń: kolejne zdania nie zaczynają się od tego samego słowa, a „system” nie jest podmiotem kilku scen z rzędu.
- Liczby (czas odpowiedzi, wyniki testów) podajemy tylko wtedy, gdy mamy je z pomiaru. Celowo nie ma ich w tym skrypcie.

## Przygotowanie do nagrania
- [ ] Każda scena przetestowana na działającej instancji, oczekiwane wyniki potwierdzone albo przykłady zmienione
- [ ] Każde pytanie puszczone raz przed nagraniem (korpus uzupełnia się wtedy z gov.pl, a kolejne zapytania są szybsze)
- [ ] Nagranie na **publicznym wdrożeniu**: strona demonstracyjna z ukrytą instrukcją nie zadziała z adresu lokalnego, bo moduł wyszukiwania odrzuca adresy lokalne i prywatne
- [ ] Moduł wyszukiwania (`rag/`) rozgrzany po wdrożeniu. Zimny start trwa kilkanaście sekund według README modułu, a pierwszy start z pobieraniem modeli (ok. 3 GB) znacznie dłużej (`docs/docker.md`)
- [ ] Zrzut ekranu do sceny z odczytem tekstu przygotowany: tekst widoczny, bez danych osobowych
- [ ] Bot Discord online na serwerze testowym, komenda `/factcheck` zarejestrowana (ustawione `DISCORD_GUILD_ID`, wtedy pojawia się od razu)
- [ ] Klucze, tokeny i adresy administracyjne poza kadrem
- [ ] Każdy przykład wklejany z notatki, nie z pamięci, bez literówek
- [ ] Nagranie w rozdzielczości co najmniej 1080p, dźwięk sprawdzony
- [ ] Film opublikowany pod linkiem dostępnym dla jury, długość do 3:00 sprawdzona

## Plan B
- **Brak sieci:** pokazujemy nagranie.
- **Padnięty Discord:** scena 2:05–2:30 idzie przez adapter demonstracyjny (`POST /api/channels/demo`) z tym samym pytaniem w terminalu, a lektor mówi „drugi kanał”.
- **Awaria modułu wyszukiwania:** scenę ze zrzutem ekranu pokazujemy w trybie demonstracyjnym interfejsu. Przy awarii modelu lub bazy zostawiamy w kadrze komunikat o błędzie technicznym jako dowód, że awaria nie udaje werdyktu, i nagrywamy scenę ponownie.

## Jeśli film przekroczy 3:00 (kolejność cięcia)
1. Plansza końcowa do 10 s.
2. Intro do 8 s.
3. Scena o Wrocławiu do 25 s (mniej wędrowania kursorem).
4. Scena o UE do 14 s.
5. Scena ze zrzutem ekranu do 18 s (cięcie między wyborem pliku a odczytanym tekstem).
6. Dopiero na końcu cała scena o UE. **Nie wycinamy** sceny ze stroną z ukrytą instrukcją ani sceny z Discordem: pierwsza pokazuje odporność na manipulację, a druga spełnia warunek dwóch kanałów z briefu.

## Opcjonalnie (jeśli zostanie 10 sekund)
Pętla informacji: ten sam brak dowodów (Limanowa) pokazany w widoku analityka jako sprawa, z rozróżnieniem „zalecona” i „przekazana”. Dodajemy tylko wtedy, gdy ekran to naprawdę pokazuje.
