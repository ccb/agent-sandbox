"""Tests for variable action durations / the per-turn NPC time budget (issue #24)."""

import pytest

from text_adventure_games import games, things
from text_adventure_games.actions.base import Action
from text_adventure_games.actions.locations import Go
from text_adventure_games.actions.rose import Smell_Rose
from text_adventure_games.actions.things import Examine, Inventory
from text_adventure_games.clock import GameClock
from text_adventure_games.llm_client import MockLlmClient
from text_adventure_games.npc import (
    _parse_decision,
    make_hybrid_behavior,
    make_react_behavior,
)


@pytest.fixture
def field_game():
    """Field --north--> Forest, with a player and a troll in the Field."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)
    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")
    game = games.Game(field, player, characters=[troll])
    field.add_character(troll)
    return game


class _StubGame:
    parser = None


class _Quick(Action):
    DURATION = 5


class _Default(Action):
    pass


def test_get_duration_default_is_none():
    assert _Default(_StubGame()).get_duration() is None


def test_get_duration_returns_declared_value():
    assert _Quick(_StubGame()).get_duration() == 5


# ----------------------------------------------------------------------
# Sample declared durations on real actions: quick informational/sensory
# actions are cheap so an NPC can do several in one turn (issue #24). Movement
# (Go) deliberately stays at the default so the clock tests stay pinned.
# ----------------------------------------------------------------------


def test_quick_actions_declare_short_durations():
    assert Smell_Rose.DURATION == 1
    assert Examine.DURATION == 1
    assert Inventory.DURATION == 1


def test_go_keeps_default_duration():
    assert Go.DURATION is None


# ----------------------------------------------------------------------
# _parse_decision: the optional "Duration:" line
# ----------------------------------------------------------------------


def test_parse_decision_reads_duration_line():
    reasoning, command, duration = _parse_decision(
        "Reasoning: it's quick\nAction: smell rose\nDuration: 5"
    )
    assert reasoning == "it's quick"
    assert command == "smell rose"
    assert duration == 5


def test_parse_decision_duration_absent_is_none():
    _, command, duration = _parse_decision("Reasoning: r\nAction: go north")
    assert command == "go north"
    assert duration is None


def test_parse_decision_duration_in_prose_is_extracted():
    _, _, duration = _parse_decision("Action: climb\nDuration: about 30 minutes")
    assert duration == 30


def test_parse_decision_unparseable_duration_is_none():
    _, _, duration = _parse_decision("Action: wait\nDuration: a while")
    assert duration is None


def test_parse_decision_nonpositive_duration_is_none():
    _, _, duration = _parse_decision("Action: blink\nDuration: -3")
    assert duration is None


def test_parse_decision_clamps_absurd_duration():
    _, _, duration = _parse_decision("Action: nap\nDuration: 999999")
    assert duration == 1440  # one in-game day


# ----------------------------------------------------------------------
# Parser records the last successfully executed action (for duration lookup)
# ----------------------------------------------------------------------


def test_parser_records_last_action_on_success(field_game):
    player = field_game.player
    assert field_game.parser.parse_command("go north", actor=player) is True
    assert isinstance(field_game.parser.last_action, Go)
    assert field_game.parser.last_action.get_duration() is None


# ----------------------------------------------------------------------
# take_turn: the per-turn budget loop
#
# Behaviors return the minutes they spent (truthy) to opt into another action
# this turn, or None/falsy when they are done.
# ----------------------------------------------------------------------


def _counting_behavior(minutes, calls):
    """A behavior that records each call and reports it spent `minutes`."""

    def behavior(character, game):
        calls.append(1)
        return minutes

    return behavior


def test_npc_takes_multiple_actions_within_budget(field_game):
    field_game.clock = GameClock(minutes_per_turn=15)
    troll = field_game.characters["troll"]
    calls = []
    troll.set_behavior(_counting_behavior(5, calls))  # 15 / 5 = 3 actions

    troll.take_turn(field_game)
    assert len(calls) == 3


def test_npc_action_costing_full_budget_runs_once(field_game):
    field_game.clock = GameClock(minutes_per_turn=15)
    troll = field_game.characters["troll"]
    calls = []
    troll.set_behavior(_counting_behavior(20, calls))  # one action overruns budget

    troll.take_turn(field_game)
    assert len(calls) == 1  # always >= 1 action, even when it overruns


def test_npc_behavior_returning_none_runs_once(field_game):
    """Legacy behaviors return None -> exactly one action, as before #24."""
    field_game.clock = GameClock(minutes_per_turn=15)
    troll = field_game.characters["troll"]
    calls = []

    def behavior(character, game):
        calls.append(1)
        return None

    troll.set_behavior(behavior)
    troll.take_turn(field_game)
    assert len(calls) == 1


def test_no_clock_means_single_action(field_game):
    """Without a clock there is no budget: one action per turn, as before."""
    troll = field_game.characters["troll"]  # field_game has no clock
    calls = []
    troll.set_behavior(_counting_behavior(5, calls))

    troll.take_turn(field_game)
    assert len(calls) == 1


def test_budget_loop_has_safety_cap(field_game):
    field_game.clock = GameClock(minutes_per_turn=10000)
    troll = field_game.characters["troll"]
    calls = []
    troll.set_behavior(_counting_behavior(1, calls))  # would loop 10000x uncapped

    troll.take_turn(field_game)
    assert len(calls) == 100  # MAX_ACTIONS_PER_TURN


# ----------------------------------------------------------------------
# ReAct / hybrid behaviors report the minutes they spent
# ----------------------------------------------------------------------


def test_react_behavior_returns_estimated_duration(field_game):
    field_game.clock = GameClock(minutes_per_turn=15)
    troll = field_game.characters["troll"]
    behavior = make_react_behavior(MockLlmClient(["Action: go north\nDuration: 5"]))
    assert behavior(troll, field_game) == 5


def test_react_behavior_returns_none_when_llm_silent(field_game):
    field_game.clock = GameClock(minutes_per_turn=15)
    troll = field_game.characters["troll"]
    behavior = make_react_behavior(MockLlmClient(default=None))
    assert behavior(troll, field_game) is None


def test_react_npc_takes_multiple_actions_with_estimates(field_game):
    field_game.clock = GameClock(minutes_per_turn=15)
    troll = field_game.characters["troll"]
    mock = MockLlmClient(
        [
            "Action: go north\nDuration: 5",
            "Action: go south\nDuration: 5",
            "Action: go north\nDuration: 5",
        ]
    )
    troll.set_behavior(make_react_behavior(mock))

    troll.take_turn(field_game)
    assert len(mock.calls) == 3  # three cheap moves fit one 15-minute turn
    assert troll.location is field_game.locations["Forest"]


def test_hybrid_returns_estimate_when_llm_acts(field_game):
    field_game.clock = GameClock(minutes_per_turn=15)
    troll = field_game.characters["troll"]

    def scripted(character, game):
        return None

    behavior = make_hybrid_behavior(
        MockLlmClient(["Action: go north\nDuration: 5"]), scripted
    )
    assert behavior(troll, field_game) == 5
