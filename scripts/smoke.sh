#!/usr/bin/env bash
# End-to-end check of the M3 workflow: upload a form, watch the engine route it,
# advance it by hand, download the certificate, then do the needs_info loop, the
# business tax path and (M24) the short-term rental licence path. Run against a
# live stack (docker compose up -d).
# Usage: bash scripts/smoke.sh [base_url]   (default http://localhost:8080)
#
# Since M11 the staff half of that path needs a session, so the script signs in
# first and keeps the cookie in a jar. Credentials come from
# STAFF_USERNAME/STAFF_PASSWORD, defaulting to the seeded demo account. Signing
# in is a precondition, not a numbered check, so a passing run prints 13 PASS
# lines (11 up to M20, plus the two M24 added for the STRO path: the tracking
# number and the status it reaches unaided).
#
# Since M20 the resident half needs a jar of its own: the first upload or chat
# turn on $SESSION is handed a `resident_session` cookie, and every later
# request on that id has to send it back or the API answers 403. Two jars, not
# one, because staff and resident are two different callers here.
#
# SMOKE_MODEL=stub drops the checks that can only pass with a real model behind
# the API — the ones that read a fee out of a chat reply, or need the extractor
# to pull fields off a PDF. CI runs against scripts/ci/stub_openai.py, which
# answers every classification "smalltalk" and every answer with one fixed
# sentence, so those checks would be asserting the stub, not the system. What is
# left still covers the whole workflow spine: forms schema, document upload, an
# application filed through the inline-form path, the worker routing it to
# in_review, staff sign-in, two advances and the certificate PDF. Every run
# prints the list of checks it performed at the end.

set -uo pipefail

BASE="${1:-http://localhost:8080}"
FORMS="$(cd "$(dirname "$0")/.." && pwd)/api/forms"
SESSION="smoke-$(date +%s)"
# The XXXXXX is required: BSD mktemp appends a suffix on its own, GNU coreutils
# refuses a template with "too few X's", so without it the script dies on Linux.
COOKIES="$(mktemp -t civic-smoke-cookies.XXXXXX)"
RESIDENT_COOKIES="$(mktemp -t civic-smoke-resident.XXXXXX)"
trap 'rm -f "$COOKIES" "$RESIDENT_COOKIES"' EXIT
FAILURES=0
# "real" (the default) runs every check; "stub" runs only the ones that do not
# depend on what the model says. Bash 3.2: no arrays worth the trouble, so the
# list of checks performed is one newline-separated string.
MODE="${SMOKE_MODEL:-real}"
RAN=""

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
check() {
  RAN="$RAN  $2
"
  if [ "$1" = "1" ]; then pass "$2"; else fail "$2${3:+ — $3}"; fi
}
skip() { printf 'SKIP  %s — needs a real model (SMOKE_MODEL=%s)\n' "$1" "$MODE"; }

