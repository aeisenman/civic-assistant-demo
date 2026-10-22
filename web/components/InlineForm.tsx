"use client";

/**
 * The application form the assistant renders inside the conversation.
 * Rendered by the chat page when a turn returns a render_form action; fields
 * come from GET /api/forms/{type}, the submit goes to POST /api/applications.
 */

import { useEffect, useId, useState } from "react";
import {
  createApplication,
  getForm,
  type Application,
  type FormField,
  type FormSchema,
} from "@/lib/api";
import { getSessionId } from "@/lib/session";

type Values = Record<string, string | boolean>;

function initialValues(fields: FormField[]): Values {
  const v: Values = {};
  for (const f of fields) v[f.name] = f.type === "checkbox" ? false : "";
  return v;
}

/** Strip empties so the API's validator sees "missing", not "blank". */
function toPayload(fields: FormField[], values: Values): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const raw = values[f.name];
    if (f.type === "checkbox") {
      out[f.name] = Boolean(raw);
    } else if (typeof raw === "string" && raw.trim() !== "") {
      out[f.name] = f.type === "number" ? Number(raw) : raw.trim();
    }
  }
  return out;
}

export default function InlineForm({
  formType,
  schema: given,
  onSubmitted,
}: {
  formType: string;
  schema?: FormSchema | null;
  onSubmitted: (app: Application) => void;
}) {
  const uid = useId();
  const [schema, setSchema] = useState<FormSchema | null>(given ?? null);
  const [values, setValues] = useState<Values>(given ? initialValues(given.fields) : {});
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (schema) return;
    let alive = true;
    getForm(formType)
      .then((s) => {
        if (!alive) return;
        setSchema(s);
        setValues(initialValues(s.fields));
      })
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [formType, schema]);

  if (error && !schema) {
    return (
      <p className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-meta text-red-700">
        Could not load the form: {error}
      </p>
    );
  }
  if (!schema) return <p className="mt-3 text-meta text-muted">Loading form…</p>;
  if (done) return null;

  const set = (name: string, value: string | boolean) =>
    setValues((v) => ({ ...v, [name]: value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!schema) return;
    setPending(true);
    setError(null);
    try {
      const app = await createApplication({
        type: schema.form_type || formType,
        fields: toPayload(schema.fields, values),
        session_id: getSessionId(),
      });
      setDone(true);
      onSubmitted(app);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPending(false);
    }
  }

  const inputCls =
    "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-meta text-ink " +
    "placeholder:text-muted focus:border-primary focus:outline-none";

  return (
    <form
      onSubmit={submit}
      data-testid="inline-form"
      data-form-type={schema.form_type || formType}
      className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
    >
      <div className="border-b border-rule bg-primary-soft px-4 py-3">
        <h3 className="text-section font-semibold text-primary">{schema.title}</h3>
        <p className="text-meta text-muted">
          Fields marked <span className="text-red-600">*</span> are required. Everything else
          can follow later.
        </p>
      </div>

      <div className="grid gap-3.5 px-4 py-4 sm:grid-cols-2">
        {schema.fields.map((f) => {
          const id = `${uid}-${f.name}`;
          // Shared across every widget; `placeholder` is added only where the
          // element actually supports it (a <select> would warn).
          const common = { id, "data-testid": `field-${f.name}`, className: inputCls };
          return (
            <div
              key={f.name}
              className={f.type === "textarea" ? "sm:col-span-2" : undefined}
            >
              <label htmlFor={id} className="mb-1 block text-meta font-medium text-ink-soft">
                {f.label}
                {f.required ? (
                  <span className="text-red-600" aria-hidden="true">
                    {" "}
                    *
                  </span>
                ) : null}
              </label>
              {f.type === "textarea" ? (
                <textarea
                  {...common}
                  placeholder={f.placeholder}
                  rows={3}
                  value={String(values[f.name] ?? "")}
                  onChange={(e) => set(f.name, e.target.value)}
                />
              ) : f.type === "select" ? (
                <select
                  {...common}
                  value={String(values[f.name] ?? "")}
                  onChange={(e) => set(f.name, e.target.value)}
                >
                  <option value="">Select…</option>
                  {(f.options ?? []).map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              ) : f.type === "checkbox" ? (
                <input
                  {...common}
                  type="checkbox"
                  className="mt-1 h-4 w-4 rounded border-slate-300 accent-[#0f2f4f]"
                  checked={Boolean(values[f.name])}
                  onChange={(e) => set(f.name, e.target.checked)}
                />
              ) : (
                <input
                  {...common}
                  placeholder={f.placeholder}
                  type={
                    f.type === "number"
                      ? "number"
                      : f.type === "date"
                        ? "date"
                        : f.type === "email"
                          ? "email"
                          : "text"
                  }
                  value={String(values[f.name] ?? "")}
                  onChange={(e) => set(f.name, e.target.value)}
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-rule bg-slate-50 px-4 py-3">
        <button
          type="submit"
          disabled={pending}
          data-testid="form-submit"
          className="rounded-lg bg-primary px-4 py-2 text-meta font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover disabled:opacity-50"
        >
          {pending ? "Submitting…" : "Submit application"}
        </button>
        {error ? (
          <p className="text-meta text-red-700" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </form>
  );
}
