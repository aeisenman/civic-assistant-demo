-- M20: an upload belongs to a conversation.
--
-- The resident_session cookie is minted on "first contact", which app/resident_session.py
-- defines as a session id with no chat_messages row and no documents row. Uploads
-- had no session id at all, so a resident who dropped a permit form in before
-- typing anything left the id unclaimed and a second browser could still take it.
-- NULL on every pre-M20 row and on any caller that does not send one: those rows
-- simply do not claim a session.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS session_id TEXT;

-- The first-contact check runs on every request that arrives without a valid
-- cookie. chat_messages already has chat_messages_session_idx (001_init.sql);
-- this is the other half of the same EXISTS.
CREATE INDEX IF NOT EXISTS documents_session_id_idx ON documents (session_id);
