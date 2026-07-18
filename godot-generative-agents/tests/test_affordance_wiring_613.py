"""Penn affordance wiring (#613): the per-decide toolset inherits #612's
affordance curation, arena tags come from world data, and the live decide
prompt gains a nearby-affordances line -- all without disturbing the
byte-identical mock bake.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_affordance_wiring_613.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    ARENA_AFFORDANCE_TAGS,
    action_tools_for,
    attach_agents,
    nearby_affordances_line,
    observe_and_decide,
)
from backend.prompt_templates import render  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402
from text_adventure_games.llm_client import MockLlmClient, ToolCallResult  # noqa: E402
from text_adventure_games.things import Item, Location  # noqa: E402


# A three-location, one-persona world (mirrors test_decide_context's tiny world).
def _locations():
    return [
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
        },
    ]


def _personas():
    return [
        {
            "name": "Ada",
            "home": "The Green",
            "persona": "I am Ada, a curious first-year.",
            "emoji": "\U0001f4d6",
            "destination": "Cafe",
            "activity": "reading a novel",
            "schedule": [
                {
                    "place": "Cafe",
                    "activity": "reading a novel",
                    "emoji": "\U0001f4d6",
                    "steps": None,
                }
            ],
        }
    ]


def _world_with_offer(extra):
    """(game, Ada) with `extra` verbs added to every agent's action_names."""
    personas = _personas()
    game, chars = build_world(None, personas, _locations())
    attach_agents(chars, personas, extra_action_names=extra)
    return game, chars["Ada"]


def _tool_names(game, char):
    return {t["name"] for t in action_tools_for(game, char)}


def test_action_tools_for_curates_a_tagged_verb_by_scope():
    # `read` declares REQUIRED_AFFORDANCES = (READABLE,) in the engine (#612).
    game, ada = _world_with_offer(["read"])

    # A READABLE book only at the Cafe.
    book = Item("book", "a slim paperback")
    book.set_property(Property.READABLE, True)
    game.locations["Cafe"].add_item(book)

    # In a bare arena (home / The Green): nothing READABLE in scope -> no `read`.
    assert "read" not in _tool_names(game, ada)
    # travel/perform are universal (empty declaration) and always offered.
    assert {"travel", "perform"} <= _tool_names(game, ada)

    # Walk Ada to the Cafe: the book is now in scope -> `read` is offered.
    game.locations["The Green"].remove_character(ada)
    game.locations["Cafe"].add_character(ada)
    assert "read" in _tool_names(game, ada)


def test_build_world_applies_location_properties():
    locs = [
        {"name": "Hub", "description": "h", "address": None, "hub": True},
        {
            "name": "Lib",
            "description": "l",
            "address": "T:Lib:x",
            "properties": ["studyable"],
        },
    ]
    personas = _personas()
    personas[0]["home"] = "Hub"
    personas[0]["destination"] = "Hub"
    personas[0]["schedule"] = [
        {"place": "Hub", "activity": "idling", "emoji": "\U0001f4d6", "steps": None}
    ]
    game, _chars = build_world(None, personas, locs)
    assert game.locations["Lib"].get_property("studyable")
    # No `properties:` key -> no tags, existing worlds unchanged.
    assert not game.locations["Hub"].get_property("studyable")


def test_penn_arena_tags_are_authored():
    pw = build_penn_world()
    game, _chars = pw.build_world_fn(pw.world_map)
    assert game.locations["Van Pelt — Moelis Reading Room"].get_property("studyable")
    assert game.locations["Van Pelt — Study Booths"].get_property("studyable")
    assert game.locations["Houston Hall"].get_property("dining")
    # An untagged arena stays untagged -- tags are authored, not blanket.
    assert not game.locations["College Hall"].get_property("studyable")
    assert not game.locations["College Hall"].get_property("dining")


TRAVEL = ToolCallResult(
    text=None,
    tool_calls=[
        {
            "id": "call_1",
            "name": "travel",
            "arguments": {"reasoning": "go study", "destination": "Library"},
        }
    ],
)


class _FakeGame:
    """Just enough game for the helper: a fixed perceivable set."""

    def __init__(self, perceivable):
        self._perceivable = perceivable

    def perceivable_locations(self, _char):
        return self._perceivable


class _CharAt:
    def __init__(self, location):
        self.location = location


def _tagged(name, tag):
    loc = Location(name, name)
    loc.set_property(tag, True)
    return loc


def test_nearby_line_lists_tagged_arenas_and_skips_here_and_untagged():
    here = Location("The Green", "the lawn")
    reading = _tagged("Van Pelt — Moelis Reading Room", "studyable")
    houston = _tagged("Houston Hall", "dining")
    plain = Location("College Hall", "admin")  # no tag -> skipped
    game = _FakeGame([here, plain, houston, reading])  # unsorted on purpose
    char = _CharAt(here)

    line = nearby_affordances_line(game, char)
    # Sorted by name; `here` and the untagged arena are absent.
    assert line == (
        "Nearby, worth traveling to: "
        "Houston Hall (dining); Van Pelt — Moelis Reading Room (studyable)."
    )


def test_nearby_line_is_empty_when_nothing_tagged_is_in_sight():
    here = Location("The Green", "the lawn")
    game = _FakeGame([here, Location("College Hall", "admin")])
    assert nearby_affordances_line(game, _CharAt(here)) == ""


def test_studyable_and_dining_are_known_arena_tags():
    assert "studyable" in ARENA_AFFORDANCE_TAGS
    assert "dining" in ARENA_AFFORDANCE_TAGS


def test_decide_prompt_carries_the_nearby_line_under_a_real_brain():
    brain = MockLlmClient(tool_calls_responses=[TRAVEL])
    game, ada = _world_with_offer(None)
    ada.agent.llm_client = brain  # make _use_action_tools(agent) true

    # Ada stands on The Green (untagged); the Library nearby is studyable.
    game.locations["Library"].set_property("studyable", True)
    game.perceivable_locations = lambda char: [
        game.locations["The Green"],
        game.locations["Library"],
    ]

    observe_and_decide(game, ada, 0)

    user = brain.tool_calls_log[0]["messages"][-1]["content"]
    assert "Nearby, worth traveling to: Library (studyable)." in user


def test_mock_never_sees_the_nearby_line():
    # Default mock brain: _use_action_tools is false -> no line, bake unchanged.
    game, ada = _world_with_offer(None)  # no llm_client -> mock == schedule brain
    game.locations["Library"].set_property("studyable", True)
    game.perceivable_locations = lambda char: [
        game.locations["The Green"],
        game.locations["Library"],
    ]

    base = game.describe_for(ada)
    observe_and_decide(game, ada, 0)
    # The mock decides off describe_for's first line; the nearby line is never
    # added on its path. Assert the helper's phrase is absent from the base the
    # mock reads (the deterministic guard the byte-identical bake relies on).
    assert "Nearby, worth traveling to" not in base


def test_render_pins_the_nearby_line():
    assert render(
        "nearby_affordances",
        arenas="Van Pelt — Moelis Reading Room (studyable); Houston Hall (dining)",
    ) == (
        "Nearby, worth traveling to: "
        "Van Pelt — Moelis Reading Room (studyable); Houston Hall (dining)."
    )