# Read one dotted key out of a JSON blob on stdin; prints "" when absent.
jget() { python3 -c '
import json,sys
try: data = json.load(sys.stdin)
except Exception: sys.exit(0)
for key in sys.argv[1].split("."):
    if isinstance(data, list): data = data[int(key)]
    elif isinstance(data, dict): data = data.get(key)
    else: data = None
    if data is None: sys.exit(0)
print(data)' "$1"; }

# The resident half of the script is one browser: -c writes the cookie the first
# request is given, -b sends it on every one after that.
resident_curl() { curl -s -c "$RESIDENT_COOKIES" -b "$RESIDENT_COOKIES" "$@"; }

upload() {
  resident_curl -X POST "$BASE/api/documents" \
    -F "file=@$1;type=application/pdf" -F "session_id=$SESSION"
}

say() {
  python3 -c '
import json,sys
print(json.dumps({"session_id": sys.argv[1], "message": sys.argv[2],
                  "document_ids": [int(x) for x in sys.argv[3:] if x]}))' "$SESSION" "$@" |
    resident_curl -X POST "$BASE/api/chat" -H 'content-type: application/json' -d @-
}

# Every staff call goes through the cookie jar filled in by the sign-in below.
staff_curl() { curl -s -b "$COOKIES" "$@"; }

app_field() { staff_curl "$BASE/api/applications/$1" | jget "$2"; }

# Poll an application until it reaches $2, up to $3 seconds.
wait_for_status() {
  local tracking="$1" want="$2" limit="${3:-30}" i=0 status=""
  while [ "$i" -lt "$limit" ]; do
    status="$(app_field "$tracking" status)"
    [ "$status" = "$want" ] && { echo "$status"; return 0; }
    sleep 1
    i=$((i + 1))
  done
  echo "$status"
  return 1
}

# File an application straight through the inline-form endpoint: same engine,
# same validators, same tracking sequence as an extracted PDF, but no model.
form_file() {
  python3 -c '
import json,sys
print(json.dumps({"type": "permit", "session_id": sys.argv[1], "fields": {
    "applicant_name": "Smoke Tester",
    "applicant_email": "smoke@example.gov",
    "project_address": "202 C Street, San Diego, CA 92101",
    "permit_type": "Building Permit with Plans",
    "project_description": "Replace the kitchen window in a single-family home.",
    "valuation_usd": 12000.0,
    "square_feet": 40,
    "owner_builder": True}}))' "$SESSION" |
    resident_curl -X POST "$BASE/api/applications" -H 'content-type: application/json' -d @-
}

echo "== smoke against $BASE (session $SESSION, SMOKE_MODEL=$MODE)"

# ---------------------------------------------------------------- 1. health
HEALTH="$(curl -s "$BASE/health")"
[ "$(echo "$HEALTH" | jget status)" = "ok" ] && check 1 "health is ok" ||
  check 0 "health is ok" "$HEALTH"

# ------------------------------------------------- 1b. staff sign-in (M11)
LOGIN="$(python3 -c '
import json,sys
print(json.dumps({"username": sys.argv[1], "password": sys.argv[2]}))' \
  "${STAFF_USERNAME:-staff}" "${STAFF_PASSWORD:-staff}" |
  curl -s -c "$COOKIES" -X POST "$BASE/api/auth/login" \
    -H 'content-type: application/json' -d @-)"
WHO="$(echo "$LOGIN" | jget display_name)"
if [ -z "$WHO" ]; then
  fail "staff sign-in as '${STAFF_USERNAME:-staff}' — $LOGIN"
  echo "== cannot continue without a staff session"
  exit 1
fi
echo "      (signed in as $WHO)"

# ------------------------------------------- 2-3. upload + chat -> application
DOC="$(upload "$FORMS/sample_permit_application.pdf" | jget document_id)"
[ -n "$DOC" ] && check 1 "uploaded sample_permit_application.pdf (document $DOC)" ||
  check 0 "uploaded sample_permit_application.pdf"

if [ "$MODE" = "stub" ]; then
  # The form schema the web app renders, straight from the pydantic model. No
  # model involved, and it is what the inline-form path below is validated by.
  FIELDS="$(curl -s "$BASE/api/forms/permit" | jget fields.0.name)"
  [ -n "$FIELDS" ] && check 1 "GET /api/forms/permit returns a field list (first: $FIELDS)" ||
    check 0 "GET /api/forms/permit returns a field list"

  skip "chat filed the permit"
  FORMED="$(form_file)"
  TRACKING="$(echo "$FORMED" | jget tracking_number)"
  case "$TRACKING" in
    PRM-*) check 1 "inline form filed the permit as $TRACKING" ;;
    *) check 0 "inline form filed the permit" "$FORMED" ;;
  esac
else
  CHAT="$(say "Here is my permit application." "$DOC")"
  TRACKING="$(echo "$CHAT" | jget actions.0.tracking_number)"
  case "$TRACKING" in
    PRM-*) check 1 "chat filed the permit as $TRACKING" ;;
    *) check 0 "chat filed the permit" "$(echo "$CHAT" | jget reply)" ;;
  esac
fi

# ------------------------------------------------------ 4. worker routes it
if [ -n "$TRACKING" ]; then
  STATUS="$(wait_for_status "$TRACKING" in_review 30)"
  [ "$STATUS" = "in_review" ] && check 1 "$TRACKING reached in_review" ||
    check 0 "$TRACKING reached in_review" "stuck at '$STATUS'"

  # --------------------------------------------- 5-6. staff advances it
  for TO in approved issued; do
    OUT="$(staff_curl -X POST "$BASE/api/applications/$TRACKING/advance" \
      -H 'content-type: application/json' -d "{\"to\":\"$TO\"}")"
    [ "$(echo "$OUT" | jget status)" = "$TO" ] && check 1 "advanced $TRACKING to $TO" ||
      check 0 "advanced $TRACKING to $TO" "$OUT"
  done

  # ------------------------------------------------- 7. certificate is a PDF
  MAGIC="$(staff_curl "$BASE/api/applications/$TRACKING/certificate" | head -c 4)"
  [ "$MAGIC" = "%PDF" ] && check 1 "certificate for $TRACKING downloads as a PDF" ||
    check 0 "certificate for $TRACKING downloads as a PDF" "first bytes '$MAGIC'"
