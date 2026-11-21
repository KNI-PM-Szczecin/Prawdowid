package agent

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

// ErrModelAnswer means the model replied, but not with the JSON the prompt asked for (after one retry).
var ErrModelAnswer = errors.New("model answer is not valid JSON")

// extractedClaim is one claim the model found in the submission.
type extractedClaim struct {
	Text     string `json:"tekst"`
	Fragment string `json:"fragment"`
}

type extractAnswer struct {
	Claims  []extractedClaim `json:"twierdzenia"`
	Omitted int              `json:"pominiete"`
}

// judgeCitation is one quote the model attributed to a source id.
type judgeCitation struct {
	ID    string `json:"id"`
	Quote string `json:"cytat"`
	Role  string `json:"rola"`
}

type judgeAnswer struct {
	Verdict       string          `json:"werdykt"`
	Justification string          `json:"uzasadnienie"`
	Citations     []judgeCitation `json:"cytaty"`
	Missing       *string         `json:"brakuje"`
	Suspicious    bool            `json:"podejrzane"`
}

// firstJSONObject cuts the first balanced {...} out of a model answer that may carry stray text around it.
func firstJSONObject(text string) (string, bool) {
	start := strings.Index(text, "{")
	if start < 0 {
		return "", false
	}
	depth := 0
	inString := false
	escaped := false
	for i := start; i < len(text); i++ {
		char := text[i]
		switch {
		case escaped:
			escaped = false
		case char == '\\' && inString:
			escaped = true
		case char == '"':
			inString = !inString
		case inString:
		case char == '{':
			depth++
		case char == '}':
			depth--
			if depth == 0 {
				return text[start : i+1], true
			}
		}
	}
	return "", false
}

// askJSON runs the model and decodes its JSON answer into target, retrying once on malformed output.
func askJSON(ctx context.Context, provider LLMProvider, system, user string, target any) (Completion, error) {
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		completion, err := provider.Generate(ctx, system, user)
		if err != nil {
			return completion, err
		}
		object, found := firstJSONObject(completion.Text)
		if !found {
			lastErr = fmt.Errorf("%w: no object in %q", ErrModelAnswer, truncate(completion.Text, maxErrorBodyLen))
			continue
		}
		if err := json.Unmarshal([]byte(object), target); err != nil {
			lastErr = fmt.Errorf("%w: %w", ErrModelAnswer, err)
			continue
		}
		return completion, nil
	}
	return Completion{}, lastErr
}
