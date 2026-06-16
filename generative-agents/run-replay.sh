#!/usr/bin/env bash
#
# One-command launcher for the Smallville (mock-LLM) port.
#
#   1. Ensures the frontend assets exist (runs ./setup.sh if needed).
#   2. Generates the backend simulation -- but ONLY if it hasn't been generated
#      already (otherwise it skips straight to serving).
#   3. Ensures the Django frontend venv exists (Python 3.9).
#   4. Starts the frontend and prints the replay URL to watch.
#
# Idempotent: re-running is safe and fast (it reuses an existing sim + venv).
#
# Usage:
#   ./run-replay.sh                 # generate if missing, then serve
#   ./run-replay.sh --rebuild       # force-regenerate the sim, then serve
#   ./run-replay.sh --steps 120     # pass through to the backend generator
#   ./run-replay.sh --port 9000     # serve on a different port (default 8000)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

SIM_CODE="mock_the_ville_isabella_maria_klaus"
SIM_MOVEMENT="$HERE/frontend/storage/$SIM_CODE/movement/0.json"

REBUILD=0
PORT=8000
STEPS_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --rebuild) REBUILD=1; shift ;;
    --steps)   STEPS_ARGS=(--steps "$2"); shift 2 ;;
    --port)    PORT="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

# --- 1. Frontend assets ------------------------------------------------------
if [ ! -f "$HERE/frontend/manage.py" ]; then
  echo ">> Frontend not set up yet -- running ./setup.sh ..."
  ./setup.sh
fi

# --- 2. Backend simulation (the skip-if-already-done step) -------------------
# The backend runs in the repo's uv project env (the engine lives there). We
# don't pre-create it: `uv run` finds the repo's pyproject.toml one level up and
# syncs the .venv on demand. We just need uv itself on PATH.
if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: 'uv' not found on PATH." >&2
  echo "This port uses uv to run the engine. Install it, e.g.:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  echo "Then re-run; 'uv run' provisions the engine env automatically." >&2
  exit 1
fi

if [ "$REBUILD" -eq 1 ] || [ ! -f "$SIM_MOVEMENT" ]; then
  if [ "$REBUILD" -eq 1 ]; then
    echo ">> --rebuild requested: regenerating simulation '$SIM_CODE' ..."
  else
    echo ">> No simulation found -- generating '$SIM_CODE' ..."
  fi
  uv run python -m backend.run_simulation "${STEPS_ARGS[@]}"
else
  echo ">> Simulation '$SIM_CODE' already generated -- skipping (use --rebuild to force)."
fi

# --- 3. Frontend venv (Python 3.9 for Django 2.2) ---------------------------
# Managed by uv: `uv venv --python 3.9` fetches a managed CPython 3.9 if one
# isn't already installed, so there's no separate python3.9 to install by hand.
FRONTEND_PY="$HERE/frontend-venv/bin/python"
if [ ! -x "$FRONTEND_PY" ]; then
  echo ">> Creating frontend venv (uv, Python 3.9) ..."
  uv venv --python 3.9 "$HERE/frontend-venv"
  uv pip install -q --python "$FRONTEND_PY" -r "$HERE/requirements-frontend.txt"
fi

# --- 4. Serve ---------------------------------------------------------------
REPLAY_URL="http://localhost:$PORT/replay/$SIM_CODE/0/"
echo
echo "=================================================================="
echo " Starting the frontend. Watch the replay at:"
echo "   $REPLAY_URL"
echo " (Press Ctrl-C to stop the server.)"
echo "=================================================================="
echo

# Best-effort: open the browser shortly after the server comes up (macOS).
if command -v open >/dev/null 2>&1; then
  ( sleep 2; open "$REPLAY_URL" >/dev/null 2>&1 || true ) &
fi

cd "$HERE/frontend"
exec "$FRONTEND_PY" manage.py runserver "0.0.0.0:$PORT"
