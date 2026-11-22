package main

import (
	"bytes"
	"context"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"prawdowid/agent"
)

// Closed information loop (brief, scenario H): an unresolved question joins a case with its paraphrases; a case that
// repeats or matches a known campaign is recommended for the moderator, and it counts as forwarded only after the
// moderator's webhook accepted it. The rule is code, never the model's opinion.

const (
	caseStatusLogged      = "logged"
	caseStatusRecommended = "recommended"
	caseStatusForwarded   = "forwarded"

	reportsMatchPath = "/reports/match"
	// caseTrackTimeout bounds matching, storing and notifying for one check, so the loop never delays an answer much.
	caseTrackTimeout = 4 * time.Second
	// maxReportsBodyBytes caps the rag answer, which is a few fields.
	maxReportsBodyBytes = 1 << 14
	// maxWebhookClaimRunes keeps the notification well under chat limits (Discord: 2000 characters).
	maxWebhookClaimRunes = 500
	// caseListLimit is how many cases the analyst list returns, most reported first.
	caseListLimit = 200
)

const createCasesSQL = `
CREATE TABLE IF NOT EXISTS moderation_cases (
    case_id         uuid PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    claim_masked    text NOT NULL,
    reports         integer NOT NULL,
    campaign        boolean NOT NULL,
    status          text NOT NULL,
    forwarded_at    timestamptz,
    last_request_id uuid NOT NULL
);
CREATE INDEX IF NOT EXISTS moderation_cases_updated_at_idx ON moderation_cases (updated_at);
ALTER TABLE moderation_cases ENABLE ROW LEVEL SECURITY;
`

// CaseNotice is what the citizen sees about the case of one unresolved claim (CONTRACT.md section 1a).
type CaseNotice struct {
	ClaimID string `json:"claimId"`
	CaseID  string `json:"caseId"`
	Reports int    `json:"reports"`
	Status  string `json:"status"`
}

// CaseRecord is one case on the analyst list (GET /api/admin/cases).
type CaseRecord struct {
	CaseID      string     `json:"caseId"`
	Claim       string     `json:"claim"`
	Reports     int        `json:"reports"`
	Campaign    bool       `json:"campaign"`
	Status      string     `json:"status"`
	CreatedAt   time.Time  `json:"createdAt"`
	UpdatedAt   time.Time  `json:"updatedAt"`
	ForwardedAt *time.Time `json:"forwardedAt"`
}

// escalationStatus is the deterministic rule: repeated or campaign-like unresolved questions are recommended.
func escalationStatus(reports, repeatThreshold int, campaign bool) string {
	if campaign || reports >= repeatThreshold {
		return caseStatusRecommended
	}
	return caseStatusLogged
}

type caseStore struct {
	pool *pgxpool.Pool
}

// record adds one report to the case and returns its report count, campaign flag and current status.
func (s *caseStore) record(ctx context.Context, caseID, claim string, campaign bool, requestID string) (int, bool, string, error) {
	var reports int
	var anyCampaign bool
	var status string
	err := s.pool.QueryRow(ctx,
		`INSERT INTO moderation_cases (case_id, claim_masked, reports, campaign, status, last_request_id)
		 VALUES ($1, $2, 1, $3, $4, $5)
		 ON CONFLICT (case_id) DO UPDATE SET
		     reports = moderation_cases.reports + 1,
		     campaign = moderation_cases.campaign OR EXCLUDED.campaign,
		     updated_at = now(),
		     last_request_id = EXCLUDED.last_request_id
		 RETURNING reports, campaign, status`,
		caseID, claim, campaign, caseStatusLogged, requestID).Scan(&reports, &anyCampaign, &status)
	if err != nil {
		return 0, false, "", fmt.Errorf("record case: %w", err)
	}
	return reports, anyCampaign, status, nil
}

// setStatus moves a case forward (logged -> recommended -> forwarded); it never moves it back.
func (s *caseStore) setStatus(ctx context.Context, caseID, status string) error {
	query := `UPDATE moderation_cases SET status = $2 WHERE case_id = $1 AND status = 'logged'`
	if status == caseStatusForwarded {
		query = `UPDATE moderation_cases SET status = $2, forwarded_at = now() WHERE case_id = $1 AND status <> 'forwarded'`
	}
	if _, err := s.pool.Exec(ctx, query, caseID, status); err != nil {
		return fmt.Errorf("update case status: %w", err)
	}
	return nil
}

