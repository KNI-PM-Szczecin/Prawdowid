// Demo-only fixtures for `pnpm dev:mock`. Everything here is fictional and labelled as such in the UI.
import type { CheckResult, CheckedDocument, Claim, InputType, RunMeta, Source, TextSpan } from "./types";

const MOCK_DELAY_MS = 1500;
const MOCK_FETCHED_AT = "2026-11-20T08:00:00Z";
const MOCK_LATENCY_MS = 6400;
const MOCK_LABEL = " (dane przykładowe)";
const MAX_FALLBACK_CLAIM_LENGTH = 200;

export interface MockExample {
  label: string;
  input: string;
}

const TICKETS_TEXT = "Od 1 stycznia 2027 r. uczniowie w Przykładowie jeżdżą komunikacją miejską za darmo.";
const WATER_TEXT = "Woda z wodociągów w Przykładowie jest skażona i nie wolno jej pić do końca miesiąca.";
const BRIDGE_TITLE = "Nowy most w Przykładowie otwarty. Inwestycja kosztowała 120 mln zł";
const BRIDGE_TEXT =
  "Most nad rzeką Przykładówką otwarto 15 listopada 2026 r. Budowa kosztowała 120 mln zł. " +
  "To najdłuższy most w województwie, ma 840 metrów.\n\n" +
  "Mieszkańcy czekali na przeprawę od ponad dziesięciu lat. Według urzędu miasta most skróci dojazd do centrum o kwadrans.";
const RESIGNATION_TEXT = "Dziś rano burmistrz Przykładowa podał się do dymisji.";

export const MOCK_EXAMPLES: MockExample[] = [
  { label: "Prawdziwa informacja", input: TICKETS_TEXT },
  { label: "Fałszywa informacja", input: WATER_TEXT },
  { label: "Artykuł z kilkoma twierdzeniami", input: `${BRIDGE_TITLE}\n\n${BRIDGE_TEXT}` },
  { label: "Brak dowodów", input: RESIGNATION_TEXT },
];

function spanOf(text: string, fragment: string): TextSpan | null {
  const index = text.indexOf(fragment);
  if (index < 0) {
    return null;
  }
  const start = Array.from(text.slice(0, index)).length;
  return { start, end: start + Array.from(fragment).length };
}

function source(fields: Omit<Source, "fetchedAt" | "license" | "publisher"> & { publisher: string }): Source {
  return { ...fields, publisher: fields.publisher + MOCK_LABEL, fetchedAt: MOCK_FETCHED_AT, license: "CC BY 4.0" };
}

function meta(abstained: boolean): RunMeta {
  return {
    channel: "web",
    receivedAt: new Date().toISOString(),
    latencyMs: MOCK_LATENCY_MS,
    model: "tryb-demonstracyjny",
    estimatedCostUsd: 0,
    corpusVersion: "demo",
    retrievedPassages: abstained ? 0 : 4,
    searchErrors: 0,
    injectionAttempts: 0,
    abstained,
    timedOut: false,
  };
}

function textDocument(text: string): CheckedDocument {
  return { title: null, text, url: null, publisher: null, fetchedAt: null };
}

const LIMITATION_CORPUS = "Korpus demonstracyjny obejmuje źródła do 20 listopada 2026 r.";

function ticketsResult(requestId: string): CheckResult {
  const claim: Claim = {
    id: "c1",
    text: "Od 1 stycznia 2027 r. uczniowie w Przykładowie jeżdżą komunikacją miejską za darmo.",
    span: spanOf(TICKETS_TEXT, TICKETS_TEXT),
    verdict: "confirmed",
    justification:
      "Uchwała rady miasta wprowadza bezpłatne przejazdy dla uczniów od 1 stycznia 2027 r. Informację powtarza lokalny dziennik.",
    evidenceStrength: "strong",
    strengthReasons: ["źródło urzędowe", "aktualne (październik 2026)", "dosłownie zgodne z twierdzeniem"],
    sources: [
      source({
        id: "s1",
        title: "Uchwała w sprawie bezpłatnych przejazdów dla uczniów",
        publisher: "Rada Miasta Przykładowo",
        publishedAt: "2026-10-14T00:00:00Z",
        url: "https://przyklad.gov.pl/uchwala-bezplatne-przejazdy",
        sourceType: "official",
        role: "supports",
        quote: "Od dnia 1 stycznia 2027 r. uczniowie szkół z terenu miasta korzystają z komunikacji miejskiej bezpłatnie.",
      }),
      source({
        id: "s2",
        title: "Darmowa komunikacja dla uczniów od stycznia",
        publisher: "Dziennik Przykładowski",
        publishedAt: "2026-10-15T00:00:00Z",
        url: "https://przyklad-dziennik.pl/darmowa-komunikacja",
        sourceType: "secondary",
        role: "supports",
        quote: "Rada miasta zdecydowała, że od nowego roku uczniowie nie zapłacą za bilety.",
      }),
    ],
    warnings: [],
    conflict: null,
    missing: null,
  };
  return {
    requestId,
    status: "ok",
    message: null,
    document: textDocument(TICKETS_TEXT),
    summary: { level: "high", reasons: ["1 z 1 twierdzeń potwierdzone", "w tym 1 źródło urzędowe"] },
    badges: ["fresh_material", "official_source_present"],
    campaignAlert: null,
    claims: [claim],
    limitations: [LIMITATION_CORPUS],
    meta: meta(false),
  };
}

