#!/usr/bin/env bash
#
# Populate generative-agents/frontend/ from the upstream generative_agents clone.
#
# Copies the Django visualizer + the ~38MB of the_ville map/sprite assets, but
# NOT the ~1GB of pre-baked example simulations (we generate our own). Also
# brings in the 25-resident base sim (~500KB), whose initial tile positions and
# per-persona memory the backend reuses. Idempotent: safe to re-run; never
# touches a sim you generated under frontend/storage/ (that path is preserved).
#
# Usage:  ./setup.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/../external/generative_agents/environment/frontend_server"
DST="$HERE/frontend"
BASE_SIM="base_the_ville_n25"

if [ ! -d "$SRC" ]; then
  echo "ERROR: upstream frontend not found at:" >&2
  echo "  $SRC" >&2
  echo "Clone it first, e.g.:" >&2
  echo "  git clone https://github.com/joonspk-research/generative_agents.git \\" >&2
  echo "    $HERE/../external/generative_agents" >&2
  exit 1
fi

echo "Copying Django frontend + the_ville assets (excluding the ~1GB example sims)..."
mkdir -p "$DST"
# --delete keeps DST in sync with SRC, but excluded paths (storage/, etc.) are
# left untouched, so a sim you generated under frontend/storage/ survives re-runs.
rsync -a --delete \
  --exclude 'storage/' \
  --exclude 'compressed_storage/' \
  --exclude 'temp_storage/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$SRC/" "$DST/"

# Runtime dirs the frontend expects to exist (empty is fine).
mkdir -p "$DST/storage" "$DST/temp_storage" "$DST/compressed_storage"

# The base sim (~500KB): the backend reads its environment/0.json for initial
# tile positions and copies its per-persona memory into each generated sim.
if [ -d "$SRC/storage/$BASE_SIM" ]; then
  echo "Copying base simulation '$BASE_SIM'..."
  rsync -a "$SRC/storage/$BASE_SIM/" "$DST/storage/$BASE_SIM/"
fi

# The upstream landing page (http://localhost:8000/) just says "server is up and
# running" with no link, which is a confusing dead-end -- the visualization lives
# at /replay/<sim>/0/. Replace it with a version that links straight to the
# generated replay. (rsync above restores the pristine template each run, so this
# overwrite re-applies every time and stays idempotent.)
SIM_CODE="mock_the_ville_n25"
cat > "$DST/templates/landing/landing.html" <<'LANDING'
{% extends "base.html" %}
{% load staticfiles %}

{% block content %}
<div style="padding:2em; font-family:sans-serif; line-height:1.5">
  <img src="{% static 'img/atlas.png' %}"><br>
  Your environment server is up and running!
  <h2 style="margin-top:1em">Generative Agents — Smallville (mock-LLM port)</h2>
  <p style="font-size:1.2em">
    ▶ <a href="/replay/mock_the_ville_n25/0/">Open the Smallville replay (25 residents)</a>
  </p>
  <p style="color:#666">
    Seeing a 404 or an empty map? Generate a simulation first:<br>
    <code>uv run python -m backend.run_simulation</code>
  </p>
</div>
{% endblock content %}
LANDING

echo "Installing local replay UI overrides (camera zoom/pan + fill-the-view)..."
# The replay UI is heavily modified from upstream: the Phaser camera now drives
# zoom + pan (mouse wheel, drag-to-pan, arrow keys, on-screen +/-/Reset buttons),
# the canvas is responsive (Scale.RESIZE so it fills its container), and the
# default view fills the area with the world's top-left pinned. Rather than
# fragile in-place string patches, the final files live under frontend_overrides/
# and are copied over the freshly-rsynced upstream tree. They're committed there
# because frontend/ itself is git-ignored -- so edits made directly under
# frontend/ are NOT tracked and get wiped by the rsync --delete above.
#
# KNOWN ISSUE (unresolved): on at least one reporter's machine the replay world
# renders centered / pushed toward the bottom-right with black space along the top
# and left, and rightward panning is limited, instead of filling the view from the
# top-left. The camera/scale logic verifies correct in headless Chrome at dpr 1
# and 2, and these overrides are what *should* render. A likely cause was this
# script regenerating the OLD upstream UI on top of local edits -- which moving the
# UI into these committed overrides is meant to fix. If it still mis-renders after
# a clean regen + fresh browser, it needs further investigation.
rsync -a "$HERE/frontend_overrides/" "$DST/"

echo
echo "Frontend ready at: $DST"
echo
echo "Next steps:"
echo "  1. Generate a simulation (runs the engine in the repo's uv project env):"
echo "       uv run python -m backend.run_simulation"
echo "  2. Run the frontend in its OWN Python 3.9 venv (Django 2.2 needs an older"
echo "     interpreter than the engine's). uv fetches Python 3.9 for you:"
echo "       uv venv --python 3.9 frontend-venv"
echo "       uv pip install --python frontend-venv -r requirements-frontend.txt"
echo "       (cd frontend && ../frontend-venv/bin/python manage.py runserver)"
echo "  3. Open: http://localhost:8000/replay/mock_the_ville_n25/0/"
