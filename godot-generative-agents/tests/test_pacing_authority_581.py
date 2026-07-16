"""Brain-authoritative pacing (issue #581).

The executed action -- not the ScheduleMockClient stop pointer -- owns an
agent's duration, emoji, and stop-advance. Pins:

* the ``perform`` tool's optional ``duration_minutes`` / ``emoji`` meta-args
  reach the agent without leaking into the routed command string;
* the step loop honors a model duration (clamped) and emoji, falling back to
  the schedule when absent -- so the mock bake stays byte-identical;
* ``advance()`` fires only when the activity completed at the scheduled place;
  a place deviation keeps the pointer and fires one cooldown-guarded revision;
* new duration-bearing verbs settle like ``perform`` while the #300
  instantaneous verbs keep falling through.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_pacing_authority_581.py -v
"""

import datetime
import sys
from pathlib import Path

# Same import shim as test_per_action_decide.py: the Penn sim modules run as
# scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents, observe_and_decide  # noqa: E402
from backend.run_simulation import step  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402
from backend.sim_config import CognitionConfig  # noqa: E402
from text_adventure_games.llm_client import ToolCallResult  # noqa: E402


def test_cognition_config_has_pacing_knobs_with_defaults():
    cog = CognitionConfig()
    assert cog.duration_min_minutes == 1
    assert cog.duration_max_minutes == 90
    assert cog.deviation_cooldown_steps == 30


def test_cognition_config_round_trips_pacing_knobs():
    import pytest

    from backend.sim_config import SimulationConfig

    cfg = SimulationConfig.from_dict(
        {"cognition": {"duration_max_minutes": 45, "deviation_cooldown_steps": 12}}
    )
    assert cfg.cognition.duration_max_minutes == 45
    assert cfg.cognition.deviation_cooldown_steps == 12
    # Unknown keys are still rejected by the section validator (no silent drop).
    with pytest.raises(ValueError):
        SimulationConfig.from_dict({"cognition": {"duration_bogus": 1}})


LOCATIONS = [
    {
        "name": "The Green",
        "description": "the central lawn",
        "address": None,
        "hub": True,
    },
    {"name": "Cafe", "description": "a coffee shop", "address": "T:Cafe:counter"},
    {"name": "Library", "description": "a small library", "address": "T:Library:desks"},
]


def _persona(steps=None, place="Cafe", activity="reading a novel"):
    # Fresh dict per test: attach_agents + the step loop mutate the spec.
    return {
        "name": "Ada",
        "home": "The Green",
        "persona": "I am Ada, a curious first-year.",
        "emoji": "\U0001f4d6",
        "start_tile": [0, 0],
        "destination": place,
        "activity": activity,
        "schedule": [
            {
                "place": place,
                "activity": activity,
                "emoji": "\U0001f4d6",
                "steps": steps,
            }
        ],
    }


class PerActionBrain:
    """A real-shaped brain: answers with one scripted per-action tool call."""

    def __init__(self, name, arguments):
        self._name = name
        self._arguments = arguments
        self.context: dict = {}
        self.offers: list[dict] = []

    def call_tools(
        self, messages, tools, tool_choice="auto", max_tokens=256, temperature=0.0
    ):
        self.offers.append({"tools": tools, "context": dict(self.context)})
        return ToolCallResult(
            text=None,
            tool_calls=[
                {"id": "c1", "name": self._name, "arguments": dict(self._arguments)}
            ],
        )


def _world(llm_client=None, **persona_kw):
    personas = [_persona(**persona_kw)]
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, llm_client=llm_client)
    return game, chars["Ada"]


def test_perform_tool_advertises_duration_and_emoji_slots():
    brain = PerActionBrain("perform", {"activity": "reading"})
    game, ada = _world(llm_client=brain)
    observe_and_decide(game, ada, 0)
    perform = {t["name"]: t for t in brain.offers[0]["tools"]}["perform"]
    props = perform["parameters"]["properties"]
    assert "duration_minutes" in props
    assert "emoji" in props
    # They are optional -- only ``activity`` is required (byte-identical routing).
    assert perform["parameters"]["required"] == ["activity"]


def test_meta_args_stash_on_agent_without_leaking_into_the_command():
    brain = PerActionBrain(
        "perform",
        {
            "activity": "napping in the sun",
            "duration_minutes": 25,
            "emoji": "\U0001f634",
        },
    )
    game, ada = _world(llm_client=brain)
    command = observe_and_decide(game, ada, 0)
    # The command the parser sees is clean -- no "25", no emoji spliced in.
    assert command == "perform napping in the sun"
    assert ada.agent.last_duration_minutes == 25
    assert ada.agent.last_emoji == "\U0001f634"


