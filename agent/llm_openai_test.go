package agent

import (
	"encoding/json"
	"testing"
	"time"
)

func payloadFields(t *testing.T, baseURL, effort string) map[string]any {
	t.Helper()
	provider := NewOpenAICompatibleProvider(baseURL, "key", "gpt-6-luna", time.Second).WithReasoningEffort(effort)
	raw, err := provider.payload("rules", "claim")
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]any
	if err := json.Unmarshal(raw, &fields); err != nil {
		t.Fatal(err)
	}
	return fields
}

func TestOpenAIPayloadOmitsRejectedFields(t *testing.T) {
	fields := payloadFields(t, "https://api.openai.com/v1", "")
	for _, rejected := range []string{"temperature", "max_tokens", "think"} {
		if _, present := fields[rejected]; present {
			t.Errorf("OpenAI payload must not contain %q", rejected)
		}
	}
	if fields["max_completion_tokens"] != float64(openAIMaxCompletionTokens) {
		t.Errorf("max_completion_tokens = %v", fields["max_completion_tokens"])
	}
	if fields["reasoning_effort"] != "none" {
		t.Errorf("reasoning_effort = %v, want none", fields["reasoning_effort"])
	}
}

func TestOpenAIReasoningEffortOverride(t *testing.T) {
	if got := payloadFields(t, "https://api.openai.com/v1/", "low")["reasoning_effort"]; got != "low" {
		t.Errorf("reasoning_effort = %v, want low", got)
	}
}

func TestLocalPayloadUnchanged(t *testing.T) {
	fields := payloadFields(t, "http://127.0.0.1:52625/v1", "low")
	if fields["max_tokens"] != float64(llmMaxTokens) || fields["temperature"] != float64(0) || fields["think"] != false {
		t.Errorf("local payload changed: %v", fields)
	}
	for _, openAIOnly := range []string{"max_completion_tokens", "reasoning_effort"} {
		if _, present := fields[openAIOnly]; present {
			t.Errorf("local payload must not contain %q", openAIOnly)
		}
	}
}

func TestIsOpenAIOnlyForHostedAPI(t *testing.T) {
	cases := map[string]bool{
		"https://api.openai.com/v1":      true,
		"https://API.OPENAI.COM/v1":      true,
		"https://openrouter.ai/api/v1":   false,
		"http://127.0.0.1:52625/v1":      false,
		"https://api.openai.com.evil.io": false,
	}
	for baseURL, want := range cases {
		if got := NewOpenAICompatibleProvider(baseURL, "", "m", time.Second).isOpenAI(); got != want {
			t.Errorf("isOpenAI(%q) = %v, want %v", baseURL, got, want)
		}
	}
}
