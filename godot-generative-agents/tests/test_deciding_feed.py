"""The deciding lifecycle feed record (#551): begin/end around each real decide.
Fully offline. Run from the repo root:
    uv run pytest godot-generative-agents/tests/test_deciding_feed.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend import run_simulation  # noqa: E402


def test_decide_for_emits_begin_then_end_around_the_decision(monkeypatch):
    calls = []
    # Stub the decision so the test is independent of a real brain.
    monkeypatch.setattr(run_simulation, "observe_and_decide", lambda *a, **k: "look")

    class _Char:
        class agent:
            llm_client = None

        name = "Maya"

    result = run_simulation._decide_for(
        game=None,
        char=_Char(),
        step_idx=7,
        retrieval=None,
        deciding_sink=lambda name, state, step: calls.append((name, state, step)),
    )
    assert result == "look"
    assert calls == [("Maya", "begin", 7), ("Maya", "end", 7)]


def test_decide_for_emits_end_even_if_the_decision_raises(monkeypatch):
    calls = []

    def _boom(*a, **k):
        raise RuntimeError("brain down")

    monkeypatch.setattr(run_simulation, "observe_and_decide", _boom)

    class _Char:
        class agent:
            llm_client = None

        name = "Diego"

    import pytest

    with pytest.raises(RuntimeError):
        run_simulation._decide_for(
            game=None,
            char=_Char(),
            step_idx=3,
            retrieval=None,
            deciding_sink=lambda n, s, st: calls.append((n, s, st)),
        )
    # begin fired, and end fired via finally so a crashed decide can't strand a bubble.
    assert calls == [("Diego", "begin", 3), ("Diego", "end", 3)]


def test_no_sink_is_a_noop(monkeypatch):
    monkeypatch.setattr(run_simulation, "observe_and_decide", lambda *a, **k: "look")

    class _Char:
        class agent:
            llm_client = None

        name = "Sofia"

    # Default deciding_sink=None: no error, decision returned unchanged.
    assert run_simulation._decide_for(None, _Char(), 0, None) == "look"