def test_absent_meta_args_leave_the_attrs_none():
    brain = PerActionBrain("perform", {"activity": "reading"})
    game, ada = _world(llm_client=brain)
    observe_and_decide(game, ada, 0)
    assert ada.agent.last_duration_minutes is None
    assert ada.agent.last_emoji is None


def test_mock_decide_leaves_pacing_attrs_none():
    game, ada = _world(llm_client=None)  # brain IS the schedule mock
    observe_and_decide(game, ada, 0)
    assert getattr(ada.agent, "last_duration_minutes", "unset") is None
    assert getattr(ada.agent, "last_emoji", "unset") is None


class _StubMap:
    def walk_path(self, src, address, furniture=None):
        return [(1, 1)]


def _clock():
    return SimClock(datetime.datetime(2023, 2, 13, 12, 0, 0), sec_per_step=10)


def _state():
    # Minimal per-agent state; step() fills the rest via st.get(...) defaults.
    return {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "\U0001f4d6",
            "desc": "waking up",
            "performing": False,
            "perform_until": None,
            "reasoning": "(waking up)",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }


def _run_step(game, chars, state, idx, clock):
    return step(
        game,
        chars,
        state,
        idx,
        order=["Ada"],
        world_map=_StubMap(),
        emoji={"Ada": "\U0001f4d6"},
        clock=clock,
        cog=CognitionConfig(),
    )


def test_model_duration_is_honored_in_steps():
    # 20 minutes at 10s/step = 120 steps. Ada is scheduled at The Green (home),
    # where she starts -- so this perform is on-plan; duration honoring is
    # independent of that.
    brain = PerActionBrain("perform", {"activity": "reading", "duration_minutes": 20})
    game, ada = _world(llm_client=brain, place="The Green")
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    assert state["Ada"]["performing"] is True
    assert state["Ada"]["perform_until"] == 0 + 120


def test_model_duration_is_clamped_to_the_max():
    # 999 minutes clamps to the 90-minute ceiling => 540 steps at 10s/step.
    brain = PerActionBrain("perform", {"activity": "reading", "duration_minutes": 999})
    game, ada = _world(llm_client=brain, place="The Green")
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    assert state["Ada"]["perform_until"] == 0 + 540  # 90 * 60 / 10


def test_absent_duration_falls_back_to_schedule_steps():
    brain = PerActionBrain("perform", {"activity": "reading"})
    game, ada = _world(llm_client=brain, place="The Green", steps=7)
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    assert state["Ada"]["perform_until"] == 0 + 7  # schedule.steps, unclamped


def test_model_emoji_wins_and_deviation_falls_to_persona_default():
    # Perform at The Green while scheduled for Cafe => place deviation. With no
    # model emoji, a deviation must NOT wear the (wrong) stop emoji: persona
    # default instead. Use a distinct stop emoji to tell them apart.
    persona = _persona(place="Cafe", activity="reading")
    persona["emoji"] = "\U0001f9d1"  # persona default: person
    persona["schedule"][0]["emoji"] = "\U0001f4d6"  # stop emoji: book
    game, chars = build_world(None, [persona], LOCATIONS)
    brain = PerActionBrain("perform", {"activity": "wandering"})  # deviation, no emoji
    attach_agents(chars, [persona], llm_client=brain)
    state = _state()
    step(
        game,
        chars,
        state,
        0,
        order=["Ada"],
        world_map=_StubMap(),
        emoji={"Ada": "\U0001f9d1"},
        clock=_clock(),
        cog=CognitionConfig(),
    )
    assert state["Ada"]["on_plan"] is False
    assert state["Ada"]["pron"] == "\U0001f9d1"  # persona default, not the book


def test_model_supplied_emoji_overrides_stop_and_persona():
    # On-plan perform at the scheduled place ("The Green" == home, so Ada
    # starts there) would otherwise wear the stop's own book emoji (the
    # `if matched: st["pron"] = schedule.emoji` branch) -- but a model-supplied
    # emoji must win regardless of plan status. This is the branch the
    # "model_emoji_wins"-named test above never actually exercises (it
    # supplies none); this one does, with an emoji distinct from both the
    # stop's book emoji and the persona-default book emoji `_run_step` hands
    # in as the fallback.
    brain = PerActionBrain("perform", {"activity": "reading", "emoji": "\U0001f9ea"})
    game, ada = _world(llm_client=brain, place="The Green")
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    assert state["Ada"]["on_plan"] is True
    assert state["Ada"]["pron"] == "\U0001f9ea"


from text_adventure_games.planning import RevisionTrigger  # noqa: E402


