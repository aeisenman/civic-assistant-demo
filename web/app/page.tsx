"use client";

/**
 * The resident chat: an empty state with quick actions, a composer with an
 * attachment, replies that stream in token by token with citations, an inline
 * application form, and an expandable trace panel per answer.
 * The only page a resident sees. Depends on lib/stream (the SSE turn), lib/api,
 * lib/health, lib/session and the components in components/.
 */

import { useEffect, useRef, useState } from "react";
import Citations from "@/components/Citations";
import CitySeal from "@/components/CitySeal";
import InlineForm from "@/components/InlineForm";
import MarkdownLite from "@/components/MarkdownLite";
import TracePanel from "@/components/TracePanel";
import TrackingCard from "@/components/TrackingCard";
import {
  uploadDocument,
  withSessionRetry,
  type Application,
  type ChatAction,
  type Citation,
  type FormSchema,
  type Trace,
  type UploadedDocument,
} from "@/lib/api";
import { modelLabel, useProviderModels } from "@/lib/health";
import { getSessionId, rotateSessionId } from "@/lib/session";
import { streamChat, type ChatStreamEvent } from "@/lib/stream";

type Message = {
  id: number;
  role: "user" | "assistant" | "system";
  text: string;
  at: number;
  attachment?: string;
  citations?: Citation[];
  trace?: Trace;
  formType?: string;
  formSchema?: FormSchema | null;
  tracking?: { number: string; status?: string | null; note?: string | null };
  /** True while the answer is still arriving; `status` is the line above it. */
  streaming?: boolean;
  status?: string;
  /** The socket died mid-answer: `text` is as far as the model got. */
  incomplete?: boolean;
};

const QUICK_ACTIONS: { label: string; message: string; formHint?: string }[] = [
  { label: "Apply for a permit", message: "I want to apply for a permit", formHint: "permit" },
  {
    label: "Start a business",
    message: "I want to start a business and get a business tax certificate",
    formHint: "business_tax",
  },
  {
    label: "Apply for a short-term rental license",
    message: "I want to apply for a short-term rental (STRO) license",
    formHint: "stro",
  },
  {
    label: "Report a missed pickup",
    message: "I want to report a missed trash pickup",
    formHint: "service_request",
  },
  { label: "What's on this weekend?", message: "What's on this weekend?" },
  { label: "Check my permit status", message: "Check my permit status" },
];

/** The action key differs between the spec (`type`) and the API (`action`). */
function actionKind(a: ChatAction): string {
  return a.action ?? a.type ?? "";
}

