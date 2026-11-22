package main

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestSourcesProxyForwardsRagListingsUnchanged(t *testing.T) {
	var seenPaths []string
	rag := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seenPaths = append(seenPaths, r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[{"documentId":"law:kodeks-pracy","url":"https://dziennikustaw.gov.pl/DU/2026/1245"}]`))
	}))
	t.Cleanup(rag.Close)
	proxy := newSourcesProxy(slog.New(slog.NewTextHandler(io.Discard, nil)), rag.URL, 2*time.Second)

	for public, upstream := range sourcesProxyPaths {
		recorder := httptest.NewRecorder()
		proxy.handle(recorder, httptest.NewRequest(http.MethodGet, public, nil))
		if recorder.Code != http.StatusOK {
			t.Fatalf("%s: status %d", public, recorder.Code)
		}
		var listing []map[string]any
		if err := json.Unmarshal(recorder.Body.Bytes(), &listing); err != nil || len(listing) != 1 {
			t.Fatalf("%s: body %s", public, recorder.Body.String())
		}
		if seenPaths[len(seenPaths)-1] != upstream {
			t.Fatalf("%s should call rag %s, got %s", public, upstream, seenPaths[len(seenPaths)-1])
		}
	}
}

func TestSourcesProxyReportsOutageAsErrorNotEmptyList(t *testing.T) {
	rag := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"error":{"code":"index_unavailable","message":"x"}}`))
	}))
	t.Cleanup(rag.Close)
	proxy := newSourcesProxy(slog.New(slog.NewTextHandler(io.Discard, nil)), rag.URL, 2*time.Second)

	recorder := httptest.NewRecorder()
	proxy.handle(recorder, httptest.NewRequest(http.MethodGet, "/api/sources", nil))
	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", recorder.Code)
	}
	var envelope errorEnvelope
	if err := json.Unmarshal(recorder.Body.Bytes(), &envelope); err != nil || envelope.Error.Code != sourcesUnavailableCode {
		t.Fatalf("body %s", recorder.Body.String())
	}

	unknown := httptest.NewRecorder()
	proxy.handle(unknown, httptest.NewRequest(http.MethodGet, "/api/sources/secret", nil))
	if unknown.Code != http.StatusNotFound {
		t.Fatalf("unknown path status %d", unknown.Code)
	}
}
