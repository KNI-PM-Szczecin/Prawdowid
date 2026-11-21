package agent

import (
	"fmt"
	"regexp"
	"strings"
	"time"
	"unicode"
)

// Hard rules from CONTRACT.md §4. The model's answer is input here, never the final word.

const (
	minQuoteRunes       = 10
	minIndependentSecnd = 2
	freshnessWindow     = 365 * 24 * time.Hour
)

var polishVerdicts = map[string]string{
	"potwierdzone":            VerdictConfirmed,
	"falszywe":                VerdictFalse,
	"fałszywe":                VerdictFalse,
	"wprowadzajace_w_blad":    VerdictMisleading,
	"wprowadzające_w_błąd":    VerdictMisleading,
	"brak_dowodow":            VerdictInsufficientEvidence,
	"brak_dowodów":            VerdictInsufficientEvidence,
	"nie_do_sprawdzenia":      VerdictNotVerifiable,
	"nie_podlega_weryfikacji": VerdictNotVerifiable,
}

var polishRoles = map[string]string{
	"potwierdza": RoleSupports,
	"obala":      RoleRefutes,
	"kontekst":   RoleContext,
	"supports":   RoleSupports,
	"refutes":    RoleRefutes,
	"context":    RoleContext,
}

// mapVerdict turns the model's Polish label into a contract verdict; anything unknown is an abstention.
func mapVerdict(label string) string {
	if verdict, ok := polishVerdicts[strings.ToLower(strings.TrimSpace(label))]; ok {
		return verdict
	}
	return VerdictInsufficientEvidence
}

func mapRole(label string) string {
	if role, ok := polishRoles[strings.ToLower(strings.TrimSpace(label))]; ok {
		return role
	}
	return RoleContext
}

var quoteLikeRunes = strings.NewReplacer(
	"„", "\"", "”", "\"", "“", "\"", "‚", "'", "’", "'", "‘", "'", "–", "-", "—", "-", "…", "...",
)

// normalizeForMatch makes quote matching tolerant to whitespace, case and typographic punctuation only.
func normalizeForMatch(text string) string {
	text = quoteLikeRunes.Replace(text)
	text = strings.ToLower(text)
	fields := strings.FieldsFunc(text, unicode.IsSpace)
	return strings.Join(fields, " ")
}

// quoteInPassage checks that the quote is a verbatim part of the passage (rule 1 in prompts/README.md).
func quoteInPassage(quote, passage string) bool {
	normalizedQuote := normalizeForMatch(quote)
	if len([]rune(normalizedQuote)) < minQuoteRunes {
		return false
	}
	return strings.Contains(normalizeForMatch(passage), normalizedQuote)
}

// validateCitations keeps only citations whose id exists and whose quote is really in that passage.
func validateCitations(citations []judgeCitation, passages map[string]Passage) (valid []SourceRef, dropped int) {
	valid = []SourceRef{} // never nil: the contract promises a list, and JSON must say [] not null
	seen := map[string]bool{}
	for _, citation := range citations {
		passage, ok := passages[citation.ID]
		if !ok || seen[citation.ID] || !quoteInPassage(citation.Quote, passage.Passage) {
			dropped++
			continue
		}
		seen[citation.ID] = true
		valid = append(valid, SourceRef{
			ID:          passage.ChunkID,
			Title:       passage.Title,
			Publisher:   passage.Publisher,
			PublishedAt: passage.PublishedAt,
			FetchedAt:   passage.FetchedAt,
			URL:         passage.URL,
			License:     passage.License,
			SourceType:  passage.SourceType,
			Role:        mapRole(citation.Role),
			Quote:       strings.TrimSpace(citation.Quote),
		})
	}
	return valid, dropped
}

// Fact-checker ratings as rag renders them: "Ocena weryfikatora (Demagog): Fałsz. ..."
var factcheckRating = regexp.MustCompile(`Ocena weryfikatora \(([^)]+)\): ([^.]+)`)

