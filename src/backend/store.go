package main

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"prawdowid/agent"
)

const storeTimeout = 5 * time.Second

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

// runStore keeps one row per check: masked question, time, sources and the full result (CONTRACT.md §2).
type runStore struct {
	pool *pgxpool.Pool
}

func newRunStore(ctx context.Context, pool *pgxpool.Pool) (*runStore, error) {
	migrateCtx, cancel := context.WithTimeout(ctx, storeTimeout)
	defer cancel()
	if _, err := pool.Exec(migrateCtx, createCheckRunsSQL); err != nil {
		return nil, fmt.Errorf("create check_runs: %w", err)
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
	_, err = s.pool.Exec(saveCtx,
		`INSERT INTO check_runs (request_id, channel, input_type, input_masked, status, latency_ms, model, abstained, result)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		 ON CONFLICT (request_id) DO NOTHING`,
		request.RequestID, request.Channel, request.InputType, request.Input, result.Status,
		result.Meta.LatencyMs, result.Meta.Model, result.Meta.Abstained, payload)
	if err != nil {
		return fmt.Errorf("insert check run: %w", err)
	}
	return nil
}

// delete removes a stored run and reports whether it existed.
func (s *runStore) delete(ctx context.Context, requestID string) (bool, error) {
	deleteCtx, cancel := context.WithTimeout(ctx, storeTimeout)
	defer cancel()
	tag, err := s.pool.Exec(deleteCtx, `DELETE FROM check_runs WHERE request_id = $1`, requestID)
	if err != nil {
		return false, fmt.Errorf("delete check run: %w", err)
	}
	return tag.RowsAffected() > 0, nil
}

// purgeOlderThan enforces the retention period and returns how many runs were removed.
func (s *runStore) purgeOlderThan(ctx context.Context, age time.Duration) (int64, error) {
	purgeCtx, cancel := context.WithTimeout(ctx, storeTimeout)
	defer cancel()
	tag, err := s.pool.Exec(purgeCtx, `DELETE FROM check_runs WHERE created_at < now() - $1::interval`, age.String())
	if err != nil {
		return 0, fmt.Errorf("purge check runs: %w", err)
	}
	return tag.RowsAffected(), nil
}
