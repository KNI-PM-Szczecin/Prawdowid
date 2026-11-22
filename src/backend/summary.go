package main

import (
	"fmt"
	"time"

	"prawdowid/agent"
)

const (
	summaryLevelHigh    = "high"
	summaryLevelMixed   = "mixed"
	summaryLevelLow     = "low"
	summaryLevelUnknown = "unknown"

	badgeFreshMaterial    = "fresh_material"
	badgeArchivalMaterial = "archival_material"
	badgeOfficialPresent  = "official_source_present"
	badgeOfficialAbsent   = "official_source_absent"
)

const (
	dateOnlyLayout = "2006-01-02"
	// dateTimeNoZoneLayout is an ISO date-time without a zone, which CONTRACT.md defines as UTC (time.Parse assumes UTC).
	dateTimeNoZoneLayout = "2006-01-02T15:04:05"
)

// Summary is the deterministic overall rating of a submission (CONTRACT.md §1a). It is never produced by a model
// and carries no percentage: a rule over the decided verdicts picks the level, the reasons say why.
type Summary struct {
	Level   string   `json:"level"`
	Reasons []string `json:"reasons"`
}

// buildSummary reads only claims with a substantive verdict (confirmed, false, misleading): high when all of them
// are confirmed, low when all are false, mixed otherwise (one misleading claim is enough), unknown when none is
// decided, because an abstention is not "50% true". A status other than ok has no summary at all.
func buildSummary(result agent.CheckResult) *Summary {
	if result.Status != agent.StatusOK {
		return nil
	}
	var confirmed, falseCount, misleading, withoutVerdict int
	for _, claim := range result.Claims {
		switch claim.Verdict {
		case agent.VerdictConfirmed:
			confirmed++
		case agent.VerdictFalse:
			falseCount++
		case agent.VerdictMisleading:
			misleading++
		default:
			withoutVerdict++
		}
	}
	decided := confirmed + falseCount + misleading
	if decided == 0 {
		return &Summary{Level: summaryLevelUnknown, Reasons: []string{}}
	}

	reasons := []string{fmt.Sprintf("%d z %d twierdzeń potwierdzone", confirmed, len(result.Claims))}
	if falseCount > 0 {
		reasons = append(reasons, fmt.Sprintf("fałszywe: %d", falseCount))
	}
	if misleading > 0 {
		reasons = append(reasons, fmt.Sprintf("wprowadzające w błąd: %d", misleading))
	}
	if withoutVerdict > 0 {
		reasons = append(reasons, fmt.Sprintf("bez oceny z powodu braku dowodów lub możliwości sprawdzenia: %d", withoutVerdict))
	}
	if official := countOfficialSources(result.Claims); official > 0 {
		reasons = append(reasons, fmt.Sprintf("w tym źródeł urzędowych: %d", official))
	}
	return &Summary{Level: summaryLevel(confirmed, falseCount, decided), Reasons: reasons}
}

func summaryLevel(confirmed, falseCount, decided int) string {
	switch {
	case confirmed == decided:
		return summaryLevelHigh
	case falseCount == decided:
		return summaryLevelLow
	default:
		return summaryLevelMixed
	}
}

func countOfficialSources(claims []agent.Claim) int {
	seen := make(map[string]bool)
	for _, claim := range claims {
		for _, source := range claim.Sources {
			if source.SourceType == agent.SourceTypeOfficial {
				seen[source.ID] = true
			}
		}
	}
	return len(seen)
}

// buildBadges returns neutral labels derived only from source dates and source types, never from domain reputation.
// A source whose publishedAt is missing or unparsable counts as neither fresh nor archival.
// The freshness badge looks at the newest dated source of each claim: archival_material when any claim is older
// than the threshold, fresh_material otherwise.
func buildBadges(result agent.CheckResult, now time.Time, archivalAfter time.Duration) []string {
	badges := []string{}
	var sourceCount int
	var officialPresent, anyDated, anyArchival bool

	for _, claim := range result.Claims {
		var newest time.Time
		for _, source := range claim.Sources {
			sourceCount++
			if source.SourceType == agent.SourceTypeOfficial {
				officialPresent = true
			}
			if published, ok := parsePublishedAt(source.PublishedAt); ok && published.After(newest) {
				newest = published
			}
		}
		if newest.IsZero() {
			continue
		}
		anyDated = true
		if now.Sub(newest) > archivalAfter {
			anyArchival = true
		}
	}

	// One claim resting on old material is enough to warn, even when another claim has a fresh source.
	switch {
	case anyArchival:
		badges = append(badges, badgeArchivalMaterial)
	case anyDated:
		badges = append(badges, badgeFreshMaterial)
	}
	if sourceCount > 0 {
		if officialPresent {
			badges = append(badges, badgeOfficialPresent)
		} else {
			badges = append(badges, badgeOfficialAbsent)
		}
	}
	return badges
}

func parsePublishedAt(value *string) (time.Time, bool) {
	if value == nil {
		return time.Time{}, false
	}
	for _, layout := range []string{time.RFC3339, dateTimeNoZoneLayout, dateOnlyLayout} {
		if parsed, err := time.Parse(layout, *value); err == nil {
			return parsed, true
		}
	}
	return time.Time{}, false
}
