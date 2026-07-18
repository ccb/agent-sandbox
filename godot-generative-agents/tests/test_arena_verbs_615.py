"""Arena-tier affordance verbs (issue #615): `study` in `studyable` arenas,
`eat` where an EDIBLE meal is in scope (Houston Hall).

Pins:
* `study` is offered exactly where its gate's place-check passes (#612/#617
  invariant), sets the activity label, and accumulates `studied_minutes`;
* `study` advertises the #581 pacing slots and settles like `perform`;
* `eat` needs no new code -- Houston Hall meals make the engine verb
  offerable there, and the get -> eat two-step clears `is_hungry`;
* the study/eat first-person memory lines.

Fully offline. Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_arena_verbs_615.py -v
"""

import datetime
import sys
from pathlib import Path

# Same import shim as test_pacing_authority_581.py: the Penn sim modules run
# as scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.actions import DEFAULT_STUDY_MINUTES, Study  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    action_tools_for,
    attach_agents,
    observe_and_decide,
    remember_outcome,
)
from backend.prompt_templates import render  # noqa: E402
from backend.run_simulation import step  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402
from backend.sim_config import CognitionConfig  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402
from text_adventure_games.llm_client import ToolCallResult  # noqa: E402
from text_adventure_games.things import Item  # noqa: E402

# -- tiny-world harness (mirrors test_pacing_authority_581) ------------------

LOCATIONS = [
    {
        "name": "The Green",
        "description": "the central lawn",
        "address": None,
        "hub": True,
    },
    {"name": "Cafe", "description": "a coffee shop", "address": "T:Cafe:counter"},
    {
        "name": "Library",
        "description": "a small library",
        "address": "T:Library:desks",
        "properties": ["studyable"],
    },
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
    """(game, Ada) with the #615 verbs offered and Study registered."""
    personas = [_persona(**persona_kw)]
    game, chars = build_world(None, personas, LOCATIONS, extra_actions=[Study])
    attach_agents(
        chars, personas, llm_client=llm_client, extra_action_names=["study", "eat"]
    )
    return game, chars["Ada"]


def _move(game, char, dest):
    if char.location is not None:
        char.location.remove_character(char)
    game.locations[dest].add_character(char)


def _tool_names(game, char):
    return {t["name"] for t in action_tools_for(game, char)}


# -- study: offered <=> gate place-check (the #617 invariant) -----------------


def test_study_offered_only_in_a_studyable_arena():
    game, ada = _world()
    # Home (The Green) carries no tag: not offered; universals still are.
    assert "study" not in _tool_names(game, ada)
    assert {"travel", "perform"} <= _tool_names(game, ada)
    _move(game, ada, "Library")
    assert "study" in _tool_names(game, ada)


def test_study_gate_fails_elsewhere_with_actionable_feedback():
    game, ada = _world()  # Ada on The Green, untagged
    assert not game.parser.parse_command("study thermodynamics", actor=ada)
    msg = getattr(game.parser, "last_fail_message", "")
    assert "study" in msg and "here" in msg


# -- study: effects ------------------------------------------------------------


def test_study_sets_activity_and_accumulates_minutes():
    game, ada = _world()
    _move(game, ada, "Library")
    ada.agent.last_duration_minutes = 45  # what _take_pacing_args stashes (#581)
    assert game.parser.parse_command("study thermodynamics", actor=ada)
    assert ada.get_property("activity") == "studying thermodynamics"
    assert ada.get_property("studied_minutes") == 45
    assert ada.get_property("just_studied_minutes") == 45  # Task 3's one-shot
    ada.agent.last_duration_minutes = 25
    assert game.parser.parse_command("study lab reports", actor=ada)
    assert ada.get_property("studied_minutes") == 70  # accumulates across studies


def test_study_without_duration_or_topic_uses_defaults():
    game, ada = _world()
    _move(game, ada, "Library")
    ada.agent.last_duration_minutes = None
    assert game.parser.parse_command("study", actor=ada)
    assert ada.get_property("activity") == "studying"
    assert ada.get_property("studied_minutes") == DEFAULT_STUDY_MINUTES


# -- study: #581 pacing opt-in -------------------------------------------------


def test_study_tool_advertises_the_pacing_slots():
    brain = PerActionBrain("study", {"topic": "thermodynamics"})
    game, ada = _world(llm_client=brain, place="Library")
    _move(game, ada, "Library")  # offered only where afforded
    observe_and_decide(game, ada, 0)
    study = {t["name"]: t for t in brain.offers[0]["tools"]}["study"]
    props = study["parameters"]["properties"]
    assert "duration_minutes" in props
    assert "emoji" in props
    # Everything is optional -- a bare "study" must stay routable.
    assert "topic" not in study["parameters"].get("required", [])


def test_study_meta_args_stash_without_leaking_into_the_command():
    brain = PerActionBrain(
        "study",
        {"topic": "thermodynamics", "duration_minutes": 45, "emoji": "\U0001f4da"},
    )
    game, ada = _world(llm_client=brain, place="Library")
    _move(game, ada, "Library")
    command = observe_and_decide(game, ada, 0)
    assert command == "study thermodynamics"  # no "45", no emoji spliced in
    assert ada.agent.last_duration_minutes == 45
    assert ada.agent.last_emoji == "\U0001f4da"
