import pytest
from text_adventure_games.actions import Action
from text_adventure_games.adventures import action_castle
from text_adventure_games import (
    things,
    games,
)
from text_adventure_games.enums import Property

from text_adventure_games.adventures.action_castle import (
    Eat,
    Set_energy,
    Check_energy,
    Unlock_Door,
    Read_Runes,
)
from text_adventure_games.reporting import CaptureRenderer
from tests.test_action_castle_2 import _said
from text_adventure_games import clock
DEAFULT_EXERCISE_COST = 15
DEFAULT_PER_TURN_DEDUCTION = 1


# creat a game so you can test for each
@pytest.fixture
def tiny_game():
    """Initialize a game of action castle each time so you can test different aspects of the game"""

    player = things.Character("player", "a brave worrior", "I eat")
    player.set_property("energy", 50)

    # Locations
    gym = things.Location("gym", "an outdoors gym")
    garden = things.Location("Garden", " A lush garden full of fruits and vegetables")
    # Add connections
    garden.add_connection("east", gym)
    gym.add_connection("west", garden)

    # food items
    apple = things.Item("apple", "A lush green apple", "Looks really good")
    banana = things.Item("banana", "A normal looking banana", "Looks yellow")
    pear = things.Item("pear", "A foul smelling pear", "Looks rotten")
    poisoned_apple = things.Item(
        "poisoned apple",
        "Looks like a redish apple",
        "there's a skull with bones on it",
    )

    # make food edible
    apple.set_property("edible", True)
    banana.set_property("edible", True)
    pear.set_property("edible", True)
    poisoned_apple.set_property("edible", True)

    apple.set_property("energy_value", 20)
    banana.set_property("energy_value", 30)
    pear.set_property("energy_value", -20)  # very sweet - makes you dizzy

    poisoned_apple.set_property("is_poisonous", True)

    # add items to garden
    garden.add_item(apple)
    garden.add_item(poisoned_apple)
    garden.add_item(pear)
    garden.add_item(banana)

    # define action excercise
    class Excercise(Action):
        ACTION_NAME = "excercise"
        ACTION_DESCRIPTION = "DO SOME PUSHUPSS NOW!!"
        ACTION_ALIASES = ["pushup", "sit up", "weights"]

        def __init__(self, game, command, actor=None):
            super().__init__(game, actor=actor)
            self.character = player

        def check_preconditions(self) -> bool:
            if not self.character.get_property("energy") > 10:
                return False
            if not self.was_matched(self.character):
                return False
            if not self.character.location == gym:
                return False
            return True

        def apply_effects(self):
            """Character simply looses some energy
            and can't excercise after a while"""
            curr_energy = self.character.get_property("energy")
            self.character.set_property("energy", curr_energy - DEAFULT_EXERCISE_COST)
            self.parser.ok("Getting stronger")

    actions_available = [
        Eat,
        Set_energy,
        Check_energy,
        Unlock_Door,
        Read_Runes,
        Excercise,
    ]
    game = games.Game(garden, player, [], actions_available)
    return game


# add a troll for later tests
# will add a troll block later so the player can only fight
# the troll if energy is 80 or more
@pytest.fixture
def troll(tiny_game):
    troll = things.Character("troll", "a mean troll", "Hi amd I mean and hungry Troll")
    tiny_game.add_character(troll)
    return troll


# ----Testing suite------#
# 1. Tesing setup - basic eat increse of energy, decrease becaue of non-free action


def test_character_starts_with_default_energy(tiny_game):
    assert tiny_game.player.get_property(Property.ENERGY) == 50


def test_character_after_eating_energy(tiny_game):
    player = tiny_game.player
    tiny_game.do_command("get apple")
    tiny_game.do_command("eat apple")  # apple is worth 20 so total is 70
    tiny_game.do_command("show energy")
    assert player.get_property("energy") == 70


def test_eating_pear_decreases_energy(tiny_game):
    """pear's energy_value is -20, so eating it should REDUCE energy."""
    player = tiny_game.player
    tiny_game.do_command("get pear")
    tiny_game.do_command("eat pear")  # 50 + (-20) = 30
    assert player.get_property("energy") == 30


def test_excercise_costs_energy_at_gym(tiny_game):
    """excercise only works at the gym and costs DEAFULT_EXERCISE_COST (15)."""
    player = tiny_game.player
    tiny_game.do_command("east")  # garden -> gym
    result = tiny_game.do_command("excercise")
    assert result is True
    assert player.get_property("energy") == 35  # 50 - 15


def test_excercise_fails_when_not_at_gym(tiny_game):
    """excercise's check_preconditions requires location == gym; player starts
    in the garden, so this should fail and energy should be untouched."""
    player = tiny_game.player
    result = tiny_game.do_command("excercise")
    assert result is False
    assert player.get_property("energy") == 50


# ---- TODO: write these yourself -------------------------------------------
# Each one below is a real gap in coverage -- same fixture, just a different
# scenario. Follow the pattern above: do_command(...) then assert on
# tiny_game.player.get_property(...) or tiny_game.player.inventory.

# TODO: test_eating_poisoned_apple_kills_player
#   get + eat the poisoned_apple, then assert the player's "is_dead" property
#   is True. (This comes from consume.Eat.apply_effects via super() -- your
#   Eat override doesn't need to implement poison itself, it inherits it.)
def test_eating_poisoned_apple_kills_player(tiny_game):
    player = tiny_game.player
    tiny_game.do_command("get the poisoned apple")
    result = tiny_game.do_command("eat poisoned apple")
    if result:
        assert player.get_property("is_dead") == True
    else: False

# TODO: test_show_energy_reports_current_value
#   Check_energy's apply_effects calls self.parser.ok(f"{energy} is your
#   energy level") -- you'll need a CaptureRenderer (see test_scenarios.py or
#   test_action_castle_2.py for the pattern) to assert on the printed text,
#   since "show energy" only reports a value, it doesn't return one.
def test_show_energy_reports_current_valyue(tiny_game):
    player = tiny_game.player
    energy = player.get_property("energy")
    fresh = CaptureRenderer()
    tiny_game.parser.set_renderer(fresh)
    result = tiny_game.do_command("show energy")
    assert result == True
    assert _said(fresh,f"{energy} is your energy level")

# TODO: test_set_energy_resets_to_50
#   Set energy to something else first (e.g. player.set_property("energy", 5)),
#   then do_command("energy mode"), then assert energy == 50.

def test_set_energy_rests_to_50(tiny_game):
    player = tiny_game.player
   
    tiny_game.do_command("get apple")
    tiny_game.do_command("eat apple")
    energy = player.get_property("energy")
    assert energy == 70
    
    tiny_game.do_command("energy mode")
    energy_after = player.get_property("energy")
    assert energy_after == 50

# TODO: test_excercise_fails_when_energy_at_or_below_10
#   check_preconditions requires energy > 10. Set energy to 10 (or less)
#   before moving to the gym, then assert "excercise" fails and energy is
#   unchanged.
def test_excercise_fails_when_energy_at_or_below_10(tiny_game):
    player = tiny_game.player
    player.set_property("energy",10)
    tiny_game.do_command("go east")
    result = tiny_game.do_command("excercise")
    assert result == False

# TODO: test_item_removed_from_inventory_after_eating
#   get + eat any food item, then assert it's no longer in
#   tiny_game.player.inventory.
def test_item_removed_from_inventory_after_eating(tiny_game):
    player = tiny_game.player
    tiny_game.do_command('get apple')
    tiny_game.do_command("eat apple")
    assert "apple" not in player.inventory
