"use client";

/**
 * GET /health, shared by everything that needs it and re-polled every 30 s.
 * Called by components/HealthPill, components/TracePanel and app/traces;
 * depends on lib/api.getHealth. The promise is cached at module scope so three
 * components mounting at once still make one request.
 */

import { useEffect, useState } from "react";
import { getHealth, type Health } from "@/lib/api";

/** How long a /health answer is treated as current, and the re-poll period. */
export const HEALTH_POLL_MS = 30_000;

let pending: Promise<Health> | null = null;
let fetchedAt = 0;

/**
 * The shared in-flight (or recent) /health promise; useHealth is the public door.
 *
 * Two things the first version got wrong: a *failed* promise stayed cached for
 * the life of the tab, so one blip pinned the pill to "API unreachable" until a
 * hard reload, and a *successful* one never expired, so a degrading API was
 * never noticed. Now a rejection clears the cache immediately and a success
 * expires after HEALTH_POLL_MS — still one request per window, however many
 * components ask.
 */
function loadHealth(): Promise<Health> {
  if (!pending || Date.now() - fetchedAt >= HEALTH_POLL_MS) {
    fetchedAt = Date.now();
    pending = getHealth().catch((e) => {
      pending = null;
      fetchedAt = 0;
      throw e;
    });
  }
  return pending;
}

export function useHealth(): { health: Health | null; failed: boolean } {
  const [health, setHealth] = useState<Health | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    const poll = () => {
      loadHealth()
        .then((h) => {
          if (!alive) return;
          setHealth(h);
          setFailed(false);
        })
        .catch(() => {
          if (!alive) return;
          // Keep the last good body on screen; only the flag flips, so the pill
          // says "unreachable" without losing what it knew.
          setFailed(true);
        });
    };
    poll();
    const timer = setInterval(poll, HEALTH_POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return { health, failed };
}

const NONE: Record<string, string> = {};

/**
 * Gateway alias -> the model that actually answered ("smart" -> "claude-sonnet-4-6").
 * Empty until /health lands, and empty on a provider that has no aliases.
 */
export function useProviderModels(): Record<string, string> {
  return useHealth().health?.provider_models ?? NONE;
}

/** "smart · claude-sonnet-4-6" when the alias resolves, else the bare alias. */
export function modelLabel(
  alias: string | null | undefined,
  models: Record<string, string>,
): string {
  if (!alias) return "—";
  const real = models[alias];
  return real ? `${alias} · ${real}` : alias;
}
