"use client";

/**
 * Picks which chrome a route gets: the resident bar and footer, or nothing at
 * all under /staff, where app/staff/layout.tsx supplies the console's own nav.
 * Rendered by app/layout.tsx. Depends on components/ResidentNav.
 *
 * Why a client component and not two root layouts: the root layout is a server
 * component and cannot read the pathname, and splitting `/` and `/login` into a
 * route group would move files other milestones are editing. One `startsWith`
 * is the cheapest honest way to say "the console owns its own frame".
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import ResidentNav from "./ResidentNav";

export default function SiteChrome({ children }: { children: React.ReactNode }) {
  // /login keeps the resident chrome: a staff member arriving there has not
  // signed in yet, so the console nav would have nothing to show.
  const isConsole = usePathname().startsWith("/staff");
  if (isConsole) return <>{children}</>;

  return (
    <>
      <ResidentNav />
      <main className="flex w-full flex-1 flex-col">{children}</main>
      <footer className="shrink-0 border-t border-rule bg-page px-4 py-2.5 text-center sm:px-6">
        <Link
          href="/login"
          data-testid="footer-staff-login"
          className="text-meta text-muted hover:text-primary hover:underline"
        >
          City staff sign-in
        </Link>
      </footer>
    </>
  );
}
