"""Load a repo-root ``.env`` file before a backend CLI reads the environment.

The backend's entrypoints are configured through environment variables --
``ANTHROPIC_API_KEY`` for ``serve_penn --brain llm``, ``LLM_PROVIDER`` /
``LLM_MODEL`` / ``LLM_MAX_COST`` for ``backend.run_simulation``,
``SIM_API_TOKEN`` / ``SIM_LIVE`` for the API demo -- and exporting them in
every terminal is easy to forget. Each CLI therefore calls :func:`load_dotenv`
first, which folds ``KEY=VALUE`` lines from a ``.env`` file at the repository
root into ``os.environ``. The file is git-ignored (a copy-me template lives at
``.env.example``), so keys never end up in the repo.

**The real environment always wins.** A variable that is already exported is
never overridden by the file -- one-off ``FOO=bar cmd`` runs, CI settings, and
shell-profile exports all behave exactly as before. A missing file is fine;
the loader just reports ``False``.

Deliberately hand-rolled rather than a ``python-dotenv`` dependency: the
subset we need -- comments, blank lines, an optional ``export`` prefix,
optional quotes -- is a dozen lines, and this way a reader can see exactly
what reaches the environment.
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_repo_root() -> Path:
    """The checkout root: the nearest ancestor of this file with a pyproject.toml.

    Anchored on that marker file rather than a fixed number of ``parents[...]``
    levels, so moving this package (as #399 did -- see #776) cannot silently
    point the default ``.env`` lookup at the wrong directory again. The walk
    starts from this source file, not the cwd, so the loader finds the
    checkout's own ``.env`` no matter where a CLI is launched from.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    # No marker anywhere above us (an unusual install layout): fall back to
    # counting levels -- <repo>/godot-generative-agents/backend/env.py.
    return here.parents[2]


_REPO_ROOT = _find_repo_root()


def load_dotenv(path: str | os.PathLike | None = None) -> bool:
    """Fold *path* (default: ``<repo root>/.env``) into ``os.environ``.

    Returns True when a file was found and parsed, False when there is none.
    Each line is ``KEY=VALUE``: blank lines and ``#`` comments are skipped, a
    leading ``export `` is tolerated (so a file can double as shell source),
    and one pair of matching single or double quotes around the value is
    stripped. Variables already present in the environment are left untouched.
    """
    env_file = Path(path) if path is not None else _REPO_ROOT / ".env"
    if not env_file.is_file():
        return False
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)
    return True
