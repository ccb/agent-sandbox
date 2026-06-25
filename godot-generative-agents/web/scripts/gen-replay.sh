#!/usr/bin/env bash
# Regenerate the Penn replay and drop it where the web viewer serves it. Because
# the viewer fetches this JSON at runtime, a new sim needs NO Godot re-export —
# just re-run this and refresh the browser.
#
# Any args are forwarded to the sim, e.g.:  npm run gen:replay -- --steps 600
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"           # .../godot-generative-agents/web
GODOT_PROJECT="$(cd "$WEB_DIR/.." && pwd)"         # .../godot-generative-agents
REPO_ROOT="$(cd "$GODOT_PROJECT/.." && pwd)"
SRC_JSON="$GODOT_PROJECT/maps/penn_replay.json"
DEST_JSON="$WEB_DIR/public/replay/penn_replay.json"

echo "==> Running the Penn sim…"
( cd "$REPO_ROOT" && uv run python godot-generative-agents/sim/generate_penn_replay.py "$@" )

mkdir -p "$(dirname "$DEST_JSON")"
cp "$SRC_JSON" "$DEST_JSON"
echo "==> Copied replay to $DEST_JSON"
echo "    Refresh the browser to see it (no re-export needed)."
