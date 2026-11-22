package main

import (
	"context"
	"fmt"
	"log/slog"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/bwmarrin/discordgo"

	"prawdowid/agent"
)

const (
	discordChannelName     = "discord"
	discordCommandName     = "factcheck"
	discordQueryOption     = "query"
	discordCheckTimeout    = 50 * time.Second // above the agent Verify budget (45 s)
	discordMaxMessageRunes = 2000
	discordTruncatedNote   = "\n\n(odpowiedź skrócona)"

	discordMaxShortSources = 4
	discordExpandHint      = "Daj %s, aby zobaczyć więcej"
	discordCollapseHint    = "Kliknij %s ponownie, aby zwinąć"

	discordReactionAlarm     = "🚨"
	discordReactionQuestion  = "❓"
	discordReactionConfirmed = "✅"
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

	// replies tracks fact-check messages so a reaction can expand or collapse them.
	mu      sync.Mutex
	replies map[string]*discordReply
}

// discordReply holds the two renderings of one fact-check answer plus the reaction that toggles them.
type discordReply struct {
	channelID string
	messageID string
	emoji     string
	short     string
	full      string
	userCount int
}

func newDiscordBot(logger *slog.Logger, checks *checkHandlers, token, guildID string) (*discordBot, error) {
	session, err := discordgo.New("Bot " + token)
	if err != nil {
		return nil, fmt.Errorf("create discord session: %w", err)
	}
	bot := &discordBot{
		logger:  logger,
		checks:  checks,
		session: session,
		guildID: guildID,
		replies: make(map[string]*discordReply),
	}
	session.AddHandler(bot.handleInteraction)
	session.AddHandler(bot.handleReactionAdd)
	session.AddHandler(bot.handleReactionRemove)
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
		b.replyNow(session, interaction, withQuestion(inputType, query, formatCheckReply(result)))
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

	shortContent := truncateReply(withQuestion(inputType, query, formatDiscordReply(result, false)))
	fullContent := truncateReply(withQuestion(inputType, query, formatDiscordReply(result, true)))
	message, err := session.InteractionResponseEdit(interaction.Interaction, &discordgo.WebhookEdit{Content: &shortContent})
	if err != nil {
		b.logger.Error("discord edit reply failed", "requestId", requestID, "error", err)
		return
	}

	// Only substantive answers get the toggle reaction; errors and clarifications stay plain text.
	if result.Status == agent.StatusOK && len(result.Claims) > 0 {
		emoji := discordReactionEmoji(result.Claims[0])
		if err := session.MessageReactionAdd(message.ChannelID, message.ID, emoji); err != nil {
			b.logger.Error("discord add reaction failed", "requestId", requestID, "error", err)
			return
		}
		b.rememberReply(message.ChannelID, message.ID, emoji, shortContent, fullContent)
	}
}

