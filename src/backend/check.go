package main

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"prawdowid/agent"
)

const (
	webChannel      = "web"
	maxInputRunes   = 5000
	maxBodyBytes    = 64 << 10
	requestIDLength = 16
)

// Messages shown to the citizen (CONTRACT.md: simple Polish); details go to the log.
const (
	messageBadBody       = "Nie udało się odczytać zgłoszenia. Spróbuj jeszcze raz."
	messageEmptyInput    = "Wpisz tekst albo adres strony, który chcesz sprawdzić."
	messageInputTooLong  = "Zgłoszenie jest za długie. Skróć je do 5000 znaków."
	messageBadInputType  = "Nieznany rodzaj zgłoszenia. Wybierz tekst albo adres strony."
	messageRateLimited   = "Zbyt wiele zapytań. Spróbuj ponownie za chwilę."
	messageInternalError = "Wystąpił błąd po naszej stronie. Spróbuj ponownie później."
	messageBadRequestID  = "Niepoprawny identyfikator sprawdzenia."
	messageRunNotFound   = "Nie znaleziono takiego sprawdzenia."
)

var requestIDPattern = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

type checkRequest struct {
	Input     string `json:"input"`
	InputType string `json:"inputType"`
}

type verifyFunc func(ctx context.Context, request agent.VerifyRequest) (agent.CheckResult, error)

// checkHandlers serves the web channel. It validates and masks input, calls the agent and stores the run;
// it never decides a verdict (AGENTS.md: channels contain no verification logic).
type checkHandlers struct {
	logger    *slog.Logger
	verify    verifyFunc
	saveRun   func(ctx context.Context, request agent.VerifyRequest, result agent.CheckResult) error
	deleteRun func(ctx context.Context, requestID string) (bool, error)
	limiter   *rateLimiter
	now       func() time.Time
}

func (h *checkHandlers) check(writer http.ResponseWriter, request *http.Request) {
	requestID, early, statusCode, ok := h.beginCheck(request, webChannel)
	if !ok {
		h.reply(writer, statusCode, early)
		return
	}

	var body checkRequest
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, maxBodyBytes))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		h.logger.Warn("invalid check body", "requestId", requestID, "error", err)
		h.reply(writer, http.StatusBadRequest, h.nonMerit(requestID, webChannel, agent.StatusTechnicalError, messageBadBody))
		return
	}

	if message := validateCheck(body); message != "" {
		h.reply(writer, http.StatusOK, h.nonMerit(requestID, webChannel, agent.StatusNeedsClarification, message))
		return
	}

	result, statusCode := h.runCheck(request.Context(), requestID, webChannel, body.Input, body.InputType)
	h.reply(writer, statusCode, result)
}

// beginCheck reserves a request id and a rate-limit slot for every channel.
// When ok is false, early is the non-merit answer to send with statusCode.
func (h *checkHandlers) beginCheck(request *http.Request, channel string) (requestID string, early agent.CheckResult, statusCode int, ok bool) {
	requestID, err := newRequestID()
	if err != nil {
		h.logger.Error("generate request id failed", "error", err)
		return "", h.nonMerit("", channel, agent.StatusTechnicalError, messageInternalError), http.StatusServiceUnavailable, false
	}

	if !h.limiter.allow(clientAddress(request)) {
		h.logger.Warn("rate limit exceeded", "requestId", requestID)
		return requestID, h.nonMerit(requestID, channel, agent.StatusTechnicalError, messageRateLimited), http.StatusTooManyRequests, false
	}
	return requestID, agent.CheckResult{}, http.StatusOK, true
}

