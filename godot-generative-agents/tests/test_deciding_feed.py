"""The deciding lifecycle feed record (#551): begin/end around each real decide.
Fully offline. Run from the repo root:
    uv run pytest godot-generative-agents/tests/test_deciding_feed.py -v
"""

import sys
import threading
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


def test_live_feed_publishes_deciding_records():
    # End-to-end through the real run_loop (not a monkeypatched tick), mirroring
    # the drive pattern in test_live_seam.py: poll the log with a timeout instead
    # of a fixed sleep, so the assertion isn't racing the event loop's schedule.
    import asyncio
    import contextlib

    from backend.live import EventLog, LiveRunController, ScriptedStepper, run_loop

    class _Stepper(ScriptedStepper):
        def __init__(self):
            super().__init__(
                frames=[{"Maya": {"x": 0, "y": 0}}]
            )  # one frame then finished
            self._drained = False

        def drain_deciding(self):
            if self._drained:
                return []
            self._drained = True
            return [
                {"agent": "Maya", "state": "begin", "step": 0},
                {"agent": "Maya", "state": "end", "step": 0, "elapsed_ms": 12},
            ]

    async def scenario():
        log = EventLog()
        controller = LiveRunController(_Stepper(), threading.Lock())
        task = asyncio.create_task(run_loop(controller, log, tick_seconds=0.0))
        async with asyncio.timeout(5):
            while not any(r["kind"] == "deciding" for r in log.since(0)):
                await asyncio.sleep(0.001)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return log.since(0)

    records = asyncio.run(scenario())
    deciding = [r for r in records if r.get("kind") == "deciding"]
    assert {"agent": "Maya", "state": "begin", "step": 0} in [
        {k: r[k] for k in ("agent", "state", "step")} for r in deciding
    ]
    assert any(r["state"] == "end" and r.get("elapsed_ms") == 12 for r in deciding)


def test_deciding_sink_publishes_begin_out_of_band_when_wired():
    # #605: with a live publisher wired (api.create_app does this at boot), the
    # sink sends `begin` the moment the decide starts -- before the decide
    # returns, before any tick-boundary drain -- and must NOT also surface it
    # at the drain (that would double-publish). `end` keeps the boundary path.
    from serve_penn import PennStepper
    from penn_world import build_penn_world

    published = []
    stepper = PennStepper(num_steps=5, world=build_penn_world())
    stepper.set_deciding_publisher(published.append)

    stepper._deciding_sink("Maya", "begin", 3)
    assert published == [{"agent": "Maya", "state": "begin", "step": 3}]  # immediate
    assert stepper.drain_deciding() == []  # and NOT buffered for the drain

    stepper._deciding_sink("Maya", "end", 3)
    assert len(published) == 1  # ends stay boundary-published
    rows = stepper.drain_deciding()
    assert [(r["agent"], r["state"], r["step"]) for r in rows] == [("Maya", "end", 3)]
    assert isinstance(rows[0]["elapsed_ms"], int) and rows[0]["elapsed_ms"] >= 0


def test_llm_stepper_publishes_begins_out_of_band_and_drains_only_ends(monkeypatch):
    # #605 end-to-end through the real serial decide path (--brain llm,
    # decide_workers=0): _decide_for's sink call publishes each begin through
    # the wired publisher inside tick(), and the boundary drain then carries
    # only the matching ends -- one per begin, no duplicates.
    import test_penn_live_llm as tll

    stepper = tll._llm_stepper(monkeypatch)
    published = []
    stepper.set_deciding_publisher(published.append)
    drained = []
    for _ in range(6):
        stepper.tick()
        drained.extend(stepper.drain_deciding())
        if published and drained:
            break
    assert published and all(r["state"] == "begin" for r in published)
    assert drained and all(r["state"] == "end" for r in drained)
    # Every out-of-band begin has exactly one boundary end, and vice versa.
    assert sorted((r["agent"], r["step"]) for r in published) == sorted(
        (r["agent"], r["step"]) for r in drained
    )


def test_deciding_sink_drops_an_orphan_end():
    # #598 review: an `end` with no matching `begin` this run -- a #366 straggler
    # finishing after a reset cleared _deciding_started -- is dropped, so a stray
    # elapsed-less record can't leak into the fresh run's feed and clear a real
    # bubble. A matched begin/end pair still round-trips, the end carrying elapsed.
    from serve_penn import PennStepper
    from penn_world import build_penn_world

    stepper = PennStepper(num_steps=5, world=build_penn_world())
    stepper._deciding_sink("Maya", "end", 0)  # orphan: no prior begin this run
    assert stepper.drain_deciding() == []

    stepper._deciding_sink("Maya", "begin", 1)
    stepper._deciding_sink("Maya", "end", 1)
    rows = stepper.drain_deciding()
    assert [r["state"] for r in rows] == ["begin", "end"]
    assert rows[0] == {"agent": "Maya", "state": "begin", "step": 1}
    assert set(rows[1]) == {"agent", "state", "step", "elapsed_ms"}
    assert isinstance(rows[1]["elapsed_ms"], int) and rows[1]["elapsed_ms"] >= 0


def test_terminal_tick_still_publishes_a_straggler_end():
    # #598 review: tick_once drains the deciding buffer even on the finishing
    # tick, and a parked #366 straggler may have appended its `end` there after
    # the last real tick. run_loop must publish those before the "finished"
    # status -- else the bubble stays stuck on the finished screen.
    import asyncio
    import contextlib

    from backend.live import EventLog, LiveRunController, ScriptedStepper, run_loop

    class _Stepper(ScriptedStepper):
        def __init__(self):
            # A CALLABLE (not a list, which cycles forever): one frame at step 0,
            # then None -> the run finishes and run_loop takes the terminal path.
            super().__init__(
                frames=lambda step: {"Maya": {"x": 0, "y": 0}} if step == 0 else None
            )
            self._drains = 0

        def drain_deciding(self):
            # The straggler's end lands on the SECOND drain -- the terminal
            # (finished) tick, after the one real frame's tick.
            self._drains += 1
            if self._drains == 2:
                return [{"agent": "Maya", "state": "end", "step": 0, "elapsed_ms": 7}]
            return []

    async def scenario():
        log = EventLog()
        controller = LiveRunController(_Stepper(), threading.Lock())
        task = asyncio.create_task(run_loop(controller, log, tick_seconds=0.0))
        async with asyncio.timeout(5):
            while not any(
                r["kind"] == "status" and r.get("reason") == "finished"
                for r in log.since(0)
            ):
                await asyncio.sleep(0.001)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return log.since(0)

    records = asyncio.run(scenario())
    ends = [
        r for r in records if r.get("kind") == "deciding" and r.get("state") == "end"
    ]
    assert (
        ends and ends[0]["elapsed_ms"] == 7
    ), "terminal-tick straggler end was dropped"
    # ...and it was published before the finished status, so the viewer clears
    # the bubble before the run marks finished.
    kinds = [(r["kind"], r.get("state"), r.get("reason")) for r in records]
    assert kinds.index(("deciding", "end", None)) < kinds.index(
        ("status", None, "finished")
    )
