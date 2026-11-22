package agent

import (
	"strings"
	"unicode/utf8"
)

// findSpan locates a claim in the checked text as code-point offsets (CONTRACT.md §1a): the model's verbatim
// fragment first, then the claim sentence itself. Matching ignores case only; a paraphrase has no span, and the
// front then shows the claim in the list without a highlight.
func findSpan(text string, candidates ...string) *Span {
	lowered := strings.ToLower(text)
	for _, candidate := range candidates {
		candidate = strings.TrimSpace(candidate)
		if candidate == "" {
			continue
		}
		index := strings.Index(lowered, strings.ToLower(candidate))
		if index < 0 {
			continue
		}
		// ToLower maps rune to rune, so rune counts in the lowered text equal those in the original.
		start := utf8.RuneCountInString(lowered[:index])
		return &Span{Start: start, End: start + utf8.RuneCountInString(candidate)}
	}
	return nil
}
