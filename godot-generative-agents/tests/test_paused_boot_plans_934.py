"""Deferred plan authorship under --start-paused (#934).

A paying brain shouldn't spend before anyone is watching: ``--brain llm``
boots paused, but boot builds the *default* world and (under ``--plan
llm``/auto) the LLMPlanner authors every default persona's day at attach
time -- real plan calls -- and a pre-start ``POST /config`` then throws
that world away and re-authors for the applied cast. ``defer_plans``
(wired to ``--start-paused``) moves authorship to the first tick, so a
re-cast during the paused window never pays for a discarded world.

Fully offline: the client factory is monkeypatched (the
test_penn_live_llm.py pattern), so the whole --brain llm path runs against
an inert stand-in and the assertions count its calls.

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_paused_boot_plans_934.py -v
"""

import sys
from pathlib import Path

from backend.run_store import RunStore

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from serve_penn import PennStepper  # noqa: E402

PAID = {"provider": "anthropic", "model": "claude-haiku-4-5", "max_cost_usd": 5.0}


class _InertBrain:
    """A ``create_llm_client`` stand-in that never answers, recording every
    call as ``(tool_or_chat, role)`` into a shared list. Plan authorship
    against it degrades to the static fallback; nothing touches the network."""

    def __init__(self, ledger, calls):
        self.ledger = ledger
        self.context: dict = {}
        self._calls = calls

    def chat(self, messages, max_tokens=256, temperature=0.0):
        self._calls.append(("chat", self.context.get("role")))
        return None

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self._calls.append((tool["name"], self.context.get("role")))
        return None

    def call_tools(
        self, messages, tools, tool_choice=None, max_tokens=256, temperature=0.0
    ):
        # The N-tools decide route (#356), taken when a RecordingClient wraps
        # this fake (a run store is present); answering None degrades the
        # decide to idle, exactly like a brain outage.
        self._calls.append(("call_tools", self.context.get("role")))
        return None

    def count_tokens(self, text):
        return len(text) // 4


def _factory(calls):
    def create(config, ledger=None):
        return _InertBrain(ledger, calls)

    return create


def _plan_calls(calls):
    return [c for c in calls if c[1] == "plan"]


def test_paused_boot_spends_no_plan_calls_until_the_first_tick(monkeypatch):
    calls: list = []
    monkeypatch.setattr(serve_penn, "create_llm_client", _factory(calls))
    stepper = PennStepper(
        num_steps=3, world=build_penn_world(), llm=dict(PAID), defer_plans=True
    )
    # Boot (the paused window): the world is built, agents attached, and NOT
    # one planner call spent -- this is the #934 waste. A pre-start /config
    # re-cast can now discard this world for free.
    assert _plan_calls(calls) == []
    assert set(stepper._planner_sources.values()) == {"deferred"}

    # First tick (what POST /resume drives): authorship happens now, for the
    # cast that is actually running.
    stepper.tick()
    first_tick_plan_calls = _plan_calls(calls)
    assert first_tick_plan_calls  # generation was attempted...
    # ...for every persona (the inert brain answers nothing, so each agent
    # falls back to its static schedule -- the safe degradation).
    assert set(stepper._planner_sources.values()) == {"static"}

    # Authored once: the next tick adds no further plan-role spend.
    stepper.tick()
    assert _plan_calls(calls) == first_tick_plan_calls


def test_undeferred_boot_still_authors_at_attach_time(monkeypatch):
    # The default path (no --start-paused) is unchanged: plans author inside
    # the build, before the first tick.
    calls: list = []
    monkeypatch.setattr(serve_penn, "create_llm_client", _factory(calls))
    stepper = PennStepper(num_steps=3, world=build_penn_world(), llm=dict(PAID))
    assert _plan_calls(calls)
    assert set(stepper._planner_sources.values()) == {"static"}


def test_deferred_authoring_restamps_the_manifest(tmp_path, monkeypatch):
    # The stored manifest's plan provenance must describe the AUTHORED day,
    # not the paused window's placeholder -- same contract as the boot
    # re-stamp after attach_agents.
    calls: list = []
    monkeypatch.setattr(serve_penn, "create_llm_client", _factory(calls))
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(
        num_steps=3,
        world=build_penn_world(),
        llm=dict(PAID),
        run_store=store,
        defer_plans=True,
    )
    (row,) = store.list_runs()
    manifest = store.get_run(row["id"])["manifest"]
    assert set(manifest["planner_sources"].values()) == {"deferred"}

    stepper.tick()
    manifest = store.get_run(row["id"])["manifest"]
    assert set(manifest["planner_sources"].values()) == {"static"}


def test_mock_brain_is_unaffected_by_the_flag(monkeypatch):
    # The mock path never had the problem (MockPlanner is free) and must not
    # grow a deferral window: sources stay "mock" from boot.
    stepper = PennStepper(num_steps=3, world=build_penn_world(), defer_plans=True)
    assert set(stepper._planner_sources.values()) == {"mock"}
    stepper.tick()
    assert set(stepper._planner_sources.values()) == {"mock"}
