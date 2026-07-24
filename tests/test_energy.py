"""Tests for the energy/food system (TDD scaffold — implementation pending).

Describes the intended behavior before the feature exists:
1. Every Character starts with a default energy value (things/characters.py).
2. Eating food restores energy, gated by Property.EDIBLE (actions/consume.py).
3. Energy is deducted once per turn via Game.end_turn() (games.py).
4. Energy is deducted per successful action, skipping FREE_ACTIONs (stretch goal).
5. Energy never exceeds a max or drops below 0.

Run with: uv run pytest tests/test_energy.py -v
Expect failures until Character/Eat/Game are updated per the plan.
"""

import pytest  # CLASS that for test

from text_adventure_games import (
    games,
    things,
)  # from text adventure import things superclass and game to run game
from text_adventure_games.enums import (
    Property,
)  # from enums we need property to set properties for food and hunger


# testing set up
@pytest.fixture  # NOT SURE WHAT THIS DOES - NEED TO REVIEW
def tiny_game():
    """A 1-room world with just a player, matching the tiny_game convention
    used in test_triggers.py / test_time_model.py."""
    field = things.Location("Field", "An open grassy field.")
    player = things.Character("player", "a brave adventurer", "I explore.")
    game = games.Game(field, player, characters=[])
    return game


# add a is_cooked if everythig works later on
@pytest.fixture
def fish(tiny_game):
    """An edible item carried by the player, worth 20 energy."""
    item = things.Item("fish", "a big trout fish")
    item.set_property(Property.EDIBLE, True)  # already in the game
    item.set_property("energy_value", 20)  # to be added to the game
    tiny_game.player.add_to_inventory(item)
    return item


@pytest.fixture
def troll(tiny_game):
    troll = things.Character(
        "troll", "a mean troll", "hello I'm Shkrek"
    )  # fix: was things.Characters (doesn't exist)
    tiny_game.add_character(troll)
    return troll


def test_character_starts_with_default_energy(tiny_game):
    assert tiny_game.player.get_property(Property.ENERGY) == 50  # start out with 50


def test_npc_also_starts_with_default_energy():
    npc = things.Character("troll", "a mean troll", "I am hungry.")
    assert npc.get_property(Property.ENERGY) == 50


# 1. eating food suite test
# eating increases energy by amount
def test_eating_food_increases_energy(tiny_game, fish):
    tiny_game.player.set_property(Property.ENERGY, 50)
    tiny_game.do_command("eat fish")
    assert tiny_game.player.get_property(Property.ENERGY) == 69


# if food property is set to false then can't be eaten
def test_eating_food_edible_false(tiny_game, fish):
    fish.set_property(Property.EDIBLE, False)
    assert tiny_game.do_command("eat fish") == False
    assert tiny_game.player.get_property(Property.ENERGY) == 49


# You cannot eat non edible item
def test_eating_non_edible_item_does_not_change_energy(tiny_game):
    rock = things.Item("rock", "a plain rock")
    rock.set_property(Property.EDIBLE, False)
    tiny_game.player.add_to_inventory(rock)
    tiny_game.player.set_property(Property.ENERGY, 50)
    tiny_game.do_command("eat rock")
    assert tiny_game.player.get_property(Property.ENERGY) == 50
    # fix: do_command lives on Game, not Character
    assert tiny_game.do_command("eat rock") == False


# You cannot eat if maximum
def test_energy_does_not_exceed_max_on_eating(tiny_game, fish):
    tiny_game.player.set_property(Property.ENERGY, 90)
    tiny_game.do_command("eat fish")
    assert tiny_game.player.get_property(Property.ENERGY) == 100


# each turn energy gets deducted by a little
def test_end_turn_deducts_energy(tiny_game):
    start = tiny_game.player.get_property(Property.ENERGY)
    tiny_game.end_turn()
    assert tiny_game.player.get_property(Property.ENERGY) == start - 1


# NPC does not loose energy points
def test_end_turn_npc_energy(tiny_game, troll):
    tiny_game.add_character(troll)
    # fix: game.characters is a dict (name -> Character), not callable
    start = tiny_game.characters["troll"].get_property(Property.ENERGY)
    tiny_game.end_turn()
    assert tiny_game.characters["troll"].get_property(Property.ENERGY) == start


# item is not in inventory after it's eaten
def test_item_not_in_inventory_after_eaten(tiny_game, fish):
    start = tiny_game.player.get_property(Property.ENERGY)

    if tiny_game.player.is_in_inventory(fish):
        tiny_game.player.discard_item(fish)

    assert tiny_game.do_command("eat fish") == False
    assert tiny_game.player.get_property(Property.ENERGY) == start


# After eating item is not in inventory
def test_item_discared_after_eating(tiny_game, fish):
    tiny_game.player.add_to_inventory(fish)
    tiny_game.do_command("eat fish")
    return not (tiny_game.player.is_in_inventory(fish))


def test_energy_does_not_go_below_zero(tiny_game):
    tiny_game.player.set_property(Property.ENERGY, 0)
    tiny_game.end_turn()
    assert tiny_game.player.get_property(Property.ENERGY) == 0


# unskipped: per-action energy cost is now implemented in Game.do_command
def test_successful_action_costs_energy(tiny_game):
    start = tiny_game.player.get_property(Property.ENERGY)
    tiny_game.do_command("look")
    assert tiny_game.player.get_property(Property.ENERGY) < start


# unskipped: per-action energy cost is now implemented in Game.do_command
def test_free_actions_do_not_cost_energy(tiny_game):
    start = tiny_game.player.get_property(Property.ENERGY)
    tiny_game.do_command("inventory")
    assert tiny_game.player.get_property(Property.ENERGY) == start
