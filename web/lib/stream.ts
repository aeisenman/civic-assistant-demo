/**
 * POST /api/chat/stream as server-sent events, parsed with fetch + ReadableStream.
 * Called by app/page.tsx; depends on lib/api for API_URL, ApiError, the
 * ChatResponse type and postChat, the fallback for an API without the route.
 *
 * Not EventSource: that API can only GET, and a chat turn is a POST with a body.
 */

import { API_URL, ApiError, postChat, type ChatResponse } from "@/lib/api";

export type ChatStreamEvent =
  /** Routing is done: which intent, which tier, which model is answering. */
  | { type: "status"; intent?: string | null; tier?: string | null; model?: string | null }
  /** One tool call is being dispatched. `cached` means the turn already ran it. */
  | { type: "tool"; name: string; cached?: boolean }
  /** A piece of the final answer, in the order the model wrote it. */
  | { type: "token"; text: string }
  /** Always last: the whole ChatResponse body /api/chat would have returned. */
  | ({ type: "done" } & ChatResponse);

export type ChatBody = {
  session_id: string;
  message: string;
  document_ids?: number[];
};

/**
 * A finished turn. `connectionLost` marks the salvage case: the socket died
 * after tokens had arrived, so `reply` is however much of the answer got
 * through and there is no trace or citation list to show.
 */
export type ChatStreamResult = ChatResponse & { connectionLost?: boolean };

/** No answer can legitimately take this long; past it the socket is wedged. */
export const STREAM_TIMEOUT_MS = 90_000;

/** Statuses that mean "this API has no streaming route", nothing else. */
const NO_ROUTE = new Set([404, 405]);

/**
 * Stream one turn, calling `onEvent` as each event lands, and resolve with the
 * final ChatResponse.
 *
 * Three failure modes, deliberately told apart:
 *
 * - 404/405 — an older API without the route. Retry the whole turn buffered on
 *   POST /api/chat. Previously *any* non-200 did this, so a transient 500 re-ran
 *   the turn behind the resident's back: two model calls, two trace rows, double
 *   the spend, and no sign anything had gone wrong.
 * - any other non-200 — an ApiError carrying the status and the FastAPI
 *   `detail`, so a 429 from the cost breaker reads as itself in the bubble. A
 *   403 (this session id belongs to another browser, M20) is one of these on
 *   purpose: the recovery is to rotate the id and resend the whole turn, which
 *   only the caller can do, so `withSessionRetry` in lib/api.ts wraps this call
 *   rather than this function retrying itself with an id nobody else knows.
 * - a socket that dies mid-answer — resolve with what arrived and
 *   `connectionLost: true`. Throwing here made app/page.tsx delete the bubble,
 *   discarding a 90%-complete answer.
 */
export async function streamChat(
  body: ChatBody,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<ChatStreamResult> {
  // One ceiling for the whole turn, not per read: a server that dribbles one
  // token a minute is as broken as one that stops answering.
  const control = new AbortController();
  const ceiling = setTimeout(() => control.abort(), STREAM_TIMEOUT_MS);
  try {
    return await run(body, onEvent, control.signal);
  } finally {
    clearTimeout(ceiling);
  }
}

async function run(
  body: ChatBody,
  onEvent: (event: ChatStreamEvent) => void,
  signal: AbortSignal,
): Promise<ChatStreamResult> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/chat/stream`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch {
    // Nothing arrived, so there is nothing to salvage: DNS, refused connection,
    // or the ceiling firing before a single byte.
    throw new ApiError(`Cannot reach the API at ${API_URL}. Is it running?`, 0);
  }

  if (NO_ROUTE.has(res.status)) return postChat(body);
  if (!res.ok) throw new ApiError(await detailOf(res), res.status);
  // A 200 with no body is not a stream; the buffered route is the honest retry.
  if (!res.body) return postChat(body);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamed = "";
  let done: ChatResponse | null = null;

  try {
    for (;;) {
      const { value, done: finished } = await reader.read();
      if (finished) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE frames are separated by a blank line; a partial frame stays buffered.
      let split = buffer.indexOf("\n\n");
      while (split !== -1) {
        const frame = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        const line = frame.split("\n").find((l) => l.startsWith("data: "));
        if (line) {
          const event = JSON.parse(line.slice(6)) as ChatStreamEvent;
          onEvent(event);
          if (event.type === "token") streamed += event.text;
          if (event.type === "done") {
            // Named field by field, so `type` cannot leak into the ChatResponse.
            done = {
              reply: event.reply,
              citations: event.citations,
              actions: event.actions,
              trace: event.trace,
            };
          }
        }
        split = buffer.indexOf("\n\n");
      }
    }
  } catch {
    // Read error (dropped socket, or the 90 s ceiling aborting mid-answer).
    if (done) return done;
    return salvage(streamed);
  }

  if (done) return done;
  // Clean EOF with no `done` frame: the API hung up early. Same salvage rule.
  return salvage(streamed);
}

/** Keep a partial answer if there is one; otherwise this turn produced nothing. */
function salvage(streamed: string): ChatStreamResult {
  if (!streamed.trim()) {
    throw new ApiError("The answer stream ended before it was finished.", 0);
  }
  return { reply: streamed, citations: [], actions: [], trace: {}, connectionLost: true };
}

/** The FastAPI `detail` when there is one, else the status line. */
async function detailOf(res: Response): Promise<string> {
  try {
    const parsed = await res.json();
    if (parsed?.detail) {
      return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    }
  } catch {
    /* non-JSON body: keep the status line */
  }
  return `${res.status} ${res.statusText}`;
}
