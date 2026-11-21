package agent

import (
	"reflect"
	"testing"
)

func TestCardinalNumbers(t *testing.T) {
	cases := map[string][]string{
		"Sejm składa się z 460 posłów.":                      {"460"},
		"Sejm może liczyć 458 parlamentarzystów":             {"458"},
		"dla osób po 65. roku życia":                         {},
		"Art. 98. 1. Sejm i Senat są wybierane":              {},
		"zgodnie z art. 98 ust. 1 Konstytucji":               {},
		"Inflacja wyniosła 11,4% w 2023 roku.":               {"11,4", "2023"},
		"Na program przeznaczono 3 000 000 zł.":              {"3000000"},
		"Komunikat z 24.02.2022 o ataku":                     {"24", "2", "2022"},
		"Sejm i Senat są wybierane na czteroletnie kadencje": {},
		"Twierdzenie: Polska weszła do UE 1 maja 2004 roku.": {"1", "2004"},
	}
	for text, want := range cases {
		got := []string{}
		for number := range cardinalNumbers(text) {
			got = append(got, number)
		}
		wantSet, gotSet := map[string]bool{}, map[string]bool{}
		for _, number := range want {
			wantSet[number] = true
		}
		for _, number := range got {
			gotSet[number] = true
		}
		if !reflect.DeepEqual(wantSet, gotSet) {
			t.Errorf("cardinalNumbers(%q) = %v, want %v", text, got, want)
		}
	}
}

// Issue 1, the Sejm case: a source about 458 members was cited as confirming a claim about 460.
func TestSupportingQuoteWithOtherNumberAbstains(t *testing.T) {
	passage := officialPassage()
	passage.Passage = "Po wygaszeniu dwóch mandatów Sejm może liczyć 458 parlamentarzystów do czasu uzupełnienia składu."
	quote := "Sejm może liczyć 458 parlamentarzystów"
	result := verify(t, newTestAgent(t, &fakeProvider{judge: judgeJSON("potwierdzone", quote, "potwierdza")},
		&ragStub{search: searchWith(passage)}), "Sejm Rzeczypospolitej Polskiej składa się z 460 posłów.", InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictInsufficientEvidence || claim.Sources[0].Role != RoleContext {
		t.Fatalf("expected abstention with the quote as context, got %+v", claim)
	}
	if claim.Missing == nil || *claim.Missing != missingNumbersMismatch {
		t.Fatalf("missing should explain the number mismatch, got %v", claim.Missing)
	}
	if len(result.Limitations) != 1 {
		t.Fatalf("expected one limitation, got %v", result.Limitations)
	}
}

func TestSupportingQuoteWithSameNumberStaysConfirmed(t *testing.T) {
	passage := officialPassage()
	passage.Passage = "Art. 96. 1. Sejm składa się z 460 posłów."
	result := verify(t, newTestAgent(t, &fakeProvider{judge: judgeJSON("potwierdzone", "Sejm składa się z 460 posłów", "potwierdza")},
		&ragStub{search: searchWith(passage)}), "Sejm Rzeczypospolitej Polskiej składa się z 460 posłów.", InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictConfirmed || claim.Sources[0].Role != RoleSupports || len(result.Limitations) != 0 {
		t.Fatalf("expected confirmed without limitations, got %+v %v", claim, result.Limitations)
	}
}

// A refuting quote carries another number by design, so it is not demoted.
func TestRefutingQuoteWithOtherNumberStillRefutes(t *testing.T) {
	passage := officialPassage()
	passage.Passage = "Art. 96. 1. Sejm składa się z 460 posłów."
	result := verify(t, newTestAgent(t, &fakeProvider{judge: judgeJSON("falszywe", "Sejm składa się z 460 posłów", "obala")},
		&ragStub{search: searchWith(passage)}), "Sejm składa się z 500 posłów.", InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictFalse || claim.Sources[0].Role != RoleRefutes {
		t.Fatalf("expected false with a refuting source, got %+v", claim)
	}
}

// A fact-checker rated a claim with other numbers; its rating says nothing about the user's claim.
func TestFactcheckOfClaimWithOtherNumberIsContextOnly(t *testing.T) {
	passage := factcheckPassage()
	passage.Passage = "Twierdzenie sprawdzone przez weryfikatora faktów: Kadencja Sejmu trwa 5 lat. " +
		"Ocena weryfikatora (Demagog): Fałsz. Tytuł weryfikacji: Nie 5, a 4 lata."
	result := verify(t, newTestAgent(t, &fakeProvider{judge: factcheckJudge("falszywe", "obala")},
		&ragStub{search: searchWith(passage)}), claimSejm, InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictInsufficientEvidence || claim.Sources[0].Role != RoleContext {
		t.Fatalf("expected abstention, got %+v", claim)
	}
}
