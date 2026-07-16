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
