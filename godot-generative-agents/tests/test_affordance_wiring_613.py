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
    action_tools_for,
    attach_agents,
)
from penn_world import build_penn_world  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402
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
