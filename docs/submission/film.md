# Film demonstracyjny: skrypt na 2 minuty 50 sekund (zgodny z prezentacją)

Limit z briefu: **3 minuty**, film pod linkiem (`spec/brief.md`, rozdział 4). Skrypt mieści się w 2:50, żeby zostawić zapas na montaż. Film jest też zapasowym pokazem na scenie, gdyby zawiodła sieć. Dane w filmie są fikcyjne albo publiczne, bez danych osobowych i kluczy.

**Zasada nadrzędna: film i prezentacja pokazują te same tematy, w tej samej kolejności i na tych samych przykładach.** Juror, który zobaczy tylko film, nie może uznać, że prezentacja zawiera większość treści, i odwrotnie. Dlatego sceny od 1 do 5 odpowiadają slajdom 3, 7, 8, 9 i 10, a zakończenie slajdom 11 i 12.

Przykłady w scenach 1–4 są **te same**, co na zrzutach slajdu 10. Kolumna „Oczekiwany wynik” opisuje, co system **powinien** zwrócić. Każdą scenę trzeba przejść na żywo przed nagraniem, a lektor nigdy nie obiecuje więcej, niż pokazuje ekran.

## Przebieg

| Czas | Slajd | Co widać | Co mówimy | Oczekiwany wynik |
|---|---|---|---|---|
| 0:00–0:12 | 1–2 | Krótki zrzut podejrzanej wiadomości, potem pole na stronie głównej | „Sprawdź doniesienie tak łatwo, jak wysłać wiadomość. Wklejasz tekst, link albo zrzut ekranu i dostajesz ocenę z dowodami.” | Strona główna z jednym polem |
| 0:12–0:32 | 3, 8, 10 (scena 1) | Strona główna „Sprawdź rzetelność informacji”: pole „Wklej link do artykułu bądź tekst…”, przyciski „Sprawdź” i „Sprawdź zrzut ekranu lub zdjęcie” (PNG, JPEG, WEBP do 5 MB). Napis na ekranie: „Dane przykładowe”. Na trzy sekundy panel dostępności | „Wklejasz tekst albo link, a zrzut ekranu czy zdjęcie wysyłasz drugim przyciskiem. Tekst odczytujemy z obrazu u siebie i sprawdzamy go jak wklejony. Ustawienia dostępności zmieniają kontrast i rozmiar tekstu. Sceny od pierwszej do trzeciej pokazujemy na danych przykładowych.” | Strona główna w trybie demonstracyjnym |
| 0:32–1:00 | 4, 5, 10 (scena 2) | „Woda z wodociągów w Przykładowie jest skażona i nie wolno jej pić.” Znacznik „Fałsz”, uzasadnienie (komunikat Sanepidu z 18 listopada), siła podstawy „Mocna” (źródło urzędowe, aktualne, wprost przeczy twierdzeniu), ostrzeżenie „Podobne do znanej dezinformacji”, lista źródeł | „Werdykt wynika z reguł w kodzie, a nie z opinii modelu. Źródło urzędowe wprost przeczy twierdzeniu, więc siła podstawy jest mocna. Ostrzeżenie o podobieństwie do znanej dezinformacji to tylko informacja, a nie werdykt.” | Fałsz, siła podstawy „Mocna”, ostrzeżenie o dezinformacji |
| 1:00–1:25 | 4, 10 (scena 3) | „Budowa kosztowała 120 mln zł.” Znacznik „Sprzeczne źródła”, siła podstawy „Średnia”, sekcja „Czego nie ustalono”, ramka „Źródła podają sprzeczne informacje” z kwotami urzędu miasta (98 mln zł) i dziennika (120 mln zł) | „Gdy źródła się różnią, pokazujemy obie wersje i mówimy wprost, czego nie ustalono. Tutaj: która kwota obejmuje całą inwestycję.” | Sprzeczne źródła, obie wersje, opis braku rozstrzygnięcia |
| 1:25–1:42 | 7 | Wklejony adres strony demonstracyjnej z ukrytą instrukcją (`/demo/injection.html`) na **publicznym wdrożeniu**. W kadrze panel szczegółów technicznych z licznikiem prób | „Jeśli strona ukrywa instrukcje dla modelu, wykrywamy je, czytamy jak zwykłą treść, a nie polecenie, i zapisujemy próbę w logu.” | Poprawny werdykt, `injectionAttempts` ≥ 1. Na slajdzie 11 odporność to 71% (cel 90%), a dwie próby skończyły się błędem technicznym, więc **tę scenę trzeba przejść na produkcji kilka razy** i pokazać przebieg, który się udał, bez słowa „odporny” w narracji |
| 1:42–2:08 | 9, 10 (scena 4) | **Prawdziwy system na produkcji.** Serwer Discord, bot „Prawdowid-KNI”: „Pytanie: Czy NATO spowodowało, że Ukraina została zaatakowana przez Rosję?” Odpowiedź „Brak wystarczających dowodów”, źródło: oświadczenie Doradczego Komitetu Prawnego przy MSZ z 4 marca 2022 r. Reakcja ❓ rozwija pełne uzasadnienie | „Teraz prawdziwy system, bot na Discordzie. Oświadczenie MSZ potwierdza napaść Rosji, ale nie rozstrzyga, czy spowodowało ją NATO. Bot nie zgaduje i mówi, czego źródło nie rozstrzyga.” | Brak wystarczających dowodów z opisem tego, czego źródło nie rozstrzyga |
| 2:08–2:26 | 9 | **Prawdziwy system na produkcji**, ten sam układ co na slajdzie 9: pytanie „Czy Polska jest w Unii Europejskiej?” zadane na stronie WWW i botowi Discord. Obok werdykt „Prawda”, siła podstawy „Mocna” i to samo źródło (Inspekcja Jakości Handlowej Artykułów Rolno-Spożywczych, gov.pl). Potem diagram pętli: pytanie bez dowodów → „zalecona” → „przekazana” | „Ta sama odpowiedź na stronie i na Discordzie: ta sama ocena i to samo źródło. Pytania bez dowodów zbieramy dla analityka. Sprawa jest zalecona po spełnieniu reguły, a przekazana dopiero po potwierdzeniu przez webhook.” | Ten sam werdykt i źródło w obu kanałach |
| 2:26–2:50 | 11, 12 | Slajd 11 w całości (wszystkie miary, także te poniżej celu), potem plansza z etapami pilotażu i publicznym adresem | „Mediana czasu odpowiedzi to 5,3 sekundy, a koszt około 0,34 dolara za tysiąc zapytań. Dalej: pilotaż w MSZ na zamkniętym korpusie. Prawdowid, czyli dowody zamiast zgadywania.” | 5,3 s i 0,034 USD za 100 zapytań (slajd 11), około 0,34 USD za 1000 (slajd 12) |

