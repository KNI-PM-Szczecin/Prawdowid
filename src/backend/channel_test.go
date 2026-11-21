package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"prawdowid/agent"
)

func newDemoHandler(verify verifyFunc, limit int) (*channelHandler, *[]agent.VerifyRequest) {
	checks, saved := newTestHandlers(verify, limit)
	return newChannelHandler(checks, demoAdapter{}), saved
}

func postDemo(handler *channelHandler, body string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodPost, "/api/channels/demo", strings.NewReader(body))
	recorder := httptest.NewRecorder()
	handler.handle(recorder, request)
	return recorder
}

func TestChannelInvalidMessageIsRejectedWithoutVerify(t *testing.T) {
	tests := []struct {
		name string
		body string
	}{
		{"broken json", `{"text":`},
		{"unknown field", `{"text":"abc def","extra":1}`},
		{"empty text", `{"text":"   "}`},
		{"missing text", `{}`},
		{"too long", `{"text":"` + strings.Repeat("ż", maxInputRunes+1) + `"}`},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			handler, saved := newDemoHandler(func(context.Context, agent.VerifyRequest) (agent.CheckResult, error) {
				t.Fatal("agent must not be called for invalid channel input")
				return agent.CheckResult{}, nil
			}, 10)

			recorder := postDemo(handler, test.body)
			if recorder.Code != http.StatusBadRequest {
				t.Fatalf("status %d, body %s", recorder.Code, recorder.Body.String())
			}
			if !strings.Contains(recorder.Body.String(), messageInvalidChannelMessage) {
				t.Fatalf("missing plain Polish message: %s", recorder.Body.String())
			}
			if len(*saved) != 0 {
				t.Fatal("invalid channel input must not be stored")
			}
		})
	}
}

func TestChannelRateLimitIsSharedWithWeb(t *testing.T) {
	checks, _ := newTestHandlers(okVerify, 2)
	handler := newChannelHandler(checks, demoAdapter{})

	if code := postCheck(checks, `{"input":"abc def","inputType":"text"}`).Code; code != http.StatusOK {
		t.Fatalf("web status %d", code)
	}
	if code := postDemo(handler, `{"text":"abc def"}`).Code; code != http.StatusOK {
		t.Fatalf("demo status %d", code)
	}

	recorder := postDemo(handler, `{"text":"abc def"}`)
	if recorder.Code != http.StatusTooManyRequests {
		t.Fatalf("status %d, body %s", recorder.Code, recorder.Body.String())
	}
	if !strings.Contains(recorder.Body.String(), messageRateLimited) {
		t.Fatalf("missing rate-limit message: %s", recorder.Body.String())
	}
}
