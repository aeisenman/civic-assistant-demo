-- M2 adds four columns the chat orchestrator records but 001 did not have:
-- the router's one-line reason, the per-call breakdown from TraceCollector,
-- the document ids the turn was given, and an error string so a failed turn is
-- still a readable trace instead of a 500.

ALTER TABLE traces ADD COLUMN IF NOT EXISTS reason       TEXT;
ALTER TABLE traces ADD COLUMN IF NOT EXISTS error        TEXT;
ALTER TABLE traces ADD COLUMN IF NOT EXISTS calls        JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE traces ADD COLUMN IF NOT EXISTS document_ids JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS traces_created_idx ON traces (created_at DESC);
