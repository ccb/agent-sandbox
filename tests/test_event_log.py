"""Tests for the event log (issue #6): GameEvent records and command capture."""

import pytest

from text_adventure_games import games, things
from text_adventure_games.events import GameEvent


def test_game_event_fields_and_to_primitive():
    event = GameEvent(3, "troll", "go", "troll go north", {"direction": "north"})
    assert event.turn == 3
    assert event.actor == "troll"
    assert event.action == "go"
    assert event.summary == "troll go north"
    assert event.payload == {"direction": "north"}
    assert event.to_primitive() == {
        "turn": 3,
        "actor": "troll",
        "action": "go",
        "summary": "troll go north",
        "payload": {"direction": "north"},
    }


def test_game_event_defaults():
    event = GameEvent(1, "player", "look")
    assert event.summary == ""
    assert event.payload == {}


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


def test_player_command_is_logged(tiny_game):
    tiny_game.do_command("go north")
    assert len(tiny_game.events) == 1
    event = tiny_game.events[0]
    assert event.actor == "player"
    assert event.action == "go"
    assert "north" in event.summary
    # turn is incremented in end_turn AFTER the player's command, so the
    # player's own event carries the pre-increment turn (documented v1 quirk).
    assert event.turn == 0


def test_npc_command_is_logged(tiny_game):
    troll = tiny_game.characters["troll"]
    troll.set_behavior(lambda c, g: g.parser.parse_command("troll go north"))
    tiny_game.end_turn()
    assert any(e.actor == "troll" and e.action == "go" for e in tiny_game.events)


def test_failed_command_is_not_logged(tiny_game):
    tiny_game.do_command("go south")  # Field has no south exit; precondition fails
    assert tiny_game.events == []
