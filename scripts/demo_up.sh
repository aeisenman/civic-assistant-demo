#!/usr/bin/env bash
# Brings the demo to a ready state and opens every tab the demo script needs.
# Called by hand (`bash scripts/demo_up.sh`) or by the launchd job in
# scripts/com.municipality.demo-up.plist. Depends on: Docker Desktop, the built
# images (it never builds), the api on :8080, the web on :3001, and one cheap
# chat turn (~$0.003) to warm the Bedrock path so the first demo answer is quick.
set -uo pipefail
cd "$(dirname "$0")/.."
LOG="data/demo_up.log"; mkdir -p data
exec > >(tee -a "$LOG") 2>&1
echo "== demo_up $(date '+%Y-%m-%d %H:%M:%S')"
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

# Everything that shells out to `open` is macOS-only; on Linux the script still
# brings the stack up and warms it, it just cannot start Docker Desktop or open
# tabs. Guarding rather than assuming keeps it runnable on a CI box or an EC2 host.
IS_MAC=0; [ "$(uname)" = "Darwin" ] && IS_MAC=1

# 1. Docker Desktop. AutoStart is off on this Mac, so start it if the daemon is down.
if ! docker info >/dev/null 2>&1; then
  if [ "$IS_MAC" = "1" ]; then
    echo "docker daemon not running; starting Docker Desktop"
    open -a Docker
    for i in $(seq 1 60); do sleep 3; docker info >/dev/null 2>&1 && break; done
  else
    echo "docker daemon not running and this is not macOS; start it yourself"
  fi
fi
docker info >/dev/null 2>&1 || { echo "FAIL: docker never came up"; exit 1; }

# 2. The credential helper blocks non-interactive shells (STATE.md); use the copy without it.
if [ -f "$HOME/.docker/config.json" ] && grep -q credsStore "$HOME/.docker/config.json"; then
  rm -rf /tmp/dockercfg; mkdir -p /tmp/dockercfg
  cp -R "$HOME/.docker/contexts" /tmp/dockercfg/ 2>/dev/null || true
  python3 - <<'PY'
import json, os
src = os.path.join(os.environ["HOME"], ".docker", "config.json")
d = json.load(open(src)); d.pop("credsStore", None)
json.dump(d, open("/tmp/dockercfg/config.json", "w"))
PY
  export DOCKER_CONFIG=/tmp/dockercfg
fi

# 3. Containers (no build: the images on disk are the verified ones).
docker compose up -d 2>&1 | grep -v "^$" | tail -6

# 4. Health.
H=""
for i in $(seq 1 40); do sleep 3; H=$(curl -s -m 3 localhost:8080/health); echo "$H" | grep -q '"status":"ok"' && break; done
echo "$H" | grep -q '"status":"ok"' || { echo "FAIL: api health not ok: $H"; exit 1; }
CH=$(echo "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['kb_chunks'])")
echo "health ok, kb_chunks=$CH"
[ "$CH" = "120" ] || echo "WARN: kb_chunks is $CH, expected 120"
for i in $(seq 1 20); do curl -s -m 3 -o /dev/null -w "%{http_code}" localhost:3001/ | grep -q 200 && break; sleep 3; done
echo "web $(curl -s -m 3 -o /dev/null -w '%{http_code}' localhost:3001/)"

# 5. Warm the model path with one cheap turn and prove Bedrock answers.
R=$(curl -s -m 60 -X POST -H "Content-Type: application/json" \
  -d '{"session_id":"demo-warmup","message":"hi"}' localhost:8080/api/chat)
echo "$R" | python3 -c "import sys,json;r=json.load(sys.stdin);t=r.get('trace') or {};print('warm-up ok:',t.get('tier'),t.get('latency_ms'),'ms $',t.get('cost_usd'),'error' if t.get('error') else '')" \
  || { echo "FAIL: warm-up turn failed: $R"; exit 1; }

# 6. Staff login works with the shipped credentials.
curl -s -m 10 -o /dev/null -w "staff login %{http_code}\n" -X POST -H "Content-Type: application/json" \
  -d '{"username":"staff","password":"staff"}' localhost:8080/api/auth/login

# 7. Open everything the demo script uses (macOS only; `open` does not exist elsewhere).
if [ "$IS_MAC" = "1" ]; then
  open "http://localhost:3001/"
  open "http://localhost:3001/staff"
  open "http://localhost:3001/staff/dashboard"
  open "http://localhost:3001/staff/traces"
  open "https://claude.ai/code/artifact/bc49c3c8-c01c-4de3-9d04-3405c441070e"
  open "api/forms"
  echo "READY $(date '+%H:%M:%S') — chat, staff queue (login staff/staff), dashboard, traces, walkthrough and the sample-PDF folder are open."
else
  echo "READY $(date '+%H:%M:%S') — chat on :3001, staff queue (login staff/staff), /staff/dashboard, /staff/traces; open them yourself."
fi
