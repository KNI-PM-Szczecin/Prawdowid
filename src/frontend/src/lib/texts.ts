import type { Badge, CaseStatus, EvidenceStrength, SourceRole, SourceType, SummaryLevel, Verdict, WarningType } from "./types";

export const texts = {
  appName: "Prawdowid",
  skipToContent: "Przejdź do treści",
  nav: {
    label: "Nawigacja główna",
    accessibility: "Dostępność",
  },
  demoBanner:
    "Tryb demonstracyjny: wyniki są przykładowe i nie pochodzą z prawdziwego sprawdzania. Dane i źródła są fikcyjne.",
  form: {
    title: "Sprawdź rzetelność informacji",
    lead: "Wklej treść wiadomości albo link do artykułu. Wskażemy twierdzenia, które da się sprawdzić, porównamy je z wiarygodnymi źródłami i pokażemy ocenę razem z dowodami.",
    label: "Link do artykułu albo tekst do sprawdzenia",
    placeholder: "Wklej link do artykułu bądź tekst…",
    submit: "Sprawdź",
    shortcutHint: "Możesz też nacisnąć Ctrl + Enter.",
    note: "Odpowiedź opiera się na źródłach z naszego katalogu. Pokazujemy je przy każdym wyniku, sprawdź je sam. Zawsze weryfikuj wszystkie informacje.",
    tooLong: (max: number) => `Tekst jest za długi. Skróć go do ${max} znaków.`,
    empty: "Wklej tekst albo link, który chcesz sprawdzić.",
    charCount: (count: number, max: number) => `${count} z ${max} znaków`,
    examplesTitle: "Wypróbuj przykład",
  },
  landing: {
    sampleTitle: "Tak wygląda wynik",
    sampleNote: "Przykład na fikcyjnych danych.",
    sampleSentence: {
      before: "Most nad rzeką Przykładówką ",
      confirmed: "otwarto 15 listopada 2026 r.",
      middle: " Budowa ",
      conflicting: "kosztowała 120 mln zł",
      after: ". To najdłuższa przeprawa w powiecie.",
    },
    sampleClaims: [
      {
        verdict: "confirmed",
        label: "Prawda",
        text: "Potwierdza komunikat urzędu miasta z 15 listopada 2026 r., z cytatem.",
      },
      {
        verdict: "conflicting",
        label: "Sprzeczne źródła",
        text: "Urząd podaje 98 mln zł, dziennik 120 mln zł. Pokazujemy oba źródła i nie rozstrzygamy.",
      },
    ],
    processTitle: "Co dzieje się po naciśnięciu „Sprawdź”",
    steps: [
      {
        title: "Wyodrębniamy twierdzenia",
        text: "Z tekstu wybieramy konkretne, sprawdzalne stwierdzenia: liczby, daty, zdarzenia, decyzje. Opinie, prognozy i pytania oznaczamy jako niemożliwe do sprawdzenia.",
      },
      {
        title: "Szukamy w katalogu źródeł",
        text: "Każde twierdzenie porównujemy z dokumentami z naszego katalogu: komunikatami urzędów, ocenami weryfikatorów faktów i publikacjami rzetelnych mediów. Nie przeszukujemy całego internetu.",
      },
      {
        title: "Pokazujemy ocenę z dowodami",
        text: "Dla każdego twierdzenia dostajesz ocenę, krótkie uzasadnienie, siłę podstawy i źródła z cytatem. Gdy dowodów brakuje, mówimy to wprost i nie zgadujemy.",
      },
    ],
    verdictsTitle: "Pięć możliwych ocen",
    verdictsLead: "Ocena dotyczy pojedynczego twierdzenia, nie całego tekstu ani jego autora.",
    verdictDescriptions: {
      confirmed: "Wiarygodne źródła potwierdzają twierdzenie.",
      false: "Wiarygodne źródła przeczą twierdzeniu.",
      misleading: "Twierdzenie zawiera prawdziwe elementy, ale pomija kontekst albo zniekształca fakty.",
      insufficient_evidence: "Nie znaleźliśmy wystarczających źródeł. To nie znaczy, że twierdzenie jest fałszywe.",
      not_verifiable: "Opinia, prognoza albo pytanie, których nie da się sprawdzić w źródłach.",
    } satisfies Record<Verdict, string>,
    verdictsNote: "Awaria techniczna i niejasne pytanie nie są ocenami. Pokazujemy je osobno, bez koloru werdyktu.",
    sourcesTitle: "Na czym opieramy ocenę",
    sourceDescriptions: {
      official: "Komunikaty i dokumenty urzędów, akty prawne, dane publiczne.",
      factcheck: "Oceny organizacji weryfikujących fakty, które pracują według jawnych zasad.",
      secondary: "Publikacje rzetelnych mediów i instytucji badawczych.",
      incident: "Katalog znanych przypadków dezinformacji. Podobieństwo do nich pokazujemy jako kontekst, nigdy jako ocenę.",
    } satisfies Record<SourceType, string>,
    sourcesNote: "Każde źródło w wyniku ma tytuł, wydawcę, datę publikacji, datę pobrania i link. Możesz je otworzyć i sprawdzić samodzielnie.",
    principlesTitle: "Zasady, których przestrzegamy",
    principles: [
      {
        title: "Nie oceniamy po nadawcy",
        text: "O ocenie decydują źródła, nie domena strony, autor, kanał ani liczba udostępnień.",
      },
      {
        title: "Nie zgadujemy",
        text: "Bez dowodów wstrzymujemy się od oceny i mówimy, czego nie udało się ustalić.",
      },
      {
        title: "Treść stron to dane, nie polecenia",
        text: "Instrukcje ukryte w sprawdzanych materiałach nie zmieniają sposobu działania. Takie próby odnotowujemy.",
      },
      {
        title: "To nie jest sędzia prawdy",
        text: "Wynik wspiera Twoją ocenę, ale jej nie zastępuje. Nie wymagamy logowania ani danych osobowych.",
      },
    ],
  },
  footer: {
    about: "Prawdowid to prototyp stworzony podczas hackathonu HackNation 2026 w ramach zadania Ministerstwa Spraw Zagranicznych. Nie jest serwisem administracji publicznej.",
    repository: "Kod źródłowy",
    repositoryUrl: "https://github.com/KNI-PM-Szczecin/prawdowid",
  },
  loading: {
    title: "Sprawdzam informację",
    description: "Szukam twierdzeń w tekście i porównuję je ze źródłami. To może potrwać do 30 sekund.",
  },
  connectionError: {
    title: "Nie udało się połączyć z serwerem",
    description:
      "To problem techniczny, a nie ocena treści. Sprawdź połączenie z internetem i spróbuj ponownie za chwilę.",
  },
  status: {
    technicalErrorTitle: "Nie udało się teraz sprawdzić tej informacji",
    technicalErrorNote: "To problem techniczny, a nie ocena treści.",
    needsClarificationTitle: "Potrzebujemy więcej szczegółów",
    outOfScopeTitle: "Tego nie sprawdzamy",
    fallbackMessage: "Spróbuj ponownie za kilka minut.",
    retry: "Spróbuj ponownie",
    back: "Wróć do formularza",
  },
  summary: {
    high: {
      title: "Tekst prawdopodobnie prawdziwy",
      description: "Sprawdzone twierdzenia potwierdzają wiarygodne źródła.",
    },
    mixed: {
      title: "Część twierdzeń prawdziwa, część nie",
      description: "Tekst zawiera twierdzenia potwierdzone i takie, które wprowadzają w błąd albo są fałszywe. Sprawdź każde z nich poniżej.",
    },
    low: {
      title: "Tekst prawdopodobnie fałszywy",
      description: "Wiarygodne źródła przeczą sprawdzonym twierdzeniom.",
    },
    unknown: {
      title: "Nie udało się ocenić",
      description: "Nie znaleźliśmy wystarczających źródeł. To nie znaczy, że informacja jest fałszywa.",
    },
  } satisfies Record<SummaryLevel, { title: string; description: string }>,
  summaryReasonsLabel: "Na jakiej podstawie",
  badges: {
    fresh_material: "Świeży",
    archival_material: "Archiwalny",
    official_source_present: "Oficjalna informacja",
    official_source_absent: "Brak oficjalnej informacji",
    input_source_in_catalog: "Adres z katalogu źródeł",
    input_source_outside_catalog: "Adres spoza katalogu źródeł",
  } satisfies Record<Badge, string>,
  badgesLabel: "Cechy źródeł",
  cases: {
    title: (count: number) => (count === 1 ? "Zapisaliśmy to pytanie" : "Zapisaliśmy te twierdzenia"),
    firstReport: (count: number) =>
      count === 1 ? "To pierwsze takie zgłoszenie." : "Nikt wcześniej nie pytał o te twierdzenia.",
    repeated: (reports: number, count: number) =>
      count === 1 ? `O to samo pytano już ${reports} razy.` : `O jedno z nich pytano już ${reports} razy.`,
    status: {
      logged: () =>
        "Jeśli więcej osób zapyta o to samo bez odpowiedzi w źródłach, sprawa trafi do rekomendacji dla analityka.",
      recommended: (count: number) =>
        count === 1
          ? "Sprawa kwalifikuje się do przekazania analitykowi. Nie została jeszcze przekazana: czeka na osobę, która obsługuje zgłoszenia."
          : `${count} sprawy kwalifikują się do przekazania analitykowi. Nie zostały jeszcze przekazane: czekają na osobę, która obsługuje zgłoszenia.`,
      forwarded: (count: number) =>
        count === 1
          ? "Sprawa została przekazana analitykowi do sprawdzenia."
          : `${count} sprawy zostały przekazane analitykowi do sprawdzenia.`,
    } satisfies Record<CaseStatus, (count: number) => string>,
    caseNumbers: (count: number) => (count === 1 ? "Numer sprawy" : "Numery spraw"),
  },
  campaign: {
    title: "Ten tekst może być częścią kampanii dezinformacyjnej",
    moreInfo: "Więcej informacji",
    matchesLabel: "Podobne znane przypadki",
  },
  verdict: {
    confirmed: "Prawda",
    false: "Fałsz",
    misleading: "Wprowadza w błąd",
    insufficient_evidence: "Brak wystarczających dowodów",
    conflicting: "Sprzeczne źródła",
    partial: "Ustalono częściowo",
    not_verifiable: "Nie da się sprawdzić",
  },
  claims: {
    listTitle: (count: number) => `Sprawdzone twierdzenia (${count})`,
    listHint: "Wybierz twierdzenie, aby zobaczyć ocenę, uzasadnienie i źródła. Fragmenty w tekście też można kliknąć.",
    noClaims: "Nie znaleźliśmy w tym tekście twierdzeń do sprawdzenia.",
    open: "Pokaż szczegóły",
  },
  panel: {
    close: "Zamknij szczegóły",
    justification: "Uzasadnienie",
    strength: "Siła podstawy",
    missing: "Czego nie ustalono",
    sources: "Źródła",
    noSources: "Nie znaleźliśmy źródeł na ten temat.",
    warnings: "Ostrzeżenia",
    conflictTitle: "Źródła podają sprzeczne informacje",
    conflictHint: "Porównaj je i wyciągnij własne wnioski.",
    quote: "Cytat ze źródła",
    published: "Opublikowano",
    fetched: "pobrano",
    noDate: "brak daty publikacji",
    license: "Licencja",
    openSource: "Otwórz źródło",
    opensInNewTab: "(otwiera się w nowej karcie)",
  },
  strength: {
    strong: "Mocna",
    moderate: "Średnia",
    weak: "Słaba",
    none: "Brak",
  } satisfies Record<EvidenceStrength, string>,
  sourceType: {
    official: "Źródło urzędowe",
    secondary: "Źródło wtórne",
    factcheck: "Weryfikator faktów",
    incident: "Baza incydentów",
  } satisfies Record<SourceType, string>,
  sourceRole: {
    supports: "Potwierdza",
    refutes: "Zaprzecza",
    context: "Kontekst",
  } satisfies Record<SourceRole, string>,
  warningType: {
    source_status: "Status źródła",
    incident_match: "Podobne do znanej dezinformacji",
    archival_material: "Materiał archiwalny",
    other: "Uwaga",
  } satisfies Record<WarningType, string>,
  limitations: {
    title: "Ograniczenia",
    general:
      "Sprawdzamy tylko źródła z naszego katalogu i nie mamy dostępu do wszystkich publikacji. Wynik wspiera Twoją ocenę, ale jej nie zastępuje.",
  },
  technical: {
    title: "Szczegóły techniczne",
    requestId: "Identyfikator sprawdzenia",
    latency: "Czas odpowiedzi",
    model: "Model językowy",
    corpus: "Wersja korpusu źródeł",
    injection: "Wykryte próby manipulacji systemem",
    seconds: (ms: number) => `${(ms / 1000).toFixed(1)} s`,
    none: "brak",
  },
  resultTitle: "Wynik sprawdzenia",
  source: "Źródło",
  checkedUrl: "Sprawdzany adres",
  newCheck: "Sprawdź inną informację",
  accessibility: {
    title: "Ustawienia dostępności",
    description: "Dostosuj sposób wyświetlania strony do swoich potrzeb.",
    close: "Zamknij ustawienia dostępności",
    contrast: "Kontrast",
    contrastDefault: "Domyślny",
    contrastHighLight: "Wysoki kontrast: jasny",
    contrastHighDark: "Wysoki kontrast: ciemny",
    textSize: "Rozmiar tekstu",
    motion: "Animacje",
    reduceMotion: "Ogranicz animacje",
    reset: "Przywróć domyślne",
  },
} as const;
