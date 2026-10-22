# web — City of San Diego virtual assistant (Next.js 16, TypeScript, Tailwind)

Dev: `npm install` then `PORT=3001 npm run dev` → http://localhost:3001.
Build check: `npm run build` (also what CI/the Docker image runs).
Lint: `npm run lint`. End-to-end: `npm run test:e2e` (see `e2e/README.md`).
Docker: `docker compose up -d --build web` from the repo root (3001 → 3000).

Env: `NEXT_PUBLIC_API_URL` (default `http://localhost:8080`). It is inlined at
build time, so the Dockerfile takes it as a build arg — changing it needs a rebuild.
The browser calls the FastAPI service directly; CORS on the API is open.

Pages: `/` resident chat (empty state with quick actions, file upload, inline
application form, citations, an expandable trace panel per reply) · `/staff`
application queue with a filter bar, a slide-in detail panel (Fields, Warnings,
Timeline, Actions) and a certificate link, polled every 5 s · `/traces` last 100
turns with tokens, latency, cost and tool calls.

Design system: `app/globals.css`. One deep civic navy (`--color-primary`,
`#0f2f4f`) for the nav, primary buttons and resident bubbles; one warm amber
(`--color-accent`, `#d97706`) used sparingly for the seal, focus rings and the
active nav underline; Tailwind's slate scale for everything neutral; white
surfaces on a slate-50 page. Four type steps (`text-title` 24 / `text-section` 16
/ `text-body` 15 / `text-meta` 13). Content is capped at 1100px, the chat column
at 760px. Light-only on purpose — this is projected in a room. No UI library.

`e2e/screenshots/*.png` are committed: they are the design-review record and are
regenerated with `npm run test:e2e:shots`.
