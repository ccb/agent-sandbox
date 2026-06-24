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

# The replay reads maps/penn_replay.json, which is git-ignored (regenerated per
# checkout). Nudge the user if it's missing instead of opening to an empty map.
if [[ "$SCENE" == *penn_replay* && ! -f "$PROJECT_DIR/maps/penn_replay.json" ]]; then
  echo "No maps/penn_replay.json yet — generate it first (from the repo root):" >&2
  echo "  uv run python tools/geo/osm_to_ville.py --area core --out godot-generative-agents/sim/the_upenn" >&2
  echo "  LLM_PROVIDER=mock uv run python godot-generative-agents/sim/generate_penn_replay.py" >&2
  exit 1
fi

exec "$GODOT" --path "$PROJECT_DIR" "res://$SCENE"
