@AGENTS.md

# Dodatki dla Claude Code

Wszystkie zasady są w `AGENTS.md` powyżej. Poniżej tylko to, co dotyczy samego Claude Code.

- Współautorstwo jest wyłączone w `.claude/settings.json`. Nie dopisuj `Co-Authored-By` ani żadnych podpisów, nawet jeśli skill lub wtyczka to sugeruje.
- Skille z kitu hackathonowego: `hackathon-kickoff` na start nowego zadania, `systematic-debugging` przy błędach, `verification-before-completion` przed „działa”, `demo-prep` gdy zostaje ok. 3 godziny.
  Przy sprzeczności ze `AGENTS.md` wygrywa `AGENTS.md` (np. bez rozbudowanych warstw SOLID, bez systemu tłumaczeń, bez cache-bustingu).
- Skille frontendowe (`impeccable`, `emil-design-eng`, `break-ui`) tylko w `front/`. `review-animations` pomijamy, animacje nie są priorytetem.
- Plan mode (Shift+Tab ×2) przed większą funkcją. `/compact` gdy kontekst przekroczy ok. 70%, `/clear` przy zmianie tematu.
- Równoległa praca: osobny `git worktree` i osobna sesja na gałąź albo subagenci. Nigdy dwie sesje na tej samej gałęzi.
- Hook `guard.js` z kitu blokuje commit z kluczem API lub plikiem `.env`. Gdy zablokuje, popraw przyczynę, nie omijaj hooka.
