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


def test_stepper_drains_deciding_records_under_a_real_brain(monkeypatch):
    # Reuse the live-llm fake-client stepper helper.
    import test_penn_live_llm as tll

    stepper = tll._llm_stepper(monkeypatch)  # --brain llm mode, fakes swapped in
    # Tick until at least one agent hits a decision point and emits records.
    seen = []
    for _ in range(6):
        stepper.tick()
        seen.extend(stepper.drain_deciding())
        if seen:
            break
    assert seen, "no deciding records emitted under a real brain"
    kinds = {(r["state"]) for r in seen}
    assert "begin" in kinds
    for r in seen:
        assert set(r) >= {"agent", "state", "step"}
        if r["state"] == "end":
            assert isinstance(r["elapsed_ms"], int) and r["elapsed_ms"] >= 0
    # Draining twice is idempotent (buffer cleared).
    assert stepper.drain_deciding() == []


def test_mock_stepper_emits_no_deciding_records():
    sys.path.insert(0, str(_SIM_DIR))
    from serve_penn import PennStepper
    from penn_world import build_penn_world

    stepper = PennStepper(num_steps=5, world=build_penn_world())  # --brain mock
    for _ in range(5):
        stepper.tick()
    assert stepper.drain_deciding() == []  # byte-identical mock feed
