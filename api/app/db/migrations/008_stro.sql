-- M24: the fourth application type, the Short-Term Residential Occupancy (STRO)
-- licence, needs its own tracking-number sequence — exactly like the three in
-- 006_sequences.sql. `applications.type` is plain TEXT with no CHECK constraint,
-- so nothing else about the schema changes: a new type is a new pydantic model,
-- a new validator branch and this sequence.
--
-- Additive and idempotent: CREATE SEQUENCE IF NOT EXISTS, then setval to the
-- highest STR- number already on the table, floored at 499 so generated numbers
-- stay clear of the seeded fixtures (STR-2026-000401 and STR-2026-000402).
-- `true` means "already used", so the first nextval() returns 500.

CREATE SEQUENCE IF NOT EXISTS tracking_stro_seq;
SELECT setval(
    'tracking_stro_seq',
    GREATEST(
        (SELECT COALESCE(MAX(substring(tracking_number from '(\d{6})$')::BIGINT), 0)
           FROM applications WHERE tracking_number LIKE 'STR-%'),
        499
    ),
    true
);
