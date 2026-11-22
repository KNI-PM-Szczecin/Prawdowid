package agent

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Errors from rag/, mapped to statuses by Verify.
var (
	ErrRagUnavailable = errors.New("rag unavailable") // index_unavailable, transport, timeout -> technical_error
	ErrFetchRejected  = errors.New("fetch rejected")  // 422 from POST /fetch -> needs_clarification or out_of_scope
)

// Reasons rag gives for a rejected page (CONTRACT.md §3, POST /fetch); the agent picks the citizen's message by them.
const (
	FetchCodeUnsupportedHost = "unsupported_host"
	FetchCodeNotHTML         = "not_html"
	FetchCodeNoText          = "no_text"
	FetchCodeBotWall         = "bot_wall"
)

// fetchRejection carries rag's reason code; errors.Is(err, ErrFetchRejected) still holds.
type fetchRejection struct {
	code   string
	detail string
}

func (r *fetchRejection) Error() string { return "fetch rejected (" + r.code + "): " + r.detail }

func (r *fetchRejection) Is(target error) bool { return target == ErrFetchRejected }

// fetchRejectionCode returns rag's reason code for a rejected fetch, or "" for any other error.
func fetchRejectionCode(err error) string {
	var rejection *fetchRejection
	if errors.As(err, &rejection) {
		return rejection.code
	}
	return ""
}

type fetchErrorBody struct {
	Detail json.RawMessage `json:"detail"`
}

type fetchErrorDetail struct {
	Message string `json:"message"`
	Code    string `json:"code"`
}

// parseFetchRejection reads rag's 422 body: `{"detail": {"message", "code"}}`, or a plain string from an older rag.
func parseFetchRejection(body []byte) *fetchRejection {
	var envelope fetchErrorBody
	if err := json.Unmarshal(body, &envelope); err == nil && len(envelope.Detail) > 0 {
		var detail fetchErrorDetail
		if err := json.Unmarshal(envelope.Detail, &detail); err == nil && detail.Code != "" {
			return &fetchRejection{code: detail.Code, detail: detail.Message}
		}
		var message string
		if err := json.Unmarshal(envelope.Detail, &message); err == nil {
			return &fetchRejection{detail: message}
		}
	}
	return &fetchRejection{detail: truncate(string(body), maxErrorBodyLen)}
}

const (
	flagSuspectedInjection      = "suspected_injection"
	externalSourceFactcheck     = "google_factcheck"
	externalSourceIncidentCatal = "incident_catalog"
	externalStatusError         = "error"
	externalStatusDisabled      = "disabled"
	// What rag/ renders for an empty result list; used when an older rag sends no contextXml at all.
	emptyContextXML = "<dostepne_zrodla>\n\n</dostepne_zrodla>"
)

// Passage is one evidence fragment from rag/ (CONTRACT.md §3).
type Passage struct {
	DocumentID  string   `json:"documentId"`
	Title       string   `json:"title"`
	Publisher   string   `json:"publisher"`
	PublishedAt *string  `json:"publishedAt"`
	FetchedAt   string   `json:"fetchedAt"`
	URL         string   `json:"url"`
	License     *string  `json:"license"`
	SourceType  string   `json:"sourceType"`
	Passage     string   `json:"passage"`
	Score       float64  `json:"score"`
	Flags       []string `json:"flags"`
	ChunkID     string   `json:"chunkId"`
	Tier        int      `json:"tier"`
	Reliability string   `json:"reliability"`
}

// ExternalSourceStatus reports a live source (Google Fact Check) or the incident catalog.
type ExternalSourceStatus struct {
	Name    string `json:"name"`
	Status  string `json:"status"`
	Results int    `json:"results"`
}

type ragCampaignMatch struct {
	CampaignMatch
	Score float64 `json:"score"`
}

type ragCampaignAlert struct {
	Category string             `json:"category"`
	Message  string             `json:"message"`
	Matches  []ragCampaignMatch `json:"matches"`
}

// SearchResponse is rag's answer to POST /search.
type SearchResponse struct {
	Results         []Passage              `json:"results"`
	CorpusVersion   string                 `json:"corpusVersion"`
	ContextXML      string                 `json:"contextXml"`
	ExternalSources []ExternalSourceStatus `json:"externalSources"`
	CampaignAlert   *ragCampaignAlert      `json:"campaignAlert"`
	ExpandedQueries *ExpandedQueries       `json:"expandedQueries"`
}

