package main

import (
	"regexp"
	"strings"
	"unicode"
)

const (
	maskPlaceholder = "[ukryto]"

	peselLength       = 11
	peselCenturyShift = 20
	peselCheckModulus = 10
	monthsInYear      = 12
	numberJoiners     = ".,-/"
)

// peselWeights are the official weights for the first ten PESEL digits.
var peselWeights = [peselLength - 1]int{1, 3, 7, 9, 1, 3, 7, 9, 1, 3}

// amountWords start a word that makes the digits before them an amount, share or count, never personal data.
var amountWords = []string{"zł", "pln", "mln", "mld", "tys", "eur", "usd", "%", "proc"}

var datePattern = regexp.MustCompile(`\b\d{4}[-./]\d{1,2}[-./]\d{1,2}\b|\b\d{1,2}[-./]\d{1,2}[-./]\d{4}\b`)

// maskRule finds candidates with a regular expression (RE2 has no lookahead) and masks only those that pass confirm.
// guardNumbers adds the checks that keep amounts, dates and parts of longer numbers readable.
type maskRule struct {
	pattern      *regexp.Regexp
	confirm      func(text string, start, end int) bool
	guardNumbers bool
}

// Order matters: e-mail and IBAN first, then PESEL, which would otherwise be swallowed by a phone pattern.
var maskRules = []maskRule{
	{pattern: regexp.MustCompile(`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`)},
	{pattern: regexp.MustCompile(`\b(?:[Pp][Ll] ?)?\d{2}(?: ?\d{4}){6}\b`)},
	{pattern: regexp.MustCompile(`\b\d{6}[ -]?\d{5}\b`), confirm: isValidPesel, guardNumbers: true},
	{pattern: regexp.MustCompile(`(?:\+|\b00)\d(?:[ ().-]{0,2}\d){7,14}`), confirm: isInternationalPhone, guardNumbers: true},
	{pattern: regexp.MustCompile(`\(\d{2}\)[ .-]?\d{3}[ .-]?\d{2}[ .-]?\d{2}\b`), guardNumbers: true},
	{pattern: regexp.MustCompile(`\b[4-8]\d{2}[ .-]?\d{3}[ .-]?\d{3}\b`), guardNumbers: true},
}

// maskPersonalData hides obvious personal data (e-mail, IBAN, PESEL, phone number) before text is stored or sent on.
func maskPersonalData(text string) string {
	for _, rule := range maskRules {
		text = rule.apply(text)
	}
	return text
}

func (r maskRule) apply(text string) string {
	locations := r.pattern.FindAllStringIndex(text, -1)
	if locations == nil {
		return text
	}
	var dateSpans [][]int
	if r.guardNumbers {
		dateSpans = datePattern.FindAllStringIndex(text, -1)
	}

	var builder strings.Builder
	copied := 0
	for _, location := range locations {
		start, end := location[0], location[1]
		if r.confirm != nil && !r.confirm(text, start, end) {
			continue
		}
		if r.guardNumbers && (isAmountOrPartOfNumber(text, start, end) || overlapsAny(dateSpans, start, end)) {
			continue
		}
		builder.WriteString(text[copied:start])
		builder.WriteString(maskPlaceholder)
		copied = end
	}
	builder.WriteString(text[copied:])
	return builder.String()
}

func isValidPesel(text string, start, end int) bool {
	digits := digitsOnly(text[start:end])
	if len(digits) != peselLength {
		return false
	}
	month := int(digits[2]-'0')*10 + int(digits[3]-'0')
	if !isValidPeselMonth(month) {
		return false
	}
	sum := 0
	for index, weight := range peselWeights {
		sum += int(digits[index]-'0') * weight
	}
	control := (peselCheckModulus - sum%peselCheckModulus) % peselCheckModulus
	return control == int(digits[peselLength-1]-'0')
}

// isValidPeselMonth accepts the month codes of the centuries 1800-2299: month, month+20, +40, +60 and +80.
func isValidPeselMonth(code int) bool {
	month := code % peselCenturyShift
	return month >= 1 && month <= monthsInYear
}

const (
	minInternationalDigits = 8
	maxInternationalDigits = 15
)

// isInternationalPhone counts the digits after the + or 00 prefix. A 00 that follows another digit group
// ("5 000 000 000 000") is a big number, not a dialling prefix.
func isInternationalPhone(text string, start, end int) bool {
	candidate := text[start:end]
	digitCount := len(digitsOnly(candidate))
	if strings.HasPrefix(candidate, "00") {
		digitCount -= len("00")
		before := strings.TrimRightFunc(text[:start], unicode.IsSpace)
		if before != "" && isDigitByte(before[len(before)-1]) {
			return false
		}
	}
	return digitCount >= minInternationalDigits && digitCount <= maxInternationalDigits
}

func digitsOnly(text string) string {
	var builder strings.Builder
	for _, character := range text {
		if character >= '0' && character <= '9' {
			builder.WriteRune(character)
		}
	}
	return builder.String()
}

// isAmountOrPartOfNumber reports digits that are followed by a currency, percent or magnitude word,
// or that are glued to a longer number (decimal part, date, thousands group).
func isAmountOrPartOfNumber(text string, start, end int) bool {
	if start > 0 && isDigitByte(text[start-1]) {
		return true
	}
	if start > 1 && strings.IndexByte(numberJoiners, text[start-1]) >= 0 && isDigitByte(text[start-2]) {
		return true
	}
	if end < len(text) && isDigitByte(text[end]) {
		return true
	}
	if end+1 < len(text) && strings.IndexByte(numberJoiners, text[end]) >= 0 && isDigitByte(text[end+1]) {
		return true
	}
	following := strings.ToLower(strings.TrimLeftFunc(text[end:], unicode.IsSpace))
	for _, word := range amountWords {
		if strings.HasPrefix(following, word) {
			return true
		}
	}
	return false
}

func isDigitByte(character byte) bool {
	return character >= '0' && character <= '9'
}

func overlapsAny(spans [][]int, start, end int) bool {
	for _, span := range spans {
		if start < span[1] && end > span[0] {
			return true
		}
	}
	return false
}
