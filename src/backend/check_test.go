package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"prawdowid/agent"
)

func newTestHandlers(verify verifyFunc, limit int) (*checkHandlers, *[]agent.VerifyRequest) {
	var saved []agent.VerifyRequest
	handlers := &checkHandlers{
		logger: slog.New(slog.NewTextHandler(io.Discard, nil)),
		verify: verify,
		saveRun: func(_ context.Context, request agent.VerifyRequest, _ agent.CheckResult) error {
			saved = append(saved, request)
			return nil
		},
		deleteRun:     func(_ context.Context, requestID string) (bool, error) { return requestID != "", nil },
		limiter:       newRateLimiter(limit, time.Minute, slog.New(slog.NewTextHandler(io.Discard, nil))),
		now:           time.Now,
		archivalAfter: 365 * 24 * time.Hour,
	}
	return handlers, &saved
}

func postCheck(handlers *checkHandlers, body string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodPost, "/api/check", strings.NewReader(body))
	recorder := httptest.NewRecorder()
	handlers.check(recorder, request)
	return recorder
}

func decodeResult(t *testing.T, recorder *httptest.ResponseRecorder) agent.CheckResult {
	t.Helper()
	var result agent.CheckResult
	if err := json.Unmarshal(recorder.Body.Bytes(), &result); err != nil {
		t.Fatalf("response is not a CheckResult: %v, body %s", err, recorder.Body.String())
	}
	return result
}

func okVerify(_ context.Context, request agent.VerifyRequest) (agent.CheckResult, error) {
	return agent.CheckResult{RequestID: request.RequestID, Status: agent.StatusOK}, nil
}

func TestCheckMasksInputBeforeAgentAndStore(t *testing.T) {
	var seenByAgent string
	handlers, saved := newTestHandlers(func(ctx context.Context, request agent.VerifyRequest) (agent.CheckResult, error) {
		seenByAgent = request.Input
		return okVerify(ctx, request)
	}, 10)

	recorder := postCheck(handlers, `{"input":"Pisz na jan@example.com albo dzwon +48 600 700 800, PESEL 44051401359","inputType":"text"}`)

	if recorder.Code != http.StatusOK {
		t.Fatalf("status %d, body %s", recorder.Code, recorder.Body.String())
	}
	for _, leaked := range []string{"jan@example.com", "600 700 800", "44051401359"} {
		if strings.Contains(seenByAgent, leaked) || strings.Contains((*saved)[0].Input, leaked) {
			t.Fatalf("personal data %q reached the agent or the store: %q", leaked, seenByAgent)
		}
	}
	if (*saved)[0].Channel != "web" {
		t.Fatalf("channel %q", (*saved)[0].Channel)
	}
}

func TestCheckResponseHasContractShape(t *testing.T) {
	handlers, _ := newTestHandlers(okVerify, 10)
	recorder := postCheck(handlers, `{"input":"Polska jest w UE","inputType":"text"}`)

	var raw map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &raw); err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{"claims", "limitations"} {
		if list, ok := raw[field].([]any); !ok || list == nil {
			t.Fatalf("%s must be a JSON list, got %v", field, raw[field])
		}
	}
	if decodeResult(t, recorder).RequestID == "" {
		t.Fatal("requestId is empty")
	}
}

func TestCheckRejectsBadInput(t *testing.T) {
	tests := []struct {
		name       string
		body       string
		wantCode   int
		wantStatus string
	}{
		{"broken json", `{"input":`, http.StatusBadRequest, agent.StatusTechnicalError},
		{"unknown field", `{"input":"x y z","inputType":"text","extra":1}`, http.StatusBadRequest, agent.StatusTechnicalError},
		{"empty input", `{"input":"   ","inputType":"text"}`, http.StatusOK, agent.StatusNeedsClarification},
		{"unknown input type", `{"input":"abc def","inputType":"voice"}`, http.StatusOK, agent.StatusNeedsClarification},
		{"too long", `{"input":"` + strings.Repeat("ż", maxInputRunes+1) + `","inputType":"text"}`, http.StatusOK, agent.StatusNeedsClarification},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			handlers, saved := newTestHandlers(func(context.Context, agent.VerifyRequest) (agent.CheckResult, error) {
				t.Fatal("agent must not be called for invalid input")
				return agent.CheckResult{}, nil
			}, 10)
			recorder := postCheck(handlers, test.body)
			result := decodeResult(t, recorder)
			if recorder.Code != test.wantCode || result.Status != test.wantStatus {
				t.Fatalf("got %d %q, want %d %q", recorder.Code, result.Status, test.wantCode, test.wantStatus)
			}
			if result.Message == nil || len(result.Claims) != 0 {
				t.Fatalf("non-merit answer needs a message and no claims: %+v", result)
			}
			if len(*saved) != 0 {
				t.Fatal("invalid input must not be stored")
			}
		})
	}
}

func TestCheckTechnicalErrorIs503(t *testing.T) {
	handlers, _ := newTestHandlers(func(_ context.Context, request agent.VerifyRequest) (agent.CheckResult, error) {
		message := "Nie mogę teraz sprawdzić."
		return agent.CheckResult{RequestID: request.RequestID, Status: agent.StatusTechnicalError, Message: &message}, nil
	}, 10)
	recorder := postCheck(handlers, `{"input":"abc def","inputType":"text"}`)
	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", recorder.Code)
	}
}

