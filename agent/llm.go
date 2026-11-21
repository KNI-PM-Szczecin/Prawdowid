package agent

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const (
	// Deterministic answers: the same input must give the same verdict on every channel (CONTRACT.md §2).
	llmTemperature  = 0.0
	llmMaxTokens    = 400
	maxErrorBodyLen = 200
)

// Completion is one model answer with token counts for cost logging.
type Completion struct {
	Text         string
	InputTokens  int
	OutputTokens int
}

// LLMProvider is the only thing the rest of agent/ knows about the model (CONTRACT.md §5).
// system holds the rules; user holds the claim and the sources, which are data.
type LLMProvider interface {
	Name() string
	Generate(ctx context.Context, system, user string) (Completion, error)
}

// ErrLLMUnavailable marks transport, auth and quota failures: a technical_error, never a verdict.
var ErrLLMUnavailable = errors.New("llm unavailable")

// OpenAICompatibleProvider talks to any /v1/chat/completions server, including FastFlowLM (think disabled).
type OpenAICompatibleProvider struct {
	baseURL string
	apiKey  string
	model   string
	client  *http.Client
}

// NewOpenAICompatibleProvider builds a provider; apiKey may be empty for local servers.
func NewOpenAICompatibleProvider(baseURL, apiKey, model string, timeout time.Duration) *OpenAICompatibleProvider {
	return &OpenAICompatibleProvider{
		baseURL: strings.TrimRight(baseURL, "/"),
		apiKey:  apiKey,
		model:   model,
		client:  &http.Client{Timeout: timeout},
	}
}

func (p *OpenAICompatibleProvider) Name() string { return p.model }

type chatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type chatRequest struct {
	Model       string        `json:"model"`
	Messages    []chatMessage `json:"messages"`
	Temperature float64       `json:"temperature"`
	MaxTokens   int           `json:"max_tokens"`
	Think       bool          `json:"think"` // Qwen3 on FastFlowLM: thinking off keeps answers short and JSON-only
}

type chatResponse struct {
	Choices []struct {
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	} `json:"choices"`
	Usage struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
	} `json:"usage"`
}

// Generate sends system and user messages separately; source text never reaches the system message.
func (p *OpenAICompatibleProvider) Generate(ctx context.Context, system, user string) (Completion, error) {
	payload, err := json.Marshal(chatRequest{
		Model:       p.model,
		Messages:    []chatMessage{{Role: "system", Content: system}, {Role: "user", Content: user}},
		Temperature: llmTemperature,
		MaxTokens:   llmMaxTokens,
		Think:       false,
	})
	if err != nil {
		return Completion{}, fmt.Errorf("encode chat request: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, p.baseURL+"/chat/completions", bytes.NewReader(payload))
	if err != nil {
		return Completion{}, fmt.Errorf("build chat request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	if p.apiKey != "" {
		request.Header.Set("Authorization", "Bearer "+p.apiKey)
	}
	response, err := p.client.Do(request)
	if err != nil {
		return Completion{}, fmt.Errorf("%w: %w", ErrLLMUnavailable, err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return Completion{}, fmt.Errorf("%w: read response: %w", ErrLLMUnavailable, err)
	}
	if response.StatusCode != http.StatusOK {
		return Completion{}, fmt.Errorf("%w: HTTP %d: %s", ErrLLMUnavailable, response.StatusCode, truncate(string(body), maxErrorBodyLen))
	}
	var parsed chatResponse
	if err := json.Unmarshal(body, &parsed); err != nil {
		return Completion{}, fmt.Errorf("%w: decode response: %w", ErrLLMUnavailable, err)
	}
	if len(parsed.Choices) == 0 {
		return Completion{}, fmt.Errorf("%w: no choices in response", ErrLLMUnavailable)
	}
	return Completion{
		Text:         parsed.Choices[0].Message.Content,
		InputTokens:  parsed.Usage.PromptTokens,
		OutputTokens: parsed.Usage.CompletionTokens,
	}, nil
}

func truncate(text string, limit int) string {
	if len(text) <= limit {
		return text
	}
	return text[:limit]
}
