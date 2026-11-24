package main

import (
	"context"
	"testing"
	"time"

	"prawdowid/agent"
)

const (
	purgeTestRetention = 300 * 24 * time.Hour // far beyond real retention, so a shared database never loses real runs
	purgeTestBackdate  = 400 * 24 * time.Hour
	testLatencyMs      = 42
)

func TestNewRunStoreCreatesTableAndIsIdempotent(t *testing.T) {
	pool := newTestPool(t)
	ctx := context.Background()

	for attempt := 1; attempt <= 2; attempt++ {
		store, err := newRunStore(ctx, pool)
		if err != nil {
			t.Fatalf("attempt %d: newRunStore: %v", attempt, err)
		}
		if store == nil {
			t.Fatalf("attempt %d: newRunStore returned a nil store", attempt)
		}
	}

	var tables int
	err := pool.QueryRow(ctx,
		`SELECT count(*) FROM information_schema.tables
		 WHERE table_schema = current_schema() AND table_name = 'check_runs'`).Scan(&tables)
	if err != nil {
		t.Fatalf("look up check_runs table: %v", err)
	}
	if tables != 1 {
		t.Fatalf("check_runs table count %d, want 1", tables)
	}
}

func TestRunStoreSaveStoresRow(t *testing.T) {
	pool := newTestPool(t)
	ctx := context.Background()
	store := newTestStore(t, ctx, pool)

	requestID := newTestRequestID(t)
	defer deleteTestRun(t, pool, requestID)

	model := "test-model"
	request := agent.VerifyRequest{
		RequestID: requestID,
		Channel:   webChannel,
		Input:     "mail: [ukryto]",
		InputType: agent.InputTypeText,
	}
	result := agent.CheckResult{
		RequestID:   requestID,
		Status:      agent.StatusOK,
		Claims:      []agent.Claim{},
		Limitations: []string{},
		Meta:        agent.RunMeta{Channel: webChannel, LatencyMs: testLatencyMs, Model: &model},
	}
	if err := store.save(ctx, request, result); err != nil {
		t.Fatalf("save: %v", err)
	}

	var inputMasked, channel, inputType, status string
	var storedModel *string
	var latencyMs int64
	var abstained bool
	err := pool.QueryRow(ctx,
		`SELECT input_masked, channel, input_type, status, latency_ms, model, abstained
		 FROM check_runs WHERE request_id = $1`, requestID).
		Scan(&inputMasked, &channel, &inputType, &status, &latencyMs, &storedModel, &abstained)
	if err != nil {
		t.Fatalf("read stored run: %v", err)
	}
	if inputMasked != request.Input {
		t.Errorf("input_masked %q, want %q", inputMasked, request.Input)
	}
	if channel != request.Channel || inputType != request.InputType || status != result.Status {
		t.Errorf("stored channel=%q input_type=%q status=%q, want %q %q %q",
			channel, inputType, status, request.Channel, request.InputType, result.Status)
	}
	if latencyMs != testLatencyMs {
		t.Errorf("latency_ms %d, want %d", latencyMs, testLatencyMs)
	}
	if storedModel == nil || *storedModel != model {
		t.Errorf("model %v, want %q", storedModel, model)
	}
	if abstained {
		t.Error("abstained stored as true, want false")
	}
}

func TestRunStoreSaveConflictDoesNotDuplicate(t *testing.T) {
	pool := newTestPool(t)
	ctx := context.Background()
	store := newTestStore(t, ctx, pool)

	requestID := newTestRequestID(t)
	defer deleteTestRun(t, pool, requestID)

	request := agent.VerifyRequest{
		RequestID: requestID,
		Channel:   webChannel,
		Input:     "powtórzone zgłoszenie",
		InputType: agent.InputTypeText,
	}
	result := agent.CheckResult{
		RequestID:   requestID,
		Status:      agent.StatusOK,
		Claims:      []agent.Claim{},
		Limitations: []string{},
		Meta:        agent.RunMeta{Channel: webChannel},
	}
	if err := store.save(ctx, request, result); err != nil {
		t.Fatalf("first save: %v", err)
	}
	if err := store.save(ctx, request, result); err != nil {
		t.Fatalf("second save with the same request_id must not fail (ON CONFLICT DO NOTHING): %v", err)
	}
	if rows := countTestRuns(t, pool, requestID); rows != 1 {
		t.Fatalf("rows for request_id %s: %d, want exactly 1 (no duplicate)", requestID, rows)
	}
}

