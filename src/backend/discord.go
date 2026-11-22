package main

import (
	"context"
	"fmt"
	"log/slog"
	"regexp"
	"strings"
	"time"

	"github.com/bwmarrin/discordgo"

	"prawdowid/agent"
)

const (
	discordChannelName     = "discord"
	discordCommandName     = "factcheck"
	discordQueryOption     = "query"
	discordCheckTimeout    = 30 * time.Second
	discordMaxMessageRunes = 2000
	discordTruncatedNote   = "\n\n(odpowiedź skrócona)"
)

// urlPattern mirrors the frontend detectInputType (src/frontend/src/lib/input.ts), so both
// channels classify text and URLs the same way.
var urlPattern = regexp.MustCompile(`(?i)^https?://\S+$`)

// discordBot is the second channel (CONTRACT.md §2): a Discord slash command that runs the
// shared checkHandlers pipeline, so it changes only Channel and the reply format, never the verdict.
type discordBot struct {
	logger    *slog.Logger
	checks    *checkHandlers
	session   *discordgo.Session
	guildID   string
	commandID string
}

func newDiscordBot(logger *slog.Logger, checks *checkHandlers, token, guildID string) (*discordBot, error) {
	session, err := discordgo.New("Bot " + token)
	if err != nil {
		return nil, fmt.Errorf("create discord session: %w", err)
	}
	bot := &discordBot{logger: logger, checks: checks, session: session, guildID: guildID}
	session.AddHandler(bot.handleInteraction)
	return bot, nil
}

// start opens the gateway and registers (or refreshes) the /factcheck command.
func (b *discordBot) start() error {
	if err := b.session.Open(); err != nil {
		return fmt.Errorf("open discord gateway: %w", err)
	}
	command, err := b.registerCommand()
	if err != nil {
		_ = b.session.Close()
		return fmt.Errorf("register discord command: %w", err)
	}
	b.commandID = command.ID
	b.logger.Info("discord bot connected", "guildId", b.guildID, "commandId", b.commandID)
	return nil
}

func (b *discordBot) close() error {
	return b.session.Close()
}

// registerCommand upserts the slash command so repeated starts never stack duplicate commands.
func (b *discordBot) registerCommand() (*discordgo.ApplicationCommand, error) {
	appID := b.session.State.User.ID
	command := factcheckCommand()
	existing, err := b.session.ApplicationCommands(appID, b.guildID)
	if err != nil {
		return nil, err
	}
	for _, cmd := range existing {
		if cmd.Name == discordCommandName {
			return b.session.ApplicationCommandEdit(appID, b.guildID, cmd.ID, command)
		}
	}
	return b.session.ApplicationCommandCreate(appID, b.guildID, command)
}

func factcheckCommand() *discordgo.ApplicationCommand {
	return &discordgo.ApplicationCommand{
		Name:        discordCommandName,
		Description: "Sprawdź doniesienie: podaj tekst albo adres strony, tak jak na stronie Prawdowida.",
		Options: []*discordgo.ApplicationCommandOption{
			{
				Type:        discordgo.ApplicationCommandOptionString,
				Name:        discordQueryOption,
				Description: "Tekst albo adres strony (URL) do sprawdzenia.",
				Required:    true,
			},
		},
	}
}

func (b *discordBot) handleInteraction(session *discordgo.Session, interaction *discordgo.InteractionCreate) {
	if interaction.Type != discordgo.InteractionApplicationCommand {
		return
	}
	data := interaction.ApplicationCommandData()
	if data.Name != discordCommandName {
		return
	}
	b.logger.Info("discord factcheck command",
		"guildId", interaction.GuildID, "channelId", interaction.ChannelID, "userId", discordUserID(interaction.Interaction))

	query, ok := commandQuery(data)
	if !ok {
		b.replyNow(session, interaction, messageEmptyInput)
		return
	}

	requestID, err := newRequestID()
	if err != nil {
		b.logger.Error("generate request id failed", "error", err)
		b.replyNow(session, interaction, messageInternalError)
		return
	}

	inputType := detectInputType(query)
	if message := validateCheck(checkRequest{Input: query, InputType: inputType}); message != "" {
		result := b.checks.nonMerit(requestID, discordChannelName, agent.StatusNeedsClarification, message)
		b.replyNow(session, interaction, formatCheckReply(result))
		return
	}

	// Acknowledge within Discord's 3-second window, then run the shared pipeline and edit the answer in place.
	if err := session.InteractionRespond(interaction.Interaction, &discordgo.InteractionResponse{
		Type: discordgo.InteractionResponseDeferredChannelMessageWithSource,
	}); err != nil {
		b.logger.Error("discord defer reply failed", "requestId", requestID, "error", err)
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), discordCheckTimeout)
	defer cancel()
	result, _ := b.checks.runCheck(ctx, requestID, discordChannelName, query, inputType)

	content := truncateReply(formatCheckReply(result))
	if _, err := session.InteractionResponseEdit(interaction.Interaction, &discordgo.WebhookEdit{Content: &content}); err != nil {
		b.logger.Error("discord edit reply failed", "requestId", requestID, "error", err)
	}
}

func (b *discordBot) replyNow(session *discordgo.Session, interaction *discordgo.InteractionCreate, message string) {
	if err := session.InteractionRespond(interaction.Interaction, &discordgo.InteractionResponse{
		Type: discordgo.InteractionResponseChannelMessageWithSource,
		Data: &discordgo.InteractionResponseData{Content: truncateReply(message)},
	}); err != nil {
		b.logger.Error("discord reply failed", "error", err)
	}
}

// commandQuery returns the trimmed query from the required single string option.
func commandQuery(data discordgo.ApplicationCommandInteractionData) (string, bool) {
	if len(data.Options) == 0 {
		return "", false
	}
	value, ok := data.Options[0].Value.(string)
	if !ok {
		return "", false
	}
	query := strings.TrimSpace(value)
	return query, query != ""
}

// detectInputType classifies an input as url or text exactly like the web frontend.
func detectInputType(input string) string {
	if urlPattern.MatchString(strings.TrimSpace(input)) {
		return agent.InputTypeURL
	}
	return agent.InputTypeText
}

// truncateReply keeps an answer under Discord's 2000-character message limit.
func truncateReply(reply string) string {
	runes := []rune(reply)
	if len(runes) <= discordMaxMessageRunes {
		return reply
	}
	budget := discordMaxMessageRunes - len([]rune(discordTruncatedNote))
	return string(runes[:budget]) + discordTruncatedNote
}

func discordUserID(interaction *discordgo.Interaction) string {
	if interaction.Member != nil && interaction.Member.User != nil {
		return interaction.Member.User.ID
	}
	if interaction.User != nil {
		return interaction.User.ID
	}
	return ""
}
