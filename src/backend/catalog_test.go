package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type fakeClock struct {
	current time.Time
}

func (c *fakeClock) now() time.Time {
	return c.current
}

func (c *fakeClock) advance(by time.Duration) {
	c.current = c.current.Add(by)
}

func newCatalogTestHandler(catalogJSON string, hits *atomic.Int64) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != catalogPath {
			writer.WriteHeader(http.StatusNotFound)
			return
		}
		hits.Add(1)
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(catalogJSON))
	}
}

func newCatalogTestServer(catalogJSON string) *httptest.Server {
	return httptest.NewServer(newCatalogTestHandler(catalogJSON, &atomic.Int64{}))
}

func newCountingCatalogTestServer(catalogJSON string) (*atomic.Int64, *httptest.Server) {
	hits := &atomic.Int64{}
	return hits, httptest.NewServer(newCatalogTestHandler(catalogJSON, hits))
}

const testCatalogJSON = `{
  "version": "2026-11-21",
  "note": "katalog testowy",
  "rules": {"official": "domeny urzędowe"},
  "external": [],
  "entries": [
    {"publisher": "Przykładowy urząd", "domains": ["example.pl"], "sourceType": "official", "tier": 1, "reliability": "high", "qualification": "domena urzędowa"}
  ]
}`

func newTestSourceCatalog(serverURL string, clock *fakeClock) *sourceCatalog {
	catalog := newSourceCatalog(serverURL, catalogFetchTimeout)
	catalog.now = clock.now
	return catalog
}

func TestBadgeForURLInCatalog(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	hits, server := newCountingCatalogTestServer(testCatalogJSON)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	badge, ok, err := catalog.badgeForURL(context.Background(), "https://example.pl/komunikat")
	if err != nil {
		t.Fatalf("badgeForURL returned error: %v", err)
	}
	if !ok || badge != badgeInputSourceInCatalog {
		t.Fatalf("badge = %q, ok = %v; want %q, true", badge, ok, badgeInputSourceInCatalog)
	}
	if got := hits.Load(); got != 1 {
		t.Fatalf("server hits = %d, want 1", got)
	}
}

func TestBadgeForURLSubdomainInCatalog(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	server := newCatalogTestServer(testCatalogJSON)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	badge, ok, err := catalog.badgeForURL(context.Background(), "https://news.example.pl/wpis")
	if err != nil {
		t.Fatalf("badgeForURL returned error: %v", err)
	}
	if !ok || badge != badgeInputSourceInCatalog {
		t.Fatalf("badge = %q, ok = %v; want %q, true", badge, ok, badgeInputSourceInCatalog)
	}
}

func TestBadgeForURLOutsideCatalog(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	server := newCatalogTestServer(testCatalogJSON)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	badge, ok, err := catalog.badgeForURL(context.Background(), "https://other-domain.org/wpis")
	if err != nil {
		t.Fatalf("badgeForURL returned error: %v", err)
	}
	if !ok || badge != badgeInputSourceOutsideCatalog {
		t.Fatalf("badge = %q, ok = %v; want %q, true", badge, ok, badgeInputSourceOutsideCatalog)
	}
}

func TestBadgeForURLWWWPrefix(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	server := newCatalogTestServer(testCatalogJSON)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	badge, ok, err := catalog.badgeForURL(context.Background(), "https://WWW.Example.pl/wpis")
	if err != nil {
		t.Fatalf("badgeForURL returned error: %v", err)
	}
	if !ok || badge != badgeInputSourceInCatalog {
		t.Fatalf("badge = %q, ok = %v; want %q, true", badge, ok, badgeInputSourceInCatalog)
	}
}

func TestBadgeForURLLookalikeDomain(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	server := newCatalogTestServer(testCatalogJSON)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	badge, ok, err := catalog.badgeForURL(context.Background(), "https://evil-example.pl/wpis")
	if err != nil {
		t.Fatalf("badgeForURL returned error: %v", err)
	}
	if !ok || badge != badgeInputSourceOutsideCatalog {
		t.Fatalf("badge = %q, ok = %v; want %q, true", badge, ok, badgeInputSourceOutsideCatalog)
	}
}

