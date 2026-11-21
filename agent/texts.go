package agent

// User-facing Polish texts in one place (AGENTS.md §5). Technical detail goes to logs, not here.
const (
	msgTechnicalError = "Nie udało się teraz sprawdzić tej informacji z powodu problemu technicznego. " +
		"To nie jest ocena treści. Spróbuj ponownie za kilka minut."
	msgNoClaims = "Nie znaleźliśmy w tekście twierdzenia, które da się sprawdzić. " +
		"Wklej konkretną informację, np. „Rząd podniósł płacę minimalną do 5000 zł”."
	msgPageUnreadable = "Nie udało się odczytać treści tej strony. Wklej jej tekst albo wybierz inny adres."
	msgEmptyInput     = "Wpisz informację do sprawdzenia albo wklej adres strony."

	missingNoSources    = "Nie znaleziono publikacji na ten temat w dostępnych źródłach."
	missingWeakEvidence = "Źródła nie wystarczają, by potwierdzić lub obalić to twierdzenie: " +
		"potrzebne jest źródło urzędowe, ocena weryfikatora faktów albo dwa niezależne źródła wtórne."
	missingNoValidQuote = "Model nie wskazał dosłownego cytatu ze źródła, który odnosiłby się do tego twierdzenia."
	missingDiscrepancy  = "Źródła podają rozbieżne dane i nie da się ustalić, które są właściwe."

	limitationFactcheckUnavailable = "Nie mogę teraz sprawdzić ocen weryfikatorów faktów (usługa niedostępna); " +
		"wynik opiera się tylko na korpusie źródeł."
	limitationCatalogEmpty  = "Katalog znanych kampanii dezinformacyjnych jest pusty; dopasowanie nie było możliwe."
	limitationClaimsSkipped = "Sprawdzono %d najważniejsze twierdzenia z około %d w tekście."
	limitationPageTruncated = "Strona była bardzo długa; sprawdzono jej początek."
	limitationFactcheckRule = "Werdykt dla twierdzenia %s oparto na ocenie weryfikatora faktów (%s), " +
		"która różniła się od wstępnej oceny modelu."
	limitationModelFallback = "Dla twierdzenia %s model nie zwrócił poprawnej odpowiedzi; " +
		"podano wstrzymanie się od oceny."

	warningInjection  = "Jedno ze źródeł zawierało polecenia skierowane do systemu; zostały zignorowane."
	warningSuspicious = "Model zgłosił, że treść źródeł zawierała polecenia; zostały zignorowane."

	reasonOfficial           = "źródło urzędowe"
	reasonFactcheck          = "ocena weryfikatora faktów (%s)"
	reasonTwoSecondary       = "co najmniej dwa niezależne źródła wtórne"
	reasonOneSecondary       = "jedno źródło wtórne"
	reasonContextOnly        = "źródła dają tylko kontekst, nie rozstrzygają twierdzenia"
	reasonNoSources          = "brak źródeł"
	reasonFresh              = "aktualne (ostatnie 12 miesięcy)"
	reasonDated              = "źródła starsze niż rok"
	reasonConsistentWithRole = "cytaty zgodne z werdyktem"
)
