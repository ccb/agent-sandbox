#!/usr/bin/env bash
# Drive one headless live-LLM Penn run end to end (#760).
#
# serve_penn boots PAUSED under a paid brain, so a run is a fixed five-step
# dance: boot -> POST /config (the only way to pick a cast; there is no --cast
# flag) -> POST /resume -> poll GET /live -> GET /usage -> POST /shutdown.
# Batch 1 did this by hand and lost the script; batch 2 commits it.
#
# Two orderings here are load-bearing, both learned the hard way in batch 1:
#   * `. .env` before launching -- #776 is still open, so the backend's own
#     load_dotenv() looks one directory too shallow and never finds the key.
#   * GET /usage BEFORE /shutdown -- tokens, by_tool and by_role live only in
#     the in-process ledger. Only the USD total reaches sim.db.
#
# usage: drive_run.sh <label> <cast-csv> <max-cost> [extra serve_penn flags...]
#   e.g. drive_run.sh r6 omar,bethany,tessa,ellis,ravi,hannah,tanaka 1.50 --plan schedule
set -euo pipefail

LABEL="${1:?usage: drive_run.sh <label> <cast-csv> <max-cost> [flags...]}"
CAST="${2:?cast (comma-separated persona ids)}"
MAX_COST="${3:?max cost in USD}"
shift 3

PORT="${PORT:-8080}"
# BRAIN=mock exercises this whole sequence offline and free -- do that once
# before every batch, so a typo here costs nothing.
BRAIN="${BRAIN:-llm}"
STEPS="${STEPS:-1200}"
SEED="${SEED:-42}"
TICK="${TICK:-0.05}"
BASE="http://127.0.0.1:${PORT}"
# The repo root is three levels up from runs/issue-760-batch-2/.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT="${OUT:-$ROOT/godot-generative-agents/runs/issue-760-batch-2/$LABEL}"
mkdir -p "$OUT"

# #776: the backend cannot find a repo-root .env on its own. Already-exported
# variables still win, matching load_dotenv's own contract.
# .env is git-ignored, so a worktree never has its own copy -- fall back to the
# main checkout, which is the parent of the shared git dir.
MAIN_CHECKOUT="$(dirname "$(cd "$ROOT" && git rev-parse --path-format=absolute --git-common-dir)")"
for candidate in "$ROOT/.env" "$MAIN_CHECKOUT/.env"; do
  if [[ -f "$candidate" ]]; then set -a; . "$candidate"; set +a; break; fi
done
if [[ "$BRAIN" == "llm" ]]; then
  : "${ANTHROPIC_API_KEY:?no ANTHROPIC_API_KEY -- put one in $ROOT/.env}"
fi

echo "== $LABEL: brain=$BRAIN cast=$CAST steps=$STEPS max_cost=\$$MAX_COST flags=$*"

cd "$ROOT"
# By script path, not -m: serve_penn imports its siblings bare (`scripted_brain`),
# which only resolves with backend/penn/ on sys.path -- the documented invocation
# in .claude/commands/serve-backend.md. PYTHONPATH adds the `backend` package.
PYTHONPATH=.:godot-generative-agents uv run --no-sync python \
  godot-generative-agents/backend/penn/serve_penn.py \
  --brain "$BRAIN" --scenario penn --steps "$STEPS" --tick-seconds "$TICK" \
  --seed "$SEED" --max-cost "$MAX_COST" --decide-workers 0 --port "$PORT" \
  --start-paused "$@" >"$OUT/server.log" 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 60); do
  curl -sf "$BASE/live" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "$BASE/live" >/dev/null || { echo "server never came up"; tail -20 "$OUT/server.log"; exit 1; }

# The cast is chosen here, while the loop is paused at tick 0; POST /config
# rebuilds the world and hands back a new run id.
jq -n --arg cast "$CAST" '{cast: ($cast | split(","))}' \
  | curl -sf -X POST "$BASE/config" -H 'content-type: application/json' -d @- \
  > "$OUT/config-applied.json"
RUN_ID=$(jq -r '.run_id // .applied.run_id // empty' "$OUT/config-applied.json")
echo "   run_id=$RUN_ID"

curl -sf -X POST "$BASE/resume" >/dev/null
START=$(date +%s)

# Poll until the day ends: the loop pauses itself at --steps and on a tripped
# budget, so "paused && (step>=steps || over_budget)" is the terminal state.
while :; do
  sleep 10
  LIVE=$(curl -sf "$BASE/live" || true)
  [[ -z "$LIVE" ]] && { echo "   server vanished"; break; }
  STEP=$(jq -r '.step // .cursor // 0' <<<"$LIVE")
  OVER=$(curl -sf "$BASE/usage" | jq -r '.over_budget // false')
  PAUSED=$(jq -r '.paused // false' <<<"$LIVE")
  printf '\r   step %s/%s  paused=%s over_budget=%s  %ss elapsed' \
    "$STEP" "$STEPS" "$PAUSED" "$OVER" "$(( $(date +%s) - START ))"
  if [[ "$PAUSED" == "true" ]] && { [[ "$OVER" == "true" ]] || (( STEP >= STEPS )); }; then
    echo; break
  fi
done

# BEFORE shutdown: the ledger is in-process only.
curl -sf "$BASE/usage" > "$OUT/usage.json"
curl -sf "$BASE/live"  > "$OUT/live-final.json"
echo "   cost=\$$(jq -r '.total_cost_usd' "$OUT/usage.json") calls=$(jq -r '.calls' "$OUT/usage.json")"

curl -sf -X POST "$BASE/shutdown" >/dev/null || true
sleep 2
echo "$RUN_ID" > "$OUT/run_id.txt"
echo "== $LABEL done -> $OUT"
