-- M11: a real staff login, because the queue can issue certificates.
-- Two tables only: one seeded user, and one row per live browser session.
-- password_hash carries its own salt and scrypt parameters (see app/auth.py);
-- staff_sessions stores the sha256 of the cookie value, never the cookie itself,
-- so a database dump cannot be replayed as a session.
CREATE TABLE IF NOT EXISTS staff_users (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staff_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES staff_users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Expired rows are deleted lazily on the next login; the index keeps that cheap.
CREATE INDEX IF NOT EXISTS staff_sessions_expires_at_idx ON staff_sessions (expires_at);