function waterResult(requestId: string): CheckResult {
  const claim: Claim = {
    id: "c1",
    text: "Woda z wodociągów w Przykładowie jest skażona i nie wolno jej pić.",
    span: spanOf(WATER_TEXT, WATER_TEXT),
    verdict: "false",
    justification:
      "Sanepid w komunikacie z 18 listopada podaje, że woda spełnia wymagania i nadaje się do picia. Nie wydano zakazu jej spożycia.",
    evidenceStrength: "strong",
    strengthReasons: ["źródło urzędowe", "aktualne (listopad 2026)", "wprost przeczy twierdzeniu"],
    sources: [
      source({
        id: "s1",
        title: "Komunikat w sprawie jakości wody w Przykładowie",
        publisher: "Powiatowa Stacja Sanitarno-Epidemiologiczna w Przykładowie",
        publishedAt: "2026-11-18T00:00:00Z",
        url: "https://przyklad-sanepid.gov.pl/komunikat-woda",
        sourceType: "official",
        role: "refutes",
        quote: "Woda z wodociągu publicznego spełnia wymagania i jest przydatna do spożycia.",
      }),
    ],
    warnings: [{ type: "incident_match", message: "Treść jest podobna do znanej sprawy dezinformacji." }],
    conflict: null,
    missing: null,
  };
  return {
    requestId,
    status: "ok",
    message: null,
    document: textDocument(WATER_TEXT),
    summary: { level: "low", reasons: ["1 z 1 twierdzeń obalone", "w tym 1 źródło urzędowe"] },
    badges: ["fresh_material", "official_source_present"],
    campaignAlert: {
      category: "possible_disinformation_campaign",
      message:
        "Treść jest podobna do znanych przypadków dezinformacji. To informacja dodatkowa, nie ocena tego tekstu.",
      matches: [
        {
          incidentId: "demo-0042",
          source: "katalog incydentów" + MOCK_LABEL,
          title: "Fałszywe ostrzeżenia o skażonej wodzie w kilku miastach",
          summary: "Seria wpisów o rzekomym skażeniu wody, rozsyłanych jako łańcuszki w komunikatorach.",
          url: "https://przyklad-incydenty.eu/sprawa/demo-0042",
          publishedAt: "2026-09-02T00:00:00Z",
        },
      ],
    },
    claims: [claim],
    limitations: [LIMITATION_CORPUS],
    meta: meta(false),
  };
}

