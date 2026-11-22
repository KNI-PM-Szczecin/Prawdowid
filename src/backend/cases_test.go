package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"prawdowid/agent"
)

const testCaseID = "11111111-2222-4333-8444-555555555555"

type memoryCases struct {
	mu       sync.Mutex
	reports  map[string]int
	campaign map[string]bool
	status   map[string]string
	claims   map[string]string
	failList bool
}

func newMemoryCases() *memoryCases {
	return &memoryCases{reports: map[string]int{}, campaign: map[string]bool{}, status: map[string]string{}, claims: map[string]string{}}
}

func (m *memoryCases) record(_ context.Context, caseID, claim string, campaign bool, _ string) (int, bool, string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.reports[caseID]++
	m.campaign[caseID] = m.campaign[caseID] || campaign
	if m.status[caseID] == "" {
		m.status[caseID] = caseStatusLogged
	}
	m.claims[caseID] = claim
	return m.reports[caseID], m.campaign[caseID], m.status[caseID], nil
}

func (m *memoryCases) setStatus(_ context.Context, caseID, status string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if status == caseStatusForwarded || m.status[caseID] == caseStatusLogged {
		m.status[caseID] = status
	}
	return nil
}

func (m *memoryCases) list(context.Context) ([]CaseRecord, error) {
	if m.failList {
		return nil, errors.New("database down")
	}
	records := []CaseRecord{}
	for id, reports := range m.reports {
		records = append(records, CaseRecord{CaseID: id, Claim: m.claims[id], Reports: reports, Status: m.status[id]})
	}
	return records, nil
}

type countingNotifier struct {
	calls int
	err   error
}

func (n *countingNotifier) notify(context.Context, string, string, int, bool) error {
	n.calls++
	return n.err
}

func sameCase(context.Context, string) (string, error) { return testCaseID, nil }

