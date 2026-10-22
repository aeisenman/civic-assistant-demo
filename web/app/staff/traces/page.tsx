"use client";

/**
 * The last 100 turns, one row each: how the router decided and what it cost.
 * Row expands to the message, the reply, the tool-call JSON and the RAG chunks.
 * A staff console page, rendered inside app/staff/layout.tsx (which owns the
 * sign-in gate). Depends on lib/api.listTraces and on lib/health for the alias
 * -> real model map, so the Model column reads "smart · claude-sonnet-4-6".
 */

import { Fragment, useEffect, useState } from "react";
import { formatTime, listTraces, type Trace } from "@/lib/api";
import { modelLabel, useProviderModels } from "@/lib/health";
import MarkdownLite from "@/components/MarkdownLite";

/** Time only — the full timestamp is the cell's title, so the table stays narrow. */
function clock(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleTimeString();
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
        {title}
      </div>
      {children}
    </div>
  );
}

/**
 * The reply, rendered the way the resident saw it, with the raw text one click
 * away. DECISIONS.md 2026-09-03 made this a raw debugging view; on a projector
 * the literal `**Required fields:**` reads as a bug, so the rendered form is now
 * the default and the raw markdown is kept behind the toggle.
 */
function Reply({ text }: { text: string }) {
  const [raw, setRaw] = useState(false);
  return (
    <div>
      <div className="mb-1 flex items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
          Reply
        </span>
        <button
          type="button"
          data-testid="trace-raw-toggle"
          aria-pressed={raw}
          onClick={() => setRaw((r) => !r)}
          className={`rounded border px-1.5 py-px text-[10px] font-semibold uppercase tracking-[0.06em] ${
            raw
              ? "border-primary bg-primary-soft text-primary"
              : "border-slate-300 text-muted hover:border-primary hover:text-primary"
          }`}
        >
          raw
        </button>
      </div>
      {raw ? (
        <p className="whitespace-pre-wrap font-mono text-[12px] leading-5 text-ink-soft">
          {text}
        </p>
      ) : (
        <div className="text-ink">
          <MarkdownLite text={text} />
        </div>
      )}
    </div>
  );
}

