package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"sync"
	"time"

	"prawdowid/agent"
)

// resultCache keeps finished check results for a while, so the same question gets the same answer on every channel
// and on a page refresh. Without it every check runs the model and the search again, and the corpus (gap fill,
// travel notices, feeds) and the fact-check service change between two clicks. The key is a hash of the masked,
// normalised input: no submitted text is kept as a key. Technical errors are never cached.
type resultCache struct {
	mu         sync.Mutex
	ttl        time.Duration
	maxEntries int
	now        func() time.Time
	entries    map[string]cachedResult
}

type cachedResult struct {
	result   agent.CheckResult
	storedAt time.Time
}

func newResultCache(ttl time.Duration, maxEntries int, now func() time.Time) *resultCache {
	return &resultCache{ttl: ttl, maxEntries: maxEntries, now: now, entries: make(map[string]cachedResult)}
}

// resultCacheKey hashes the input type, the masked input folded to lower case and single spaces, and the channel's
// extra limitations (an OCR text and a typed text are different submissions).
func resultCacheKey(inputType, maskedInput string, extraLimitations []string) string {
	normalized := strings.Join(strings.Fields(strings.ToLower(maskedInput)), " ")
	sum := sha256.Sum256([]byte(inputType + "\x00" + normalized + "\x00" + strings.Join(extraLimitations, "\x00")))
	return hex.EncodeToString(sum[:])
}

func (c *resultCache) get(key string) (agent.CheckResult, bool) {
	if c == nil {
		return agent.CheckResult{}, false
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	entry, ok := c.entries[key]
	if !ok || c.now().Sub(entry.storedAt) > c.ttl {
		delete(c.entries, key)
		return agent.CheckResult{}, false
	}
	return entry.result, true
}

func (c *resultCache) put(key string, result agent.CheckResult) {
	if c == nil || result.Status == agent.StatusTechnicalError {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if len(c.entries) >= c.maxEntries {
		c.evictOldest()
	}
	c.entries[key] = cachedResult{result: result, storedAt: c.now()}
}

// evictOldest drops expired entries and, if the cache is still full, the oldest one.
func (c *resultCache) evictOldest() {
	oldestKey, oldestAt := "", time.Time{}
	for key, entry := range c.entries {
		if c.now().Sub(entry.storedAt) > c.ttl {
			delete(c.entries, key)
			continue
		}
		if oldestKey == "" || entry.storedAt.Before(oldestAt) {
			oldestKey, oldestAt = key, entry.storedAt
		}
	}
	if len(c.entries) >= c.maxEntries && oldestKey != "" {
		delete(c.entries, oldestKey)
	}
}

type freshResultKey struct{}

// withFreshResult marks a request that must skip the cached answer and overwrite it (Cache-Control: no-cache).
func withFreshResult(ctx context.Context) context.Context {
	return context.WithValue(ctx, freshResultKey{}, true)
}

func wantsFreshResult(ctx context.Context) bool {
	fresh, _ := ctx.Value(freshResultKey{}).(bool)
	return fresh
}

const noCacheDirective = "no-cache"

// newConfiguredResultCache returns nil (no reuse) when the configured lifetime is zero or negative.
func newConfiguredResultCache(minutes int) *resultCache {
	if minutes <= 0 {
		return nil
	}
	return newResultCache(time.Duration(minutes)*time.Minute, resultCacheMaxEntries, time.Now)
}