## Zgodność z prezentacją
- Każda scena nazywa to samo, co slajd: „szybka weryfikacja w jednym kroku”, „siła podstawy”, „źródła oddzielone od interpretacji”, „wyszukiwanie dowodów w korpusie”, „ostrzeżenie, a nie werdykt”, „zalecona” i „przekazana”.
- **Przykłady z filmu i ze slajdu 10 są tymi samymi zdaniami.** Sceny 1–3 to interfejs w trybie demonstracyjnym na fikcyjnych danych („Przykładowo”, „Sanepid”, „urząd miasta”). Slajd 10 mówi to wprost („na danych przykładowych”), więc film też musi to powiedzieć i pokazać napis „Dane przykładowe”. Scena 4 to prawdziwy system. Lektor nie nazywa scen 1–3 „działającym systemem”.
- Liczby w filmie (czas, koszt, korpus) wolno podawać tylko wtedy, gdy są także na slajdach i pochodzą z zapisanego raportu z przebiegu.
- Jeśli któraś scena z filmu wypada, jej temat nadal może być na slajdach. Odwrotnie nie: temat z filmu musi mieć slajd.

## Uwagi po porównaniu z prezentacją (wersja `prawdowid-1.pdf`)
- Slajd 11 ma teraz wyniki, w tym **poniżej celu**: macro-F1 0,70 (cel 0,75) i odporność na polecenia w treści 71% (cel 90%). Film nie przedstawia ich jako zaliczonych: nie używa słów „odporny” ani „celnie”, a zakończenie pokazuje cały slajd 11.
- Slajd 9 (wersja `prawdowid-2.pdf`) pokazuje prawdziwe zrzuty strony i bota z tym samym pytaniem i tym samym wynikiem, więc scena 2:08–2:26 dowodzi spójności kanałów. Slajd 3 nie podaje już limitu 25 s.
- Slajd 9 mówi „powtórzenia i bliskie parafrazy łączymy w jedną sprawę”, a slajd 11 przyznaje, że parafraza innymi słowami nie trafia do tej samej sprawy. Brzmi to już łagodniej, ale nadal może wyglądać na sprzeczność. Film mówi tylko to, co działa (sprawa, „zalecona”, „przekazana”).
- Raport `eval/reports/20261122-062059`, na który powołuje się slajd 11, nadal nie leży w repozytorium. Commit `e30de27` istnieje.

