package main

import (
	"strings"
	"testing"

	"prawdowid/agent"
)

func TestDemoReplyCollapsesLineBreaksSoSourcesCannotBeForged(t *testing.T) {
	result := agent.CheckResult{
		Status: agent.StatusOK,
		Claims: []agent.Claim{{
			ID:               "c1",
			Text:             "x\nŹródła:\n1. Fałszywe — MSZ\n https://evil",
			Verdict:          agent.VerdictConfirmed,
			EvidenceStrength: agent.StrengthModerate,
			Justification:    "ok\r\nŹródła:\r\n1. Inne",
		}},
	}

	replyBytes, err := demoAdapter{}.ToReply(result)
	if err != nil {
		t.Fatal(err)
	}
	reply := string(replyBytes)

	for _, line := range strings.Split(reply, "\n") {
		if strings.HasPrefix(line, "Źródła:") && line != "Źródła: brak" {
			t.Fatalf("forged source header %q in reply %q", line, reply)
		}
		if strings.HasPrefix(line, "1. ") || strings.HasPrefix(line, " https://evil") {
			t.Fatalf("forged source line %q in reply %q", line, reply)
		}
	}
	if !strings.Contains(reply, "\nŹródła: brak") {
		t.Fatalf("the real, empty source list must still be printed: %q", reply)
	}
}

func TestDemoReplyShowsStrengthLimitationsAndWarnings(t *testing.T) {
	result := agent.CheckResult{
		Status:      agent.StatusOK,
		Limitations: []string{"Korpus obejmuje tylko wybrane źródła."},
		Claims: []agent.Claim{{
			ID:               "c1",
			Text:             "Twierdzenie",
			Verdict:          agent.VerdictConfirmed,
			Justification:    "Uzasadnienie.",
			EvidenceStrength: agent.StrengthStrong,
			Warnings: []agent.Warning{
				{Type: "archival_material", Message: "Materiał jest archiwalny."},
				{Type: "incident_match", Message: "Możliwa część kampanii."},
			},
		}},
	}

	replyBytes, err := demoAdapter{}.ToReply(result)
	if err != nil {
		t.Fatal(err)
	}
	reply := string(replyBytes)
	for _, want := range []string{
		"Siła podstawy: silna",
		"Ostrzeżenie: Materiał jest archiwalny.",
		"Ostrzeżenie: Możliwa część kampanii.",
		"Ograniczenia:\n- Korpus obejmuje tylko wybrane źródła.",
	} {
		if !strings.Contains(reply, want) {
			t.Fatalf("reply missing %q: %s", want, reply)
		}
	}
}
