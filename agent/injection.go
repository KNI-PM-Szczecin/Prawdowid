package agent

import (
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"
)

// Instructions hidden in the submission itself (scenario E). rag/ flags them only inside source passages, so the
// agent checks the user's text and fetched pages too. The patterns mirror rag/app/context.py and run on normalized
// text: lowercase, no diacritics, no invisible characters, single spaces. A detected attempt is counted, logged and
// cut out of the text that is checked (stripInstructions), so it never reaches the search query or the model as part
// of a claim; the document shown to the citizen keeps it.
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
	`\bforget\s+(?:about\s+)?(?:everything|all|anything)\b`,
	`\bignore\s+(?:the\s+)?(?:above|everything|anything|all|what)\b`,
	`\b(?:ignore|disregard|forget|ignoring|disregarding)\s+(?:all\s+)?(?:the\s+)?(?:provided\s+|given\s+)?(?:context|articles?|sources?|documents?)\b`,
	`\b(?:not\s+by|not\s+from|not\s+according\s+to)\s+the\s+(?:provided\s+)?(?:articles?|documents?|sources?|context)\b`,
	`\banswer\s+(?:by|from|with)\s+your\s+own\s+knowledge\b`,
	`\b(?:now|here)\s+(?:comes?|is|are)\s+(?:a|the|your|some)?\s*(?:great\s+)?(?:new|next|second|further)\s+(?:tasks?|assignments?|challenge|test|job|orders?)\b`,
	`\b(?:new|additional|further)\s+(?:instructions?|orders?|tasks?)\s+(?:follow|are\s+followed|for\s+you)\b`,
	`\byour\s+(?:new\s+)?(?:instructions?|task|job)\s+(?:is|are)\s+(?:now\s+)?to\b`,
	`\b(?:concentrate|focus)\s+(?:only\s+)?on\s+(?:this|the\s+(?:next|following|new))\s+(?:task|assignment)\b`,
	`\b(?:you\s+are|you're)\s+(?:not\s+)?supposed\s+to\b`,
	`\b(?:don't|do\s+not|never)\s+(?:listen\s+to|follow|pay\s+attention\s+to|look\s+(?:in|at))\s+(?:anything|what|the)\b`,
	`\b(?:just|only)\s+(?:output|print|say|write|reply|respond)\s*:?\s*"`,
	`\b(?:now|okay|ok)[,.!]?\s+you\s+are\s+(?:a|an|the|my)?\s*\w+`,
	`\byou\s+(?:now\s+)?act\s+as\b`,
	`\b(?:imagine|suppose)\s+(?:that\s+)?you\s+are\b`,
	`\byou\s+are\s+role-?\s*playing\b`,
	`\brepeat\s+after\s+me\b`,
	`\b(?:above|previous|initial|original)\s+prompt\b`,
	`\bwhat\s+(?:is|was)\s+written\s+(?:above|before|at\s+the\s+beginning)\b`,
	`\b(?:instructions?|orders?|commands?)\s*:\s*\w`,
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
	`\bzapomnij\s+(?:o\s+)?(?:wszystkim|wszystko|wszystkich)\b`,
	`\bzignoruj\s+(?:to,?\s+)?co\s+(?:bylo\s+)?(?:powyzej|wyzej|wczesniej|przed)`,
	`\b(?:zignoruj|pomin|pomijajac|ignorujac)\s+(?:wszystkie\s+|dostepne\s+|podane\s+)?(?:artykuly|zrodla|dokumenty|kontekst)\b`,
	`\bnie\s+(?:sluchaj|stosuj\s+sie\s+do|zwracaj\s+uwagi\s+na)\s+(?:tego,?\s+)?co\s+(?:bylo\s+)?(?:powyzej|wyzej|wczesniej|napisano|napisalem)`,
	`\b(?:teraz|oto|a\s+teraz)\s+(?:nowe|kolejne|twoje\s+nowe)\s+(?:zadanie|polecenie|wyzwanie)\b`,
	`\b(?:nowe|dodatkowe|kolejne)\s+(?:instrukcje|polecenia)\s+(?:dla\s+ciebie|brzmia|sa\s+nastepujace)\b`,
	`\btwoje\s+(?:nowe\s+)?(?:instrukcje|zadanie|polecenie)\s+(?:to|brzmi)\b`,
	`\b(?:skup|skoncentruj)\s+sie\s+(?:tylko\s+|wylacznie\s+)?na\s+(?:tym|nowym|nastepnym|kolejnym)\s+zadaniu\b`,
	`\b(?:nie\s+wolno|nie\s+mozesz|masz)\s+(?:ci\s+)?(?:mowic|powiedziec|odpowiadac)\b`,
	`\bodpowiadaj\s+(?:zawsze|na\s+kazde\s+pytanie)\b`,
	`\bodpowiadaj\s+(?:z\s+)?wlasn(?:a|ej)\s+wiedz`,
	`\bwyobraz\s+sobie,?\s+ze\s+jestes\b`,
	`\bpowtarzaj\s+za\s+mna\b`,
	`\b(?:napisz|powiedz|wypisz)\s+tylko\s*:?\s*"`,
	// Attempts to dictate the answer: a planted source, a set verdict, a sentence to write.
	`\b(?:zacytuj|cytuj|podaj|wskaz|dodaj|uzyj|wpisz)\s+(?:\w+\s+){0,2}jako\s+(?:zrodlo|dowod)\b`,
	`\bjako\s+(?:zrodlo|dowod)\s+(?:podaj\s+|wpisz\s+)?(?:te\s+|ta\s+)?(?:strone|adres|link)\b`,
	`\bw\s+odpowiedzi\s+(?:koniecznie\s+|prosze\s+|musisz\s+)?(?:zacytuj|napisz|podaj|wpisz|umiesc|dodaj|oznacz)\b`,
	`\b(?:oznacz|ustaw|zmien|wpisz|daj)\s+(?:ten\s+|swoj\s+|twoj\s+)?(?:werdykt|ocene|wynik)\b`,
	`\b(?:werdykt|verdict|ocena)\s*(?:jako|as|=|:)?\s*(?:confirmed|false|true|misleading|potwierdzone|falszywe)\b`,
	`\b(?:napisz|odpowiedz|stwierdz|powiedz|wpisz),?\s+ze\b`,
	`\b(?:cite|use|list|add)\s+(?:\S+\s+){0,3}as\s+(?:a\s+|the\s+)?(?:source|evidence)\b`,
	`\b(?:output|set|give|return|change)\s+(?:the\s+|your\s+)?verdict\b`,
	`\bignore\s+(?:the\s+|all\s+the\s+)?(?:rules|instructions|guidelines)\b`,
	`\[\s*(?:system|assistant|admin|developer|instrukcja|system\s+prompt)\s*\]`,
	`<!--[^>]{0,300}(?:assistant|system|ignore|instruction|zignoruj|polecenie|werdykt|verdict)`,
	// Off-task requests: a fact-check submission never asks for a recipe, a poem or code.
	`\b(?:podaj|napisz|wygeneruj|stworz|wymysl|uloz)\s+(?:mi\s+|nam\s+)?(?:jakis\s+|jakas\s+|jakies\s+)?` +
		`(?:przepis\s+na|wiersz|wierszyk|piosenke|opowiadanie|bajke|zart|dowcip|esej|program|list\s+milosny)\b`,
	`\b(?:write|give|tell|generate|compose)\s+(?:me\s+|us\s+)?(?:a|an|some)\s+(?:recipe|poem|song|story|joke|essay|code)\b`,
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

