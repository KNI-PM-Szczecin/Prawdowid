# frontend

Preact + TypeScript + Vite + Tailwind CSS v4, pnpm. Zasady: ../../AGENTS.md. Kontrakt API: ../../CONTRACT.md i ../../docs/api.md.

## Uruchomienie

Wymaga Node 20.19+ albo 22.12+ (Vite 8) i pnpm (`corepack pnpm …`, jeśli `pnpm` nie jest w PATH).

```
pnpm install
pnpm dev:mock   # tryb demonstracyjny: fikcyjne wyniki bez backendu, baner i przykłady na stronie głównej
pnpm dev        # prawdziwy backend: /api przekierowane na http://localhost:3001 (zmiana: BACKEND_URL)
pnpm lint
pnpm build      # albo build:mock
```

Bez działającego backendu `pnpm dev` pokazuje ekran błędu połączenia, nigdy wynik.

Railway: usługa `front` buduje `deploy/front.Dockerfile`. Zmienna `FRONT_MODE=mock` w ustawieniach usługi daje wersję demonstracyjną. Bez tej zmiennej powstaje wersja na żywo, która woła backend.

## Struktura

- `src/lib/texts.ts`: wszystkie teksty widoczne dla użytkownika.
- `src/lib/types.ts`: `CheckResult` z kontraktu. Pola z `CONTRACT.md` §1a (`document`, `summary`, `badges`, `campaignAlert`, `span`, `conflict`) są opcjonalne.
- `src/lib/api.ts`: `POST /api/check`. 200, 429 i 503 niosą `CheckResult`, wszystko inne to błąd połączenia.
- `src/lib/mockResults.ts`: dane trybu demo, tylko fikcyjne.
- `src/lib/accessibilitySettings.ts`: kontrast, rozmiar tekstu i animacje. Zapis w `localStorage`, wartości startowe z `prefers-contrast` i `prefers-reduced-motion`.
- `src/components/`: jeden komponent na plik.

## Dostępność

Każdy stan ma tekst, nie tylko kolor. Lista twierdzeń pod tekstem działa z klawiatury i przy `span: null`. Fokus przechodzi na nagłówek po zmianie widoku i wraca po zamknięciu panelu. Są trzy tryby kontrastu i rozmiar tekstu do 200%, wszystko w jednostkach rem.
