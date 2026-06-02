"""Tests for the trigger system (issue #6)."""

import pytest

from text_adventure_games import games, things
from text_adventure_games.triggers import (
    Trigger,
    at_turn,
    every,
    in_location,
    has_property,
    all_of,
    any_of,
    from_command,
)


@pytest.fixture
def tiny_game():
    """A 2-room world (Field --north--> Forest) with a player and a troll."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)

    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")

    game = games.Game(field, player, characters=[troll])
    field.add_character(troll)
    return game


def test_trigger_holds_its_fields():
    cond = lambda g: True
    act = lambda g: None
    trigger = Trigger("boom", cond, act, repeatable=True)
    assert trigger.name == "boom"
    assert trigger.condition is cond
    assert trigger.action is act
    assert trigger.repeatable is True
    assert trigger.fired is False

    # repeatable defaults to False
    default_trigger = Trigger("quiet", cond, act)
    assert default_trigger.repeatable is False


def test_at_turn(tiny_game):
    cond = at_turn(2)
    tiny_game.turn = 1
    assert cond(tiny_game) is False
    tiny_game.turn = 2
    assert cond(tiny_game) is True
    tiny_game.turn = 5
    assert cond(tiny_game) is True


def test_every(tiny_game):
    cond = every(2)
    tiny_game.turn = 0
    assert cond(tiny_game) is False
    tiny_game.turn = 2
    assert cond(tiny_game) is True
    tiny_game.turn = 3
    assert cond(tiny_game) is False
    # n=0 is guarded (never true), so it can't ZeroDivisionError
    assert every(0)(tiny_game) is False


def test_in_location(tiny_game):
    troll = tiny_game.characters["troll"]
    field = tiny_game.locations["Field"]
    forest = tiny_game.locations["Forest"]
    assert in_location(troll, field)(tiny_game) is True
    assert in_location(troll, forest)(tiny_game) is False


def test_has_property_truthiness(tiny_game):
    troll = tiny_game.characters["troll"]
    # an unset property reads False (get_property returns False for unset)
    assert has_property(troll, "is_angry")(tiny_game) is False
    troll.set_property("is_angry", True)
    assert has_property(troll, "is_angry")(tiny_game) is True
    assert has_property(troll, "is_angry", value=False)(tiny_game) is False


def test_all_of_any_of(tiny_game):
    yes = lambda g: True
    no = lambda g: False
    assert all_of(yes, yes)(tiny_game) is True
    assert all_of(yes, no)(tiny_game) is False
    assert any_of(no, yes)(tiny_game) is True
    assert any_of(no, no)(tiny_game) is False


def test_from_command_calls_parser(tiny_game):
    troll = tiny_game.characters["troll"]
    action = from_command("troll go north")
    action(tiny_game)
    assert troll.location is tiny_game.locations["Forest"]
