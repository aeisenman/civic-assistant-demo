"use client";

/**
 * The staff console's frame: its nav, and the one sign-in gate for every page
 * under /staff. Wraps app/staff/page.tsx, /staff/dashboard and /staff/traces.
 * Depends on lib/auth (the session hook), lib/api (logout) and components/
 * StaffNav + AuthGate.
 *
 * The gate lives here rather than in each page so there is exactly one
 * GET /api/auth/me per console page load and exactly one place that decides
 * what an unauthenticated or unreachable API looks like.
 */

import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import StaffNav from "@/components/StaffNav";
import { logout } from "@/lib/api";
import { useStaffSession } from "@/lib/auth";

export default function StaffLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  // true: a signed-out visitor is sent to /login?next=<this console page>.
  const session = useStaffSession(true);
  const { staff } = session;

  async function signOut() {
    try {
      await logout();
    } finally {
      session.refresh();
      router.push("/");
    }
  }

  return (
    <>
      <StaffNav staff={staff} onSignOut={signOut} />
      <main className="flex w-full flex-1 flex-col">
        {/* Nothing renders until the API says who is signed in: a 401 has
            already redirected, and an unreachable API gets an error and a
            Retry rather than a spinner that never ends. */}
        {staff ? children : <AuthGate session={session} />}
      </main>
    </>
  );
}
