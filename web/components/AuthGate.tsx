"use client";

/**
 * What /staff and /traces render before they know who is signed in: a short
 * "checking" line normally, or the error plus a Retry when the API is down.
 * Rendered by app/staff/page.tsx and app/traces/page.tsx; depends on the
 * StaffSession shape from lib/auth.
 *
 * Why it exists: a 401 redirects to /login, but an unreachable API left both
 * pages saying "Checking your sign-in…" forever, with no error and no way out
 * short of a reload (hardening audit S2). The session hook now says which of
 * the two happened, and this is the branch for the second.
 */

import type { StaffSession } from "@/lib/auth";

export default function AuthGate({ session }: { session: StaffSession }) {
  const { loading, unreachable, error, refresh } = session;
  const wrapper = "mx-auto w-full max-w-[1100px] px-6 py-7";

  if (!loading && unreachable) {
    return (
      <div className={wrapper} data-testid="auth-error">
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-meta text-red-700"
        >
          {error ?? "The API is not answering."}
        </p>
        <button
          type="button"
          data-testid="auth-retry"
          onClick={refresh}
          className="mt-3 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-meta font-medium text-primary shadow-sm hover:border-primary hover:bg-primary-soft"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <p data-testid="auth-gate" className={`${wrapper} text-meta text-muted`}>
      Checking your sign-in…
    </p>
  );
}
