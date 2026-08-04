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
from collections import defaultdict
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
from backend.prompt_templates import render

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
        # Set the moment call_tool is entered, per actor -- lets a test wait
        # for "the decide call has started" instead of asserting an
        # instantaneous tool_calls count that races the daemon thread's first
        # slice on a loaded runner (#932).
        self.called: dict[str, threading.Event] = defaultdict(threading.Event)

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
        self.called[self.context.get("actor")].set()
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
    # The parked call may not have had a time slice yet on a loaded runner --
    # the tick only waits out the 0.2 s budget, while the decide runs on its
    # own daemon thread. Wait for call-start before counting, then pin the
    # never-double-asks property on the count itself (#932).
    assert brains[hung].called[hung].wait(timeout=5)
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


# ------------------------------------- timeout -> failure memory (#758)
#
# #636 gave gate-blocked actions an "I tried X but it didn't work" memory but
# deliberately left the timeout path silent. A timed-out decide now writes the
# analogous "couldn't decide in time" record -- once per timeout EVENT, never
# again while the straggler stays parked, and the late answer's own outcome
# memory is a different fact, so applying it adds no second timeout record.

_TIMEOUT_PHRASE = "couldn't decide in time"


def test_reflection_template_pins_the_timeout_line():
    assert (
        render("reflection", timed_out=True, place="Van Pelt Library")
        == "I was thinking about what to do at Van Pelt Library but couldn't decide in time."
    )
    # Standing nowhere drops the place clause instead of rendering "at ".
    assert (
        render("reflection", timed_out=True, place="")
        == "I was thinking about what to do but couldn't decide in time."
    )


def test_decide_timeout_writes_one_failure_memory_and_the_late_answer_adds_none(
    monkeypatch,
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
        # 1.0 s, not 0.2: this test asserts BOTH that the gated agent times out
        # AND that the healthy ones don't, so the budget has to actually separate
        # "hung" from "merely slow". At 0.2 s it didn't -- a healthy decide is
        # microseconds of gated fake plus a real prompt/perception/retrieval pass,
        # and on a 2-vCPU CI runner (8 decide threads on 2 cores) that pass can
        # exceed 0.2 s, so a healthy agent wrote its own timeout memory and the
        # "everyone else" assertion below failed. It fired on ~1 run in 4, on
        # whichever Python version lost the coin flip -- 3.11 and 3.13 both seen,
        # on this test's own branch and on an unmodified main.
        # Free to raise: the gated agent blocks on gate.wait(timeout=5), so it
        # blows ANY budget under ~5 s. Costs ~0.8 s of wall clock on the one tick
        # that waits the budget out. Keep it well under that 5 s gate deadline.
        decide_timeout=1.0,
    )
    hung = stepper.order[0]
    gates[hung] = threading.Event()

    def timeout_memories(name):
        return [
            r
            for r in stepper.chars[name].agent.memory.records
            if _TIMEOUT_PHRASE in r.text
        ]

    # Tick 1: the gated decide blows its budget -> exactly one failure
    # memory, keyed to where the agent stood, at #636's failure conventions
    # (importance 3.0, unlocked -- only the pre-score floor).
    stepper.tick()
    recs = timeout_memories(hung)
    assert len(recs) == 1
    place = stepper.chars[hung].location.name
    assert (
        recs[0].text
        == f"I was thinking about what to do at {place} but couldn't decide in time."
    )
    assert recs[0].importance == 3.0
    # Everyone else decided within budget: a normal decide writes no such memory.
    assert all(not timeout_memories(n) for n in stepper.order if n != hung)

    # Tick 2: the straggler is still in flight. A parked tick is not a new
    # timeout event -- no second record.
    stepper.tick()
    assert len(timeout_memories(hung)) == 1

    # Release the straggler. Its late answer is applied at the next decision
    # point and remembered as a normal OUTCOME -- a different fact, so the
    # timeout memory count stays at one (no double-write).
    gates[hung].set()
    stepper._decide_pending[hung].result(timeout=5)
    stepper.tick()
    assert stepper.state[hung]["performing"]  # the late answer landed
    assert len(timeout_memories(hung)) == 1
    texts = [r.text for r in stepper.chars[hung].agent.memory.records]
    assert "I was pondering the day." in texts  # the applied answer's memory


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
