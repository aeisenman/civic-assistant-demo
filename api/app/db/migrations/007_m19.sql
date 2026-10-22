-- M19: two columns, both so a reader can answer a question the tables could not.
--
-- kb_documents.filename + content_hash make the knowledge-base ingest idempotent
-- per document (probe A20). Before this, ingest_kb skipped the entire run as soon
-- as one chunk existed, so a KB left half-written by a crash stayed half-written
-- and /health reported the wrong count with nothing able to repair it. Existing
-- rows keep NULL in both: app/rag/ingest.py adopts a NULL-hash row that still has
-- chunks rather than re-embedding it, which would renumber chunk ids that traces
-- already point at.
--
-- traces.tool_rounds records how many model rounds the tool loop spent. A value of
-- MAX_TOOL_ROUNDS (4) is the signature of a turn that looped until it ran out of
-- budget (probe A10) — tool_calls alone cannot distinguish that from four useful
-- calls in one round.

ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS filename TEXT;
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- One row per file. Partial so the pre-M19 rows, which all have NULL here, do not
-- collide with each other while they wait to be adopted or replaced.
CREATE UNIQUE INDEX IF NOT EXISTS kb_documents_filename_key
    ON kb_documents (filename) WHERE filename IS NOT NULL;

ALTER TABLE traces ADD COLUMN IF NOT EXISTS tool_rounds INTEGER NOT NULL DEFAULT 0;
