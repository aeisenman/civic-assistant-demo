#!/usr/bin/env bash
# Wipes the demo back to its seeded state: stops the stack, deletes the Postgres
# and SeaweedFS volumes, starts it again and waits for /health to come up green
# with the knowledge base ingested. Run it before a demo. Depends on: docker
# compose and a .env (copy one of .env.ollama / .env.openai / .env.bedrock).
# Usage: bash scripts/reset_demo.sh [--build] [--no-backup] [service ...]
# Everything a resident filed is dumped to data/backups/<timestamp>-pre-reset/
# first (scripts/backup.sh); --no-backup skips that when you know it is junk.
# Pass --build after editing api/seed_data/*.json, api/kb/*.md or any source:
# the Dockerfile COPYs them into the image, so a plain restart reuses the old ones.
# Name services to touch only those (plus db and seaweedfs, which own the
# volumes) and leave the rest of the stack running -- e.g. while someone else is
# working on web:  bash scripts/reset_demo.sh --build api litellm
# Works on either provider profile. .env.bedrock sets COMPOSE_PROFILES=aws, so
# plain `docker compose up` also starts the LiteLLM gateway, and the api's
# depends_on (condition: service_healthy, required: false) makes it wait for the
# gateway there and ignore it on the Ollama profile.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API="http://localhost:8080"
WEB="http://localhost:3001"
TIMEOUT_SECONDS=180
# Plain string, not an array: bash 3.2 (the macOS default) errors on an empty
# array expansion under `set -u`.
BUILD_ARG=""
BACKUP="yes"
while [ "$#" -gt 0 ]; do
  case "${1}" in
    --build) BUILD_ARG="--build"; shift ;;
    --no-backup) BACKUP="no"; shift ;;
    *) break ;;
  esac
done
# Empty means the whole stack. Same plain-string reason as BUILD_ARG.
SERVICES="${*:-}"

if [ ! -f .env ]; then
  echo "no .env found. Run: cp .env.ollama .env" >&2
  exit 1
fi

# Back up before anything stops: pg_dump needs the db container alive, and the
# next step deletes both volumes outright. A failed backup aborts the reset --
# losing filed applications by accident is exactly what this guards against.
if [ "$BACKUP" = "yes" ]; then
  echo "== backing up first (skip with --no-backup)"
  bash "$ROOT/scripts/backup.sh" pre-reset
else
  echo "== skipping the backup (--no-backup)"
fi

if [ -n "$SERVICES" ]; then
  # db and seaweedfs always go, because the next step deletes their volumes.
  echo "== stopping db, seaweedfs and: $SERVICES"
  docker compose rm -sf db seaweedfs ${SERVICES}
else
  echo "== stopping the stack"
  docker compose down --remove-orphans
fi

echo "== deleting data/volumes"
# Bind mounts owned by the host user, so no sudo. Everything in them is
# reproducible: migrations rebuild the schema, the seed loader reloads the
# reference tables, and the KB is re-ingested from api/kb/*.md.
rm -rf data/volumes/pg data/volumes/seaweed
mkdir -p data/volumes/pg data/volumes/seaweed

echo "== starting the stack"
docker compose up -d ${BUILD_ARG} ${SERVICES}

echo "== waiting for $API/health (up to ${TIMEOUT_SECONDS}s)"
# The API applies migrations, seeds, and embeds the whole knowledge base before
# it serves, so the first green health check is the real "ready" signal.
deadline=$((SECONDS + TIMEOUT_SECONDS))
while [ "$SECONDS" -lt "$deadline" ]; do
  body="$(curl -fsS "$API/health" 2>/dev/null || true)"
  if [ -n "$body" ]; then
    ready="$(printf '%s' "$body" | python3 -c '
import json, sys
try:
    h = json.load(sys.stdin)
except Exception:
    sys.exit(0)
# /health stopped probing the model in M14 (that is /health/deep, staff-only);
# db, s3 and an ingested KB are the readiness signal.
green = all(h.get(k) == "ok" for k in ("db", "s3")) and not h.get("startup_errors")
print("yes" if green and (h.get("kb_chunks") or 0) > 0 else "no")
print(json.dumps({k: h.get(k) for k in ("status", "db", "s3", "kb_chunks", "startup_errors")}))' || true)"
    if [ "$(printf '%s' "$ready" | head -1)" = "yes" ]; then
      printf '%s\n' "$(printf '%s' "$ready" | tail -1)"
      echo
      echo "Demo is reset and healthy."
      echo "  chat        $WEB"
      echo "  staff queue $WEB/staff"
      echo "  traces      $WEB/traces"
      echo "  api health  $API/health"
      exit 0
    fi
  fi
  sleep 3
done

echo "health did not go green within ${TIMEOUT_SECONDS}s. Last response:" >&2
curl -sS "$API/health" >&2 || true
echo >&2
echo "Check: docker compose logs api --tail 50" >&2
exit 1
