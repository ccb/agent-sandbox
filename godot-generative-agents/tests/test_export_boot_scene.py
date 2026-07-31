"""The web Godot export boots into the replay viewer, not the landing menu (#903).

The embedded landing-page figure must open straight into the campus. The web
export's boot scene is pinned by ``web/scripts/export-godot.sh`` (a ``sed`` on
the export-only ``project.godot``), not by the committed ``project.godot`` -- so
this guards the ``sed`` target. Desktop stays menu-first because that ``sed``
only touches the web export. Fully offline; the script is tracked, so this is
stable in CI.
"""

import re
from pathlib import Path

# godot-generative-agents/tests/ -> parents[1] == godot-generative-agents/
_EXPORT_SCRIPT = (
    Path(__file__).resolve().parents[1] / "web" / "scripts" / "export-godot.sh"
)


def _pinned_boot_scene() -> str:
    """The res:// scene export-godot.sh rewrites run/main_scene to."""
    text = _EXPORT_SCRIPT.read_text()
    # The rewrite is: sed '...|run/main_scene="res://scenes/<name>.tscn"|'
    # so the quoted value is the replacement (the LHS pattern is unquoted).
    match = re.search(r'run/main_scene="(res://scenes/[^"]+\.tscn)"', text)
    assert match, f"no run/main_scene rewrite found in {_EXPORT_SCRIPT}"
    return match.group(1)


def test_web_export_boots_into_the_viewer_not_the_menu():
    # #903: booting the menu on the public landing figure is a dead click and
    # surfaces the live-backend / past-runs controls #879 wants hidden.
    assert _pinned_boot_scene() == "res://scenes/viewer.tscn"
