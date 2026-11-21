package agent

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

const (
	claimSejm     = "Kadencja Sejmu trwa 4 lata."
	officialChunk = "11111111-1111-1111-1111-111111111111"
	factcheckChk  = "22222222-2222-2222-2222-222222222222"
	newsChunk     = "33333333-3333-3333-3333-333333333333"
)

var fixedNow = time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)

// fakeProvider answers by prompt kind: the judge prompt mentions <dostepne_zrodla>, the extractor <tekst>.
type fakeProvider struct {
	judge   string
	extract string
	err     error
	calls   []string
}

func (f *fakeProvider) Name() string { return "fake-model" }

func (f *fakeProvider) Generate(_ context.Context, system, user string) (Completion, error) {
	if f.err != nil {
		return Completion{}, f.err
	}
	if strings.Contains(system, "Wyodrębniasz") {
		f.calls = append(f.calls, "extract")
		return Completion{Text: f.extract}, nil
	}
	if strings.Contains(system, "<dostepne_zrodla>") && strings.Contains(user, "<dostepne_zrodla>") {
		f.calls = append(f.calls, "judge")
		return Completion{Text: f.judge}, nil
	}
	return Completion{}, errors.New("unexpected prompt")
}

func officialPassage() Passage {
	published := "2026-03-01T00:00:00Z"
	return Passage{
		DocumentID: "isap-konstytucja", Title: "Konstytucja RP", Publisher: "ISAP", PublishedAt: &published,
		FetchedAt: "2026-11-20T00:00:00Z", URL: "https://isap.sejm.gov.pl/x", SourceType: SourceTypeOfficial,
		Passage: "Art. 98. 1. Sejm i Senat są wybierane na czteroletnie kadencje. Kadencje Sejmu i Senatu rozpoczynają się z dniem zebrania się Sejmu.",
		Score:   0.9, Flags: []string{}, ChunkID: officialChunk, Tier: 1, Reliability: "high",
	}
}

func factcheckPassage() Passage {
	return Passage{
		DocumentID: "factcheck:1", Title: "Demagog o kadencji", Publisher: "Demagog", FetchedAt: "2026-11-21T00:00:00Z",
		URL: "https://demagog.org.pl/x", SourceType: SourceTypeFactcheck,
		Passage: "Twierdzenie sprawdzone przez weryfikatora faktów: Kadencja Sejmu trwa 4 lata. Ocena weryfikatora (Demagog): Fałsz. Tytuł weryfikacji: Nie 4, a 5 lat.",
		Score:   0.8, Flags: []string{}, ChunkID: factcheckChk, Tier: 2, Reliability: "medium",
	}
}

func newsPassage(flags ...string) Passage {
	if flags == nil {
		flags = []string{}
	}
	return Passage{
		DocumentID: "portal-1", Title: "Aktualności", Publisher: "Portal", FetchedAt: "2026-11-21T00:00:00Z",
		URL: "https://portal.example/x", SourceType: SourceTypeSecondary,
		Passage: "Według naszych informacji kadencja Sejmu trwa cztery lata, a wybory odbywają się jesienią.",
		Score:   0.7, Flags: flags, ChunkID: newsChunk, Tier: 3, Reliability: "low",
	}
}

type ragStub struct {
	search       SearchResponse
	searchStatus int
	fetch        FetchResponse
	fetchStatus  int
	queries      []string
}

func (s *ragStub) server(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("POST /search", func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		s.queries = append(s.queries, body["query"].(string))
		if s.searchStatus != 0 && s.searchStatus != http.StatusOK {
			w.WriteHeader(s.searchStatus)
			_, _ = w.Write([]byte(`{"error":{"code":"index_unavailable","message":"x"}}`))
			return
		}
		_ = json.NewEncoder(w).Encode(s.search)
	})
	mux.HandleFunc("POST /fetch", func(w http.ResponseWriter, r *http.Request) {
		if s.fetchStatus != 0 && s.fetchStatus != http.StatusOK {
			w.WriteHeader(s.fetchStatus)
			_, _ = w.Write([]byte(`{"detail":"Nie udało się pobrać strony: anti-bot wall."}`))
			return
		}
		_ = json.NewEncoder(w).Encode(s.fetch)
	})
	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)
	return server
}

func searchWith(passages ...Passage) SearchResponse {
	return SearchResponse{
		Results:         passages,
		CorpusVersion:   "corpus-test",
		ContextXML:      "<dostepne_zrodla>\n...\n</dostepne_zrodla>",
		ExternalSources: []ExternalSourceStatus{{Name: externalSourceFactcheck, Status: "ok"}},
	}
}

