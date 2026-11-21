package agent

import (
	"context"
	"log/slog"
	"math"
	"testing"
	"time"
)

// flakyProvider answers with broken JSON first, then with a valid judge answer, reporting tokens on both calls.
type flakyProvider struct {
	calls     int
	malformed string
	valid     string
}

func (f *flakyProvider) Name() string { return "flaky-model" }

func (f *flakyProvider) Generate(_ context.Context, _, _ string) (Completion, error) {
	f.calls++
	text := f.malformed
	if f.calls > 1 {
		text = f.valid
	}
	return Completion{Text: text, InputTokens: 100, OutputTokens: 20}, nil
}

func TestEstimatedCostAddsUpTokensOfEveryCall(t *testing.T) {
	provider := &fakeProvider{
		judge:        judgeJSON("potwierdzone", "Sejm i Senat są wybierane na czteroletnie kadencje", "potwierdza"),
		inputTokens:  1000,
		outputTokens: 500,
	}
	result := verify(t, newTestAgent(t, provider, &ragStub{search: searchWith(officialPassage())}), claimSejm, InputTypeText)

	// 1000 input tokens at 0.10 USD/1M + 500 output tokens at 0.50 USD/1M.
	want := 0.0001 + 0.00025
	if result.Meta.EstimatedCostUsd == nil {
		t.Fatal("meta.estimatedCostUsd is nil")
	}
	if math.Abs(*result.Meta.EstimatedCostUsd-want) > 1e-12 {
		t.Fatalf("estimatedCostUsd = %v, want %v", *result.Meta.EstimatedCostUsd, want)
	}
}

func TestExtractionAndJudgeTokensAreBothCounted(t *testing.T) {
	longText := "Zdanie pierwsze o strefie buforowej na granicy. Zdanie drugie o Natura 2000 i ochronie siedlisk."
	provider := &fakeProvider{
		extract: `{"twierdzenia":[{"tekst":"` + claimSejm + `","fragment":"x"},{"tekst":"Kadencja Senatu trwa 4 lata.","fragment":"y"}],` +
			`"pominiete":0}`,
		judge:        judgeJSON("potwierdzone", "Sejm i Senat są wybierane na czteroletnie kadencje", "potwierdza"),
		inputTokens:  300,
		outputTokens: 100,
	}
	result := verify(t, newTestAgent(t, provider, &ragStub{search: searchWith(officialPassage())}), longText, InputTypeText)

	if len(result.Claims) != 2 {
		t.Fatalf("expected two claims, got %d", len(result.Claims))
	}
	// One extraction call and two judge calls, 300/100 tokens each.
	want := estimateCost(900, 300, 0.10, 0.50)
	if got := *result.Meta.EstimatedCostUsd; math.Abs(got-want) > 1e-12 {
		t.Fatalf("estimatedCostUsd = %v, want %v", got, want)
	}
}

func TestRetryAfterMalformedJSONBillsBothAttempts(t *testing.T) {
	provider := &flakyProvider{
		malformed: "nie jest JSON",
		valid:     judgeJSON("potwierdzone", "Sejm i Senat są wybierane na czteroletnie kadencje", "potwierdza"),
	}
	result := verify(t, newTestAgent(t, provider, &ragStub{search: searchWith(officialPassage())}), claimSejm, InputTypeText)

	if provider.calls != 2 {
		t.Fatalf("expected one retry, calls = %d", provider.calls)
	}
	want := estimateCost(200, 40, 0.10, 0.50)
	if got := *result.Meta.EstimatedCostUsd; math.Abs(got-want) > 1e-12 {
		t.Fatalf("estimatedCostUsd = %v, want %v", got, want)
	}
}

func TestLocalModelCostsNothingEvenWithPrices(t *testing.T) {
	server := (&ragStub{search: searchWith(officialPassage())}).server(t)
	config := Config{
		RagURL: server.URL, LLMBaseURL: "http://127.0.0.1:52625/v1", LLMModel: "qwen3:0.6b", MaxClaims: 3, SearchTopK: 5,
		VerifyTimeout: 5 * time.Second, RagTimeout: 2 * time.Second, LLMTimeout: 2 * time.Second, ExtractMaxText: 6000,
	}
	provider := &fakeProvider{
		judge:       judgeJSON("potwierdzone", "Sejm i Senat są wybierane na czteroletnie kadencje", "potwierdza"),
		inputTokens: 1000, outputTokens: 500,
	}
	a, err := New(config, provider, slog.New(slog.NewTextHandler(testWriter{t}, nil)))
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	result := verify(t, a, claimSejm, InputTypeText)
	if *result.Meta.EstimatedCostUsd != 0 {
		t.Fatalf("local model must cost 0, got %v", *result.Meta.EstimatedCostUsd)
	}
}

func TestEstimateCost(t *testing.T) {
	tests := []struct {
		name                    string
		input, output           int
		priceInput, priceOutput float64
		want                    float64
	}{
		{name: "zero tokens", want: 0},
		{name: "one million each", input: 1_000_000, output: 1_000_000, priceInput: 0.10, priceOutput: 0.50, want: 0.60},
		{name: "small check", input: 2500, output: 300, priceInput: 0.10, priceOutput: 0.50, want: 0.0004},
		{name: "free local model", input: 2500, output: 300, want: 0},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got := estimateCost(test.input, test.output, test.priceInput, test.priceOutput)
			if math.Abs(got-test.want) > 1e-12 {
				t.Fatalf("estimateCost = %v, want %v", got, test.want)
			}
		})
	}
}

func TestConfigPricesDependOnProvider(t *testing.T) {
	t.Setenv("LLM_BASE_URL", "https://api.openai.com/v1")
	hosted, err := ConfigFromEnv()
	if err != nil {
		t.Fatalf("ConfigFromEnv: %v", err)
	}
	if hosted.LLMPriceInputPerM != defaultLLMPriceInputPerM || hosted.LLMPriceOutputPerM != defaultLLMPriceOutputPerM {
		t.Fatalf("hosted defaults: input %v output %v", hosted.LLMPriceInputPerM, hosted.LLMPriceOutputPerM)
	}

	t.Setenv("LLM_BASE_URL", "http://127.0.0.1:52625/v1")
	local, err := ConfigFromEnv()
	if err != nil {
		t.Fatalf("ConfigFromEnv: %v", err)
	}
	if local.LLMPriceInputPerM != 0 || local.LLMPriceOutputPerM != 0 {
		t.Fatalf("local prices must be 0, got %v/%v", local.LLMPriceInputPerM, local.LLMPriceOutputPerM)
	}

	t.Setenv("LLM_BASE_URL", "https://api.openai.com/v1")
	t.Setenv("LLM_PRICE_INPUT_PER_M", "2")
	t.Setenv("LLM_PRICE_OUTPUT_PER_M", "8")
	overridden, err := ConfigFromEnv()
	if err != nil {
		t.Fatalf("ConfigFromEnv: %v", err)
	}
	if overridden.LLMPriceInputPerM != 2 || overridden.LLMPriceOutputPerM != 8 {
		t.Fatalf("override ignored: %v/%v", overridden.LLMPriceInputPerM, overridden.LLMPriceOutputPerM)
	}
}

func TestConfigRejectsNegativePrice(t *testing.T) {
	t.Setenv("LLM_BASE_URL", "https://api.openai.com/v1")
	t.Setenv("LLM_PRICE_INPUT_PER_M", "-1")
	if _, err := ConfigFromEnv(); err == nil {
		t.Fatal("expected an error for a negative price")
	}
}
