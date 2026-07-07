"""The asset-path constants survive the #399 package move (issue #407).

``backend/`` moved to ``godot-generative-agents/backend/`` in #399, but the
Smallville (``the_ville``) and Penn (``the_upenn``) assets it reads still live
under the **repo-root** ``generative-agents/`` tree. Each constant derives its
location from ``__file__``; a one-``dirname`` computation was correct while
``backend/`` sat at the repo root, but after the move it silently resolved to a
nonexistent ``godot-generative-agents/generative-agents/`` -- so seeding read a
missing path and no-op'd without a word (the graceful-degradation branch that is
meant only for a fresh checkout without the ~38 MB upstream assets).

These guard the *resolved* locations so the same silent breakage can't recur.
Fully offline; the ``the_upenn`` matrix is tracked, so its existence check is
stable in CI.
"""

import os

from backend import run_simulation, run_upenn

# tests/ -> godot-generative-agents/ -> repo root
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_GA = os.path.join(_REPO_ROOT, "generative-agents")
# The exact wrong location the #407 regression produced.
_STALE = os.path.join("godot-generative-agents", "generative-agents")


def test_ville_constants_resolve_under_repo_root_generative_agents():
    for path in (run_simulation.DEFAULT_VILLE_DIR, run_simulation.DEFAULT_STORAGE):
        assert path.startswith(_GA + os.sep), path
        assert _STALE not in path, f"#407 regression: {path}"


def test_upenn_matrix_resolves_under_generative_agents_and_exists():
    assert run_upenn.UPENN_DIR.startswith(_GA + os.sep), run_upenn.UPENN_DIR
    assert _STALE not in run_upenn.UPENN_DIR
    # the_upenn matrix is committed, so this stays green offline / in CI.
    assert os.path.isdir(os.path.join(run_upenn.UPENN_DIR, "matrix"))