func newTestAgent(t *testing.T, provider LLMProvider, rag *ragStub) *Agent {
	t.Helper()
	server := rag.server(t)
	config := Config{
		RagURL: server.URL, LLMBaseURL: "http://unused", LLMModel: "fake-model", MaxClaims: 3, SearchTopK: 5,
		VerifyTimeout: 5 * time.Second, RagTimeout: 2 * time.Second, LLMTimeout: 2 * time.Second, ExtractMaxText: 6000,
	}
	a, err := New(config, provider, slog.New(slog.NewTextHandler(testWriter{t}, nil)))
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	a.now = func() time.Time { return fixedNow }
	return a
}

type testWriter struct{ t *testing.T }

func (w testWriter) Write(p []byte) (int, error) {
	w.t.Log(strings.TrimSpace(string(p)))
	return len(p), nil
}

func verify(t *testing.T, a *Agent, input, inputType string) CheckResult {
	t.Helper()
	result, err := a.Verify(context.Background(), VerifyRequest{RequestID: "r1", Channel: "web", Input: input, InputType: inputType})
	if err != nil {
		t.Fatalf("Verify returned error: %v", err)
	}
	return result
}

func judgeJSON(verdict, quote, role string) string {
	return `{"werdykt":"` + verdict + `","uzasadnienie":"Konstytucja mówi wprost o czteroletniej kadencji.","cytaty":[{"id":"` +
		officialChunk + `","cytat":"` + quote + `","rola":"` + role + `"}],"brakuje":null,"podejrzane":false}`
}

func TestConfirmedWithOfficialSourceAndVerbatimQuote(t *testing.T) {
	provider := &fakeProvider{judge: judgeJSON("potwierdzone", "Sejm i Senat są wybierane na czteroletnie kadencje", "potwierdza")}
	rag := &ragStub{search: searchWith(officialPassage())}
	result := verify(t, newTestAgent(t, provider, rag), claimSejm, InputTypeText)

	if result.Status != StatusOK || len(result.Claims) != 1 {
		t.Fatalf("unexpected result: %+v", result)
	}
	claim := result.Claims[0]
	if claim.Verdict != VerdictConfirmed || claim.EvidenceStrength != StrengthStrong {
		t.Fatalf("verdict %s strength %s", claim.Verdict, claim.EvidenceStrength)
	}
	if len(claim.Sources) != 1 || claim.Sources[0].Role != RoleSupports || claim.Sources[0].ID != officialChunk {
		t.Fatalf("sources: %+v", claim.Sources)
	}
	if provider.calls[0] != "judge" || len(provider.calls) != 1 {
		t.Fatalf("single statement must skip extraction, calls=%v", provider.calls)
	}
	if rag.queries[0] != claimSejm || *result.Meta.CorpusVersion != "corpus-test" || result.Meta.Abstained {
		t.Fatalf("meta/query: %+v %v", result.Meta, rag.queries)
	}
}

