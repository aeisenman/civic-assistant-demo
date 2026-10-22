"use client";

/**
 * The back-office queue: every application in a sticky-header table, filterable,
 * polled so the worker's automatic transitions appear without a refresh; click a
 * row for a slide-in panel with fields, warnings, timeline and Advance actions.
 * The console root, rendered inside app/staff/layout.tsx (which owns the sign-in
 * gate). Depends on lib/api (applications endpoints) and components/StatusPill.
 */

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import StatusPill from "@/components/StatusPill";
import {
  advanceApplication,
  certificateUrl,
  formatFee,
  formatTime,
  getApplication,
  getForm,
  listApplications,
  type Application,
  type ApplicationDetail,
  type FormField,
} from "@/lib/api";

const STATUSES = [
  "draft",
  "submitted",
  "validating",
  "needs_info",
  "routed",
  "in_review",
  "approved",
  "rejected",
  "issued",
  "closed",
];
const TYPES = ["permit", "business_tax", "service_request", "stro"];
const POLL_MS = 5000;
/** The ceiling the backoff climbs to while the API keeps failing. */
const MAX_POLL_MS = 60_000;

/** The happy path gets the filled button; a refusal gets the red one. */
const HAPPY = new Set(["approved", "issued", "routed", "in_review", "closed"]);
const DESTRUCTIVE = new Set(["rejected"]);
const VERB: Record<string, string> = {
  submitted: "Submit",
  validating: "Re-validate",
  needs_info: "Request more info",
  routed: "Route",
  in_review: "Start review",
  approved: "Approve",
  rejected: "Reject",
  issued: "Issue certificate",
  closed: "Close",
};

/**
 * One GET /api/forms/{type} per application type per page load. The endpoint
 * returns the fields in pydantic declaration order, which is the order the
 * resident filled the form in — far more readable than the arbitrary key order
 * of the stored JSON blob.
 */
const FORM_FIELDS = new Map<string, FormField[]>();

type Row = { key: string; label: string; value: unknown };

// Words that read wrong in sentence case. Small on purpose: anything not listed
// is better shown as an ordinary word than shouted.
const ACRONYMS = new Set(["apn", "zip", "id", "url", "ein", "pdf"]);

/**
 * `council_district` -> "Council district", `apn` -> "APN".
 *
 * Some fields are added by the tools rather than declared on the pydantic form
 * schema, so they have no label to borrow and used to render as the raw key
 * beside properly labelled ones (2026-09-07 verification, issue 7).
 */
function humanise(key: string): string {
  const words = key.split(/[_\s]+/).filter(Boolean);
  if (words.length === 0) return key;
  return words
    .map((w, i) =>
      ACRONYMS.has(w.toLowerCase())
        ? w.toUpperCase()
        : i === 0
          ? w.charAt(0).toUpperCase() + w.slice(1)
          : w,
    )
    .join(" ");
}

/** Schema order (with the form's labels) first; any extra keys after it, A-Z. */
function orderedFields(
  fields: Record<string, unknown> | null | undefined,
  schema: FormField[] | undefined,
): Row[] {
  const values = fields ?? {};
  const rows: Row[] = [];
  const seen = new Set<string>();
  for (const f of schema ?? []) {
    if (!(f.name in values)) continue;
    seen.add(f.name);
    rows.push({ key: f.name, label: f.label || humanise(f.name), value: values[f.name] });
  }
  for (const k of Object.keys(values)
    .filter((k) => !seen.has(k))
    .sort()) {
    rows.push({ key: k, label: humanise(k), value: values[k] });
  }
  return rows;
}

/**
 * A tick that runs until told to stop. `cancelled()` goes true when the effect
 * is torn down, so a late response cannot overwrite fresher state; a rejection
 * is the signal to back off.
 */
type Tick = (cancelled: () => boolean) => Promise<void>;

/**
 * Run `tick` now and then on a self-scheduling timer. Null means "not yet".
 *
 * Three fixes over the plain setInterval this replaces (hardening audit S4):
 * a hidden tab stops polling entirely — the queue is not being watched, so five
 * requests a minute per backgrounded tab are pure waste; a slow response can no
 * longer overlap the next tick, which used to queue requests up behind a stalled
 * API; and each consecutive failure doubles the delay to MAX_POLL_MS, so an API
 * that is down is asked once a minute rather than twelve times, with the first
 * success snapping straight back to POLL_MS.
 */
