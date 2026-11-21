package main

import (
	"io"
	"log/slog"
	"net/http"

	"prawdowid/agent"
)

const messageInvalidChannelMessage = "Nie udało się odczytać wiadomości. Wyślij sam tekst do sprawdzenia."

// ChannelAdapter is the second-channel boundary from CONTRACT.md section 2.
// It validates an incoming message and translates it into a VerifyRequest, then formats the result for its medium.
type ChannelAdapter interface {
	Name() string
	ToRequest(incoming []byte) (agent.VerifyRequest, error)
	ToReply(result agent.CheckResult) ([]byte, error)
}

// channelHandler serves one ChannelAdapter with the same verification pipeline as the web channel.
type channelHandler struct {
	logger  *slog.Logger
	checks  *checkHandlers
	adapter ChannelAdapter
}

func newChannelHandler(checks *checkHandlers, adapter ChannelAdapter) *channelHandler {
	return &channelHandler{logger: checks.logger, checks: checks, adapter: adapter}
}

func (h *channelHandler) handle(writer http.ResponseWriter, request *http.Request) {
	channel := h.adapter.Name()
	requestID, early, statusCode, ok := h.checks.beginCheck(request, channel)
	if !ok {
		h.writeReply(writer, statusCode, early)
		return
	}

	body, err := io.ReadAll(http.MaxBytesReader(writer, request.Body, maxBodyBytes))
	if err != nil {
		h.logger.Warn("read channel body failed", "channel", channel, "requestId", requestID, "error", err)
		h.writeInvalid(writer)
		return
	}

	verifyRequest, err := h.adapter.ToRequest(body)
	if err != nil {
		h.logger.Warn("invalid channel message", "channel", channel, "requestId", requestID, "error", err)
		h.writeInvalid(writer)
		return
	}

	if message := validateCheck(checkRequest{Input: verifyRequest.Input, InputType: verifyRequest.InputType}); message != "" {
		h.logger.Warn("channel message failed validation", "channel", channel, "requestId", requestID, "reason", message)
		h.writeInvalid(writer)
		return
	}

	result, statusCode := h.checks.runCheck(request.Context(), requestID, channel, verifyRequest.Input, verifyRequest.InputType)
	h.writeReply(writer, statusCode, result)
}

func (h *channelHandler) writeInvalid(writer http.ResponseWriter) {
	http.Error(writer, messageInvalidChannelMessage, http.StatusBadRequest)
}

func (h *channelHandler) writeReply(writer http.ResponseWriter, statusCode int, result agent.CheckResult) {
	reply, err := h.adapter.ToReply(result)
	if err != nil {
		h.logger.Error("build channel reply failed", "channel", h.adapter.Name(), "requestId", result.RequestID, "error", err)
		http.Error(writer, messageInternalError, http.StatusInternalServerError)
		return
	}
	writer.Header().Set("Content-Type", "text/plain; charset=utf-8")
	writer.WriteHeader(statusCode)
	if _, err := writer.Write(reply); err != nil {
		h.logger.Error("write channel reply failed", "channel", h.adapter.Name(), "requestId", result.RequestID, "error", err)
	}
}
