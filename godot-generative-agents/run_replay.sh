#!/usr/bin/env bash
# Open the UPenn campus replay in Godot, so you don't have to remember the path.
#
#   ./godot-generative-agents/run_replay.sh                       # penn_replay.tscn
#   ./godot-generative-agents/run_replay.sh scenes/campus_urban.tscn   # a different scene
#
# Works from any directory (it finds the project relative to this script) and
# finds Godot on your PATH or in the standard macOS app bundle.
set -euo pipefail

# The Godot project is the directory this script lives in.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Scene to open, relative to the project (default: the agent replay). A leading
# "res://" is optional.
SCENE="${1:-scenes/penn_replay.tscn}"
SCENE="${SCENE#res://}"

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

# maps/penn_replay.json is a *baked* artifact: generate_penn_replay.py runs the sim
# against the committed collision matrix + world data and freezes the agent paths
# into JSON. It's git-ignored (regenerated per checkout), and the Godot viewer only
# plays it back — it never re-reads the matrix. So it can silently fall out of date
# when its inputs change underneath it (a new building, a moved persona, the grass
# block, …). Re-bake with this single command — do NOT run osm_to_ville.py here:
# that regenerates the matrix from OSM at a possibly different grid size and would
# overwrite committed edits (e.g. the walled-off lawns). Only reshape the campus
# with osm_to_ville when you actually mean to.
REPLAY_JSON="$PROJECT_DIR/maps/penn_replay.json"
BAKE_CMD="LLM_PROVIDER=mock uv run python godot-generative-agents/sim/generate_penn_replay.py"
# Files the bake reads; if any is newer than the baked replay, the replay is stale.
REPLAY_INPUTS=(
  "$PROJECT_DIR/sim/the_upenn/matrix/maze/collision_maze.csv"
  "$PROJECT_DIR/sim/world_data_upenn.yaml"
)

# Live mode (issue #263): with a backend URL configured the scene follows a
# running sim over HTTP/WS and never reads the baked file, so the bake checks
# below don't apply.
if [[ "$SCENE" == *penn_replay* && -n "${SIM_API_URL:-}" ]]; then
  echo "Live mode: following $SIM_API_URL (no baked replay needed)." >&2
elif [[ "$SCENE" == *penn_replay* ]]; then
  if [[ ! -f "$REPLAY_JSON" ]]; then
    # Missing entirely — bake it before we open to an empty map.
    echo "No maps/penn_replay.json yet — bake it first (from the repo root):" >&2
    echo "  $BAKE_CMD" >&2
    exit 1
  fi
  # Present but possibly stale — warn (don't block: you may want the old one).
  for input in "${REPLAY_INPUTS[@]}"; do
    if [[ -f "$input" && "$input" -nt "$REPLAY_JSON" ]]; then
      echo "⚠️  maps/penn_replay.json is older than $(basename "$input") — the replay" >&2
      echo "    may not reflect the latest map/world (re-bake to refresh it):" >&2
      echo "      $BAKE_CMD" >&2
      break
    fi
  done
fi

# Compile any assets whose import cache is missing. Godot stores each asset as a
# committed source file + .import sidecar, but the compiled result lives in the
# git-ignored, per-machine .godot/ cache. A fresh checkout (or a pull that added
# art) therefore has the sources but no cache, so textures fail to load and themed
# UI renders broken. Opening the editor would import them; launching a scene
# directly does not — so do it here. The import is incremental: slow only the first
# time, a quick scan afterwards.
echo "Importing assets (first run compiles them; later runs are a quick scan)…" >&2
"$GODOT" --headless --path "$PROJECT_DIR" --import

exec "$GODOT" --path "$PROJECT_DIR" "res://$SCENE"
