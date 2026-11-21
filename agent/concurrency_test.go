package agent

import (
	"context"
	"errors"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

const fiveClaims = "Kadencja Sejmu trwa 4 lata. Senat ma 100 senatorów. Polska ma 16 województw. " +
	"Warszawa jest stolicą Polski. Bałtyk jest morzem."

const fiveClaimsJSON = `{"twierdzenia":[` +
	`{"tekst":"Kadencja Sejmu trwa 4 lata.","fragment":"a"},` +
	`{"tekst":"Senat ma 100 senatorów.","fragment":"b"},` +
	`{"tekst":"Polska ma 16 województw.","fragment":"c"},` +
	`{"tekst":"Warszawa jest stolicą Polski.","fragment":"d"},` +
	`{"tekst":"Bałtyk jest morzem.","fragment":"e"}],"pominiete":0}`

// countingProvider records how many judge calls overlap, so a sequential loop fails the test without timing luck.
type countingProvider struct {
	inFlight atomic.Int32
	peak     atomic.Int32
	delay    time.Duration
	failOn   string
}

func (p *countingProvider) Name() string { return "counting-model" }

func (p *countingProvider) Generate(_ context.Context, system, user string) (Completion, error) {
	current := p.inFlight.Add(1)
	defer p.inFlight.Add(-1)
	for {
		old := p.peak.Load()
		if current <= old || p.peak.CompareAndSwap(old, current) {
			break
		}
	}
	if strings.Contains(system, "Wyodrębniasz") {
		return Completion{Text: fiveClaimsJSON}, nil
	}
	if p.failOn != "" && strings.Contains(user, p.failOn) {
		return Completion{}, errors.New("model failure")
	}
	time.Sleep(p.delay)
	return Completion{
		Text:        judgeJSON("potwierdzone", "Sejm i Senat są wybierane na czteroletnie kadencje", "potwierdza"),
		InputTokens: 100, OutputTokens: 20,
	}, nil
}

func newAgentWithClaims(t *testing.T, provider LLMProvider, maxClaims int) *Agent {
	t.Helper()
	server := (&ragStub{search: searchWith(officialPassage())}).server(t)
	config := Config{
		RagURL: server.URL, LLMBaseURL: "http://unused", LLMModel: "fake-model", MaxClaims: maxClaims, SearchTopK: 5,
		VerifyTimeout: 5 * time.Second, RagTimeout: 2 * time.Second, LLMTimeout: 2 * time.Second, ExtractMaxText: 6000,
		LLMPriceInputPerM: 0.10, LLMPriceOutputPerM: 0.50,
	}
	a, err := New(config, provider, nil)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	a.now = func() time.Time { return fixedNow }
	return a
}

func TestClaimsAreCheckedInParallelUpToTheLimit(t *testing.T) {
	provider := &countingProvider{delay: 80 * time.Millisecond}
	agent := newAgentWithClaims(t, provider, 5)

	result := verify(t, agent, fiveClaims, InputTypeText)

	if len(result.Claims) != 5 {
		t.Fatalf("expected 5 claims, got %d", len(result.Claims))
	}
	if peak := provider.peak.Load(); peak < 2 || peak > claimConcurrency {
		t.Fatalf("parallel judge calls peaked at %d, want 2..%d", peak, claimConcurrency)
	}
	// The answer keeps the extraction order even though the searches finish in a different order.
	for index, claim := range result.Claims {
		if claim.ID != "c"+string(rune('1'+index)) {
			t.Fatalf("claim %d has id %s", index, claim.ID)
		}
	}
	if result.Claims[0].Text != "Kadencja Sejmu trwa 4 lata." || result.Claims[4].Text != "Bałtyk jest morzem." {
		t.Fatalf("claims out of order: %+v", result.Claims)
	}
	if result.Meta.RetrievedPassages != 5 {
		t.Fatalf("retrievedPassages = %d, want 5", result.Meta.RetrievedPassages)
	}
	if *result.Meta.EstimatedCostUsd <= 0 {
		t.Fatalf("estimatedCostUsd = %v, want > 0", *result.Meta.EstimatedCostUsd)
	}
}

func TestFailureInOneClaimStillReturnsTechnicalErrorWithoutClaims(t *testing.T) {
	provider := &countingProvider{delay: 10 * time.Millisecond, failOn: "Senat ma 100 senatorów."}
	agent := newAgentWithClaims(t, provider, 5)

	result := verify(t, agent, fiveClaims, InputTypeText)

	if result.Status != StatusTechnicalError || len(result.Claims) != 0 {
		t.Fatalf("status %s with %d claims", result.Status, len(result.Claims))
	}
}