// clauseEnd ends the cut of an instruction: the end of its sentence (punctuation followed by a space, a new line or the
// end of the text, so the dot of a web address or the "!" of "<!--" does not end it), or the end of the text when the
// sentence never ends (run-on input without punctuation).
var clauseEnd = regexp.MustCompile(`[.!?…]+(?:\s|$)|\n`)

// maxStripRounds bounds the cutting loop; every round removes at least one match, so it only guards against a regex
// that would match an empty string.
const maxStripRounds = 20

// stripInstructions cuts every detected instruction, from where it starts to the end of its sentence, out of the text
// the agent checks. The patterns run on normalized text, so each normalized rune is mapped back to its position in
// the original text and the cut keeps the user's own spelling of the rest.
func stripInstructions(text string) string {
	for range maxStripRounds {
		normalized, origins := normalizeWithOrigins(text)
		location := injectionPatterns.FindStringIndex(normalized)
		if location == nil || location[1] == location[0] {
			break
		}
		original := []rune(text)
		start := sentenceStartIfLead(original, origins[utf8.RuneCountInString(normalized[:location[0]])])
		end := len(original)
		if next := clauseEnd.FindStringIndex(string(original[start:])); next != nil {
			end = start + utf8.RuneCountInString(string(original[start:])[:next[1]])
		}
		text = string(original[:start]) + " " + string(original[end:])
	}
	return strings.Join(strings.Fields(text), " ")
}

// maxLeadWords: an instruction that starts within the first words of its sentence ("Please cite…", "Proszę, zignoruj…")
// takes the whole sentence; further in, the words before it are the user's claim and stay.
const maxLeadWords = 2

// sentenceStartIfLead moves the cut start back to the start of its sentence when only a few words precede it there.
func sentenceStartIfLead(text []rune, start int) int {
	sentenceStart := 0
	for _, location := range clauseEnd.FindAllStringIndex(string(text[:start]), -1) {
		sentenceStart = utf8.RuneCountInString(string(text[:start])[:location[1]])
	}
	if len(strings.Fields(string(text[sentenceStart:start]))) <= maxLeadWords {
		return sentenceStart
	}
	return start
}

// normalizeWithOrigins is normalizeForDetection that also returns, for every rune of the result, the index of the
// rune of text it came from.
func normalizeWithOrigins(text string) (string, []int) {
	var builder strings.Builder
	origins := []int{}
	pendingSpace := false
	for index, character := range []rune(text) {
		switch {
		case unicode.Is(unicode.Cf, character):
			continue
		case unicode.IsSpace(character):
			pendingSpace = builder.Len() > 0
			continue
		}
		if pendingSpace {
			builder.WriteRune(' ')
			origins = append(origins, index)
			pendingSpace = false
		}
		// Lowercasing can turn one rune into several (e.g. "İ"); each of them points back to the same original rune.
		for _, produced := range polishLetters.Replace(strings.ToLower(string(character))) {
			builder.WriteRune(produced)
			origins = append(origins, index)
		}
	}
	return builder.String(), origins
}
