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

	pointsConfirmed  = 100.0
	pointsMisleading = 25.0
	pointsFalse      = 0.0

	levelHighMinScore  = 70
	levelMixedMinScore = 40

	weightStrong   = 1.0
	weightModerate = 0.6
	weightWeak     = 0.3
	weightNone     = 0.1

	roundingOffset = 0.5
)

const dateOnlyLayout = "2006-01-02"

// Summary is the deterministic overall rating of a submission (CONTRACT.md §1a). It is never produced by a model.
type Summary struct {
	Level   string   `json:"level"`
	Score   *int     `json:"score"`
	Reasons []string `json:"reasons"`
}

// buildSummary scores only claims with a substantive verdict (confirmed, false, misleading).
// Score = round(sum(weight*points) / sum(weight)), where points come from the verdict
// (confirmed 100, misleading 25, false 0) and weight from evidenceStrength, so weakly
// supported claims move the score less. Abstentions are excluded: they are not "50% true".
func buildSummary(result agent.CheckResult) Summary {
	unknown := Summary{Level: summaryLevelUnknown, Reasons: []string{}}
	if result.Status != agent.StatusOK {
		return unknown
	}

	var weightedPoints, totalWeight float64
	var confirmed, falseCount, misleading, withoutVerdict int
	for _, claim := range result.Claims {
		points, counted := verdictPoints(claim.Verdict)
		if !counted {
			withoutVerdict++
			continue
		}
		switch claim.Verdict {
		case agent.VerdictConfirmed:
			confirmed++
		case agent.VerdictFalse:
			falseCount++
		case agent.VerdictMisleading:
			misleading++
		}
		weight := strengthWeight(claim.EvidenceStrength)
		weightedPoints += weight * points
		totalWeight += weight
	}
	if totalWeight == 0 {
		return unknown
	}

	score := int(weightedPoints/totalWeight + roundingOffset)

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

	return Summary{Level: levelForScore(score), Score: &score, Reasons: reasons}
}

func verdictPoints(verdict string) (float64, bool) {
	switch verdict {
	case agent.VerdictConfirmed:
		return pointsConfirmed, true
	case agent.VerdictMisleading:
		return pointsMisleading, true
	case agent.VerdictFalse:
		return pointsFalse, true
	default:
		return 0, false
	}
}

func strengthWeight(strength string) float64 {
	switch strength {
	case agent.StrengthStrong:
		return weightStrong
	case agent.StrengthModerate:
		return weightModerate
	case agent.StrengthWeak:
		return weightWeak
	default:
		return weightNone
	}
}

func levelForScore(score int) string {
	switch {
	case score >= levelHighMinScore:
		return summaryLevelHigh
	case score >= levelMixedMinScore:
		return summaryLevelMixed
	default:
		return summaryLevelLow
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
func buildBadges(result agent.CheckResult, now time.Time, archivalAfter time.Duration) []string {
	badges := []string{}
	var newest time.Time
	var sourceCount int
	var officialPresent bool

	for _, claim := range result.Claims {
		for _, source := range claim.Sources {
			sourceCount++
			if source.SourceType == agent.SourceTypeOfficial {
				officialPresent = true
			}
			if published, ok := parsePublishedAt(source.PublishedAt); ok && published.After(newest) {
				newest = published
			}
		}
	}

	if !newest.IsZero() {
		if now.Sub(newest) > archivalAfter {
			badges = append(badges, badgeArchivalMaterial)
		} else {
			badges = append(badges, badgeFreshMaterial)
		}
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
	for _, layout := range []string{time.RFC3339, dateOnlyLayout} {
		if parsed, err := time.Parse(layout, *value); err == nil {
			return parsed, true
		}
	}
	return time.Time{}, false
}
