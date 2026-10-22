"use client";

/**
 * Numbered citation chips under an assistant reply; clicking one expands the
 * quoted chunk and links to the source page.
 * Rendered by the chat page. Depends on the Citation type in lib/api.
 */

import { useState } from "react";
import type { Citation } from "@/lib/api";

export default function Citations({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState<number | null>(null);
  if (citations.length === 0) return null;

  return (
    <div className="mt-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-meta text-muted">Sources</span>
        {citations.map((c) => (
          <button
            key={`${c.n}-${c.chunk_id ?? ""}`}
            data-testid="citation-chip"
            aria-expanded={open === c.n}
            aria-label={`Source ${c.n}${c.doc_title ? `: ${c.doc_title}` : ""}`}
            onClick={() => setOpen(open === c.n ? null : c.n)}
            className={`rounded-full px-2 py-0.5 text-[12px] font-medium ring-1 ring-inset transition-colors ${
              open === c.n
                ? "bg-primary text-white ring-primary"
                : "bg-primary-soft text-primary ring-slate-200 hover:ring-primary"
            }`}
            title={c.doc_title ?? undefined}
          >
            [{c.n}]{c.implicit ? "*" : ""}
          </button>
        ))}
        {citations.some((c) => c.implicit) ? (
          <span className="text-meta text-muted">* used, not explicitly cited</span>
        ) : null}
      </div>
      {citations
        .filter((c) => c.n === open)
        .map((c) => (
          <div
            key={`open-${c.n}`}
            data-testid="citation-detail"
            className="mt-2 rounded-lg border border-rule bg-slate-50 p-3 text-meta"
          >
            <div className="font-semibold text-ink">{c.doc_title || "Knowledge base"}</div>
            <p className="mt-1 whitespace-pre-wrap text-muted">{c.text}</p>
            {c.source_url ? (
              <a
                href={c.source_url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-block font-medium text-primary hover:underline"
              >
                {c.source_url}
              </a>
            ) : null}
          </div>
        ))}
    </div>
  );
}
