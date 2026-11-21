package main

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
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
	// archivalAfter is the age of the newest source after which the archival_material badge is shown.
	archivalAfter time.Duration
	// catalog is optional: without it the input_source_* badges are simply not shown.
	catalog *sourceCatalog
	// trustedProxyHops tells the rate limiter which X-Forwarded-For entry (counted from the right) is ours.
	trustedProxyHops int
}

func (h *checkHandlers) check(writer http.ResponseWriter, request *http.Request) {
	requestID, early, statusCode, ok := h.beginCheck(request, webChannel)
	if !ok {
		h.reply(writer, statusCode, early)
		return
	}

	var body checkRequest
	if err := decodeCheckBody(http.MaxBytesReader(writer, request.Body, maxBodyBytes), &body); err != nil {
		var tooLarge *http.MaxBytesError
		if errors.As(err, &tooLarge) {
			h.reply(writer, http.StatusOK, h.nonMerit(requestID, webChannel, agent.StatusNeedsClarification, messageInputTooLong))
			return
		}
		h.logger.Warn("invalid check body", "requestId", requestID, "error", err)
		h.reply(writer, http.StatusBadRequest, h.nonMerit(requestID, webChannel, agent.StatusTechnicalError, messageBadBody))
		return
	}

	if message := validateCheck(body); message != "" {
		h.reply(writer, http.StatusOK, h.nonMerit(requestID, webChannel, agent.StatusNeedsClarification, message))
		return
	}

	result, statusCode := h.runCheck(request.Context(), requestID, webChannel, body.Input, body.InputType)
	response := h.withSummary(result)
	if body.InputType == agent.InputTypeURL && result.Status == agent.StatusOK {
		response.Badges = h.addCatalogBadge(request.Context(), response.Badges, body.Input)
	}
	writeJSON(h.logger, writer, statusCode, response)
}

// decodeCheckBody reads exactly one JSON object with known fields; trailing data is an error.
func decodeCheckBody(body io.Reader, target *checkRequest) error {
	decoder := json.NewDecoder(body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode check body: %w", err)
	}
	if err := decoder.Decode(&json.RawMessage{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("unexpected data after the JSON value")
		}
		return fmt.Errorf("read after the JSON value: %w", err)
	}
	return nil
}

// addCatalogBadge appends the neutral input_source_* badge; when the catalog is unavailable no badge is added.
func (h *checkHandlers) addCatalogBadge(ctx context.Context, badges []string, rawURL string) []string {
	if h.catalog == nil {
		return badges
	}
	badge, found, err := h.catalog.badgeForURL(ctx, strings.TrimSpace(rawURL))
	if err != nil {
		h.logger.Warn("source catalog unavailable, badge skipped", "error", err)
		return badges
	}
	if !found {
		return badges
	}
	return append(badges, badge)
}

// checkResponse is the web answer: the agent result plus the deterministic fields from CONTRACT.md section 1a.
type checkResponse struct {
	agent.CheckResult
	Summary Summary  `json:"summary"`
	Badges  []string `json:"badges"`
}

func (h *checkHandlers) withSummary(result agent.CheckResult) checkResponse {
	return checkResponse{
		CheckResult: result,
		Summary:     buildSummary(result),
		Badges:      buildBadges(result, h.now(), h.archivalAfter),
	}
}

// beginCheck reserves a request id and a rate-limit slot for every channel.
// When ok is false, early is the non-merit answer to send with statusCode.
func (h *checkHandlers) beginCheck(request *http.Request, channel string) (requestID string, early agent.CheckResult, statusCode int, ok bool) {
	requestID, err := newRequestID()
	if err != nil {
		h.logger.Error("generate request id failed", "error", err)
		return "", h.nonMerit("", channel, agent.StatusTechnicalError, messageInternalError), http.StatusServiceUnavailable, false
	}

	if !h.limiter.allow(clientAddress(request, h.trustedProxyHops)) {
		h.logger.Warn("rate limit exceeded", "requestId", requestID)
		return requestID, h.nonMerit(requestID, channel, agent.StatusTechnicalError, messageRateLimited), http.StatusTooManyRequests, false
	}
	return requestID, agent.CheckResult{}, http.StatusOK, true
}

// runCheck is the shared pipeline for every channel: mask personal data, call the agent,
// normalize the result, store the run without failing the answer and log the outcome.
// A URL goes to the agent unchanged, because masking would rewrite the address the agent has to fetch;
// only the stored copy is masked.
func (h *checkHandlers) runCheck(ctx context.Context, requestID, channel, input, inputType string) (agent.CheckResult, int) {
	trimmed := strings.TrimSpace(input)
	storedRequest := agent.VerifyRequest{
		RequestID: requestID,
		Channel:   channel,
		Input:     maskPersonalData(trimmed),
		InputType: inputType,
	}
	verifyRequest := storedRequest
	if inputType == agent.InputTypeURL {
		verifyRequest.Input = trimmed
	}
	result, err := h.verify(ctx, verifyRequest)
	if err != nil {
		h.logger.Error("verify failed", "requestId", requestID, "error", err)
		return h.nonMerit(requestID, channel, agent.StatusTechnicalError, messageInternalError), http.StatusServiceUnavailable
	}
	result = normalizeResult(result)
	result.RequestID = requestID

	// A failed audit write must not break the answer (AGENTS.md section 6).
	if err := h.saveRun(context.WithoutCancel(ctx), storedRequest, maskResultForStorage(result)); err != nil {
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

// maskResultForStorage returns a copy of the result with personal data hidden in the free text that is stored
// (claim text, justification, source title and quote); the answer sent to the user is not changed.
func maskResultForStorage(result agent.CheckResult) agent.CheckResult {
	claims := make([]agent.Claim, len(result.Claims))
	for claimIndex, claim := range result.Claims {
		claim.Text = maskPersonalData(claim.Text)
		claim.Justification = maskPersonalData(claim.Justification)
		sources := make([]agent.SourceRef, len(claim.Sources))
		for sourceIndex, source := range claim.Sources {
			source.Title = maskPersonalData(source.Title)
			source.Quote = maskPersonalData(source.Quote)
			sources[sourceIndex] = source
		}
		claim.Sources = sources
		claims[claimIndex] = claim
	}
	result.Claims = claims
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
