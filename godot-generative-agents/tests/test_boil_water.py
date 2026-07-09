"""Boil-water action layer (#300): verbs, props, mock replay, memory.

Spec: godot-generative-agents/docs/specs/2026-07-09-boil-water-action-layer.md
"""

from backend.build_world import _normalize_personas, build_world
from backend.actions import DrinkPenn, Activate, Deactivate
from text_adventure_games.enums import Property
from text_adventure_games.things.items import Item

# -- a tiny two-room world, no tile map -----------------------------------
LOCATIONS = [
    {
        "name": "Campus",
        "description": "The campus green.",
        "address": None,
        "hub": True,
    },
    {"name": "Union", "description": "The student union.", "address": None},
]


def _persona(schedule):
    return {
        "name": "Testa",
        "home": "Union",
        "persona": "I am Testa, a test persona.",
        "emoji": "🙂",
        "start_tile": [0, 0],
        "schedule": schedule,
    }


def _tiny_world(extra_actions=()):
    """(game, char) for a one-persona world with the given extra actions."""
    personas = _normalize_personas(
        [_persona([{"place": "Union", "activity": "hanging out", "steps": 5}])]
    )
    game, chars = build_world(
        None, personas, LOCATIONS, extra_actions=list(extra_actions)
    )
    return game, chars["Testa"]


def _cup(contaminated=True):
    cup = Item(
        "cup of murky water", "a cup of murky water", "Cloudy, untreated tap water."
    )
    cup.set_property(Property.DRINKABLE, True)
    if contaminated:
        cup.set_property("is_contaminated", True)
    return cup


def test_drink_override_is_registered():
    game, _ = _tiny_world(extra_actions=[DrinkPenn])
    assert game.parser.actions["drink"] is DrinkPenn


def test_contaminated_drink_sickens_and_logs_event():
    game, char = _tiny_world(extra_actions=[DrinkPenn])
    game.locations["Union"].add_item(_cup())
    assert game.parser.parse_command("get cup of murky water", actor=char)
    assert game.parser.parse_command("drink cup of murky water", actor=char)
    assert char.get_property("is_sick") is True
    sick = [e for e in game.events if e.action == "sickness"]
    assert len(sick) == 1
    assert sick[0].payload["item"] == "cup of murky water"
    assert sick[0].payload["location"] == "Union"


def test_clean_drink_has_no_sickness():
    game, char = _tiny_world(extra_actions=[DrinkPenn])
    game.locations["Union"].add_item(_cup(contaminated=False))
    assert game.parser.parse_command("get cup of murky water", actor=char)
    assert game.parser.parse_command("drink cup of murky water", actor=char)
    assert not char.get_property("is_sick")
    assert not [e for e in game.events if e.action == "sickness"]


def _stove():
    stove = Item("stove", "a small electric stove", "A single coil burner.")
    stove.set_property(Property.GETTABLE, False)
    stove.set_property("is_device", True)
    return stove


def test_activate_and_deactivate_toggle_a_device():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    game.locations["Union"].add_item(_stove())
    assert game.parser.parse_command("activate stove", actor=char)
    stove = game.locations["Union"].items["stove"]
    assert stove.get_property("is_on") is True
    # Already on: the second activate fails at the precondition gate.
    assert not game.parser.parse_command("activate stove", actor=char)
    assert game.parser.parse_command("deactivate stove", actor=char)
    assert stove.get_property("is_on") is False


def test_activate_rejects_a_non_device():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    pot = Item("pot", "a cooking pot", "An empty steel pot.")
    game.locations["Union"].add_item(pot)
    assert not game.parser.parse_command("activate pot", actor=char)
    assert not pot.get_property("is_on")


# -- PennParser.determine_intent regression tests (#300) -------------------
#
# PennParser overrides determine_intent only to catch "activate"/"deactivate"
# before they'd otherwise fall into the engine's buggy "ate " substring check
# (text_adventure_games/parsing.py ~line 296-302, which matches "ate " inside
# "activate" and mis-routes it to EAT). Everything else must delegate to
# Parser.determine_intent unchanged -- these tests pin both the new-verb
# handling and that the delegated path still behaves like the engine parser.


def test_activate_and_deactivate_are_routed_to_device_intents():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    assert game.parser.determine_intent("activate stove", actor=char) == "activate"
    assert game.parser.determine_intent("deactivate stove", actor=char) == "deactivate"


def test_eat_still_word_matches_via_delegation():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    assert game.parser.determine_intent("eat bread", actor=char) == "eat"


def test_drink_still_matches_via_delegation():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    assert (
        game.parser.determine_intent("drink cup of murky water", actor=char) == "drink"
    )


def test_custom_action_fallback_routing_intact_through_delegation():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    assert game.parser.determine_intent("travel to Union", actor=char) == "travel"


# -- authored per-stop commands: normalization, mock replay, action_names --

from backend.smallville_agents import SmallvilleMockClient, attach_agents

COMMANDS = ["get cup of murky water", "drink cup of murky water"]


def _commands_persona():
    return _persona(
        [
            {
                "place": "Union",
                "activity": "hanging out",
                "steps": 5,
                "commands": list(COMMANDS),
            }
        ]
    )


def test_normalize_passes_commands_through():
    spec = _normalize_personas([_commands_persona()])[0]
    assert spec["schedule"][0]["commands"] == COMMANDS
    # Stops authored without commands get an empty list, uniformly.
    other = _normalize_personas([_persona([{"place": "Union", "activity": "idling"}])])[
        0
    ]
    assert other["schedule"][0]["commands"] == []


def test_mock_brain_replays_authored_commands_then_performs():
    schedule = _normalize_personas([_commands_persona()])[0]["schedule"]
    brain = SmallvilleMockClient(schedule)
    away, here = "Campus\nThe green.", "Union\nThe union."
    assert brain._choose(away) == "travel to Union"
    assert brain._choose(here) == "get cup of murky water"
    assert brain._choose(here) == "drink cup of murky water"
    assert brain._choose(here) == "perform hanging out"
    assert brain._choose(here) == "perform hanging out"


def test_action_names_include_authored_verbs():
    personas = _normalize_personas([_commands_persona()])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas)
    assert chars["Testa"].agent.action_names == ["travel", "perform", "drink", "get"]