fi

# The rest of the script asserts what the model produced: which fields the
# extractor found on a half-filled PDF, whether the follow-up turn filled the
# gaps, and the fee quoted in a chat reply. Against the CI stub all three are
# assertions about a fixed string, so they are skipped rather than weakened.
if [ "$MODE" = "stub" ]; then
  skip "incomplete form stopped at needs_info"
  skip "needs_info application reached in_review after the follow-up"
  skip "chat filed the business tax application"
  skip "business tax application has an estimated fee"
  echo "== checks performed"
  printf '%s' "$RAN"
  echo "== $FAILURES failure(s)"
  [ "$FAILURES" -eq 0 ] || exit 1
  exit 0
fi

# ------------------------------------------- 8. incomplete form -> needs_info
DOC2="$(upload "$FORMS/sample_permit_incomplete.pdf" | jget document_id)"
CHAT2="$(say "And here is the one for the garage." "$DOC2")"
TRACKING2="$(echo "$CHAT2" | jget actions.0.tracking_number)"
STATUS2="$(wait_for_status "${TRACKING2:-none}" needs_info 15)"
[ "$STATUS2" = "needs_info" ] && check 1 "$TRACKING2 stopped at needs_info" ||
  check 0 "incomplete form stopped at needs_info" "status '$STATUS2'"

# ----------------------------------------- 9. resident fills the gaps in chat
if [ "$STATUS2" = "needs_info" ]; then
  say "The permit type is Building Permit with Plans and the valuation is \$80,000" >/dev/null
  STATUS3="$(wait_for_status "$TRACKING2" in_review 30)"
  [ "$STATUS3" = "in_review" ] && check 1 "$TRACKING2 reached in_review after the follow-up" ||
    check 0 "$TRACKING2 reached in_review after the follow-up" \
      "stuck at '$STATUS3', still missing $(app_field "$TRACKING2" missing_fields)"
fi

# ------------------------------------------------- 10. business tax path
DOC3="$(upload "$FORMS/sample_business_tax_application.pdf" | jget document_id)"
CHAT3="$(say "I'd like to register my coffee shop." "$DOC3")"
TRACKING3="$(echo "$CHAT3" | jget actions.0.tracking_number)"
case "$TRACKING3" in
  BTC-*) check 1 "chat filed the business tax application as $TRACKING3" ;;
  *) check 0 "chat filed the business tax application" "$(echo "$CHAT3" | jget reply)" ;;
esac
if [ -n "$TRACKING3" ]; then
  wait_for_status "$TRACKING3" in_review 30 >/dev/null
  FEE="$(app_field "$TRACKING3" fee_usd)"
  [ -n "$FEE" ] && check 1 "$TRACKING3 has an estimated fee of \$$FEE" ||
    check 0 "$TRACKING3 has an estimated fee" "missing: $(app_field "$TRACKING3" missing_fields)"
fi

# ------------------------------- 12-13. short-term rental (STRO) licence path
if [ "$MODE" = "stub" ]; then
  skip "chat filed the STRO licence application (extractor)"
else
DOC4="$(upload "$FORMS/sample_stro_application.pdf" | jget document_id)"
CHAT4="$(say "Here is my short-term rental licence application." "$DOC4")"
TRACKING4="$(echo "$CHAT4" | jget actions.0.tracking_number)"
case "$TRACKING4" in
  STR-*) check 1 "chat filed the STRO licence application as $TRACKING4" ;;
  *) check 0 "chat filed the STRO licence application" "$(echo "$CHAT4" | jget reply)" ;;
esac
if [ -n "$TRACKING4" ]; then
  STATUS4="$(wait_for_status "$TRACKING4" in_review 30)"
  [ "$STATUS4" = "in_review" ] && check 1 "$TRACKING4 reached in_review" ||
    check 0 "$TRACKING4 reached in_review" \
      "stuck at '$STATUS4', still missing $(app_field "$TRACKING4" missing_fields)"
fi
fi

echo "== checks performed"
printf '%s' "$RAN"
echo "== $FAILURES failure(s)"
[ "$FAILURES" -eq 0 ] || exit 1
