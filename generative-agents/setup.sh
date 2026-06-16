#!/usr/bin/env bash
#
# Populate generative-agents/frontend/ from the upstream generative_agents clone.
#
# Copies the Django visualizer + the ~38MB of the_ville map/sprite assets, but
# NOT the ~1GB of pre-baked example simulations (we generate our own). Also
# brings in the small 3-agent base sim, whose initial tile positions and persona
# memory the backend reuses. Idempotent: safe to re-run; never touches a sim you
# generated under frontend/storage/ (that path is preserved).
#
# Usage:  ./setup.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/../external/generative_agents/environment/frontend_server"
DST="$HERE/frontend"
BASE_SIM="base_the_ville_isabella_maria_klaus"

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

# The small base sim (≈68KB): the backend reads its environment/0.json for
# initial tile positions and copies its persona memory into each generated sim.
if [ -d "$SRC/storage/$BASE_SIM" ]; then
  echo "Copying base simulation '$BASE_SIM'..."
  rsync -a "$SRC/storage/$BASE_SIM/" "$DST/storage/$BASE_SIM/"
fi

# The upstream landing page (http://localhost:8000/) just says "server is up and
# running" with no link, which is a confusing dead-end -- the visualization lives
# at /replay/<sim>/0/. Replace it with a version that links straight to the
# generated replay. (rsync above restores the pristine template each run, so this
# overwrite re-applies every time and stays idempotent.)
SIM_CODE="mock_the_ville_isabella_maria_klaus"
cat > "$DST/templates/landing/landing.html" <<'LANDING'
{% extends "base.html" %}
{% load staticfiles %}

{% block content %}
<div style="padding:2em; font-family:sans-serif; line-height:1.5">
  <img src="{% static 'img/atlas.png' %}"><br>
  Your environment server is up and running!
  <h2 style="margin-top:1em">Generative Agents — Smallville (mock-LLM port)</h2>
  <p style="font-size:1.2em">
    ▶ <a href="/replay/mock_the_ville_isabella_maria_klaus/0/">Open the Smallville replay</a>
  </p>
  <p style="color:#666">
    Seeing a 404 or an empty map? Generate a simulation first:<br>
    <code>../venv/bin/python -m backend.run_simulation</code>
  </p>
</div>
{% endblock content %}
LANDING

echo
echo "Frontend ready at: $DST"
echo
echo "Next steps:"
echo "  1. Generate a simulation (uses the project venv with the engine installed):"
echo "       ../venv/bin/python -m backend.run_simulation"
echo "  2. Run the frontend in its OWN Python 3.9 venv (Django 2.2 needs an older"
echo "     interpreter than the engine's). From this directory:"
echo "       python3.9 -m venv frontend-venv"
echo "       ./frontend-venv/bin/pip install -r requirements-frontend.txt"
echo "       (cd frontend && ../frontend-venv/bin/python manage.py runserver)"
echo "  3. Open: http://localhost:8000/replay/mock_the_ville_isabella_maria_klaus/0/"
