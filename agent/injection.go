package agent

import (
	"regexp"
	"strings"
	"unicode"
)

// Instructions hidden in the submission itself (scenario E). rag/ flags them only inside source passages, so the
// agent checks the user's text and fetched pages too. The patterns mirror rag/app/context.py and run on normalized
// text: lowercase, no diacritics, no invisible characters, single spaces. Detection only counts and logs the attempt;
// the text is still checked as data.
const (
	injectionEarlier   = `(?:previous|prior|above|earlier|preceding|original|system|all|any|your|these|those)`
	injectionRules     = `(?:instructions?|rules|prompts?|directions|guidelines|messages|context)`
	injectionPLEarlier = `(?:wszystkie|wszystkich|wszelkie|poprzednie|poprzednich|powyzsze|powyzszych|wczesniejsze|` +
		`wczesniejszych|dotychczasowe|dotychczasowych|swoje|swoich|twoje|twoich|systemowe|systemowych|o)`
	injectionPLRules = `(?:instrukcje|instrukcji|instrukcjach|polecenia|polecen|poleceniach|zasady|zasad|zasadach|` +
		`reguly|regul|regulach|wytyczne|wytycznych|prompt)`
)

var injectionPatterns = regexp.MustCompile(strings.Join([]string{
	`\b(?:ignore|disregard|forget|override|bypass)\s+(?:(?:the|all|any|your|of)\s+)*` + injectionEarlier + `\s+` + injectionRules,
	`\bnew\s+(?:task|instructions?|role|objective|system\s+prompt)\s*:`,
	`\byou\s+are\s+now\b`,
	`\bfrom\s+now\s+on,?\s+you\b`,
	`\b(?:act\s+as|pretend\s+(?:to\s+be|you\s+are)|roleplay\s+as)\s+(?:an?|the|my)\b`,
	`\bsystem\s+(?:prompt|message)\b`,
	`\bdeveloper\s+(?:mode|message)\b`,
	`\bjailbreak`,
	`\b(?:reveal|print|show|repeat)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions)`,
	`\b(?:classify|rate|mark|label)\s+(?:this|the|it)(?:\s+claim)?\s+as\s+(?:true|verified|confirmed|false)`,
	`\b(?:respond|answer|reply|output)\s+only\s+with\b`,
	`<\s*/?\s*(?:system|instructions?|assistant|im_start|im_end|zrodlo|dostepne_zrodla)\s*>`,
	`<\|im_(?:start|end)\|>`,
	`\[/?inst\]`,
	`#{2,}\s*(?:instruction|system)`,
	`\b(?:zignoruj|pomin|zapomnij\s+o|olej|nie\s+stosuj\s+sie\s+do|nie\s+bierz\s+pod\s+uwage)\s+(?:` +
		injectionPLEarlier + `\s+)*` + injectionPLRules,
	`\bnowe\s+(?:zadanie|polecenie|instrukcje|instrukcja)\s*:`,
	`\b(?:od\s+teraz|odtad)\s+(?:jestes|bedziesz|masz)\b`,
	`\bjestes\s+teraz\b`,
	`\budawaj,?\s+ze\b`,
	`\bwciel\s+sie\s+w\b`,
	`\b(?:prompt|komunikat)\s+systemowy\b`,
	`\binstrukcje\s+systemowe\b`,
	`\btryb\s+(?:dewelopera|developera)\b`,
	`\b(?:ujawnij|pokaz|wypisz|powtorz)\s+(?:swoj|swoje|twoj|twoje)\s+(?:prompt|instrukcje|polecenia)`,
	`\b(?:ocen|oznacz|uznaj|zaklasyfikuj|oceniaj)\s+(?:to|ten|te|ta|je|go)?\s*\w*\s*(?:jako|za)\s+` +
		`(?:prawdziw|potwierdzon|wiarygodn|falszyw)`,
	`\b(?:odpowiedz|odpowiadaj)\s+(?:tylko|wylacznie)\b`,
}, "|"))

var polishLetters = strings.NewReplacer("ą", "a", "ć", "c", "ę", "e", "ł", "l", "ń", "n", "ó", "o", "ś", "s", "ź", "z", "ż", "z")

// normalizeForDetection strips invisible characters (zero-width space, soft hyphen), case and Polish diacritics so
// obfuscated variants hit the same patterns.
func normalizeForDetection(text string) string {
	visible := strings.Map(func(character rune) rune {
		if unicode.Is(unicode.Cf, character) {
			return -1
		}
		return character
	}, text)
	return strings.Join(strings.Fields(polishLetters.Replace(strings.ToLower(visible))), " ")
}

// containsInstructions reports whether the text looks like an attempt to steer the model.
func containsInstructions(text string) bool {
	return injectionPatterns.MatchString(normalizeForDetection(text))
}