// ExpandedQueries are rag's rewordings of the claim (CONTRACT.md §2); the agent reuses them to search again.
type ExpandedQueries struct {
	Negative string `json:"negative"`
	Keywords string `json:"keywords"`
}

// FetchResponse is rag's answer to POST /fetch.
type FetchResponse struct {
	URL         string  `json:"url"`
	Title       string  `json:"title"`
	Text        string  `json:"text"`
	Truncated   bool    `json:"truncated"`
	PublishedAt *string `json:"publishedAt"`
}

type matchRequest struct {
	URL         string  `json:"url"`
	Title       *string `json:"title"`
	PublishedAt *string `json:"publishedAt"`
}

// MaterialMatchResponse is rag's answer to POST /match.
type MaterialMatchResponse struct {
	Matches []MaterialMatchItem `json:"matches"`
}

// RagClient calls rag/ over HTTP; it is the only place that knows rag's endpoints.
type RagClient struct {
	baseURL string
	client  *http.Client
}

// NewRagClient builds a client with the per-call timeout from CONTRACT.md §2 (8 s).
func NewRagClient(baseURL string, timeout time.Duration) *RagClient {
	return &RagClient{baseURL: strings.TrimRight(baseURL, "/"), client: &http.Client{Timeout: timeout}}
}

type searchRequest struct {
	Query string `json:"query"`
	TopK  int    `json:"topK"`
}

type fetchRequest struct {
	URL string `json:"url"`
}

// Search returns evidence for one claim; an empty Results list means no relevant evidence, not an error.
func (r *RagClient) Search(ctx context.Context, query string, topK int) (SearchResponse, error) {
	var response SearchResponse
	status, body, err := r.post(ctx, "/search", searchRequest{Query: query, TopK: topK})
	if err != nil {
		return response, err
	}
	if status != http.StatusOK {
		return response, fmt.Errorf("%w: search HTTP %d: %s", ErrRagUnavailable, status, truncate(string(body), maxErrorBodyLen))
	}
	if err := json.Unmarshal(body, &response); err != nil {
		return response, fmt.Errorf("%w: decode search response: %w", ErrRagUnavailable, err)
	}
	return response, nil
}

// Fetch returns the text of a public page; 422 means the page cannot be read (anti-bot wall, no HTML text).
func (r *RagClient) Fetch(ctx context.Context, url string) (FetchResponse, error) {
	var response FetchResponse
	status, body, err := r.post(ctx, "/fetch", fetchRequest{URL: url})
	if err != nil {
		return response, err
	}
	switch status {
	case http.StatusOK:
		if err := json.Unmarshal(body, &response); err != nil {
			return response, fmt.Errorf("%w: decode fetch response: %w", ErrRagUnavailable, err)
		}
		return response, nil
	case http.StatusUnprocessableEntity:
		return response, parseFetchRejection(body)
	default:
		return response, fmt.Errorf("%w: fetch HTTP %d: %s", ErrRagUnavailable, status, truncate(string(body), maxErrorBodyLen))
	}
}

// MatchMaterial asks whether the fetched page itself is a known document or incident link (brief scenario I).
func (r *RagClient) MatchMaterial(ctx context.Context, url string, title, publishedAt *string) (MaterialMatchResponse, error) {
	var response MaterialMatchResponse
	status, body, err := r.post(ctx, "/match", matchRequest{URL: url, Title: title, PublishedAt: publishedAt})
	if err != nil {
		return response, err
	}
	if status != http.StatusOK {
		return response, fmt.Errorf("%w: match HTTP %d: %s", ErrRagUnavailable, status, truncate(string(body), maxErrorBodyLen))
	}
	if err := json.Unmarshal(body, &response); err != nil {
		return response, fmt.Errorf("%w: decode match response: %w", ErrRagUnavailable, err)
	}
	return response, nil
}

func (r *RagClient) post(ctx context.Context, path string, payload any) (int, []byte, error) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return 0, nil, fmt.Errorf("encode %s request: %w", path, err)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, r.baseURL+path, bytes.NewReader(encoded))
	if err != nil {
		return 0, nil, fmt.Errorf("build %s request: %w", path, err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := r.client.Do(request)
	if err != nil {
		return 0, nil, fmt.Errorf("%w: %w", ErrRagUnavailable, err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return 0, nil, fmt.Errorf("%w: read %s response: %w", ErrRagUnavailable, path, err)
	}
	return response.StatusCode, body, nil
}
