package main

import (
	"context"
	"os"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Integration tests hit a real PostgreSQL only when TEST_DATABASE_URL points at a disposable
// test database; without it they skip, so `go test ./...` stays green on machines without a database.
// Tests must never read DATABASE_URL, .env files or a hardcoded connection string.
const testDatabaseURLEnv = "TEST_DATABASE_URL"

func newTestPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	databaseURL := os.Getenv(testDatabaseURLEnv)
	if databaseURL == "" {
		t.Skipf("%s is not set; skipping check_runs integration test (needs a real PostgreSQL database)", testDatabaseURLEnv)
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("create test pool: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := pool.Ping(ctx); err != nil {
		t.Fatalf("ping test database: %v", err)
	}
	return pool
}

func newTestStore(t *testing.T, ctx context.Context, pool *pgxpool.Pool) *runStore {
	t.Helper()
	store, err := newRunStore(ctx, pool)
	if err != nil {
		t.Fatalf("newRunStore: %v", err)
	}
	return store
}

func newTestRequestID(t *testing.T) string {
	t.Helper()
	requestID, err := newRequestID()
	if err != nil {
		t.Fatalf("generate request id: %v", err)
	}
	return requestID
}

// countTestRuns counts only rows with the given test-owned request id, never the whole table.
func countTestRuns(t *testing.T, pool *pgxpool.Pool, requestID string) int {
	t.Helper()
	var rows int
	err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM check_runs WHERE request_id = $1`, requestID).Scan(&rows)
	if err != nil {
		t.Fatalf("count check runs for %s: %v", requestID, err)
	}
	return rows
}

// deleteTestRun removes only the row the calling test created; tests never truncate check_runs.
func deleteTestRun(t *testing.T, pool *pgxpool.Pool, requestID string) {
	t.Helper()
	if _, err := pool.Exec(context.Background(),
		`DELETE FROM check_runs WHERE request_id = $1`, requestID); err != nil {
		t.Fatalf("clean up check run %s: %v", requestID, err)
	}
}
