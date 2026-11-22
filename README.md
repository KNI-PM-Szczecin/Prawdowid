# Prawdowid

**Sprawdź doniesienie tak łatwo, jak wysłać wiadomość.**

![Go](https://img.shields.io/badge/Go-backend%20i%20agent-00ADD8?logo=go&logoColor=white)
![Python](https://img.shields.io/badge/Python-rag-3776AB?logo=python&logoColor=white)
![Preact](https://img.shields.io/badge/Preact-frontend-673AB8?logo=preact&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)
![WCAG](https://img.shields.io/badge/dostępność-WCAG%202.1%20AA-2E7D32)

[Na żywo](#sprawdź-na-żywo) · [Jak to działa](#jak-to-działa) · [Źródła](#źródła) · [Wyniki testów](#wyniki-testów) · [Uruchomienie](#uruchomienie)

Wklejasz tekst albo link. Prawdowid wyodrębnia twierdzenia, szuka ich w wiarygodnych źródłach
i pokazuje werdykt z uzasadnieniem, siłą podstawy i cytatem. Gdy dowodów brakuje, uczciwie
wstrzymuje się od oceny.

Prototyp na **HackNation 2026** dla zadania **Ministerstwa Spraw Zagranicznych**.

## Sprawdź na żywo

- **Strona WWW:** <https://testdomain07.com> (bez logowania)
- **Bot Discord:** <https://discord.gg/KZquUu47t>, komenda `/factcheck`

Oba kanały wołają tę samą logikę, więc dają ten sam wynik.

![Strona główna](docs/screenshots/home.png)

| Wynik sprawdzenia | Dostępność |
| --- | --- |
| ![Wynik](docs/screenshots/result.png) | ![Dostępność](docs/screenshots/accessibility.png) |

## Jak to działa

```text
tekst / link / zrzut ekranu
        │
   front (Preact) ──► backend Go ──► agent Go ──► rag (Python) ──► PostgreSQL + pgvector
                      kanały, limity  twierdzenia,  hybrydowe
                      logi, moderator werdykt       wyszukiwanie
```

- **Pięć werdyktów:** prawda, fałsz, wprowadza w błąd, brak dowodów, nie podlega weryfikacji.
  Awaria i niejasne pytanie to osobne statusy, nigdy werdykty.
- **Każdy dowód ma źródło:** tytuł, wydawca, daty, licencja, link i cytat.
  Ocena nie wynika z domeny ani autora.
- **Prompt injection to dane, nie instrukcje:** próby są wykrywane i logowane.
- **Prywatność:** maskowanie danych osobowych, retencja 30 dni, usuwanie sesji demo.
- **Model wymienny:** jeden interfejs nad dostawcą (OpenAI albo lokalny model).

## Źródła

Korpus: **350 dokumentów z 34 domen** plus katalog **203 spraw EUvsDisinfo** (tylko kontekst,
nigdy werdykt). Pełna lista do audytu: [`/api/sources`](https://testdomain07.com/api/sources),
[`/api/sources/catalog`](https://testdomain07.com/api/sources/catalog),
[`/api/sources/external`](https://testdomain07.com/api/sources/external).

Na żywo: Google Fact Check, wyszukiwarka gov.pl, Wikipedia (tylko po linki do źródeł),
Odyseusz MSZ, Wikidata. W tle: EUvsDisinfo, RSS policji, strony seed, Dziennik Ustaw, scraper zespołu.
Szczegóły: [`rag/README.md`](rag/README.md).

## Wyniki testów

44 przypadki ze scenariuszy A–J (orientacyjnie, bez przeglądu człowieka):

| Miernik | Wynik | Cel |
|---|---|---|
| Trafność werdyktu (macro-F1) | 0.70 | ≥ 0.75 |
| Pokrycie cytowań | 100% | ≥ 95% |
| Wstrzymanie się przy braku dowodów | 86% | ≥ 80% |
| Odporność na prompt injection | 71% | ≥ 90% |
| Mediana czasu odpowiedzi | 5,3 s | ≤ 30 s |
| Koszt 1000 zapytań | ≈ 0,34 USD | raportowany |

Odtworzenie: `docker compose --profile local-db --profile tools run --rm eval`
([`eval/README.md`](eval/README.md)).

## Uruchomienie

```bash
cp .env.example .env    # wpisz LLM_API_KEY
docker compose --profile local-db up -d --build
```

Strona: <http://localhost:8080>. Więcej: [`docs/docker.md`](docs/docker.md).

Drugi kanał (adapter demo): `POST /api/channels/demo`, opis w [`docs/api.md`](docs/api.md).
Bot Discord: [`src/backend/README.md`](src/backend/README.md).

## Struktura

```text
spec/            brief, regulamin, wymagania
src/frontend/    Preact + TypeScript + Vite + SCSS
src/backend/     Go: API i kanały
agent/           Go: twierdzenia, werdykt, ochrona przed injection
rag/             Python: korpus i wyszukiwanie
eval/            testy A–J i benchmark dezinformacji
docs/, deploy/   dokumentacja i Dockerfile'e
```

Kontrakty między modułami: [`CONTRACT.md`](CONTRACT.md).

## Ograniczenia

Przy małej liczbie źródeł lub zbyt świeżym wydarzeniu system odpowiada „brak wystarczających
dowodów" i wyjaśnia, czego nie ustalił. Wideo i dźwięk nie są obsługiwane, linki do serwisów
społecznościowych odrzucamy z prośbą o tekst.

## Zespół

**KNIPM**, Koło Naukowe Informatyków Politechniki Morskiej w Szczecinie:
Paweł Dutkiewicz (DudeQ7), Dominik Mech (InvisibleF0x),
Adrian Banaś (Adisman1), Wojciech Michalski (wojtas3422), Daniel Rybak (octoyeller).
