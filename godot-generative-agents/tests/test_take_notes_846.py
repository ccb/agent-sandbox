"""The `take_notes` affordance (issue #846): the note-taking/observation verb
live agents keep wishing for.

The 2026-07-28 Sonnet-5 runs captured ten #621 parse_gap wishes; nine cluster
on note-taking/observation the engine had no verb for ("taking excited notes
on curvature and geodesics", "off-center seats to watch the rubber sheet
demo", "mentally replaying the lecture"). Pins:

* `take_notes` is universal -- offered ANYWHERE, and its gate's place-check
  agrees everywhere (#446 offered <=> gate invariant). Deliberately not
  place-gated: #811 showed narrowly gated verbs (study/check_out_book, three
  Van Pelt rooms) were never offered in whole runs because casts never
  entered those rooms;
* the tool schema requires a free-text `topic` and advertises the #581
  pacing slots, so a chosen note-taking session settles like `perform`;
* the effect is a memory: `remember_outcome` records the note as a
  first-person observation ABOVE default importance (3.0 -- the
  check_out_book/read tier), so it stays retrievable. No items, no
  inventory;
* registration: every Penn entry point registers the action and offers the
  verb (penn_world's PENN_EXTRA_ACTIONS / PENN_ACTION_VERBS).

Fully offline. Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_take_notes_846.py -v
"""

import datetime
import sys
from pathlib import Path

# Same import shim as test_arena_verbs_615.py: the Penn sim modules run as
# scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.actions import TakeNotes  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    ACTION_TAG,
    action_tools_for,
    attach_agents,
    observe_and_decide,
    remember_outcome,
)
from backend.prompt_templates import render  # noqa: E402
from backend.run_simulation import step  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402
from backend.sim_config import CognitionConfig  # noqa: E402
from text_adventure_games.llm_client import ToolCallResult  # noqa: E402

# -- tiny-world harness (mirrors test_arena_verbs_615) -------------------------

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
    """(game, Ada) with TakeNotes registered and take_notes offered."""
    personas = [_persona(**persona_kw)]
    game, chars = build_world(None, personas, LOCATIONS, extra_actions=[TakeNotes])
    attach_agents(
        chars, personas, llm_client=llm_client, extra_action_names=["take_notes"]
    )
    return game, chars["Ada"]


def _move(game, char, dest):
    if char.location is not None:
        char.location.remove_character(char)
    game.locations[dest].add_character(char)


def _tool_names(game, char):
    return {t["name"] for t in action_tools_for(game, char)}


# -- offered <=> gate, everywhere (the #446 invariant) --------------------------


def test_take_notes_is_offered_everywhere():
    # Universal like perform (#811: a place-gated verb is a verb nobody is
    # ever offered) -- home hub, an untagged arena, and a tagged one alike.
    game, ada = _world()
    for place in ("The Green", "Cafe", "Library"):
        _move(game, ada, place)
        assert "take_notes" in _tool_names(game, ada), place


def test_offered_iff_gate_place_check_passes():
    # The #446 invariant, via its actual mechanism: the offer and the gate
    # both read affordance_in_scope, and for the empty declaration both sides
    # are True everywhere -- assert the equality, not just each side.
    game, ada = _world()
    for place in ("The Green", "Cafe", "Library"):
        _move(game, ada, place)
        offered = "take_notes" in _tool_names(game, ada)
        gate = TakeNotes.affordance_in_scope(ada, game)
        assert offered == gate is True, place


def test_take_notes_parses_anywhere():
    game, ada = _world()
    for place in ("The Green", "Cafe", "Library"):
        _move(game, ada, place)
        assert game.parser.parse_command(
            "take_notes the acoustics of the hall", actor=ada
        ), place


# -- gate: a topic is required ---------------------------------------------------


def test_take_notes_without_a_topic_fails_with_actionable_feedback():
    game, ada = _world()
    assert not game.parser.parse_command("take_notes", actor=ada)
    msg = getattr(game.parser, "last_fail_message", "")
    assert "note" in msg.lower()


# -- tool schema shape -----------------------------------------------------------


def test_take_notes_tool_requires_topic_and_advertises_pacing_slots():
    brain = PerActionBrain("take_notes", {"topic": "the rubber sheet demo"})
    game, ada = _world(llm_client=brain, place="The Green")
    observe_and_decide(game, ada, 0)
    tool = {t["name"]: t for t in brain.offers[0]["tools"]}["take_notes"]
    props = tool["parameters"]["properties"]
    assert "topic" in props
    assert "topic" in tool["parameters"].get("required", [])
    # The #581 pacing opt-in: a chosen note-taking session settles.
    assert "duration_minutes" in props
    assert "emoji" in props