// factcheckVerdict maps a fact-checker's textual rating to a verdict; unknown ratings return ok=false.
func factcheckVerdict(passageText string) (publisher, verdict string, ok bool) {
	match := factcheckRating.FindStringSubmatch(passageText)
	if match == nil {
		return "", "", false
	}
	rating := strings.ToLower(match[2])
	switch {
	case strings.Contains(rating, "częściow"), strings.Contains(rating, "manipulac"),
		strings.Contains(rating, "brak kontekstu"), strings.Contains(rating, "wprowadza"),
		strings.Contains(rating, "półprawda"), strings.Contains(rating, "nieaktualn"):
		return match[1], VerdictMisleading, true
	case strings.Contains(rating, "fałsz"), strings.Contains(rating, "falsz"), strings.Contains(rating, "nieprawd"):
		return match[1], VerdictFalse, true
	case strings.Contains(rating, "prawda"):
		return match[1], VerdictConfirmed, true
	case strings.Contains(rating, "nieweryfikowaln"), strings.Contains(rating, "niesprawdzaln"):
		return match[1], VerdictNotVerifiable, true
	}
	return match[1], "", false
}

// evidence summarises what the valid sources can carry.
type evidence struct {
	strength  string
	reasons   []string
	supports  int
	refutes   int
	official  bool
	factcheck string // publisher of a fact-check among the sources, if any
}

func assessEvidence(sources []SourceRef, now time.Time) evidence {
	result := evidence{strength: StrengthNone}
	if len(sources) == 0 {
		result.reasons = []string{reasonNoSources}
		return result
	}
	secondaryPublishers := map[string]bool{}
	decisive := 0
	fresh := false
	for _, source := range sources {
		switch source.Role {
		case RoleSupports:
			result.supports++
		case RoleRefutes:
			result.refutes++
		}
		if source.Role != RoleContext {
			decisive++
			switch source.SourceType {
			case SourceTypeOfficial:
				result.official = true
			case SourceTypeFactcheck:
				result.factcheck = source.Publisher
			case SourceTypeSecondary:
				secondaryPublishers[strings.ToLower(source.Publisher)] = true
			}
		}
		if source.PublishedAt != nil {
			if published, err := time.Parse(time.RFC3339, *source.PublishedAt); err == nil && now.Sub(published) <= freshnessWindow {
				fresh = true
			}
		}
	}
	switch {
	case result.official:
		result.strength, result.reasons = StrengthStrong, []string{reasonOfficial}
	case result.factcheck != "":
		result.strength, result.reasons = StrengthStrong, []string{fmt.Sprintf(reasonFactcheck, result.factcheck)}
	case len(secondaryPublishers) >= minIndependentSecnd:
		result.strength, result.reasons = StrengthStrong, []string{reasonTwoSecondary}
	case decisive > 0:
		result.strength, result.reasons = StrengthModerate, []string{reasonOneSecondary}
	default:
		result.strength, result.reasons = StrengthWeak, []string{reasonContextOnly}
	}
	if fresh {
		result.reasons = append(result.reasons, reasonFresh)
	} else {
		result.reasons = append(result.reasons, reasonDated)
	}
	return result
}

// decision is the outcome of applying the rules to the model's proposal.
type decision struct {
	verdict     string
	missing     *string
	limitations []string
	consistent  bool
}

// factcheckRuling says how the ratings of the cited fact-checks relate to the model's verdict.
type factcheckRuling struct {
	agrees            bool   // some cited fact-check rates the claim the same way as the model
	conflicts         bool   // some cited fact-check rates it differently
	conflictPublisher string // first fact-checker whose rating differs
}

var roleForFactcheckVerdict = map[string]string{
	VerdictFalse:         RoleRefutes,
	VerdictConfirmed:     RoleSupports,
	VerdictMisleading:    RoleContext,
	VerdictNotVerifiable: RoleContext,
}

