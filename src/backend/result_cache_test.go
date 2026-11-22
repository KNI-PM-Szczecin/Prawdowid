package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"prawdowid/agent"
)

const cacheTestBody = `{"input":"Most w Borowie ma 120 metrów.","inputType":"text"}`

// countingVerify answers with a different justification on every call, as a real model and corpus may.
func countingVerify(calls *int, status string) verifyFunc {
	return func(_ context.Context, request agent.VerifyRequest) (agent.CheckResult, error) {
		*calls++
		return agent.CheckResult{
			RequestID: request.RequestID,
			Status:    status,
			Claims:    []agent.Claim{{ID: "c1", Verdict: agent.VerdictConfirmed, Justification: strings.Repeat("x", *calls)}},
		}, nil
	}
}

func TestSameQuestionGetsTheSameAnswerFromTheCache(t *testing.T) {
	calls := 0
	handlers, _ := newTestHandlers(countingVerify(&calls, agent.StatusOK), 10)
	handlers.results = newResultCache(time.Minute, 10, time.Now)

	first := decodeResult(t, postCheck(handlers, cacheTestBody))
	// Different spacing and case is the same question.
	second := decodeResult(t, postCheck(handlers, `{"input":"  most w borowie   MA 120 metrów. ","inputType":"text"}`))

	if calls != 1 {
		t.Fatalf("the agent must run once, ran %d times", calls)
	}
	if second.Claims[0].Justification != first.Claims[0].Justification || !second.Meta.Cached || first.Meta.Cached {
		t.Fatalf("expected the stored answer marked as cached, got first %+v second %+v", first, second)
	}
	if second.RequestID == first.RequestID {
		t.Fatal("every request keeps its own id")
	}
}

func TestNoCacheHeaderRunsTheCheckAgainAndOverwrites(t *testing.T) {
	calls := 0
	handlers, _ := newTestHandlers(countingVerify(&calls, agent.StatusOK), 10)
	handlers.results = newResultCache(time.Minute, 10, time.Now)
	postCheck(handlers, cacheTestBody)

	request := httptest.NewRequest(http.MethodPost, "/api/check", strings.NewReader(cacheTestBody))
	request.Header.Set("Cache-Control", "no-cache")
	recorder := httptest.NewRecorder()
	handlers.check(recorder, request)
	fresh := decodeResult(t, recorder)
	again := decodeResult(t, postCheck(handlers, cacheTestBody))

	if calls != 2 || fresh.Meta.Cached || again.Claims[0].Justification != fresh.Claims[0].Justification {
		t.Fatalf("no-cache must recompute and overwrite: calls %d, fresh %+v, again %+v", calls, fresh, again)
	}
}

func TestTechnicalErrorIsNeverCached(t *testing.T) {
	calls := 0
	handlers, _ := newTestHandlers(countingVerify(&calls, agent.StatusTechnicalError), 10)
	handlers.results = newResultCache(time.Minute, 10, time.Now)
	postCheck(handlers, cacheTestBody)
	postCheck(handlers, cacheTestBody)
	if calls != 2 {
		t.Fatalf("a technical error must be retried, the agent ran %d times", calls)
	}
}

func TestCachedAnswerExpires(t *testing.T) {
	current := time.Date(2026, 11, 22, 12, 0, 0, 0, time.UTC)
	cache := newResultCache(time.Minute, 10, func() time.Time { return current })
	cache.put("key", agent.CheckResult{Status: agent.StatusOK})
	current = current.Add(2 * time.Minute)
	if _, ok := cache.get("key"); ok {
		t.Fatal("an expired answer must not be reused")
	}
}

func TestFullCacheDropsTheOldestAnswer(t *testing.T) {
	current := time.Date(2026, 11, 22, 12, 0, 0, 0, time.UTC)
	cache := newResultCache(time.Hour, 2, func() time.Time { return current })
	for _, key := range []string{"first", "second", "third"} {
		cache.put(key, agent.CheckResult{Status: agent.StatusOK})
		current = current.Add(time.Second)
	}
	if _, ok := cache.get("first"); ok {
		t.Fatal("the oldest answer must be dropped when the cache is full")
	}
	if _, ok := cache.get("third"); !ok {
		t.Fatal("the newest answer must stay")
	}
}
