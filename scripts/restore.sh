#!/usr/bin/env bash
# Restore drill: takes the newest scripts/backup.sh dump, loads it into a scratch
# database next to the live one, and prints the row counts side by side so the
# backup's restorability is a number rather than a comment in a shell script
# (audit finding 11 — no restore had ever been run).
# Called by hand, monthly, and by anyone about to trust `data/backups/`. Depends
# on: a running `db` service (pg_restore and psql run inside it, so no local
# postgres client is needed) and a dump written by scripts/backup.sh.
# Usage: bash scripts/restore.sh [--keep] [path/to/backup-dir]
#
# It never writes to the live `civic` database: everything lands in
# `civic_restore`, which is dropped again on the way out unless --keep is given.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Bash 3.2 (the macOS default) has no ${var,,}, no associative arrays and no
# `mapfile`: keep this to plain strings, POSIX test and a while-read loop.
KEEP=0
BACKUP_DIR=""
for arg in "$@"; do
  case "$arg" in
    --keep) KEEP=1 ;;
    -*) echo "unknown option: $arg" >&2; exit 2 ;;
    *) BACKUP_DIR="$arg" ;;
  esac
done

DB_USER="${POSTGRES_USER:-civic}"
DB_NAME="${POSTGRES_DB:-civic}"
SCRATCH="civic_restore"
# backup.sh writes data/backups/<stamp>-<label>/dump.pgc; the stamp sorts
# lexicographically because it is %Y%m%d-%H%M%S, so "newest" is just the last.
if [ -z "$BACKUP_DIR" ]; then
  BACKUP_DIR="$(ls -d "$ROOT"/data/backups/*/ 2>/dev/null | sort | tail -1 | sed 's:/$::')"
fi
DUMP="$BACKUP_DIR/dump.pgc"

if [ -z "$BACKUP_DIR" ] || [ ! -f "$DUMP" ]; then
  echo "no dump.pgc under data/backups/ — run scripts/backup.sh first" >&2
  exit 1
fi

echo "== restore drill"
echo "-- source:  ${DUMP#$ROOT/} ($(wc -c < "$DUMP" | tr -d ' ') bytes)"
if [ -f "$BACKUP_DIR/MANIFEST" ]; then
  sed 's/^/   /' "$BACKUP_DIR/MANIFEST"
fi

# -T everywhere: docker must not allocate a TTY, or it mangles the binary stream
# on the way in and adds \r to every line of psql output on the way out.
dbx() { docker compose exec -T db "$@"; }

# psql -tA = no header, no padding, unaligned: the output is the value itself.
sql() { dbx psql -U "$DB_USER" -d "$1" -tAc "$2"; }

count() {
  # A table the dump did not carry reports "-" rather than aborting the drill.
  sql "$1" "SELECT count(*) FROM $2" 2>/dev/null || echo "-"
}

cleanup() {
  if [ "$KEEP" = "1" ]; then
    echo "-- keeping $SCRATCH (--keep); drop it with:"
    echo "   docker compose exec -T db dropdb -U $DB_USER $SCRATCH"
    return
  fi
  echo "-- dropping $SCRATCH"
  # --force disconnects anything still attached; it is a Postgres 13+ flag and
  # the image is pg16. Failure here is worth seeing but must not mask an
  # earlier failure, hence the `|| true` on a trap that also runs on success.
  dbx dropdb --if-exists --force -U "$DB_USER" "$SCRATCH" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "-- creating scratch database $SCRATCH"
EXISTS="$(sql postgres "SELECT 1 FROM pg_database WHERE datname = '$SCRATCH'" || true)"
if [ "$EXISTS" = "1" ]; then
  echo "   already there, dropping it first"
  dbx dropdb --force -U "$DB_USER" "$SCRATCH"
fi
dbx createdb -U "$DB_USER" "$SCRATCH"

echo "-- pg_restore into $SCRATCH"
# --clean --if-exists so a rerun into a --keep'd database is idempotent. Into a
# fresh database every DROP is a no-op, and pg_restore still exits non-zero on
# the "does not exist" notices it prints for them, so the exit code is reported
# rather than fatal: the row counts below are the real verdict.
set +e
dbx pg_restore --clean --if-exists --no-owner --no-privileges \
  -U "$DB_USER" -d "$SCRATCH" < "$DUMP" 2>"$ROOT/.restore.err"
RC=$?
set -e
if [ "$RC" != "0" ]; then
  echo "   pg_restore exited $RC; first lines of its output:"
  head -5 "$ROOT/.restore.err" | sed 's/^/   /'
fi
rm -f "$ROOT/.restore.err"

printf '\n%-18s %12s %12s\n' "table" "$DB_NAME" "$SCRATCH"
printf '%-18s %12s %12s\n' "------------------" "------------" "------------"
for TABLE in applications traces kb_chunks; do
  printf '%-18s %12s %12s\n' "$TABLE" "$(count "$DB_NAME" "$TABLE")" "$(count "$SCRATCH" "$TABLE")"
done
echo ""
echo "The two columns differ by whatever the live stack has written since the"
echo "backup was taken; what the drill proves is that the dump restores at all"
echo "and that each table came back with rows in it."
