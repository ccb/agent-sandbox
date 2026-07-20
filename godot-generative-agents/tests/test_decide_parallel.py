"""Concurrent per-agent decisions, decision timeout, adaptive pacing (#366).

Pins the live loop's latency contract, fully offline:

* a decision tick with N agents due costs ~the slowest decision, not the sum
  (a daemon thread per decision fans ``observe_and_decide`` out against the
  turn-start snapshot, at most ``--decide-workers`` running at once;
  ``--mock-latency`` injects provider-shaped latency into the mock);
* a decision that outlives its wall-clock budget degrades to idle (the pinned
  brain-outage behavior), is never double-submitted while still in flight, and
  its late answer is applied -- not discarded -- once the straggler resolves
  (discarding would desync a stateful brain and bill a real one twice);
* ``run_loop`` subtracts each tick's wall time from the next sleep (``_pace``)
  and stamps ``tick_ms`` / ``deciders`` onto every ``frame`` record;
* the default path (``decide_workers=0``) builds no executor at all -- the
  simulate-equivalence suite (test_penn_live.py) stays the determinism gate.

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_decide_parallel.py -v
"""

import asyncio
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.live import (
    EventLog,
    LiveRunController,
    ScriptedStepper,
    _pace,
    run_loop,
)

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); import them off the sim directory, like test_penn_live.py.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from serve_penn import PennStepper  # noqa: E402
from text_adventure_games.usage import UsageLedger, record_call  # noqa: E402

MOCK_LATENCY = 0.3  # per-decision sleep injected into the mock brain


# ------------------------------------------------- wall-clock: T, not N*T


def _first_tick_wall(**kwargs):
    """Build a fresh latency-injected stepper and time its t=0 tick, when
    every persona is idle and therefore decides."""
    stepper = PennStepper(
        num_steps=5,
        world=build_penn_world(),
        mock_latency=MOCK_LATENCY,
        **kwargs,
    )
    started = time.monotonic()
    assert stepper.tick() is not None
    return stepper, time.monotonic() - started


def test_parallel_decision_tick_costs_the_slowest_decision_not_the_sum():
    parallel, wall_parallel = _first_tick_wall(decide_workers=8)
    serial, wall_serial = _first_tick_wall()
    n = len(parallel.order)
    assert n >= 3  # the fan-out needs a real crowd to prove anything
    assert serial._decide_executor is None  # decide_workers=0 is the default
    assert parallel.last_deciders == n  # the due-count reports either way
    assert serial.last_deciders == n
    # The serial tick pays every agent's injected latency in sequence...
    assert wall_serial >= n * MOCK_LATENCY
    # ...and the parallel tick overlaps them, so it must beat serial by about
    # the (n - 1) sleeps it no longer stacks. Asserting the DIFFERENCE of two
    # measured ticks (not an absolute ceiling) is what keeps this stable on
    # slow, loaded CI runners: each worker's perceive/retrieve CPU tail
    # serializes under the GIL and inflates both runs equally, so it cancels
    # out of the diff -- an absolute ceiling flaked on exactly that tail.
    assert wall_serial - wall_parallel > (n - 1) * MOCK_LATENCY * 0.6


# --------------------------------------- timeout -> idle -> re-ask later
#
# PennStepper builds its clients through serve_penn.create_llm_client; the
# factory is monkeypatched (the test_penn_live_llm.py pattern) so the whole
# --brain llm path runs against scripted stand-ins -- here, ones whose
# choose_action can be gated on a threading.Event per actor.


