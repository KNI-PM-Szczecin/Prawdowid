package agent

// User-facing Polish texts in one place (AGENTS.md §5). Technical detail goes to logs, not here.
const (
	msgTechnicalError = "Nie udało się teraz sprawdzić tej informacji z powodu problemu technicznego. " +
		"To nie jest ocena treści. Spróbuj ponownie za kilka minut."
	msgNoClaims = "Nie znaleźliśmy w tekście twierdzenia, które da się sprawdzić. " +
		"Wklej konkretną informację, np. „Rząd podniósł płacę minimalną do 5000 zł”."
	msgPageUnreadable       = "Nie udało się odczytać treści tej strony. Wklej jej tekst albo wybierz inny adres."
	msgEmptyInput           = "Wpisz informację do sprawdzenia albo wklej adres strony."
	msgFactcheckUnavailable = "Nie mogę teraz sprawdzić ocen weryfikatorów faktów z powodu błędu dostępu do zewnętrznej usługi, " +
		"a w naszych źródłach nie ma publikacji na ten temat. To ograniczenie techniczne, nie ocena treści. " +
		"Spróbuj ponownie za chwilę."

	missingNoSources      = "Nie znaleziono publikacji na ten temat w dostępnych źródłach."
	noteNoResultIsNoProof = "Brak wyniku w naszych źródłach nie oznacza, że to prawda ani że to nieprawda."
	missingWeakEvidence   = "Źródła nie wystarczają, by potwierdzić lub obalić to twierdzenie: " +
		"potrzebne jest źródło urzędowe, ocena weryfikatora faktów albo dwa niezależne źródła wtórne."
	missingNoValidQuote      = "Model nie wskazał dosłownego cytatu ze źródła, który odnosiłby się do tego twierdzenia."
	missingDiscrepancy       = "Źródła podają rozbieżne dane i nie da się ustalić, które są właściwe."
	missingFactcheckMismatch = "Nie ustalono, czy weryfikator faktów oceniał dokładnie to twierdzenie, " +
		"czy inne, podobne. Sprawdź jego publikację w źródłach."
	missingNumbersMismatch = "Cytowane źródła podają inne liczby niż twierdzenie, więc go nie potwierdzają ani nie obalają."

	justificationOpinion = "To opinia, ocena albo przewidywanie, a nie fakt, który da się sprawdzić w źródłach. " +
		"Nie oceniamy, czy jest słuszna."

	limitationFactcheckUnavailable = "Nie mogę teraz sprawdzić ocen weryfikatorów faktów (usługa niedostępna); " +
		"wynik opiera się tylko na korpusie źródeł."
	limitationCatalogEmpty      = "Katalog znanych kampanii dezinformacyjnych jest pusty; dopasowanie nie było możliwe."
	limitationClaimsSkipped     = "Sprawdzono %d najważniejsze twierdzenia z około %d w tekście."
	limitationPageTruncated     = "Strona była bardzo długa; sprawdzono jej początek."
	limitationFactcheckMismatch = "Dla twierdzenia %s ocena weryfikatora faktów (%s) różniła się od wniosku ze źródeł. " +
		"Weryfikator mógł oceniać inne, podobne twierdzenie, dlatego wstrzymujemy się od oceny."
	limitationNumbersMismatch = "Dla twierdzenia %s pominęliśmy jako dowód źródła, które podają inne liczby niż twierdzenie " +
		"(mogą dotyczyć innej sprawy)."
	limitationModelFallback = "Dla twierdzenia %s model nie zwrócił poprawnej odpowiedzi; " +
		"podano wstrzymanie się od oceny."

	warningInjection  = "Jedno ze źródeł zawierało polecenia skierowane do systemu; zostały zignorowane."
	warningSuspicious = "Model zgłosił, że treść źródeł zawierała polecenia; zostały zignorowane."

	limitationInputInstructions = "Zgłoszenie zawierało polecenia skierowane do systemu. " +
		"Potraktowaliśmy je jako zwykły tekst i nie zmieniły zasad sprawdzania."

	// Brief scenario B: the age of the checked page is shown beside the verdict, never used as the verdict.
	materialDateUnknown     = "nieznana"
	warningArchivalMaterial = "Ta strona została opublikowana %s, ponad rok temu. Treść mogła się zdezaktualizować; " +
		"sprawdź, czy dotyczy obecnej sytuacji."
	limitationArchivalMaterial = "Sprawdzana strona pochodzi z %s (ponad rok temu); ocena dotyczy jej treści, " +
		"nie tego, czy jest nadal aktualna."
	limitationMaterialDateUnknown = "Nie ustaliliśmy daty publikacji tej strony, więc nie wiemy, czy jej treść jest aktualna."

	// Brief scenario I: a match of the material is context about the page, never a verdict about its content.
	materialMatchByURL = "Ten adres prowadzi do materiału, który mamy w naszych źródłach (zgodny adres). " +
		"To informacja o samym materiale, nie ocena jego treści."
	materialMatchByTitleAndDate = "Tytuł i data publikacji tej strony zgadzają się z materiałem w naszych źródłach, " +
		"więc to najpewniej ten sam materiał. To informacja o samym materiale, nie ocena jego treści."
	materialMatchIncident = "Ten adres jest zapisany w katalogu znanych kampanii dezinformacyjnych jako miejsce, " +
		"gdzie rozpowszechniano sprawdzaną tam treść (zgodny adres). To kontekst, nie ocena prawdziwości."
	limitationNoMaterialMatch = "Nie znaleźliśmy tej strony w naszych źródłach ani w katalogu znanych kampanii " +
		"(porównujemy adres oraz tytuł z datą publikacji). Sama domena o niczym nie przesądza."
	limitationMaterialMatchUnavailable = "Nie udało się sprawdzić, czy ta strona jest znanym materiałem (usługa niedostępna)."

	reasonOfficial           = "źródło urzędowe"
	reasonFactcheck          = "ocena weryfikatora faktów (%s)"
	reasonTwoSecondary       = "co najmniej dwa niezależne źródła wtórne"
	reasonOneSecondary       = "jedno źródło wtórne"
	reasonContextOnly        = "źródła dają tylko kontekst, nie rozstrzygają twierdzenia"
	reasonNoSources          = "brak źródeł"
	reasonOpinion            = "opinia albo przewidywanie, nie szukano źródeł"
	reasonFresh              = "aktualne (ostatnie 12 miesięcy)"
	reasonDated              = "źródła starsze niż rok"
	reasonConsistentWithRole = "cytaty zgodne z werdyktem"
)
