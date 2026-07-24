#!/usr/bin/env bash
# Precompute the prompt-chain visualizer's data into public/promptviz/ so the
# React "Prompt chains" view can render it with no backend. promptviz normally
# runs as a Flask app; gen_promptviz.py dumps the same offline graph + prompts.
# Re-run when a chain spec or its .prompty templates change, then refresh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"           # .../godot-generative-agents/web
GODOT_PROJECT="$(cd "$WEB_DIR/.." && pwd)"         # .../godot-generative-agents
REPO_ROOT="$(cd "$GODOT_PROJECT/.." && pwd)"

echo "==> Dumping prompt-chain JSON…"
# Run from the repo root so both text_adventure_games and backend import.
( cd "$REPO_ROOT" && uv run python "$WEB_DIR/scripts/gen_promptviz.py" )

echo "    Serve the app (pnpm dev / pnpm preview) and open the Prompt chains view."
