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
)

// godotenv never overrides variables that are already set, so the real environment
// wins over backend/.env, which wins over the shared root .env.
var envFiles = []string{".env", "../.env"}

type Config struct {
	Port             string
	DatabaseURL      string
	DatabaseMaxConns int32
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

	return Config{
		Port:             stringFromEnv("PORT", defaultPort),
		DatabaseURL:      databaseURL,
		DatabaseMaxConns: int32(maxConns),
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
