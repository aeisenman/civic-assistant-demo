#!/usr/bin/env bash
# Prints the Bedrock spend recorded by this app (sum of trace cost estimates) and, when the
# aws CLI is configured, this month's Bedrock cost from AWS Cost Explorer, per model service (the ground truth;
# the whole account, so other projects on the same account show up too).
# Called by hand and by Fable before/after each verification run. Depends on: the db container
# (docker compose exec) and optionally the aws CLI.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== app-side estimate (traces.cost_usd, all time) =="
docker compose exec -T db psql -U civic -d civic -At -c \
  "select count(*) || ' turns, \$' || round(coalesce(sum(cost_usd),0)::numeric, 4) || ' estimated; today \$' || round(coalesce(sum(cost_usd) filter (where created_at::date = current_date),0)::numeric, 4) from traces"
if command -v aws >/dev/null 2>&1; then
  echo "== AWS Cost Explorer, month to date (unblended), by service =="
  # Bedrock bills model usage under per-model services ("Claude Sonnet 4.6 (Bedrock Edition)"),
  # not under "Amazon Bedrock", which only carries a few cents of platform charges. Group by
  # service and keep every line that mentions Bedrock so the total is the real one.
  START=$(date +%Y-%m-01); END=$(date -v+1d +%Y-%m-%d 2>/dev/null || date -d tomorrow +%Y-%m-%d)
  aws ce get-cost-and-usage --time-period Start="$START",End="$END" --granularity MONTHLY \
    --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE \
    --query 'ResultsByTime[0].Groups[?contains(Keys[0], `Bedrock`)].[Keys[0], Metrics.UnblendedCost.Amount]' \
    --output text 2>&1 | awk -F'\t' '{printf "  %-45s $%.4f\n", $1, $2; t+=$2} END {printf "  %-45s $%.4f\n", "total (all Bedrock services, whole account)", t}' \
    || echo "(cost explorer unavailable)"
fi
echo "Budget for phase 2 testing: \$10.00 (author, 2026-09-05). Log each run in STATE.md 'Spend ledger'."
