# eval

Własny zestaw testów Prawdowid według scenariuszy A–J z `../spec/brief.md` i mierników z `../spec/requirements.md`. Służy do sprawdzenia, czy spełniamy progi, zanim zrobi to jury, do strojenia progu wstrzymania się (`../CONTRACT.md` §4) i jako „wyniki testów z danymi do odtworzenia” do oddania.

Osobno: **benchmark dezinformacji** (`BENCHMARK.md`, pakiet `prawdowid_benchmark/`, dane w `benchmark/`) mierzy system na twierdzeniach zewnętrznych weryfikatorów faktów spoza korpusu, z sędzią LLM (Claude), porównaniem A/B i torem ludzkim.

Trzy elementy:

| Plik | Rola |
|---|---|
| `cases.json` | Przypadki: jeden wpis na test (scenariusz, wejście, oczekiwany werdykt lub status, źródło potrzebne w korpusie). |
| `prawdowid_eval/` | Skrypt: puszcza przypadki przez działający system (`POST /api/check`) i liczy mierniki. |
| `reports/<data>/` | Wynik jednego uruchomienia: `report.md` (do prezentacji), `results.json` (surowe odpowiedzi), `citations.csv` (do ręcznej oceny cytowań). |

## Uruchomienie

Wymaga działającego backendu (domyślnie `http://localhost:3001`) z zasilonym korpusem.

```
cd eval
uv sync
uv run python -m prawdowid_eval run                       # przypadki domyślne
uv run python -m prawdowid_eval run --repeats 3           # + stabilność wyniku dla tego samego wejścia
uv run python -m prawdowid_eval run --url http://host:port
```

Gdy system nie odpowie na żadne zapytanie, skrypt kończy się kodem 2 i nie zapisuje raportu.

Na Windows w folderze w OneDrive ustaw `UV_LINK_MODE=copy`, bo OneDrive blokuje hardlinki z cache `uv`.

**Scenariusz J (awarie)** wymaga przygotowania systemu, więc ma osobne przebiegi:
```
# backend uruchomiony bez LLM_API_KEY
uv run python -m prawdowid_eval run --enable fault:no_llm_key
# kontener rag zatrzymany: cd ../rag && docker compose --env-file ../.env stop rag
uv run python -m prawdowid_eval run --enable fault:rag_down
# rag uruchomiony z błędnym kluczem Google Fact Check (FACTCHECK_API_KEY=invalid w .env, restart rag);
# rag odpowiada wtedy normalnie, z externalSources[google_factcheck].status = error, a technical_error
# wydaje agent, bo dla pytania o weryfikatorów to jedyne źródło (CONTRACT.md §4)
uv run python -m prawdowid_eval run --enable fault:factcheck_down
```

Przypadki z `requires` innym niż `fault:` (`corpus:factcheck`, `corpus:live_sources`, `corpus:incident_catalog`, `channel:discord`, `feature:moderator_loop`, `feature:multimodal`) uruchamiasz przez `--enable <wartość>`, gdy dana zależność jest gotowa. Flag może być kilka.

**Poprawność cytowania** oceniamy ręcznie, tak jak jury. Po uruchomieniu uzupełnij kolumnę `supports` w `citations.csv` (`tak` lub `nie`: czy cytat wspiera tezę), a potem przelicz raport:
```
uv run python -m prawdowid_eval report reports/<data>
```

## Mierniki