func unresolvedResult(claims ...agent.Claim) agent.CheckResult {
	return agent.CheckResult{RequestID: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", Status: agent.StatusOK, Claims: claims}
}

func unresolvedClaim(verdict, text string) agent.Claim {
	return agent.Claim{ID: "c1", Text: text, Verdict: verdict}
}

func newTestTracker(repository caseRepository, notifier *countingNotifier) *caseTracker {
	tracker := &caseTracker{logger: slog.New(slog.NewTextHandler(io.Discard, nil)), repository: repository,
		match: sameCase, repeatThreshold: 3}
	if notifier != nil {
		tracker.notify = notifier.notify
	}
	return tracker
}

func TestResolvedClaimsAndNonOkResultsOpenNoCase(t *testing.T) {
	tracker := newTestTracker(newMemoryCases(), nil)
	for _, verdict := range []string{agent.VerdictConfirmed, agent.VerdictFalse, agent.VerdictMisleading, agent.VerdictNotVerifiable} {
		if notices := tracker.track(context.Background(), unresolvedResult(unresolvedClaim(verdict, "Sejm ma 460 posłów."))); len(notices) != 0 {
			t.Errorf("%s: expected no case, got %+v", verdict, notices)
		}
	}
	failed := unresolvedResult(unresolvedClaim(agent.VerdictInsufficientEvidence, "Pcim zakazał diesli."))
	failed.Status = agent.StatusTechnicalError
	if notices := tracker.track(context.Background(), failed); len(notices) != 0 {
		t.Fatalf("technical error must not open a case, got %+v", notices)
	}
}

// Scenario H: repeated unresolved questions make one case; without a webhook it is only ever recommended.
func TestRepeatsAreRecommendedButNeverForwardedWithoutWebhook(t *testing.T) {
	repository := newMemoryCases()
	tracker := newTestTracker(repository, nil)
	statuses := []string{}
	for range 4 {
		notices := tracker.track(context.Background(), unresolvedResult(unresolvedClaim(agent.VerdictInsufficientEvidence, "Pcim zakazał diesli.")))
		statuses = append(statuses, notices[0].Status)
	}
	want := []string{caseStatusLogged, caseStatusLogged, caseStatusRecommended, caseStatusRecommended}
	if strings.Join(statuses, ",") != strings.Join(want, ",") || repository.reports[testCaseID] != 4 {
		t.Fatalf("statuses %v reports %d", statuses, repository.reports[testCaseID])
	}
}

func TestWebhookSuccessForwardsOnceThenStaysForwarded(t *testing.T) {
	notifier := &countingNotifier{}
	tracker := newTestTracker(newMemoryCases(), notifier)
	var last []CaseNotice
	for range 5 {
		last = tracker.track(context.Background(), unresolvedResult(unresolvedClaim(agent.VerdictInsufficientEvidence, "Pcim zakazał diesli.")))
	}
	if last[0].Status != caseStatusForwarded || notifier.calls != 1 {
		t.Fatalf("expected one notification and forwarded, got %s after %d calls", last[0].Status, notifier.calls)
	}
}

// A failed webhook must not be reported as forwarding; the next report tries again.
func TestWebhookFailureStaysRecommendedAndRetries(t *testing.T) {
	notifier := &countingNotifier{err: errors.New("webhook 500")}
	tracker := newTestTracker(newMemoryCases(), notifier)
	var last []CaseNotice
	for range 4 {
		last = tracker.track(context.Background(), unresolvedResult(unresolvedClaim(agent.VerdictInsufficientEvidence, "Pcim zakazał diesli.")))
	}
	if last[0].Status != caseStatusRecommended || notifier.calls != 2 {
		t.Fatalf("expected recommended with two attempts, got %s after %d", last[0].Status, notifier.calls)
	}
}

func TestCampaignMatchIsRecommendedOnFirstReport(t *testing.T) {
	result := unresolvedResult(unresolvedClaim(agent.VerdictInsufficientEvidence, "NATO i MI6 zaatakowały Ust-Ługę."))
	result.CampaignAlert = &agent.CampaignAlert{Matches: []agent.CampaignMatch{{IncidentID: "x"}}}
	notices := newTestTracker(newMemoryCases(), nil).track(context.Background(), result)
	if len(notices) != 1 || notices[0].Status != caseStatusRecommended || notices[0].Reports != 1 {
		t.Fatalf("expected recommended at the first report, got %+v", notices)
	}
}

func TestRagFailureLeavesAnswerWithoutCases(t *testing.T) {
	tracker := newTestTracker(newMemoryCases(), nil)
	tracker.match = func(context.Context, string) (string, error) { return "", errors.New("rag down") }
	if notices := tracker.track(context.Background(), unresolvedResult(unresolvedClaim(agent.VerdictInsufficientEvidence, "Pcim zakazał diesli."))); len(notices) != 0 {
		t.Fatalf("expected no notices, got %+v", notices)
	}
}

func TestCaseClaimIsMaskedBeforeMatchingAndStorage(t *testing.T) {
	repository := newMemoryCases()
	tracker := newTestTracker(repository, nil)
	var matched string
	tracker.match = func(_ context.Context, claim string) (string, error) { matched = claim; return testCaseID, nil }
	tracker.track(context.Background(), unresolvedResult(unresolvedClaim(agent.VerdictInsufficientEvidence, "Jan dzwonił z 600 700 800 w sprawie diesli.")))
	if strings.Contains(matched, "600") || strings.Contains(repository.claims[testCaseID], "600") {
		t.Fatalf("phone number leaked: match %q stored %q", matched, repository.claims[testCaseID])
	}
}

func TestEscalationRule(t *testing.T) {
	cases := []struct {
		reports  int
		campaign bool
		want     string
	}{{1, false, caseStatusLogged}, {2, false, caseStatusLogged}, {3, false, caseStatusRecommended}, {1, true, caseStatusRecommended}}
	for _, item := range cases {
		if got := escalationStatus(item.reports, 3, item.campaign); got != item.want {
			t.Errorf("reports %d campaign %v: got %s want %s", item.reports, item.campaign, got, item.want)
		}
	}
}

func TestWebhookNotifierSendsMaskedContentAndChecksStatus(t *testing.T) {
	var received map[string]string
	status := http.StatusNoContent
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		_ = json.NewDecoder(request.Body).Decode(&received)
		writer.WriteHeader(status)
	}))
	defer server.Close()
	notify := webhookNotifier(server.URL, server.Client())
	if err := notify(context.Background(), testCaseID, "Pcim zakazał diesli.", 3, true); err != nil {
		t.Fatalf("expected success: %v", err)
	}
	if !strings.Contains(received["content"], testCaseID) || !strings.Contains(received["content"], "kampanii") {
		t.Fatalf("unexpected content %q", received["content"])
	}
	status = http.StatusInternalServerError
	if err := notify(context.Background(), testCaseID, "Pcim zakazał diesli.", 3, false); err == nil {
		t.Fatal("a 500 from the webhook must be an error")
	}
}

