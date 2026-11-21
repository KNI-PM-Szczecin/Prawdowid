package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"

	"prawdowid/agent"
)

const (
	demoChannelName     = "demo"
	demoFallbackMessage = "Nie udało się sprawdzić zgłoszenia."
)

var demoVerdictLabels = map[string]string{
	agent.VerdictConfirmed:            "Potwierdzone",
	agent.VerdictFalse:                "Fałszywe",
	agent.VerdictMisleading:           "Wprowadzające w błąd",
	agent.VerdictInsufficientEvidence: "Brak wystarczających dowodów",
	agent.VerdictNotVerifiable:        "Nie podlega weryfikacji",
}

// demoAdapter is the mock second channel (AGENTS.md priority 4): a real Discord adapter can replace it later.
type demoAdapter struct{}

func (demoAdapter) Name() string {
	return demoChannelName
}

type demoIncoming struct {
	Text string `json:"text"`
}

func (demoAdapter) ToRequest(incoming []byte) (agent.VerifyRequest, error) {
	decoder := json.NewDecoder(bytes.NewReader(incoming))
	decoder.DisallowUnknownFields()
	var message demoIncoming
	if err := decoder.Decode(&message); err != nil {
		return agent.VerifyRequest{}, fmt.Errorf("decode demo message: %w", err)
	}
	if reason := validateCheck(checkRequest{Input: message.Text, InputType: agent.InputTypeText}); reason != "" {
		return agent.VerifyRequest{}, fmt.Errorf("validate demo message: %s", reason)
	}
	return agent.VerifyRequest{
		Input:     strings.TrimSpace(message.Text),
		InputType: agent.InputTypeText,
	}, nil
}

func (demoAdapter) ToReply(result agent.CheckResult) ([]byte, error) {
	if result.Status != agent.StatusOK {
		if result.Message != nil && strings.TrimSpace(*result.Message) != "" {
			return []byte(*result.Message), nil
		}
		return []byte(demoFallbackMessage), nil
	}
	if len(result.Claims) == 0 {
		return []byte("Nie znalazłem twierdzeń do sprawdzenia."), nil
	}

	var builder strings.Builder
	for claimIndex, claim := range result.Claims {
		if claimIndex > 0 {
			builder.WriteString("\n\n")
		}
		builder.WriteString("Twierdzenie: ")
		builder.WriteString(claim.Text)
		builder.WriteString("\nWerdykt: ")
		builder.WriteString(verdictLabel(claim.Verdict))
		builder.WriteString("\nUzasadnienie: ")
		builder.WriteString(claim.Justification)
		if claim.Verdict == agent.VerdictInsufficientEvidence {
			builder.WriteString("\nSystem wstrzymuje się od oceny.")
		}
		if claim.Missing != nil && strings.TrimSpace(*claim.Missing) != "" {
			builder.WriteString("\nCzego nie udało się ustalić: ")
			builder.WriteString(*claim.Missing)
		}
		builder.WriteString("\nŹródła:")
		if len(claim.Sources) == 0 {
			builder.WriteString(" brak")
		}
		for sourceIndex, source := range claim.Sources {
			builder.WriteString("\n")
			builder.WriteString(strconv.Itoa(sourceIndex + 1))
			builder.WriteString(". ")
			builder.WriteString(source.Title)
			builder.WriteString(" — ")
			builder.WriteString(source.Publisher)
			builder.WriteString("\n   ")
			builder.WriteString(source.URL)
		}
	}
	return []byte(builder.String()), nil
}

func verdictLabel(verdict string) string {
	if label, found := demoVerdictLabels[verdict]; found {
		return label
	}
	return "Nieznany werdykt"
}