def test_take_notes_meta_args_stash_without_leaking_into_the_command():
    brain = PerActionBrain(
        "take_notes",
        {
            "topic": "curvature and geodesics",
            "duration_minutes": 30,
            "emoji": "\U0001f4dd",
        },
    )
    game, ada = _world(llm_client=brain, place="The Green")
    command = observe_and_decide(game, ada, 0)
    assert command == "take_notes curvature and geodesics"  # no "30", no emoji
    assert ada.agent.last_duration_minutes == 30
    assert ada.agent.last_emoji == "\U0001f4dd"


# -- effects ----------------------------------------------------------------------


def test_take_notes_sets_the_activity_label():
    game, ada = _world()
    assert game.parser.parse_command("take_notes curvature and geodesics", actor=ada)
    assert ada.get_property("activity") == "taking notes on curvature and geodesics"


# -- settles in the step loop (#581) ----------------------------------------------


class _StubMap:
    def walk_path(self, src, address, furniture=None):
        return [(1, 1)]


def _clock():
    return SimClock(datetime.datetime(2023, 2, 13, 12, 0, 0), sec_per_step=10)


def _state():
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


def test_take_notes_settles_instead_of_re_deciding_every_tick():
    brain = PerActionBrain("take_notes", {"topic": "the acoustics"})
    game, ada = _world(llm_client=brain, place="The Green")
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    st = state["Ada"]
    assert st["performing"] is True  # settled -- not the instantaneous branch
    assert "taking notes on the acoustics" in st["desc"]


def test_take_notes_settles_for_the_model_duration():
    # 20 minutes at 10s/step = 120 steps, same arithmetic the #581 tests pin.
    brain = PerActionBrain(
        "take_notes", {"topic": "the acoustics", "duration_minutes": 20}
    )
    game, ada = _world(llm_client=brain, place="The Green")
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    assert state["Ada"]["performing"] is True
    assert state["Ada"]["perform_until"] == 0 + 120


# -- the note memory (the point of the verb) ---------------------------------------


def test_render_pins_the_take_notes_reflections():
    assert (
        render("reflection", verb="take_notes", topic="curvature and geodesics")
        == "I took notes on curvature and geodesics."
    )
    # Defensive fallback only -- the gate requires a topic.
    assert render("reflection", verb="take_notes", topic="") == "I took some notes."


def _spy_memory(char):
    seen = {}
    orig = char.agent.memory.add_observation

    def spy(text, **kw):
        seen["text"] = text
        seen["importance"] = kw.get("importance", 1.0)
        seen["tags"] = kw.get("tags")
        return orig(text, **kw)

    char.agent.memory.add_observation = spy
    return seen


def test_remember_outcome_writes_the_note_above_default_importance():
    game, ada = _world()
    assert game.parser.parse_command("take_notes curvature and geodesics", actor=ada)
    seen = _spy_memory(ada)
    remember_outcome(ada, "take_notes curvature and geodesics", 3)
    assert seen["text"] == "I took notes on curvature and geodesics."
    # Above the routine 2.0 action records (the check_out_book/read tier), so
    # importance-weighted retrieval keeps surfacing what the agent chose to
    # write down. NOT locked: #583's score_new_memories may re-score it.
    assert seen["importance"] == 3.0
    assert ACTION_TAG in seen["tags"]


# -- Penn registration ---------------------------------------------------------------


def test_penn_world_registers_and_offers_take_notes():
    from penn_world import PENN_ACTION_VERBS, PENN_EXTRA_ACTIONS, build_penn_world

    assert "take_notes" in PENN_ACTION_VERBS
    assert TakeNotes in PENN_EXTRA_ACTIONS
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    attach_agents(chars, pw.personas, extra_action_names=PENN_ACTION_VERBS)
    char = next(iter(chars.values()))
    # An untagged arena -- exactly where #811 found study was never offered.
    _move(game, char, "College Hall")
    assert "take_notes" in _tool_names(game, char)
    assert game.parser.parse_command("take_notes the lecture", actor=char)
    assert game.parser.actions["take_notes"] is TakeNotes
