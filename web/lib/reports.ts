/**
 * The one call the reporting dashboard makes: GET /api/reports/summary, plus
 * the types for what comes back and two formatters the page shares.
 * Called by app/staff/dashboard/page.tsx only. Depends on lib/api for the API
 * origin and the ApiError class, so a failure here reads like every other one.
 *
 * It is a file of its own rather than more of lib/api.ts because the dashboard
 * is the only consumer and the response is a dozen nested shapes that would
 * otherwise double the length of the file every other page imports.
 */

import { API_URL, ApiError } from "@/lib/api";

export type Totals = {
  turns: number;
  sessions: number;
  cost_usd: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  error_turns: number;
  fallback_turns: number;
};

export type DayPoint = {
  date: string;
  turns: number;
  cost_usd: number;
  latency_p95_ms: number;
};

export type IntentRow = { intent: string; turns: number; share: number };
export type TierRow = { tier: string; turns: number; cost_usd: number };
export type ToolRow = { name: string; calls: number; errors: number; live_share: number };
export type TypeStatusRow = { type: string; status: string; count: number };

export type ApplicationsReport = {
  by_type_status: TypeStatusRow[];
  /** Null when nothing reached review in the window — not zero. */
  median_hours_to_review: number | null;
  issued: number;
  needs_info: number;
};

export type UnansweredRow = {
  message: string | null;
  intent: string | null;
  created_at: string | null;
  /** Why it is listed: nothing was retrieved, or the reply gave the City line. */
  reason: "no_sources" | "declined";
};

export type ReportSummary = {
  days: number;
  totals: Totals;
  by_day: DayPoint[];
  by_intent: IntentRow[];
  by_tier: TierRow[];
  tools: ToolRow[];
  citation_rate: number;
  applications: ApplicationsReport;
  unanswered: UnansweredRow[];
};

/** The windows the selector offers. The API accepts 1..90; these are the useful ones. */
export const WINDOWS = [1, 7, 30] as const;
export type ReportWindow = (typeof WINDOWS)[number];

/**
 * Fetch one window of the report. `credentials: "include"` carries the staff
 * session cookie, which is what makes the endpoint answer at all.
 */
export async function getReportSummary(days: number): Promise<ReportSummary> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/reports/summary?days=${days}`, {
      credentials: "include",
    });
  } catch {
    throw new ApiError(`Cannot reach the API at ${API_URL}. Is it running?`, 0);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON body: keep the status line */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as ReportSummary;
}

/** Dollars at a readable precision: cents are meaningless at $0.0004 a turn. */
export function money(usd: number): string {
  if (usd === 0) return "$0.00";
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

/** 0.6667 -> "67%". Shares and rates are never worth a decimal place here. */
export function percent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

/** "2026-09-15" -> "Sep 15", the only part of a date a 30-bar chart can show. */
export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