func TestCheckAgentProgrammerErrorHidesDetails(t *testing.T) {
	handlers, _ := newTestHandlers(func(context.Context, agent.VerifyRequest) (agent.CheckResult, error) {
		return agent.CheckResult{}, errors.New("secret internal detail")
	}, 10)
	recorder := postCheck(handlers, `{"input":"abc def","inputType":"text"}`)
	if recorder.Code != http.StatusServiceUnavailable || strings.Contains(recorder.Body.String(), "secret internal detail") {
		t.Fatalf("status %d, body %s", recorder.Code, recorder.Body.String())
	}
}

func TestCheckStoreFailureDoesNotBreakAnswer(t *testing.T) {
	handlers, _ := newTestHandlers(okVerify, 10)
	handlers.saveRun = func(context.Context, agent.VerifyRequest, agent.CheckResult) error { return errors.New("db down") }
	recorder := postCheck(handlers, `{"input":"abc def","inputType":"text"}`)
	if recorder.Code != http.StatusOK || decodeResult(t, recorder).Status != agent.StatusOK {
		t.Fatalf("status %d, body %s", recorder.Code, recorder.Body.String())
	}
}

func TestCheckRateLimit(t *testing.T) {
	handlers, _ := newTestHandlers(okVerify, 2)
	body := `{"input":"abc def","inputType":"text"}`
	for attempt := 1; attempt <= 2; attempt++ {
		if code := postCheck(handlers, body).Code; code != http.StatusOK {
			t.Fatalf("attempt %d: status %d", attempt, code)
		}
	}
	recorder := postCheck(handlers, body)
	if recorder.Code != http.StatusTooManyRequests || decodeResult(t, recorder).Status != agent.StatusTechnicalError {
		t.Fatalf("status %d, body %s", recorder.Code, recorder.Body.String())
	}
	if retryAfter := recorder.Header().Get("Retry-After"); retryAfter != "60" {
		t.Fatalf("expected Retry-After of one rate-limit window, got %q", retryAfter)
	}
}

func TestDeleteCheck(t *testing.T) {
	handlers, _ := newTestHandlers(okVerify, 10)
	requestID, err := newRequestID()
	if err != nil {
		t.Fatal(err)
	}

	request := httptest.NewRequest(http.MethodDelete, "/api/checks/"+requestID, nil)
	request.SetPathValue("requestId", requestID)
	recorder := httptest.NewRecorder()
	handlers.deleteCheck(recorder, request)
	if recorder.Code != http.StatusNoContent {
		t.Fatalf("status %d", recorder.Code)
	}

	bad := httptest.NewRequest(http.MethodDelete, "/api/checks/not-a-uuid", nil)
	bad.SetPathValue("requestId", "not-a-uuid")
	recorder = httptest.NewRecorder()
	handlers.deleteCheck(recorder, bad)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("status %d", recorder.Code)
	}
}

func TestRateLimiterWindowResets(t *testing.T) {
	current := time.Now()
	limiter := newRateLimiter(1, time.Minute, nil)
	limiter.now = func() time.Time { return current }
	if !limiter.allow("a") || limiter.allow("a") {
		t.Fatal("second request in the window must be rejected")
	}
	if !limiter.allow("b") {
		t.Fatal("other clients are independent")
	}
	current = current.Add(time.Minute + time.Second)
	if !limiter.allow("a") {
		t.Fatal("window should have reset")
	}
}

func TestCheckResponseIncludesSummaryAndBadges(t *testing.T) {
	handlers, _ := newTestHandlers(okVerify, 10)
	recorder := postCheck(handlers, `{"input":"Polska jest w UE","inputType":"text"}`)

	var raw map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &raw); err != nil {
		t.Fatal(err)
	}
	summary, ok := raw["summary"].(map[string]any)
	if !ok || summary["level"] != summaryLevelUnknown || summary["score"] != nil {
		t.Fatalf("an answer without verdicts must be unknown with null score, got %v", raw["summary"])
	}
	if badges, ok := raw["badges"].([]any); !ok || len(badges) != 0 {
		t.Fatalf("badges must be an empty list, got %v", raw["badges"])
	}
	if raw["requestId"] == "" || raw["status"] != agent.StatusOK {
		t.Fatalf("agent fields must stay at the top level: %v", raw)
	}
}

func TestCheckURLInputGetsCatalogBadge(t *testing.T) {
	rag := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		_, _ = writer.Write([]byte(`{"entries":[{"domains":["gov.pl"]}]}`))
	}))
	defer rag.Close()
	handlers, _ := newTestHandlers(okVerify, 10)
	handlers.catalog = newSourceCatalog(rag.URL, time.Second)

	recorder := postCheck(handlers, `{"input":"https://www.gov.pl/web/zdrowie","inputType":"url"}`)
	var response struct {
		Badges []string `json:"badges"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatal(err)
	}
	if len(response.Badges) != 1 || response.Badges[0] != badgeInputSourceInCatalog {
		t.Fatalf("badges %v, want the in-catalog badge", response.Badges)
	}

	text := postCheck(handlers, `{"input":"Polska jest w UE","inputType":"text"}`)
	if strings.Contains(text.Body.String(), "input_source") {
		t.Fatalf("text input must not get a catalog badge: %s", text.Body.String())
	}
}
