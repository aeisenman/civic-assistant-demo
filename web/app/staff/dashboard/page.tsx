"use client";

/**
 * The reporting dashboard: one window of GET /api/reports/summary drawn as KPI
 * tiles, a turns-and-cost chart, intent and tier bars, tool and application
 * tables, and the list of questions the assistant could not answer.
 * A staff console page, rendered inside app/staff/layout.tsx (the sign-in gate).
 * Depends on lib/reports for the call, the types and the formatters.
 *
 * Every mark is hand-drawn SVG or a div with a width: a charting library would
 * be 100 kB and a new dependency for eleven bars, and the design tokens in
 * globals.css already say what colour a bar should be.
 */

import { useEffect, useState } from "react";
import {
  getReportSummary,
  money,
  percent,
  shortDate,
  WINDOWS,
  type ReportSummary,
  type ReportWindow,
} from "@/lib/reports";

/** The chart's own coordinate space; the SVG scales to whatever width it gets. */
const CHART_W = 720;
const CHART_H = 220;
const PLOT_TOP = 12;
const PLOT_BOTTOM = 188; // leaves room for the date labels underneath
const PLOT_LEFT = 8;
const PLOT_RIGHT = CHART_W - 8;

function Card({
  title,
  hint,
  testId,
  children,
}: {
  title: string;
  hint?: string;
  testId?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      data-testid={testId}
      className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5"
    >
      <h2 className="text-section font-semibold text-ink">{title}</h2>
      {hint ? <p className="mt-0.5 text-meta text-muted">{hint}</p> : null}
      <div className="mt-3.5">{children}</div>
    </section>
  );
}

/** One number and its name. `value` is always a string so "—" is impossible. */
function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div
      data-testid="kpi-tile"
      data-kpi={label}
      className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
    >
      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
        {label}
      </div>
      <div className="mt-1 text-title font-semibold tabular-nums text-ink">{value}</div>
      {hint ? <div className="mt-0.5 text-meta text-muted">{hint}</div> : null}
    </div>
  );
}

/** The empty state every panel shares, so "no data" never reads as "broken". */
function NoTurns({ what = "turns" }: { what?: string }) {
  return (
    <p data-testid="empty-window" className="py-6 text-center text-meta text-muted">
      No {what} in this window.
    </p>
  );
}

/**
 * Turns and cost per day, two bars per day on two scales.
 *
 * Two scales in one frame is normally a sin, but the question a staff reader has
 * is "did the day that cost the most also carry the most turns?", which is a
 * comparison of shapes, not of values — and the exact numbers are one hover away
 * in each bar's own `<title>`.
 */
