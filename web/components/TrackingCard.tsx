/**
 * The "we filed it" card: tracking number, status, and a jump to the queue.
 * Rendered by the chat page for a submitted form and for an
 * application_created action. Depends on next/link and StatusPill.
 */

import Link from "next/link";
import StatusPill from "./StatusPill";

export default function TrackingCard({
  trackingNumber,
  status,
  note,
}: {
  trackingNumber: string;
  status?: string | null;
  note?: string | null;
}) {
  return (
    <div
      data-testid="tracking-card"
      className="mt-3 overflow-hidden rounded-xl border border-emerald-200 bg-white shadow-sm"
    >
      <div className="border-l-4 border-emerald-500 px-4 py-3.5">
        <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-emerald-700">
          Application filed
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-2.5">
          <span
            data-testid="tracking-number"
            className="font-mono text-[17px] font-semibold tracking-tight text-ink"
          >
            {trackingNumber}
          </span>
          <StatusPill status={status || "submitted"} />
        </div>
        {note ? <p className="mt-1.5 text-meta text-muted">{note}</p> : null}
        <Link
          href={`/staff?q=${encodeURIComponent(trackingNumber)}`}
          className="mt-2.5 inline-block text-meta font-medium text-primary hover:underline"
        >
          Track it in the staff queue →
        </Link>
      </div>
    </div>
  );
}
