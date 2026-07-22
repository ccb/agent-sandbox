#!/usr/bin/env bash
# Headless smoke test: run pure GDScript unit tests, then load every content scene
# and assert its campus map painted. Exit 0 = all tests and scenes OK; non-zero =
# a test failed, or a scene failed to load or painted no tiles (a broken .tmj /
# tileset / scene reference). Catches regressions in CI or before you push.
#
#   ./godot-generative-agents/run_smoke_test.sh
#
# Works from any directory (it finds the project relative to this script) and finds
# Godot on your PATH or in the standard macOS app bundle. A missing
# maps/penn_replay.json is fine: the replay scene still renders the campus, only the
# agent sprites are absent (Godot prints a harmless "cannot open" warning).
set -euo pipefail

# The Godot project is the godot/ subfolder next to this script (its siblings
# backend/ and web/ are not part of the game).
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/godot" && pwd)"

# Find a Godot 4 binary: PATH first, then the standard macOS app bundle.
GODOT="$(command -v godot || command -v godot4 || true)"
if [[ -z "$GODOT" && -x "/Applications/Godot.app/Contents/MacOS/Godot" ]]; then
  GODOT="/Applications/Godot.app/Contents/MacOS/Godot"
fi
if [[ -z "$GODOT" ]]; then
  echo "Godot 4 not found. Install it, or put it on your PATH as 'godot'." >&2
  echo "(Looked for: godot, godot4, /Applications/Godot.app/Contents/MacOS/Godot)" >&2
  exit 1
fi

# First run on a clean checkout builds the .godot/ import cache; do it quietly so
# import chatter doesn't drown the test result. Import failure isn't fatal here —
# the smoke test below will fail loudly if an asset is genuinely missing.
"$GODOT" --headless --path "$PROJECT_DIR" --import >/dev/null 2>&1 || true

# Headless unit tests (pure-GDScript helpers) run before the scene smoke; set -e
# makes a red unit test fail the whole script. Godot can exit 0 on a script
# PARSE error under --script (assertion failures quit(1) fine), so also require
# the success sentinel the test prints — grep -q + pipefail fails either way.
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_replay_markers.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_action_tally.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_day_plan_model.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_snapshot_export.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_gif_encoder.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_clip_export.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_thinking_indicator.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_agent_fanout.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_deciding_indicator.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_live_pacer.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_live_clip_span.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_restart_detect.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_run_state.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_payload_guards.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_replay_save.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"

# exec so this script's exit code IS the smoke test's quit code (0 pass / 1 fail).
exec "$GODOT" --headless --path "$PROJECT_DIR" res://scenes/smoke_test.tscn
