import { texts } from "./texts";
import type { Claim, SummaryLevel } from "./types";

export type Tone = "positive" | "negative" | "warning" | "neutral";

// Static class strings so Tailwind can find them in the source.
export const TONE_CLASSES: Record<Tone, { box: string; chip: string; icon: string; highlight: string }> = {
  positive: {
    box: "bg-positive-soft border-positive-line",
    chip: "bg-positive-soft border-positive-line",
    icon: "text-positive-strong",
    highlight: "bg-positive-soft border-positive-strong",
  },
  negative: {
    box: "bg-negative-soft border-negative-line",
    chip: "bg-negative-soft border-negative-line",
    icon: "text-negative-strong",
    highlight: "bg-negative-soft border-negative-strong",
  },
  warning: {
    box: "bg-warning-soft border-warning-line",
    chip: "bg-warning-soft border-warning-line",
    icon: "text-warning-strong",
    highlight: "bg-warning-soft border-warning-strong",
  },
  neutral: {
    box: "bg-neutral-soft border-neutral-line",
    chip: "bg-neutral-soft border-neutral-line",
    icon: "text-neutral-strong",
    highlight: "bg-neutral-soft border-neutral-strong",
  },
};

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