func TestBadgeForURLBadURL(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	hits, server := newCountingCatalogTestServer(testCatalogJSON)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	for _, rawURL := range []string{"", "example.pl/wpis", "ftp://example.pl/wpis", "https://"} {
		badge, ok, err := catalog.badgeForURL(context.Background(), rawURL)
		if ok || badge != "" {
			t.Fatalf("badgeForURL(%q) = %q, ok = %v; want no badge", rawURL, badge, ok)
		}
		if err != nil {
			t.Fatalf("badgeForURL(%q) returned unexpected error: %v", rawURL, err)
		}
	}
	if got := hits.Load(); got != 0 {
		t.Fatalf("server hits = %d, want 0 (catalog must not be fetched for a bad URL)", got)
	}
}

func TestBadgeForURLRagServerError(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	failing := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		http.Error(writer, "internal error", http.StatusInternalServerError)
	}))
	defer failing.Close()
	catalog := newTestSourceCatalog(failing.URL, clock)

	badge, ok, err := catalog.badgeForURL(context.Background(), "https://example.pl/wpis")
	if ok || badge != "" {
		t.Fatalf("badge = %q, ok = %v; want no badge on rag failure", badge, ok)
	}
	if err == nil {
		t.Fatal("badgeForURL returned nil error on rag failure; want wrapped error")
	}
	if !strings.Contains(err.Error(), "unexpected status 500") {
		t.Fatalf("error = %v; want it to mention the wrapped status", err)
	}
}

func TestBadgeForURLCacheHit(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	hits, server := newCountingCatalogTestServer(testCatalogJSON)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	for range 2 {
		badge, ok, err := catalog.badgeForURL(context.Background(), "https://example.pl/wpis")
		if err != nil {
			t.Fatalf("badgeForURL returned error: %v", err)
		}
		if !ok || badge != badgeInputSourceInCatalog {
			t.Fatalf("badge = %q, ok = %v; want %q, true", badge, ok, badgeInputSourceInCatalog)
		}
	}
	if got := hits.Load(); got != 1 {
		t.Fatalf("server hits = %d, want 1 (second call must use the cache)", got)
	}
}

func TestBadgeForURLCacheExpiry(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	hits, server := newCountingCatalogTestServer(testCatalogJSON)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	for range 2 {
		if _, _, err := catalog.badgeForURL(context.Background(), "https://example.pl/wpis"); err != nil {
			t.Fatalf("badgeForURL returned error: %v", err)
		}
	}
	clock.advance(catalogCacheTTL + time.Minute)
	if _, _, err := catalog.badgeForURL(context.Background(), "https://example.pl/wpis"); err != nil {
		t.Fatalf("badgeForURL returned error after cache expiry: %v", err)
	}
	if got := hits.Load(); got != 2 {
		t.Fatalf("server hits = %d, want 2 (expired cache must be refetched)", got)
	}
}

func TestBadgeForURLFetchErrorIsWrapped(t *testing.T) {
	// The fake clock makes the cache never stale, so this test only exercises the fetch path.
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	catalog := newTestSourceCatalog("http://127.0.0.1:1", clock)

	if _, _, err := catalog.badgeForURL(context.Background(), "https://example.pl/wpis"); err == nil {
		t.Fatal("badgeForURL returned nil error for unreachable rag; want wrapped error")
	}
}

func TestSourceCatalogDecodesRealCatalogShape(t *testing.T) {
	// Guard against drift from the rag payload: unknown fields must not break decoding
	// of the fields this client needs, and camelCase names must match CONTRACT.md section 3.
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	server := newCatalogTestServer(testCatalogJSON)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	if _, ok, err := catalog.badgeForURL(context.Background(), "https://example.pl/wpis"); err != nil || !ok {
		t.Fatalf("badgeForURL = %v, %v; want ok with nil error", ok, err)
	}
}