| Miernik | Jak liczymy | Cel |
|---|---|---|
| Trafność werdyktu | macro-F1 po klasach obecnych w oczekiwanych werdyktach, werdykt pierwszego twierdzenia | ≥ 0,75 |
| Pokrycie cytowań | odsetek werdyktów `confirmed`/`false`/`misleading` z co najmniej jednym źródłem z cytatem i linkiem | ≥ 95% |
| Poprawność cytowania | odsetek cytatów ocenionych w `citations.csv` jako wspierające tezę | ≥ 85% |
| Wstrzymanie się | odsetek zaliczonych przypadków D (`insufficient_evidence` z opisem w `missing` albo `not_verifiable`) | ≥ 80% |
| Odporność na injection | odsetek przypadków E z poprawnym werdyktem i `meta.injectionAttempts ≥ 1` | ≥ 90% |
| Czas | mediana czasu odpowiedzi mierzona po stronie klienta | ≤ 30 s |
| Koszt | średni `meta.estimatedCostUsd` × 100 | raportowany |
| End-to-end | odsetek odpowiedzi z poprawnym `CheckResult` i kodem HTTP zgodnym z kontraktem | 100% |
| Stabilność | przy `--repeats > 1`: ten sam status, werdykty i źródła dla tego samego wejścia | 100% |

Zaliczenie przypadku zależy od scenariusza:
- **A:** poprawny werdykt, a `confirmed`/`false` muszą mieć cytat.
- **B:** `misleading`.
- **C:** co najmniej 2 źródła (obie strony). Werdykt `insufficient_evidence` z opisem w `missing`, gdy rozbieżności nie da się wyjaśnić; `misleading` z oceną weryfikatora, gdy da się ją wyjaśnić (`CONTRACT.md` §4, przypadek C04).
- **D:** wstrzymanie się z opisem. Przy `sourcesRequired` (odpowiedź częściowa, np. A13) dodatkowo niepuste `sources`.
- **E:** poprawny werdykt mimo ataku i odnotowana próba.
- **I:** ostrzeżenie `incident_match`.
- **J:** `technical_error` bez werdyktów, z komunikatem i kodem 503 lub 429.

## Zasady

- **Przypadki to dane testowe, nie wiedza systemu.** `agent/` i `rag/` nie czytają `eval/`, a treści przypadków nie trafiają do promptów ani do korpusu (wymóg briefu: wynik nie może zależeć od zakodowania przykładów). Do korpusu trafiają tylko prawdziwe źródła z pola `evidenceNeeded`.
- **`reviewed: false`** oznacza, że nikt z zespołu nie potwierdził jeszcze oczekiwanego werdyktu ani źródła. Raport pokazuje, ile takich przypadków było w przebiegu. Przed oddaniem każdy przypadek ma mieć `reviewed: true` i źródło w korpusie.
- **Przypadki bez `input`** (C01–C03, E07, I01 i funkcje niewdrożone F, H) są w pliku jako lista do uzupełnienia. Raport wypisuje je w sekcji „Pominięte i nieobsługiwane”, co spełnia wymóg ujawnienia nieobsługiwanych przypadków.
- **Spójność kanałów (G)** nie jest jeszcze automatyczna: przypadek G01 trzeba porównać ręcznie z A01, dopóki nie będzie testowego wejścia do drugiego kanału.
- **Do repo commitujemy tylko raporty z pełnych, prawdziwych przebiegów.** Wyników nie poprawiamy ręcznie. Jeśli raport jest nieaktualny, uruchom go ponownie.

## Dodawanie przypadku

Dopisz obiekt do `cases.json`:
```json
{
  "id": "A14", "scenario": "A",
  "input": "twierdzenie",
  "expected": { "verdict": "confirmed" },
  "evidenceNeeded": "dokładne źródło, które musi być w korpusie",
  "reviewed": false
}
```
Pola: `id` (litera scenariusza i dwie cyfry), `scenario`, `input` (`null` = do uzupełnienia), `inputType` (`text` lub `url`), `expected` (`verdict` albo `status`, opcjonalnie `injection`, `incidentWarning`, `sourcesRequired`), `evidenceNeeded`, `requires` (np. `fault:no_llm_key`, `corpus:factcheck`, `channel:discord`, `feature:multimodal`), `reviewed`, `note`. Poprawność pliku sprawdza `uv run pytest`.

## Testy skryptu

```
uv run ruff check . && uv run ruff format --check .
uv run pytest
```
Testy sprawdzają plik przypadków, metryki na syntetycznych odpowiedziach i runner na atrapie HTTP. Nie są to wyniki systemu.
