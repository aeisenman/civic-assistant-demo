-- M26a: the four schema changes the hostile load test asked for.
--
-- Every statement is additive and IF NOT EXISTS: this file is applied to the
-- shared demo database by whichever process boots next, and re-applying it must
-- be a no-op. Nothing here drops or rewrites an existing row.

-- 1. Per-IP token bucket (app/rate_limit.py).
--    In Postgres rather than in the process, because two API replicas with two
--    in-process dicts is two rate limits: the reviewer's finding #2, "nothing in
--    this stack survives a second replica". One row per bucket key, refilled
--    lazily from `updated_at` on the request that reads it, so there is no
--    sweeper and no background task.
CREATE TABLE IF NOT EXISTS rate_limits (
    key        TEXT PRIMARY KEY,
    tokens     DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ      NOT NULL DEFAULT now()
);

-- 2. Idempotency for POST /api/applications (finding #7: 30 double-clicks made
--    30 tracking numbers). Partial, so the column stays NULL on every existing
--    row and on every caller that does not send the header.
ALTER TABLE applications ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS applications_idempotency_key_idx
    ON applications (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- 3. kb_documents.filename UNIQUE: deliberately NOT created here.
--    Two replicas booting at once used to ingest the same kb/*.md twice, and
--    retrieval then cited the same passage twice — but 007_m19.sql already ships
--    `kb_documents_filename_key UNIQUE (filename) WHERE filename IS NOT NULL`,
--    which is the same guarantee (NULLs never collide under a plain UNIQUE
--    either). A second index on the same column would be write cost for nothing.
--    Verified against the shared database: 9 rows, 9 distinct filenames, 0 NULLs,
--    and \d kb_documents lists kb_documents_filename_key. The other half of the
--    fix — the advisory lock in app/rag/ingest.py — is new in M26a.

-- 4. traces(created_at): deliberately NOT created here.
--    The daily cost breaker now filters on the Pacific-local day, which is a
--    range scan over created_at, and 002_traces_m2.sql already ships
--    `traces_created_idx btree (created_at DESC)`. A DESC b-tree serves a range
--    predicate exactly as well as an ASC one (Postgres walks it either way), so
--    a second index on the same column would be write cost for no read benefit.
--    Verified against the shared database: \d traces lists traces_created_idx.
