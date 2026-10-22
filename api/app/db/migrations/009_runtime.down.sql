-- Down migration for 009_runtime.sql. Run with:
--   python -m app.db.migrations --rollback 009_runtime.sql
--
-- Drops the per-IP token bucket table and the idempotency key — the only two
-- things 009 actually created. Its points 3 and 4 create nothing: they are
-- comments explaining why a second index on an already-indexed column was not
-- added, so there is nothing there to undo.
--
-- rate_limits is derived state: every bucket is refilled lazily from `updated_at`
-- on the request that reads it, so dropping the table costs nothing but a moment
-- of unlimited requests until app/rate_limit.py is rolled back with it (without
-- the table it takes its "limiter unavailable, allow" branch, which is fail-open
-- by design).
--
-- applications.idempotency_key does lose data: after a rollback a replayed POST
-- /api/applications mints a second tracking number instead of returning the
-- first, which is the double-click bug 009 fixed. Take scripts/backup.sh first.
-- The unique index would go with its column anyway; it is dropped explicitly so
-- the intent is readable here.

DROP INDEX IF EXISTS applications_idempotency_key_idx;
ALTER TABLE applications DROP COLUMN IF EXISTS idempotency_key;
DROP TABLE IF EXISTS rate_limits;
