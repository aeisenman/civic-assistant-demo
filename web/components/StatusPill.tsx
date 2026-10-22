/**
 * One coloured pill per workflow status, so the staff queue is scannable.
 * One hue per meaning: amber = waiting on the resident, blue = a human has it,
 * green = done, red = refused, gray = inert, indigo = still in the pipeline.
 * Rendered by the staff page and the tracking card. Unknown statuses go gray.
 */

const COLORS: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700 ring-slate-300",
  submitted: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  validating: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  routed: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  needs_info: "bg-amber-50 text-amber-800 ring-amber-300",
  in_review: "bg-blue-50 text-blue-700 ring-blue-200",
  approved: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  issued: "bg-emerald-50 text-emerald-800 ring-emerald-300",
  rejected: "bg-red-50 text-red-700 ring-red-200",
  closed: "bg-slate-100 text-slate-600 ring-slate-300",
};

export default function StatusPill({ status }: { status?: string | null }) {
  const key = (status || "").toLowerCase();
  const cls = COLORS[key] || "bg-slate-100 text-slate-700 ring-slate-300";
  return (
    <span
      data-testid="status-pill"
      data-status={key || "unknown"}
      className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-[12px] font-medium ring-1 ring-inset ${cls}`}
    >
      {status || "—"}
    </span>
  );
}
