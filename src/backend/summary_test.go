package main

import (
	"reflect"
	"testing"
	"time"

	"prawdowid/agent"
)

func strPtr(value string) *string { return &value }

func claimWith(verdict, strength string, sources ...agent.SourceRef) agent.Claim {
	return agent.Claim{Verdict: verdict, EvidenceStrength: strength, Sources: sources}
}

func TestBuildSummary(t *testing.T) {
	official := agent.SourceRef{ID: "s1", SourceType: agent.SourceTypeOfficial}
	tests := []struct {
		name      string
		result    agent.CheckResult
		wantLevel string
		wantFirst string
	}{
		{
			name: "all confirmed",
			result: agent.CheckResult{Status: agent.StatusOK, Claims: []agent.Claim{
				claimWith(agent.VerdictConfirmed, agent.StrengthStrong, official),
				claimWith(agent.VerdictConfirmed, agent.StrengthModerate, official),
			}},
			wantLevel: summaryLevelHigh, wantFirst: "2 z 2 twierdzeń potwierdzone",
		},
		{
			name: "confirmed and false is mixed",
			result: agent.CheckResult{Status: agent.StatusOK, Claims: []agent.Claim{
				claimWith(agent.VerdictConfirmed, agent.StrengthStrong),
				claimWith(agent.VerdictFalse, agent.StrengthStrong),
			}},
			wantLevel: summaryLevelMixed, wantFirst: "1 z 2 twierdzeń potwierdzone",
		},
		{
			name: "misleading only is mixed, not low",
			result: agent.CheckResult{Status: agent.StatusOK, Claims: []agent.Claim{
				claimWith(agent.VerdictMisleading, agent.StrengthStrong),
			}},
			wantLevel: summaryLevelMixed, wantFirst: "0 z 1 twierdzeń potwierdzone",
		},
		{
			name: "all false is low",
			result: agent.CheckResult{Status: agent.StatusOK, Claims: []agent.Claim{
				claimWith(agent.VerdictFalse, agent.StrengthStrong),
				claimWith(agent.VerdictFalse, agent.StrengthWeak),
			}},
			wantLevel: summaryLevelLow, wantFirst: "0 z 2 twierdzeń potwierdzone",
		},
		{
			name: "evidence strength does not change the level",
			result: agent.CheckResult{Status: agent.StatusOK, Claims: []agent.Claim{
				claimWith(agent.VerdictConfirmed, agent.StrengthStrong),
				claimWith(agent.VerdictFalse, agent.StrengthWeak),
			}},
			wantLevel: summaryLevelMixed, wantFirst: "1 z 2 twierdzeń potwierdzone",
		},
		{
			name: "abstained claim is excluded from the level",
			result: agent.CheckResult{Status: agent.StatusOK, Claims: []agent.Claim{
				claimWith(agent.VerdictConfirmed, agent.StrengthStrong),
				claimWith(agent.VerdictInsufficientEvidence, agent.StrengthNone),
			}},
			wantLevel: summaryLevelHigh, wantFirst: "1 z 2 twierdzeń potwierdzone",
		},
		{
			name: "only insufficient evidence",
			result: agent.CheckResult{Status: agent.StatusOK, Claims: []agent.Claim{
				claimWith(agent.VerdictInsufficientEvidence, agent.StrengthNone),
				claimWith(agent.VerdictNotVerifiable, agent.StrengthNone),
			}},
			wantLevel: summaryLevelUnknown,
		},
		{
			name:      "no claims",
			result:    agent.CheckResult{Status: agent.StatusOK},
			wantLevel: summaryLevelUnknown,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got := buildSummary(test.result)
			if got == nil {
				t.Fatal("ok status must have a summary")
			}
			if got.Level != test.wantLevel {
				t.Errorf("level = %q, want %q", got.Level, test.wantLevel)
			}
			if got.Reasons == nil {
				t.Error("reasons must be non-nil")
			}
			if test.wantFirst != "" && (len(got.Reasons) == 0 || got.Reasons[0] != test.wantFirst) {
				t.Errorf("reasons = %v, want first %q", got.Reasons, test.wantFirst)
			}
			if test.wantFirst == "" && len(got.Reasons) != 0 {
				t.Errorf("unknown summary must have no reasons, got %v", got.Reasons)
			}
		})
	}
}

func TestBuildSummaryIsNilForNonOkStatus(t *testing.T) {
	for _, status := range []string{agent.StatusTechnicalError, agent.StatusNeedsClarification, agent.StatusOutOfScope} {
		result := agent.CheckResult{Status: status, Claims: []agent.Claim{claimWith(agent.VerdictConfirmed, agent.StrengthStrong)}}
		if got := buildSummary(result); got != nil {
			t.Errorf("status %s: summary = %+v, want nil", status, got)
		}
	}
}

