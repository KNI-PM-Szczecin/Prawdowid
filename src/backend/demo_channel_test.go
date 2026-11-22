package main

import (
	"context"
	"net/http"
	"reflect"
	"strings"
	"testing"

	"prawdowid/agent"
)

type captureAdapter struct {
	ChannelAdapter
	result agent.CheckResult
	called bool
}

func (a *captureAdapter) ToReply(result agent.CheckResult) ([]byte, error) {
	a.result = result
	a.called = true
	return a.ChannelAdapter.ToReply(result)
}

func TestDemoToRequestUsesTextInput(t *testing.T) {
	request, err := demoAdapter{}.ToRequest([]byte(`{"text":"  Polska jest w UE  "}`))
	if err != nil {
		t.Fatal(err)
	}
	if request.Input != "Polska jest w UE" || request.InputType != agent.InputTypeText {
		t.Fatalf("unexpected request: %+v", request)
	}
}

func TestDemoAndWebGiveSameVerdictsAndSources(t *testing.T) {
	published := "2026-11-01T00:00:00Z"
	verify := func(_ context.Context, request agent.VerifyRequest) (agent.CheckResult, error) {
		return agent.CheckResult{
			RequestID: request.RequestID,
			Status:    agent.StatusOK,
			Claims: []agent.Claim{{
				ID:               "c1",
				Text:             request.Input,
				Verdict:          agent.VerdictFalse,
				Justification:    "Źródła przeczą temu twierdzeniu.",
				EvidenceStrength: agent.StrengthStrong,
				Sources: []agent.SourceRef{{
					ID:          "s1",
					Title:       "Tytuł źródła",
					Publisher:   "Wydawca",
					PublishedAt: &published,
					FetchedAt:   "2026-11-21T10:00:00Z",
					URL:         "https://example.gov.pl/a",
					SourceType:  agent.SourceTypeOfficial,
					Role:        agent.RoleRefutes,
					Quote:       "cytat",
				}},
			}},
		}, nil
	}

	checks, saved := newTestHandlers(verify, 10)
	webRecorder := postCheck(checks, `{"input":"To samo twierdzenie","inputType":"text"}`)
	if webRecorder.Code != http.StatusOK {
		t.Fatalf("web status %d, body %s", webRecorder.Code, webRecorder.Body.String())
	}
	webResult := decodeResult(t, webRecorder)

	demo := &captureAdapter{ChannelAdapter: demoAdapter{}}
	demoRecorder := postDemo(newChannelHandler(checks, demo), `{"text":"To samo twierdzenie"}`)
	if demoRecorder.Code != http.StatusOK {
		t.Fatalf("demo status %d, body %s", demoRecorder.Code, demoRecorder.Body.String())
	}
	if !demo.called {
		t.Fatal("demo reply was not built")
	}
	if !reflect.DeepEqual(webResult.Claims, demo.result.Claims) {
		t.Fatalf("claims differ:\nweb  %+v\ndemo %+v", webResult.Claims, demo.result.Claims)
	}

	if len(*saved) != 2 {
		t.Fatalf("stored runs %d, want 2", len(*saved))
	}
	if (*saved)[0].Channel != webChannel || (*saved)[1].Channel != demoChannelName {
		t.Fatalf("channels %q and %q", (*saved)[0].Channel, (*saved)[1].Channel)
	}
	if (*saved)[0].Input != (*saved)[1].Input || (*saved)[0].InputType != (*saved)[1].InputType {
		t.Fatalf("inputs differ: %+v and %+v", (*saved)[0], (*saved)[1])
	}

	reply := demoRecorder.Body.String()
	for _, want := range []string{"Fałszywe", "Tytuł źródła", "Wydawca", "https://example.gov.pl/a"} {
		if !strings.Contains(reply, want) {
			t.Fatalf("reply missing %q: %s", want, reply)
		}
	}
}

