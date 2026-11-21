@AGENTS.md
@spec/requirements.md

# Dodatki dla Claude Code

**Zanim zrobisz cokolwiek, przeczytaj wszystkie pliki w folderze `spec/`** (`spec/README.md`, `spec/requirements.md`, `spec/brief.md`, `spec/regulation.md`). `AGENTS.md` i `spec/requirements.md` są zaimportowane powyżej; `brief.md` i `regulation.md` przeczytaj samodzielnie.

Wszystkie zasady są w `AGENTS.md` powyżej. Poniżej tylko to, co dotyczy samego Claude Code.

- Skille z kitu hackathonowego: `hackathon-kickoff` na start nowego zadania, `systematic-debugging` przy błędach, `verification-before-completion` przed „działa”, `demo-prep` gdy zostaje ok. 3 godziny.
  Przy sprzeczności ze `AGENTS.md` wygrywa `AGENTS.md` (np. bez rozbudowanych warstw SOLID, bez systemu tłumaczeń, bez cache-bustingu).
- Skille frontendowe (`impeccable`, `emil-design-eng`, `break-ui`) tylko w `front/`. `review-animations` pomijamy, animacje nie są priorytetem.
- Plan mode (Shift+Tab ×2) przed większą funkcją. `/compact` gdy kontekst przekroczy ok. 70%, `/clear` przy zmianie tematu.
- Równoległa praca: osobny `git worktree` i osobna sesja na gałąź albo subagenci. Nigdy dwie sesje na tej samej gałęzi.
- Hook `guard.js` z kitu blokuje commit z kluczem API lub plikiem `.env`. Gdy zablokuje, popraw przyczynę, nie omijaj hooka.