func TestBuildSummaryOfficialReason(t *testing.T) {
	shared := agent.SourceRef{ID: "s1", SourceType: agent.SourceTypeOfficial}
	result := agent.CheckResult{Status: agent.StatusOK, Claims: []agent.Claim{
		claimWith(agent.VerdictConfirmed, agent.StrengthStrong, shared),
		claimWith(agent.VerdictConfirmed, agent.StrengthStrong, shared),
	}}
	got := buildSummary(result)
	want := []string{"2 z 2 twierdzeń potwierdzone", "w tym źródeł urzędowych: 1"}
	if !reflect.DeepEqual(got.Reasons, want) {
		t.Errorf("reasons = %v, want %v", got.Reasons, want)
	}
}

func TestBuildBadges(t *testing.T) {
	now := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	archivalAfter := 365 * 24 * time.Hour
	boundary := now.Add(-archivalAfter).Format(time.RFC3339)
	justOlder := now.Add(-archivalAfter - time.Second).Format(time.RFC3339)

	source := func(sourceType string, publishedAt *string) agent.SourceRef {
		return agent.SourceRef{SourceType: sourceType, PublishedAt: publishedAt}
	}
	resultWith := func(sources ...agent.SourceRef) agent.CheckResult {
		return agent.CheckResult{Claims: []agent.Claim{{Sources: sources}}}
	}

	tests := []struct {
		name   string
		result agent.CheckResult
		want   []string
	}{
		{"nil claims", agent.CheckResult{}, []string{}},
		{"claim with nil sources", agent.CheckResult{Claims: []agent.Claim{{}}}, []string{}},
		{"fresh official", resultWith(source(agent.SourceTypeOfficial, strPtr("2026-05-01"))),
			[]string{badgeFreshMaterial, badgeOfficialPresent}},
		{"exactly at threshold is fresh", resultWith(source(agent.SourceTypeSecondary, &boundary)),
			[]string{badgeFreshMaterial, badgeOfficialAbsent}},
		{"just past threshold is archival", resultWith(source(agent.SourceTypeSecondary, &justOlder)),
			[]string{badgeArchivalMaterial, badgeOfficialAbsent}},
		{"newest dated source decides", resultWith(
			source(agent.SourceTypeSecondary, strPtr("2015-01-01")),
			source(agent.SourceTypeFactcheck, strPtr("2026-05-20T10:00:00Z"))),
			[]string{badgeFreshMaterial, badgeOfficialAbsent}},
		{"date-time without zone is read as UTC", resultWith(source(agent.SourceTypeSecondary, strPtr("2026-05-20T10:00:00"))),
			[]string{badgeFreshMaterial, badgeOfficialAbsent}},
		{"archival claim is not hidden by a fresh claim", agent.CheckResult{Claims: []agent.Claim{
			{Sources: []agent.SourceRef{source(agent.SourceTypeSecondary, strPtr("2015-01-01"))}},
			{Sources: []agent.SourceRef{source(agent.SourceTypeSecondary, strPtr("2026-05-20"))}},
		}}, []string{badgeArchivalMaterial, badgeOfficialAbsent}},
		{"fresh when every dated claim is fresh and another has no date", agent.CheckResult{Claims: []agent.Claim{
			{Sources: []agent.SourceRef{source(agent.SourceTypeSecondary, nil)}},
			{Sources: []agent.SourceRef{source(agent.SourceTypeSecondary, strPtr("2026-05-20"))}},
		}}, []string{badgeFreshMaterial, badgeOfficialAbsent}},
		{"missing dates give neither", resultWith(source(agent.SourceTypeOfficial, nil)),
			[]string{badgeOfficialPresent}},
		{"unparsable date gives neither", resultWith(source(agent.SourceTypeSecondary, strPtr("wczoraj"))),
			[]string{badgeOfficialAbsent}},
		{"official in a second claim", agent.CheckResult{Claims: []agent.Claim{
			{Sources: []agent.SourceRef{source(agent.SourceTypeSecondary, nil)}},
			{Sources: []agent.SourceRef{source(agent.SourceTypeOfficial, nil)}},
		}}, []string{badgeOfficialPresent}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got := buildBadges(test.result, now, archivalAfter)
			if got == nil {
				t.Fatal("badges must be non-nil")
			}
			if !reflect.DeepEqual(got, test.want) {
				t.Errorf("badges = %v, want %v", got, test.want)
			}
		})
	}
}