func TestRunStoreDelete(t *testing.T) {
	pool := newTestPool(t)
	ctx := context.Background()
	store := newTestStore(t, ctx, pool)

	requestID := newTestRequestID(t)
	defer deleteTestRun(t, pool, requestID)

	request := agent.VerifyRequest{
		RequestID: requestID,
		Channel:   webChannel,
		Input:     "zgłoszenie do usunięcia",
		InputType: agent.InputTypeText,
	}
	result := agent.CheckResult{
		RequestID:   requestID,
		Status:      agent.StatusOK,
		Claims:      []agent.Claim{},
		Limitations: []string{},
		Meta:        agent.RunMeta{Channel: webChannel},
	}
	if err := store.save(ctx, request, result); err != nil {
		t.Fatalf("save: %v", err)
	}

	deleted, err := store.delete(ctx, requestID)
	if err != nil {
		t.Fatalf("delete existing run: %v", err)
	}
	if !deleted {
		t.Fatal("delete of an existing run returned false, want true")
	}

	deleted, err = store.delete(ctx, requestID)
	if err != nil {
		t.Fatalf("delete of a missing run must not fail: %v", err)
	}
	if deleted {
		t.Fatal("delete of a missing run returned true, want false")
	}
}

func TestRunStorePurgeOlderThan(t *testing.T) {
	pool := newTestPool(t)
	ctx := context.Background()
	store := newTestStore(t, ctx, pool)

	oldRequestID := newTestRequestID(t)
	freshRequestID := newTestRequestID(t)
	defer deleteTestRun(t, pool, oldRequestID)
	defer deleteTestRun(t, pool, freshRequestID)

	request := agent.VerifyRequest{
		RequestID: oldRequestID,
		Channel:   webChannel,
		Input:     "stare zgłoszenie",
		InputType: agent.InputTypeText,
	}
	result := agent.CheckResult{
		RequestID:   oldRequestID,
		Status:      agent.StatusOK,
		Claims:      []agent.Claim{},
		Limitations: []string{},
		Meta:        agent.RunMeta{Channel: webChannel},
	}
	if err := store.save(ctx, request, result); err != nil {
		t.Fatalf("save old run: %v", err)
	}
	request.RequestID = freshRequestID
	result.RequestID = freshRequestID
	if err := store.save(ctx, request, result); err != nil {
		t.Fatalf("save fresh run: %v", err)
	}

	// save() always stores created_at = now(), so the test ages the row with a direct UPDATE.
	if _, err := pool.Exec(ctx,
		`UPDATE check_runs SET created_at = now() - $1::interval WHERE request_id = $2`,
		purgeTestBackdate.String(), oldRequestID); err != nil {
		t.Fatalf("back-date old run: %v", err)
	}

	removed, err := store.purgeOlderThan(ctx, time.Now().Add(-purgeTestRetention))
	if err != nil {
		t.Fatalf("purgeOlderThan: %v", err)
	}
	if removed != 1 {
		t.Fatalf("purgeOlderThan removed %d rows, want 1 (only the back-dated row)", removed)
	}
	if rows := countTestRuns(t, pool, oldRequestID); rows != 0 {
		t.Fatalf("back-dated run still stored: %d rows, want 0", rows)
	}
	if rows := countTestRuns(t, pool, freshRequestID); rows != 1 {
		t.Fatalf("fresh run was purged: %d rows, want 1", rows)
	}
}

func TestPromptLogKeepsTimeAfterDeleteButErasesText(t *testing.T) {
	pool := newTestPool(t)
	ctx := context.Background()
	store := newTestStore(t, ctx, pool)

	requestID := newTestRequestID(t)
	defer deleteTestRun(t, pool, requestID)
	defer func() {
		if _, err := pool.Exec(ctx, `DELETE FROM prompt_log WHERE request_id = $1`, requestID); err != nil {
			t.Errorf("cleanup prompt log %s: %v", requestID, err)
		}
	}()

	request := agent.VerifyRequest{RequestID: requestID, Channel: webChannel, Input: "pytanie jury", InputType: agent.InputTypeText}
	result := agent.CheckResult{
		RequestID: requestID, Status: agent.StatusOK, Claims: []agent.Claim{}, Limitations: []string{},
		Meta: agent.RunMeta{Channel: webChannel, LatencyMs: testLatencyMs},
	}
	if err := store.save(ctx, request, result); err != nil {
		t.Fatalf("save: %v", err)
	}

	readLog := func() (text *string, channel string) {
		err := pool.QueryRow(ctx,
			`SELECT input_masked, channel FROM prompt_log WHERE request_id = $1`, requestID).Scan(&text, &channel)
		if err != nil {
			t.Fatalf("read prompt log: %v", err)
		}
		return text, channel
	}
	text, channel := readLog()
	if text == nil || *text != "pytanie jury" || channel != webChannel {
		t.Fatalf("prompt log = %v / %q, want the saved question on the web channel", text, channel)
	}

	deleted, err := store.delete(ctx, requestID)
	if err != nil || !deleted {
		t.Fatalf("delete = %v, %v, want true, nil", deleted, err)
	}
	text, _ = readLog()
	if text != nil {
		t.Fatalf("prompt log text after delete = %q, want NULL", *text)
	}
}
