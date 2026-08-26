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
    known_food_location_line,
    known_sleep_location_line,
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
    assert game.locations["Houston Hall"].get_property("marketplace")
    assert game.locations["Houston Hall — Reading Room"].get_property("sleepable")
    # An untagged arena stays untagged -- tags are authored, not blanket.
    assert not game.locations["College Hall"].get_property("studyable")
    assert not game.locations["College Hall"].get_property("dining")


def test_penn_hungry_and_sleepy_arenas_surface_their_full_tag_set():
    # #931 follow-up: a hungry/sleepy brain needs a locational hint, the same
    # way thirst/dining already worked -- Houston Hall's marketplace tag (not
    # just dining) and the Reading Room's sleepable tag must both appear in
    # the nearby-affordances line once in sight, not just be set on the
    # location object (test_penn_arena_tags_are_authored checks the latter).
    pw = build_penn_world()
    game, _chars = pw.build_world_fn(pw.world_map)
    houston = game.locations["Houston Hall"]
    reading_room = game.locations["Houston Hall — Reading Room"]
    game.perceivable_locations = lambda char: [houston, reading_room]
    line = nearby_affordances_line(game, _CharAt(game.locations["College Hall"]))
    assert "Houston Hall (dining, marketplace)" in line
    assert "Houston Hall — Reading Room (sleepable)" in line


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
    # Pin the generic nearby-affordance rendering; #849's focused tests cover
    # the schedule-aware destination filter.
    ada.agent.schedule = None

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
    # Default mock brain: _use_action_tools is false -> the nearby line is never
    # appended, so the bake stays byte-identical. Spy on agent.decide (the seam
    # the mock path calls) to inspect the observation the mock ACTUALLY received
    # -- this fails if the gate regresses and the line leaks onto the mock path.
    game, ada = _world_with_offer(None)  # no llm_client -> mock == schedule brain
    game.locations["Library"].set_property("studyable", True)
    game.perceivable_locations = lambda character: [
        game.locations["The Green"],
        game.locations["Library"],
    ]
    captured = {}
    orig_decide = ada.agent.decide

    def _spy(observation):
        captured["observation"] = observation
        return orig_decide(observation)

    ada.agent.decide = _spy
    observe_and_decide(game, ada, 0)

    assert "observation" in captured  # the mock path really ran
    assert "Nearby, worth traveling to" not in captured["observation"]


def test_known_food_and_sleep_lines_are_campus_wide_not_distance_gated():
    # #931 follow-up: nearby_affordances_line only names arenas within
    # vision_r; known_food_location_line/known_sleep_location_line must find
    # Houston Hall / its Reading Room regardless of where the character is
    # standing or what it can currently see -- these functions never consult
    # perceivable_locations or char.location at all, only game.locations.
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    char = next(iter(chars.values()))
    game.locations["College Hall"].add_character(char)  # far from Houston Hall

    assert known_food_location_line(game, char) == ""  # not hungry yet
    assert known_sleep_location_line(game, char) == ""  # not sleepy yet

    char.set_property("is_low_energy", True)
    char.set_property(Property.IS_SLEEPY, True)

    # Houston Hall — Reception Hall is also stocked now (#907: every
    # dining-tagged location, not just the building-level hall), so it joins
    # the list; sorted by name, it lands after "Houston Hall" itself.
    assert known_food_location_line(game, char) == (
        "Even if it isn't nearby, you know food can be found at: "
        "Houston Hall (dining, marketplace); Houston Hall — Reception Hall (dining)."
    )
    assert known_sleep_location_line(game, char) == (
        "Even if it isn't nearby, you know you can sleep at: "
        "Houston Hall — Reading Room."
    )


def test_decide_prompt_carries_known_food_and_sleep_lines_under_a_real_brain():
    brain = MockLlmClient(tool_calls_responses=[TRAVEL])
    game, ada = _world_with_offer(None)
    ada.agent.llm_client = brain  # make _use_action_tools(agent) true
    game.locations["Cafe"].set_property("dining", True)
    game.locations["Library"].set_property("sleepable", True)
    ada.set_property("is_low_energy", True)
    ada.set_property(Property.IS_SLEEPY, True)
    # Ada is on The Green, neither Cafe nor Library is in her perceivable set.
    game.perceivable_locations = lambda char: [game.locations["The Green"]]

    observe_and_decide(game, ada, 0)

    user = brain.tool_calls_log[0]["messages"][-1]["content"]
    assert (
        "Even if it isn't nearby, you know food can be found at: Cafe (dining)." in user
    )
    assert "Even if it isn't nearby, you know you can sleep at: Library." in user


def test_mock_never_sees_known_food_or_sleep_lines():
    # Same byte-identical-mock guarantee as nearby_affordances_line.
    game, ada = _world_with_offer(None)  # no llm_client -> mock == schedule brain
    game.locations["Cafe"].set_property("dining", True)
    ada.set_property("is_low_energy", True)
    ada.set_property(Property.IS_SLEEPY, True)
    captured = {}
    orig_decide = ada.agent.decide

    def _spy(observation):
        captured["observation"] = observation
        return orig_decide(observation)

    ada.agent.decide = _spy
    observe_and_decide(game, ada, 0)

    assert "observation" in captured
    assert "you know food can be found at" not in captured["observation"]
    assert "you know you can sleep at" not in captured["observation"]


def test_render_pins_the_known_food_and_sleep_lines():
    assert (
        render("known_food_location", places="Houston Hall (dining, marketplace)")
        == "Even if it isn't nearby, you know food can be found at: Houston Hall (dining, marketplace)."
    )
    assert (
        render("known_sleep_location", places="Houston Hall — Reading Room")
        == "Even if it isn't nearby, you know you can sleep at: Houston Hall — Reading Room."
    )


def test_render_pins_the_nearby_line():
    assert render(
        "nearby_affordances",
        arenas="Van Pelt — Moelis Reading Room (studyable); Houston Hall (dining)",
    ) == (
        "Nearby, worth traveling to: "
        "Van Pelt — Moelis Reading Room (studyable); Houston Hall (dining)."
    )
