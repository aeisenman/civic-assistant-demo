-- Down migration for 006_sequences.sql. Run with:
--   python -m app.db.migrations --rollback 006_sequences.sql
--
-- Drops the three tracking-number sequences. Nothing else references them, so
-- this is reversible in both directions: re-applying 006 recreates each one and
-- setvals it from MAX(tracking_number) on the table, which is still there.
--
-- What it does NOT undo: app/workflows/store.py calls nextval() on these, so
-- after this runs the application code cannot mint a tracking number until 006
-- is re-applied. Roll the code and the schema back together, in that order.

DROP SEQUENCE IF EXISTS tracking_permit_seq;
DROP SEQUENCE IF EXISTS tracking_business_tax_seq;
DROP SEQUENCE IF EXISTS tracking_service_request_seq;
