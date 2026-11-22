// Package agent verifies claims against sources returned by rag/ and produces the CheckResult from CONTRACT.md.
// The model proposes a verdict and quotes; the rules in rules.go decide what is allowed to reach the user.
package agent

// Verdicts and statuses from CONTRACT.md.
const (
	VerdictConfirmed            = "confirmed"
	VerdictFalse                = "false"
	VerdictMisleading           = "misleading"
	VerdictInsufficientEvidence = "insufficient_evidence"
	VerdictNotVerifiable        = "not_verifiable"

	StatusOK                 = "ok"
	StatusTechnicalError     = "technical_error"
	StatusNeedsClarification = "needs_clarification"
	StatusOutOfScope         = "out_of_scope"

	StrengthStrong   = "strong"
	StrengthModerate = "moderate"
	StrengthWeak     = "weak"
	StrengthNone     = "none"

	RoleSupports = "supports"
	RoleRefutes  = "refutes"
	RoleContext  = "context"

	SourceTypeOfficial  = "official"
	SourceTypeSecondary = "secondary"
	SourceTypeFactcheck = "factcheck"

	WarningSourceStatus     = "source_status"
	WarningIncidentMatch    = "incident_match"
	WarningArchivalMaterial = "archival_material"
	WarningOther            = "other"

	InputTypeText = "text"
	InputTypeURL  = "url"
)

// VerifyRequest is what every channel passes to Verify (CONTRACT.md §2).
type VerifyRequest struct {
	RequestID string `json:"requestId"`
	Channel   string `json:"channel"`
	Input     string `json:"input"`
	InputType string `json:"inputType"`
}

// SourceRef is one cited source with the verbatim quote that supports, refutes or contextualises the claim.
type SourceRef struct {
	ID          string  `json:"id"`
	Title       string  `json:"title"`
	Publisher   string  `json:"publisher"`
	PublishedAt *string `json:"publishedAt"`
	FetchedAt   string  `json:"fetchedAt"`
	URL         string  `json:"url"`
	License     *string `json:"license"`
	SourceType  string  `json:"sourceType"`
	Role        string  `json:"role"`
	Quote       string  `json:"quote"`
}

// Warning is a neutral notice shown beside a claim; it never changes the verdict.
type Warning struct {
	Type    string `json:"type"`
	Message string `json:"message"`
}

// Span locates a claim in Document.Text as code-point offsets, end exclusive (CONTRACT.md §1a).
type Span struct {
	Start int `json:"start"`
	End   int `json:"end"`
}

// Claim is one verified statement extracted from the submission.
type Claim struct {
	ID               string      `json:"id"`
	Text             string      `json:"text"`
	Verdict          string      `json:"verdict"`
	Justification    string      `json:"justification"`
	EvidenceStrength string      `json:"evidenceStrength"`
	StrengthReasons  []string    `json:"strengthReasons"`
	Sources          []SourceRef `json:"sources"`
	Warnings         []Warning   `json:"warnings"`
	Missing          *string     `json:"missing"`
	Span             *Span       `json:"span"`
}

// RunMeta goes to logs and the developer panel; the front may ignore it.
type RunMeta struct {
	Channel           string   `json:"channel"`
	ReceivedAt        string   `json:"receivedAt"`
	LatencyMs         int64    `json:"latencyMs"`
	Model             *string  `json:"model"`
	EstimatedCostUsd  *float64 `json:"estimatedCostUsd"`
	CorpusVersion     *string  `json:"corpusVersion"`
	RetrievedPassages int      `json:"retrievedPassages"`
	SearchErrors      int      `json:"searchErrors"`
	InjectionAttempts int      `json:"injectionAttempts"`
	Abstained         bool     `json:"abstained"`
	TimedOut          bool     `json:"timedOut"`
}

// Document is the checked text as the front shows it (CONTRACT.md §1a, optional).
type Document struct {
	Title       *string `json:"title"`
	Text        string  `json:"text"`
	URL         *string `json:"url"`
	Publisher   *string `json:"publisher"`
	PublishedAt *string `json:"publishedAt"`
	FetchedAt   *string `json:"fetchedAt"`
}

// Kinds and bases of a material match (CONTRACT.md §1a, brief scenario I).
const (
	MaterialKindCorpusDocument = "corpus_document"
	MaterialKindIncident       = "incident"
	MaterialBasisURL           = "url"
	MaterialBasisTitle         = "title"
	MaterialBasisDate          = "date"
)

// MaterialMatchItem is one known material the submitted page was recognised as, with the explicit basis.
type MaterialMatchItem struct {
	Kind        string   `json:"kind"`
	Basis       []string `json:"basis"`
	Title       string   `json:"title"`
	Publisher   string   `json:"publisher"`
	URL         string   `json:"url"`
	PublishedAt *string  `json:"publishedAt"`
	SourceType  *string  `json:"sourceType"`
	IncidentID  *string  `json:"incidentId"`
	Source      *string  `json:"source"`
}

// MaterialMatch says whether the submitted page itself is a known material; context, never a verdict.
type MaterialMatch struct {
	Message string              `json:"message"`
	Matches []MaterialMatchItem `json:"matches"`
}

// CampaignMatch is one known disinformation case similar to the submission; context only.
type CampaignMatch struct {
	IncidentID  string  `json:"incidentId"`
	Source      string  `json:"source"`
	Title       string  `json:"title"`
	Summary     string  `json:"summary"`
	URL         string  `json:"url"`
	PublishedAt *string `json:"publishedAt"`
}

// CampaignAlert is rag's campaign alert without scores (CONTRACT.md §1a); never a basis for a verdict.
type CampaignAlert struct {
	Category string          `json:"category"`
	Message  string          `json:"message"`
	Matches  []CampaignMatch `json:"matches"`
}

// CheckResult is the full answer for one submission (CONTRACT.md §1).
type CheckResult struct {
	RequestID     string         `json:"requestId"`
	Status        string         `json:"status"`
	Message       *string        `json:"message"`
	Document      *Document      `json:"document"`
	CampaignAlert *CampaignAlert `json:"campaignAlert"`
	MaterialMatch *MaterialMatch `json:"materialMatch"`
	Claims        []Claim        `json:"claims"`
	Limitations   []string       `json:"limitations"`
	Meta          RunMeta        `json:"meta"`
}
