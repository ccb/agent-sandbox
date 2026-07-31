"""Tests for EatPenn (#931): Penn meals restoring energy.

Plain `eat` already worked in Penn before this -- Houston Hall is furnished
with EDIBLE meals (penn_world.py's _furnish_meals) and the engine's
affordance-gated Eat (REQUIRED_AFFORDANCES = (Property.EDIBLE,)) offers it
there. EatPenn (backend/actions.py) adds the energy payoff: it overrides
"eat" (mirroring DrinkPenn's override-by-same-action-name pattern) and
restores Property.ENERGY from the eaten item's energy_value, capped at
MAX_ENERGY -- the same way Action Castle's Eat override does.

This is the #931 scaffold slice: energy restore only. The 16-hour eat-again
cooldown (Action Castle's ate_food/ate_at pair) is a deliberate follow-up --
see the TODOs below and #931's open design question (a boolean flag + a
timestamp vs. a single Property.NOT_HUNGRY_TIME "resume-hunger-at" value).

Run with: uv run pytest godot-generative-agents/tests/test_eat_energy.py -v
"""

from backend.actions import EatPenn  # noqa: E402
from backend.build_world import _normalize_personas, build_world  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402
from text_adventure_games.things.characters import MAX_ENERGY  # noqa: E402
from text_adventure_games.things.items import Item  # noqa: E402

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


def _sandwich(energy_value=20):
    item = Item("sandwich", "a wrapped sandwich", "A turkey club.")
    item.set_property(Property.EDIBLE, True)
    item.set_property("energy_value", energy_value)
    return item


def test_eat_override_is_registered():
    game, _ = _tiny_world(extra_actions=[EatPenn])
    assert game.parser.actions["eat"] is EatPenn


def test_eating_restores_energy_by_the_items_value():
    game, char = _tiny_world(extra_actions=[EatPenn])
    char.set_property(Property.ENERGY, 50)
    game.locations["Union"].add_item(_sandwich(energy_value=20))
    assert game.parser.parse_command("get sandwich", actor=char)
    assert game.parser.parse_command("eat sandwich", actor=char)
    assert char.get_property(Property.ENERGY) == 70


def test_energy_is_capped_at_max_energy():
    game, char = _tiny_world(extra_actions=[EatPenn])
    char.set_property(Property.ENERGY, MAX_ENERGY - 10)
    game.locations["Union"].add_item(_sandwich(energy_value=20))
    assert game.parser.parse_command("get sandwich", actor=char)
    assert game.parser.parse_command("eat sandwich", actor=char)
    assert char.get_property(Property.ENERGY) == MAX_ENERGY


def test_eaten_item_is_removed_from_inventory():
    game, char = _tiny_world(extra_actions=[EatPenn])
    char.set_property(Property.ENERGY, 50)
    game.locations["Union"].add_item(_sandwich())
    assert game.parser.parse_command("get sandwich", actor=char)
    assert game.parser.parse_command("eat sandwich", actor=char)
    assert "sandwich" not in char.inventory


def test_eating_a_poisonous_item_does_not_restore_energy():
    # Mirrors DrinkPenn's is_dead guard: the engine's Eat already kills the
    # character on a poisonous item (consume.Eat.apply_effects); a corpse
    # shouldn't also get an energy "reward" from what just killed it.
    game, char = _tiny_world(extra_actions=[EatPenn])
    char.set_property(Property.ENERGY, 50)
    poison = _sandwich(energy_value=20)
    poison.set_property(Property.IS_POISONOUS, True)
    game.locations["Union"].add_item(poison)
    assert game.parser.parse_command("get sandwich", actor=char)
    assert game.parser.parse_command("eat sandwich", actor=char)
    assert char.get_property("is_dead") is True
    assert char.get_property(Property.ENERGY) == 50


def test_live_penn_world_meals_carry_energy_value():
    # Wiring check: the real Penn world (not this file's tiny synthetic one)
    # must actually furnish Houston Hall's meals with energy_value, or
    # EatPenn has nothing to restore energy *from* in the live sim/bake.
    from backend.penn.penn_world import build_penn_world

    world = build_penn_world()
    game, _characters = world.build_world_fn(world.world_map)
    hall = game.locations.get("Houston Hall")
    assert hall is not None
    meals = [item for item in hall.items.values() if item.get_property(Property.EDIBLE)]
    assert meals, "expected at least one EDIBLE meal in Houston Hall"
    for meal in meals:
        assert meal.get_property("energy_value")


# TODO (#931 follow-ups, not yet implemented):
# - A 16-in-game-hour eat-again cooldown, porting Action Castle's
#   ate_food/ate_at pair -- or Property.NOT_HUNGRY_TIME as a single
#   "resume-hunger-at" timestamp instead (open design question in #931).
# - An energy *decay* drive (backend/drives.py::accrue_energy, mirroring
#   accrue_thirst) so energy actually falls over time between meals --
#   see test_energy_drive.py, currently its own failing TDD scaffold.
# - Clearing Property.IS_HUNGRY / setting it back true on decay, once a
#   hunger drive exists to set it in the first place.
# - An end-to-end scenario test driving a scheduled Penn persona through
#   travel -> get meal -> eat, the way test_eat_energy's tiny world skips
#   straight to "get"/"eat" without a real schedule stop.
