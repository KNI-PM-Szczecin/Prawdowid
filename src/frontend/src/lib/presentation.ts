import { texts } from "./texts";
import type { Claim, SummaryLevel } from "./types";

export type Tone = "positive" | "negative" | "warning" | "neutral";

// Sets --tone-soft, --tone-line and --tone-strong for the element (styles/_tokens.scss).
export const toneClass = (tone: Tone) => `tone--${tone}`;

export const SUMMARY_TONE: Record<SummaryLevel, Tone> = {
  high: "positive",
  mixed: "warning",
  low: "negative",
  unknown: "neutral",
};

// Until agent/ returns claims[].conflict (CONTRACT.md §1a), sources with both roles mean a conflict.
export function hasConflict(claim: Claim): boolean {
  if (claim.conflict) {
    return true;
  }
  const roles = new Set(claim.sources.map((source) => source.role));
  return claim.verdict === "insufficient_evidence" && roles.has("supports") && roles.has("refutes");
}

export function verdictTone(claim: Claim): Tone {
  switch (claim.verdict) {
    case "confirmed":
      return "positive";
    case "false":
      return "negative";
    case "misleading":
      return "warning";
    case "insufficient_evidence":
      return hasConflict(claim) ? "warning" : "neutral";
    case "not_verifiable":
      return "neutral";
  }
}

export function verdictLabel(claim: Claim): string {
  if (claim.verdict !== "insufficient_evidence") {
    return texts.verdict[claim.verdict];
  }
  if (hasConflict(claim)) {
    return texts.verdict.conflicting;
  }
  return claim.sources.length > 0 ? texts.verdict.partial : texts.verdict.insufficient_evidence;
}

const dateFormatter = new Intl.DateTimeFormat("pl-PL", { day: "numeric", month: "long", year: "numeric" });

export function formatDate(isoDate: string | null): string | null {
  if (!isoDate) {
    return null;
  }
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime()) ? null : dateFormatter.format(date);
}
