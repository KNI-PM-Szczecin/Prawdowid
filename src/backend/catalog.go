package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

const (
	// catalogFetchTimeout bounds a single GET /sources/catalog call, on top of the caller's context.
	catalogFetchTimeout = 5 * time.Second
	// catalogCacheTTL is how long the fetched catalog is reused before rag is asked again.
	catalogCacheTTL = 10 * time.Minute
	// maxCatalogBodyBytes caps the response size so a broken rag cannot exhaust memory.
	maxCatalogBodyBytes = 1 << 20
	catalogPath         = "/sources/catalog"

	badgeInputSourceInCatalog      = "input_source_in_catalog"
	badgeInputSourceOutsideCatalog = "input_source_outside_catalog"
)

// catalogEntry keeps only the field badges need; other fields of GET /sources/catalog (CONTRACT.md section 3) are ignored on purpose,
// so a field added to rag later cannot silently disable the badge.
type catalogEntry struct {
	Domains []string `json:"domains"`
}

type catalogResponse struct {
	Entries []catalogEntry `json:"entries"`
}

// sourceCatalog matches the domain of a submitted URL against the trusted-source
// catalog from rag (GET /sources/catalog). It produces only neutral status badges
// (CONTRACT.md section 1a); a badge is never a verdict basis and a failed fetch
// must never invent one.
type sourceCatalog struct {
	baseURL string
	client  *http.Client
	// ttl is how long the cached catalog stays valid; configurable for tests.
	ttl time.Duration
	// now is injectable so tests can move time forward past the TTL.
	now func() time.Time

	mu        sync.Mutex
	domains   map[string]struct{}
	fetchedAt time.Time
}

func newSourceCatalog(ragBaseURL string, fetchTimeout time.Duration) *sourceCatalog {
	return &sourceCatalog{
		baseURL: strings.TrimRight(ragBaseURL, "/"),
		client:  &http.Client{Timeout: fetchTimeout},
		ttl:     catalogCacheTTL,
		now:     time.Now,
	}
}

// badgeForURL returns input_source_in_catalog or input_source_outside_catalog for a
// submitted URL, or ok=false when there is no badge: a URL that is not valid http(s),
// or a catalog that could not be fetched (err is then wrapped for the caller to log).
func (c *sourceCatalog) badgeForURL(ctx context.Context, rawURL string) (badge string, ok bool, err error) {
	parsed, parseErr := url.Parse(rawURL)
	if parseErr != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Hostname() == "" {
		return "", false, nil
	}
	host := strings.TrimPrefix(strings.ToLower(parsed.Hostname()), "www.")

	domains, fetchErr := c.catalogDomains(ctx)
	if fetchErr != nil {
		return "", false, fmt.Errorf("get source catalog for %s: %w", catalogPath, fetchErr)
	}
	for domain := range domains {
		if host == domain || strings.HasSuffix(host, "."+domain) {
			return badgeInputSourceInCatalog, true, nil
		}
	}
	return badgeInputSourceOutsideCatalog, true, nil
}

// catalogDomains returns the set of catalog domains, fetching from rag when the cache is empty or stale.
func (c *sourceCatalog) catalogDomains(ctx context.Context) (map[string]struct{}, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.domains != nil && c.now().Sub(c.fetchedAt) < c.ttl {
		return c.domains, nil
	}

	fetched, err := c.fetch(ctx)
	if err != nil {
		return nil, err
	}
	c.domains = fetched
	c.fetchedAt = c.now()
	return c.domains, nil
}

func (c *sourceCatalog) fetch(ctx context.Context) (map[string]struct{}, error) {
	ctx, cancel := context.WithTimeout(ctx, catalogFetchTimeout)
	defer cancel()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+catalogPath, nil)
	if err != nil {
		return nil, fmt.Errorf("build request for %s: %w", catalogPath, err)
	}
	response, err := c.client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("call %s%s: %w", c.baseURL, catalogPath, err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("call %s%s: unexpected status %d", c.baseURL, catalogPath, response.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, maxCatalogBodyBytes))
	if err != nil {
		return nil, fmt.Errorf("read %s%s body: %w", c.baseURL, catalogPath, err)
	}

	var payload catalogResponse
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("decode %s%s body: %w", c.baseURL, catalogPath, err)
	}

	domains := make(map[string]struct{}, len(payload.Entries))
	for _, entry := range payload.Entries {
		for _, domain := range entry.Domains {
			domains[strings.ToLower(domain)] = struct{}{}
		}
	}
	return domains, nil
}