function usePoll(tick: Tick | null) {
  useEffect(() => {
    if (!tick) return;
    let alive = true;
    let running = false;
    let delay = POLL_MS;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const schedule = () => {
      if (alive) timer = setTimeout(run, delay);
    };

    const run = async () => {
      if (!alive) return;
      // A hidden tab or a still-running request: wait for the next slot rather
      // than skip the schedule, or polling would stop for good.
      if (document.hidden || running) {
        schedule();
        return;
      }
      running = true;
      try {
        await tick(() => !alive);
        delay = POLL_MS;
      } catch {
        delay = Math.min(delay * 2, MAX_POLL_MS);
      } finally {
        running = false;
        schedule();
      }
    };

    run();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [tick]);
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-rule px-5 py-4 first:border-t-0">
      <h3 className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
        {title}
      </h3>
      {children}
    </section>
  );
}

function StaffQueue() {
  const params = useSearchParams();

  const [rows, setRows] = useState<Application[]>([]);
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [search, setSearch] = useState((params.get("q") || "").trim());
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  // The row that opened the drawer, so focus can go back to it on close.
  const opener = useRef<HTMLTableRowElement | null>(null);
  const panel = useRef<HTMLElement | null>(null);
  const focusedFor = useRef<number | null>(null);

  function fail(e: unknown) {
    setError(e instanceof Error ? e.message : String(e));
  }

  // Poll while the page is open: the worker advances rows every few seconds.
  const listTick = useCallback<Tick>(
    async (cancelled) => {
      try {
        const r = await listApplications({
          status: status || undefined,
          type: type || undefined,
          limit: 200,
        });
        if (cancelled()) return;
        setRows(r);
        setError(null);
      } catch (e) {
        if (!cancelled()) fail(e);
        throw e; // usePoll reads the rejection as "slow down".
      }
    },
    [status, type],
  );
  // app/staff/layout.tsx does not render this page until the session is known,
  // so the first tick already carries the cookie.
  usePoll(listTick);

  // The selected row is polled too, so its timeline grows in front of you.
  const detailTick = useCallback<Tick>(
    async (cancelled) => {
      if (selected == null) return;
      try {
        const d = await getApplication(selected);
        if (!cancelled()) setDetail(d);
      } catch (e) {
        if (!cancelled()) fail(e);
        throw e;
      }
    },
    [selected],
  );
  usePoll(selected == null ? null : detailTick);

  // Fetch the form schema for whatever type is on screen; cached per type, so a
  // second application of the same type costs nothing. A failure just leaves the
  // fields in raw key order rather than blanking the panel.
  const [, setSchemaLoaded] = useState(0);
  const detailType = detail?.type;
  useEffect(() => {
    if (!detailType || FORM_FIELDS.has(detailType)) return;
    let alive = true;
    getForm(detailType)
      .then((schema) => {
        FORM_FIELDS.set(detailType, schema.fields ?? []);
        if (alive) setSchemaLoaded((n) => n + 1);
      })
      .catch(() => {
        /* raw key order is a fine fallback */
      });
    return () => {
      alive = false;
    };
  }, [detailType]);

  function select(id: number, row?: HTMLTableRowElement | null) {
    if (selected === id) {
      close();
    } else {
      opener.current = row ?? null;
      setSelected(id);
      setNote("");
    }
  }

  function close() {
    setSelected(null);
    setDetail(null);
    setNote("");
    // Back where the keyboard user was, not at the top of the document.
    opener.current?.focus();
    opener.current = null;
  }

  // Escape is the one shortcut a modal must have. The backdrop is decorative
  // now: a focusable bare <button> sat between the table and the panel in the
  // tab order and announced nothing useful.
  useEffect(() => {
    if (selected == null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selected]);

  // Move focus into the panel once, when it first renders for this application.
  // The detail arrives a fetch after the click and is re-fetched every POLL_MS,
  // so the guard stops the poll stealing focus back every five seconds.
  useEffect(() => {
    if (!detail) {
      focusedFor.current = null;
      return;
    }
    if (focusedFor.current === detail.id) return;
    focusedFor.current = detail.id;
    panel.current?.focus();
  }, [detail]);

  // ?q=PRM-2026-000412 from the chat's tracking card prefilters the table.
  const visible = search
    ? rows.filter((r) => r.tracking_number?.toLowerCase().includes(search.toLowerCase()))
    : rows;

  async function advance(to: string) {
    if (detail == null) return;
    setBusy(true);
    try {
      await advanceApplication(detail.id, to, note.trim() || undefined);
      // POST /advance returns the row without events or allowed_transitions,
      // so re-read the detail rather than render a half-empty panel.
      setDetail(await getApplication(detail.id));
      setNote("");
      // Re-read the table now rather than wait out POLL_MS: the row the user
      // just advanced is the one they are looking at. A failure here has
      // already been reported by the tick itself.
      await listTick(() => false).catch(() => {});
      setError(null);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }

  const controlCls =
    "rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-meta text-ink focus:border-primary focus:outline-none";
  const th = "px-3 py-2";

  return (
    <div className="mx-auto w-full max-w-[1100px] px-4 py-7 sm:px-6">
      <div className="mb-5">
        <h1 className="text-title font-semibold">Staff queue</h1>
        <p className="mt-1 text-meta text-muted">
          Every application, newest first. Automatic transitions land here within seconds — the
          table refreshes itself every 5 s.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <label className="flex items-center gap-2 text-meta text-muted">
          <span>Status</span>
          <select
            data-testid="filter-status"
            className={controlCls}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-meta text-muted">
          <span>Type</span>
          <select
            data-testid="filter-type"
            className={controlCls}
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="">All</option>
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-meta text-muted">
          <span className="sr-only sm:not-sr-only">Tracking</span>
          <input
            data-testid="filter-search"
            className={`${controlCls} w-44 font-mono`}
            placeholder="PRM-2026-…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <span className="ml-auto text-meta text-muted" data-testid="row-count">
          {visible.length} application{visible.length === 1 ? "" : "s"}
        </span>
      </div>

      {error ? (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-meta text-red-700"
        >
          {error}
        </p>
      ) : null}

      <div className="max-h-[68vh] overflow-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="data-table w-full min-w-[54rem] border-collapse text-left text-meta">
          <thead>
            <tr>
              <th className={th}>Tracking</th>
              <th className={th}>Type</th>
              <th className={th}>Status</th>
              <th className={th}>Department</th>
              <th className={`${th} text-right`}>Fee</th>
              <th className={`${th} text-right`}>Missing</th>
              <th className={th}>Updated</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-10 text-center text-muted">
                  No applications match these filters.
                </td>
              </tr>
            ) : (
              visible.map((r, i) => (
                <tr
                  key={r.id}
                  data-testid="staff-row"
                  data-status={r.status}
                  data-tracking={r.tracking_number}
                  tabIndex={0}
                  onClick={(e) => select(r.id, e.currentTarget)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      select(r.id, e.currentTarget);
                    }
                  }}
                  className={`cursor-pointer border-t border-rule transition-colors hover:bg-primary-soft ${
                    selected === r.id
                      ? "bg-primary-soft"
                      : i % 2
                        ? "bg-slate-50/70"
                        : "bg-white"
                  }`}
                >
                  <td className="px-3 py-2.5 font-mono font-medium text-ink">
                    {r.tracking_number}
                  </td>
                  <td className="px-3 py-2.5 text-ink-soft">{r.type}</td>
                  <td className="px-3 py-2.5">
                    <StatusPill status={r.status} />
                  </td>
                  <td className="px-3 py-2.5 text-ink-soft">{r.department || "—"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{formatFee(r.fee_cents)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {(r.missing_fields ?? []).length}
                  </td>
                  <td className="px-3 py-2.5 text-muted">{formatTime(r.updated_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {detail ? (
        <div className="fixed inset-0 z-40 flex justify-end">
          <button
            tabIndex={-1}
            aria-hidden="true"
            onClick={close}
            className="flex-1 cursor-default bg-slate-900/20"
          />
          <aside
            ref={panel}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-labelledby="detail-heading"
            data-testid="detail-panel"
            className="flex w-full max-w-[480px] flex-col border-l border-slate-200 bg-white shadow-2xl focus:outline-none"
          >
            <div className="shrink-0 border-b border-rule bg-white px-5 py-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2
                    id="detail-heading"
                    className="font-mono text-section font-semibold tracking-tight"
                  >
                    {detail.tracking_number}
                  </h2>
                  <div className="mt-1.5 flex items-center gap-2">
                    <StatusPill status={detail.status} />
                    <span className="text-meta text-muted">{detail.type}</span>
                  </div>
                </div>
                <button
                  onClick={close}
                  data-testid="detail-close"
                  aria-label="Close detail panel"
                  className="rounded-lg px-2 py-1 text-meta font-medium text-muted hover:bg-slate-100 hover:text-ink"
                >
                  Close
                </button>
              </div>
            </div>

            {/* The body scrolls on its own so the Actions bar below can never
                sit on top of the timeline. */}
            <div data-testid="detail-body" className="min-h-0 flex-1 overflow-y-auto">
              <Section title="Fields">
                <dl className="text-meta">
                  {orderedFields(detail.fields, FORM_FIELDS.get(detail.type)).map(
                    ({ key, label, value }) => (
                      <div
                        key={key}
                        data-testid="detail-field"
                        data-field={key}
                        className="flex gap-3 border-b border-rule py-1.5 last:border-0"
                      >
                        <dt className="w-40 shrink-0 text-muted">{label}</dt>
                        <dd className="min-w-0 break-words text-ink">
                          {value === null || value === undefined || value === "" ? (
                            <span className="text-muted">—</span>
                          ) : typeof value === "object" ? (
                            JSON.stringify(value)
                          ) : (
                            String(value)
                          )}
                        </dd>
                      </div>
                    ),
                  )}
                  {Object.keys(detail.fields ?? {}).length === 0 ? (
                    <p className="text-muted">No fields captured.</p>
                  ) : null}
                </dl>
                <p className="mt-3 text-meta text-muted">
                  Fee <span className="font-medium text-ink">{formatFee(detail.fee_cents)}</span> ·
                  Department{" "}
                  <span className="font-medium text-ink">{detail.department || "unassigned"}</span>
                </p>
              </Section>

              <Section title="Warnings">
                {(detail.warnings ?? []).length === 0 &&
                (detail.missing_fields ?? []).length === 0 ? (
                  <p className="text-meta text-muted">None — the validator was happy.</p>
                ) : null}
                {(detail.warnings ?? []).length > 0 ? (
                  <ul className="space-y-1.5 rounded-lg border border-amber-200 bg-amber-50 p-3 text-meta text-amber-900">
                    {(detail.warnings ?? []).map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                ) : null}
                {(detail.missing_fields ?? []).length > 0 ? (
                  <div className="mt-2.5 rounded-lg border border-red-200 bg-red-50 p-3 text-meta text-red-800">
                    <div className="font-semibold">Missing fields</div>
                    <ul className="mt-1 list-inside list-disc">
                      {(detail.missing_fields ?? []).map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </Section>

              <Section title="Timeline">
                <ol className="space-y-3 border-l border-rule pl-4 text-meta">
                  {(detail.events ?? []).map((e, i) => (
                    <li key={i} className="relative">
                      <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-primary ring-2 ring-white" />
                      <div className="text-ink">
                        <span className="text-muted">{e.from_status || "—"}</span> →{" "}
                        <span className="font-medium">{e.to_status}</span>
                      </div>
                      <div className="text-muted">
                        {e.actor || "system"} · {formatTime(e.created_at)}
                      </div>
                      {e.note ? <div className="text-ink-soft">{e.note}</div> : null}
                    </li>
                  ))}
                  {(detail.events ?? []).length === 0 ? (
                    <li className="text-muted">No events yet.</li>
                  ) : null}
                </ol>
                </Section>
            </div>

            <div className="shrink-0 border-t border-rule bg-white">
              <Section title="Actions">
                {(detail.allowed_transitions ?? []).length > 0 ? (
                  <label className="mb-3 block text-meta text-muted">
                    <span className="mb-1 block">Note (optional, saved on the timeline)</span>
                    <input
                      data-testid="advance-note"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="e.g. Plans checked, structural OK"
                      className={`${controlCls} w-full`}
                    />
                  </label>
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  {(detail.allowed_transitions ?? []).map((t) => {
                    const style = DESTRUCTIVE.has(t)
                      ? "bg-red-600 text-white hover:bg-red-700 shadow-sm"
                      : HAPPY.has(t)
                        ? "bg-primary text-white hover:bg-primary-hover shadow-sm"
                        : "border border-slate-300 bg-white text-primary hover:border-primary hover:bg-primary-soft";
                    return (
                      <button
                        key={t}
                        disabled={busy}
                        data-testid={`advance-${t}`}
                        data-advance-to={t}
                        onClick={() => advance(t)}
                        className={`rounded-lg px-3 py-1.5 text-meta font-semibold transition-colors disabled:opacity-50 ${style}`}
                      >
                        {VERB[t] ?? t}
                      </button>
                    );
                  })}
                  {(detail.allowed_transitions ?? []).length === 0 ? (
                    <span className="text-meta text-muted">
                      No manual transitions from this status.
                    </span>
                  ) : null}
                </div>
                {detail.certificate_s3_key ? (
                  <a
                    href={certificateUrl(detail.id)}
                    target="_blank"
                    rel="noreferrer"
                    data-testid="certificate-link"
                    className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-meta font-semibold text-emerald-800 hover:bg-emerald-100"
                  >
                    <span aria-hidden="true">↓</span> Download certificate (PDF)
                  </a>
                ) : null}
              </Section>
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}

export default function StaffPage() {
  // useSearchParams needs a Suspense boundary for the static prerender.
  return (
    <Suspense
      fallback={
        <p className="mx-auto w-full max-w-[1100px] px-6 py-7 text-meta text-muted">
          Loading queue…
        </p>
      }
    >
      <StaffQueue />
    </Suspense>
  );
}
