#!/usr/bin/env bash
# Takes a point-in-time backup of everything a resident wrote: a custom-format
# pg_dump of the Postgres database and a tar of the SeaweedFS volume (uploaded
# documents and issued certificates), into data/backups/<timestamp>/.
# Called by scripts/reset_demo.sh before it deletes the volumes, and safe to run
# by hand at any time. Depends on: a running `db` service (pg_dump runs inside
# it, so no local postgres client is needed) and read access to data/volumes.
# Usage: bash scripts/backup.sh [label]
# Restore:
#   pg_restore --clean --if-exists -U civic -d civic  < dump.pgc   (inside db)
#   tar -xzf seaweed.tar.gz -C data/volumes                        (stack down)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Bash 3.2 (the macOS default) has no ${var,,} and no associative arrays: keep
# this to plain strings and POSIX test.
LABEL="${1:-manual}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$ROOT/data/backups/${STAMP}-${LABEL}"
DB_USER="${POSTGRES_USER:-civic}"
DB_NAME="${POSTGRES_DB:-civic}"

mkdir -p "$DEST"
echo "== backing up to ${DEST#$ROOT/}"

# -Fc (custom format) so pg_restore can be selective; -T so docker does not try
# to allocate a TTY and corrupt the binary stream on the way out.
echo "-- pg_dump ${DB_NAME}"
if docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$DEST/dump.pgc"; then
  echo "   $(wc -c < "$DEST/dump.pgc" | tr -d ' ') bytes"
else
  echo "pg_dump failed (is the db service running?)" >&2
  rm -f "$DEST/dump.pgc"
  exit 1
fi

# The object store is a bind mount, so a tar of the directory is the whole
# backup. Missing directory is not an error: a fresh checkout has no volumes.
echo "-- tar data/volumes/seaweed"
if [ -d "$ROOT/data/volumes/seaweed" ]; then
  tar -czf "$DEST/seaweed.tar.gz" -C "$ROOT/data/volumes" seaweed
  echo "   $(wc -c < "$DEST/seaweed.tar.gz" | tr -d ' ') bytes"
else
  echo "   no data/volumes/seaweed, skipping"
fi

{
  echo "taken_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "label: $LABEL"
  echo "database: $DB_NAME"
  echo "host: $(hostname)"
} > "$DEST/MANIFEST"

echo "Backup complete: ${DEST#$ROOT/}"