func (s *caseStore) list(ctx context.Context) ([]CaseRecord, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT case_id::text, claim_masked, reports, campaign, status, created_at, updated_at, forwarded_at
		 FROM moderation_cases ORDER BY reports DESC, updated_at DESC LIMIT $1`, caseListLimit)
	if err != nil {
		return nil, fmt.Errorf("list cases: %w", err)
	}
	records, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (CaseRecord, error) {
		var record CaseRecord
		err := row.Scan(&record.CaseID, &record.Claim, &record.Reports, &record.Campaign, &record.Status,
			&record.CreatedAt, &record.UpdatedAt, &record.ForwardedAt)
		return record, err
	})
	if err != nil {
		return nil, fmt.Errorf("read cases: %w", err)
	}
	return records, nil
}

// purgeOlderThan applies the same retention as check runs to cases nobody reported since cutoff.
func (s *caseStore) purgeOlderThan(ctx context.Context, cutoff time.Time) (int64, error) {
	purgeCtx, cancel := context.WithTimeout(ctx, storeTimeout)
	defer cancel()
	tag, err := s.pool.Exec(purgeCtx, `DELETE FROM moderation_cases WHERE updated_at < $1`, cutoff)
	if err != nil {
		return 0, fmt.Errorf("purge cases: %w", err)
	}
	return tag.RowsAffected(), nil
}

type caseRepository interface {
	record(ctx context.Context, caseID, claim string, campaign bool, requestID string) (int, bool, string, error)
	setStatus(ctx context.Context, caseID, status string) error
	list(ctx context.Context) ([]CaseRecord, error)
}

// matchReport asks rag which case an unresolved claim belongs to (CONTRACT.md section 3, POST /reports/match).
type matchReport func(ctx context.Context, claim string) (string, error)

func ragReportMatcher(ragBaseURL string, client *http.Client) matchReport {
	endpoint := strings.TrimRight(ragBaseURL, "/") + reportsMatchPath
	return func(ctx context.Context, claim string) (string, error) {
		body, err := json.Marshal(map[string]string{"claim": claim})
		if err != nil {
			return "", fmt.Errorf("encode report: %w", err)
		}
		request, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
		if err != nil {
			return "", fmt.Errorf("build report request: %w", err)
		}
		request.Header.Set("Content-Type", "application/json")
		response, err := client.Do(request)
		if err != nil {
			return "", fmt.Errorf("match report: %w", err)
		}
		defer response.Body.Close()
		if response.StatusCode != http.StatusOK {
			return "", fmt.Errorf("match report: rag answered %d", response.StatusCode)
		}
		var answer struct {
			CaseID string `json:"caseId"`
		}
		if err := json.NewDecoder(io.LimitReader(response.Body, maxReportsBodyBytes)).Decode(&answer); err != nil {
			return "", fmt.Errorf("decode report match: %w", err)
		}
		if !requestIDPattern.MatchString(answer.CaseID) {
			return "", errors.New("match report: rag returned no case id")
		}
		return answer.CaseID, nil
	}
}

// notifyModerator delivers a recommended case; nil means the moderator really received it.
type notifyModerator func(ctx context.Context, caseID, claim string, reports int, campaign bool) error

// webhookNotifier posts a short text to the webhook the administrator configured (Discord-compatible "content").
func webhookNotifier(webhookURL string, client *http.Client) notifyModerator {
	return func(ctx context.Context, caseID, claim string, reports int, campaign bool) error {
		reason := fmt.Sprintf("pytano %d razy bez źródeł", reports)
		if campaign {
			reason += ", podobne do znanej kampanii dezinformacyjnej"
		}
		content := fmt.Sprintf("Prawdowid: sprawa %s do sprawdzenia (%s).\nTwierdzenie: %s", caseID, reason,
			truncateRunes(claim, maxWebhookClaimRunes))
		body, err := json.Marshal(map[string]string{"content": content})
		if err != nil {
			return fmt.Errorf("encode notification: %w", err)
		}
		request, err := http.NewRequestWithContext(ctx, http.MethodPost, webhookURL, bytes.NewReader(body))
		if err != nil {
			return fmt.Errorf("build notification: %w", err)
		}
		request.Header.Set("Content-Type", "application/json")
		response, err := client.Do(request)
		if err != nil {
			return fmt.Errorf("send notification: %w", err)
		}
		defer response.Body.Close()
		if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
			return fmt.Errorf("send notification: webhook answered %d", response.StatusCode)
		}
		return nil
	}
}

func truncateRunes(text string, limit int) string {
	runes := []rune(text)
	if len(runes) <= limit {
		return text
	}
	return string(runes[:limit-1]) + "…"
}

func validWebhookURL(raw string) bool {
	parsed, err := url.Parse(raw)
	return err == nil && parsed.Scheme == "https" && parsed.Host != ""
}

// caseTracker runs the loop after a check. Any failure is logged and leaves the answer without case notices:
// the loop must never break the check itself (AGENTS.md section 6).
type caseTracker struct {
	logger          *slog.Logger
	repository      caseRepository
	match           matchReport
	notify          notifyModerator // nil when no webhook is configured: cases can then only be recommended
	repeatThreshold int
}

func (t *caseTracker) track(ctx context.Context, result agent.CheckResult) []CaseNotice {
	notices := []CaseNotice{}
	if t == nil || result.Status != agent.StatusOK {
		return notices
	}
	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), caseTrackTimeout)
	defer cancel()
	campaign := result.CampaignAlert != nil && len(result.CampaignAlert.Matches) > 0
	for _, claim := range result.Claims {
		if claim.Verdict != agent.VerdictInsufficientEvidence {
			continue
		}
		notice, err := t.trackClaim(ctx, result.RequestID, claim, campaign)
		if err != nil {
			t.logger.Warn("case tracking skipped", "requestId", result.RequestID, "claimId", claim.ID, "error", err)
			continue
		}
		notices = append(notices, notice)
	}
	return notices
}

func (t *caseTracker) trackClaim(ctx context.Context, requestID string, claim agent.Claim, campaign bool) (CaseNotice, error) {
	masked := maskPersonalData(claim.Text)
	caseID, err := t.match(ctx, masked)
	if err != nil {
		return CaseNotice{}, err
	}
	reports, anyCampaign, status, err := t.repository.record(ctx, caseID, masked, campaign, requestID)
	if err != nil {
		return CaseNotice{}, err
	}
	notice := CaseNotice{ClaimID: claim.ID, CaseID: caseID, Reports: reports, Status: status}
	if status == caseStatusForwarded || escalationStatus(reports, t.repeatThreshold, anyCampaign) != caseStatusRecommended {
		return notice, nil
	}
	if status == caseStatusLogged {
		if err := t.repository.setStatus(ctx, caseID, caseStatusRecommended); err != nil {
			return notice, err
		}
		notice.Status = caseStatusRecommended
		t.logger.Info("case recommended for the moderator", "caseId", caseID, "reports", reports, "campaign", anyCampaign)
	}
	if t.notify == nil {
		return notice, nil
	}
	if err := t.notify(ctx, caseID, masked, reports, anyCampaign); err != nil {
		t.logger.Warn("moderator notification failed, case stays recommended", "caseId", caseID, "error", err)
		return notice, nil
	}
	if err := t.repository.setStatus(ctx, caseID, caseStatusForwarded); err != nil {
		t.logger.Error("case forwarded but status not saved", "caseId", caseID, "error", err)
		return notice, nil
	}
	notice.Status = caseStatusForwarded
	t.logger.Info("case forwarded to the moderator", "caseId", caseID)
	return notice, nil
}

// caseRequestTimeout bounds each rag or webhook call made by the loop.
const caseRequestTimeout = 3 * time.Second

func newCaseTracker(logger *slog.Logger, config Config, repository caseRepository) *caseTracker {
	client := &http.Client{Timeout: caseRequestTimeout}
	tracker := &caseTracker{
		logger:          logger,
		repository:      repository,
		match:           ragReportMatcher(config.RagURL, client),
		repeatThreshold: config.ModeratorRepeatThreshold,
	}
	if config.ModeratorWebhookURL != "" {
		tracker.notify = webhookNotifier(config.ModeratorWebhookURL, client)
	}
	logger.Info("moderator loop ready", "repeatThreshold", config.ModeratorRepeatThreshold,
		"webhook", tracker.notify != nil, "adminList", config.ModeratorToken != "")
	return tracker
}

// adminCasesHandler lists cases for the analyst; without a configured token the list is closed.
func adminCasesHandler(logger *slog.Logger, repository caseRepository, token string) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		if token == "" {
			writeJSON(logger, writer, http.StatusForbidden, map[string]string{"error": "moderator access is not configured"})
			return
		}
		if !constantTimeEqual(request.Header.Get("X-Admin-Token"), token) {
			writeJSON(logger, writer, http.StatusUnauthorized, map[string]string{"error": "invalid token"})
			return
		}
		records, err := repository.list(request.Context())
		if err != nil {
			logger.Error("list cases failed", "error", err)
			writeJSON(logger, writer, http.StatusServiceUnavailable, map[string]string{"error": "cases unavailable"})
			return
		}
		writeJSON(logger, writer, http.StatusOK, map[string]any{"cases": records})
	}
}

func constantTimeEqual(given, expected string) bool {
	return subtle.ConstantTimeCompare([]byte(given), []byte(expected)) == 1
}