func TestRagReportMatcherRejectsBadAnswers(t *testing.T) {
	answers := map[string]int{`{"caseId":"` + testCaseID + `"}`: http.StatusOK, `{"caseId":"nie-uuid"}`: http.StatusOK, `{}`: http.StatusServiceUnavailable}
	for body, code := range answers {
		server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			if request.URL.Path != reportsMatchPath {
				t.Errorf("unexpected path %s", request.URL.Path)
			}
			writer.WriteHeader(code)
			_, _ = writer.Write([]byte(body))
		}))
		caseID, err := ragReportMatcher(server.URL, server.Client())(context.Background(), "Pcim zakazał diesli.")
		server.Close()
		valid := code == http.StatusOK && strings.Contains(body, testCaseID)
		if valid && (err != nil || caseID != testCaseID) || !valid && err == nil {
			t.Errorf("body %s code %d: got %q %v", body, code, caseID, err)
		}
	}
}

func TestAdminCasesNeedsConfiguredToken(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	repository := newMemoryCases()
	call := func(handler http.HandlerFunc, token string) int {
		request := httptest.NewRequest(http.MethodGet, "/api/admin/cases", nil)
		if token != "" {
			request.Header.Set("X-Admin-Token", token)
		}
		recorder := httptest.NewRecorder()
		handler(recorder, request)
		return recorder.Code
	}
	if code := call(adminCasesHandler(logger, repository, ""), "cokolwiek"); code != http.StatusForbidden {
		t.Errorf("unconfigured: got %d", code)
	}
	open := adminCasesHandler(logger, repository, "sekret")
	if code := call(open, ""); code != http.StatusUnauthorized {
		t.Errorf("missing token: got %d", code)
	}
	if code := call(open, "zly"); code != http.StatusUnauthorized {
		t.Errorf("wrong token: got %d", code)
	}
	if code := call(open, "sekret"); code != http.StatusOK {
		t.Errorf("right token: got %d", code)
	}
	repository.failList = true
	if code := call(open, "sekret"); code != http.StatusServiceUnavailable {
		t.Errorf("database down: got %d", code)
	}
}

// Integration: the real SQL of the case store (skips without TEST_DATABASE_URL, like the check_runs tests).
func TestCaseStoreCountsReportsAndMovesStatusForward(t *testing.T) {
	pool := newTestPool(t)
	if _, err := newRunStore(context.Background(), pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	store := &caseStore{pool: pool}
	ctx := context.Background()
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM moderation_cases WHERE case_id = $1`, testCaseID)
	})

	reports, campaign, status, err := store.record(ctx, testCaseID, "Pcim zakazał diesli.", false, "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
	if err != nil || reports != 1 || campaign || status != caseStatusLogged {
		t.Fatalf("first report: %d %v %s %v", reports, campaign, status, err)
	}
	reports, campaign, _, err = store.record(ctx, testCaseID, "Pcim zakazał diesli.", true, "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeef")
	if err != nil || reports != 2 || !campaign {
		t.Fatalf("second report: %d %v %v", reports, campaign, err)
	}
	if err := store.setStatus(ctx, testCaseID, caseStatusForwarded); err != nil {
		t.Fatal(err)
	}
	if err := store.setStatus(ctx, testCaseID, caseStatusRecommended); err != nil {
		t.Fatal(err)
	}
	records, err := store.list(ctx)
	if err != nil {
		t.Fatal(err)
	}
	for _, record := range records {
		if record.CaseID == testCaseID {
			if record.Status != caseStatusForwarded || record.ForwardedAt == nil || record.Reports != 2 {
				t.Fatalf("status must not move back from forwarded: %+v", record)
			}
			return
		}
	}
	t.Fatal("case missing from the list")
}
