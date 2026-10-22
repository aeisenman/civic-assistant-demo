-- Down migration for 008_stro.sql. Run with:
--   python -m app.db.migrations --rollback 008_stro.sql
--
-- Drops the STRO tracking-number sequence, exactly as 006_sequences.down.sql
-- drops the other three. Nothing references it, so this is reversible in both
-- directions: re-applying 008_stro recreates the sequence and setvals it from
-- MAX(tracking_number) over the STR- rows, which are still on the table.
--
-- What it does NOT undo: the STRO applications themselves stay (they are
-- resident filings, and no down migration in this project deletes one), and
-- app/workflows/store.py calls nextval() on this sequence, so after this runs no
-- new STRO licence can be filed until 008_stro is re-applied. Roll the code and
-- the schema back together, in that order.

DROP SEQUENCE IF EXISTS tracking_stro_seq;
