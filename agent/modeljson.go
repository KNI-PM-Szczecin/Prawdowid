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

// kindOpinion marks an extracted sentence that is an opinion, a wish or a prediction: it is shown as
// not_verifiable and never searched (CONTRACT.md §4). Anything else is a factual claim.
const kindOpinion = "opinia"

// extractedClaim is one claim the model found in the submission.
type extractedClaim struct {
	Text     string `json:"tekst"`
	Fragment string `json:"fragment"`
	Kind     string `json:"rodzaj"`
}

func (c extractedClaim) isOpinion() bool {
	return strings.EqualFold(strings.TrimSpace(c.Kind), kindOpinion)
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
	// WidelyReported: the claim describes an event of national weight that should already have happened and that the
	// media or institutions would certainly have reported; with no evidence found it earns a warning, not a verdict.
	WidelyReported bool `json:"szeroko_opisane"`
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
// The returned Completion carries the token counts of every attempt, also when both fail.
func askJSON(ctx context.Context, provider LLMProvider, system, user string, target any) (Completion, error) {
	var lastErr error
	var usage Completion
	for attempt := 0; attempt < 2; attempt++ {
		completion, err := provider.Generate(ctx, system, user)
		usage.InputTokens += completion.InputTokens
		usage.OutputTokens += completion.OutputTokens
		if err != nil {
			return usage, err
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
		usage.Text = completion.Text
		return usage, nil
	}
	return usage, lastErr
}
