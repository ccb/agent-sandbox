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
