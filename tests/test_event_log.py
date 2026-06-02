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
