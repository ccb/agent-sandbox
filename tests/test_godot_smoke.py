"""Smoke-test the Godot campus viewer — but only when a Godot 4 binary is present.

The viewer lives in ``godot-generative-agents/`` and renders the UPenn campus from
``.tmj`` map files that the geo tools regenerate often. Godot only *warns* about a
map it can't read, so a broken regen renders an empty world without failing anything.
``run_smoke_test.sh`` loads each scene headless and fails if its map painted zero
cells; this test wires that into ``pytest`` so ``uv run pytest`` exercises it too.

It skips cleanly when Godot isn't installed (e.g. CI without the engine), so it
never blocks the suite — it only runs for developers who have Godot locally.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_PROJECT = Path(__file__).resolve().parent.parent / "godot-generative-agents"
_SMOKE = _PROJECT / "run_smoke_test.sh"


def _find_godot() -> str | None:
    """Locate a Godot 4 binary the same way the shell launcher does."""
    for name in ("godot", "godot4"):
        found = shutil.which(name)
        if found:
            return found
    mac_bundle = "/Applications/Godot.app/Contents/MacOS/Godot"
    return mac_bundle if Path(mac_bundle).exists() else None


@pytest.mark.skipif(_find_godot() is None, reason="Godot 4 not installed")
def test_godot_scenes_render():
    """Every campus scene loads headless and paints a non-empty map."""
    result = subprocess.run(
        ["bash", str(_SMOKE)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        "Godot smoke test failed (a scene didn't load or painted 0 map cells):\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