// withQuestion quotes the user's exact input at the top of the reply, so the answer always shows
// what was asked, even when claim extraction rephrases the question into a statement. URL inputs
// skip the prefix: the quoted claim already echoes the link.
func withQuestion(inputType, query, reply string) string {
	if inputType != agent.InputTypeText {
		return reply
	}
	return "Pytanie: " + query + "\n\n" + reply
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

// discordVerdictHeadline is the short Polish label shown as the first line of a Discord answer.
func discordVerdictHeadline(verdict string) string {
	switch verdict {
	case agent.VerdictConfirmed:
		return "Prawdziwe"
	case agent.VerdictFalse:
		return "Fałszywe"
	case agent.VerdictMisleading:
		return "Wprowadzające w błąd"
	case agent.VerdictInsufficientEvidence:
		return "Brak wystarczających dowodów"
	case agent.VerdictNotVerifiable:
		return "Nie podlega weryfikacji"
	default:
		return "Nieznany werdykt"
	}
}

// discordReactionEmoji is the toggle reaction: an alarm for false or misleading results,
// a question mark for abstentions, and a check for confirmed ones.
func discordReactionEmoji(claim agent.Claim) string {
	switch claim.Verdict {
	case agent.VerdictFalse, agent.VerdictMisleading:
		return discordReactionAlarm
	case agent.VerdictInsufficientEvidence, agent.VerdictNotVerifiable:
		return discordReactionQuestion
	default:
		return discordReactionConfirmed
	}
}

// formatDiscordReply renders a CheckResult for Discord. The short form repeats the checked claim,
// the verdict label, a concise justification, up to discordMaxShortSources links and a
// hint to expand; the detailed form adds strength reasons, missing evidence, all sources with
// publisher and quote, limitations and a hint to collapse.
func formatDiscordReply(result agent.CheckResult, detailed bool) string {
	if result.Status != agent.StatusOK {
		if result.Message != nil && strings.TrimSpace(*result.Message) != "" {
			return *result.Message
		}
		return demoFallbackMessage
	}
	if len(result.Claims) == 0 {
		return "Nie znalazłem twierdzeń do sprawdzenia."
	}

	emoji := discordReactionEmoji(result.Claims[0])
	var builder strings.Builder
	for claimIndex, claim := range result.Claims {
		if claimIndex > 0 {
			builder.WriteString("\n\n")
		}
		builder.WriteString("Twierdzenie: ")
		builder.WriteString(singleLine(claim.Text))
		builder.WriteString("\n")
		builder.WriteString(discordHeadline(claim))
		if detailed {
			writeDiscordJustification(&builder, claim)
			writeDiscordSources(&builder, claim, true)
		} else {
			builder.WriteString("\n")
			if justification := singleLine(claim.Justification); justification != "" {
				builder.WriteString(justification)
			}
			writeDiscordSources(&builder, claim, false)
		}
	}
	if detailed && len(result.Limitations) > 0 {
		builder.WriteString("\n\nOgraniczenia:")
		for _, limitation := range result.Limitations {
			builder.WriteString("\n- ")
			builder.WriteString(singleLine(limitation))
		}
	}
	builder.WriteString("\n\n")
	if detailed {
		builder.WriteString(fmt.Sprintf(discordCollapseHint, emoji))
	} else {
		builder.WriteString(fmt.Sprintf(discordExpandHint, emoji))
	}
	return builder.String()
}

// discordHeadline is the verdict label for a claim.
func discordHeadline(claim agent.Claim) string {
	return discordVerdictHeadline(claim.Verdict)
}

// writeDiscordJustification appends the detailed reasoning behind a claim: the justification,
// strength reasons, what could not be established and neutral warnings.
func writeDiscordJustification(builder *strings.Builder, claim agent.Claim) {
	if justification := singleLine(claim.Justification); justification != "" {
		builder.WriteString("\n")
		builder.WriteString(justification)
	}
	if len(claim.StrengthReasons) > 0 {
		builder.WriteString("\n\nDlaczego ta ocena:")
		for _, reason := range claim.StrengthReasons {
			builder.WriteString("\n- ")
			builder.WriteString(singleLine(reason))
		}
	}
	if claim.Missing != nil && strings.TrimSpace(*claim.Missing) != "" {
		builder.WriteString("\n\nCzego nie udało się ustalić: ")
		builder.WriteString(singleLine(*claim.Missing))
	}
	for _, warning := range claim.Warnings {
		builder.WriteString("\n\nOstrzeżenie: ")
		builder.WriteString(singleLine(warning.Message))
	}
}

// writeDiscordSources appends the source list as bullets. The short form shows a link per source
// capped at discordMaxShortSources; the detailed form shows every source with publisher and quote.
func writeDiscordSources(builder *strings.Builder, claim agent.Claim, detailed bool) {
	sources := claim.Sources
	if len(sources) == 0 {
		builder.WriteString("\nŹródła: brak")
		return
	}
	limit := len(sources)
	if !detailed && limit > discordMaxShortSources {
		limit = discordMaxShortSources
	}
	builder.WriteString("\nŹródła:")
	for index := 0; index < limit; index++ {
		source := sources[index]
		builder.WriteString("\n• ")
		title := singleLine(source.Title)
		if source.URL != "" {
			builder.WriteString("[")
			builder.WriteString(title)
			builder.WriteString("](")
			builder.WriteString(source.URL)
			builder.WriteString(")")
		} else {
			builder.WriteString(title)
		}
		if detailed {
			if publisher := singleLine(source.Publisher); publisher != "" {
				builder.WriteString(" — ")
				builder.WriteString(publisher)
			}
			if quote := singleLine(source.Quote); quote != "" {
				builder.WriteString("\n  „")
				builder.WriteString(quote)
				builder.WriteString("”")
			}
		}
	}
	if !detailed && len(sources) > discordMaxShortSources {
		builder.WriteString("\n…")
	}
}

// rememberReply stores a fact-check message so a reaction on it can expand or collapse it.
func (b *discordBot) rememberReply(channelID, messageID, emoji, short, full string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.replies[messageID] = &discordReply{
		channelID: channelID,
		messageID: messageID,
		emoji:     emoji,
		short:     short,
		full:      full,
	}
}

func (b *discordBot) handleReactionAdd(session *discordgo.Session, reaction *discordgo.MessageReactionAdd) {
	b.toggle(session, reaction.MessageReaction, +1)
}

func (b *discordBot) handleReactionRemove(session *discordgo.Session, reaction *discordgo.MessageReactionRemove) {
	b.toggle(session, reaction.MessageReaction, -1)
}

// toggle expands a reply when a user adds the anchor reaction and collapses it when the last
// such reaction is removed; the bot's own reaction is ignored so it does not count as a toggle.
func (b *discordBot) toggle(session *discordgo.Session, reaction *discordgo.MessageReaction, delta int) {
	botID := ""
	if session.State != nil && session.State.User != nil {
		botID = session.State.User.ID
	}
	if reaction.UserID == botID {
		return
	}

	b.mu.Lock()
	reply, found := b.replies[reaction.MessageID]
	if !found || reaction.Emoji.APIName() != reply.emoji {
		b.mu.Unlock()
		return
	}
	reply.userCount += delta
	if reply.userCount < 0 {
		reply.userCount = 0
	}
	content := reply.short
	if reply.userCount > 0 {
		content = reply.full
	}
	channelID, messageID := reply.channelID, reply.messageID
	b.mu.Unlock()

	if _, err := session.ChannelMessageEdit(channelID, messageID, content); err != nil {
		b.logger.Error("discord toggle edit failed", "messageId", messageID, "error", err)
	}
}
