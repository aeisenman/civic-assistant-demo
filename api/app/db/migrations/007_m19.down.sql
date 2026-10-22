-- Down migration for 007_m19.sql. Run with:
--   python -m app.db.migrations --rollback 007_m19.sql
--
-- Drops the two kb_documents columns and the traces counter 007 added.
--
-- This one loses data: kb_documents.filename and content_hash are what make the
-- knowledge-base ingest idempotent per document, so after a rollback the next
-- `python -m app.rag.ingest` re-embeds every file (spend, and renumbered chunk
-- ids that existing traces point at). traces.tool_rounds is history that cannot
-- be recomputed. Take scripts/backup.sh first. The index would go with its
-- column anyway; it is dropped explicitly so the intent is readable here.

DROP INDEX IF EXISTS kb_documents_filename_key;
ALTER TABLE kb_documents DROP COLUMN IF EXISTS filename;
ALTER TABLE kb_documents DROP COLUMN IF EXISTS content_hash;
ALTER TABLE traces DROP COLUMN IF EXISTS tool_rounds;
