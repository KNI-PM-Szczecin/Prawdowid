package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"prawdowid/agent"
)

func TestCheckURLInputReachesAgentUnmasked(t *testing.T) {
	const pageURL = "https://pap.pl/aktualnosci/123456789?autor=jan@example.com"
	var seenByAgent string
	handlers, saved := newTestHandlers(func(ctx context.Context, request agent.VerifyRequest) (agent.CheckResult, error) {
		seenByAgent = request.Input
		return okVerify(ctx, request)
	}, 10)

	recorder := postCheck(handlers, `{"input":"  `+pageURL+`  ","inputType":"url"}`)
	if recorder.Code != http.StatusOK {
		t.Fatalf("status %d, body %s", recorder.Code, recorder.Body.String())
	}
	if seenByAgent != pageURL {
		t.Fatalf("agent got %q, want the original trimmed URL", seenByAgent)
	}
	if strings.Contains((*saved)[0].Input, "jan@example.com") {
		t.Fatalf("stored copy must be masked: %q", (*saved)[0].Input)
	}
}

func TestCheckForcesBackendRequestID(t *testing.T) {
	var storedID string
	handlers, _ := newTestHandlers(func(context.Context, agent.VerifyRequest) (agent.CheckResult, error) {
		return agent.CheckResult{RequestID: "", Status: agent.StatusOK}, nil
	}, 10)
	handlers.saveRun = func(_ context.Context, _ agent.VerifyRequest, result agent.CheckResult) error {
		storedID = result.RequestID
		return nil
	}
	recorder := postCheck(handlers, `{"input":"abc def","inputType":"text"}`)
	if got := decodeResult(t, recorder).RequestID; !requestIDPattern.MatchString(got) {
		t.Fatalf("response requestId %q is not the backend UUID", got)
	}
	if !requestIDPattern.MatchString(storedID) {
		t.Fatalf("stored requestId %q is not the backend UUID", storedID)
	}
}

func TestStoredResultIsMaskedButResponseIsNot(t *testing.T) {
	const quote = "Kontakt: biuro@urzad.gov.pl"
	var stored agent.CheckResult
	handlers, _ := newTestHandlers(func(_ context.Context, request agent.VerifyRequest) (agent.CheckResult, error) {
		return agent.CheckResult{RequestID: request.RequestID, Status: agent.StatusOK, Claims: []agent.Claim{{
			ID: "c1", Text: "Napisz na jan@example.com", Verdict: agent.VerdictConfirmed,
			Justification: "Tel +48 600 700 800",
			Sources:       []agent.SourceRef{{ID: "s1", Title: "Strona jan@example.com", Quote: quote}},
		}}}, nil
	}, 10)
	handlers.saveRun = func(_ context.Context, _ agent.VerifyRequest, result agent.CheckResult) error {
		stored = result
		return nil
	}

	recorder := postCheck(handlers, `{"input":"abc def","inputType":"text"}`)
	response := decodeResult(t, recorder)
	if response.Claims[0].Sources[0].Quote != quote || response.Claims[0].Text != "Napisz na jan@example.com" {
		t.Fatalf("the answer must stay unmasked: %+v", response.Claims[0])
	}
	storedClaim := stored.Claims[0]
	for _, text := range []string{storedClaim.Text, storedClaim.Justification, storedClaim.Sources[0].Title, storedClaim.Sources[0].Quote} {
		if !strings.Contains(text, maskPlaceholder) {
			t.Errorf("stored text %q was not masked", text)
		}
	}
}

func TestCheckOversizeBodyIsNeedsClarification(t *testing.T) {
	handlers, saved := newTestHandlers(func(context.Context, agent.VerifyRequest) (agent.CheckResult, error) {
		t.Fatal("agent must not be called for an oversize body")
		return agent.CheckResult{}, nil
	}, 10)
	body := `{"input":"` + strings.Repeat("a", maxBodyBytes) + `","inputType":"text"}`
	recorder := postCheck(handlers, body)
	result := decodeResult(t, recorder)
	if recorder.Code != http.StatusOK || result.Status != agent.StatusNeedsClarification {
		t.Fatalf("got %d %q, want 200 needs_clarification", recorder.Code, result.Status)
	}
	if result.Message == nil || *result.Message != messageInputTooLong {
		t.Fatalf("message %v, want the too-long message", result.Message)
	}
	if len(*saved) != 0 {
		t.Fatal("oversize body must not be stored")
	}
}

func TestCheckRejectsTrailingData(t *testing.T) {
	handlers, _ := newTestHandlers(okVerify, 10)
	for _, body := range []string{
		`{"input":"abc def","inputType":"text"}{"input":"x"}`,
		`{"input":"abc def","inputType":"text"} garbage`,
	} {
		recorder := postCheck(handlers, body)
		if recorder.Code != http.StatusBadRequest || decodeResult(t, recorder).Status != agent.StatusTechnicalError {
			t.Errorf("body %q: status %d, response %s", body, recorder.Code, recorder.Body.String())
		}
	}
	if recorder := postCheck(handlers, `{"input":"abc def","inputType":"text"}`+"\n"); recorder.Code != http.StatusOK {
		t.Errorf("trailing newline must be accepted, got %d", recorder.Code)
	}
}

func TestCheckRateLimitIgnoresSpoofedForwardedFor(t *testing.T) {
	handlers, _ := newTestHandlers(okVerify, 1)
	handlers.trustedProxyHops = 1
	send := func(spoofed string) int {
		request := httptest.NewRequest(http.MethodPost, "/api/check", strings.NewReader(`{"input":"abc def","inputType":"text"}`))
		request.RemoteAddr = "10.0.0.1:1234"
		request.Header.Set("X-Forwarded-For", spoofed+", 198.51.100.7")
		recorder := httptest.NewRecorder()
		handlers.check(recorder, request)
		return recorder.Code
	}
	if code := send("1.1.1.1"); code != http.StatusOK {
		t.Fatalf("first request: %d", code)
	}
	if code := send("2.2.2.2"); code != http.StatusTooManyRequests {
		t.Fatalf("a different spoofed left entry must not give a fresh bucket, got %d", code)
	}
}

func TestLivenessDoesNotNeedDatabase(t *testing.T) {
	handlers, _ := newTestHandlers(okVerify, 1)
	recorder := httptest.NewRecorder()
	livenessHandler(handlers.logger)(recorder, httptest.NewRequest(http.MethodGet, "/livez", nil))
	if recorder.Code != http.StatusOK || strings.TrimSpace(recorder.Body.String()) != `{"status":"ok"}` {
		t.Fatalf("status %d, body %s", recorder.Code, recorder.Body.String())
	}
}
