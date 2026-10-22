-- Down migration for 008_resident_sessions.sql. Run with:
--   python -m app.db.migrations --rollback 008_resident_sessions.sql
--
-- Drops the documents.session_id column and its index.
--
-- This one loses data: session_id is how an upload claims a conversation, so
-- after a rollback every document on file becomes unclaimed and the first-contact
-- check in app/resident_session.py sees only chat_messages again — a second
-- browser could take over an id whose only activity was an upload, which is the
-- hole 008 closed. Nothing recomputes it; the column is the only record of it.
-- Take scripts/backup.sh first. The index would go with its column anyway; it is
-- dropped explicitly so the intent is readable here.

DROP INDEX IF EXISTS documents_session_id_idx;
ALTER TABLE documents DROP COLUMN IF EXISTS session_id;
