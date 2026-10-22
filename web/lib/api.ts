/**
 * Typed fetch helpers for every FastAPI endpoint the UI touches.
 * Called by the four pages and their components; depends on NEXT_PUBLIC_API_URL
 * and lib/session (the 403 retry below). The API is a different origin (a
 * different port counts), so every call sends `credentials: "include"` to carry
 * the staff_session and resident_session cookies.
 */

import { resetSession } from "@/lib/session";

// Inlined at build time by Next, so it must be referenced as a full literal.
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

/** An error with the HTTP status attached, so callers can tell 401 from 500. */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isUnauthorized(e: unknown): boolean {
  return e instanceof ApiError && e.status === 401;
}

/** 403 from a resident route means "this session id is another browser's" (M20). */
export function isForeignSession(e: unknown): boolean {
  return e instanceof ApiError && e.status === 403;
}

/**
 * Run a resident call, and on a 403 rotate to a fresh session id and try once more.
 *
 * The API binds a session id to the first browser that uses it, so a 403 here
 * is recoverable exactly once: a new id has no history, so it mints its own
 * cookie and the turn goes through. A second 403 is not retried — that would be
 * a loop — and its `detail` is what the page shows the resident.
 *
 * `onReset` hands the new id back to the caller, because the page caches it in
 * a ref and would otherwise keep sending the id that was just refused.
 */
