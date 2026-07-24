"""The Penn asset-path constants resolve correctly and the matrix exists (issue #407).

The ``the_upenn`` map assets moved with the backend into
``godot-generative-agents/backend/penn/the_upenn`` (#399) and are tracked in git.
``penn_world`` derives their location from ``__file__``; these guard the *resolved*
paths so a future move can't silently repoint them at a nonexistent directory -- the
#407 failure mode, where seeding read a missing path and no-op'd without a word.

Fully offline; the ``the_upenn`` matrix is tracked, so the existence checks are
stable in CI.
"""

import os
import sys
from pathlib import Path

# The Penn sim modules run as scripts (no package); import them off the sim dir,
# the way the scripts import each other (see test_penn_live).
_SIM_DIR = Path(__file__).resolve().parents[1] / "backend" / "penn"
sys.path.insert(0, str(_SIM_DIR))

import penn_world  # noqa: E402

_BACKEND_PENN = str(_SIM_DIR)


def test_upenn_dir_resolves_under_backend_penn_and_exists():
    # Robust to the #399 move: the constant is derived from penn_world's __file__,
    # so it must land inside .../godot-generative-agents/backend/penn/the_upenn.
    assert penn_world.UPENN_DIR.startswith(_BACKEND_PENN + os.sep), penn_world.UPENN_DIR
    # the_upenn matrix is committed, so this stays green offline / in CI.
    assert os.path.isdir(os.path.join(penn_world.UPENN_DIR, "matrix"))


def test_world_data_resolves_and_exists():
    assert penn_world.WORLD_DATA.startswith(
        _BACKEND_PENN + os.sep
    ), penn_world.WORLD_DATA
    assert os.path.isfile(penn_world.WORLD_DATA)
