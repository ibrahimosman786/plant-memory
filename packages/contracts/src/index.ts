/**
 * Hand-maintained TypeScript mirrors of the JSON schemas in ../schemas.
 * The Python side validates with Pydantic models generated from the same schema set
 * (services/api/plant_memory/contracts.py). Keep both in step; CI runs
 * `test/schema-sync.test.ts` to catch drift in enum values.
 */

export type ToolStatus = "complete" | "partial" | "blocked" | "failed";

export interface Unresolved {
  code: string;
  message: string;
  subject?: string;
}

export interface ToolResult<T = Record<string, unknown>> {
  status: ToolStatus;
  snapshot_id: string;
  data: T;
  evidence_ids: string[];
  warnings: string[];
  unresolved: Unresolved[];
  tool_version: string;
}

export const FINDING_TYPES = [
  "duplicate_tag",
  "duplicate_channel",
  "missing_equipment",
  "incompatible_units",
  "conflicting_ranges",
  "missing_evidence",
  "unpriced_line",
  "expired_price",
  "superseded_evidence",
  "unsupported_assertion",
  "reuse_candidate",
  "required_work",
  "ambiguous_identifier",
  "no_relevant_finding",
  "other",
] as const;
export type FindingType = (typeof FINDING_TYPES)[number];

export const SEVERITIES = ["high", "medium", "low", "info"] as const;
export type Severity = (typeof SEVERITIES)[number];

export type FindingBasis = "rule" | "recorded_fact" | "candidate_interpretation" | "engineer_decision";
export type ReviewStatus = "unreviewed" | "accepted" | "rejected" | "needs_info";

export interface Finding {
  id: string;
  type: FindingType;
  severity: Severity;
  title: string;
  summary: string;
  affected_equipment_ids: string[];
  evidence_ids: string[];
  basis: FindingBasis;
  rule_id: string | null;
  open_questions: string[];
  review_status: ReviewStatus;
}

export type PricingStatus = "priced" | "unpriced" | "expired" | "allowance";
export type LineKind = "part" | "labour" | "allowance" | "service";
export type Classification = "included" | "excluded" | "optional";

export interface EstimateLine {
  id: string;
  kind: LineKind;
  description: string;
  equipment_ids?: string[];
  quantity: string;
  unit: string;
  unit_price: string | null;
  extended: string | null;
  currency: string;
  price_source: string | null;
  price_effective_date: string | null;
  pricing_status: PricingStatus;
  assumption_status: "recorded" | "assumed" | "engineer_confirmed";
  classification: Classification;
  origin: { kind: "rule" | "finding" | "evidence" | "template" | "engineer"; ref: string };
  evidence_ids?: string[];
}

export interface Estimate {
  currency: "CAD";
  rate_set_version: string;
  lines: EstimateLine[];
  priced_subtotal: string;
  allowances: EstimateLine[];
  unpriced: EstimateLine[];
  exclusions: string[];
  scenarios?: { name: string; total: string; assumptions: string[] }[];
  complete: boolean;
}

export interface ChecklistItem {
  id: string;
  requirement: string;
  proposed_verification: string;
  expected_outcome: string | null;
  expected_outcome_status: "from_requirement" | "missing";
  evidence_ids: string[];
  finding_ids?: string[];
  equipment_ids?: string[];
  template_id: string;
  reviewer_decision: "pending" | "accepted" | "modified" | "rejected";
}

export type PackageStatus = "review_ready" | "needs_clarification" | "incomplete";
export type PackageSection =
  | "scope"
  | "dependencies"
  | "consistency"
  | "requirements"
  | "work_breakdown"
  | "estimate"
  | "checklist";

export interface DraftPackage {
  status: PackageStatus;
  scope_summary: string;
  affected_equipment_ids: string[];
  finding_ids: string[];
  work_item_ids: string[];
  estimate_id: string | null;
  checklist_ids: string[];
  reuse_candidates: {
    equipment_id: string;
    rationale: string;
    evidence_ids: string[];
    status: "candidate" | "insufficient_evidence";
  }[];
  open_questions: string[];
  sections_incomplete: { section: PackageSection; reason: string }[];
}

export const RUN_EVENT_TYPES = [
  "run.created",
  "run.started",
  "snapshot.frozen",
  "scope.parsed",
  "tool.started",
  "tool.completed",
  "tool.failed",
  "finding.added",
  "section.completed",
  "section.incomplete",
  "clarification.requested",
  "clarification.answered",
  "limit.reached",
  "package.saved",
  "run.completed",
  "run.failed",
  "run.cancelled",
] as const;
export type RunEventType = (typeof RUN_EVENT_TYPES)[number];

export interface RunEvent<P = Record<string, unknown>> {
  id: string;
  run_id: string;
  sequence: number;
  type: RunEventType;
  at: string;
  payload: P;
}

export type RunState =
  | "queued"
  | "running"
  | "awaiting_clarification"
  | "completed"
  | "incomplete"
  | "failed"
  | "cancelled";

export type DocumentStatus = "uploaded" | "processing" | "ready" | "partial" | "failed";

export type Role = "viewer" | "analyst" | "reviewer" | "admin";
