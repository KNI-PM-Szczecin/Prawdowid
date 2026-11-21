# Prawdowid

Narzędzie dla obywatela do sprawdzania doniesień (tekst, URL) na podstawie wiarygodnych źródeł. HackNation 2026, zadanie MSZ.
Pokazuje werdykt, źródła i granice wiedzy. Przy braku dowodów wstrzymuje się od oceny.

## Struktura
- `spec/` — brief zadania, regulamin, wymagania (przeczytaj najpierw)
- `front/` — React (interfejs WWW)
- `backend/` — Node.js (API, kanały)
- `agent/` — logika weryfikacji
- `rag/` — korpus i wyszukiwanie źródeł

Zasady pracy dla ludzi i agentów AI: `AGENTS.md`. Kontrakty między modułami: `CONTRACT.md`.

## Wymagania
Narzędzia do zainstalowania przed startem: Git, Node.js z npm (`backend/`, `front/`, `agent/`), Python 3.12 i `uv` (`rag/`).

ArchLinux:
```
sudo pacman -S nodejs npm python uv
```

Windows (PowerShell):
```
winget install Git.Git
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.12
winget install astral-sh.uv
```
Po instalacji uruchom terminal ponownie. Hook `.githooks/commit-msg` działa w Git Bash dołączonym do Git for Windows.

## Start zespołu
```
git config core.hooksPath .githooks
cp .env.example .env
```

## Uruchomienie
Uzupełnimy po powstaniu pierwszego przepływu (jedna komenda).

## Zespół
Uzupełnić.
