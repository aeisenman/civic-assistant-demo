"use client";

/**
 * The old traces URL, kept alive as a redirect to /staff/traces (M21).
 * Reached only by a bookmark, a demo script or a link written before the staff
 * console got its own section. Depends on next/navigation.
 *
 * A client redirect rather than a `redirect()` in next.config: the route is a
 * courtesy for humans, and doing it in the page keeps the rule next to the page
 * it is about instead of in a config file nobody reads.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function TracesRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/staff/traces");
  }, [router]);

  return (
    <p data-testid="traces-redirect" className="mx-auto w-full max-w-[1100px] px-6 py-7 text-meta text-muted">
      Traces moved into the staff console. Taking you to <code>/staff/traces</code>…
    </p>
  );
}
