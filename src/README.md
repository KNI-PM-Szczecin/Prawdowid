# src (front)

React 19 + TypeScript + Vite + Tailwind. Interfejs WWW dla obywatela, bez logiki weryfikacji: woła `backend/` (Go) zgodnie z `../CONTRACT.md`. Zasady: `../AGENTS.md`. Najpierw przeczytaj `../spec`.

```
pnpm install
pnpm dev      # http://localhost:5173
pnpm build    # tsc -b && vite build, wynik w dist/
pnpm lint     # oxlint
```

Kod w `app/` (`main.tsx`, `App.tsx`), teksty widoczne dla użytkownika w `app/lib/texts.ts`.
