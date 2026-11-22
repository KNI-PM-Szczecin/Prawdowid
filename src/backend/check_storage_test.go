package main

import (
	"strings"
	"testing"

	"prawdowid/agent"
)

func TestMaskResultForStorageHidesPersonalDataInDocumentAndCutsIt(t *testing.T) {
	title := "Kontakt: anna@example.org"
	long := strings.Repeat("a", maxStoredDocumentRunes+100)
	result := agent.CheckResult{
		Status:   agent.StatusOK,
		Document: &agent.Document{Title: &title, Text: "Zadzwoń 600 700 800. " + long},
		Claims:   []agent.Claim{{Text: "PESEL 44051401359 to przykład"}},
	}

	stored := maskResultForStorage(result)

	if strings.Contains(stored.Document.Text, "600 700 800") || strings.Contains(*stored.Document.Title, "anna@example.org") {
		t.Fatalf("personal data reached the stored document: %+v", stored.Document)
	}
	if got := len([]rune(stored.Document.Text)); got > maxStoredDocumentRunes || !strings.HasSuffix(stored.Document.Text, "…") {
		t.Fatalf("stored document should be cut to at most %d runes with an ellipsis, got %d", maxStoredDocumentRunes, got)
	}
	if strings.Contains(stored.Claims[0].Text, "44051401359") {
		t.Fatalf("claim text not masked: %q", stored.Claims[0].Text)
	}
	if !strings.Contains(result.Document.Text, "600 700 800") || len([]rune(result.Document.Text)) <= maxStoredDocumentRunes {
		t.Fatal("the answer for the user must stay unchanged")
	}
}
