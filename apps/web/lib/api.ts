import type {
  ChangeRequest,
  ChecklistItem,
  DocumentVersion,
  Equipment,
  EquipmentDetail,
  Estimate,
  EvidenceItem,
  Finding,
  Me,
  Project,
  ProjectDocument,
  ReportListItem,
  ReportVersion,
  Role,
  Run,
  RunEvent,
  SearchData,
  Snapshot,
  ToolResult,
  TraceData,
  WorkItem,
} from "./types";

const TOKEN_KEY = "plant-memory.token";

export function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : detailMessage(detail) || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

function detailMessage(detail: unknown): string {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && "detail" in detail) return detailMessage((detail as { detail: unknown }).detail);
  if (Array.isArray(detail)) return detail.map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d))).join("; ");
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

function qs(params: Record<string, string | number | boolean | string[] | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === "") continue;
    if (Array.isArray(v)) v.forEach((item) => u.append(k, item));
    else u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${apiBase()}${path}`, { ...init, headers });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = text;
  if (text) {
    try {
      data = JSON.parse(text) as unknown;
    } catch {
      data = text;
    }
  } else {
    data = null;
  }
  if (!res.ok) throw new ApiError(res.status, data ?? text);
  return data as T;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body?: unknown, extra?: HeadersInit) =>
  request<T>(path, { method: "POST", body: body == null ? undefined : JSON.stringify(body), headers: extra });

export const api = {
  chat: (projectId: string, body: { question: string; snapshot_id: string; model: string; history: { role: "user" | "assistant"; content: string }[] }) => post<ChatAnswer>(`/v1/projects/${projectId}/chat`, body),
  health: () => get<{ ok: boolean; db: boolean }>("/healthz"),
  status: () =>
    get<{
      database: boolean;
      auth_backend: string;
      dev_login_enabled: boolean;
      agent_backend: string;
      model_connected: boolean;
      reasoning_model: string | null;
      model_configured: boolean;
      connection_verified: boolean;
      model_health: { state: string; message: string; checked_at: string | null };
      default_model: string;
      models: string[];
    }>("/v1/status"),
  checkModel: (model: string) => post<{ model: string; state: string; message: string; checked_at: string | null }>("/v1/models/check", { model }),
  me: () => get<Me>("/v1/me"),
  devToken: (body: { email: string; name?: string; org_name?: string; role?: Role }) =>
    post<{ token: string; user_id: string; org_id: string; role: Role }>("/v1/auth/dev-token", body),

  projects: () => get<Project[]>("/v1/projects"),
  createProject: (body: { name: string; description?: string }) => post<Project>("/v1/projects", body),
  project: (id: string) => get<Project>(`/v1/projects/${id}`),

  documents: (projectId: string) => get<ProjectDocument[]>(`/v1/projects/${projectId}/documents`),
  uploadDocument: (projectId: string, file: File, kind: string, revisionLabel?: string, documentId?: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    if (revisionLabel) form.append("revision_label", revisionLabel);
    if (documentId) form.append("document_id", documentId);
    return request<DocumentVersion & { created: boolean; filename: string; kind: string }>(`/v1/projects/${projectId}/documents`, {
      method: "POST",
      body: form,
    });
  },
  documentVersion: (projectId: string, documentId: string, versionId: string) =>
    get<DocumentVersion>(`/v1/projects/${projectId}/documents/${documentId}/versions/${versionId}`),
  evidence: (projectId: string, ids: string[]) =>
    get<EvidenceItem[]>(`/v1/projects/${projectId}/evidence${qs({ ids })}`),

  snapshots: (projectId: string) => get<Snapshot[]>(`/v1/projects/${projectId}/snapshots`),
  createSnapshot: (projectId: string, name: string, document_version_ids?: string[]) =>
    post<Snapshot>(`/v1/projects/${projectId}/snapshots`, { name, document_version_ids }),

  equipment: (projectId: string, params?: { snapshot_id?: string; q?: string; type?: string }) =>
    get<{ snapshot_id: string; equipment: Equipment[] }>(`/v1/projects/${projectId}/equipment${qs(params ?? {})}`),
  equipmentDetail: (projectId: string, equipmentId: string, snapshot_id?: string) =>
    get<EquipmentDetail>(`/v1/projects/${projectId}/equipment/${equipmentId}${qs({ snapshot_id })}`),
  unresolved: (projectId: string, snapshot_id?: string) =>
    get<{ id: string; raw_tag: string; normalized_tag: string; source: string; evidence_ids: string[] }[]>(
      `/v1/projects/${projectId}/unresolved${qs({ snapshot_id })}`,
    ),
  search: (projectId: string, q: string, snapshot_id?: string) =>
    get<ToolResult<SearchData>>(`/v1/projects/${projectId}/search${qs({ q, snapshot_id, limit: 12 })}`),
  trace: (projectId: string, equipmentIds: string[], snapshot_id?: string, depth?: number) =>
    get<ToolResult<TraceData>>(`/v1/projects/${projectId}/trace${qs({ equipment_ids: equipmentIds, snapshot_id, depth })}`),
  catalogue: (projectId: string) =>
    get<{
      parts: { id: string; part_number: string; description: string; category: string; unit_price: string | null; currency: string; effective_date: string; source: string }[];
      rates: { id: string; rate_code: string; description: string; unit: string; rate: string; currency: string; effective_date: string; rate_set_version: string }[];
    }>(`/v1/projects/${projectId}/catalogue`),
  recordDecision: (projectId: string, body: { subject_type: string; subject_key: string; decision: string; rationale?: string; evidence_ids?: string[] }) =>
    post(`/v1/projects/${projectId}/decisions`, body),

  changeRequests: (projectId: string) => get<ChangeRequest[]>(`/v1/projects/${projectId}/change-requests`),
  createChangeRequest: (projectId: string, body: { title: string; request_text: string; target_tags?: string[]; assumptions?: string[] }) =>
    post<ChangeRequest>(`/v1/projects/${projectId}/change-requests`, body),
  startRun: (projectId: string, changeRequestId: string, snapshot_id: string, backend?: string, model?: string) =>
    post<Run>(`/v1/projects/${projectId}/change-requests/${changeRequestId}/runs`, { snapshot_id, backend, model }),
  run: (projectId: string, runId: string) => get<Run>(`/v1/projects/${projectId}/runs/${runId}`),
  runEvents: (projectId: string, runId: string, after = -1) =>
    get<RunEvent[]>(`/v1/projects/${projectId}/runs/${runId}/events${qs({ after })}`),
  cancelRun: (projectId: string, runId: string) => post<Run>(`/v1/projects/${projectId}/runs/${runId}/cancel`),
  answerClarification: (projectId: string, runId: string, clarificationId: string, answer: string) =>
    post<Run>(`/v1/projects/${projectId}/runs/${runId}/clarifications/${clarificationId}/answer`, { answer }),
  findings: (projectId: string, runId: string) => get<Finding[]>(`/v1/projects/${projectId}/runs/${runId}/findings`),
  work: (projectId: string, runId: string) =>
    get<{ work_items: WorkItem[]; estimate: Estimate | null; checklist: ChecklistItem[] }>(`/v1/projects/${projectId}/runs/${runId}/work`),

  reports: (projectId: string) => get<ReportListItem[]>(`/v1/projects/${projectId}/reports`),
  reportVersion: (projectId: string, reportVersionId: string) =>
    get<ReportVersion>(`/v1/projects/${projectId}/report-versions/${reportVersionId}`),
  analyses: (projectId: string, reportVersionId: string) =>
    get<ReportAnalysis[]>(`/v1/projects/${projectId}/report-versions/${reportVersionId}/analyses`),
  analyzeReport: (projectId: string, reportVersionId: string, question: string, model: string) =>
    post<ReportAnalysis>(`/v1/projects/${projectId}/report-versions/${reportVersionId}/analyses`, { question, model }),
  createReview: (
    projectId: string,
    reportVersionId: string,
    body: {
      decision: "approved" | "changes_requested" | "rejected";
      comment?: string;
      items?: { kind: "finding" | "checklist"; id: string; decision: string; note?: string; modified_text?: string }[];
    },
  ) => post(`/v1/projects/${projectId}/report-versions/${reportVersionId}/reviews`, body),
  reviews: (projectId: string, reportVersionId: string) =>
    get<{ id: string; reviewer: string; decision: string; comment: string; item_decisions: Record<string, unknown>; created_at: string }[]>(
      `/v1/projects/${projectId}/report-versions/${reportVersionId}/reviews`,
    ),
  exportReport: (projectId: string, reportVersionId: string, format: "md" | "html" | "json") =>
    post<{ url: string; format: string; bytes: number; stale: boolean }>(
      `/v1/projects/${projectId}/report-versions/${reportVersionId}/export${qs({ format })}`,
    ),
};

export type ReportAnalysis = {
  id: string;
  question: string;
  model: string;
  created_at: string;
  cost_usd: string;
  notice: string;
  analysis: {
    claims: { statement: string; evidence_ids: string[] }[];
    questions_for_engineer: string[];
    limitations: string[];
  };
};

export type ChatAnswer = {
  analysis: ReportAnalysis["analysis"];
  sources: { id: string; filename: string; text: string; revision_label: string | null }[];
  model: string;
  snapshot_id: string;
  steps: string[];
  cost_usd: string;
};