function bridgeResult(requestId: string): CheckResult {
  const claims: Claim[] = [
    {
      id: "c1",
      text: "Most otwarto 15 listopada 2026 r.",
      span: spanOf(BRIDGE_TEXT, "otwarto 15 listopada 2026 r."),
      verdict: "confirmed",
      justification: "Urząd miasta potwierdza otwarcie mostu 15 listopada 2026 r.",
      evidenceStrength: "strong",
      strengthReasons: ["źródło urzędowe", "aktualne", "dosłownie zgodne z twierdzeniem"],
      sources: [
        source({
          id: "s1",
          title: "Most nad Przykładówką otwarty dla ruchu",
          publisher: "Urząd Miasta Przykładowo",
          publishedAt: "2026-11-15T00:00:00Z",
          url: "https://przyklad.gov.pl/most-otwarty",
          sourceType: "official",
          role: "supports",
          quote: "15 listopada 2026 r. most nad rzeką Przykładówką został otwarty dla ruchu.",
        }),
      ],
      warnings: [],
      conflict: null,
      missing: null,
    },
    {
      id: "c2",
      text: "Budowa kosztowała 120 mln zł.",
      span: spanOf(BRIDGE_TEXT, "Budowa kosztowała 120 mln zł."),
      verdict: "insufficient_evidence",
      justification:
        "Urząd miasta podaje 98 mln zł, a lokalny dziennik 120 mln zł. Nie da się ustalić, która kwota jest właściwa.",
      evidenceStrength: "moderate",
      strengthReasons: ["źródło urzędowe i wtórne", "sprzeczne dane"],
      sources: [
        source({
          id: "s2",
          title: "Ile kosztował nowy most?",
          publisher: "Dziennik Przykładowski",
          publishedAt: "2026-11-16T00:00:00Z",
          url: "https://przyklad-dziennik.pl/koszt-mostu",
          sourceType: "secondary",
          role: "supports",
          quote: "Łączny koszt inwestycji przekroczył 120 mln zł.",
        }),
        source({
          id: "s3",
          title: "Sprawozdanie z wykonania budżetu inwestycyjnego",
          publisher: "Urząd Miasta Przykładowo",
          publishedAt: "2026-11-10T00:00:00Z",
          url: "https://przyklad.gov.pl/sprawozdanie-inwestycje",
          sourceType: "official",
          role: "refutes",
          quote: "Wydatki na budowę mostu wyniosły 98 mln zł.",
        }),
      ],
      warnings: [],
      conflict: {
        summary:
          "Urząd podaje 98 mln zł, dziennik 120 mln zł. Możliwe, że dziennik doliczył koszty dróg dojazdowych.",
      },
      missing: "Nie ustalono, która kwota obejmuje całą inwestycję.",
    },
    {
      id: "c3",
      text: "To najdłuższy most w województwie.",
      span: spanOf(BRIDGE_TEXT, "To najdłuższy most w województwie"),
      verdict: "misleading",
      justification:
        "Według rejestru obiektów mostowych to najdłuższy most w powiecie, ale nie w województwie. W województwie są dwa dłuższe.",
      evidenceStrength: "moderate",
      strengthReasons: ["źródło urzędowe", "twierdzenie zawyża zasięg"],
      sources: [
        source({
          id: "s4",
          title: "Rejestr obiektów mostowych województwa",
          publisher: "Zarząd Dróg Wojewódzkich",
          publishedAt: "2026-06-30T00:00:00Z",
          url: "https://przyklad-zdw.gov.pl/rejestr-mostow",
          sourceType: "official",
          role: "refutes",
          quote: "Najdłuższe obiekty w województwie: most w Dalekowie (1120 m), most w Brzegowie (910 m).",
        }),
      ],
      warnings: [],
      conflict: null,
      missing: null,
    },
  ];
  return {
    requestId,
    status: "ok",
    message: null,
    document: { title: BRIDGE_TITLE, text: BRIDGE_TEXT, url: null, publisher: null, fetchedAt: null },
    summary: {
      level: "mixed",
      reasons: ["1 z 3 twierdzeń potwierdzone", "1 wprowadza w błąd", "1 bez wystarczających dowodów"],
    },
    badges: ["fresh_material", "official_source_present"],
    campaignAlert: null,
    claims,
    limitations: [LIMITATION_CORPUS],
    meta: meta(false),
  };
}

function noEvidenceResult(requestId: string, text: string): CheckResult {
  const claimText =
    text.length > MAX_FALLBACK_CLAIM_LENGTH ? `${text.slice(0, MAX_FALLBACK_CLAIM_LENGTH)}…` : text;
  return {
    requestId,
    status: "ok",
    message: null,
    document: textDocument(text),
    summary: { level: "unknown", reasons: ["1 z 1 twierdzeń bez wystarczających dowodów"] },
    badges: [],
    campaignAlert: null,
    cases: [{ claimId: "c1", caseId: "3f2a9c1e-0000-4000-8000-000000000000", reports: 3, status: "recommended" }],
    claims: [
      {
        id: "c1",
        text: claimText,
        span: null,
        verdict: "insufficient_evidence",
        justification: "W dostępnych źródłach nie ma informacji na ten temat.",
        evidenceStrength: "none",
        strengthReasons: ["brak pasujących źródeł"],
        sources: [],
        warnings: [],
        conflict: null,
        missing:
          "Nie znaleźliśmy żadnej publikacji na ten temat. To może być bardzo świeża informacja. Sprawdź ponownie później.",
      },
    ],
    limitations: [LIMITATION_CORPUS],
    meta: meta(true),
  };
}

function clarificationResult(requestId: string): CheckResult {
  return {
    requestId,
    status: "needs_clarification",
    message:
      "W trybie demonstracyjnym nie pobieramy stron. Wklej treść artykułu jako tekst albo wybierz jeden z przykładów.",
    document: null,
    summary: null,
    badges: [],
    campaignAlert: null,
    claims: [],
    limitations: [],
    meta: meta(true),
  };
}

const delay = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export async function mockCheck(input: string, inputType: InputType): Promise<CheckResult> {
  await delay(MOCK_DELAY_MS);
  const requestId = crypto.randomUUID();
  const text = input.trim();
  if (inputType === "url") {
    return clarificationResult(requestId);
  }
  if (text === TICKETS_TEXT) {
    return ticketsResult(requestId);
  }
  if (text === WATER_TEXT) {
    return waterResult(requestId);
  }
  if (text.includes(BRIDGE_TEXT.slice(0, 40))) {
    return bridgeResult(requestId);
  }
  return noEvidenceResult(requestId, text);
}
