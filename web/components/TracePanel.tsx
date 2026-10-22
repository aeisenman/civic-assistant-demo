"use client";

/**
 * "Show your work": the trace behind one assistant reply, as an inline panel
 * the resident expands under the answer — a monospace key/value grid for the
 * routing decision, then the tool calls, the per-model costs and the RAG hits.
 * Rendered by the chat page. Depends on the Trace type in lib/api — every
 * field is optional so a failed turn still renders — and on lib/health for the
 * alias -> real model map, so "smart" reads as "smart · claude-sonnet-4-6".
 */

import type { Trace } from "@/lib/api";
import { modelLabel, useProviderModels } from "@/lib/health";

function Kv({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <>
      <dt className="py-1 pr-3 text-muted">{label}</dt>
      <dd className="min-w-0 break-words py-1 text-ink">{value}</dd>
    </>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
      {children}
    </h4>
  );
}

export default function TracePanel({ trace }: { trace: Trace }) {
  const calls = trace.calls ?? [];
  const tools = trace.tool_calls ?? [];
  const models = useProviderModels();

  return (
    <div
      data-testid="trace-panel"
      className="mt-2 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4"
    >
      {trace.error ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-meta text-red-700">
          {trace.error}
        </p>
      ) : null}

      <section>
        <Heading>Routing</Heading>
        <dl className="grid grid-cols-[6.5rem_minmax(0,1fr)] font-mono text-[12px] leading-5">
          <Kv label="Intent" value={trace.intent ?? "—"} />
          <Kv
            label="Confidence"
            value={trace.confidence != null ? trace.confidence.toFixed(2) : "—"}
          />
          <Kv label="Tier" value={trace.tier ?? "—"} />
          <Kv label="Model" value={modelLabel(trace.model, models)} />
          <Kv label="Latency" value={`${trace.latency_ms ?? 0} ms`} />
          <Kv
            label="Tokens"
            value={`${trace.prompt_tokens ?? 0} in / ${trace.completion_tokens ?? 0} out`}
          />
          <Kv label="Cost" value={`$${(trace.cost_usd ?? 0).toFixed(6)}`} />
          <Kv
            label="Reason"
            value={<span className="font-sans">{trace.reason || "—"}</span>}
          />
        </dl>
      </section>

      <section>
        <Heading>Tool calls ({tools.length})</Heading>
        {tools.length === 0 ? (
          <p className="text-meta text-muted">None — answered from the knowledge base.</p>
        ) : (
          <ul className="space-y-2">
            {tools.map((t, i) => (
              <li
                key={i}
                data-testid="tool-call"
                className="rounded-lg border border-slate-200 bg-white p-2.5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[12px] font-semibold text-primary">
                    {t.name}
                  </span>
                  {t.source ? (
                    <span
                      data-testid="tool-source"
                      className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                        t.source === "live"
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-slate-100 text-muted"
                      }`}
                    >
                      {t.source}
                      {t.match ? ` · ${t.match}` : ""}
                    </span>
                  ) : null}
                </div>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2 font-mono text-[11px] text-muted">
                  {JSON.stringify(t.arguments ?? {}, null, 2)}
                </pre>
                {t.result_summary ? (
                  <div className="mt-1 text-meta text-ink-soft">{t.result_summary}</div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {calls.length > 0 ? (
        <section>
          <Heading>Model calls ({calls.length})</Heading>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full min-w-[26rem] text-left font-mono text-[11px]">
              <thead className="bg-white text-muted">
                <tr className="border-b border-rule">
                  <th className="px-2 py-1 font-medium">tier</th>
                  <th className="px-2 py-1 font-medium">model</th>
                  <th className="px-2 py-1 text-right font-medium">in</th>
                  <th className="px-2 py-1 text-right font-medium">out</th>
                  <th className="px-2 py-1 text-right font-medium">ms</th>
                  <th className="px-2 py-1 text-right font-medium">cost</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((c, i) => (
                  <tr key={i} className="border-t border-rule">
                    <td className="px-2 py-1">{c.tier ?? "—"}</td>
                    <td className="px-2 py-1">{modelLabel(c.model, models)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{c.prompt_tokens ?? 0}</td>
                    <td className="px-2 py-1 text-right tabular-nums">
                      {c.completion_tokens ?? 0}
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums">{c.latency_ms ?? 0}</td>
                    <td className="px-2 py-1 text-right tabular-nums">
                      ${(c.cost_usd ?? 0).toFixed(6)}
                    </td>
                  </tr>
                ))}
                <tr className="border-t-2 border-slate-300 font-semibold">
                  <td className="px-2 py-1">total</td>
                  <td className="px-2 py-1">—</td>
                  <td className="px-2 py-1 text-right tabular-nums">{trace.prompt_tokens ?? 0}</td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    {trace.completion_tokens ?? 0}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">{trace.latency_ms ?? 0}</td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    ${(trace.cost_usd ?? 0).toFixed(6)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section>
        <Heading>RAG chunks</Heading>
        <p className="font-mono text-[11px] text-muted">
          {(trace.rag_chunk_ids ?? []).join(", ") || "none"}
        </p>
      </section>
    </div>
  );
}
