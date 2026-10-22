-- M3 adds the column the validator writes and re-asserts the two intake columns.
-- `warnings` holds non-blocking validation notes (unconfirmed address, late
-- business start) that the staff queue shows next to `missing_fields`.
-- The session/document columns already exist in 001; ADD COLUMN IF NOT EXISTS
-- keeps this file safe to apply against a database created before or after that.

ALTER TABLE applications ADD COLUMN IF NOT EXISTS warnings JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS resident_session_id TEXT;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS applications_session_idx ON applications (resident_session_id);
