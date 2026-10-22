-- M15: one Postgres sequence per application type, so two concurrent creates
-- can never mint the same tracking number. The old code read MAX(tracking_number)
-- and added one, which raced into a UNIQUE violation and a 500 for the loser.
--
-- Each sequence is created IF NOT EXISTS and then setval'd to the highest number
-- already on the table, so nothing this demo has issued is handed out twice; the
-- 399 floor keeps generated numbers clear of the seeded fixtures, which occupy
-- 000101+, 000201+ and 000301+. `true` means "already used", so the first
-- nextval() returns one more than the value set here.
--
-- Written out three times rather than as a plpgsql loop: nine plain statements
-- are easier to read, and to run by hand during a recovery, than a DO block.

CREATE SEQUENCE IF NOT EXISTS tracking_permit_seq;
SELECT setval(
    'tracking_permit_seq',
    GREATEST(
        (SELECT COALESCE(MAX(substring(tracking_number from '(\d{6})$')::BIGINT), 0)
           FROM applications WHERE tracking_number LIKE 'PRM-%'),
        399
    ),
    true
);

CREATE SEQUENCE IF NOT EXISTS tracking_business_tax_seq;
SELECT setval(
    'tracking_business_tax_seq',
    GREATEST(
        (SELECT COALESCE(MAX(substring(tracking_number from '(\d{6})$')::BIGINT), 0)
           FROM applications WHERE tracking_number LIKE 'BTC-%'),
        399
    ),
    true
);

CREATE SEQUENCE IF NOT EXISTS tracking_service_request_seq;
SELECT setval(
    'tracking_service_request_seq',
    GREATEST(
        (SELECT COALESCE(MAX(substring(tracking_number from '(\d{6})$')::BIGINT), 0)
           FROM applications WHERE tracking_number LIKE 'SR-%'),
        399
    ),
    true
);
