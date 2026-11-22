# Prezentacja PDF: zarys 12 slajdów

Limit: **12 slajdów** (`spec/brief.md` §4). Kolejność z briefu: problem, użytkownicy, architektura, demo, wyniki testów, ryzyka, dalsze kroki. Status: `[WDROŻONE]` jest w kodzie, `[ZAPLANOWANE]` nie, `[DO UZUPEŁNIENIA]` czeka na dane. Slajdu nie wolno opierać na funkcji, której nie ma w kodzie.

| # | Slajd | Treść | Dowód / grafika | Status |
|---|---|---|---|---|
| 1 | Tytuł | Prawdowid, hasło, zespół KNIPM, zadanie MSZ, data | logo, nazwa zespołu | |
| 2 | Problem | Fałszywe doniesienia krążą w komunikatorach szybciej niż je sprawdzamy. Płynny język modelu nie gwarantuje prawdy. Treści bywają prawdziwe, ale nieaktualne albo wyjęte z kontekstu | 1 liczba lub przykład z briefu | |
| 3 | Użytkownicy | Obywatel, także z niskimi kompetencjami cyfrowymi. Administrator/analityk (powtarzające się pytania bez odpowiedzi) | persony, 2 zdania | |
| 4 | Rozwiązanie | Sprawdzasz tak łatwo, jak wysyłasz wiadomość. Werdykt + źródła + granice wiedzy. Nie „sędzia prawdy” | schemat: zgłoszenie → twierdzenia (opinie jako „nie podlega weryfikacji”, podświetlenie w tekście) → dowody → werdykt | [WDROŻONE] pełny przepływ |
| 5 | Architektura | Preact / Go (backend, agent) / Python (rag) / PostgreSQL + Qdrant. Kanały oddzielone od logiki (WWW + adapter demonstracyjny; brief §5 dopuszcza adapter, bo organizator nie zapewnia kont, numerów ani kluczy do komunikatorów). Model wymienny | diagram z `CONTRACT.md` | [WDROŻONE] rag, agent, backend |
| 6 | Źródła i korpus | Urzędowe + wtórne + weryfikatorzy (Google Fact Check) + katalog kampanii (EUvsDisinfo) + akty z Dziennika Ustaw + uzupełnianie luk z gov.pl. Licencje, kwalifikacja, reguły wykluczania, wygaszanie, minimum 100 dok. / 10 domen | tabela z `sources_catalog.json` | [WDROŻONE] mechanizmy, [DO UZUPEŁNIENIA] liczby z `GET /sources` |
| 7 | Jak decydujemy | Reguły werdyktu i wstrzymania się (`CONTRACT.md` §4): cytat obowiązkowy i sprawdzany dosłownie, zgodność liczb, ocena weryfikatora tylko tego samego twierdzenia, wydarzenia bieżące. Domena nigdy nie jest werdyktem | tabela reguł | [WDROŻONE] `agent/rules.go` |
| 8 | Bezpieczeństwo i prywatność | Prompt injection (dane ≠ instrukcje, wykrywanie w zgłoszeniu i stronie), tokeny, maskowanie danych osobowych, retencja 30 dni, usuwanie sesji, limit żądań | schemat obrony | [WDROŻONE] injection, tokeny, maskowanie, retencja, usuwanie; [DO UZUPEŁNIENIA] miejsce przetwarzania (OpenAI i Google Fact Check poza EOG, bez deklaracji hostingu w EOG) |
| 9 | Demo | 4 ekrany: potwierdzone ze źródłem, wstrzymanie się, zrzut ekranu sprawdzony przez OCR (scenariusz F, ograniczenia o OCR i dacie na obrazie), odpowiedź adaptera demonstracyjnego (`POST /api/channels/demo`, tekst jak z komunikatora) z tym samym wynikiem | zrzuty ekranu i okno terminala | [WDROŻONE] funkcje, [DO UZUPEŁNIENIA] zrzuty |
| 10 | Wyniki testów | Miary z briefu z celami: macro-F1 ≥ 0,75, cytowania 95% / 85%, wstrzymanie 80%, injection 90%, czas ≤ 30 s, koszt 100 testów deklarowany i zmierzony (brief §6 wymaga obu liczb). Dodatkowo benchmark zewnętrzny (`eval/BENCHMARK.md`) | tabela z raportu `eval/reports` | [DO UZUPEŁNIENIA] raport |
| 11 | Ryzyka i ograniczenia | Halucynacje, stronniczość źródeł, prywatność, prompt injection, dostępność, nadużycia. Czego nie obsługujemy: wideo i dźwięk, wyszukiwanie odwrotne obrazu (OCR zrzutów jest, bez oceny autentyczności), URL w środku tekstu, materiał spoza korpusu nie jest rozpoznawany (dopasowanie po adresie albo tytule i dacie), sprawy tylko z WWW, bot Discord | tabela z `docs/draft.md` i lista z `opis.md` | [WDROŻONE] analiza |
| 12 | Koszt i dalsze kroki | Koszt 1000 zapytań, zależności i miejsce przetwarzania, pilotaż z MSZ (zamknięty korpus, kolejka ekspercka), kanały, języki | oś czasu 4–6 tygodni z briefu §9 | [DO UZUPEŁNIENIA] koszt |

Do rozważenia w limicie 12 slajdów (kosztem połączenia 2 i 3 albo 11 i 12): osobny slajd o pętli moderatora (sprawy dla twierdzeń bez dowodów, grupowanie parafraz, `recommended` vs `forwarded`, lista `GET /api/admin/cases`) i o benchmarku z `eval/BENCHMARK.md` (zewnętrzny zbiór fact-checków, sędzia LLM, porównanie A/B, przegląd ręczny).

## Zasady
- Jeden komunikat na slajd, wyniki liczbowe tylko z prawdziwego przebiegu `eval/` (bez ręcznego poprawiania).
- Dane osobowe i klucze na zrzutach: zamaskować.
- Przy każdym ograniczeniu napisać wprost, czego system nie obsługuje (wymóg briefu).