export default function TracesPage() {
  // Traces are every resident message and reply; the console layout is the gate.
  const [traces, setTraces] = useState<Trace[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const models = useProviderModels();

  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    listTraces(100)
      .then((t) => {
        if (!alive) return;
        setTraces(t);
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
  }, [nonce]);

  /** Refresh re-runs the effect above; the flag is set here, not in the effect. */
  function refresh() {
    setLoading(true);
    setNonce((n) => n + 1);
  }

  // The table lives in a 1050px scroller. `max-w` and `truncate` on a <td> are
  // ignored under auto table layout, so the Model and Tools cells grew to their
  // full content and pushed Tokens/Latency/Cost past the right edge (issue 2);
  // the cap now sits on an inner <div>, and the cells are a notch tighter.
  const th = "px-2.5 py-2";
  const cell = "px-2.5 py-2";
  const num = "px-2.5 py-2 text-right tabular-nums";

  return (
    <div className="mx-auto w-full max-w-[1100px] px-4 py-7 sm:px-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-title font-semibold">Traces</h1>
          <p className="mt-1 text-meta text-muted">
            Every turn the assistant has taken: the intent it classified, the tier it routed to,
            the tools it called, and what the tokens cost. Click a row to open it.
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          data-testid="traces-refresh"
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-meta font-medium text-primary shadow-sm hover:border-primary hover:bg-primary-soft disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error ? (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-meta text-red-700"
        >
          {error}
        </p>
      ) : null}

      <div className="max-h-[72vh] overflow-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="data-table w-full min-w-[56rem] border-collapse text-left text-meta">
          <thead>
            <tr>
              <th className={th}>Time</th>
              <th className={th}>Intent</th>
              <th className={`${th} text-right`}>Conf.</th>
              <th className={th}>Tier</th>
              <th className={th}>Model</th>
              <th className={th}>Tools</th>
              <th className={`${th} text-right`}>Tokens</th>
              <th className={`${th} text-right`}>Latency</th>
              <th className={`${th} text-right`}>Cost</th>
              <th className={th}>Err</th>
            </tr>
          </thead>
          <tbody>
            {traces.length === 0 && !loading ? (
              <tr>
                <td colSpan={10} className="px-3 py-10 text-center text-muted">
                  No traces yet — ask the assistant something on the Chat page.
                </td>
              </tr>
            ) : null}
            {traces.map((t, i) => {
              const isOpen = open === t.id;
              return (
                <Fragment key={t.id}>
                  <tr
                    data-testid="trace-row"
                    data-open={isOpen}
                    tabIndex={0}
                    onClick={() => setOpen(isOpen ? null : (t.id ?? null))}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setOpen(isOpen ? null : (t.id ?? null));
                      }
                    }}
                    className={`cursor-pointer border-t border-rule transition-colors hover:bg-primary-soft ${
                      isOpen ? "bg-primary-soft" : i % 2 ? "bg-slate-50/70" : "bg-white"
                    }`}
                  >
                    <td
                      className={`${cell} whitespace-nowrap text-muted`}
                      title={formatTime(t.created_at)}
                    >
                      <span aria-hidden="true" className="mr-1.5 text-muted">
                        {isOpen ? "\u25be" : "\u25b8"}
                      </span>
                      {clock(t.created_at)}
                    </td>
                    <td className={`${cell} font-medium text-ink`}>{t.intent ?? "—"}</td>
                    <td className={num}>
                      {t.confidence != null ? t.confidence.toFixed(2) : "—"}
                    </td>
                    <td className={`${cell} text-ink-soft`}>{t.tier ?? "—"}</td>
                    <td className={cell} title={modelLabel(t.model, models)}>
                      <div className="max-w-[11rem] truncate font-mono text-[12px] text-ink-soft">
                        {modelLabel(t.model, models)}
                      </div>
                    </td>
                    <td
                      className={cell}
                      title={(t.tool_calls ?? []).map((c) => c.name).join(", ")}
                    >
                      <div className="max-w-[8rem] truncate font-mono text-[12px] text-ink-soft">
                        {(t.tool_calls ?? []).map((c) => c.name).join(", ") || "—"}
                      </div>
                    </td>
                    <td className={num}>
                      {t.prompt_tokens ?? 0}/{t.completion_tokens ?? 0}
                    </td>
                    <td className={`${num} whitespace-nowrap`}>{t.latency_ms ?? 0} ms</td>
                    <td className={num}>${(t.cost_usd ?? 0).toFixed(6)}</td>
                    <td className={`${cell} ${t.error ? "text-red-600" : "text-muted"}`}>
                      {t.error ? "yes" : "—"}
                    </td>
                  </tr>
                  {isOpen ? (
                    <tr data-testid="trace-detail" className="border-t border-rule bg-white">
                      <td colSpan={10} className="px-4 py-4">
                        {/* w-0 keeps this cell out of the table's intrinsic
                            width calculation, min-w-full still fills the row:
                            without it the JSON <pre> blocks stretched the table
                            to 1432px and hid Tokens/Latency/Cost (issue 2). */}
                        <div className="w-0 min-w-full space-y-3.5">
                          {t.error ? (
                            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-700">
                              {t.error}
                            </p>
                          ) : null}
                          {t.reason ? (
                            <Block title="Routing reason">
                              <p className="text-ink-soft">{t.reason}</p>
                            </Block>
                          ) : null}
                          <Block title="Message">
                            <p className="whitespace-pre-wrap text-ink">{t.message}</p>
                          </Block>
                          <Reply text={t.reply ?? ""} />
                          <Block title="Tool calls">
                            <pre
                              data-testid="trace-tool-json"
                              className="overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 p-2.5 font-mono text-[11px] leading-5 text-ink-soft"
                            >
                              {JSON.stringify(t.tool_calls ?? [], null, 2)}
                            </pre>
                          </Block>
                          <Block title="Model calls">
                            <pre className="overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 p-2.5 font-mono text-[11px] leading-5 text-ink-soft">
                              {JSON.stringify(t.calls ?? [], null, 2)}
                            </pre>
                          </Block>
                          <Block title="RAG chunk ids">
                            <p className="font-mono text-[11px] text-muted">
                              {(t.rag_chunk_ids ?? []).join(", ") || "none"}
                            </p>
                          </Block>
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
