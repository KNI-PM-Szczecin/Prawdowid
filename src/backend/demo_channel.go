package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"regexp"
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

var demoStrengthLabels = map[string]string{
	agent.StrengthStrong:   "silna",
	agent.StrengthModerate: "umiarkowana",
	agent.StrengthWeak:     "słaba",
	agent.StrengthNone:     "brak",
}

var lineBreakPattern = regexp.MustCompile(`[\r\n]+`)

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
		builder.WriteString(singleLine(claim.Text))
		builder.WriteString("\nWerdykt: ")
		builder.WriteString(verdictLabel(claim.Verdict))
		builder.WriteString("\nSiła podstawy: ")
		builder.WriteString(strengthLabel(claim.EvidenceStrength))
		builder.WriteString("\nUzasadnienie: ")
		builder.WriteString(singleLine(claim.Justification))
		if claim.Verdict == agent.VerdictInsufficientEvidence {
			builder.WriteString("\nSystem wstrzymuje się od oceny.")
		}
		if claim.Missing != nil && strings.TrimSpace(*claim.Missing) != "" {
			builder.WriteString("\nCzego nie udało się ustalić: ")
			builder.WriteString(singleLine(*claim.Missing))
		}
		for _, warning := range claim.Warnings {
			builder.WriteString("\nOstrzeżenie: ")
			builder.WriteString(singleLine(warning.Message))
		}
		builder.WriteString("\nŹródła:")
		if len(claim.Sources) == 0 {
			builder.WriteString(" brak")
		}
		for sourceIndex, source := range claim.Sources {
			builder.WriteString("\n")
			builder.WriteString(strconv.Itoa(sourceIndex + 1))
			builder.WriteString(". ")
			builder.WriteString(singleLine(source.Title))
			builder.WriteString(" — ")
			builder.WriteString(singleLine(source.Publisher))
			builder.WriteString("\n   ")
			builder.WriteString(singleLine(source.URL))
		}
	}
	if len(result.Limitations) > 0 {
		builder.WriteString("\n\nOgraniczenia:")
		for _, limitation := range result.Limitations {
			builder.WriteString("\n- ")
			builder.WriteString(singleLine(limitation))
		}
	}
	return []byte(builder.String()), nil
}

// singleLine turns line breaks into spaces so model or source text cannot start a fake line such as a source list.
func singleLine(text string) string {
	return strings.TrimSpace(lineBreakPattern.ReplaceAllString(text, " "))
}

func strengthLabel(strength string) string {
	if label, found := demoStrengthLabels[strength]; found {
		return label
	}
	return "nieokreślona"
}

func verdictLabel(verdict string) string {
	if label, found := demoVerdictLabels[verdict]; found {
		return label
	}
	return "Nieznany werdykt"
}