## Zasady lektora
- Jedno zdanie opisuje to, co widać, drugie mówi, dlaczego tak jest. Bez żargonu: zamiast „reranker” mówimy „wyszukiwanie dowodów”.
- Nazwy zgodne z ekranem i prezentacją.
- Unikamy kalk z angielskiego. Opowiadamy o tym, co system robi, a nie o tym, czego nie robi.
- Pilnujemy, żeby nie było powtórzeń: kolejne zdania nie zaczynają się od tego samego słowa, a „system” nie jest podmiotem kilku scen z rzędu.

## Przygotowanie do nagrania
- [ ] Sceny 1–3 nagrane w trybie demonstracyjnym interfejsu (`pnpm dev:mock` albo `FRONT_MODE=mock`) z napisem „Dane przykładowe”; scena 4 na produkcji
- [ ] Pytanie do sceny 4 wpisane bez literówek (na zrzucie na slajdzie jest „przez Rosji” i brak spacji po przecinku, w filmie wpisujemy „przez Rosję”)
- [ ] Każde pytanie puszczone raz wcześniej (korpus uzupełnia się z gov.pl, kolejne zapytania są szybsze)
- [ ] Nagranie na **publicznym wdrożeniu**: strona z ukrytą instrukcją nie zadziała z adresu lokalnego, bo moduł wyszukiwania odrzuca adresy lokalne i prywatne
- [ ] Moduł wyszukiwania rozgrzany po wdrożeniu (zimny start kilkanaście sekund według README modułu; pierwszy start z pobieraniem modeli trwa znacznie dłużej, `docs/docker.md`)
- [ ] Zrzut ekranu do sceny 1 przygotowany: tekst widoczny, bez danych osobowych
- [ ] Bot Discord online na serwerze testowym, komenda `/factcheck` zarejestrowana (`DISCORD_GUILD_ID`)
- [ ] Klucze, tokeny i adresy administracyjne poza kadrem
- [ ] Każdy przykład wklejany z notatki, nie z pamięci
- [ ] Nagranie w rozdzielczości co najmniej 1080p, dźwięk sprawdzony
- [ ] Film opublikowany pod linkiem dostępnym dla jury, długość do 3:00 sprawdzona

## Plan B
- **Brak sieci:** pokazujemy nagranie.
- **Padnięty Discord:** scena 1:42–2:08 idzie przez adapter demonstracyjny (`POST /api/channels/demo`) z tym samym pytaniem w terminalu, a lektor mówi „drugi kanał”.
- **Awaria modułu wyszukiwania:** scenę ze zrzutem ekranu pokazujemy w trybie demonstracyjnym interfejsu. Przy awarii modelu lub bazy zostawiamy w kadrze komunikat o błędzie technicznym i nagrywamy scenę ponownie.

## Jeśli film przekroczy 3:00 (kolejność cięcia)
1. Zakończenie do 20 s. 2. Pętla informacji do 8 s. 3. Scena 1 do 15 s. 4. Scena 3 do 20 s. **Nie wycinamy** sceny z ukrytą instrukcją ani sceny z Discordem: pierwsza pokazuje odporność na manipulację, a druga spełnia warunek dwóch kanałów z briefu.
