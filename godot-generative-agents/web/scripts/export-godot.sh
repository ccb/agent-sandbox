#!/usr/bin/env bash
# Export the Godot project to a Web (WebAssembly) build under web/public/godot/.
# Run this once, and again whenever the Godot scripts/scenes/art change. New
# *replay* data does NOT need this — see gen-replay.sh.
#
# Requires Godot 4.6.x with the matching **Web export templates** installed
# (Godot editor -> Editor -> Manage Export Templates -> Download and Install).
# Override the binary with: GODOT_BIN=/path/to/Godot pnpm export:godot
set -euo pipefail

GODOT_BIN="${GODOT_BIN:-/Applications/Godot.app/Contents/MacOS/Godot}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"              # .../godot-generative-agents/web
GODOT_PROJECT="$(cd "$WEB_DIR/../godot" && pwd)"     # .../godot-generative-agents/godot
OUT_DIR="$WEB_DIR/public/godot"
PROJECT_FILE="$GODOT_PROJECT/project.godot"

if [[ ! -x "$GODOT_BIN" ]]; then
  echo "error: Godot binary not found at '$GODOT_BIN'." >&2
  echo "       Set GODOT_BIN to your Godot 4.6 executable and retry." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

# The web build boots the landing menu, same as desktop — but on web the menu
# reduces itself to a single "Start replay" button (issue #903, PR #928 review):
# the reader gets an explicit start affordance instead of landing mid-scene, and
# none of the live-backend / past-runs controls #879 keeps out of public
# navigation. That gating lives in godot/scripts/main_menu.gd, keyed on
# OS.has_feature("web"). We still force the boot scene explicitly for the export
# so the web entry point stays pinned even if the desktop main scene changes,
# then restore project.godot no matter what happens. (The bundled replay isn't
# packed into the build — the viewer fetches it over HTTP, web_replay_url.)
BACKUP="$(mktemp)"
cp "$PROJECT_FILE" "$BACKUP"
restore() { cp "$BACKUP" "$PROJECT_FILE"; rm -f "$BACKUP"; }
trap restore EXIT
sed -i.bak 's|^run/main_scene=.*|run/main_scene="res://scenes/main_menu.tscn"|' "$PROJECT_FILE"
rm -f "$PROJECT_FILE.bak"

echo "==> Importing assets (first run can take a minute)…"
"$GODOT_BIN" --headless --path "$GODOT_PROJECT" --import

echo "==> Exporting Web build to $OUT_DIR/index.html …"
"$GODOT_BIN" --headless --path "$GODOT_PROJECT" --export-release "Web" "$OUT_DIR/index.html"

echo "==> Done. Web build written to $OUT_DIR"
echo "    Start the viewer with:  pnpm dev"
