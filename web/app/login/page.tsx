"use client";

/**
 * Staff sign-in. Posts to /api/auth/login, which sets the HttpOnly session
 * cookie; on success it returns to ?next= (the page that bounced you here) or
 * the staff queue. Depends on lib/api.login and the tokens in app/globals.css.
 */

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import CitySeal from "@/components/CitySeal";
import { login } from "@/lib/api";

/** Only same-site paths: ?next=https://evil.example would be an open redirect. */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/staff";
  return raw;
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  const field =
    "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-body text-ink " +
    "focus:border-primary focus:outline-none";

  return (
    <div className="mx-auto flex w-full max-w-[420px] flex-1 flex-col justify-center px-4 py-10 sm:px-6">
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-5 flex items-center gap-3">
          <CitySeal size={34} />
          <div>
            <h1 className="text-title font-semibold">Staff sign-in</h1>
            <p className="text-meta text-muted">
              The queue and the traces are staff-only. Residents can use the chat without an
              account.
            </p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4" data-testid="login-form">
          <label className="block text-meta font-medium text-ink-soft">
            <span className="mb-1 block">Username</span>
            <input
              data-testid="login-username"
              name="username"
              autoComplete="username"
              autoFocus
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={field}
            />
          </label>

          <label className="block text-meta font-medium text-ink-soft">
            <span className="mb-1 block">Password</span>
            <input
              data-testid="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={field}
            />
          </label>

          {error ? (
            <p
              role="alert"
              data-testid="login-error"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-meta text-red-800"
            >
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            data-testid="login-submit"
            className="w-full rounded-lg bg-primary px-4 py-2 text-body font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>

      <p className="mt-4 text-center text-meta text-muted">
        Demo credentials come from <code className="font-mono">STAFF_USERNAME</code> and{" "}
        <code className="font-mono">STAFF_PASSWORD</code> in <code className="font-mono">.env</code>
        .
      </p>
    </div>
  );
}

export default function LoginPage() {
  // useSearchParams needs a Suspense boundary for the static prerender.
  return (
    <Suspense
      fallback={
        <p className="mx-auto w-full max-w-[420px] px-6 py-10 text-meta text-muted">Loading…</p>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
