/**
 * The client-side half of the staff session: one hook that asks the API who is
 * signed in and sends the browser to /login when the answer is 401.
 * Used by app/staff/layout.tsx, the console's single gate for /staff,
 * /staff/dashboard and /staff/traces. Depends on lib/api.
 *
 * The resident app has no caller: since M21 the chat page carries no staff
 * links, so nothing outside /staff asks who is signed in.
 */

"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ApiError, getMe, isUnauthorized, type StaffIdentity } from "@/lib/api";

export type StaffSession = {
  /** null while the first GET /api/auth/me is in flight. */
  staff: StaffIdentity | null;
  loading: boolean;
  /** True once we know nobody is signed in. */
  signedOut: boolean;
  /** The message from the last failed GET /api/auth/me; null after a success. */
  error: string | null;
  /**
   * True when that failure was "could not reach the API" (ApiError status 0)
   * rather than a 401. A 401 redirects; an unreachable API has no way out of
   * the loading state, so the pages render this as an error with a Retry.
   */
  unreachable: boolean;
  /** Re-ask the API — Nav calls it after signing out, Retry calls it too. */
  refresh: () => void;
};

/**
 * Ask the API who is signed in. `redirect` sends a signed-out visitor to
 * /login?next=<this page>; Nav passes false because the chat page is public.
 */
export function useStaffSession(redirect: boolean): StaffSession {
  const router = useRouter();
  const pathname = usePathname();
  const [staff, setStaff] = useState<StaffIdentity | null>(null);
  const [loading, setLoading] = useState(true);
  const [signedOut, setSignedOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    getMe()
      .then((who) => {
        if (!alive) return;
        setStaff(who);
        setSignedOut(false);
        setError(null);
        setUnreachable(false);
      })
      .catch((e) => {
        if (!alive) return;
        setStaff(null);
        setSignedOut(true);
        setError(e instanceof Error ? e.message : String(e));
        setUnreachable(e instanceof ApiError && e.status === 0);
        // Only a 401 means "sign in"; an API that is down should not bounce the
        // page, or a restart would look like a logout.
        if (redirect && isUnauthorized(e)) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // pathname is in the deps so the nav re-checks after login/logout navigation.
  }, [redirect, router, pathname, nonce]);

  /** Called from an event handler (Nav's Log out), never from an effect. */
  function refresh() {
    setLoading(true);
    setNonce((n) => n + 1);
  }

  return { staff, loading, signedOut, error, unreachable, refresh };
}
