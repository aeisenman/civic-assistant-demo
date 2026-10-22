-- M8: ZIP -> collection zone, so a geocoded or ZIP-only address still gets a
-- trash day. 003 is already taken by the M3 workflow tables, so this is 004.
-- JSONB (not TEXT[]) to match the other list columns the seed loader writes.
ALTER TABLE trash_zones ADD COLUMN IF NOT EXISTS zips JSONB NOT NULL DEFAULT '[]'::jsonb;
