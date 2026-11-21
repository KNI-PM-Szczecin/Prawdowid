package agent

import (
	"regexp"
	"strings"
)

// A source on the same topic can carry a different number than the claim ("458 posłów" for a claim about 460), and
// the model tends to cite it as support anyway. A decisive citation must therefore contain every number written in
// the claim. Sources often write numbers in words ("czteroletnie"), so the rule applies only when the cited text has
// numbers in digits of its own; ordinals ("65."), legal references ("art. 98") and dates split by dots are handled
// so they neither trigger nor block the rule.

var (
	digitGroupSpace = regexp.MustCompile(`(\d)[  ](\d{3})\b`)
	numberToken     = regexp.MustCompile(`\d+(?:,\d+)?`)
	legalReference  = regexp.MustCompile(`(?i)(?:art|ust|pkt|poz|nr|par|§)\.?\s*$`)
)

// How rag renders a fact-check passage (rag/app/factcheck.py, passage_text).
const (
	factcheckClaimPrefix  = "Twierdzenie sprawdzone przez weryfikatora faktów:"
	factcheckRatingPrefix = "Ocena weryfikatora"
)

// cardinalNumbers returns the numbers written in digits that state a quantity, a year or a date, normalized
// (no thousands separators, no leading zeros, decimal comma).
func cardinalNumbers(text string) map[string]bool {
	for digitGroupSpace.MatchString(text) {
		text = digitGroupSpace.ReplaceAllString(text, "$1$2")
	}
	numbers := map[string]bool{}
	for _, bounds := range numberToken.FindAllStringIndex(text, -1) {
		start, end := bounds[0], bounds[1]
		isOrdinal := end < len(text) && text[end] == '.' && (end+1 == len(text) || !isASCIIDigit(text[end+1]))
		if isOrdinal || legalReference.MatchString(text[:start]) {
			continue
		}
		numbers[normalizeNumber(text[start:end])] = true
	}
	return numbers
}

func isASCIIDigit(character byte) bool { return character >= '0' && character <= '9' }

func normalizeNumber(token string) string {
	whole, fraction, hasFraction := strings.Cut(token, ",")
	whole = strings.TrimLeft(whole, "0")
	if whole == "" {
		whole = "0"
	}
	if hasFraction {
		return whole + "," + fraction
	}
	return whole
}

// citedClaimText is the text a citation's numbers are compared with: for a fact-check it is the claim the
// fact-checker rated (its rating may be about that claim only), for any other source the quote itself.
func citedClaimText(source SourceRef, passages map[string]Passage) string {
	if source.SourceType != SourceTypeFactcheck {
		return source.Quote
	}
	passage, ok := passages[source.ID]
	if !ok {
		return source.Quote
	}
	_, rest, found := strings.Cut(passage.Passage, factcheckClaimPrefix)
	if !found {
		return source.Quote
	}
	checkedClaim, _, _ := strings.Cut(rest, factcheckRatingPrefix)
	return checkedClaim
}

// demoteMismatchedNumbers turns decisive citations whose numbers differ from the claim's into context. A refuting
// quote may legitimately carry another number (that is how it refutes), so only supporting citations and fact-checks
// (whose rating concerns the exact numbers they checked) are compared. It returns how many citations were demoted.
func demoteMismatchedNumbers(claimText string, sources []SourceRef, passages map[string]Passage) int {
	claimNumbers := cardinalNumbers(claimText)
	if len(claimNumbers) == 0 {
		return 0
	}
	demoted := 0
	for index := range sources {
		source := &sources[index]
		comparable := source.Role == RoleSupports || (source.Role == RoleRefutes && source.SourceType == SourceTypeFactcheck)
		if !comparable {
			continue
		}
		citedNumbers := cardinalNumbers(citedClaimText(*source, passages))
		if len(citedNumbers) == 0 {
			continue
		}
		for number := range claimNumbers {
			if !citedNumbers[number] {
				source.Role = RoleContext
				demoted++
				break
			}
		}
	}
	return demoted
}
