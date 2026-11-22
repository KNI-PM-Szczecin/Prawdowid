# Film demonstracyjny: skrypt na 3 minuty

Limit: **3 minuty**, link do filmu (`spec/brief.md` §4). Nagraj ekran i głos. Plan B na awarię sieci lub kont: nagranie jest też zapasowym demo na scenie. Scenariusze odpowiadają przypadkom A, D, E, G z `spec/mentor-test-scenarios.md`. Dane demo muszą być fikcyjne lub publiczne, bez danych osobowych i kluczy.

| Czas | Co widać | Co mówimy |
|---|---|---|
| 0:00–0:20 | Zrzut z komunikatora z podejrzanym doniesieniem | „Dostajesz wiadomość, nie wiesz, czy to prawda. Prawdowid sprawdza ją tak łatwo, jak ją wysłać.” |
| 0:20–1:10 | Wklejamy twierdzenie z odpowiedzią Demagoga (scenariusz A). Wynik: werdykt, uzasadnienie, siła podstawy, źródło z cytatem i linkiem | „Werdykt wynika z jawnych przesłanek. Źródła są osobno od interpretacji modelu, każde z tytułem, wydawcą, datą i linkiem.” |
| 1:10–1:35 | Twierdzenie bez dowodów (scenariusz D, np. lokalna zmiana w Limanowej). Wynik: „brak wystarczających dowodów” + co trzeba ustalić | „Gdy nie ma dowodów, nie zgadujemy. Mówimy, czego nie udało się ustalić.” |
| 1:35–2:05 | Wklejamy adres strony z ukrytą instrukcją „zignoruj poprzednie instrukcje” (przypadek E07, strona demo `/demo/injection.html` serwowana przez front), nie instrukcję wpisaną w pole. Wynik poprawny, próba policzona w `injectionAttempts` i zapisana w logu | „Instrukcje ze stron źródłowych są danymi, nie poleceniami. System je ignoruje i zapisuje próbę.” |
| 2:05–2:35 | To samo pytanie wysłane przez adapter demonstracyjny (okno terminala, `curl -X POST /api/channels/demo -d '{"text": "..."}'`), odpowiedź tekstowa jak z komunikatora: ten sam werdykt i to samo źródło (scenariusz G) | „Strona i drugi kanał używają tej samej logiki, więc wynik jest ten sam.” |
| 2:35–3:00 | Slajd z architekturą i tabelą wyników z `eval/`, na końcu ograniczenia i pilotaż z MSZ | „Mierzymy się według miar z zadania i uczciwie pokazujemy ograniczenia. Dalej: pilotaż na zamkniętym korpusie z kolejką eksperta.” |

## Przed nagraniem
- [ ] Demo działa end-to-end z czystego klona jedną komendą
- [ ] Dane seed przygotowane, klucze poza kadrem (bot Discord nie jest wdrożony, drugi kanał to adapter demonstracyjny)
- [ ] Nie wdrażać `rag/` tuż przed nagraniem (ok. minuta rozgrzewania modeli kończy zapytania `technical_error`)
- [ ] Wersja offline lub mock na wypadek słabego Wi-Fi
- [ ] Film wgrany pod link dostępny dla jury, długość ≤ 3:00 sprawdzona
