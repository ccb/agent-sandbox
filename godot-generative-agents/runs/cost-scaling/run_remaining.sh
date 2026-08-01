#!/usr/bin/env bash
# The two #921 cells the 2026-07-30 workspace API limit blocked (resets
# 2026-08-01 00:00 UTC). Same recipe as the rest of the batch; C-OFF must NOT
# get --cognition-tools anywhere (CLI/config/game.agent OR-resolve, #921).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DRIVER=$ROOT/godot-generative-agents/runs/issue-760-batch-4/drive_run.sh
CS=$ROOT/godot-generative-agents/runs/cost-scaling
TIER=(--model claude-sonnet-5 --effort medium
      --model-for converse=claude-haiku-4-5 --model-for score=claude-haiku-4-5
      --model-for react=claude-haiku-4-5)

STEPS=4320 SEED=42 TICK=0.05 PORT=8095 READY_TIMEOUT=900 OUT=$CS/C-OFF \
  "$DRIVER" C-OFF tanaka,maya,priya,theo,mateo 10 "${TIER[@]}" || exit 1
jq -e '.over_budget | not' "$CS/C-OFF/usage.json" >/dev/null \
  || { echo "C-OFF tripped its cap — discard, raise cap, rerun"; exit 1; }
sleep 5
STEPS=4320 SEED=42 TICK=0.05 PORT=8095 READY_TIMEOUT=900 OUT=$CS/A7 \
  "$DRIVER" A7 tanaka,maya,priya,theo,mateo,diego,sofia 14 "${TIER[@]}" --cognition-tools
