-- Initial schema: every table in PLAN.md §5. Applied once at startup by
-- app/db/migrations.py, which substitutes {{EMBED_DIM}} with settings.embed_dim
-- (768 for nomic-embed-text) so the vector width follows the embedding model.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------- documents
CREATE TABLE IF NOT EXISTS documents (
    id            BIGSERIAL PRIMARY KEY,
    s3_key        TEXT NOT NULL,
    filename      TEXT NOT NULL,
    content_type  TEXT,
    size          INTEGER,
    text          TEXT,
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------- applications
CREATE TABLE IF NOT EXISTS applications (
    id                  BIGSERIAL PRIMARY KEY,
    tracking_number     TEXT UNIQUE NOT NULL,
    type                TEXT NOT NULL,           -- permit | business_tax | service_request | stro (M24)
    status              TEXT NOT NULL DEFAULT 'draft',
    fields              JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_fields      JSONB NOT NULL DEFAULT '[]'::jsonb,
    department          TEXT,
    fee_cents           INTEGER,
    resident_session_id TEXT,
    document_id         BIGINT REFERENCES documents(id) ON DELETE SET NULL,
    certificate_s3_key  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS applications_status_idx ON applications (status);

-- One row per state transition: the audit trail the staff page renders.
CREATE TABLE IF NOT EXISTS application_events (
    id             BIGSERIAL PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    from_status    TEXT,
    to_status      TEXT NOT NULL,
    actor          TEXT,
    note           TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS application_events_app_idx ON application_events (application_id);

-- ------------------------------------------------- reference data (seeded)
CREATE TABLE IF NOT EXISTS trash_zones (
    zone_id        TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    trash_day      TEXT NOT NULL,
    recycling_week TEXT,                          -- "A" or "B"
    organics_week  TEXT,
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS addresses (
    id               BIGSERIAL PRIMARY KEY,
    address          TEXT NOT NULL,
    zip              TEXT,
    zone_id          TEXT,
    council_district INTEGER
);
CREATE INDEX IF NOT EXISTS addresses_address_idx ON addresses (lower(address));

CREATE TABLE IF NOT EXISTS events (
    id          BIGSERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    date        DATE,
    start_time  TEXT,
    end_time    TEXT,
    location    TEXT,
    department  TEXT,
    cost        TEXT,
    description TEXT,
    url         TEXT
);
CREATE INDEX IF NOT EXISTS events_date_idx ON events (date);

CREATE TABLE IF NOT EXISTS permit_types (
    code                             TEXT PRIMARY KEY,
    name                             TEXT NOT NULL,
    description                      TEXT,
    base_fee_cents                   INTEGER,
    per_1000_valuation_cents         INTEGER,
    typical_turnaround_days          INTEGER,
    requires_plans_over_valuation_cents INTEGER
);

CREATE TABLE IF NOT EXISTS service_categories (
    category    TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    department  TEXT,
    sla_days    INTEGER,
    description TEXT
);

CREATE TABLE IF NOT EXISTS referrals (
    id     BIGSERIAL PRIMARY KEY,
    topic  TEXT NOT NULL,
    agency TEXT NOT NULL,
    url    TEXT,
    note   TEXT
);

CREATE TABLE IF NOT EXISTS council_districts (
    district      INTEGER PRIMARY KEY,
    councilmember TEXT,
    neighborhoods JSONB NOT NULL DEFAULT '[]'::jsonb
);

-- ----------------------------------------------------- knowledge base (RAG)
CREATE TABLE IF NOT EXISTS kb_documents (
    id         BIGSERIAL PRIMARY KEY,
    title      TEXT NOT NULL,
    topic      TEXT,
    source_url TEXT,
    s3_key     TEXT
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    embedding   vector({{EMBED_DIM}}),
    tsv         tsvector
);
-- Vector half of hybrid retrieval. hnsw (not ivfflat) because the table is
-- empty at migration time and ivfflat needs rows to train its lists.
CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx
    ON kb_chunks USING hnsw (embedding vector_cosine_ops);
-- Keyword half.
CREATE INDEX IF NOT EXISTS kb_chunks_tsv_idx ON kb_chunks USING gin (tsv);

-- ------------------------------------------------- observability (M2 fills)
CREATE TABLE IF NOT EXISTS traces (
    id                BIGSERIAL PRIMARY KEY,
    session_id        TEXT,
    message           TEXT,
    reply             TEXT,
    intent            TEXT,
    confidence        DOUBLE PRECISION,
    tier              TEXT,
    model             TEXT,
    rag_chunk_ids     JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_calls        JSONB NOT NULL DEFAULT '[]'::jsonb,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms        INTEGER NOT NULL DEFAULT 0,
    cost_usd          DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    trace_id   BIGINT REFERENCES traces(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON chat_messages (session_id, id);
