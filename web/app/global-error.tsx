"use client";

/**
 * The last-resort boundary: a throw in app/layout.tsx itself, which is the one
 * case app/error.tsx cannot catch. Rendered by Next *instead of* the root
 * layout, so it must supply its own <html> and <body>. Depends on
 * app/globals.css for the design tokens.
 *
 * The real nav cannot be reused here — it is a child of the layout that just
 * failed, so rendering it risks throwing again inside the boundary. A static
 * navy bar with a link home keeps the page recognisably the City's.
 */

import "./globals.css";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex h-full flex-col bg-page text-ink">
        <header className="bg-primary text-white shadow-sm">
          <div className="mx-auto w-full max-w-[1100px] px-6 py-3">
            {/* A plain anchor on purpose: next/link navigates on the client
                through the very router tree that just threw, so the only thing
                that reliably works here is a full page load. */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a href="/" className="text-[15px] font-semibold tracking-tight">
              City of San Diego
            </a>
            <span className="ml-2 text-[11px] uppercase tracking-[0.12em] text-white/65">
              Virtual Assistant
            </span>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[760px] flex-1 px-6 py-10" data-testid="global-error">
          <h1 className="text-title font-semibold">The application failed to start</h1>
          <p className="mt-2 text-body text-muted">
            Something went wrong before any page could render.
          </p>
          <p
            role="alert"
            className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 font-mono text-meta text-red-700"
          >
            {error.message || "Unknown error"}
            {error.digest ? ` (${error.digest})` : ""}
          </p>
          <button
            type="button"
            data-testid="global-error-retry"
            onClick={reset}
            className="mt-4 rounded-lg bg-primary px-4 py-2 text-meta font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover"
          >
            Retry
          </button>
        </main>
      </body>
    </html>
  );
}
