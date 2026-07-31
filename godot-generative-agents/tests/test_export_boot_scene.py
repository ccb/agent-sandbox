"""The web Godot export boots a one-button "Start replay" menu (#903).

The embedded landing-page figure must not surface the live-backend / past-runs
controls #879 keeps out of public navigation, but the reader still gets an
explicit "this is a thing you start" affordance rather than landing mid-scene
(PR #928 review). Two halves, each guarded here:

* the export's boot scene stays ``main_menu.tscn`` — pinned by
  ``web/scripts/export-godot.sh`` (a ``sed`` on the export-only
  ``project.godot``), so this guards the ``sed`` target; and
* ``main_menu.gd`` reduces itself to the single "Start replay" button when
  running on web (``OS.has_feature("web")``), keeping desktop menu-first and
  untouched.

Fully offline; both files are tracked, so this is stable in CI.
"""

import re
from pathlib import Path

# godot-generative-agents/tests/ -> parents[1] == godot-generative-agents/
_GGA = Path(__file__).resolve().parents[1]
_EXPORT_SCRIPT = _GGA / "web" / "scripts" / "export-godot.sh"
_MENU_SCRIPT = _GGA / "godot" / "scripts" / "main_menu.gd"


def _pinned_boot_scene() -> str:
    """The res:// scene export-godot.sh rewrites run/main_scene to."""
    text = _EXPORT_SCRIPT.read_text()
    # The rewrite is: sed '...|run/main_scene="res://scenes/<name>.tscn"|'
    # so the quoted value is the replacement (the LHS pattern is unquoted).
    match = re.search(r'run/main_scene="(res://scenes/[^"]+\.tscn)"', text)
    assert match, f"no run/main_scene rewrite found in {_EXPORT_SCRIPT}"
    return match.group(1)


def test_web_export_boots_the_menu():
    # #903 (as revised in PR #928 review): the web entry point is the menu —
    # reduced to a single Start button by main_menu.gd, not a separate scene —
    # so the export keeps pinning the same boot scene desktop uses.
    assert _pinned_boot_scene() == "res://scenes/main_menu.tscn"


def test_web_menu_reduces_to_a_single_start_button():
    # The web half of the gate lives in main_menu.gd. String-level tripwires
    # (this is GDScript, so we can't import it): the web-only label must exist,
    # and the desktop-only sections must still be gated on the web feature tag.
    text = _MENU_SCRIPT.read_text()
    assert '"▶  Start replay"' in text, (
        "main_menu.gd lost the web-only 'Start replay' label — the web export "
        "would boot the full desktop menu (live/past-runs controls, #879)"
    )
    assert 'OS.has_feature("web")' in text
    # The full desktop label must survive too — losing it means desktop picked
    # up the reduced web copy.
    assert '"▶  Play the bundled replay"' in text