func TestDemoReplyListsSourcesOutsideJustification(t *testing.T) {
	published := "2026-11-01T00:00:00Z"
	result := agent.CheckResult{
		RequestID: "r1",
		Status:    agent.StatusOK,
		Claims: []agent.Claim{{
			ID:            "c1",
			Text:          "Twierdzenie",
			Verdict:       agent.VerdictConfirmed,
			Justification: "To jest uzasadnienie.",
			Sources: []agent.SourceRef{{
				Title:       "Tytuł źródła",
				Publisher:   "Wydawca",
				PublishedAt: &published,
				URL:         "https://example.gov.pl/a",
			}},
		}},
	}

	replyBytes, err := demoAdapter{}.ToReply(result)
	if err != nil {
		t.Fatal(err)
	}
	reply := string(replyBytes)

	var justificationLine string
	for _, line := range strings.Split(reply, "\n") {
		if strings.HasPrefix(line, "Uzasadnienie:") {
			justificationLine = line
			break
		}
	}
	if justificationLine == "" {
		t.Fatalf("no justification line in %q", reply)
	}
	for _, forbidden := range []string{"Tytuł źródła", "Wydawca", "https://example.gov.pl/a"} {
		if strings.Contains(justificationLine, forbidden) {
			t.Fatalf("source %q leaked into justification line %q", forbidden, justificationLine)
		}
	}
	for _, want := range []string{"Źródła:", "Tytuł źródła", "Wydawca", "https://example.gov.pl/a"} {
		if !strings.Contains(reply, want) {
			t.Fatalf("reply missing %q: %s", want, reply)
		}
	}
}

func TestDemoReplyShowsMaterialMatchWithBasisOutsideVerdict(t *testing.T) {
	result := agent.CheckResult{
		RequestID: "r1",
		Status:    agent.StatusOK,
		MaterialMatch: &agent.MaterialMatch{
			Message: "Tytuł i data publikacji zgadzają się z materiałem w naszych źródłach.",
			Matches: []agent.MaterialMatchItem{{
				Kind: agent.MaterialKindCorpusDocument, Basis: []string{agent.MaterialBasisTitle, agent.MaterialBasisDate},
				Title: "Depesza PAP", Publisher: "PAP", URL: "https://pap.pl/depesza",
			}},
		},
		Claims: []agent.Claim{{ID: "c1", Text: "Twierdzenie", Verdict: agent.VerdictInsufficientEvidence, Justification: "Brak źródeł."}},
	}
	replyBytes, err := demoAdapter{}.ToReply(result)
	if err != nil {
		t.Fatal(err)
	}
	reply := string(replyBytes)
	for _, want := range []string{"Znamy ten materiał", "Depesza PAP", "zgodny tytuł, zgodna data publikacji", "https://pap.pl/depesza", "Brak wystarczających dowodów"} {
		if !strings.Contains(reply, want) {
			t.Fatalf("reply missing %q: %s", want, reply)
		}
	}
}

func TestDemoReplyNonOKStatusIsOnlyMessage(t *testing.T) {
	message := "Dopisz, co chcesz sprawdzić."
	for _, status := range []string{agent.StatusNeedsClarification, agent.StatusOutOfScope, agent.StatusTechnicalError} {
		reply, err := demoAdapter{}.ToReply(agent.CheckResult{Status: status, Message: &message})
		if err != nil {
			t.Fatal(err)
		}
		if got := strings.TrimSpace(string(reply)); got != message {
			t.Fatalf("status %s: got %q, want %q", status, got, message)
		}
	}
}

func TestDemoReplyStatesAbstentionHonestly(t *testing.T) {
	missing := "Brak komunikatu urzędu."
	result := agent.CheckResult{
		RequestID: "r1",
		Status:    agent.StatusOK,
		Claims: []agent.Claim{{
			ID:            "c1",
			Text:          "Nowe twierdzenie",
			Verdict:       agent.VerdictInsufficientEvidence,
			Justification: "Nie znalazłem wystarczających źródeł.",
			Missing:       &missing,
		}},
	}

	replyBytes, err := demoAdapter{}.ToReply(result)
	if err != nil {
		t.Fatal(err)
	}
	reply := string(replyBytes)

	for _, want := range []string{
		"Brak wystarczających dowodów",
		"System wstrzymuje się od oceny.",
		"Brak komunikatu urzędu.",
		"Źródła: brak",
	} {
		if !strings.Contains(reply, want) {
			t.Fatalf("reply missing %q: %s", want, reply)
		}
	}
	for _, forbidden := range []string{"Potwierdzone", "Fałszywe"} {
		if strings.Contains(reply, forbidden) {
			t.Fatalf("abstention must not claim %q: %s", forbidden, reply)
		}
	}
}
