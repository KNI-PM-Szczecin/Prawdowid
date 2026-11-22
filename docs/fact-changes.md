# Zmiany stanu faktycznego w korpusie demo

Lista najważniejszych zmian stanu prawnego i faktycznego, które obywatel może spotkać w nieaktualnej formie („UE liczy 28 państw”, „wiek emerytalny 67 lat”). Każdą zmianę opisują dosłowne fragmenty stron rządowych z `rag/app/data/seed_documents.json`, wgrywane automatycznie przy starcie `rag/`.
Dzięki nim system ma w korpusie zarówno stan obecny, jak i informację, co obowiązywało wcześniej, więc twierdzenie nieaktualne da się odróżnić od fałszywego na podstawie źródła, a nie wiedzy modelu.

Stan na: **22 listopada 2026 r.** (data pobrania stron).

## Zmiany i stan obecny

| Dziedzina | Wcześniej | Obecnie | Od kiedy | Źródło w korpusie |
|---|---|---|---|---|
| Liczba państw UE | 28 | 27 (wyjście Wielkiej Brytanii) | 1 lutego 2020 r. | [Ministerstwo Infrastruktury, 30.01.2020](https://www.gov.pl/web/infrastruktura/wyjscie-zjednoczonego-krolestwa-z-ue) (`seed:brexit-ue-27`) |
| Powszechny wiek emerytalny | stopniowo podwyższany do 67 lat bez względu na płeć (reforma z 2012 r.) | 60 lat kobiety, 65 lat mężczyźni | 1 października 2017 r. | [MRPiPS, 16.11.2016](https://www.gov.pl/web/rodzina/sejm-przywrocil-wiek-emerytalny), [MRPiPS, 02.10.2017](https://www.gov.pl/web/rodzina/twoja-emerytura-zmiany-od-1-pazdziernika), [NIST](https://archiwum.nist.gov.pl/wydarzenia/obnizenie-wieku-emerytalnego,781.html) (`seed:wiek-emerytalny-*`) |
| Polska w strefie Schengen | kontrole na granicach wewnętrznych | członek strefy Schengen | 21 grudnia 2007 r. | [Ministerstwo Funduszy i Polityki Regionalnej, 27.04.2026](https://funduszeeuropejskie.gov.pl/funduszowy-maj/aktualnosci-akcji-funduszowy-maj/europa-bez-granic/) (`seed:schengen-polska-2007`) |
| Bułgaria i Rumunia w Schengen | kontrole na granicach | pełni członkowie; granice lotnicze i morskie od 31 marca 2024 r., lądowe od 1 stycznia 2025 r. | 1 stycznia 2025 r. | [Europe Direct Zielona Góra (LUW), 03.01.2025](https://europedirect-zielonagora.lubuskie.uw.gov.pl/wiadomosci/103547/bulgaria-i-rumunia-dolaczaja-do-strefy-schengen) (`seed:schengen-bulgaria-rumunia-2025`) |
| Strefa euro | 20 państw | 21 państw (Bułgaria) | 1 stycznia 2026 r. | [Europe Direct Zielona Góra (LUW), 02.01.2026](https://europedirect-zielonagora.lubuskie.uw.gov.pl/wiadomosci/128913/euro-oficjalna-waluta-bulgarii) (`seed:euro-bulgaria-2026`) |
| Liczba członków NATO | 31 | 32 (Szwecja) | 7 marca 2024 r. | [MSZ, 07.03.2024](https://www.gov.pl/web/diplomacy/statement-of-the-ministry-of-foreign-affairs), [Stałe Przedstawicielstwo RP przy NATO, 03.04.2024](https://www.gov.pl/web/nato/spotkanie-ministrow-spraw-zagranicznych-nato) (`seed:nato-szwecja-*`) |
| Świadczenie wychowawcze | 500 zł (Rodzina 500+) | 800 zł (Rodzina 800+) | 1 stycznia 2024 r. | [KPRM, 07.08.2023](https://www.gov.pl/web/premier/ustawa-800plus-podpisana) (`seed:rodzina-800-plus`) |
| Minimalne wynagrodzenie | 4666 zł (2025) | 4806 zł, stawka godzinowa 31,40 zł | 1 stycznia 2026 r. | [Zielona Linia, 29.12.2025](https://zielonalinia.gov.pl/wynagrodzenie-minimalne-w-2026-1/) (`seed:placa-minimalna-2026`) |
| Kadencja rad gmin, powiatów i sejmików | 4 lata (1990–2018) | 5 lat; kadencja z 2023 r. jednorazowo przedłużona do 30 kwietnia 2024 r. | 2018 r. | [GUS, sdg.gov.pl, dane z 19.11.2026](https://sdg.gov.pl/statistics_glob/5-5-1/) (`seed:kadencja-samorzadu-5-lat`) |
| Podział administracyjny | dwustopniowy podział z 1975 r. | trójstopniowy, 16 województw | 1 stycznia 1999 r. | GUS (`seed:gus-podzial-administracyjny`, w korpusie wcześniej) |

Kwota 4666 zł pochodzi z tej samej strony Zielonej Linii (poza cytowanym fragmentem). Wartości „Wcześniej” bez cytatu w korpusie (20 państw strefy euro, 31 członków NATO) wynikają z kolejnych zmian w tabeli i nie są dowodem dla systemu. System cytuje wyłącznie fragmenty z `seed_documents.json`.

## Zasady wyboru i aktualizacji

- **Kryterium:** zmiana dotyczy wielu obywateli albo podstawowych faktów o państwie i UE, a jej stara wersja wciąż krąży w obiegu. Wybór nie odtwarza przypadków z `eval/cases.json`: część zmian pokrywa się z tematami eval (UE 27, wiek emerytalny, Schengen), dlatego wynik eval po tej zmianie trzeba czytać razem z przypadkami spoza tej listy.
- **Źródła:** wyłącznie domeny `gov.pl` z katalogu (`rag/app/data/sources_catalog.json`, wpis „Administracja rządowa RP”), typ `official`. Tekst to dosłowny fragment widocznej treści strony, bez skrótów i parafraz.
- **Daty:** `publishedAt` to data publikacji widoczna na stronie (gov.pl, Europe Direct) albo w metadanych (`article:published_time` na zielonalinia.gov.pl, „data aktualizacji danych” na sdg.gov.pl). Dla strony NIST bez daty publikacji przypięto datę wydarzenia opisanego w treści (konferencja KPRM 2 października 2017 r.), zgodnie z zasadą z `seed_urls.json`.
- **Aktualizacja:** gdy stan się zmienia (np. coroczna waloryzacja minimalnego wynagrodzenia), dodajemy nowy dokument z nową datą i nie usuwamy starego: starszy zostaje jako dowód tego, co obowiązywało wcześniej. Wiek źródła ocenia `agent/` (ostrzeżenie o materiale archiwalnym).
- **Wykluczenie:** dokument usuwamy, gdy strona zniknie, a treści nie da się potwierdzić w innym źródle urzędowym, albo gdy okaże się nieścisła.
