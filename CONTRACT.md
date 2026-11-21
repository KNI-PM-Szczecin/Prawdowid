# Kontrakty między modułami

Zmiana tutaj wymaga wpisu w tym pliku w tym samym PR. **Status: PROPOZYCJA do przeglądu zespołu.** Po zatwierdzeniu przez właścicieli `front/`, `backend/`, `agent/` i `rag/` usuń tę linijkę.

Przepływ: `front` / kanał → `backend` → `agent` → `rag`. Typy poniżej są w TypeScript (`front`, `backend`, `agent`) i Pydantic (`rag`); pola i nazwy są identyczne w obu.
Identyfikatory i nazwy pól po angielsku, teksty dla użytkownika (`justification`, `message`, `limitations`) po polsku, prostym językiem.

## Statusy

Werdykty (dotyczą jednego twierdzenia): `confirmed`, `false`, `misleading`, `insufficient_evidence`, `not_verifiable`.
Statusy niemerytoryczne (dotyczą całego zgłoszenia, **nie są werdyktem**): `technical_error`, `needs_clarification`, `out_of_scope`.
Odpowiedź ma albo `status: "ok"` z werdyktami, albo jeden ze statusów niemerytorycznych bez werdyktów.

## 1. front ↔ backend (HTTP)

`POST /api/check`

```ts
type CheckRequest = {
  input: string;                // tekst zgłoszenia albo URL, max 5000 znaków
  inputType: "text" | "url";
};

type EvidenceStrength = "strong" | "moderate" | "weak" | "none";

type SourceRef = {
  id: string;
  title: string;
  publisher: string;
  publishedAt: string | null;   // ISO 8601
  fetchedAt: string;            // ISO 8601
  url: string;
  license: string | null;
  sourceType: "official" | "secondary" | "factcheck" | "incident";
  role: "supports" | "refutes" | "context";
  quote: string | null;         // dosłowny cytowany fragment
};

type Claim = {
  id: string;
  text: string;                 // twierdzenie wyciągnięte z zgłoszenia
  verdict: "confirmed" | "false" | "misleading" | "insufficient_evidence" | "not_verifiable";
  justification: string;        // po polsku, interpretacja modelu, oddzielona od źródeł
  evidenceStrength: EvidenceStrength;
  strengthReasons: string[];    // jawne przesłanki: jakość i aktualność źródeł, zgodność z tezą, liczba niezależnych potwierdzeń
  sources: SourceRef[];         // pusta lista tylko przy insufficient_evidence i not_verifiable
  warnings: string[];           // neutralne ostrzeżenia (np. status źródła), nigdy podstawa werdyktu
  missing: string | null;       // przy insufficient_evidence: czego nie udało się ustalić
};

type CheckResult = {
  requestId: string;
  status: "ok" | "technical_error" | "needs_clarification" | "out_of_scope";
  message: string | null;       // po polsku, wymagane gdy status !== "ok"
  claims: Claim[];              // pusta lista gdy status !== "ok"
  limitations: string[];        // ograniczenia całej odpowiedzi, po polsku
  meta: RunMeta;                // do logu i panelu deweloperskiego, front może ignorować
};

type RunMeta = {
  channel: string;              // "web", "discord", ...
  receivedAt: string;           // ISO 8601
  latencyMs: number;
  model: string | null;
  estimatedCostUsd: number | null;
  injectionAttempts: number;    // liczba wykrytych prób prompt injection
  abstained: boolean;
};
```

Kody HTTP: `200` dla `ok`, `needs_clarification` i `out_of_scope`; `422` gdy wejście nie przechodzi walidacji (wtedy `needs_clarification`); `503` dla `technical_error` (ciało ma ten sam kształt `CheckResult`). Brak klucza API, limit i awaria zależności to zawsze `technical_error`, nigdy werdykt.

## 2. backend ↔ agent (wywołanie funkcji, ten sam proces)

Każdy kanał (web, Discord, ...) woła dokładnie tę samą funkcję. Kanał tłumaczy wiadomość na `VerifyRequest` i `CheckResult` na odpowiedź swojego medium.

```ts
type VerifyRequest = {
  requestId: string;
  channel: string;
  input: string;
  inputType: "text" | "url";
};

// agent/ eksportuje:
function verify(request: VerifyRequest): Promise<CheckResult>;

// backend/ implementuje dla każdego kanału:
interface ChannelAdapter {
  name: string;
  toRequest(incoming: unknown): VerifyRequest;
  toReply(result: CheckResult): unknown;
}
```

`backend/` zapisuje przebieg sprawdzenia (pytanie, czas, użyte źródła, wynik, `meta`) na podstawie `CheckResult`. `verify` nie rzuca wyjątkiem dla błędów zależności, tylko zwraca `status: "technical_error"`.

## 3. agent ↔ rag (HTTP)

`agent/` (TypeScript) woła serwis `rag/` (Python). Adres w `RAG_URL`.

`POST /search`

```ts
type SearchRequest = {
  query: string;                // jedno twierdzenie
  topK: number;                 // domyślnie 8
  filters?: {
    sourceTypes?: SourceRef["sourceType"][];
    publishedAfter?: string;    // ISO 8601
  };
};

type Passage = {
  documentId: string;
  title: string;
  publisher: string;
  publishedAt: string | null;
  fetchedAt: string;
  url: string;
  license: string | null;
  sourceType: SourceRef["sourceType"];
  passage: string;              // fragment tekstu
  score: number;                // 0..1, im wyżej tym trafniej
  flags: string[];              // np. "suspected_injection"; decyzja o reakcji należy do agent/
};

type SearchResponse = {
  results: Passage[];           // pusta lista = brak wyników (to nie błąd)
  corpusVersion: string;
};
```

Fragment bez kompletnych metadanych (tytuł, wydawca, `fetchedAt`, `url`) nie jest zwracany. Błąd indeksu to `503` z ciałem `{ "error": { "code": "index_unavailable", "message": "..." } }`; `agent/` zamienia go na `technical_error`.

Pozostałe endpointy:
- `GET /health` → `{ "status": "ok", "corpusVersion": "..." }`
- `GET /sources` → lista źródeł korpusu (nazwa, domena, typ, licencja, data ostatniej aktualizacji). Wymagane przez brief do audytu.

## 4. agent: dostawca modelu (wewnętrzny interfejs)

Model językowy jest wymienny przez jeden interfejs. Reszta `agent/` nie zna konkretnego dostawcy.

```ts
interface LlmProvider {
  name: string;
  generate(request: {
    system: string;            // reguły systemu, nigdy treść ze źródeł ani od użytkownika
    user: string;
    schema?: unknown;          // opcjonalny schemat wymaganej odpowiedzi
  }): Promise<{ text: string; inputTokens: number; outputTokens: number }>;
}
```

## Otwarte pytania do zespołu
1. Skala `evidenceStrength` i próg, od którego `agent/` wstrzymuje się od oceny (propozycja: `none` lub `weak` bez cytatu daje `insufficient_evidence`).
2. Maksymalna długość `input` (propozycja: 5000 znaków) i limit żądań na klienta.
3. Czy `meta` ma być widoczne dla frontu, czy tylko w logu.
4. Drugi kanał: Discord (propozycja) czy inny.
