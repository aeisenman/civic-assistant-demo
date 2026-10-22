/**
 * The resident's session id: a uuid in localStorage, created lazily in the
 * browser. Called by the chat page (and nothing else) — residents have no
 * account (staff sign-in is lib/auth.ts), so this id is the only thing tying a
 * conversation together. Depends on nothing.
 */

const KEY = "civic.session_id";

/**
 * A v4 uuid without `crypto.randomUUID`.
 *
 * `randomUUID` is gated on a secure context, and `deploy/aws/up.sh` publishes
 * plain http on a non-localhost host, so on the deployed demo it is simply
 * absent. `getRandomValues` has no such gate, so the fallback stays
 * cryptographically random rather than dropping to `Math.random`, whose output
 * an attacker who sees one id can predict for every other tab.
 */
function randomUuid(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function newId(): string {
  if (typeof crypto === "undefined") {
    // No Web Crypto at all: only reachable in a non-browser runtime, where the
    // id is never sent anywhere. A timestamp keeps the type honest.
    return `sess-${Date.now().toString(36)}`;
  }
  if ("randomUUID" in crypto) {
    try {
      return crypto.randomUUID();
    } catch {
      /* SecureContext refusal: fall through to getRandomValues */
    }
  }
  return randomUuid();
}

/**
 * localStorage throws, it does not return null, when the browser refuses it
 * (Safari private mode, "block all cookies", an iframe with storage
 * partitioned off). An unhandled throw here blanked the whole chat page, so
 * every access is guarded and a refusal simply means a per-tab session id.
 */
function read(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function write(id: string): void {
  try {
    window.localStorage.setItem(KEY, id);
  } catch {
    /* storage refused: the in-memory id below still holds for this page view */
  }
}

/** Survives a storage refusal so one page view keeps one session id. */
let memoryId: string | null = null;

/** Returns the stored id, creating one on first call. Client-side only. */
export function getSessionId(): string {
  if (typeof window === "undefined") return "";
  const stored = read();
  if (stored) return stored;
  if (!memoryId) memoryId = newId();
  write(memoryId);
  return memoryId;
}

/** "New conversation": mint a fresh id and return it. */
export function rotateSessionId(): string {
  const id = newId();
  memoryId = id;
  if (typeof window !== "undefined") write(id);
  return id;
}

/**
 * The 403 recovery path (M20): the API binds a session id to the browser that
 * first used it, and answers 403 for an id that belongs to someone else.
 *
 * That is reachable without anyone doing anything wrong — a session id copied
 * between browsers, or a cookie cleared while localStorage survived — and the
 * only way forward is a new id, so callers rotate and retry once. Same rotation
 * as "New conversation"; a separate name because the two call sites mean
 * different things and only one of them is the resident's choice.
 */
export function resetSession(): string {
  return rotateSessionId();
}
