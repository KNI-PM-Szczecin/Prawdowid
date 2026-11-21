# Prawdowid

Narzędzie dla obywatela do sprawdzania doniesień (tekst, URL) na podstawie wiarygodnych źródeł. HackNation 2026, zadanie MSZ.
Pokazuje werdykt, źródła i granice wiedzy. Przy braku dowodów wstrzymuje się od oceny.

## Struktura
- `spec/` — brief zadania, regulamin, wymagania (przeczytaj najpierw)
- `src/` — React + Vite (interfejs WWW, frontend)
- `front/` — nieużywany, frontend jest w `src/`
- `backend/` — Go (API, kanały)
- `agent/` — Go (logika weryfikacji)
- `rag/` — korpus i wyszukiwanie źródeł

Zasady pracy dla ludzi i agentów AI: `AGENTS.md`. Kontrakty między modułami: `CONTRACT.md`.

## Wymagania
Narzędzia do zainstalowania przed startem: Git, Go (`backend/`, `agent/`), Node.js i `pnpm` (`src/`), Python 3.12 i `uv` (`rag/`).

ArchLinux:
```
sudo pacman -S go nodejs pnpm python uv
```

Windows (PowerShell):
```
winget install Git.Git
winget install GoLang.Go
winget install OpenJS.NodeJS.LTS
winget install pnpm.pnpm
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