func TestFabricatedQuoteIsDroppedAndVerdictDowngraded(t *testing.T) {
	provider := &fakeProvider{judge: judgeJSON("potwierdzone", "Kadencja Sejmu trwa dokładnie cztery lata i ani dnia dłużej", "potwierdza")}
	result := verify(t, newTestAgent(t, provider, &ragStub{search: searchWith(officialPassage())}), claimSejm, InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictInsufficientEvidence || len(claim.Sources) != 0 || claim.Missing == nil {
		t.Fatalf("expected abstention without sources, got %+v", claim)
	}
	if !result.Meta.Abstained {
		t.Fatal("meta.abstained should be true")
	}
}

func TestSingleSecondarySourceIsNotEnoughForFalse(t *testing.T) {
	judge := `{"werdykt":"falszywe","uzasadnienie":"Portal twierdzi inaczej.","cytaty":[{"id":"` + newsChunk +
		`","cytat":"kadencja Sejmu trwa cztery lata","rola":"obala"}],"brakuje":null,"podejrzane":false}`
	result := verify(t, newTestAgent(t, &fakeProvider{judge: judge}, &ragStub{search: searchWith(newsPassage())}), claimSejm, InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictInsufficientEvidence || claim.EvidenceStrength != StrengthModerate || len(claim.Sources) != 1 {
		t.Fatalf("expected downgrade with the source kept as context, got %+v", claim)
	}
}

func TestFactcheckerRatingOverridesModelVerdict(t *testing.T) {
	judge := `{"werdykt":"potwierdzone","uzasadnienie":"Demagog to sprawdzał.","cytaty":[{"id":"` + factcheckChk +
		`","cytat":"Ocena weryfikatora (Demagog): Fałsz","rola":"potwierdza"}],"brakuje":null,"podejrzane":false}`
	result := verify(t, newTestAgent(t, &fakeProvider{judge: judge}, &ragStub{search: searchWith(factcheckPassage())}), claimSejm, InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictFalse {
		t.Fatalf("fact-checker rating must win, got %s", claim.Verdict)
	}
	if len(result.Limitations) == 0 || !strings.Contains(result.Limitations[0], "Demagog") {
		t.Fatalf("expected a limitation naming the fact-checker, got %v", result.Limitations)
	}
}

func TestNoResultsAbstainsWithoutCallingTheModel(t *testing.T) {
	provider := &fakeProvider{judge: "should not be used"}
	result := verify(t, newTestAgent(t, provider, &ragStub{search: searchWith()}), "Wczoraj w Pcimiu otwarto elektrownię termojądrową.", InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictInsufficientEvidence || claim.Missing == nil || *claim.Missing != missingNoSources {
		t.Fatalf("unexpected claim: %+v", claim)
	}
	if len(provider.calls) != 0 {
		t.Fatalf("model must not be called without evidence, calls=%v", provider.calls)
	}
}

func TestRagOutageIsTechnicalError(t *testing.T) {
	result := verify(t, newTestAgent(t, &fakeProvider{}, &ragStub{searchStatus: http.StatusServiceUnavailable}), claimSejm, InputTypeText)
	if result.Status != StatusTechnicalError || result.Message == nil || len(result.Claims) != 0 {
		t.Fatalf("expected technical_error, got %+v", result)
	}
}

func TestModelOutageIsTechnicalError(t *testing.T) {
	provider := &fakeProvider{err: ErrLLMUnavailable}
	result := verify(t, newTestAgent(t, provider, &ragStub{search: searchWith(officialPassage())}), claimSejm, InputTypeText)
	if result.Status != StatusTechnicalError {
		t.Fatalf("expected technical_error, got %s", result.Status)
	}
}

func TestMalformedModelAnswerFallsBackToAbstention(t *testing.T) {
	provider := &fakeProvider{judge: "Oto moja ocena: twierdzenie jest prawdziwe."}
	result := verify(t, newTestAgent(t, provider, &ragStub{search: searchWith(officialPassage())}), claimSejm, InputTypeText)
	claim := result.Claims[0]
	if result.Status != StatusOK || claim.Verdict != VerdictInsufficientEvidence {
		t.Fatalf("expected ok with abstention, got %s / %+v", result.Status, claim)
	}
	if len(provider.calls) != 2 {
		t.Fatalf("expected one retry, calls=%v", provider.calls)
	}
}

func TestInjectionFlagsAndCampaignAlertAreContextOnly(t *testing.T) {
	search := searchWith(officialPassage(), newsPassage(flagSuspectedInjection))
	search.CampaignAlert = &ragCampaignAlert{
		Category: "possible_disinformation_campaign", Message: "Podobne twierdzenie pojawiło się w znanej kampanii.",
		Matches: []ragCampaignMatch{{CampaignMatch: CampaignMatch{IncidentID: "1", Source: "euvsdisinfo", Title: "t", Summary: "s", URL: "https://euvsdisinfo.eu/1"}, Score: 0.8}},
	}
	provider := &fakeProvider{judge: judgeJSON("potwierdzone", "Sejm i Senat są wybierane na czteroletnie kadencje", "potwierdza")}
	result := verify(t, newTestAgent(t, provider, &ragStub{search: search}), claimSejm, InputTypeText)

	claim := result.Claims[0]
	if claim.Verdict != VerdictConfirmed {
		t.Fatalf("campaign alert must not change the verdict, got %s", claim.Verdict)
	}
	if result.Meta.InjectionAttempts != 1 {
		t.Fatalf("injectionAttempts = %d", result.Meta.InjectionAttempts)
	}
	types := map[string]bool{}
	for _, warning := range claim.Warnings {
		types[warning.Type] = true
	}
	if !types[WarningIncidentMatch] || !types[WarningOther] {
		t.Fatalf("warnings: %+v", claim.Warnings)
	}
	if result.CampaignAlert == nil || len(result.CampaignAlert.Matches) != 1 {
		t.Fatalf("campaignAlert missing: %+v", result.CampaignAlert)
	}
}

func TestLongTextGoesThroughExtractionAndReportsSkippedClaims(t *testing.T) {
	extract := `{"twierdzenia":[{"tekst":"Kadencja Sejmu trwa 4 lata.","fragment":"Kadencja Sejmu trwa 4 lata."},{"tekst":"Senat ma 100 senatorów.","fragment":"Senat ma 100 senatorów."}],"pominiete":2}`
	provider := &fakeProvider{extract: extract, judge: judgeJSON("potwierdzone", "Sejm i Senat są wybierane na czteroletnie kadencje", "potwierdza")}
	rag := &ragStub{search: searchWith(officialPassage())}
	longText := "Kadencja Sejmu trwa 4 lata. Senat ma 100 senatorów. Poza tym wczoraj padał deszcz. Myślę, że będzie lepiej."
	result := verify(t, newTestAgent(t, provider, rag), longText, InputTypeText)

	if len(result.Claims) != 2 || provider.calls[0] != "extract" {
		t.Fatalf("expected 2 claims via extraction, got %d (%v)", len(result.Claims), provider.calls)
	}
	if rag.queries[1] != "Senat ma 100 senatorów." {
		t.Fatalf("second query: %q", rag.queries[1])
	}
	if len(result.Limitations) == 0 || !strings.Contains(result.Limitations[0], "Sprawdzono 2") {
		t.Fatalf("expected skipped-claims limitation, got %v", result.Limitations)
	}
}

func TestURLInputIsFetchedThroughRag(t *testing.T) {
	provider := &fakeProvider{judge: judgeJSON("potwierdzone", "Sejm i Senat są wybierane na czteroletnie kadencje", "potwierdza")}
	rag := &ragStub{search: searchWith(officialPassage()), fetch: FetchResponse{URL: "https://example.gov.pl/a", Title: "Tytuł", Text: claimSejm}}
	result := verify(t, newTestAgent(t, provider, rag), "https://example.gov.pl/a", InputTypeURL)

	if result.Status != StatusOK || result.Document == nil || *result.Document.Title != "Tytuł" {
		t.Fatalf("expected document from fetch, got %+v", result)
	}
	if len(result.Claims) != 1 {
		t.Fatalf("claims: %+v", result.Claims)
	}
}

func TestUnreadablePageIsNeedsClarification(t *testing.T) {
	rag := &ragStub{fetchStatus: http.StatusUnprocessableEntity}
	result := verify(t, newTestAgent(t, &fakeProvider{}, rag), "https://ulc.gov.pl/x", InputTypeURL)
	if result.Status != StatusNeedsClarification || result.Message == nil {
		t.Fatalf("expected needs_clarification, got %+v", result)
	}
}

func TestEmptyInputIsNeedsClarification(t *testing.T) {
	result := verify(t, newTestAgent(t, &fakeProvider{}, &ragStub{}), "   ", InputTypeText)
	if result.Status != StatusNeedsClarification {
		t.Fatalf("got %s", result.Status)
	}
}

func TestQuoteMatchingIgnoresTypographyAndCase(t *testing.T) {
	passage := "Minister powiedział: „Strefa buforowa zostaje – do odwołania”."
	if !quoteInPassage("strefa buforowa zostaje - do odwołania", passage) {
		t.Fatal("quote with plain quotes and dash should match")
	}
	if quoteInPassage("strefa", passage) {
		t.Fatal("very short quotes must be rejected")
	}
}

func TestFactcheckVerdictMapping(t *testing.T) {
	cases := map[string]string{
		"Ocena weryfikatora (Demagog): Fałsz.":              VerdictFalse,
		"Ocena weryfikatora (Demagog): Częściowa prawda.":   VerdictMisleading,
		"Ocena weryfikatora (AFP): Prawda.":                 VerdictConfirmed,
		"Ocena weryfikatora (Demagog): Manipulacja. Dalej.": VerdictMisleading,
		"Ocena weryfikatora (Konkret24): Nieweryfikowalne.": VerdictNotVerifiable,
	}
	for text, want := range cases {
		if _, got, ok := factcheckVerdict(text); !ok || got != want {
			t.Errorf("%q -> %q (ok=%v), want %q", text, got, ok, want)
		}
	}
	if _, _, ok := factcheckVerdict("Ocena weryfikatora (X): Dziwna etykieta."); ok {
		t.Error("unknown rating must not map")
	}
}

func TestFirstJSONObjectSkipsSurroundingText(t *testing.T) {
	object, ok := firstJSONObject("Odpowiedź: {\"a\":{\"b\":\"x}y\"}} koniec")
	if !ok || object != `{"a":{"b":"x}y"}}` {
		t.Fatalf("got %q ok=%v", object, ok)
	}
}
