package main

import (
	"context"
	"strings"
	"testing"
	"unicode/utf8"

	"github.com/bwmarrin/discordgo"

	"prawdowid/agent"
)

func TestDetectInputTypeMatchesFrontend(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"Polska jest w Unii Europejskiej", agent.InputTypeText},
		{"https://www.gov.pl/web/zdrowie", agent.InputTypeURL},
		{"HTTP://GOV.PL/komunikat", agent.InputTypeURL},
		{"www.gov.pl/komunikat", agent.InputTypeText}, // no scheme is not a URL for the frontend either
		{"https://", agent.InputTypeText},
		{"  https://gov.pl/a  ", agent.InputTypeURL},
	}
	for _, test := range tests {
		if got := detectInputType(test.input); got != test.want {
			t.Fatalf("detectInputType(%q) = %q, want %q", test.input, got, test.want)
		}
	}
}

func TestCommandQueryExtractsTrimmedOption(t *testing.T) {
	tests := []struct {
		name string
		data discordgo.ApplicationCommandInteractionData
		want string
		ok   bool
	}{
		{
			name: "plain text",
			data: discordgo.ApplicationCommandInteractionData{Options: []*discordgo.ApplicationCommandInteractionDataOption{
				{Name: discordQueryOption, Type: discordgo.ApplicationCommandOptionString, Value: "Polska jest w UE"},
			}},
			want: "Polska jest w UE",
			ok:   true,
		},
		{
			name: "trimmed",
			data: discordgo.ApplicationCommandInteractionData{Options: []*discordgo.ApplicationCommandInteractionDataOption{
				{Value: "  https://gov.pl/a  "},
			}},
			want: "https://gov.pl/a",
			ok:   true,
		},
		{"no options", discordgo.ApplicationCommandInteractionData{}, "", false},
		{"whitespace only", discordgo.ApplicationCommandInteractionData{Options: []*discordgo.ApplicationCommandInteractionDataOption{
			{Value: "   "},
		}}, "", false},
		{"non-string value", discordgo.ApplicationCommandInteractionData{Options: []*discordgo.ApplicationCommandInteractionDataOption{
			{Value: 42},
		}}, "", false},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got, ok := commandQuery(test.data)
			if got != test.want || ok != test.ok {
				t.Fatalf("commandQuery() = %q, %v; want %q, %v", got, ok, test.want, test.ok)
			}
		})
	}
}

func TestFactcheckCommandDefinition(t *testing.T) {
	command := factcheckCommand()
	if command.Name != discordCommandName {
		t.Fatalf("command name %q, want %q", command.Name, discordCommandName)
	}
	if len(command.Options) != 1 {
		t.Fatalf("options %d, want exactly one", len(command.Options))
	}
	option := command.Options[0]
	if option.Name != discordQueryOption || option.Type != discordgo.ApplicationCommandOptionString || !option.Required {
		t.Fatalf("option %+v must be a required string named %q", option, discordQueryOption)
	}
}

func TestTruncateReplyKeepsDiscordLimit(t *testing.T) {
	short := "Krótka odpowiedź."
	if got := truncateReply(short); got != short {
		t.Fatalf("short reply changed: %q", got)
	}

	long := strings.Repeat("ż", 2500)
	truncated := truncateReply(long)
	if count := utf8.RuneCountInString(truncated); count > discordMaxMessageRunes {
		t.Fatalf("truncated reply has %d runes, over the %d limit", count, discordMaxMessageRunes)
	}
	if !strings.HasSuffix(truncated, discordTruncatedNote) {
		t.Fatalf("truncated reply must end with the note, got suffix %q", truncated[len(truncated)-20:])
	}
	if !strings.HasPrefix(truncated, strings.Repeat("ż", 10)) {
		t.Fatal("truncated reply must keep the beginning of the answer")
	}
}

func TestDiscordChannelRunsSharedPipelineWithSameLabels(t *testing.T) {
	handlers, saved := newTestHandlers(func(_ context.Context, request agent.VerifyRequest) (agent.CheckResult, error) {
		return agent.CheckResult{
			RequestID: request.RequestID,
			Status:    agent.StatusOK,
			Claims: []agent.Claim{{
				ID:               "c1",
				Text:             request.Input,
				Verdict:          agent.VerdictFalse,
				Justification:    "Źródła przeczą temu twierdzeniu.",
				EvidenceStrength: agent.StrengthStrong,
				Sources: []agent.SourceRef{{
					ID:         "s1",
					Title:      "Tytuł źródła",
					Publisher:  "Wydawca",
					URL:        "https://example.gov.pl/a",
					SourceType: agent.SourceTypeOfficial,
					Role:       agent.RoleRefutes,
				}},
			}},
		}, nil
	}, 10)

	result, _ := handlers.runCheck(context.Background(), newTestRequestID(t), discordChannelName, "Polska jest w UE", agent.InputTypeText)

	if len(*saved) != 1 || (*saved)[0].Channel != discordChannelName {
		t.Fatalf("stored channel %q, want %q", (*saved)[0].Channel, discordChannelName)
	}
	reply := formatCheckReply(result)
	for _, want := range []string{"Fałszywe", "Tytuł źródła", "Wydawca", "https://example.gov.pl/a"} {
		if !strings.Contains(reply, want) {
			t.Fatalf("discord reply missing %q: %s", want, reply)
		}
	}
}