class SequenceBrain:
    """Answers call_tools from a scripted queue of (name, arguments), so a test
    can drive travel-then-perform (on-plan) or a run of off-plan performs."""

    def __init__(self, script):
        self._script = list(script)
        self.context: dict = {}

    def call_tools(
        self, messages, tools, tool_choice="auto", max_tokens=256, temperature=0.0
    ):
        name, arguments = (
            self._script.pop(0)
            if self._script
            else ("perform", {"activity": "waiting"})
        )
        return ToolCallResult(
            text=None,
            tool_calls=[{"id": "c", "name": name, "arguments": dict(arguments)}],
        )


class RecordingPlanner:
    """Records the triggers maybe_revise_plan hands it; never changes the plan
    (so the schedule is untouched -- we assert on the recorded reasons)."""

    def __init__(self):
        self.reasons = []

    def generate(self, persona=None, memory=None, clock=None):
        raise AssertionError("generate is not called in-loop")

    def revise(self, plan, trigger=None, memory=None, clock=None):
        self.reasons.append(getattr(trigger, "reason", None))
        return plan


def test_deviation_keeps_the_pointer_and_fires_one_revision():
    # Ada scheduled Cafe (steps=2), but the brain performs at The Green (start)
    # every tick => place deviation. The stop pointer must NOT advance, and
    # exactly one DEVIATED revision fires within the cooldown window.
    from backend.run_simulation import DEVIATED

    persona = _persona(place="Cafe", activity="reading", steps=2)
    game, chars = build_world(None, [persona], LOCATIONS)
    brain = SequenceBrain([("perform", {"activity": "wandering"})] * 6)
    attach_agents(chars, [persona], llm_client=brain)
    ada = chars["Ada"]
    ada.agent.planner = RecordingPlanner()  # swap in a recorder
    state = _state()
    clock = _clock()
    for idx in range(5):  # perform(0), settle, complete@2, re-decide, ...
        step(
            game,
            chars,
            state,
            idx,
            order=["Ada"],
            world_map=_StubMap(),
            emoji={"Ada": "\U0001f4d6"},
            clock=clock,
            cog=CognitionConfig(),
        )
    # Pointer never advanced past the un-executed scheduled stop.
    assert ada.agent.schedule.stop_index == 0
    # Exactly one revision, tagged DEVIATED (cooldown suppressed the rest).
    assert ada.agent.planner.reasons == [DEVIATED]
    assert RevisionTrigger(DEVIATED, 0).reason == "deviated"


def test_on_plan_perform_still_advances_the_pointer():
    # A two-stop schedule driven by the default mock: travel->perform stop 0,
    # then the pointer advances to stop 1. This is the byte-identical baseline
    # advance-by-match must preserve.
    persona = _persona(place="Cafe", activity="reading", steps=1)
    persona["schedule"].append(
        {"place": "Library", "activity": "studying", "emoji": "\U0001f4d6", "steps": 1}
    )
    game, chars = build_world(None, [persona], LOCATIONS)
    attach_agents(chars, [persona], llm_client=None)  # mock brain
    ada = chars["Ada"]
    state = _state()
    clock = _clock()
    for idx in range(6):
        step(
            game,
            chars,
            state,
            idx,
            order=["Ada"],
            world_map=_StubMap(),
            emoji={"Ada": "\U0001f4d6"},
            clock=clock,
            cog=CognitionConfig(),
        )
    # The mock reached + performed stop 0 (on-plan) so the pointer advanced.
    assert ada.agent.schedule.stop_index >= 1


def test_off_plan_perform_without_duration_is_bounded_not_frozen():
    # A deviation whose scheduled stop is "stay put" (steps=None) and that
    # carries no model duration must NOT inherit "stay forever" -- that would
    # freeze the agent (perform_until=None => the settle-completion check never
    # fires again => it never re-decides). It gets the max-duration ceiling so
    # the brain re-decides. Ada is scheduled at Cafe (steps=None) but performs
    # at The Green (home, where she starts) => off-plan.
    brain = PerActionBrain("perform", {"activity": "wandering"})
    game, ada = _world(llm_client=brain, place="Cafe", steps=None)
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    assert state["Ada"]["on_plan"] is False
    # 90-minute ceiling at 10s/step = 540 steps, not None (frozen).
    assert state["Ada"]["perform_until"] == 0 + 540


def test_stray_duration_on_a_non_pacing_verb_is_ignored():
    # A model that hallucinates duration_minutes onto a verb that never
    # advertised the slot (travel) must have it popped (no leak into the
    # command) but NOT stashed -- else a one-tick verb would settle.
    brain = PerActionBrain("travel", {"destination": "Cafe", "duration_minutes": 30})
    game, ada = _world(llm_client=brain, place="Cafe")
    command = observe_and_decide(game, ada, 0)
    assert command == "travel to Cafe"  # clean -- no "30" spliced in
    assert ada.agent.last_duration_minutes is None
