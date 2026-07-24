"""Suite-wide guard for the shared RunStore (#752).

``generate_penn_replay --persist`` now defaults ON, so a bake test that forgets
BOTH ``--no-persist`` and an isolated ``--runs-dir`` would silently append a run
row to the *real* shared store (``godot-generative-agents/runs/``) during an
ordinary ``pytest`` run. This autouse fixture makes that impossible to miss: it
fails the offending test loudly the moment the real store gains an entry, so the
"tests never touch the shared store" invariant holds structurally instead of
resting on every future author remembering the flag.

It *asserts* rather than monkeypatching ``DEFAULT_RUNS_DIR`` because the
byte-identity bake runs the CLI in a subprocess (``test_replay_contract``), which
a parent-process monkeypatch can't reach -- an after-the-fact check catches both
in-process ``main()`` calls and subprocess bakes. It only flags *new* entries, so
a developer's real saved runs are left untouched (and never deleted).
"""

import sys
from pathlib import Path

# godot-generative-agents/ holds the `backend` package; put it on the path so this
# conftest imports cleanly even without PYTHONPATH set (mirrors the test modules).
_SIM_ROOT = Path(__file__).resolve().parents[1]
if str(_SIM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SIM_ROOT))

import pytest

from backend.run_store import DEFAULT_RUNS_DIR


def _store_entries() -> set[str]:
    if not DEFAULT_RUNS_DIR.exists():
        return set()
    return {p.name for p in DEFAULT_RUNS_DIR.iterdir()}


@pytest.fixture(autouse=True)
def _no_shared_store_pollution():
    before = _store_entries()
    yield
    new = _store_entries() - before
    assert not new, (
        f"test wrote {sorted(new)} into the real shared RunStore ({DEFAULT_RUNS_DIR}); "
        "a bake test must pass --no-persist or an isolated --runs-dir (#752)"
    )
