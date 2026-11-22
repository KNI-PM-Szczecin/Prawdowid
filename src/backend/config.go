package main

import (
	"errors"
	"fmt"
	"os"
	"strconv"

	"github.com/joho/godotenv"
)

const (
	defaultPort             = "3001"
	defaultDatabaseMaxConns = 5
	defaultRateLimit        = 20
	defaultRetentionDays    = 30
	defaultArchivalDays     = 365
	defaultRagURL           = "http://localhost:8001"
	defaultTrustedProxyHops = 1
	// defaultModeratorRepeats: three unresolved reports of one question make a case worth a moderator's time.
	defaultModeratorRepeats = 3
)

// godotenv never overrides variables that are already set, so the real environment
// wins over backend/.env, which wins over the shared root .env.
var envFiles = []string{".env", "../.env"}

type Config struct {
	Port             string
	DatabaseURL      string
	DatabaseMaxConns int32
	// RateLimitPerMinute is the number of checks one client address may start per minute.
	RateLimitPerMinute int
	// RetentionDays is how long stored check runs are kept before they are deleted.
	RetentionDays int
	// ArchivalDays is the age of the newest source after which material is flagged as archival.
	ArchivalDays int
	// RagURL is the rag service address, the same variable the agent reads.
	RagURL string
	// TrustedProxyHops is how many proxies append to X-Forwarded-For before the backend; the rate limiter reads that entry from the right.
	TrustedProxyHops int
	// ModeratorRepeatThreshold is the number of similar unresolved reports after which a case is recommended.
	ModeratorRepeatThreshold int
	// ModeratorWebhookURL receives recommended cases (https only); empty means cases are only recommended, never forwarded.
	ModeratorWebhookURL string
	// ModeratorToken opens GET /api/admin/cases; empty keeps the list closed.
	ModeratorToken string
}

func loadConfig() (Config, error) {
	for _, path := range envFiles {
		if err := godotenv.Load(path); err != nil && !errors.Is(err, os.ErrNotExist) {
			return Config{}, fmt.Errorf("load %s: %w", path, err)
		}
	}

	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		return Config{}, errors.New("DATABASE_URL is not set, see .env.example")
	}

	maxConns, err := intFromEnv("DATABASE_MAX_CONNS", defaultDatabaseMaxConns)
	if err != nil {
		return Config{}, err
	}

	rateLimit, err := intFromEnv("CHECK_RATE_LIMIT_PER_MINUTE", defaultRateLimit)
	if err != nil {
		return Config{}, err
	}
	retentionDays, err := intFromEnv("CHECK_RETENTION_DAYS", defaultRetentionDays)
	if err != nil {
		return Config{}, err
	}

	archivalDays, err := intFromEnv("BADGE_ARCHIVAL_DAYS", defaultArchivalDays)
	if err != nil {
		return Config{}, err
	}

	trustedProxyHops, err := intFromEnv("TRUSTED_PROXY_HOPS", defaultTrustedProxyHops)
	if err != nil {
		return Config{}, err
	}

	moderatorRepeats, err := intFromEnv("MODERATOR_REPEAT_THRESHOLD", defaultModeratorRepeats)
	if err != nil {
		return Config{}, err
	}
	webhookURL := os.Getenv("MODERATOR_WEBHOOK_URL")
	if webhookURL != "" && !validWebhookURL(webhookURL) {
		return Config{}, errors.New("MODERATOR_WEBHOOK_URL must be an https URL")
	}

	return Config{
		Port:               stringFromEnv("PORT", defaultPort),
		DatabaseURL:        databaseURL,
		DatabaseMaxConns:   int32(maxConns),
		RateLimitPerMinute: rateLimit,
		RetentionDays:      retentionDays,
		ArchivalDays:       archivalDays,
		RagURL:             stringFromEnv("RAG_URL", defaultRagURL),
		TrustedProxyHops:   trustedProxyHops,

		ModeratorRepeatThreshold: moderatorRepeats,
		ModeratorWebhookURL:      webhookURL,
		ModeratorToken:           os.Getenv("MODERATOR_TOKEN"),
	}, nil
}

func stringFromEnv(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}

func intFromEnv(name string, fallback int) (int, error) {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value < 1 {
		return 0, fmt.Errorf("%s must be a positive integer, got %q", name, raw)
	}
	return value, nil
}
