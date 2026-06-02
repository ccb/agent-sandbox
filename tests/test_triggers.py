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


def test_at_turn_trigger_fires_once(tiny_game):
    fired = []
    tiny_game.add_trigger("boom", at_turn(2), lambda g: fired.append(g.turn))
    tiny_game.end_turn()  # turn 1 -> condition false
    assert fired == []
    tiny_game.end_turn()  # turn 2 -> fires
    assert fired == [2]
    tiny_game.end_turn()  # turn 3 -> non-repeatable, already fired
    assert fired == [2]


def test_every_repeatable_trigger_fires_each_period(tiny_game):
    ticks = []
    tiny_game.add_trigger(
        "tick", every(2), lambda g: ticks.append(g.turn), repeatable=True
    )
    for _ in range(4):
        tiny_game.end_turn()  # turns 1, 2, 3, 4
    assert ticks == [2, 4]


def test_in_location_trigger_fires_via_player_move(tiny_game):
    forest = tiny_game.locations["Forest"]
    player = tiny_game.player
    entered = []
    tiny_game.add_trigger(
        "reached", in_location(player, forest), lambda g: entered.append(g.turn)
    )
    tiny_game.do_command("go north")  # player moves; react phase fires the trigger
    assert entered == [1]


def test_compound_trigger(tiny_game):
    troll = tiny_game.characters["troll"]
    fired = []
    tiny_game.add_trigger(
        "ambush",
        all_of(at_turn(1), has_property(troll, "is_angry")),
        lambda g: fired.append(True),
        repeatable=True,
    )
    tiny_game.end_turn()  # turn 1 but troll not angry -> no fire
    assert fired == []
    troll.set_property("is_angry", True)
    # turn 2: at_turn(1) is still true (turn >= 1), so anger is the only gate -> fires
    tiny_game.end_turn()
    assert fired == [True]


def test_from_command_trigger_respects_precondition_gate(tiny_game):
    troll = tiny_game.characters["troll"]
    tiny_game.add_trigger("flee", at_turn(1), from_command("troll go south"))
    tiny_game.end_turn()  # fires, but Field has no south exit
    assert troll.location is tiny_game.locations["Field"]  # did not move


def test_from_command_trigger_runs_valid_command(tiny_game):
    troll = tiny_game.characters["troll"]
    tiny_game.add_trigger("advance", at_turn(1), from_command("troll go north"))
    tiny_game.end_turn()
    assert troll.location is tiny_game.locations["Forest"]


def test_trigger_firing_is_logged(tiny_game):
    tiny_game.add_trigger("boom", at_turn(1), lambda g: None)
    tiny_game.end_turn()
    assert any(e.actor == "trigger" and e.action == "boom" for e in tiny_game.events)


def test_cascade_fires_dependent_trigger_one_level(tiny_game):
    troll = tiny_game.characters["troll"]
    order = []
    # B is registered before A and depends on a property A sets:
    tiny_game.add_trigger(
        "B", has_property(troll, "awake"), lambda g: order.append("B")
    )
    tiny_game.add_trigger("A", at_turn(1), lambda g: troll.set_property("awake", True))
    tiny_game.end_turn()
    # pass 1: B sees awake=False (no fire), A fires and sets awake.
    # pass 2: B now sees awake=True and fires.
    assert order == ["B"]


def test_cascade_cap_terminates(tiny_game):
    fires = []
    bump = lambda g: fires.append(1)
    # Two always-true repeatable triggers. Without the per-round guard they would
    # re-fire on the second cascade pass (4 fires total); the guard caps each at
    # one firing per round, so the count stays 2 and the pass loop then stops.
    tiny_game.add_trigger("X", every(1), bump, repeatable=True)
    tiny_game.add_trigger("Y", every(1), bump, repeatable=True)
    tiny_game.end_turn()
    assert len(fires) == 2
