package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"prawdowid/agent"
)

const (
	readHeaderTimeout = 10 * time.Second
	idleTimeout       = 60 * time.Second
	// writeTimeout must exceed the agent verification budget (25 s) so a slow check can still be answered.
	writeTimeout    = 40 * time.Second
	shutdownTimeout = 30 * time.Second
	rateLimitWindow = time.Minute
	purgeInterval   = time.Hour
	hoursPerDay     = 24
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	if err := run(logger); err != nil {
		logger.Error("backend stopped", "error", err)
		os.Exit(1)
	}
}

func run(logger *slog.Logger) error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	config, err := loadConfig()
	if err != nil {
		return err
	}

	pool, err := connectDatabase(ctx, config)
	if err != nil {
		return err
	}
	defer pool.Close()
	logger.Info("database connected", "maxConns", config.DatabaseMaxConns)

	verifier, err := agent.NewFromEnv(logger)
	if err != nil {
		return fmt.Errorf("create agent: %w", err)
	}
	store, err := newRunStore(ctx, pool)
	if err != nil {
		return err
	}
	cases := &caseStore{pool: pool}
	retention := time.Duration(config.RetentionDays) * hoursPerDay * time.Hour
	purgeDone := make(chan struct{})
	go func() {
		defer close(purgeDone)
		purgeLoop(ctx, logger, retention, store, cases)
	}()
	// Registered after pool.Close, so it runs first: the purge must finish before the pool closes.
	defer func() {
		stop()
		<-purgeDone
	}()

	checks := &checkHandlers{
		logger:           logger,
		verify:           verifier.Verify,
		saveRun:          store.save,
		deleteRun:        store.delete,
		limiter:          newRateLimiter(config.RateLimitPerMinute, rateLimitWindow, logger),
		now:              time.Now,
		archivalAfter:    time.Duration(config.ArchivalDays) * hoursPerDay * time.Hour,
		catalog:          newSourceCatalog(config.RagURL, catalogFetchTimeout),
		trustedProxyHops: config.TrustedProxyHops,
		cases:            newCaseTracker(logger, config, cases),
		ocr:              newOCRClient(config.RagURL, ocrTimeout),
	}

	demo := newChannelHandler(checks, demoAdapter{})

	mux := http.NewServeMux()
	mux.HandleFunc("GET /livez", livenessHandler(logger))
	mux.HandleFunc("GET /health", healthHandler(logger, pool))
	mux.HandleFunc("POST /api/check", checks.check)
	mux.HandleFunc("POST /api/check/image", checks.checkImage)
	mux.HandleFunc("DELETE /api/checks/{requestId}", checks.deleteCheck)
	mux.HandleFunc("POST /api/channels/demo", demo.handle)
	mux.HandleFunc("GET /api/admin/cases", adminCasesHandler(logger, cases, config.ModeratorToken))

	server := &http.Server{
		Addr:              ":" + config.Port,
		Handler:           mux,
		ReadHeaderTimeout: readHeaderTimeout,
		WriteTimeout:      writeTimeout,
		IdleTimeout:       idleTimeout,
	}

	serverErrors := make(chan error, 1)
	go func() {
		logger.Info("backend listening", "port", config.Port)
		serverErrors <- server.ListenAndServe()
	}()

	select {
	case err := <-serverErrors:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
		return nil
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
		defer cancel()
		return server.Shutdown(shutdownCtx)
	}
}

type healthResponse struct {
	Status   string `json:"status"`
	Database string `json:"database"`
}

// livenessHandler answers without touching the database, so a short database outage does not get the process restarted.
func livenessHandler(logger *slog.Logger) http.HandlerFunc {
	return func(writer http.ResponseWriter, _ *http.Request) {
		writeJSON(logger, writer, http.StatusOK, map[string]string{"status": "ok"})
	}
}

func healthHandler(logger *slog.Logger, pool *pgxpool.Pool) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		response := healthResponse{Status: "ok", Database: "ok"}
		statusCode := http.StatusOK
		if err := pingDatabase(request.Context(), pool); err != nil {
			logger.Error("health check failed", "error", err)
			response = healthResponse{Status: "degraded", Database: "unavailable"}
			statusCode = http.StatusServiceUnavailable
		}
		writeJSON(logger, writer, statusCode, response)
	}
}

func writeJSON(logger *slog.Logger, writer http.ResponseWriter, statusCode int, body any) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(statusCode)
	if err := json.NewEncoder(writer).Encode(body); err != nil {
		logger.Error("write response failed", "error", err)
	}
}

type retentionPurger interface {
	purgeOlderThan(ctx context.Context, cutoff time.Time) (int64, error)
}

// purgeLoop deletes stored runs and cases older than the retention period until ctx is cancelled.
func purgeLoop(ctx context.Context, logger *slog.Logger, retention time.Duration, purgers ...retentionPurger) {
	ticker := time.NewTicker(purgeInterval)
	defer ticker.Stop()
	for {
		for _, purger := range purgers {
			removed, err := purger.purgeOlderThan(ctx, time.Now().Add(-retention))
			if err != nil {
				logger.Error("retention purge failed", "error", err)
			} else if removed > 0 {
				logger.Info("retention purge removed rows", "removed", removed)
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
