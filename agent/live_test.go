//go:build live

package agent

// Run against a live rag/ (docker compose up in rag/): go test -tags live -run TestLiveRag -v
// The model is a stub that quotes the first passage, so this checks the rag client and the rules on real data.

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"os"
	"strings"
	"testing"
	"time"
)

type quotingProvider struct{ rag *RagClient }

func (q *quotingProvider) Name() string { return "stub-quoting-model" }

func (q *quotingProvider) Generate(ctx context.Context, system, user string) (Completion, error) {
	const header = "Twierdzenie do oceny:"
	start := strings.Index(user, header)
	end := strings.Index(user, "Dzisiejsza data")
	if start < 0 || end < 0 || end <= start {
		return Completion{}, errors.New("stub: judge user message has an unexpected layout")
	}
	claim := strings.TrimSpace(user[start+len(header) : end])
	search, err := q.rag.Search(ctx, claim, 5, false)
	if err != nil || len(search.Results) == 0 {
		return Completion{Text: `{"werdykt":"brak_dowodow","uzasadnienie":"Brak źródeł.","cytaty":[],"brakuje":"Brak publikacji.","podejrzane":false}`}, nil
	}
	first := search.Results[0]
	words := strings.Fields(first.Passage)
	quote := strings.Join(words[:min(12, len(words))], " ")
	answer := judgeAnswer{Verdict: "potwierdzone", Justification: "Źródło opisuje to zdarzenie.",
		Citations: []judgeCitation{{ID: first.ChunkID, Quote: quote, Role: "potwierdza"}}}
	encoded, _ := json.Marshal(answer)
	return Completion{Text: string(encoded)}, nil
}

func TestLiveRag(t *testing.T) {
	ragURL := os.Getenv("RAG_URL")
	if ragURL == "" {
		ragURL = defaultRagURL
	}
	config := Config{RagURL: ragURL, LLMBaseURL: "http://unused", LLMModel: "stub", MaxClaims: 3, SearchTopK: 5,
		VerifyTimeout: 25 * time.Second, RagTimeout: 8 * time.Second, LLMTimeout: 10 * time.Second, ExtractMaxText: 6000}
	rag := NewRagClient(ragURL, config.RagTimeout)
	a, err := New(config, &quotingProvider{rag: rag}, slog.New(slog.NewTextHandler(os.Stdout, nil)))
	if err != nil {
		t.Fatal(err)
	}
	for _, input := range []string{
		"Czy strefa buforowa na granicy polsko-białoruskiej została przedłużona?",
		"Kraje Europy, które pomagają Ukrainie, stoją na krawędzi bankructwa.",
		"Kto wygrał olimpiadę szachową w 1998 roku?",
	} {
		result, err := a.Verify(context.Background(), VerifyRequest{RequestID: "live", Channel: "test", Input: input, InputType: InputTypeText})
		if err != nil {
			t.Fatal(err)
		}
		encoded, _ := json.MarshalIndent(result, "", "  ")
		t.Logf("%s\n%s", input, encoded)
		if result.Status != StatusOK {
			t.Errorf("status %s for %q", result.Status, input)
		}
	}
	page, err := rag.Fetch(context.Background(), "https://www.gov.pl/web/rcb/raport-dobowy3")
	if err != nil {
		t.Fatalf("fetch: %v", err)
	}
	t.Logf("fetch: title=%q chars=%d truncated=%v", page.Title, len(page.Text), page.Truncated)
}
