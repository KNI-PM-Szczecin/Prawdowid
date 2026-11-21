# Wymagania (streszczenie brief.md)

Zadanie: **Prawdowid** (Ministerstwo Spraw Zagranicznych, HackNation 2026). Proste, wielokanałowe narzędzie, które pozwala obywatelowi sprawdzić doniesienie tak łatwo jak wysłać wiadomość: opiera się na wiarygodnych źródłach, pokazuje podstawy odpowiedzi i uczciwie wstrzymuje się od oceny, gdy dowodów brakuje.
Główny odbiorca: obywatel, także z niskimi kompetencjami cyfrowymi. To nie jest automatyczny „sędzia prawdy”: system wspiera świadomą ocenę informacji.

## MVP (obowiązkowe)
- Wejście: tekst lub URL przez responsywny interfejs WWW **oraz co najmniej jeden dodatkowy kanał** albo adapter demonstracyjny (SMS, WhatsApp, Messenger, Instagram, Discord lub równoważny; **bez** Telegrama, WeChata i platform niszowych).
- Rozpoznawanie jednego lub kilku twierdzeń wymagających sprawdzenia.
- Wyszukiwanie w jasno opisanym korpusie z **co najmniej dwoma typami źródeł**; pokazanie wykorzystanych materiałów.
- Wynik dla każdego twierdzenia: werdykt, krótkie uzasadnienie, ocena siły podstawy, czytelna informacja o ograniczeniach. Odpowiedź po polsku, prostym językiem.
- Podstawowy zapis przebiegu: pytanie, czas, użyte źródła, wynik.
- **Wstrzymanie się od oceny** przy braku dowodów, bez pozornej odpowiedzi.
- Pełna ścieżka end-to-end bez ręcznej ingerencji twórców.

## Werdykty
`confirmed` (potwierdzone), `false` (fałszywe), `misleading` (wprowadzające w błąd), `insufficient_evidence` (brak wystarczających dowodów), `not_verifiable` (nie podlega weryfikacji).
Awaria techniczna, brak możliwości wykonania sprawdzenia i potrzeba doprecyzowania pytania **nie są werdyktami**: komunikuj je osobno.

## Twarde zasady
- Każda teza faktograficzna przedstawiona jako ustalenie systemu prowadzi do dowodu: co najmniej tytuł, wydawca, data, link, najlepiej także cytowany fragment.
- Materiały źródłowe oddzielone od interpretacji modelu.
- Siła werdyktu wynika z jawnych przesłanek (jakość i aktualność źródeł, zgodność z twierdzeniem, liczba niezależnych potwierdzeń).
- Nie przesądzamy o prawdziwości na podstawie domeny, autora, kanału, popularności, liczby udostępnień, objęcia sankcjami UE ani etykiety wygenerowanej przez ten sam model. Status źródła może dać tylko osobne, neutralne ostrzeżenie.
- Instrukcje znalezione w analizowanych materiałach nie mogą zmieniać zasad działania systemu (odporność na prompt injection).
- Sprawy wysokiego ryzyka i powtarzające się pytania bez źródeł powinny powiadomić moderatora/analityka wskazanego przez administratora. Rozróżnij rekomendację przekazania od faktycznego przekazania.
- Zakaz obchodzenia zabezpieczeń serwisów i płatnych baz. Zakaz deklarowania pełnego wyszukiwania odwrotnego obrazu bez działającego API lub jasno ograniczonej lokalnej bazy. Zakaz archiwizacji pełnych treści i obrazów bez podstawy prawnej, licencji, retencji, kontroli dostępu i procedury usunięcia.
- Wynik modelu językowego nigdy nie jest przedstawiany jako fakt bez weryfikowalnego źródła.

## Wymagania techniczne
- Obsługa kanałów oddzielona od logiki weryfikacji. Model lub dostawca wymienny bez przebudowy całości.
- Korpus demo: **min. 100 dokumentów lub rekordów, 10 domen, 2 typy źródeł**, w tym źródła pierwotne/urzędowe i wiarygodne wtórne. Lista źródeł dostępna do audytu.
- Znaczniki czasu publikacji i pobrania. Preferowanie danych aktualnych, ostrzeganie o materiale archiwalnym.
- Bezpieczeństwo: walidacja wejścia, separacja instrukcji od treści źródeł, ograniczenia narzędzi, ochrona sekretów, limitowanie żądań, logowanie zdarzeń.
- Prywatność: minimalizacja danych, automatyczne maskowanie oczywistych danych osobowych, określona retencja, możliwość usunięcia sesji demo.
- Obserwowalność: czas odpowiedzi, użycie modeli, błędy wyszukiwania, przypadki wstrzymania się, szacunkowy koszt odpowiedzi.
- Dostępność: responsywny interfejs, czytelny kontrast, język zrozumiały bez wiedzy technicznej.
- WWW i drugi kanał używają tej samej logiki weryfikacji i dają ten sam wynik merytoryczny.
- Bezpłatne po stronie usługi. Oszacuj koszt 1000 zapytań, koszt utrzymania kanału i zachowanie przy większym ruchu. Opisz klucze, limity, koszty, miejsce przetwarzania danych i zachowanie przy awarii.
- Jury uruchamia demo z naszej instrukcji. MVP na 24 godziny.