// runCheck is the shared pipeline for every channel: mask personal data, call the agent,
// normalize the result, store the run without failing the answer and log the outcome.
func (h *checkHandlers) runCheck(ctx context.Context, requestID, channel, input, inputType string) (agent.CheckResult, int) {
	verifyRequest := agent.VerifyRequest{
		RequestID: requestID,
		Channel:   channel,
		Input:     maskPersonalData(strings.TrimSpace(input)),
		InputType: inputType,
	}
	result, err := h.verify(ctx, verifyRequest)
	if err != nil {
		h.logger.Error("verify failed", "requestId", requestID, "error", err)
		return h.nonMerit(requestID, channel, agent.StatusTechnicalError, messageInternalError), http.StatusServiceUnavailable
	}
	result = normalizeResult(result)

	// A failed audit write must not break the answer (AGENTS.md section 6).
	if err := h.saveRun(context.WithoutCancel(ctx), verifyRequest, result); err != nil {
		h.logger.Error("save check run failed", "requestId", requestID, "error", err)
	}
	h.logger.Info("check finished",
		"requestId", requestID, "status", result.Status, "latencyMs", result.Meta.LatencyMs,
		"abstained", result.Meta.Abstained, "retrievedPassages", result.Meta.RetrievedPassages,
		"searchErrors", result.Meta.SearchErrors, "injectionAttempts", result.Meta.InjectionAttempts,
		"timedOut", result.Meta.TimedOut)

	statusCode := http.StatusOK
	if result.Status == agent.StatusTechnicalError {
		statusCode = http.StatusServiceUnavailable
	}
	return result, statusCode
}

func (h *checkHandlers) deleteCheck(writer http.ResponseWriter, request *http.Request) {
	requestID := request.PathValue("requestId")
	if !requestIDPattern.MatchString(requestID) {
		h.reply(writer, http.StatusBadRequest, h.nonMerit(requestID, webChannel, agent.StatusTechnicalError, messageBadRequestID))
		return
	}
	deleted, err := h.deleteRun(request.Context(), requestID)
	if err != nil {
		h.logger.Error("delete check run failed", "requestId", requestID, "error", err)
		h.reply(writer, http.StatusServiceUnavailable, h.nonMerit(requestID, webChannel, agent.StatusTechnicalError, messageInternalError))
		return
	}
	if !deleted {
		h.reply(writer, http.StatusNotFound, h.nonMerit(requestID, webChannel, agent.StatusTechnicalError, messageRunNotFound))
		return
	}
	h.logger.Info("check run deleted", "requestId", requestID)
	writer.WriteHeader(http.StatusNoContent)
}

func (h *checkHandlers) reply(writer http.ResponseWriter, statusCode int, result agent.CheckResult) {
	writeJSON(h.logger, writer, statusCode, result)
}

// nonMerit builds a CheckResult without verdicts: claims is an empty list and message is set (CONTRACT.md section 1).
func (h *checkHandlers) nonMerit(requestID, channel, status, message string) agent.CheckResult {
	return normalizeResult(agent.CheckResult{
		RequestID: requestID,
		Status:    status,
		Message:   &message,
		Meta:      agent.RunMeta{Channel: channel, ReceivedAt: h.now().UTC().Format(time.RFC3339)},
	})
}

func validateCheck(body checkRequest) string {
	trimmed := strings.TrimSpace(body.Input)
	switch {
	case body.InputType != agent.InputTypeText && body.InputType != agent.InputTypeURL:
		return messageBadInputType
	case trimmed == "":
		return messageEmptyInput
	case utf8.RuneCountInString(trimmed) > maxInputRunes:
		return messageInputTooLong
	}
	return ""
}

// normalizeResult turns nil slices into empty lists so the JSON always matches the contract.
func normalizeResult(result agent.CheckResult) agent.CheckResult {
	if result.Claims == nil {
		result.Claims = []agent.Claim{}
	}
	if result.Limitations == nil {
		result.Limitations = []string{}
	}
	for index := range result.Claims {
		claim := &result.Claims[index]
		if claim.StrengthReasons == nil {
			claim.StrengthReasons = []string{}
		}
		if claim.Sources == nil {
			claim.Sources = []agent.SourceRef{}
		}
		if claim.Warnings == nil {
			claim.Warnings = []agent.Warning{}
		}
	}
	return result
}

// newRequestID returns a random UUID v4 without an extra dependency.
func newRequestID() (string, error) {
	raw := make([]byte, requestIDLength)
	if _, err := rand.Read(raw); err != nil {
		return "", fmt.Errorf("read random bytes: %w", err)
	}
	raw[6] = raw[6]&0x0f | 0x40
	raw[8] = raw[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", raw[0:4], raw[4:6], raw[6:8], raw[8:10], raw[10:16]), nil
}
