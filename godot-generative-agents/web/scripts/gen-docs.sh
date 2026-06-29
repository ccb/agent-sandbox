#!/usr/bin/env bash
# Build the MkDocs site and drop it where the web viewer serves it, so the docs
# live at /docs/ under the SAME origin as the replay app. The "Docs" link in the
# app header just points at this static output — no Godot re-export needed; build
# the docs, then `pnpm dev` / `pnpm preview` and open /docs/.
#
# Re-run this whenever the docs change (and after `update-mkdocs` resyncs the API
# reference). The output lands in public/docs/, which is git-ignored.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"           # .../godot-generative-agents/web
GODOT_PROJECT="$(cd "$WEB_DIR/.." && pwd)"         # .../godot-generative-agents
REPO_ROOT="$(cd "$GODOT_PROJECT/.." && pwd)"
MKDOCS_DIR="$REPO_ROOT/mkdocs"
DEST_DIR="$WEB_DIR/public/docs"

echo "==> Building the MkDocs site…"
# --strict fails on dangling links / unresolved API refs. --site-dir takes an
# absolute path, so mkdocs writes straight into public/docs/ (it cleans that dir
# first). uv run --extra docs pulls in the docs deps on the fly.
( cd "$MKDOCS_DIR" && uv run --extra docs mkdocs build --strict --site-dir "$DEST_DIR" )

echo "==> Built docs to $DEST_DIR"
echo "    Serve the app (pnpm dev / pnpm preview) and click \"Docs\" (opens /docs/)."