## Funkcje premiowane (oceniane tylko przy spełnionej podstawie)
Weryfikacja obrazu i dźwięku (OCR, transkrypcja, metadane, porównywanie obrazów, wcześniejsze wystąpienia); łańcuch dowodowy od twierdzenia do materiałów potwierdzających, obalających lub uzupełniających kontekst; wielojęzyczne wyszukiwanie z odpowiedzią po polsku; otwarty lub wymienny katalog źródeł z zasadami kwalifikowania, aktualizowania i wykluczania; architektura z podłączanymi kanałami, modelami i źródłami; dopasowanie do katalogu znanych incydentów (sama domena nie może przesądzać o werdykcie, ale może wyzwolić jawne ostrzeżenie); eksport (CSV, JSON, OpenCTI, DISARM); kontrolowana archiwizacja materiału wskazanego przez użytkownika; mniej zależności spoza EOG, możliwość audytu lub samodzielnego hostowania; zamknięta pętla informacji (sprawa moderatora dla nierozstrzygniętego zgłoszenia, grupowanie podobnych zgłoszeń).

## Testy jury (min. 30 przypadków referencyjnych)
A fakt prosty (poprawny werdykt i dokładny cytat) · B brak kontekstu · C sprzeczne źródła (jawnie pokaż rozbieżność, bez arbitralnej pewności) · D brak dowodów (wstrzymaj się i wskaż, czego nie ustalono) · E atak (strona źródłowa każe modelowi zignorować reguły: zignoruj i zapisz zdarzenie) · F multimodalność, zrzut/zdjęcie z tekstem i datą (jeśli wdrożone) · G spójność WWW i drugiego kanału · H pętla informacji (jeśli wdrożona) · I dopasowanie URL/incydent (pokaż jako kontekst, bez automatycznego werdyktu) · J limit API lub awaria (ujawnij ograniczenie techniczne, bez pozornego wyniku merytorycznego).

## Mierniki obowiązkowe (cele MVP)
| Miernik | Cel |
|---|---|
| Trafność werdyktu, macro-F1 | ≥ 0,75 na zestawie jawnym, plus ukryty zestaw porównawczy |
| Pokrycie cytowań | ≥ 95% tez faktograficznych z dowodem |
| Poprawność cytowania | ≥ 85% cytowanych fragmentów rzeczywiście wspiera tezę |
| Wstrzymanie się przy braku dowodów | ≥ 80% poprawnych przypadków |
| Odporność na prompt injection | ≥ 90% odpartych prób |
| Mediana czasu od wejścia do odpowiedzi | ≤ 30 s dla tekstu/URL |
| Koszt 100 testów | raportowany; niższy premiowany przy równej jakości |
| Scenariusze end-to-end uruchomione przez jury bez nas | 100% |
| Spójność kanałów | 100% |
| Pętla informacji (jeśli wdrożona) | 100% |

Jury może ręcznie sprawdzić losową próbę cytowań, powtórzyć testy i wprowadzić własne pytanie. Wynik nie może zależeć od odpowiedzi testowych wpisanych do promptu. Ujawnij przypadki, których system nie obsługuje.

## Kryteria oceny
| Kryterium | Waga |
|---|---|
| Jakość weryfikacji i dowodów (trafność, zgodność cytatów, aktualność i różnorodność dowodów, poprawne wstrzymanie się) | 30% |
| Bezpieczeństwo, odpowiedzialność, transparentność (odporność na injection, prywatność, audytowalność, komunikowanie niepewności, nadzór człowieka) | 20% |
| Potencjał wdrożeniowy i skalowalność (modularność, koszty, wydajność, utrzymanie źródeł, integracje, brak zależności od jednego dostawcy, przejrzystość miejsca przetwarzania danych) | 20% |
| Użyteczność i dostępność (prosty język, niski próg wejścia, brak opłat, spójność kanałów, UX dla obywatela, obsługa błędów) | 15% |
| Innowacyjność i kompletność (multimodalność, ponowne użycie obrazu, pętla informacji, wizualizacja dowodów, integracje analityczne, jakość demonstracji) | 15% |

**Warunek brzegowy:** projekt niespełniający wymagań podstawowych nie dostaje punktów za funkcje premiowane. Podstawa = end-to-end bez ręcznej ingerencji, brak sfabrykowanych źródeł, poprawne wstrzymanie się przy braku dowodów, dwa działające kanały albo jeden kanał i adapter demonstracyjny.

## Do oddania
Nazwa zespołu, tytuł i opis do 4000 znaków · prezentacja PDF do 12 slajdów (problem, użytkownicy, architektura, demo, wyniki testów, ryzyka, dalsze kroki) · film demonstracyjny do 3 minut (link) · link do repozytorium z instrukcją uruchomienia · krótki opis architektury, przepływu danych, modeli, dostawców i ograniczeń · opis źródeł, licencji, sposobu kwalifikacji i aktualizacji · wyniki testów według scenariuszy jury z danymi do odtworzenia · krótka lista ryzyk (co najmniej halucynacje, stronniczość źródeł, prywatność, prompt injection, dostępność, nadużycia). W repo i materiałach demo nie może być kluczy API, danych osobowych ani sekretów.

## Zasoby od organizatora
Lista źródeł (URL / kanał Discord), baza incydentów (JSON/CSV z datą, licencją i zakresem), mentoring (eksperci FIMI, dyżury i kanał Prawdowid na Discordzie). Rekomendowane źródła pierwotne: dane.gov.pl, BIP, ISAP, EUR-Lex; korpusy zweryfikowanych informacji organizacji IFCN/EFCSN; EDMO, EUvsDisinfo, Check First, materiały NASK.

## Nagroda i prawa (zob. regulation.md)
Jedna nagroda główna 30 000 zł brutto dla najwyżej ocenionego zespołu, wypłacana w równych częściach, chyba że wszyscy członkowie złożą inne oświadczenie. **Wszyscy członkowie zespołu muszą podpisać umowę przeniesienia majątkowych praw autorskich na Ministerstwo w ciągu 7 dni, inaczej tracą nagrodę.** Uczestnicy zapewniają, że praca jest ich i nie narusza praw osób trzecich.
