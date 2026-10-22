/**
 * The nav a resident sees: the seal, the title, the honesty badge, the health
 * pill. No links, because `/` is the only page a resident has.
 * Rendered by components/SiteChrome. Depends on CitySeal and HealthPill.
 *
 * Why nothing else is here: until M21 this bar carried "Staff queue" and
 * "Traces" links that a resident could click and be bounced to a login form
 * they have no account for. The staff console has its own nav now, and the only
 * way in from the resident side is the quiet footer line under the chat.
 */

import Link from "next/link";
import CitySeal from "./CitySeal";
import HealthPill from "./HealthPill";

export default function ResidentNav() {
  return (
    <header className="bg-primary text-white shadow-sm">
      <div className="mx-auto flex w-full max-w-[1100px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5" data-testid="nav-home">
          <CitySeal size={30} onDark />
          <span className="leading-tight">
            <span className="block text-[15px] font-semibold tracking-tight">
              City of San Diego
            </span>
            <span className="block text-[11px] uppercase tracking-[0.12em] text-white/65">
              Virtual Assistant
            </span>
          </span>
        </Link>

        <span className="rounded-full border border-accent/50 bg-accent/15 px-2 py-0.5 text-[11px] font-medium tracking-wide text-amber-200">
          demo — fictional applications, live City map data
        </span>

        <div className="ml-auto flex items-center">
          <HealthPill />
        </div>
      </div>
    </header>
  );
}
