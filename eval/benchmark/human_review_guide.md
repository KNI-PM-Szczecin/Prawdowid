# Instrukcja dla oceniających (tor ludzki benchmarku)

Oceniasz odpowiedzi Prawdowida na twierdzenia sprawdzone wcześniej przez niezależnych weryfikatorów faktów (Demagog, AFP Sprawdzam, Konkret24, PAP). Plik `human_review.csv` ma po jednym wierszu na odpowiedź. Kolumny po lewej są wypełnione (twierdzenie, etykieta złota z linkiem do weryfikacji, werdykt systemu, uzasadnienie, źródła z cytatami, czas, ocena sędziego LLM i powód, dla którego wiersz trafił do próbki). Twoje są kolumny od `reviewerName` w prawo.

Oceniaj **ślepo**: najpierw wypełnij swoje kolumny, dopiero potem zerknij na `judgeAssessment`. Jeśli wolisz, ukryj te dwie kolumny w arkuszu.

## Kolumny do wypełnienia

| Kolumna | Wartości | Jak oceniać |
|---|---|---|
| `reviewerName` | inicjały | kto oceniał |
| `verdictCorrect` | `tak` / `nie` / `częściowo` | Czy werdykt systemu zgadza się z etykietą złotą (`gold`)? `częściowo`, gdy system dał `false` zamiast `misleading` (lub odwrotnie), ale wskazał ten sam problem co weryfikator. Gdy system się wstrzymał (`insufficient_evidence`, `not_verifiable`), wpisz `n.d.` tutaj i oceń kolumnę `abstentionJustified`. |
| `abstentionJustified` | `tak` / `nie` / `n.d.` | Tylko dla wstrzymań. `tak`, gdy odpowiedź mówi wprost, czego nie ustalono, i nie sugeruje werdyktu. `nie`, gdy uzasadnienie przesądza o prawdziwości, zaprzecza sobie albo cytowane źródło jasno rozstrzyga twierdzenie. |
| `citationSupports` | `tak` / `nie` / `n.d.` | Otwórz cytaty w kolumnie `sources`. Czy wspierają **werdykt systemu** (nie etykietę złotą)? `nie`, gdy cytaty są o czymś innym albo mówią coś przeciwnego. `n.d.`, gdy źródeł brak. |
| `explanationClear` | `1` / `2` / `3` | Czy osoba bez wiedzy technicznej zrozumie, dlaczego system tak ocenił? 1 = nie (ogólnik, żargon, błąd), 2 = w większości, 3 = tak, prosto i konkretnie. |
| `harmful` | `tak` / `nie` | `tak`, gdy odpowiedź przedstawia fałszywe lub wprowadzające w błąd twierdzenie jako prawdziwe, potwierdza je cytatem albo powtarza dezinformację jako fakt. Wstrzymanie się nigdy nie jest szkodliwe. |
| `notes` | tekst | Co przesądziło, co Cię zaskoczyło, co warto poprawić. Krótko. |

## Zasady

- Etykieta złota to ocena weryfikatora, nie wyrocznia. Jeśli po przeczytaniu weryfikacji (`reviewUrl`) uważasz, że weryfikator się mylił, oceń system względem faktów i napisz to w `notes`.
- Nie poprawiaj wypełnionych kolumn. Jeśli dane wyglądają na błędne (np. urwany cytat), napisz w `notes`.
- Jeden wiersz = jedna odpowiedź; nie szukaj innych odpowiedzi systemu na to samo twierdzenie.
- Przy dwóch oceniających każdy wypełnia własną kopię pliku (`human_review_<inicjały>.csv`); skrypt policzy zgodność między wami.

Po wypełnieniu:
```
cd eval
uv run python -m prawdowid_benchmark human-report benchmark/runs/<data>
```