// applyFactcheckRatings reads the rating from the full passage of every cited fact-check (the quote may be only
// the claim part). A rating that matches the model's verdict aligns the citation role with it. A rating that differs
// is not applied: the fact-checker may have rated a different claim on the same topic (CONTRACT.md §4: the rating is
// evidence, not a ready verdict, and topical similarity is not enough), so decide turns it into an abstention.
func applyFactcheckRatings(sources []SourceRef, passages map[string]Passage, proposed string) factcheckRuling {
	ruling := factcheckRuling{}
	for index := range sources {
		if sources[index].SourceType != SourceTypeFactcheck {
			continue
		}
		passage, ok := passages[sources[index].ID]
		if !ok {
			continue
		}
		publisher, verdict, known := factcheckVerdict(passage.Passage)
		if !known {
			continue
		}
		if verdict == proposed {
			sources[index].Role = roleForFactcheckVerdict[verdict]
			ruling.agrees = true
			continue
		}
		if !ruling.conflicts {
			ruling.conflicts = true
			ruling.conflictPublisher = publisher
		}
	}
	return ruling
}

// decide applies CONTRACT.md §4: confirmed/false need strong evidence with matching roles; a cited fact-check whose
// rating differs from the model's verdict makes the claim an abstention; otherwise weak evidence also abstains.
func decide(claimID, proposed string, modelMissing *string, sources []SourceRef, ev evidence, dropped int, ruling factcheckRuling) decision {
	result := decision{verdict: proposed, missing: modelMissing, consistent: true}
	if ruling.conflicts && !ruling.agrees {
		result.limitations = append(result.limitations, fmt.Sprintf(limitationFactcheckMismatch, claimID, ruling.conflictPublisher))
		result.consistent = false
		if proposed != VerdictInsufficientEvidence {
			result.verdict = VerdictInsufficientEvidence
			result.missing = stringPtr(missingFactcheckMismatch)
		}
	}
	switch result.verdict {
	case VerdictNotVerifiable:
		result.missing = nil
		return result
	case VerdictInsufficientEvidence:
		if result.missing == nil || strings.TrimSpace(*result.missing) == "" {
			result.missing = stringPtr(missingWeakEvidence)
		}
		return result
	}
	needsRole := RoleSupports
	if result.verdict == VerdictFalse {
		needsRole = RoleRefutes
	}
	roleMatches := (needsRole == RoleSupports && ev.supports > 0) || (needsRole == RoleRefutes && ev.refutes > 0)
	if result.verdict == VerdictMisleading {
		roleMatches = ev.supports+ev.refutes > 0 || len(sources) > 0
	}
	if len(sources) == 0 {
		result.verdict = VerdictInsufficientEvidence
		result.missing = stringPtr(missingNoValidQuote)
		if dropped == 0 {
			result.missing = stringPtr(missingNoSources)
		}
		return result
	}
	if result.verdict != VerdictMisleading && (ev.strength != StrengthStrong || !roleMatches) {
		result.verdict = VerdictInsufficientEvidence
		result.missing = stringPtr(missingWeakEvidence)
		return result
	}
	if !roleMatches {
		result.verdict = VerdictInsufficientEvidence
		result.missing = stringPtr(missingWeakEvidence)
		return result
	}
	result.missing = nil
	return result
}

func stringPtr(value string) *string { return &value }

const maxSingleStatementRunes = 300

// A sentence ends with . ! ? or … followed by a capital letter. An ordinal number ("po 65. roku życia") is followed by
// a lowercase word, so it does not split the statement.
var sentenceBoundary = regexp.MustCompile(`[.!?…]\s+\p{Lu}`)

// isSingleStatement decides whether the submission is already one claim, so extraction can be skipped. Questions go
// through extraction, which rewrites them as statements; checked as they are, they would read as no claim at all.
func isSingleStatement(input string) bool {
	trimmed := strings.TrimSpace(input)
	if len([]rune(trimmed)) > maxSingleStatementRunes || strings.Contains(trimmed, "\n") || strings.HasSuffix(trimmed, "?") {
		return false
	}
	return !sentenceBoundary.MatchString(trimmed)
}
