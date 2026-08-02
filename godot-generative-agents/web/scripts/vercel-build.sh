#!/usr/bin/env bash
# Vercel's buildCommand (see ../vercel.json): a guard in front of `pnpm build`.
#
# The Godot Web export (public/godot/, ~52 MB) is git-ignored build output, so a
# build that runs from a *clone* — a Vercel Git deployment, or `vercel deploy`
# without --prebuilt — silently produces a site whose demo figure 404s: Vite just
# copies public/, so a missing export is not a build error. Deploys are
# local-prebuilt only (`vercel build && vercel deploy --prebuilt`, see
# ../README.md); this stops a hollow showcase page instead of shipping one.
#
# Not part of `pnpm build`: CI builds a clone on purpose (type-check + bundle
# gate) and must stay green without a 52 MB export.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"           # .../godot-generative-agents/web
cd "$WEB_DIR"

ok=1
for f in \
  public/godot/index.js \
  public/godot/index.wasm \
  public/godot/index.pck \
  public/replay/penn_replay.json
do
  if [[ ! -f "$f" ]]; then
    echo "error: missing generated asset web/$f" >&2
    ok=0
  fi
done

if [[ "$ok" != 1 ]]; then
  echo "Run 'pnpm export:godot' (and 'pnpm gen:replay') in web/, then retry." >&2
  exit 1
fi

pnpm build

# The MkDocs site is a local dev convenience (`pnpm gen:docs` → public/docs/, served
# at /docs/ by the dev middleware in vite.config.ts). It is NOT part of the public
# showcase — #882 exposes Home only — so drop it from the deployed output rather than
# depending on whoever deploys not having run gen:docs. With it gone, /docs/ falls
# through vercel.json's catch-all rewrite to the landing page like any other stray URL.
rm -rf dist/docs