export async function withSessionRetry<T>(
  sessionId: string,
  run: (sessionId: string) => Promise<T>,
  onReset: (sessionId: string) => void,
): Promise<T> {
  try {
    return await run(sessionId);
  } catch (e) {
    if (!isForeignSession(e)) throw e;
    const fresh = resetSession();
    onReset(fresh);
    return run(fresh);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    // credentials: "include" on every call — the session cookie is what makes
    // the staff endpoints answer, and a cross-origin fetch omits it by default.
    res = await fetch(`${API_URL}${path}`, { credentials: "include", ...init });
  } catch {
    throw new ApiError(`Cannot reach the API at ${API_URL}. Is it running?`, 0);
  }
  if (!res.ok) {
    // FastAPI errors are {detail: ...}; fall back to the status line.
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON body: keep the status line */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

// --------------------------------------------------------------------- types

export type Citation = {
  n: number;
  doc_title?: string | null;
  source_url?: string | null;
  text?: string | null;
  chunk_id?: number | null;
  implicit?: boolean;
};

/** The orchestrator emits `action`; the spec calls it `type`. Accept both. */
export type ChatAction = {
  action?: string;
  type?: string;
  form_type?: string;
  form?: FormSchema | null;
  tracking_number?: string;
  status?: string;
  department?: string | null;
  sla_days?: number | null;
};

export type TraceCall = {
  tier?: string;
  model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  latency_ms?: number;
  cost_usd?: number;
  tool_call_names?: string[];
};

export type TraceToolCall = {
  name: string;
  arguments?: unknown;
  result_summary?: string;
  /** M8 live tools: "live" (City map service) or "seed" (demo data). */
  source?: string | null;
  /** How the address was resolved: "seed" | "geocoded" | "zip". */
  match?: string | null;
};

export type Trace = {
  id?: number | null;
  session_id?: string | null;
  message?: string | null;
  reply?: string | null;
  intent?: string | null;
  confidence?: number | null;
  tier?: string | null;
  model?: string | null;
  reason?: string | null;
  error?: string | null;
  rag_chunk_ids?: number[];
  tool_calls?: TraceToolCall[];
  calls?: TraceCall[];
  document_ids?: number[];
  prompt_tokens?: number;
  completion_tokens?: number;
  latency_ms?: number;
  cost_usd?: number;
  created_at?: string | null;
};

export type ChatResponse = {
  reply: string;
  citations: Citation[];
  actions: ChatAction[];
  trace: Trace;
};

export type UploadedDocument = {
  document_id: number;
  filename: string;
  content_type?: string | null;
  size?: number | null;
  text_preview?: string | null;
  has_text?: boolean;
};

export type FormField = {
  name: string;
  label: string;
  type: "text" | "number" | "date" | "email" | "select" | "textarea" | "checkbox";
  required?: boolean;
  options?: string[];
  placeholder?: string;
};

export type FormSchema = {
  form_type: string;
  title: string;
  fields: FormField[];
};

export type Application = {
  id: number;
  tracking_number: string;
  type: string;
  status: string;
  fields?: Record<string, unknown> | null;
  missing_fields?: string[] | null;
  warnings?: string[] | null;
  department?: string | null;
  fee_cents?: number | null;
  certificate_s3_key?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ApplicationEvent = {
  from_status?: string | null;
  to_status?: string | null;
  actor?: string | null;
  note?: string | null;
  created_at?: string | null;
};

export type ApplicationDetail = Application & {
  events?: ApplicationEvent[];
  allowed_transitions?: string[];
};

export type Health = {
  status: string;
  db: string;
  s3: string;
  kb_chunks?: number | null;
  /** One entry per startup step that failed; empty on a clean boot (M14). */
  startup_errors?: Record<string, string>;
  models?: Record<string, string>;
  /** Gateway alias -> the model behind it, e.g. {"smart": "claude-sonnet-4-6"}. */
  provider_models?: Record<string, string>;
};

/** Who is signed in at the back office (M11). */
export type StaffIdentity = {
  display_name: string;
  username: string;
};

// ----------------------------------------------------------------- endpoints

export function login(username: string, password: string): Promise<StaffIdentity> {
  return request<StaffIdentity>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}

/** 200 with the signed-in staff member, or an ApiError with status 401. */
export function getMe(): Promise<StaffIdentity> {
  return request<StaffIdentity>("/api/auth/me");
}


export function postChat(body: {
  session_id: string;
  message: string;
  document_ids?: number[];
}): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function uploadDocument(file: File, sessionId: string): Promise<UploadedDocument> {
  const data = new FormData();
  data.append("file", file);
  // In the form body, not the query string: a session id in a URL ends up in
  // access logs and referrers. It is what binds the upload to this conversation,
  // so a resident who drops a form in before typing still owns the session.
  if (sessionId) data.append("session_id", sessionId);
  return request<UploadedDocument>("/api/documents", { method: "POST", body: data });
}

export function getForm(formType: string): Promise<FormSchema> {
  return request<FormSchema>(`/api/forms/${encodeURIComponent(formType)}`);
}

/** A fresh opaque key per submit, so a retried POST files one application. */
function idempotencyKey(): string {
  try {
    return crypto.randomUUID();
  } catch {
    // Older Safari and any non-secure context: the key only has to be unique
    // to this submit, so Math.random plus the clock is enough.
    return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

export function createApplication(body: {
  type: string;
  fields: Record<string, unknown>;
  session_id: string;
}): Promise<Application> {
  return request<Application>("/api/applications", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // One key per call, generated here rather than by the form: a double
      // click, a flaky connection retried by the browser, or the 403 rotation
      // above all replay this same request, and the API returns the original
      // application instead of filing a second one.
      "Idempotency-Key": idempotencyKey(),
    },
    body: JSON.stringify(body),
  });
}

export function listApplications(params: {
  status?: string;
  type?: string;
  limit?: number;
} = {}): Promise<Application[]> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.type) q.set("type", params.type);
  if (params.limit) q.set("limit", String(params.limit));
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return request<Application[]>(`/api/applications${suffix}`);
}

export function getApplication(idOrTracking: string | number): Promise<ApplicationDetail> {
  return request<ApplicationDetail>(`/api/applications/${encodeURIComponent(String(idOrTracking))}`);
}

export function advanceApplication(
  id: string | number,
  to: string,
  note?: string,
): Promise<ApplicationDetail> {
  return request<ApplicationDetail>(`/api/applications/${encodeURIComponent(String(id))}/advance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to, note: note || null }),
  });
}

export function certificateUrl(id: string | number): string {
  return `${API_URL}/api/applications/${encodeURIComponent(String(id))}/certificate`;
}

export function listTraces(limit = 100): Promise<Trace[]> {
  return request<Trace[]>(`/api/traces?limit=${limit}`);
}

export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}

// ------------------------------------------------------------------ helpers

/** Cents to "$1,234.00"; null/undefined renders as an em dash. */
export function formatFee(cents?: number | null): string {
  if (cents === null || cents === undefined) return "—";
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
}
