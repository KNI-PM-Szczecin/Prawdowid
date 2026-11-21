package main

import "regexp"

const maskPlaceholder = "[ukryto]"

// Order matters: e-mail and PESEL run before the phone pattern, which would otherwise swallow an 11-digit PESEL.
var personalDataPatterns = []*regexp.Regexp{
	regexp.MustCompile(`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`),
	regexp.MustCompile(`\b\d{11}\b`),
	regexp.MustCompile(`(?:(?:\+|00)\d{2}[ -]?)?\b(?:\d[ -]?){8}\d\b`),
}

// maskPersonalData hides obvious personal data (e-mail, PESEL, phone number) before text is stored or sent on.
func maskPersonalData(text string) string {
	for _, pattern := range personalDataPatterns {
		text = pattern.ReplaceAllString(text, maskPlaceholder)
	}
	return text
}
