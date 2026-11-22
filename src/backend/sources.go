package main

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

const (
	// sourcesProxyTimeout bounds one audit listing; the corpus list is a few hundred rows.
	sourcesProxyTimeout = 10 * time.Second
	// maxSourcesBodyBytes caps rag's answer so a broken service cannot exhaust memory.
	maxSourcesBodyBytes = 8 << 20

	sourcesUnavailableCode    = "sources_unavailable"
	sourcesUnavailableMessage = "Lista źródeł jest chwilowo niedostępna. Spróbuj ponownie za chwilę."
)

// sourcesProxyPaths maps the public audit endpoints to rag's read-only listings (CONTRACT.md section 3).
// rag has no public address, so the brief's "list of sources available for audit" is served through the backend.
var sourcesProxyPaths = map[string]string{
	"/api/sources":          "/sources",
	"/api/sources/catalog":  "/sources/catalog",
	"/api/sources/external": "/sources/external",
}

// sourcesProxy forwards GET requests for the source listings to rag unchanged; it never filters or rewrites them.
type sourcesProxy struct {
	logger  *slog.Logger
	baseURL string
	client  *http.Client
}

func newSourcesProxy(logger *slog.Logger, ragBaseURL string, timeout time.Duration) *sourcesProxy {
	return &sourcesProxy{logger: logger, baseURL: strings.TrimRight(ragBaseURL, "/"), client: &http.Client{Timeout: timeout}}
}

type errorEnvelope struct {
	Error errorBody `json:"error"`
}

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func (p *sourcesProxy) handle(writer http.ResponseWriter, request *http.Request) {
	ragPath, known := sourcesProxyPaths[request.URL.Path]
	if !known {
		http.NotFound(writer, request)
		return
	}
	upstream, err := http.NewRequestWithContext(request.Context(), http.MethodGet, p.baseURL+ragPath, nil)
	if err != nil {
		p.logger.Error("build sources request failed", "path", ragPath, "error", err)
		p.unavailable(writer)
		return
	}
	response, err := p.client.Do(upstream)
	if err != nil {
		p.logger.Warn("sources listing unavailable", "path", ragPath, "error", err)
		p.unavailable(writer)
		return
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, maxSourcesBodyBytes))
	if err != nil || response.StatusCode != http.StatusOK || !json.Valid(body) {
		p.logger.Warn("sources listing failed", "path", ragPath, "status", response.StatusCode, "error", err)
		p.unavailable(writer)
		return
	}
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.Header().Set("Cache-Control", "no-store")
	writer.WriteHeader(http.StatusOK)
	if _, err := writer.Write(body); err != nil {
		p.logger.Warn("write sources listing failed", "path", ragPath, "error", err)
	}
}

func (p *sourcesProxy) unavailable(writer http.ResponseWriter) {
	writeJSON(p.logger, writer, http.StatusServiceUnavailable, errorEnvelope{
		Error: errorBody{Code: sourcesUnavailableCode, Message: sourcesUnavailableMessage},
	})
}
