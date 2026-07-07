#!/usr/bin/env bash
# Launch the Generative Agents Godot game. It opens the landing menu (issue #399),
# where you choose how to enter the viewer — watch the bundled replay, open a local
# replay file, or connect to a live backend. The mode is an in-game choice now, not
# a command-line flag: just run the game and pick.
#
#   ./godot-generative-agents/run.sh                          # the landing menu (default)
#   ./godot-generative-agents/run.sh scenes/viewer.tscn       # skip straight into the viewer
#   ./godot-generative-agents/run.sh scenes/campus_urban.tscn # a different scene
#
# Works from any directory (it finds the project relative to this script) and finds
# Godot on your PATH or in the standard macOS app bundle.
set -euo pipefail

# This script lives at godot-generative-agents/; the Godot project is the godot/
# subfolder next to it (backend/ and web/ are its siblings, not part of the game).
GG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$GG_DIR/godot"

# Optional scene to open, relative to the project. With none, Godot boots the
# project's main scene (the landing menu). A leading "res://" is optional.
SCENE="${1:-}"
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

# godot/maps/penn_replay.json is a *baked* artifact: backend/penn/generate_penn_replay.py
# runs the sim against the committed collision matrix + world data and freezes the
# agent paths into JSON. It's git-ignored (regenerated per checkout), and the viewer
# only plays it back — it never re-reads the matrix. So it can silently fall out of
# date when its inputs change (a new building, a moved persona, …). The menu's "Play
# the bundled replay" needs it; if it's missing or stale we just say so here — the
# menu still opens, so you can run live or open a different file instead. Re-bake with
# the command below — do NOT run osm_to_ville.py to refresh it: that regenerates the
# matrix from OSM at a possibly different grid size and would overwrite committed
# edits (e.g. the walled-off lawns). Only reshape the campus with osm_to_ville when
# you actually mean to.
REPLAY_JSON="$PROJECT_DIR/maps/penn_replay.json"
BAKE_CMD="LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py"
# Files the bake reads; if any is newer than the baked replay, the replay is stale.
REPLAY_INPUTS=(
  "$GG_DIR/backend/penn/the_upenn/matrix/maze/collision_maze.csv"
  "$GG_DIR/backend/penn/world_data_upenn.yaml"
)
if [[ ! -f "$REPLAY_JSON" ]]; then
  echo "Note: no baked replay at godot/maps/penn_replay.json yet. 'Play the bundled" >&2
  echo "      replay' needs it — bake it (from the repo root) with:" >&2
  echo "        $BAKE_CMD" >&2
else
  for input in "${REPLAY_INPUTS[@]}"; do
    if [[ -f "$input" && "$input" -nt "$REPLAY_JSON" ]]; then
      echo "⚠️  godot/maps/penn_replay.json is older than $(basename "$input") — the" >&2
      echo "    bundled replay may not reflect the latest map/world (re-bake to refresh):" >&2
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

# No scene arg → boot the project's main scene (the landing menu).
if [[ -n "$SCENE" ]]; then
  exec "$GODOT" --path "$PROJECT_DIR" "res://$SCENE"
else
  exec "$GODOT" --path "$PROJECT_DIR"
fi
