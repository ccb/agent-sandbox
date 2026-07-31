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

# The web build boots straight into the replay viewer (issue #903), NOT the
# landing menu the desktop build uses. On the public landing-page figure the menu
# is a dead click (the reader already asked for the demo) and it surfaces the
# live-backend and past-runs controls #879 keeps out of public navigation. Forced
# for the export ONLY -- the committed project.godot and the desktop launch stay
# menu-first -- and project.godot is restored no matter what happens below. The
# viewer, launched directly on web, falls through to fetching the bundled replay
# over HTTP (it isn't packed into the build); the menu stays reachable via the
# viewer's back button.
BACKUP="$(mktemp)"
cp "$PROJECT_FILE" "$BACKUP"
restore() { cp "$BACKUP" "$PROJECT_FILE"; rm -f "$BACKUP"; }
trap restore EXIT
sed -i.bak 's|^run/main_scene=.*|run/main_scene="res://scenes/viewer.tscn"|' "$PROJECT_FILE"
rm -f "$PROJECT_FILE.bak"

echo "==> Importing assets (first run can take a minute)…"
"$GODOT_BIN" --headless --path "$GODOT_PROJECT" --import

echo "==> Exporting Web build to $OUT_DIR/index.html …"
"$GODOT_BIN" --headless --path "$GODOT_PROJECT" --export-release "Web" "$OUT_DIR/index.html"

echo "==> Done. Web build written to $OUT_DIR"
echo "    Start the viewer with:  pnpm dev"
