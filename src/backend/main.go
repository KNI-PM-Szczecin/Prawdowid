package main

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	readHeaderTimeout = 10 * time.Second
	shutdownTimeout   = 10 * time.Second
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

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", healthHandler(logger, pool))

	server := &http.Server{
		Addr:              ":" + config.Port,
		Handler:           mux,
		ReadHeaderTimeout: readHeaderTimeout,
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
