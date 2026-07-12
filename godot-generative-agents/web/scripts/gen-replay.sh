#!/usr/bin/env bash
# Regenerate the Penn replay and drop it where the web viewer serves it. Because
# the viewer fetches this JSON at runtime, a new sim needs NO Godot re-export —
# just re-run this and refresh the browser.
#
# Any args are forwarded to the sim, e.g.:  pnpm gen:replay --steps 600
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"           # .../godot-generative-agents/web
GG_DIR="$(cd "$WEB_DIR/.." && pwd)"                # .../godot-generative-agents
REPO_ROOT="$(cd "$GG_DIR/.." && pwd)"
# The bake writes into the Godot project (godot/, split out in #400).
SRC_JSON="$GG_DIR/godot/maps/penn_replay.json"
DEST_JSON="$WEB_DIR/public/replay/penn_replay.json"

echo "==> Running the Penn sim…"
( cd "$REPO_ROOT" && uv run python godot-generative-agents/backend/penn/generate_penn_replay.py "$@" )

mkdir -p "$(dirname "$DEST_JSON")"
cp "$SRC_JSON" "$DEST_JSON"
echo "==> Copied replay to $DEST_JSON"
echo "    Refresh the browser to see it (no re-export needed)."
