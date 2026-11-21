package agent

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"time"
)

const (
	defaultRagURL         = "http://localhost:8001"
	defaultLLMBaseURL     = "http://127.0.0.1:52625/v1"
	defaultLLMModel       = "qwen3:0.6b"
	defaultMaxClaims      = 3
	defaultVerifyTimeout  = 25 * time.Second // CONTRACT.md §2
	defaultRagTimeout     = 8 * time.Second  // CONTRACT.md §2
	defaultLLMTimeout     = 10 * time.Second
	defaultSearchTopK     = 5
	defaultExtractMaxText = 6000 // characters of page/submission text handed to the extraction prompt
)

// Config is read from the environment by the backend and passed to New; nothing here is secret except LLMAPIKey.
type Config struct {
	RagURL         string
	LLMBaseURL     string
	LLMAPIKey      string
	LLMModel       string
	MaxClaims      int
	SearchTopK     int
	VerifyTimeout  time.Duration
	RagTimeout     time.Duration
	LLMTimeout     time.Duration
	ExtractMaxText int
}

// ConfigFromEnv builds the configuration from RAG_URL, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL and AGENT_* variables.
func ConfigFromEnv() (Config, error) {
	config := Config{
		RagURL:         stringFromEnv("RAG_URL", defaultRagURL),
		LLMBaseURL:     stringFromEnv("LLM_BASE_URL", defaultLLMBaseURL),
		LLMAPIKey:      os.Getenv("LLM_API_KEY"),
		LLMModel:       stringFromEnv("LLM_MODEL", defaultLLMModel),
		VerifyTimeout:  defaultVerifyTimeout,
		RagTimeout:     defaultRagTimeout,
		LLMTimeout:     defaultLLMTimeout,
		SearchTopK:     defaultSearchTopK,
		ExtractMaxText: defaultExtractMaxText,
	}
	var err error
	if config.MaxClaims, err = intFromEnv("AGENT_MAX_CLAIMS", defaultMaxClaims); err != nil {
		return Config{}, err
	}
	if config.LLMBaseURL == "" {
		return Config{}, errors.New("LLM_BASE_URL is empty")
	}
	return config, nil
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
