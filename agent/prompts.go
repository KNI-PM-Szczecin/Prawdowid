package agent

import (
	"embed"
	"fmt"
	"strconv"
	"strings"
)

//go:embed prompts/*.md
var promptFiles embed.FS

// Prompt templates are data (prompts/README.md); placeholders are {{name}}.
type promptSet struct {
	extractSystem string
	extractUser   string
	judgeSystem   string
	judgeUser     string
}

func loadPrompts() (promptSet, error) {
	read := func(name string) (string, error) {
		content, err := promptFiles.ReadFile("prompts/" + name)
		if err != nil {
			return "", fmt.Errorf("read prompt %s: %w", name, err)
		}
		// Git may check the files out with CRLF on Windows; the model and tests expect LF only.
		return strings.TrimSpace(strings.ReplaceAll(string(content), "\r\n", "\n")), nil
	}
	var set promptSet
	var err error
	if set.extractSystem, err = read("extract.system.md"); err != nil {
		return set, err
	}
	if set.extractUser, err = read("extract.user.md"); err != nil {
		return set, err
	}
	if set.judgeSystem, err = read("judge.system.md"); err != nil {
		return set, err
	}
	if set.judgeUser, err = read("judge.user.md"); err != nil {
		return set, err
	}
	return set, nil
}

func render(template string, values map[string]string) string {
	out := template
	for name, value := range values {
		out = strings.ReplaceAll(out, "{{"+name+"}}", value)
	}
	return out
}

func (s promptSet) extractMessages(input string, maxClaims int) (system, user string) {
	system = render(s.extractSystem, map[string]string{"max_claims": strconv.Itoa(maxClaims)})
	user = render(s.extractUser, map[string]string{"input": input})
	return system, user
}

// judgeMessages puts the claim and rag's contextXml into the user message only: sources are data, never rules.
func (s promptSet) judgeMessages(claim, contextXML, today string) (system, user string) {
	user = render(s.judgeUser, map[string]string{"claim": claim, "context_xml": contextXML, "today": today})
	return s.judgeSystem, user
}
