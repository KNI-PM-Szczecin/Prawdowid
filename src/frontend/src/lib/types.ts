// CheckResult from CONTRACT.md §1 and §1a. Fields from §1a are optional until the backend returns them.

export type Verdict = "confirmed" | "false" | "misleading" | "insufficient_evidence" | "not_verifiable";
export type Status = "ok" | "technical_error" | "needs_clarification" | "out_of_scope";
export type InputType = "text" | "url";
export type EvidenceStrength = "strong" | "moderate" | "weak" | "none";
export type SourceType = "official" | "secondary" | "factcheck" | "incident";
export type SourceRole = "supports" | "refutes" | "context";
export type WarningType = "source_status" | "incident_match" | "archival_material" | "other";
export type SummaryLevel = "high" | "mixed" | "low" | "unknown";
export type Badge = "fresh_material" | "archival_material" | "official_source_present" | "official_source_absent";

export interface Source {
  id: string;
  title: string;
  publisher: string;
  publishedAt: string | null;
  fetchedAt: string;
  url: string;
  license: string | null;
  sourceType: SourceType;
  role: SourceRole;
  quote: string;
}

export interface ClaimWarning {
  type: WarningType;
  message: string;
}

export interface TextSpan {
  start: number;
  end: number;
}

export interface Claim {
  id: string;
  text: string;
  span?: TextSpan | null;
  verdict: Verdict;
  justification: string;
  evidenceStrength: EvidenceStrength;
  strengthReasons: string[];
  sources: Source[];
  warnings: ClaimWarning[];
  conflict?: { summary: string } | null;
  missing: string | null;
}

export interface CheckedDocument {
  title: string | null;
  text: string;
  url: string | null;
  publisher: string | null;
  fetchedAt: string | null;
}

export interface Summary {
  level: SummaryLevel;
  reasons: string[];
}

export interface CampaignMatch {
  incidentId: string;
  source: string;
  title: string;
  summary: string;
  url: string;
  publishedAt: string | null;
}

export interface CampaignAlert {
  category: "possible_disinformation_campaign";
  message: string;
  matches: CampaignMatch[];
}

export interface RunMeta {
  channel: string;
  receivedAt: string;
  latencyMs: number;
  model: string | null;
  estimatedCostUsd: number | null;
  corpusVersion: string | null;
  retrievedPassages: number;
  searchErrors: number;
  injectionAttempts: number;
  abstained: boolean;
  timedOut: boolean;
}

export interface CheckResult {
  requestId: string;
  status: Status;
  message: string | null;
  document?: CheckedDocument | null;
  summary?: Summary | null;
  badges?: Badge[];
  campaignAlert?: CampaignAlert | null;
  claims: Claim[];
  limitations: string[];
  meta: RunMeta;
}
