package agent

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"regexp"
	"strings"
	"sync"
	"time"
)

// Agent wires the model, rag/ and the rules; create one with New and share it between channels.
type Agent struct {
	config   Config
	provider LLMProvider
	rag      *RagClient
	prompts  promptSet
	logger   *slog.Logger
	now      func() time.Time
}

// New builds an Agent for the given provider; the rag client is created from config.RagURL.
func New(config Config, provider LLMProvider, logger *slog.Logger) (*Agent, error) {
	prompts, err := loadPrompts()
	if err != nil {
		return nil, err
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Agent{
		config:   config,
		provider: provider,
		rag:      NewRagClient(config.RagURL, config.RagTimeout),
		prompts:  prompts,
		logger:   logger,
		now:      time.Now,
	}, nil
}

// NewFromEnv is the one-call constructor for the backend: config and provider from the environment.
func NewFromEnv(logger *slog.Logger) (*Agent, error) {
	config, err := ConfigFromEnv()
	if err != nil {
		return nil, err
	}
	provider := NewOpenAICompatibleProvider(config.LLMBaseURL, config.LLMAPIKey, config.LLMModel, config.LLMTimeout).
		WithReasoningEffort(config.LLMReasoningEffort)
	return New(config, provider, logger)
}

type run struct {
	claimRun
	startedAt time.Time
	result    CheckResult
	material  *MaterialMatch
	// archival is set when the checked page is older than the freshness window (scenario B).
	archival bool
}

// claimRun holds what one claim contributes to the answer; claims run in parallel, so each one writes here
// and the results are merged in claim order afterwards.
type claimRun struct {
	request VerifyRequest
	// materialDate is the publication date of the checked page (YYYY-MM-DD) or empty when unknown or for text input.
	materialDate string
	limitations  []string
	injections   int
	searchErrs   int
	// factcheckDown is set when the fact-check service failed for this claim's search (CONTRACT.md §4).
	factcheckDown bool
	passages      int
	inputTokens   int
	outputTokens  int
	corpus        *string
	abstained     bool
	campaign      *CampaignAlert
}

// claimConcurrency caps parallel claims: each one is a rag search plus a model call, and three is both the
// default claim limit and enough to use the rag replica without flooding it.
const claimConcurrency = 3

// tokenUsage is what the model billed for one or more calls; it feeds meta.estimatedCostUsd.
type tokenUsage struct {
	input  int
	output int
}

func usageOf(completion Completion) tokenUsage {
	return tokenUsage{input: completion.InputTokens, output: completion.OutputTokens}
}

func (r *claimRun) addUsage(usage tokenUsage) {
	r.inputTokens += usage.input
	r.outputTokens += usage.output
}

func (r *run) mergeClaim(claim claimRun) {
	r.passages += claim.passages
	r.inputTokens += claim.inputTokens
	r.outputTokens += claim.outputTokens
	r.injections += claim.injections
	r.searchErrs += claim.searchErrs
	r.abstained = r.abstained || claim.abstained
	if claim.corpus != nil {
		r.corpus = claim.corpus
	}
	r.limitations = append(r.limitations, claim.limitations...)
	if r.campaign == nil && claim.campaign != nil {
		r.campaign = claim.campaign
	}
}

// estimateCost turns token counts into USD; both prices are per 1M tokens and 0 means a free local model.
func estimateCost(inputTokens, outputTokens int, priceInputPerM, priceOutputPerM float64) float64 {
	const tokensPerMillion = 1_000_000
	return float64(inputTokens)/tokensPerMillion*priceInputPerM + float64(outputTokens)/tokensPerMillion*priceOutputPerM
}

// Verify checks one submission from any channel (CONTRACT.md §2). Dependency failures become
// status technical_error; the error return is reserved for programming mistakes.
func (a *Agent) Verify(ctx context.Context, request VerifyRequest) (CheckResult, error) {
	ctx, cancel := context.WithTimeout(ctx, a.config.VerifyTimeout)
	defer cancel()
	r := &run{request: request, startedAt: a.now()}
	r.result = CheckResult{
		RequestID:   request.RequestID,
		Status:      StatusOK,
		Claims:      []Claim{},
		Limitations: []string{},
	}

	input := strings.TrimSpace(request.Input)
	if input == "" {
		return a.finish(r, StatusNeedsClarification, msgEmptyInput), nil
	}

	if request.InputType != InputTypeURL && !hasEnoughWords(input) {
		return a.finish(r, StatusNeedsClarification, msgNoClaims), nil
	}

	text, document, err := a.resolveInput(ctx, r, request)
	if err != nil {
		if errors.Is(err, ErrFetchRejected) {
			a.logger.Warn("page unreadable", "requestId", request.RequestID, "error", err.Error())
			status, message := rejectedPageAnswer(fetchRejectionCode(err))
			return a.finish(r, status, message), nil
		}
		return a.technicalError(r, err), nil
	}
	if document == nil {
		// The text the agent checked (already masked by the backend): claims[].span points into it.
		document = &Document{Text: text}
	}
	r.result.Document = document
	if document.URL != nil {
		r.material = a.matchMaterial(ctx, r, document)
		r.materialDate = a.noteMaterialAge(r, document)
	}
	if containsInstructions(text) {
		r.injections++
		r.limitations = append(r.limitations, limitationInputInstructions)
		a.logger.Warn("prompt injection in submission", "requestId", request.RequestID, "inputType", request.InputType)
	}

	claims, omitted, usage, err := a.extractClaims(ctx, text)
	r.addUsage(usage)
	if err != nil {
		return a.technicalError(r, err), nil
	}
	if len(claims) == 0 {
		return a.finish(r, StatusNeedsClarification, msgNoClaims), nil
	}
	if omitted > 0 {
		r.limitations = append(r.limitations, fmt.Sprintf(limitationClaimsSkipped, len(claims), len(claims)+omitted))
	}

	checked, err := a.checkClaims(ctx, r.claimRun, claims)
	if err != nil {
		return a.technicalError(r, err), nil
	}
	for index := range checked {
		r.mergeClaim(checked[index].run)
		checked[index].claim.Span = findSpan(document.Text, claims[index].Fragment, claims[index].Text)
		if r.archival {
			checked[index].claim.Warnings = append(checked[index].claim.Warnings,
				Warning{Type: WarningArchivalMaterial, Message: fmt.Sprintf(warningArchivalMaterial, r.materialDate)})
		}
		r.result.Claims = append(r.result.Claims, checked[index].claim)
	}
	return a.finish(r, StatusOK, ""), nil
}

// noteMaterialAge records the page's publication date for the judge and flags a page older than the freshness
// window (brief scenario B: true material shown as current). The age is context beside the verdict, never a verdict.
func (a *Agent) noteMaterialAge(r *run, document *Document) string {
	if document == nil || document.PublishedAt == nil {
		r.limitations = appendUnique(r.limitations, limitationMaterialDateUnknown)
		return ""
	}
	published, err := time.Parse(time.RFC3339, *document.PublishedAt)
	if err != nil {
		a.logger.Warn("unparseable material date", "requestId", r.request.RequestID, "publishedAt", *document.PublishedAt)
		r.limitations = appendUnique(r.limitations, limitationMaterialDateUnknown)
		return ""
	}
	date := published.UTC().Format("2006-01-02")
	if a.now().Sub(published) > freshnessWindow {
		r.archival = true
		r.limitations = appendUnique(r.limitations, fmt.Sprintf(limitationArchivalMaterial, date))
	}
	return date
}

type checkedClaim struct {
	claim Claim
	run   claimRun
}

// checkClaims runs one claim per worker, at most claimConcurrency at a time, and returns the results in claim order.
// The answer therefore does not depend on which search finishes first (CONTRACT.md §2: the same input must give the
// same verdict). A failure surfaces after every worker stops, so a technical_error never carries partial claims.
// An opinion needs no worker: it is not_verifiable by definition and is never searched.
func (a *Agent) checkClaims(ctx context.Context, shared claimRun, claims []extractedClaim) ([]checkedClaim, error) {
	results := make([]checkedClaim, len(claims))
	errs := make([]error, len(claims))
	semaphore := make(chan struct{}, claimConcurrency)
	var wait sync.WaitGroup
	for index, extracted := range claims {
		claimID := fmt.Sprintf("c%d", index+1)
		if extracted.isOpinion() {
			results[index] = checkedClaim{claim: opinionClaim(claimID, extracted.Text), run: claimRun{request: shared.request, abstained: true}}
			continue
		}
		wait.Add(1)
		go func(index int, claimText string) {
			defer wait.Done()
			semaphore <- struct{}{}
			defer func() { <-semaphore }()
			local := claimRun{request: shared.request, materialDate: shared.materialDate}
			claim, err := a.checkClaim(ctx, &local, claimID, claimText)
			if err != nil {
				errs[index] = err
				return
			}
			results[index] = checkedClaim{claim: claim, run: local}
		}(index, extracted.Text)
	}
	wait.Wait()
	for _, err := range errs {
		if err != nil {
			return nil, err
		}
	}
	return results, nil
}

// rejectedPageAnswer maps rag's reason for not reading a page to the status and message for the citizen.
// A video or social-media address is out of scope by design; everything else asks for the text instead.
func rejectedPageAnswer(code string) (status, message string) {
	switch code {
	case FetchCodeUnsupportedHost:
		return StatusOutOfScope, msgUnsupportedService
	case FetchCodeNotHTML:
		return StatusNeedsClarification, msgPageIsFile
	case FetchCodeBotWall, FetchCodeNoText:
		return StatusNeedsClarification, msgPageBlocked
	default:
		return StatusNeedsClarification, msgPageUnreadable
	}
}

// resolveInput returns the text to check and, when a page was fetched, the document. A URL submission fetches
// that page; a text with exactly one link inside fetches the link as part of the checked material (mentor
// scenario E: "check this page too"), and a failure there only adds a limitation.
func (a *Agent) resolveInput(ctx context.Context, r *run, request VerifyRequest) (string, *Document, error) {
	input := strings.TrimSpace(request.Input)
	if request.InputType == InputTypeURL {
		page, err := a.rag.Fetch(ctx, input)
		if err != nil {
			return "", nil, err
		}
		document := a.documentFromPage(page)
		return pageText(page), document, nil
	}

	links := findLinks(input)
	switch {
	case len(links) == 0:
		return input, nil, nil
	case len(links) > 1:
		r.limitations = appendUnique(r.limitations, limitationLinksSkipped)
		return input, nil, nil
	}
	link := links[0]
	page, err := a.rag.Fetch(ctx, link)
	if err != nil {
		a.logger.Warn("link inside text not fetched", "requestId", request.RequestID, "error", err.Error())
		limitation := limitationLinkNotFetched
		if fetchRejectionCode(err) == FetchCodeUnsupportedHost {
			limitation = limitationLinkUnsupported
		}
		r.limitations = appendUnique(r.limitations, fmt.Sprintf(limitation, link))
		return input, nil, nil
	}
	r.limitations = appendUnique(r.limitations, fmt.Sprintf(limitationLinkFetched, link))
	text := input + "\n\n" + pageText(page)
	document := a.documentFromPage(page)
	document.Text = text
	return text, document, nil
}

func (a *Agent) documentFromPage(page FetchResponse) *Document {
	fetchedAt := a.now().UTC().Format(time.RFC3339)
	document := &Document{Text: page.Text, URL: stringPtr(page.URL), PublishedAt: page.PublishedAt, FetchedAt: &fetchedAt}
	if page.Title != "" {
		document.Title = stringPtr(page.Title)
	}
	return document
}

func pageText(page FetchResponse) string {
	if page.Title != "" {
		return page.Title + "\n" + page.Text
	}
	return page.Text
}

var linkPattern = regexp.MustCompile(`https?://[^\s<>"']+`)

// findLinks returns the http(s) addresses inside a text, without the punctuation that closes a sentence after them.
func findLinks(text string) []string {
	var links []string
	for _, match := range linkPattern.FindAllString(text, -1) {
		if link := strings.TrimRight(match, ".,;:!?)]}>"); link != "" {
			links = append(links, link)
		}
	}
	return links
}

// matchMaterial asks rag whether the submitted page is a known material (brief scenario I). The answer is context
// beside the verdict, so a failure here only logs and adds a limitation; it never turns the check into an error.
func (a *Agent) matchMaterial(ctx context.Context, r *run, document *Document) *MaterialMatch {
	if document == nil || document.URL == nil {
		return nil
	}
	response, err := a.rag.MatchMaterial(ctx, *document.URL, document.Title, document.PublishedAt)
	if err != nil {
		a.logger.Warn("material match failed", "requestId", r.request.RequestID, "error", err.Error())
		r.limitations = appendUnique(r.limitations, limitationMaterialMatchUnavailable)
		return nil
	}
	if len(response.Matches) == 0 {
		r.limitations = appendUnique(r.limitations, limitationNoMaterialMatch)
		return nil
	}
	return &MaterialMatch{Message: materialMatchMessage(response.Matches), Matches: response.Matches}
}

// materialMatchMessage names the strongest basis explicitly: the citizen must see why the page was recognised.
func materialMatchMessage(matches []MaterialMatchItem) string {
	byURL, incident := false, false
	for _, match := range matches {
		if match.Kind == MaterialKindIncident {
			incident = true
		}
		for _, basis := range match.Basis {
			if basis == MaterialBasisURL {
				byURL = true
			}
		}
	}
	switch {
	case incident:
		return materialMatchIncident
	case byURL:
		return materialMatchByURL
	default:
		return materialMatchByTitleAndDate
	}
}

// opinionClaim is the answer for a sentence the extractor marked as an opinion or a prediction (CONTRACT.md §4).
func opinionClaim(claimID, text string) Claim {
	return Claim{
		ID:               claimID,
		Text:             text,
		Verdict:          VerdictNotVerifiable,
		Justification:    justificationOpinion,
		EvidenceStrength: StrengthNone,
		StrengthReasons:  []string{reasonOpinion},
		Sources:          []SourceRef{},
		Warnings:         []Warning{},
	}
}

// asSingleClaim wraps text the agent checks as it is (no extraction), so the whole text is also its fragment.
func asSingleClaim(text string) []extractedClaim {
	trimmed := strings.TrimSpace(text)
	return []extractedClaim{{Text: trimmed, Fragment: trimmed}}
}

// extractClaims returns the claims to check: the input itself for a single statement, otherwise the model's list.
// The usage covers every model call made here, including a retry after malformed JSON.
func (a *Agent) extractClaims(ctx context.Context, text string) ([]extractedClaim, int, tokenUsage, error) {
	if isSingleStatement(text) {
		return asSingleClaim(text), 0, tokenUsage{}, nil
	}
	runes := []rune(text)
	if len(runes) > a.config.ExtractMaxText {
		text = string(runes[:a.config.ExtractMaxText])
	}
	system, user := a.prompts.extractMessages(text, a.config.MaxClaims)
	var answer extractAnswer
	completion, err := askJSON(ctx, a.provider, system, user, &answer)
	if err != nil {
		if errors.Is(err, ErrModelAnswer) {
			// A single statement that only looked complex: check it as it is rather than fail the request.
			a.logger.Warn("claim extraction returned no JSON, checking the input as one claim", "error", err.Error())
			return asSingleClaim(text), 0, usageOf(completion), nil
		}
		return nil, 0, usageOf(completion), err
	}
	claims := make([]extractedClaim, 0, len(answer.Claims))
	for _, claim := range answer.Claims {
		if trimmed := strings.TrimSpace(claim.Text); hasEnoughWords(trimmed) {
			claims = append(claims, extractedClaim{Text: trimmed, Fragment: claim.Fragment, Kind: claim.Kind})
		}
		if len(claims) == a.config.MaxClaims {
			break
		}
	}
	if len(claims) == 0 {
		if statement, ok := questionAsStatement(text); ok && hasEnoughWords(statement) {
			a.logger.Info("extraction found no claim in a yes/no question, checking the question as a statement")
			return []extractedClaim{{Text: statement, Fragment: text}}, 0, usageOf(completion), nil
		}
	}
	return claims, max(answer.Omitted, 0), usageOf(completion), nil
}

// checkClaim runs search, the judge and the rules for one claim.
func (a *Agent) checkClaim(ctx context.Context, r *claimRun, claimID, claimText string) (Claim, error) {
	search, err := a.rag.Search(ctx, claimText, a.config.SearchTopK)
	if err != nil {
		return Claim{}, err
	}
	a.noteSearch(r, search)
	claim := Claim{ID: claimID, Text: claimText, StrengthReasons: []string{}, Sources: []SourceRef{}, Warnings: []Warning{}}
	for _, passage := range search.Results {
		for _, flag := range passage.Flags {
			if flag == flagSuspectedInjection {
				r.injections++
				claim.Warnings = append(claim.Warnings, Warning{Type: WarningOther, Message: warningInjection})
				a.logger.Warn("prompt injection flagged by rag", "requestId", r.request.RequestID, "chunkId", passage.ChunkID)
			}
		}
	}
	if search.CampaignAlert != nil && len(search.CampaignAlert.Matches) > 0 {
		claim.Warnings = append(claim.Warnings, Warning{Type: WarningIncidentMatch, Message: search.CampaignAlert.Message})
	}

	if len(search.Results) == 0 {
		return a.checkClaimWithoutSources(ctx, r, claim, search.ContextXML)
	}

	answer, err := a.judge(ctx, r, claimID, claimText, search.ContextXML)
	if err != nil {
		return Claim{}, err
	}
	if answer.Suspicious {
		r.injections++
		claim.Warnings = append(claim.Warnings, Warning{Type: WarningOther, Message: warningSuspicious})
		a.logger.Warn("model reported instructions inside sources", "requestId", r.request.RequestID, "claimId", claimID)
	}

	passages := map[string]Passage{}
	for _, passage := range search.Results {
		passages[passage.ChunkID] = passage
	}
	sources, dropped := validateCitations(answer.Citations, passages)
	if dropped > 0 {
		a.logger.Info("citations dropped by validation", "requestId", r.request.RequestID, "claimId", claimID, "dropped", dropped)
	}
	proposed := mapVerdict(answer.Verdict)
	ruling := applyFactcheckRatings(claimText, sources, passages, proposed)
	demoted := demoteMismatchedNumbers(claimText, sources, passages)
	ev := assessEvidence(sources, a.now())
	d := decide(claimID, proposed, answer.Missing, sources, ev, dropped, ruling)
	r.limitations = append(r.limitations, d.limitations...)
	if demoted > 0 {
		a.logger.Info("citations with other numbers demoted to context", "requestId", r.request.RequestID, "claimId", claimID, "demoted", demoted)
		r.limitations = append(r.limitations, fmt.Sprintf(limitationNumbersMismatch, claimID))
		if d.verdict == VerdictInsufficientEvidence && proposed != VerdictInsufficientEvidence {
			d.missing = stringPtr(missingNumbersMismatch)
		}
	}
	if d.verdict == VerdictInsufficientEvidence && len(sources) == 0 {
		// The search found passages but no quote survived: show the best ones as context, so an abstention still
		// says what was found (e.g. an announcement without word on whether the event took place).
		sources = fallbackSources(search.Results)
		ev = assessEvidence(sources, a.now())
		if len(sources) > 0 {
			a.logger.Info("context sources attached to abstention", "requestId", r.request.RequestID, "claimId", claimID, "sources", len(sources))
		}
	}

	claim.Verdict = d.verdict
	claim.Justification = strings.TrimSpace(answer.Justification)
	if claim.Justification == "" {
		claim.Justification = missingWeakEvidence
	}
	claim.Sources = sources
	claim.EvidenceStrength = ev.strength
	claim.StrengthReasons = ev.reasons
	if d.consistent && (claim.Verdict == VerdictConfirmed || claim.Verdict == VerdictFalse) {
		claim.StrengthReasons = append(claim.StrengthReasons, reasonConsistentWithRole)
	}
	claim.Missing = d.missing
	if claim.Verdict == VerdictInsufficientEvidence || claim.Verdict == VerdictNotVerifiable {
		r.abstained = true
	}
	return claim, nil
}

// judge asks the model for a verdict; a malformed answer becomes an abstention, any other failure is returned.
func (a *Agent) judge(ctx context.Context, r *claimRun, claimID, claimText, contextXML string) (judgeAnswer, error) {
	materialDate := r.materialDate
	if materialDate == "" {
		materialDate = materialDateUnknown
	}
	system, user := a.prompts.judgeMessages(claimText, contextXML, a.now().Format("2006-01-02"), materialDate)
	var answer judgeAnswer
	completion, err := askJSON(ctx, a.provider, system, user, &answer)
	r.addUsage(usageOf(completion))
	if err != nil {
		if !errors.Is(err, ErrModelAnswer) {
			return judgeAnswer{}, err
		}
		a.logger.Warn("judge returned no JSON", "requestId", r.request.RequestID, "claimId", claimID, "error", err.Error())
		r.limitations = append(r.limitations, fmt.Sprintf(limitationModelFallback, claimID))
		answer = judgeAnswer{Verdict: "brak_dowodow", Justification: missingWeakEvidence}
	}
	return answer, nil
}

// checkClaimWithoutSources handles a search with no passages. The model still sees the claim, because an opinion or a
// prediction is not_verifiable whether or not sources exist; any other verdict is impossible without evidence, so it
// becomes insufficient_evidence and the model's justification is not shown.
func (a *Agent) checkClaimWithoutSources(ctx context.Context, r *claimRun, claim Claim, contextXML string) (Claim, error) {
	if r.factcheckDown {
		// The fact-check service was the only possible basis and it failed: a technical limitation, never the
		// claim "there is no such publication" (CONTRACT.md §4, brief scenario J).
		return Claim{}, errFactcheckUnavailable
	}
	if strings.TrimSpace(contextXML) == "" {
		contextXML = emptyContextXML
	}
	claim.EvidenceStrength = StrengthNone
	claim.StrengthReasons = []string{reasonNoSources}
	r.abstained = true
	answer, err := a.judge(ctx, r, claim.ID, claim.Text, contextXML)
	if err != nil {
		return Claim{}, err
	}
	if answer.Suspicious {
		r.injections++
	}
	if mapVerdict(answer.Verdict) == VerdictNotVerifiable && strings.TrimSpace(answer.Justification) != "" {
		claim.Verdict = VerdictNotVerifiable
		claim.Justification = strings.TrimSpace(answer.Justification)
		return claim, nil
	}
	claim.Verdict = VerdictInsufficientEvidence
	claim.Justification = missingNoSources
	claim.Missing = stringPtr(noSourcesMissing(answer.Missing))
	return claim, nil
}

// maxMissingRunes caps the model's one-sentence note on what would settle a claim.
const maxMissingRunes = 300

func truncateRunes(text string, limit int) string {
	runes := []rune(text)
	if len(runes) <= limit {
		return text
	}
	return strings.TrimSpace(string(runes[:limit-1])) + "…"
}

// noSourcesMissing tells the citizen what would settle the claim. The model only names the kind of source (prompt
// rule on "brakuje"), never a finding, and the fixed note says that an empty search proves nothing either way.
func noSourcesMissing(modelMissing *string) string {
	if modelMissing == nil || strings.TrimSpace(*modelMissing) == "" {
		return missingNoSources + " " + noteNoResultIsNoProof
	}
	return truncateRunes(strings.TrimSpace(*modelMissing), maxMissingRunes) + " " + noteNoResultIsNoProof
}

func (a *Agent) noteSearch(r *claimRun, search SearchResponse) {
	r.passages += len(search.Results)
	if search.CorpusVersion != "" {
		r.corpus = stringPtr(search.CorpusVersion)
	}
	for _, external := range search.ExternalSources {
		switch {
		case external.Status == externalStatusError:
			r.searchErrs++
			if external.Name == externalSourceFactcheck {
				r.factcheckDown = true
				r.limitations = appendUnique(r.limitations, limitationFactcheckUnavailable)
			}
		case external.Name == externalSourceIncidentCatal && external.Status == externalStatusDisabled:
			r.limitations = appendUnique(r.limitations, limitationCatalogEmpty)
		}
	}
	if search.CampaignAlert != nil && len(search.CampaignAlert.Matches) > 0 && r.campaign == nil {
		matches := make([]CampaignMatch, 0, len(search.CampaignAlert.Matches))
		for _, match := range search.CampaignAlert.Matches {
			matches = append(matches, match.CampaignMatch)
		}
		r.campaign = &CampaignAlert{Category: search.CampaignAlert.Category, Message: search.CampaignAlert.Message, Matches: matches}
	}
}

// errFactcheckUnavailable means the fact-check service failed and the corpus had nothing for the claim.
var errFactcheckUnavailable = errors.New("fact-check service unavailable and no corpus results")

func (a *Agent) technicalError(r *run, err error) CheckResult {
	a.logger.Error("verify failed", "requestId", r.request.RequestID, "error", err.Error())
	message := msgTechnicalError
	if errors.Is(err, errFactcheckUnavailable) {
		message = msgFactcheckUnavailable
	}
	result := a.finish(r, StatusTechnicalError, message)
	result.Meta.TimedOut = errors.Is(err, context.DeadlineExceeded)
	return result
}

func (a *Agent) finish(r *run, status, message string) CheckResult {
	result := r.result
	result.Status = status
	if status != StatusOK {
		result.Message = stringPtr(message)
		result.Claims = []Claim{}
		result.Document = nil
	}
	result.CampaignAlert = r.campaign
	result.MaterialMatch = r.material
	result.Limitations = appendUniqueAll(result.Limitations, r.limitations)
	model := a.provider.Name()
	cost := estimateCost(r.inputTokens, r.outputTokens, a.config.LLMPriceInputPerM, a.config.LLMPriceOutputPerM)
	result.Meta = RunMeta{
		Channel:           r.request.Channel,
		ReceivedAt:        r.startedAt.UTC().Format(time.RFC3339),
		LatencyMs:         a.now().Sub(r.startedAt).Milliseconds(),
		Model:             &model,
		EstimatedCostUsd:  &cost,
		CorpusVersion:     r.corpus,
		RetrievedPassages: r.passages,
		SearchErrors:      r.searchErrs,
		InjectionAttempts: r.injections,
		Abstained:         r.abstained,
	}
	return result
}

func appendUnique(list []string, item string) []string {
	for _, existing := range list {
		if existing == item {
			return list
		}
	}
	return append(list, item)
}

func appendUniqueAll(list []string, items []string) []string {
	for _, item := range items {
		list = appendUnique(list, item)
	}
	return list
}