class _GatedBrain:
    """A '_ScriptedBrain'-shaped fake whose decide blocks while ``gates`` holds
    an un-set Event for the calling actor (read off ``self.context`` -- the
    decide path stamps it before the call, per-instance under #366's
    per-agent clients). Everyone else answers instantly."""

    def __init__(self, ledger=None, gates=None):
        self.ledger = ledger or UsageLedger()
        self.context: dict = {}
        self.gates = gates if gates is not None else {}
        self.tool_calls: list[str] = []

    def _record(self, messages, response):
        raw = SimpleNamespace(
            input_tokens=1000,
            output_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        record_call(
            self.ledger,
            self.context,
            "anthropic",
            "claude-haiku-4-5",
            raw,
            messages,
            str(response),
            latency_ms=42.0,
        )

    def chat(self, messages, max_tokens=256, temperature=0.0):
        self._record(messages, None)
        return None

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.tool_calls.append(tool["name"])
        gate = self.gates.get(self.context.get("actor"))
        if gate is not None:
            gate.wait(timeout=5)  # deadline so a failing test can't hang CI
        result = {
            "reasoning": "scripted decision",
            "action": "perform",
            "arguments": "pondering the day",
        }
        self._record(messages, result)
        return result

    def count_tokens(self, text):
        return len(text) // 4


def test_timeout_degrades_to_idle_never_double_asks_then_applies_the_late_answer(
    monkeypatch, capsys
):
    gates = {}

    def fake_create(config, ledger=None):
        return _GatedBrain(ledger=ledger, gates=gates)

    monkeypatch.setattr(serve_penn, "create_llm_client", fake_create)
    llm = {"provider": "anthropic", "model": "claude-haiku-4-5", "max_cost_usd": 5.0}
    stepper = PennStepper(
        num_steps=50,
        world=build_penn_world(),
        llm=llm,
        decide_workers=8,
        decide_timeout=0.2,
    )
    hung = stepper.order[0]
    gates[hung] = threading.Event()

    # Per-agent clients (#366): parallel decides must not share one mutable
    # `context`, so every agent gets its own instance; the shared one stays
    # as the mode flag only.
    brains = {name: stepper.chars[name].agent.llm_client for name in stepper.order}
    assert len({id(b) for b in brains.values()}) == len(stepper.order)
    assert all(b is not stepper.llm_client for b in brains.values())

    # Tick 1: the gated decision blows its 0.2 s budget -> the agent idles
    # exactly like a brain outage (path empty, not performing, still waking
    # up), the skip is printed, and the future is parked, still in flight.
    # The replay card is NOT refreshed from the half-made decision.
    started = time.monotonic()
    stepper.tick()
    assert time.monotonic() - started < 2.0  # bounded by the budget, not 5 s
    st = stepper.state[hung]
    assert st["path"] == [] and not st["performing"]
    assert st["desc"].startswith("waking up")
    assert st["reasoning"] == "(waking up)"  # card untouched while parked
    assert f"DECIDE TIMEOUT {hung}" in capsys.readouterr().out
    assert hung in stepper._decide_pending
    assert brains[hung].tool_calls.count("choose_action") == 1
    others_decided = {
        name: brains[name].tool_calls.count("choose_action")
        for name in stepper.order
        if name != hung
    }
    assert all(count == 1 for count in others_decided.values())

    # Tick 2: still in flight -> still idle, and crucially NOT asked again.
    stepper.tick()
    assert brains[hung].tool_calls.count("choose_action") == 1
    assert hung in stepper._decide_pending

    # Release the straggler. Its late answer is APPLIED at the next decision
    # point (not discarded -- a stateful brain like the mock consumes
    # schedule state per ask, and a real one bills per ask), so the brain is
    # NOT consulted a second time.
    gates[hung].set()
    stepper._decide_pending[hung].result(timeout=5)
    stepper.tick()
    assert brains[hung].tool_calls.count("choose_action") == 1
    assert hung not in stepper._decide_pending
    assert stepper.state[hung]["performing"]  # the late answer landed


def test_decide_threads_cap_bounds_concurrent_decides():
    # --decide-workers N promises a provider rate-limit bound: with 2 slots
    # and 3 submissions, the third must queue until a slot frees.
    executor = serve_penn._DecideThreads(2)
    gate = threading.Event()
    started = []

    def task(i):
        started.append(i)
        gate.wait(timeout=5)
        return i

    futs = [executor.submit(task, i) for i in range(3)]
    deadline = time.monotonic() + 5
    while len(started) < 2 and time.monotonic() < deadline:
        time.sleep(0.005)
    time.sleep(0.05)  # ample time for an un-capped third thread to slip in
    assert len(started) == 2  # any two may win the slots; never all three
    gate.set()  # frees the running two; the queued third then runs too
    assert sorted(f.result(timeout=5) for f in futs) == [0, 1, 2]


def test_step_fails_loud_when_executor_lacks_timeout_or_registry():
    # Passing an executor without its companion knobs must raise, not
    # silently wait forever / drop the never-double-ask guard.
    stepper = PennStepper(num_steps=2, world=build_penn_world(), decide_workers=1)
    stepper.decide_timeout = None
    with pytest.raises(ValueError, match="decide_timeout"):
        stepper.tick()
    stepper.decide_timeout = 30.0
    stepper._decide_pending = None
    with pytest.raises(ValueError, match="decide_pending"):
        stepper.tick()


# ------------------------------------------------- pacing + feed metadata


def test_pace_subtracts_tick_time_and_never_goes_negative():
    assert _pace(0.1, 0.0) == 0.1
    assert abs(_pace(0.1, 0.03) - 0.07) < 1e-9
    assert _pace(0.1, 0.5) == 0.0


def test_frame_records_carry_tick_ms_and_deciders():
    async def scenario():
        log = EventLog()
        stepper = ScriptedStepper([{"a": {"x": 0, "y": 0, "act": "hi", "e": "x"}}])
        stepper.last_deciders = 2  # what PennStepper sets after each tick()
        controller = LiveRunController(stepper, threading.Lock())
        task = asyncio.create_task(run_loop(controller, log, 0.005))
        async with asyncio.timeout(2):
            while len([r for r in log.since(0) if r["kind"] == "frame"]) < 2:
                await asyncio.sleep(0.005)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        frames = [r for r in log.since(0) if r["kind"] == "frame"]
        assert all(f["tick_ms"] >= 0 for f in frames)
        assert all(f["deciders"] == 2 for f in frames)
        return True

    assert asyncio.run(scenario())


def test_frames_omit_deciders_when_the_stepper_does_not_report_them():
    async def scenario():
        log = EventLog()
        stepper = ScriptedStepper([{"a": {"x": 0, "y": 0, "act": "hi", "e": "x"}}])
        controller = LiveRunController(stepper, threading.Lock())
        task = asyncio.create_task(run_loop(controller, log, 0.005))
        async with asyncio.timeout(2):
            while not [r for r in log.since(0) if r["kind"] == "frame"]:
                await asyncio.sleep(0.005)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        frame = [r for r in log.since(0) if r["kind"] == "frame"][0]
        assert "deciders" not in frame  # ScriptedStepper has no last_deciders
        assert frame["tick_ms"] >= 0  # ...but wall time is always stamped
        return True

    assert asyncio.run(scenario())