function DayChart({ days }: { days: ReportSummary["by_day"] }) {
  if (days.length === 0) return <NoTurns />;

  const maxTurns = Math.max(...days.map((d) => d.turns), 1);
  const maxCost = Math.max(...days.map((d) => d.cost_usd), 0.000001);
  const slot = (PLOT_RIGHT - PLOT_LEFT) / days.length;
  const barW = Math.max(3, Math.min(18, slot * 0.36));
  const height = PLOT_BOTTOM - PLOT_TOP;
  // At 30 days there is not room for 30 labels; show roughly ten.
  const labelEvery = Math.ceil(days.length / 10);

  return (
    <div className="overflow-x-auto">
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-meta text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-primary" /> turns (max{" "}
          {maxTurns})
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-accent" /> cost (max{" "}
          {money(maxCost)})
        </span>
      </div>
      <svg
        data-testid="day-chart"
        role="img"
        aria-label={`Turns and cost per day over ${days.length} days`}
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        className="h-[220px] w-full min-w-[420px]"
      >
        <line
          x1={PLOT_LEFT}
          y1={PLOT_BOTTOM}
          x2={PLOT_RIGHT}
          y2={PLOT_BOTTOM}
          stroke="var(--color-rule)"
          strokeWidth="1"
        />
        {days.map((d, i) => {
          const centre = PLOT_LEFT + slot * (i + 0.5);
          const turnsH = (d.turns / maxTurns) * height;
          const costH = (d.cost_usd / maxCost) * height;
          const label = `${shortDate(d.date)} — ${d.turns} turns, ${money(d.cost_usd)}, p95 ${d.latency_p95_ms} ms`;
          return (
            <g key={d.date} data-testid="day-bar" data-date={d.date}>
              <rect
                x={centre - barW - 1}
                y={PLOT_BOTTOM - turnsH}
                width={barW}
                height={Math.max(turnsH, d.turns > 0 ? 2 : 0)}
                rx="2"
                fill="var(--color-primary)"
              >
                <title>{label}</title>
              </rect>
              <rect
                x={centre + 1}
                y={PLOT_BOTTOM - costH}
                width={barW}
                height={Math.max(costH, d.cost_usd > 0 ? 2 : 0)}
                rx="2"
                fill="var(--color-accent)"
              >
                <title>{label}</title>
              </rect>
              {i % labelEvery === 0 ? (
                <text
                  x={centre}
                  y={PLOT_BOTTOM + 16}
                  textAnchor="middle"
                  fontSize="11"
                  fill="var(--color-muted)"
                >
                  {shortDate(d.date)}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** A labelled horizontal bar: the share is the width, the count is the value. */
function BarRow({
  label,
  value,
  fraction,
  tone = "primary",
  testId,
}: {
  label: string;
  value: string;
  fraction: number;
  tone?: "primary" | "accent";
  testId: string;
}) {
  const width = `${Math.max(fraction * 100, fraction > 0 ? 1.5 : 0)}%`;
  return (
    <div data-testid={testId} data-label={label} className="grid grid-cols-[9rem_1fr_5rem] items-center gap-3">
      <span className="truncate text-meta text-ink-soft" title={label}>
        {label}
      </span>
      <span className="h-2.5 overflow-hidden rounded-full bg-primary-soft">
        <span
          className={`block h-full rounded-full ${tone === "accent" ? "bg-accent" : "bg-primary"}`}
          style={{ width }}
        />
      </span>
      <span className="text-right text-meta tabular-nums text-ink">{value}</span>
    </div>
  );
}

export default function DashboardPage() {
  const [days, setDays] = useState<ReportWindow>(7);
  const [data, setData] = useState<ReportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    getReportSummary(days)
      .then((d) => {
        if (!alive) return;
        setData(d);
        setError(null);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [days]);

  /**
   * The spinner flag is set here and cleared in the effect, never set inside it:
   * a synchronous setState in an effect body is a cascading render, and the last
   * window's numbers should stay on screen (dimmed) while the next one loads.
   */
  function selectWindow(next: ReportWindow) {
    if (next === days) return;
    setLoading(true);
    setDays(next);
  }

  const th = "px-3 py-2";

  return (
    <div
      className="mx-auto w-full max-w-[1100px] px-4 py-7 sm:px-6"
      data-testid="dashboard"
      data-days={data ? data.days : ""}
    >
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-title font-semibold">Reporting</h1>
          <p className="mt-1 text-meta text-muted">
            What the assistant did, what it cost, and what it could not answer.{" "}
            <span data-testid="dashboard-window">Last {days === 1 ? "24 hours" : `${days} days`}</span>.
          </p>
        </div>
        <div
          role="group"
          aria-label="Reporting window"
          data-testid="window-selector"
          className="inline-flex overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm"
        >
          {WINDOWS.map((w) => (
            <button
              key={w}
              type="button"
              data-testid={`window-${w}`}
              aria-pressed={days === w}
              onClick={() => selectWindow(w)}
              className={`px-3 py-1.5 text-meta font-medium transition-colors ${
                days === w
                  ? "bg-primary text-white"
                  : "text-primary hover:bg-primary-soft"
              }`}
            >
              {w} {w === 1 ? "day" : "days"}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <p
          role="alert"
          data-testid="dashboard-error"
          className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-meta text-red-700"
        >
          {error}
        </p>
      ) : null}

      {!data ? (
        <p className="text-meta text-muted">
          {loading ? "Loading the report…" : "No report to show."}
        </p>
      ) : (
        <div className={`space-y-5 ${loading ? "opacity-60" : ""}`}>
          {/* Eight tiles, because eight is what a staff reader can hold at once:
              volume, spend, speed, and the two ways a turn goes wrong. */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Kpi label="Turns" value={String(data.totals.turns)} />
            <Kpi label="Conversations" value={String(data.totals.sessions)} />
            <Kpi
              label="Cost"
              value={money(data.totals.cost_usd)}
              hint={
                data.totals.turns
                  ? `${money(data.totals.cost_usd / data.totals.turns)} a turn`
                  : undefined
              }
            />
            <Kpi label="Citation rate" value={percent(data.citation_rate)} hint="non-smalltalk turns" />
            <Kpi label="Latency p50" value={`${data.totals.latency_p50_ms} ms`} />
            <Kpi label="Latency p95" value={`${data.totals.latency_p95_ms} ms`} />
            <Kpi label="Error turns" value={String(data.totals.error_turns)} />
            <Kpi label="Fallback turns" value={String(data.totals.fallback_turns)} hint="apology reply" />
          </div>

          <Card
            title="Turns and cost by day"
            hint="Hover a bar for the day's exact turns, spend and p95 latency."
            testId="card-by-day"
          >
            <DayChart days={data.by_day} />
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Intents" hint="What residents asked about." testId="card-intents">
              {data.by_intent.length === 0 ? (
                <NoTurns />
              ) : (
                <div className="space-y-2">
                  {data.by_intent.map((r) => (
                    <BarRow
                      key={r.intent}
                      testId="intent-bar"
                      label={r.intent}
                      value={`${r.turns} · ${percent(r.share)}`}
                      fraction={r.share}
                    />
                  ))}
                </div>
              )}
            </Card>

            <Card title="Tiers" hint="Where the router sent the work, and its bill." testId="card-tiers">
              {data.by_tier.length === 0 ? (
                <NoTurns />
              ) : (
                <div className="space-y-2">
                  {data.by_tier.map((r) => (
                    <BarRow
                      key={r.tier}
                      testId="tier-bar"
                      label={r.tier}
                      value={`${r.turns} · ${money(r.cost_usd)}`}
                      fraction={data.totals.turns ? r.turns / data.totals.turns : 0}
                      tone="accent"
                    />
                  ))}
                </div>
              )}
            </Card>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card
              title="Tools"
              hint="Calls made, calls that returned an error, and the share answered by live City data."
              testId="card-tools"
            >
              {data.tools.length === 0 ? (
                <NoTurns what="tool calls" />
              ) : (
                <div className="overflow-x-auto">
                  <table
                    data-testid="tools-table"
                    className="data-table w-full border-collapse text-left text-meta"
                  >
                    <thead>
                      <tr>
                        <th className={th}>Tool</th>
                        <th className={`${th} text-right`}>Calls</th>
                        <th className={`${th} text-right`}>Errors</th>
                        <th className={`${th} text-right`}>Live</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.tools.map((t) => (
                        <tr key={t.name} className="border-t border-rule">
                          <td className="px-3 py-2 font-mono text-[12px] text-ink">{t.name}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{t.calls}</td>
                          <td
                            className={`px-3 py-2 text-right tabular-nums ${
                              t.errors ? "font-medium text-red-700" : "text-muted"
                            }`}
                          >
                            {t.errors}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {percent(t.live_share)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card
              title="Applications"
              hint="Filed in this window, by type and status."
              testId="card-applications"
            >
              {data.applications.by_type_status.length === 0 ? (
                <NoTurns what="applications" />
              ) : (
                <div className="overflow-x-auto">
                  <table
                    data-testid="applications-table"
                    className="data-table w-full border-collapse text-left text-meta"
                  >
                    <thead>
                      <tr>
                        <th className={th}>Type</th>
                        <th className={th}>Status</th>
                        <th className={`${th} text-right`}>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.applications.by_type_status.map((r) => (
                        <tr key={`${r.type}/${r.status}`} className="border-t border-rule">
                          <td className="px-3 py-2 text-ink">{r.type}</td>
                          <td className="px-3 py-2 text-ink-soft">{r.status}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{r.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="mt-3 text-meta text-muted" data-testid="applications-summary">
                Issued <span className="font-medium text-ink">{data.applications.issued}</span> ·
                Waiting on the resident{" "}
                <span className="font-medium text-ink">{data.applications.needs_info}</span> · Median
                time to review{" "}
                <span className="font-medium text-ink">
                  {data.applications.median_hours_to_review === null
                    ? "—"
                    : `${data.applications.median_hours_to_review} h`}
                </span>
              </p>
            </Card>
          </div>

          <Card
            title="Unanswered"
            hint="Recent questions with no sources behind the reply, or answered with the City's general line. This is the list of things to write into the knowledge base next."
            testId="card-unanswered"
          >
            {data.unanswered.length === 0 ? (
              <NoTurns what="unanswered questions" />
            ) : (
              <ul data-testid="unanswered-list" className="space-y-2.5">
                {data.unanswered.map((r, i) => (
                  <li
                    key={i}
                    data-testid="unanswered-row"
                    className="flex flex-wrap items-start gap-x-3 gap-y-1 border-b border-rule pb-2.5 last:border-0 last:pb-0"
                  >
                    <span
                      data-testid="unanswered-reason"
                      data-reason={r.reason}
                      className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${
                        r.reason === "declined"
                          ? "bg-amber-50 text-amber-800 ring-amber-300"
                          : "bg-slate-100 text-slate-700 ring-slate-300"
                      }`}
                    >
                      {r.reason === "declined" ? "declined" : "no sources"}
                    </span>
                    <span className="min-w-0 flex-1 text-meta text-ink">{r.message}</span>
                    <span className="shrink-0 text-meta text-muted">
                      {r.intent ?? "—"}
                      {r.created_at
                        ? ` · ${new Date(r.created_at).toLocaleString([], {
                            month: "short",
                            day: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                          })}`
                        : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
