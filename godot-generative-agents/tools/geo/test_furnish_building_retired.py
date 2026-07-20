import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "furnish_building.py")


def test_cli_refuses_and_exits_nonzero():
    r = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    msg = (r.stderr + r.stdout).lower()
    assert "furnish_williams" in msg
    assert "retired" in msg or "authored" in msg


def test_cli_refuses_even_with_dry_run():
    r = subprocess.run(
        [sys.executable, SCRIPT, "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0


def test_module_still_imports_as_a_library():
    sys.path.insert(0, HERE)
    import furnish_building as fb

    # Palette constants + helpers that furnish_williams / add_entrances rely on.
    assert isinstance(fb.WALL, int)
    assert isinstance(fb.WINDOW, int)
    assert fb.SOUTH_DOOR_X == (43, 44)
    assert callable(fb.paint_shell)
