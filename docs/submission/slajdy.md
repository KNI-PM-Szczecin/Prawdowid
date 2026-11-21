# Prezentacja PDF: zarys 12 slajdów

Limit: **12 slajdów** (`spec/brief.md` §4). Kolejność z briefu: problem, użytkownicy, architektura, demo, wyniki testów, ryzyka, dalsze kroki. Status: `[WDROŻONE]` jest w kodzie, `[ZAPLANOWANE]` nie, `[DO UZUPEŁNIENIA]` czeka na dane. Slajdu nie wolno opierać na funkcji, której nie ma w kodzie.

| # | Slajd | Treść | Dowód / grafika | Status |
|---|---|---|---|---|
| 1 | Tytuł | Prawdowid, hasło, nazwa zespołu, zadanie MSZ, data | logo, nazwa zespołu | [DO UZUPEŁNIENIA] nazwa |
| 2 | Problem | Fałszywe doniesienia krążą w komunikatorach szybciej niż je sprawdzamy. Płynny język modelu nie gwarantuje prawdy. Treści bywają prawdziwe, ale nieaktualne albo wyjęte z kontekstu | 1 liczba lub przykład z briefu | |
| 3 | Użytkownicy | Obywatel, także z niskimi kompetencjami cyfrowymi. Administrator/analityk (powtarzające się pytania bez odpowiedzi) | persony, 2 zdania | |
| 4 | Rozwiązanie | Sprawdzasz tak łatwo, jak wysyłasz wiadomość. Werdykt + źródła + granice wiedzy. Nie „sędzia prawdy” | schemat: zgłoszenie → twierdzenia → dowody → werdykt | [ZAPLANOWANE] pełny przepływ |
| 5 | Architektura | React / Go (backend, agent) / Python (rag) / PostgreSQL + Qdrant. Kanały oddzielone od logiki. Model wymienny | diagram z `CONTRACT.md` | [WDROŻONE] rag, [ZAPLANOWANE] agent i backend |
| 6 | Źródła i korpus | Urzędowe + wtórne + weryfikatorzy (Google Fact Check) + katalog kampanii (EUvsDisinfo). Licencje, kwalifikacja, wygaszanie, minimum 100 dok. / 10 domen | tabela z `sources_catalog.json` | [WDROŻONE] mechanizmy, [DO UZUPEŁNIENIA] liczby |
| 7 | Jak decydujemy | Reguły werdyktu i wstrzymania się (`CONTRACT.md` §4): cytat obowiązkowy, wyjaśnialna rozbieżność, ocena weryfikatora, wydarzenia bieżące. Domena nigdy nie jest werdyktem | tabela reguł | [ZAPLANOWANE] w `agent/` |
| 8 | Bezpieczeństwo i prywatność | Prompt injection (dane ≠ instrukcje), tokeny, maskowanie danych osobowych, retencja, usuwanie sesji, hosting w EOG | schemat obrony | [WDROŻONE] injection i tokeny, [ZAPLANOWANE] reszta |
| 9 | Demo | 3 ekrany: potwierdzone ze źródłem, wstrzymanie się, odpowiedź na Discordzie z tym samym wynikiem | zrzuty ekranu | [ZAPLANOWANE] |
| 10 | Wyniki testów | Miary z briefu z celami: macro-F1 ≥ 0,75, cytowania 95% / 85%, wstrzymanie 80%, injection 90%, czas ≤ 30 s, koszt | tabela z raportu `eval/reports` | [DO UZUPEŁNIENIA] raport |
| 11 | Ryzyka i ograniczenia | Halucynacje, stronniczość źródeł, prywatność, prompt injection, dostępność, nadużycia. Co nie działa | tabela z `docs/draft.md` | [WDROŻONE] analiza |
| 12 | Koszt i dalsze kroki | Koszt 1000 zapytań, zależności i miejsce przetwarzania, pilotaż z MSZ (zamknięty korpus, kolejka ekspercka), kanały, języki | oś czasu 4–6 tygodni z briefu §9 | [DO UZUPEŁNIENIA] koszt |

## Zasady
- Jeden komunikat na slajd, wyniki liczbowe tylko z prawdziwego przebiegu `eval/` (bez ręcznego poprawiania).
- Dane osobowe i klucze na zrzutach: zamaskować.
- Przy każdym ograniczeniu napisać wprost, czego system nie obsługuje (wymóg briefu).
