#!/usr/bin/env bash
# Deploy ONLY the phone-legible reel to
#   https://ccb.github.io/tomb-of-nassak-an-rah/animations-iphone/
#
# Unlike deploy_web.sh (which wipes and rebuilds the whole site), this adds or
# updates just the animations-iphone/ directory and leaves every other file --
# the live game, the /animations/ reel -- exactly as last deployed. The page is
# self-contained (figures.js inlined), so it cannot affect the game.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_URL="https://github.com/ccb/tomb-of-nassak-an-rah.git"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$HERE/.."
uv run python app/build_iphone_reel.py

git clone -q --depth 1 "$REPO_URL" "$WORK"
mkdir -p "$WORK/animations-iphone"
cp app/dist/animations-iphone/index.html "$WORK/animations-iphone/index.html"
touch "$WORK/.nojekyll"

cd "$WORK"
git add -A
if git diff --cached --quiet; then
    echo "nothing changed; animations-iphone already current"
    exit 0
fi
git commit -q -m "deploy(animations-iphone): $(git -C "$HERE/.." rev-parse --short HEAD) from agent-sandbox

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push -q origin main
echo "deployed -> https://ccb.github.io/tomb-of-nassak-an-rah/animations-iphone/ (live in ~1 min)"
