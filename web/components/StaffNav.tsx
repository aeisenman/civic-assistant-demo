"use client";

/**
 * The staff console's own nav: the three console pages, who is signed in, and
 * Sign out. Rendered by app/staff/layout.tsx, which owns the session it is
 * handed. Depends on CitySeal, HealthPill and the StaffIdentity type in lib/api.
 *
 * The links are console-relative on purpose — there is no way back to the chat
 * from here except the browser's Back button and the seal, because a staff
 * member reading the queue is not half-way through a resident conversation.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { StaffIdentity } from "@/lib/api";
import CitySeal from "./CitySeal";
import HealthPill from "./HealthPill";

const LINKS = [
  { href: "/staff", label: "Queue", testId: "nav-queue" },
  { href: "/staff/dashboard", label: "Dashboard", testId: "nav-dashboard" },
  { href: "/staff/traces", label: "Traces", testId: "nav-traces" },
];

export default function StaffNav({
  staff,
  onSignOut,
}: {
  /** Null only in the moment before GET /api/auth/me answers. */
  staff: StaffIdentity | null;
  onSignOut: () => void;
}) {
  const pathname = usePathname();

  return (
    <header className="bg-primary-deep text-white shadow-sm">
      <div className="mx-auto flex w-full max-w-[1100px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/staff" className="flex items-center gap-2.5" data-testid="nav-home">
          <CitySeal size={30} onDark />
          <span className="leading-tight">
            <span className="block text-[15px] font-semibold tracking-tight">
              City of San Diego
            </span>
            <span className="block text-[11px] uppercase tracking-[0.12em] text-white/65">
              Staff console
            </span>
          </span>
        </Link>

        <nav aria-label="Staff console" className="flex flex-wrap items-center gap-x-5 gap-y-2">
          {LINKS.map((l) => {
            const active = pathname === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                data-testid={l.testId}
                className={`border-b-2 pb-0.5 text-meta font-medium transition-colors ${
                  active
                    ? "border-accent text-white"
                    : "border-transparent text-white/70 hover:text-white"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-2">
          {staff ? (
            <span className="flex items-center gap-2.5" data-testid="nav-staff-identity">
              <span className="text-meta text-white/80">
                Signed in as <span className="font-medium text-white">{staff.display_name}</span>
              </span>
              <button
                onClick={onSignOut}
                data-testid="logout-button"
                className="rounded-lg border border-white/30 px-2.5 py-1 text-meta font-medium text-white/85 transition-colors hover:border-white/60 hover:text-white"
              >
                Sign out
              </button>
            </span>
          ) : null}
          <HealthPill />
        </div>
      </div>
    </header>
  );
}
