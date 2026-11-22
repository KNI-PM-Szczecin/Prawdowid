// CheckResult from CONTRACT.md §1 and §1a. Fields from §1a are optional until the backend returns them.

export type Verdict = "confirmed" | "false" | "misleading" | "insufficient_evidence" | "not_verifiable";
export type Status = "ok" | "technical_error" | "needs_clarification" | "out_of_scope";
export type InputType = "text" | "url";
export type EvidenceStrength = "strong" | "moderate" | "weak" | "none";
export type SourceType = "official" | "secondary" | "factcheck" | "incident" | "reference";
export type SourceRole = "supports" | "refutes" | "context";
export type WarningType = "source_status" | "incident_match" | "archival_material" | "other";
export type SummaryLevel = "high" | "mixed" | "low" | "unknown";
export type Badge =
  | "fresh_material"
  | "archival_material"
  | "official_source_present"
  | "official_source_absent"
  | "input_source_in_catalog"
  | "input_source_outside_catalog";

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
  publishedAt?: string | null;
  fetchedAt: string | null;
}

// Brief scenario I: the submitted page recognised as a known material, with the explicit basis. Context only.
export type MaterialMatchKind = "corpus_document" | "incident";
export type MaterialMatchBasis = "url" | "title" | "date";

export interface MaterialMatchItem {
  kind: MaterialMatchKind;
  basis: MaterialMatchBasis[];
  title: string;
  publisher: string;
  url: string;
  publishedAt: string | null;
  sourceType: SourceType | null;
  incidentId: string | null;
  source: string | null;
}

export interface MaterialMatch {
  message: string;
  matches: MaterialMatchItem[];
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
  // Set when the backend served the stored answer to the same question (consistency cache).
  cached?: boolean;
}

// Closed information loop (CONTRACT.md §1a): "forwarded" only after the moderator's webhook accepted the case.
export type CaseStatus = "logged" | "recommended" | "forwarded";

export interface CaseNotice {
  claimId: string;
  caseId: string;
  reports: number;
  status: CaseStatus;
}

export interface CheckResult {
  requestId: string;
  status: Status;
  message: string | null;
  document?: CheckedDocument | null;
  summary?: Summary | null;
  badges?: Badge[];
  campaignAlert?: CampaignAlert | null;
  materialMatch?: MaterialMatch | null;
  cases?: CaseNotice[];
  claims: Claim[];
  limitations: string[];
  meta: RunMeta;
}
