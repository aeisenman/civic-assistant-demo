"use client";

/**
 * The route-level error boundary: what a resident sees when a page component
 * throws. Rendered by Next in place of the page; app/layout.tsx still wraps it,
 * so the nav, the health pill and the sign-in state all survive. Depends on
 * nothing but React.
 *
 * Without this file any render throw produced Next's bare production error
 * page — no nav, no health pill, no way back except the browser's back button
 * (hardening audit S3).
 */

import { useEffect } from "react";

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Next has already logged this server-side; the browser console is where
    // the author looks during a demo.
    console.error("Page error:", error);
  }, [error]);

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-10" data-testid="route-error">
      <h1 className="text-title font-semibold">This page hit an error</h1>
      <p className="mt-2 text-body text-muted">
        The rest of the site still works — the nav above will take you somewhere else.
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
        data-testid="route-error-retry"
        onClick={reset}
        className="mt-4 rounded-lg bg-primary px-4 py-2 text-meta font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover"
      >
        Retry
      </button>
    </div>
  );
}
