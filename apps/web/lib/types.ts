export type Role = "viewer" | "analyst" | "reviewer" | "admin";
export type DocumentStatus = "uploaded" | "processing" | "ready" | "partial" | "failed";
export type RunState =
  | "queued"
  | "running"
  | "waiting_clarification"
  | "awaiting_clarification"
  | "completed"
  | "incomplete"
  | "failed"
  | "cancelled";

export type Me = {
  user_id: string;
  org_id: string;
  email: string;
  name: string;
  org_role: Role;
  projects: { id: string; name: string; role: Role }[];
};

export type Project = {
  id: string;
  name: string;
  description: string;
  permissions_version: number;
  role: Role | null;
  created_at: string;
  members?: { user_id: string; email: string; name: string; role: Role }[];
};

export type DocumentVersion = {
  id: string;
  document_id: string;
  version_no: number;
  sha256: string;
  revision_label: string | null;
  status: DocumentStatus;
  status_detail: Record<string, unknown> | string | null;
  content_type: string;
  size_bytes: number;
  page_count: number | null;
  pipeline_version: string | null;
  supersedes_id: string | null;
  created_at: string;
  filename?: string;
  kind?: string;
  download_url?: string;
  page_images?: string[];
};

export type ProjectDocument = {
  id: string;
  filename: string;
  kind: string;
  created_at: string;
  versions: DocumentVersion[];
};

export type Equipment = {
  id: string;
  tag: string;
  raw_tag: string;
  type: string;
  description: string | null;
  location: string | null;
  evidence_ids: string[];
  assertion_count?: number;
  duplicate_tag?: boolean;
  depth?: number;
};

export type AssertionView = {
  id: string;
  value: string;
  unit: string | null;
  value_canonical: string | null;
  unit_canonical: string | null;
  method: string;
  review_status: string;
  source: string;
  document_version_id: string;
  evidence_ids: string[];
};

export type EquipmentDetail = Equipment & {
  snapshot_id: string;
  assertions: Record<string, AssertionView[]>;
  conflicting_attributes: string[];
  relationships: {
    id: string;
    type: string;
    status: string;
    direction: "in" | "out";
    other: Equipment | null;
    evidence_ids: string[];
  }[];
  decisions: {
    id: string;
    subject_key: string;
    decision: string;
    rationale: string;
    evidence_ids: string[];
    created_at: string;
  }[];
  source: string;
};

export type Snapshot = {
  id: string;
  name: string;
  document_version_ids: string[];
  created_at: string;
};

export type EvidenceItem = {
  id: string;
  document_version_id: string;
  document_id: string;
  filename: string;
  kind: string;
  revision_label: string | null;
  version_no: number;
  locator: Record<string, unknown>;
  text: string;
  span_kind: string;
  page_image_url?: string;
};

export type Finding = {
  id: string;
  type: string;
  severity: "high" | "medium" | "low" | "info";
  title: string;
  summary: string;
  affected_equipment_ids: string[];
  evidence_ids: string[];
  basis: string;
  rule_id: string | null;
  open_questions: string[];
  review_status: string;
};

export type EstimateLine = {
  id: string;
  kind: string;
  description: string;
  quantity: string;
  unit: string;
  unit_price: string | null;
  extended: string | null;
  currency: string;
  pricing_status: string;
  assumption_status: string;
  classification: string;
  evidence_ids?: string[];
};

export type Estimate = {
  currency: "CAD";
  rate_set_version: string;
  lines: EstimateLine[];
  priced_subtotal: string;
  allowances: EstimateLine[];
  unpriced: EstimateLine[];
  exclusions: string[];
  scenarios?: { name: string; total: string; assumptions: string[] }[];
  complete: boolean;
};

export type ChecklistItem = {
  id: string;
  requirement: string;
  proposed_verification: string;
  expected_outcome: string | null;
  expected_outcome_status: "from_requirement" | "missing";
  evidence_ids: string[];
  finding_ids?: string[];
  template_id: string;
  reviewer_decision: "pending" | "accepted" | "modified" | "rejected";
};

export type WorkItem = {
  id: string;
  template_id: string;
  title: string;
  description: string;
  equipment_ids: string[];
  finding_ids: string[];
  labour: { rate_code: string; description: string; hours_low: string; hours_base: string; hours_high: string; unit?: string }[];
  parts: { description: string; quantity: string; reuse_candidate?: boolean }[];
  assumption_status: string;
};

export type Run = {
  id: string;
  change_request_id: string;
  snapshot_id: string;
  state: RunState;
  backend?: string;
  tool_invocations: number;
  clarification_cycles: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  deadline_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  cancel_requested: boolean;
  created_at: string;
  clarifications?: {
    id: string;
    question: string;
    options: string[];
    answer: string | null;
    asked_at: string;
  }[];
  report_version_id?: string | null;
};

export type ChangeRequest = {
  id: string;
  title: string;
  request_text: string;
  target_tags: string[];
  assumptions: string[];
  created_at: string;
  runs: Run[];
};

export type RunEvent = {
  id: string;
  run_id: string;
  sequence: number;
  type: string;
  at: string;
  payload: Record<string, unknown>;
};

export type ReportVersion = {
  id: string;
  report_id: string;
  run_id: string;
  snapshot_id: string;
  version_no: number;
  status: string;
  stale: boolean;
  stale_reason: string | null;
  created_at: string;
  export_key: string | null;
  package?: Record<string, unknown>;
};

export type ReportListItem = {
  id: string;
  change_request: Omit<ChangeRequest, "runs"> | null;
  versions: ReportVersion[];
};

export type ToolResult<T = Record<string, unknown>> = {
  status: "complete" | "partial" | "blocked" | "failed";
  snapshot_id: string;
  data: T;
  evidence_ids: string[];
  warnings: string[];
  unresolved: { code: string; message: string; subject?: string }[];
  tool_version: string;
};

export type SearchData = {
  passages: {
    chunk_id: string;
    score: number;
    matched_by: string[];
    source: string;
    document_version_id: string;
    evidence_ids: string[];
    locator: Record<string, unknown>;
    tags: string[];
    text: string;
  }[];
  query: string;
};

export type TraceData = {
  depth: number;
  truncated: boolean;
  nodes: Equipment[];
  edges: {
    id: string;
    source_id: string;
    target_id: string;
    type: string;
    status: string;
    evidence_ids: string[];
    source: string;
  }[];
  views: { recorded: string[]; verified: string[]; candidate: string[] };
  unresolved_links: { raw_tag: string; normalized_tag: string; evidence_ids: string[]; source: string }[];
};

export const DOCUMENT_KINDS = [
  "equipment_list",
  "io_list",
  "narrative",
  "datasheet",
  "pid",
  "config_export",
  "catalogue",
  "rates",
  "note",
  "other",
] as const;
