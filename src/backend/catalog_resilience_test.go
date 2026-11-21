package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

// newSwitchableCatalogServer answers with the catalog until failing is set, then with 500.
func newSwitchableCatalogServer(catalogJSON string) (*atomic.Bool, *atomic.Int64, *httptest.Server) {
	failing := &atomic.Bool{}
	hits := &atomic.Int64{}
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		hits.Add(1)
		if failing.Load() {
			writer.WriteHeader(http.StatusInternalServerError)
			return
		}
		_, _ = writer.Write([]byte(catalogJSON))
	}))
	return failing, hits, server
}

func TestCatalogServesStaleCatalogOnFetchError(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	failing, _, server := newSwitchableCatalogServer(testCatalogJSON)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	if _, _, err := catalog.badgeForURL(context.Background(), "https://example.pl/a"); err != nil {
		t.Fatalf("first fetch: %v", err)
	}
	failing.Store(true)
	clock.advance(catalogCacheTTL + time.Second)

	badge, ok, err := catalog.badgeForURL(context.Background(), "https://example.pl/a")
	if err != nil || !ok || badge != badgeInputSourceInCatalog {
		t.Fatalf("stale catalog must be served: badge %q, ok %v, err %v", badge, ok, err)
	}
}

func TestCatalogRemembersFailureWithoutStaleCatalog(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	failing, hits, server := newSwitchableCatalogServer(testCatalogJSON)
	defer server.Close()
	failing.Store(true)
	catalog := newTestSourceCatalog(server.URL, clock)

	if _, _, err := catalog.badgeForURL(context.Background(), "https://example.pl/a"); err == nil {
		t.Fatal("first call must report the fetch error")
	}
	for attempt := 0; attempt < 3; attempt++ {
		if _, _, err := catalog.badgeForURL(context.Background(), "https://example.pl/a"); err == nil {
			t.Fatal("inside the failure window the error must be returned at once")
		}
	}
	if got := hits.Load(); got != 1 {
		t.Fatalf("server hits = %d, want 1 (failure window must stop retries)", got)
	}

	failing.Store(false)
	clock.advance(catalogFailureWindow + time.Second)
	badge, ok, err := catalog.badgeForURL(context.Background(), "https://example.pl/a")
	if err != nil || !ok || badge != badgeInputSourceInCatalog {
		t.Fatalf("after the window the catalog must be fetched again: %q %v %v", badge, ok, err)
	}
}

func TestCatalogNormalisesBothSidesTheSame(t *testing.T) {
	clock := &fakeClock{current: time.Date(2026, 11, 21, 12, 0, 0, 0, time.UTC)}
	server := newCatalogTestServer(`{"entries":[{"domains":["WWW.Gov.PL.","example.pl"]}]}`)
	defer server.Close()
	catalog := newTestSourceCatalog(server.URL, clock)

	for _, address := range []string{"https://gov.pl/a", "https://www.gov.pl./a", "https://GOV.pl/a"} {
		badge, ok, err := catalog.badgeForURL(context.Background(), address)
		if err != nil || !ok || badge != badgeInputSourceInCatalog {
			t.Errorf("%s: badge %q, ok %v, err %v", address, badge, ok, err)
		}
	}
}
