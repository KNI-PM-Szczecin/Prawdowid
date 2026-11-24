package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"prawdowid/agent"
)

const (
	storeTimeout = 5 * time.Second
	// migrationLockKey identifies the advisory lock that serializes CREATE TABLE between starting instances.
	migrationLockKey = 7351002
)

const createCheckRunsSQL = `
CREATE TABLE IF NOT EXISTS check_runs (
    request_id   uuid PRIMARY KEY,
    created_at   timestamptz NOT NULL DEFAULT now(),
    channel      text NOT NULL,
    input_type   text NOT NULL,
    input_masked text NOT NULL,
    status       text NOT NULL,
    latency_ms   bigint NOT NULL,
    model        text,
    abstained    boolean NOT NULL,
    result       jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS check_runs_created_at_idx ON check_runs (created_at);
ALTER TABLE check_runs ENABLE ROW LEVEL SECURITY;
`

// createPromptLogSQL is an append-only history of questions for the team ("did the jury really test us?").
// It outlives a user deleting the run, but then only the text goes away: time, channel and status stay.
const createPromptLogSQL = `
CREATE TABLE IF NOT EXISTS prompt_log (
    request_id   uuid PRIMARY KEY,
    asked_at     timestamptz NOT NULL DEFAULT now(),
    channel      text NOT NULL,
    input_type   text NOT NULL,
    input_masked text,
    status       text NOT NULL
);
CREATE INDEX IF NOT EXISTS prompt_log_asked_at_idx ON prompt_log (asked_at);
ALTER TABLE prompt_log ENABLE ROW LEVEL SECURITY;
`

// runStore keeps one row per check: masked question, time, sources and the full result (CONTRACT.md §2).
type runStore struct {
	pool *pgxpool.Pool
}

func newRunStore(ctx context.Context, pool *pgxpool.Pool) (*runStore, error) {
	migrateCtx, cancel := context.WithTimeout(ctx, storeTimeout)
	defer cancel()

	// The lock is per session, so the lock, the migration and the unlock must share one connection.
	connection, err := pool.Acquire(migrateCtx)
	if err != nil {
		return nil, fmt.Errorf("acquire connection for migration: %w", err)
	}
	defer connection.Release()
	if _, err := connection.Exec(migrateCtx, `SELECT pg_advisory_lock($1)`, migrationLockKey); err != nil {
		return nil, fmt.Errorf("lock migration: %w", err)
	}
	defer func() {
		unlockCtx, unlockCancel := context.WithTimeout(context.WithoutCancel(ctx), storeTimeout)
		defer unlockCancel()
		// An unlock failure only matters until the connection is released, which also drops the session lock.
		if _, err := connection.Exec(unlockCtx, `SELECT pg_advisory_unlock($1)`, migrationLockKey); err != nil {
			slog.Warn("unlock migration failed", "error", err)
		}
	}()

	if _, err := connection.Exec(migrateCtx, createCheckRunsSQL); err != nil {
		return nil, fmt.Errorf("create check_runs: %w", err)
	}
	if _, err := connection.Exec(migrateCtx, createPromptLogSQL); err != nil {
		return nil, fmt.Errorf("create prompt_log: %w", err)
	}
	if _, err := connection.Exec(migrateCtx, createCasesSQL); err != nil {
		return nil, fmt.Errorf("create moderation_cases: %w", err)
	}
	return &runStore{pool: pool}, nil
}

func (s *runStore) save(ctx context.Context, request agent.VerifyRequest, result agent.CheckResult) error {
	payload, err := json.Marshal(result)
	if err != nil {
		return fmt.Errorf("encode result: %w", err)
	}
	saveCtx, cancel := context.WithTimeout(ctx, storeTimeout)
	defer cancel()
	transaction, err := s.pool.Begin(saveCtx)
	if err != nil {
		return fmt.Errorf("begin save transaction: %w", err)
	}
	defer func() {
		// Rollback after a successful commit is a no-op; any other error only means the connection is already gone.
		if err := transaction.Rollback(context.WithoutCancel(saveCtx)); err != nil && !errors.Is(err, pgx.ErrTxClosed) {
			slog.Warn("rollback save transaction failed", "error", err)
		}
	}()
	_, err = transaction.Exec(saveCtx,
		`INSERT INTO check_runs (request_id, channel, input_type, input_masked, status, latency_ms, model, abstained, result)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		 ON CONFLICT (request_id) DO NOTHING`,
		request.RequestID, request.Channel, request.InputType, request.Input, result.Status,
		result.Meta.LatencyMs, result.Meta.Model, result.Meta.Abstained, payload)
	if err != nil {
		return fmt.Errorf("insert check run: %w", err)
	}
	_, err = transaction.Exec(saveCtx,
		`INSERT INTO prompt_log (request_id, channel, input_type, input_masked, status)
		 VALUES ($1, $2, $3, $4, $5)
		 ON CONFLICT (request_id) DO NOTHING`,
		request.RequestID, request.Channel, request.InputType, request.Input, result.Status)
	if err != nil {
		return fmt.Errorf("insert prompt log: %w", err)
	}
	if err := transaction.Commit(saveCtx); err != nil {
		return fmt.Errorf("commit save transaction: %w", err)
	}
	return nil
}

// delete removes a stored run and reports whether it existed.
func (s *runStore) delete(ctx context.Context, requestID string) (bool, error) {
	deleteCtx, cancel := context.WithTimeout(ctx, storeTimeout)
	defer cancel()
	// Erase the question text from the history first: the deletion promise covers content, not the fact of a request.
	if _, err := s.pool.Exec(deleteCtx, `UPDATE prompt_log SET input_masked = NULL WHERE request_id = $1`, requestID); err != nil {
		return false, fmt.Errorf("erase prompt log text: %w", err)
	}
	tag, err := s.pool.Exec(deleteCtx, `DELETE FROM check_runs WHERE request_id = $1`, requestID)
	if err != nil {
		return false, fmt.Errorf("delete check run: %w", err)
	}
	return tag.RowsAffected() > 0, nil
}

// purgeOlderThan enforces the retention period (runs created before cutoff) and returns how many runs were removed.
func (s *runStore) purgeOlderThan(ctx context.Context, cutoff time.Time) (int64, error) {
	purgeCtx, cancel := context.WithTimeout(ctx, storeTimeout)
	defer cancel()
	tag, err := s.pool.Exec(purgeCtx, `DELETE FROM check_runs WHERE created_at < $1`, cutoff)
	if err != nil {
		return 0, fmt.Errorf("purge check runs: %w", err)
	}
	if _, err := s.pool.Exec(purgeCtx, `DELETE FROM prompt_log WHERE asked_at < $1`, cutoff); err != nil {
		return 0, fmt.Errorf("purge prompt log: %w", err)
	}
	return tag.RowsAffected(), nil
}
