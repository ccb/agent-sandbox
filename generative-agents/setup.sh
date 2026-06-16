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
    <code>uv run python -m backend.run_simulation</code>
  </p>
</div>
{% endblock content %}
LANDING

echo "Applying local replay UI fixes..."
REPLAY_DST="$DST" python3 - <<'PY'
import os
from pathlib import Path

root = Path(os.environ["REPLAY_DST"])
script_path = root / "templates/home/main_script.html"
style_path = root / "static_dirs/css/style.css"
base_path = root / "templates/base.html"
home_path = root / "templates/home/home.html"

base = base_path.read_text()
base_old = """	<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@3.4.1/dist/css/bootstrap-theme.min.css" integrity="sha384-6pzBo3FDv/PJ8r2KRkGHifhEocL+1X2rVCTTkUfGk7/0pbek5mMa1upzvWbrUbOZ" crossorigin="anonymous">

</head>"""
base_new = """	<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@3.4.1/dist/css/bootstrap-theme.min.css" integrity="sha384-6pzBo3FDv/PJ8r2KRkGHifhEocL+1X2rVCTTkUfGk7/0pbek5mMa1upzvWbrUbOZ" crossorigin="anonymous">
	<link rel="stylesheet" href="{% static 'css/style.css' %}">

</head>"""
if base_old not in base:
    raise SystemExit("Could not apply base stylesheet patch; missing bootstrap theme snippet")
base_path.write_text(base.replace(base_old, base_new, 1))

home = home_path.read_text()
home_old = """	<div style="width:55%; margin: 0 auto; margin-top:4.5em">"""
home_new = """	<div id="replay-status-panel" style="width:55%; margin: 0 auto; margin-top:4.5em">"""
if home_old not in home:
    raise SystemExit("Could not apply replay status panel patch; missing panel container")
home_path.write_text(home.replace(home_old, home_new, 1))

script = script_path.read_text()
script_replacements = [
    (
        """	const config = {
	  type: Phaser.AUTO,
	  width: 1500,
	  height: 800,""",
        """	const map_width = 4480;
	const map_height = 3200;
	const config = {
	  type: Phaser.AUTO,
	  width: map_width,
	  height: map_height,""",
    ),
    (
        """	let curr_maze = "the_ville";""",
        """	let curr_maze = "the_ville";
	let replay_started = "{{ mode }}" !== "replay";""",
    ),
    (
        """	  camera.setBounds(0, 0, map.widthInPixels, map.heightInPixels);
	  cursors = this.input.keyboard.createCursorKeys();""",
        """	  camera.setBounds(0, 0, map.widthInPixels, map.heightInPixels);
	  camera.centerOn(map.widthInPixels / 2, map.heightInPixels / 2);
	  cursors = this.input.keyboard.createCursorKeys();""",
    ),
    (
        """	function update(time, delta) {
		// *** SETUP PLAY AND PAUSE BUTTON *** 
		let play_context = this;
		function game_resume() {  
			play_context.scene.resume();
		}  
		play_button.onclick = function(){
			game_resume();
		};
		function game_pause() {  
			play_context.scene.pause();
		}  
		pause_button.onclick = function(){
			game_pause();
		};

	  // *** MOVE CAMERA *** """,
        """	function update(time, delta) {
		if (!replay_started) {
			return;
		}

	  // *** MOVE CAMERA *** """,
    ),
    (
        """	// Control button binders
	var play_button=document.getElementById("play_button");
	var pause_button=document.getElementById("pause_button");""",
        """	// Control button binders
	var play_button=document.getElementById("play_button");
	var pause_button=document.getElementById("pause_button");
	function update_playback_buttons() {
		if (!play_button || !pause_button) {
			return;
		}
		play_button.style.display = replay_started ? "none" : "inline-block";
		pause_button.style.display = replay_started ? "inline-block" : "none";
	}
	play_button.onclick = function(){
		replay_started = true;
		update_playback_buttons();
	};
	pause_button.onclick = function(){
		replay_started = false;
		update_playback_buttons();
	};
	update_playback_buttons();""",
    ),
]
for old, new in script_replacements:
    if old not in script:
        raise SystemExit(f"Could not apply replay script patch; missing snippet:\n{old}")
    script = script.replace(old, new, 1)
script_path.write_text(script)

style = style_path.read_text()
style_replacements = [
    (
        """#game-container {
  /*min-width: 100vw;
  min-height: 100vh;*/
  display: flex;
  align-items: center;
  justify-content: center;
}""",
        """#game-container {
  display: flex;
  align-items: center;
  justify-content: center;
  max-width: 100vw;
  overflow: hidden;
  width: 100%;
}""",
    ),
    (
        """#game-container>canvas {
  border-radius: 5px;
}""",
        """#game-container>canvas {
  border-radius: 5px;
  display: block;
  height: auto !important;
  max-height: 78vh;
  max-width: 100vw;
  width: auto !important;
}

#replay-status-panel {
  max-width: 920px;
  width: calc(100% - 32px) !important;
}

@media (max-width: 767px) {
  #replay-status-panel {
    margin-top: 2.5em !important;
  }

  #replay-status-panel .media {
    padding: 1em !important;
  }

  #replay-status-panel .media-left,
  #replay-status-panel .media-body {
    display: block;
    padding-left: 0 !important;
    width: 100%;
  }

  #replay-status-panel .media-left {
    margin-bottom: 1em;
    text-align: center;
  }

  #replay-status-panel h2 {
    font-size: 1.35em !important;
    overflow-wrap: anywhere;
  }
}""",
    ),
]
for old, new in style_replacements:
    if old not in style:
        raise SystemExit(f"Could not apply replay style patch; missing snippet:\n{old}")
    style = style.replace(old, new, 1)
style_path.write_text(style)
PY

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
echo "  3. Open: http://localhost:8000/replay/mock_the_ville_isabella_maria_klaus/0/"
