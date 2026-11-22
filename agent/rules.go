package agent

import (
	"cmp"
	"fmt"
	"regexp"
	"slices"
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
	byDocument := map[string]int{}
	for _, citation := range citations {
		passage, ok := passages[citation.ID]
		if !ok || seen[citation.ID] || !quoteInPassage(citation.Quote, passage.Passage) {
			dropped++
			continue
		}
		seen[citation.ID] = true
		// Two fragments of one document are one source for the citizen and one confirmation for the rules; a decisive
		// role wins over context, otherwise the first quote stays.
		if index, duplicate := byDocument[passage.DocumentID]; duplicate {
			if valid[index].Role == RoleContext && mapRole(citation.Role) != RoleContext {
				valid[index].ID = passage.ChunkID
				valid[index].Role = mapRole(citation.Role)
				valid[index].Quote = strings.TrimSpace(citation.Quote)
			}
			continue
		}
		byDocument[passage.DocumentID] = len(valid)
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

const (
	// maxFallbackSources caps the passages shown as context when the model cited nothing valid.
	maxFallbackSources = 2
	// maxFallbackQuoteRunes caps the verbatim opening of a passage shown as the quote of a context source.
	maxFallbackQuoteRunes = 280
)

// fallbackSources picks the best-scored passages with full metadata (title, publisher, publication date, link) as
// context for an abstention without valid citations, so the citizen sees what was found. They never carry a verdict:
// the role is always context and the quote is the verbatim opening of the passage. Flagged passages are skipped.
func fallbackSources(results []Passage) []SourceRef {
	candidates := make([]Passage, 0, len(results))
	for _, passage := range results {
		if hasFullMetadata(passage) && !slices.Contains(passage.Flags, flagSuspectedInjection) {
			candidates = append(candidates, passage)
		}
	}
	slices.SortStableFunc(candidates, func(left, right Passage) int { return cmp.Compare(right.Score, left.Score) })
	sources := []SourceRef{}
	seenDocuments := map[string]bool{}
	for _, passage := range candidates {
		if len(sources) == maxFallbackSources {
			break
		}
		quote := passageOpening(passage.Passage, maxFallbackQuoteRunes)
		if seenDocuments[passage.DocumentID] || len([]rune(quote)) < minQuoteRunes {
			continue
		}
		seenDocuments[passage.DocumentID] = true
		sources = append(sources, SourceRef{
			ID:          passage.ChunkID,
			Title:       passage.Title,
			Publisher:   passage.Publisher,
			PublishedAt: passage.PublishedAt,
			FetchedAt:   passage.FetchedAt,
			URL:         passage.URL,
			License:     passage.License,
			SourceType:  passage.SourceType,
			Role:        RoleContext,
			Quote:       quote,
		})
	}
	return sources
}

func hasFullMetadata(passage Passage) bool {
	return strings.TrimSpace(passage.Title) != "" && strings.TrimSpace(passage.Publisher) != "" &&
		passage.PublishedAt != nil && strings.TrimSpace(*passage.PublishedAt) != "" &&
		strings.TrimSpace(passage.URL) != "" && strings.TrimSpace(passage.FetchedAt) != "" && passage.ChunkID != ""
}

var sentenceEnd = regexp.MustCompile(`[.!?…]\s`)

// passageOpening returns the verbatim start of a passage, at most limit runes long, cut after the last full sentence
// that fits, or else at the last word boundary, so the quote is never a broken word.
func passageOpening(text string, limit int) string {
	trimmed := strings.TrimSpace(text)
	runes := []rune(trimmed)
	if len(runes) <= limit {
		return trimmed
	}
	head := string(runes[:limit])
	if ends := sentenceEnd.FindAllStringIndex(head, -1); len(ends) > 0 {
		cut := strings.TrimSpace(head[:ends[len(ends)-1][1]])
		if len([]rune(cut)) >= minQuoteRunes {
			return cut
		}
	}
	if space := strings.LastIndexFunc(head, unicode.IsSpace); space > 0 {
		return strings.TrimSpace(head[:space])
	}
	return head
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

// Word stems that name the act of checking ("sprawdzał", "zweryfikował", "zbadał") and fact-checkers in general;
// publishers are matched by name, so the rule works for any fact-checker the sources carry. "Ocenił" is left out on
// purpose: "X ocenił to jako prawdę" is a claim about the rating itself and must be checked against it.
var (
	checkingVerbStems    = []string{"sprawdz", "weryfikow", "zbada"}
	factcheckerWordStems = []string{"weryfikator", "fact-check", "factcheck", "fact check"}
)

// minPublisherNameRunes keeps a blank or one-letter publisher from matching every claim.
const minPublisherNameRunes = 3

// isFactcheckMetaClaim reports whether the claim is about a fact-checker's check itself ("X sprawdzał, czy …"), not
// about the checked fact. Such a claim is true when the check exists, whatever rating the fact-checker gave.
func isFactcheckMetaClaim(claimText string, publishers ...string) bool {
	lowered := strings.ToLower(claimText)
	if !containsAny(lowered, checkingVerbStems) {
		return false
	}
	if containsAny(lowered, factcheckerWordStems) {
		return true
	}
	for _, publisher := range publishers {
		name := strings.ToLower(strings.TrimSpace(publisher))
		if len([]rune(name)) >= minPublisherNameRunes && strings.Contains(lowered, name) {
			return true
		}
	}
	return false
}

func containsAny(text string, stems []string) bool {
	for _, stem := range stems {
		if strings.Contains(text, stem) {
			return true
		}
	}
	return false
}

// applyFactcheckRatings reads the rating from the full passage of every cited fact-check (the quote may be only
// the claim part). A rating that matches the model's verdict aligns the citation role with it. A rating that differs
// is not applied: the fact-checker may have rated a different claim on the same topic (CONTRACT.md §4: the rating is
// evidence, not a ready verdict, and topical similarity is not enough), so decide turns it into an abstention.
// For a claim about the check itself (isFactcheckMetaClaim) the rating says nothing about the claim: the cited
// fact-check supports a confirmed verdict (the check exists) and is otherwise left as the model cited it.
func applyFactcheckRatings(claimText string, sources []SourceRef, passages map[string]Passage, proposed string) factcheckRuling {
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
		if isFactcheckMetaClaim(claimText, sources[index].Publisher, publisher) {
			if proposed == VerdictConfirmed {
				sources[index].Role = RoleSupports
				ruling.agrees = true
			}
			continue
		}
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
// Misleading needs a decisive citation (supports or refutes) or an agreeing fact-check rating: a source that is only
// context, e.g. about another place or period than the claim, settles nothing (prompt rules 7 and 11).
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
		roleMatches = ev.supports+ev.refutes > 0 || ruling.agrees
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

// minClaimWords: a single word ("Polska", "test", "x") states nothing that sources could confirm or refute, and rag/
// rejects queries under 3 characters, which would surface as a technical error instead of a request to clarify.
const minClaimWords = 2

// hasEnoughWords reports whether the text has at least minClaimWords words of letters or digits.
func hasEnoughWords(text string) bool {
	words := strings.FieldsFunc(text, func(character rune) bool {
		return !unicode.IsLetter(character) && !unicode.IsDigit(character)
	})
	return len(words) >= minClaimWords
}

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

// A yes/no question in Polish keeps statement word order after "czy", so dropping "czy" and "?" gives the claim.
var yesNoQuestion = regexp.MustCompile(`(?i)^czy\s+(.+?)\s*\?+$`)

// questionAsStatement turns one short yes/no question ("Czy we Włoszech był strajk?") into the statement it asks
// about. It is the fallback when extraction returns no claim for such a question: the model sometimes skips vague
// questions, but the citizen still asked about a fact. Anything longer or with several sentences returns false.
func questionAsStatement(input string) (string, bool) {
	trimmed := strings.TrimSpace(input)
	if len([]rune(trimmed)) > maxSingleStatementRunes || strings.Contains(trimmed, "\n") || sentenceBoundary.MatchString(trimmed) {
		return "", false
	}
	match := yesNoQuestion.FindStringSubmatch(trimmed)
	if match == nil {
		return "", false
	}
	body := []rune(match[1])
	body[0] = unicode.ToUpper(body[0])
	return string(body) + ".", true
}
