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
	// Hosted OpenAI list prices for gpt-6-luna (USD per 1M tokens, https://platform.openai.com/docs/pricing).
	// Both can be changed with LLM_PRICE_INPUT_PER_M and LLM_PRICE_OUTPUT_PER_M.
	defaultLLMPriceInputPerM  = 0.10
	defaultLLMPriceOutputPerM = 0.50
)

// Config is read from the environment by the backend and passed to New; nothing here is secret except LLMAPIKey.
type Config struct {
	RagURL     string
	LLMBaseURL string
	LLMAPIKey  string
	LLMModel   string
	// LLMReasoningEffort applies only to api.openai.com; empty keeps the provider default ("none").
	LLMReasoningEffort string
	MaxClaims          int
	SearchTopK         int
	// LLMPriceInputPerM and LLMPriceOutputPerM are USD per 1M tokens used for meta.estimatedCostUsd.
	// They stay 0 for local servers, where a check costs nothing.
	LLMPriceInputPerM  float64
	LLMPriceOutputPerM float64
	VerifyTimeout      time.Duration
	RagTimeout         time.Duration
	LLMTimeout         time.Duration
	ExtractMaxText     int
}

// ConfigFromEnv builds the configuration from RAG_URL, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL and AGENT_* variables.
func ConfigFromEnv() (Config, error) {
	config := Config{
		RagURL:     stringFromEnv("RAG_URL", defaultRagURL),
		LLMBaseURL: stringFromEnv("LLM_BASE_URL", defaultLLMBaseURL),
		LLMAPIKey:  os.Getenv("LLM_API_KEY"),
		LLMModel:   stringFromEnv("LLM_MODEL", defaultLLMModel),

		LLMReasoningEffort: os.Getenv("LLM_REASONING_EFFORT"),
		VerifyTimeout:      defaultVerifyTimeout,
		RagTimeout:         defaultRagTimeout,
		LLMTimeout:         defaultLLMTimeout,
		SearchTopK:         defaultSearchTopK,
		ExtractMaxText:     defaultExtractMaxText,
	}
	var err error
	if config.MaxClaims, err = intFromEnv("AGENT_MAX_CLAIMS", defaultMaxClaims); err != nil {
		return Config{}, err
	}
	if config.LLMBaseURL == "" {
		return Config{}, errors.New("LLM_BASE_URL is empty")
	}
	if !isHostedOpenAI(config.LLMBaseURL) {
		// Local servers are free; a price there would only invent a cost for a check.
		config.LLMPriceInputPerM, config.LLMPriceOutputPerM = 0, 0
	} else if config.LLMPriceInputPerM, err = floatFromEnv("LLM_PRICE_INPUT_PER_M", defaultLLMPriceInputPerM); err != nil {
		return Config{}, err
	} else if config.LLMPriceOutputPerM, err = floatFromEnv("LLM_PRICE_OUTPUT_PER_M", defaultLLMPriceOutputPerM); err != nil {
		return Config{}, err
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

func floatFromEnv(name string, fallback float64) (float64, error) {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.ParseFloat(raw, 64)
	if err != nil || value < 0 {
		return 0, fmt.Errorf("%s must be a non-negative number, got %q", name, raw)
	}
	return value, nil
}