function clock(at: number): string {
  return new Date(at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [doc, setDoc] = useState<UploadedDocument | null>(null);
  const [uploading, setUploading] = useState(false);
  const [openTraces, setOpenTraces] = useState<number[]>([]);
  const nextId = useRef(1);
  const bottom = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  // "smart" alone is jargon; the /health alias map turns it into
  // "smart · claude-sonnet-4-6" for the status line while the answer streams.
  const providerModels = useProviderModels();
  // Lazy, not state: the id is never rendered, and reading localStorage during
  // the static prerender would just produce "" and a hydration mismatch.
  const sessionRef = useRef("");

  function session(): string {
    if (!sessionRef.current) sessionRef.current = getSessionId();
    return sessionRef.current;
  }

  const streamingNow = messages.some((m) => m.streaming);

  useEffect(() => {
    // Smooth scrolling per token would never settle, so a stream jumps instead.
    if (messages.length) {
      bottom.current?.scrollIntoView({ behavior: streamingNow ? "auto" : "smooth" });
    }
  }, [messages, pending, streamingNow]);

  function add(msg: Omit<Message, "id" | "at">) {
    setMessages((m) => [...m, { ...msg, id: nextId.current++, at: Date.now() }]);
  }

  function toggleTrace(id: number) {
    setOpenTraces((o) => (o.includes(id) ? o.filter((x) => x !== id) : [...o, id]));
  }

  async function send(text: string, formHint?: string) {
    const attached = doc;
    // An attachment is a message on its own: "here is my form" needs no words.
    const body =
      text.trim() || (attached ? "Here is my completed application. Please file it." : "");
    if (!body || pending) return;
    setInput("");
    setDoc(null);
    setError(null);
    add({ role: "user", text: body, attachment: attached?.filename });
    setPending(true);

    // The assistant bubble goes up empty and fills in as the stream arrives, so
    // the resident watches the answer being written instead of a spinner.
    const id = nextId.current++;
    setMessages((m) => [
      ...m,
      { id, role: "assistant", text: "", at: Date.now(), streaming: true, status: "routing…" },
    ]);
    const patch = (change: (m: Message) => Message) =>
      setMessages((m) => m.map((x) => (x.id === id ? change(x) : x)));

    const onEvent = (event: ChatStreamEvent) => {
      if (event.type === "status") {
        patch((m) => ({ ...m, status: modelLabel(event.model ?? event.tier, providerModels) }));
      } else if (event.type === "tool") {
        // Anything shown so far was a preamble to this call, not the answer.
        patch((m) => ({ ...m, status: `calling ${event.name}…`, text: "" }));
      } else if (event.type === "token") {
        patch((m) => ({ ...m, text: m.text + event.text }));
      }
    };

    try {
      // withSessionRetry rotates the session id and resends the turn once if the
      // API says this id belongs to another browser; a second refusal falls
      // through to the catch below and shows the API's own message.
      const res = await withSessionRetry(
        session(),
        (sessionId) =>
          streamChat(
            {
              session_id: sessionId,
              message: body,
              document_ids: attached ? [attached.document_id] : [],
            },
            onEvent,
          ),
        (fresh) => {
          sessionRef.current = fresh;
        },
      );
      if (res.connectionLost) {
        // Half an answer the resident can read beats no answer at all, so the
        // bubble keeps what streamed in and says plainly that it is cut off.
        // There is no trace and no citation list to attach: the `done` frame,
        // which carries both, is exactly what never arrived.
        patch((m) => ({
          ...m,
          streaming: false,
          status: undefined,
          text: res.reply,
          incomplete: true,
        }));
        return;
      }
      const formAction = res.actions.find((a) => actionKind(a) === "render_form");
      const created = res.actions.find((a) => actionKind(a) === "application_created");
      // The quick actions promise a form; if the model talked about one but did
      // not call the tool, honour the hint rather than leave the resident stuck.
      const hintFires =
        !formAction && formHint && /form|applicat|apply|permit|certificate|request/i.test(res.reply);
      // The `done` body is authoritative: it replaces whatever streamed in, so a
      // dropped delta or a tool-round preamble cannot survive into the answer.
      patch((m) => ({
        ...m,
        streaming: false,
        status: undefined,
        text: res.reply,
        citations: res.citations,
        trace: res.trace,
        formType: formAction?.form_type ?? (hintFires ? formHint : undefined),
        formSchema: formAction?.form ?? null,
        tracking: created?.tracking_number
          ? {
              number: created.tracking_number,
              status: created.status,
              note: created.department
                ? `Routed to ${created.department}` +
                  (created.sla_days ? `, target ${created.sla_days} days.` : ".")
                : null,
            }
          : undefined,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      // A bubble with half an answer and no trace is worse than no bubble.
      setMessages((m) => m.filter((x) => x.id !== id));
    } finally {
      setPending(false);
    }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      // Same rule as a chat turn: the upload joins this conversation, and a 403
      // means the id is another browser's, so rotate once and try again.
      setDoc(
        await withSessionRetry(
          session(),
          (sessionId) => uploadDocument(file, sessionId),
          (fresh) => {
            sessionRef.current = fresh;
          },
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  function onSubmitted(app: Application) {
    add({
      role: "system",
      text: "",
      tracking: {
        number: app.tracking_number,
        status: app.status,
        note:
          app.missing_fields && app.missing_fields.length
            ? `Still needed: ${app.missing_fields.join(", ")}.`
            : app.department
              ? `Routed to ${app.department}.`
              : null,
      },
    });
  }

  function newConversation() {
    sessionRef.current = rotateSessionId();
    setMessages([]);
    setOpenTraces([]);
    setInput("");
    setDoc(null);
    setError(null);
  }

  const chips = (
    <div className="flex flex-wrap gap-2" data-testid="quick-actions">
      {QUICK_ACTIONS.map((q) => (
        <button
          key={q.label}
          type="button"
          data-testid="quick-action"
          disabled={pending}
          onClick={() => send(q.message, q.formHint)}
          className="rounded-full border border-slate-300 bg-white px-3.5 py-1.5 text-meta font-medium text-primary shadow-sm transition-colors hover:border-primary hover:bg-primary-soft disabled:opacity-50"
        >
          {q.label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-1 flex-col overflow-hidden px-4 sm:px-6">
      <div className="flex shrink-0 flex-wrap items-baseline justify-between gap-3 pt-6 pb-4">
        <h1 className="text-title font-semibold">Ask the City</h1>
        <button
          type="button"
          data-testid="new-conversation"
          onClick={newConversation}
          className="text-meta font-medium text-primary hover:underline"
        >
          New conversation
        </button>
      </div>

      <div
        role="log"
        aria-live="polite"
        aria-label="Conversation"
        data-testid="message-list"
        className="min-h-0 flex-1 space-y-5 overflow-y-auto pb-8"
      >
        {messages.length === 0 ? (
          <div
            data-testid="empty-state"
            className="rounded-2xl border border-slate-200 bg-white px-6 py-10 text-center shadow-sm"
          >
            <div className="flex justify-center">
              <CitySeal size={56} />
            </div>
            <h2 className="mt-4 text-title font-semibold tracking-tight">City of San Diego</h2>
            <p className="mx-auto mt-2 max-w-[46ch] text-body text-muted">
              Ask about permits, starting a business, trash pickup or city events — or attach a
              filled-out form and the assistant will file it and hand you a tracking number.
            </p>
            <div className="mt-6 flex justify-center">{chips}</div>
          </div>
        ) : null}

        {messages.map((m) => {
          if (m.role === "user") {
            return (
              <div key={m.id} className="flex flex-col items-end">
                <div
                  data-testid="message-user"
                  className="max-w-[85%] rounded-xl rounded-br-sm bg-primary px-4 py-2.5 text-body text-white shadow-sm"
                >
                  <MarkdownLite text={m.text} />
                  {m.attachment ? (
                    <p className="mt-1.5 text-meta text-white/75">📎 {m.attachment}</p>
                  ) : null}
                </div>
                <span className="mt-1 pr-1 text-meta text-muted">{clock(m.at)}</span>
              </div>
            );
          }
          if (m.role === "system") {
            return (
              <div key={m.id} className="ml-[38px] max-w-[92%]">
                {m.tracking ? (
                  <TrackingCard
                    trackingNumber={m.tracking.number}
                    status={m.tracking.status}
                    note={m.tracking.note}
                  />
                ) : (
                  <p className="text-meta text-muted">{m.text}</p>
                )}
              </div>
            );
          }
          const traceOpen = openTraces.includes(m.id);
          return (
            <div key={m.id} className="flex gap-2.5">
              <span className="mt-0.5">
                <CitySeal size={28} />
              </span>
              <div className="min-w-0 flex-1">
                <div
                  data-testid="message-assistant"
                  data-streaming={m.streaming ? "true" : "false"}
                  className="rounded-xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3 text-body shadow-sm"
                >
                  {m.streaming ? (
                    <p
                      data-testid="stream-status"
                      className="mb-2 flex items-center gap-1.5 text-meta text-muted"
                    >
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                      {m.status}
                    </p>
                  ) : null}
                  {m.streaming ? (
                    <span data-testid="stream-text">
                      <MarkdownLite text={m.text} />
                    </span>
                  ) : (
                    <MarkdownLite text={m.text} />
                  )}
                </div>
                {m.incomplete ? (
                  <p
                    role="status"
                    data-testid="connection-lost"
                    className="mt-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-meta text-amber-900"
                  >
                    Connection lost, the answer above is incomplete.
                  </p>
                ) : null}
                <div className="mt-1 flex flex-wrap items-center gap-x-3 text-meta text-muted">
                  <span>City of San Diego assistant · {clock(m.at)}</span>
                </div>
                <Citations citations={m.citations ?? []} />
                {m.trace ? (
                  <>
                    <button
                      type="button"
                      data-testid="trace-toggle"
                      aria-expanded={traceOpen}
                      onClick={() => toggleTrace(m.id)}
                      className="mt-2 flex items-start gap-1.5 text-left text-meta text-muted hover:text-primary"
                    >
                      <svg
                        aria-hidden="true"
                        viewBox="0 0 12 12"
                        className={`mt-1 h-3 w-3 shrink-0 transition-transform ${
                          traceOpen ? "rotate-90" : ""
                        }`}
                      >
                        <path d="M4 2.5 8 6l-4 3.5z" fill="currentColor" />
                      </svg>
                      <span className="underline decoration-dotted underline-offset-2">
                        {traceOpen ? "Hide trace" : "Trace"} · {m.trace.intent ?? "?"} ·{" "}
                        {m.trace.tier ?? "?"} ·{" "}
                        {(m.trace.prompt_tokens ?? 0) + (m.trace.completion_tokens ?? 0)} tok ·{" "}
                        {m.trace.latency_ms ?? 0} ms
                      </span>
                    </button>
                    {traceOpen ? <TracePanel trace={m.trace} /> : null}
                  </>
                ) : null}
                {m.formType ? (
                  <InlineForm
                    formType={m.formType}
                    schema={m.formSchema}
                    onSubmitted={onSubmitted}
                  />
                ) : null}
                {m.tracking ? (
                  <TrackingCard
                    trackingNumber={m.tracking.number}
                    status={m.tracking.status}
                    note={m.tracking.note}
                  />
                ) : null}
              </div>
            </div>
          );
        })}

        {/* Only before the stream opens its own bubble — two spinners is one too many. */}
        {pending && !streamingNow ? (
          <div className="flex gap-2.5" data-testid="thinking">
            <span className="mt-0.5">
              <CitySeal size={28} />
            </span>
            <div className="rounded-xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3 text-body text-muted shadow-sm">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                Looking it up…
              </span>
            </div>
          </div>
        ) : null}
        <div ref={bottom} />
      </div>

      {error ? (
        <p
          role="alert"
          data-testid="chat-error"
          className="mb-3 shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-meta text-red-700"
        >
          {error}
        </p>
      ) : null}

      <div className="-mx-4 shrink-0 bg-page px-4 pt-3 pb-5 shadow-[0_-10px_20px_-12px_rgba(15,23,42,0.25)] sm:-mx-6 sm:px-6">
        {messages.length > 0 ? <div className="mb-2.5">{chips}</div> : null}

        {doc ? (
          <div className="mb-2.5 flex items-center gap-2" data-testid="attachment-chip">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-3 py-1 text-meta text-ink-soft">
              <span aria-hidden="true">📎</span>
              {doc.filename} —{" "}
              {doc.has_text === false || !doc.text_preview
                ? "no text found"
                : // The API caps text_preview at 300 chars, so say so honestly.
                  `${doc.text_preview.length}${doc.text_preview.length >= 300 ? "+" : ""} chars extracted`}
            </span>
            <button
              type="button"
              data-testid="attachment-remove"
              aria-label="Remove attachment"
              onClick={() => setDoc(null)}
              className="text-meta text-muted hover:text-red-700"
            >
              remove
            </button>
          </div>
        ) : null}

        <div className="flex items-end gap-2 rounded-xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-primary">
          <button
            type="button"
            data-testid="attach-button"
            onClick={() => fileInput.current?.click()}
            disabled={uploading}
            title="Attach a PDF, .txt or .md"
            aria-label="Attach a document"
            className="rounded-lg px-2 pb-1.5 text-xl text-muted hover:text-primary disabled:opacity-50"
          >
            {uploading ? "…" : "📎"}
          </button>
          <input
            ref={fileInput}
            data-testid="upload-input"
            type="file"
            aria-label="Attach a document"
            accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
            onChange={onFile}
            className="hidden"
          />
          <label htmlFor="composer" className="sr-only">
            Your message
          </label>
          <textarea
            id="composer"
            data-testid="composer-input"
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Ask about permits, trash pickup, events… (Enter sends, Shift+Enter for a new line)"
            className="min-h-[3rem] flex-1 resize-y bg-transparent px-1 py-1 text-body placeholder:text-muted focus:outline-none"
          />
          <button
            type="button"
            data-testid="send-button"
            onClick={() => send(input)}
            disabled={pending || (!input.trim() && !doc)}
            className="rounded-lg bg-primary px-4 py-2 text-meta font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
