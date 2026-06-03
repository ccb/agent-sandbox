"""Offline tests for the time model (issue #7).

Covers the three pieces the issue asks for, plus backward compatibility:

  A. GameClock — turn -> time-of-day mapping, formatting, named periods.
  B. Game integration — opt-in time_config, the turn counter, displays.
  C. Scheduled events — schedule_event(turn, callback), implemented as sugar
     over the trigger system from issue #6 (a non-repeatable at_turn trigger
     fired in the post-round react phase and recorded in the event log).
  D. Serialization — clock config round-trips through to/from_primitive.

Run with pytest::

    pytest tests/test_time_model.py -v
"""

import pytest

from text_adventure_games import games, things
from text_adventure_games.clock import GameClock


@pytest.fixture
def tiny_game_factory():
    """Build a fresh 2-room world (Field --north--> Forest) on demand.

    A factory (rather than a ready-made game) so each test can pass its own
    time_config. The world contains only a player, so rounds advance without
    any NPC behavior involved.
    """

    def build(**game_kwargs):
        field = things.Location("Field", "An open grassy field.")
        forest = things.Location("Forest", "A dark tangled forest.")
        field.add_connection("north", forest)
        player = things.Character("player", "a brave adventurer", "I explore.")
        return games.Game(field, player, **game_kwargs)

    return build


# ----------------------------------------------------------------------
# Section A: GameClock
# ----------------------------------------------------------------------


def test_clock_time_at_start():
    clock = GameClock(start_hour=8, minutes_per_turn=15)
    assert clock.time_at(0) == (0, 8, 0)
    assert clock.format_time(0) == "8:00 AM"


def test_clock_advances_per_turn():
    clock = GameClock(start_hour=8, minutes_per_turn=15)
    assert clock.time_at(1) == (0, 8, 15)
    assert clock.time_at(3) == (0, 8, 45)
    assert clock.time_at(4) == (0, 9, 0)
    assert clock.minutes_elapsed(4) == 60


def test_clock_start_minute():
    clock = GameClock(start_hour=8, start_minute=30, minutes_per_turn=15)
    assert clock.time_at(0) == (0, 8, 30)
    assert clock.time_at(2) == (0, 9, 0)


def test_clock_12_hour_formatting():
    clock = GameClock(start_hour=0, minutes_per_turn=60)
    assert clock.format_time(0) == "12:00 AM"  # midnight
    assert clock.format_time(1) == "1:00 AM"
    assert clock.format_time(12) == "12:00 PM"  # noon
    assert clock.format_time(13) == "1:00 PM"
    assert clock.format_time(23) == "11:00 PM"


def test_clock_wraps_past_midnight():
    clock = GameClock(start_hour=23, minutes_per_turn=30)
    assert clock.time_at(0) == (0, 23, 0)
    assert clock.time_at(1) == (0, 23, 30)
    assert clock.time_at(2) == (1, 0, 0)  # next day, midnight
    assert clock.time_at(4) == (1, 1, 0)  # 1:00 AM the next day


def test_clock_multi_day_counting():
    clock = GameClock(start_hour=8, minutes_per_turn=60)
    day, hour, minute = clock.time_at(40)  # 40 hours later
    assert (day, hour, minute) == (2, 0, 0)


def test_default_periods():
    # One turn per hour starting at midnight: turn number == hour of day.
    clock = GameClock(start_hour=0, minutes_per_turn=60)
    assert clock.period_at(3) == "night"  # before dawn wraps to last period
    assert clock.period_at(5) == "dawn"
    assert clock.period_at(8) == "morning"
    assert clock.period_at(12) == "afternoon"
    assert clock.period_at(17) == "dusk"
    assert clock.period_at(20) == "night"
    assert clock.period_at(23) == "night"


def test_custom_periods_sorted_and_wrapping():
    # Deliberately unsorted input; period_at must still work.
    clock = GameClock(
        start_hour=0,
        minutes_per_turn=60,
        periods=[(18, "evening"), (6, "day")],
    )
    assert clock.period_at(6) == "day"
    assert clock.period_at(17) == "day"
    assert clock.period_at(18) == "evening"
    assert clock.period_at(2) == "evening"  # pre-6AM wraps to last period


def test_empty_periods_disable_period_names():
    clock = GameClock(periods=[])
    assert clock.period_at(0) is None
    # describe falls back to just the time string
    assert clock.describe(0) == clock.format_time(0)


def test_describe_includes_period():
    clock = GameClock(start_hour=8, minutes_per_turn=15)
    assert clock.describe(3) == "8:45 AM (morning)"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_hour": 24},
        {"start_hour": -1},
        {"start_minute": 60},
        {"minutes_per_turn": 0},
        {"minutes_per_turn": -5},
        {"periods": [(25, "bad-hour")]},
        {"periods": [(5, "")]},
    ],
)
def test_clock_validates_config(kwargs):
    with pytest.raises(ValueError):
        GameClock(**kwargs)


# ----------------------------------------------------------------------
# Section B: Game integration (opt-in, backward compatible)
# ----------------------------------------------------------------------


def test_no_time_config_means_no_clock(tiny_game_factory):
    game = tiny_game_factory()
    assert game.clock is None
    assert game.current_time() is None
    # Turn counter still works exactly as before.
    game.do_command("go north")
    assert game.turn == 1
    # And the player-facing description is unchanged (no time line).
    assert "AM" not in game.describe() and "PM" not in game.describe()


def test_time_config_dict_builds_clock(tiny_game_factory):
    game = tiny_game_factory(time_config={"start_hour": 8, "minutes_per_turn": 15})
    assert isinstance(game.clock, GameClock)
    assert game.current_time() == "8:00 AM (morning)"


def test_time_config_accepts_gameclock_instance(tiny_game_factory):
    clock = GameClock(start_hour=20, minutes_per_turn=30)
    game = tiny_game_factory(time_config=clock)
    assert game.clock is clock
    assert game.current_time() == "8:00 PM (night)"


def test_time_config_rejects_garbage(tiny_game_factory):
    with pytest.raises(Exception, match="invalid time_config"):
        tiny_game_factory(time_config="8 AM")


def test_time_advances_with_turns(tiny_game_factory):
    game = tiny_game_factory(time_config={"start_hour": 8, "minutes_per_turn": 15})
    game.do_command("go north")
    game.do_command("go south")
    assert game.turn == 2
    assert game.current_time() == "8:30 AM (morning)"


def test_failed_command_does_not_advance_time(tiny_game_factory):
    game = tiny_game_factory(time_config={"start_hour": 8, "minutes_per_turn": 15})
    game.do_command("go west")  # no exit west; precondition fails
    assert game.turn == 0
    assert game.current_time() == "8:00 AM (morning)"


def test_describe_shows_time_when_clock_set(tiny_game_factory):
    game = tiny_game_factory(time_config={"start_hour": 8, "minutes_per_turn": 15})
    assert "(8:00 AM (morning))" in game.describe()


def test_describe_for_shows_time_when_clock_set(tiny_game_factory):
    game = tiny_game_factory(time_config={"start_hour": 8, "minutes_per_turn": 15})
    observation = game.describe_for(game.player)
    assert "Turn: 0 (8:00 AM (morning))" in observation


def test_describe_for_plain_turn_without_clock(tiny_game_factory):
    game = tiny_game_factory()
    observation = game.describe_for(game.player)
    assert "Turn: 0" in observation
    assert "AM" not in observation and "PM" not in observation


# ----------------------------------------------------------------------
# Section C: scheduled events
# ----------------------------------------------------------------------


def test_scheduled_event_fires_on_its_turn(tiny_game_factory):
    game = tiny_game_factory()
    fired = []
    game.schedule_event(2, lambda g: fired.append(g.turn))

    game.do_command("go north")  # turn 1
    assert fired == []
    game.do_command("go south")  # turn 2
    assert fired == [2]


def test_scheduled_event_fires_once(tiny_game_factory):
    game = tiny_game_factory()
    fired = []
    trigger = game.schedule_event(1, lambda g: fired.append(g.turn))

    game.do_command("go north")
    game.do_command("go south")
    game.do_command("go north")
    assert fired == [1]
    # The underlying trigger is non-repeatable and spent after firing.
    assert trigger.fired is True
    assert trigger.repeatable is False


def test_event_scheduled_in_past_fires_next_round(tiny_game_factory):
    game = tiny_game_factory()
    game.do_command("go north")
    game.do_command("go south")
    assert game.turn == 2

    fired = []
    game.schedule_event(1, lambda g: fired.append(g.turn))  # already passed
    game.do_command("go north")  # turn 3: catch-up fires it
    assert fired == [3]


def test_events_fire_in_turn_order_then_insertion_order(tiny_game_factory):
    game = tiny_game_factory()
    fired = []
    # Insert out of turn order, plus two events on the same turn.
    game.schedule_event(2, lambda g: fired.append("turn2-first"))
    game.schedule_event(1, lambda g: fired.append("turn1"))
    game.schedule_event(2, lambda g: fired.append("turn2-second"))

    game.do_command("go north")  # turn 1
    game.do_command("go south")  # turn 2
    assert fired == ["turn1", "turn2-first", "turn2-second"]


def test_callback_can_reschedule_itself(tiny_game_factory):
    """The documented recipe for recurring events."""
    game = tiny_game_factory()
    fired = []

    def every_other_turn(g):
        fired.append(g.turn)
        g.schedule_event(g.turn + 2, every_other_turn)

    game.schedule_event(1, every_other_turn)
    for _ in range(3):
        game.do_command("go north")
        game.do_command("go south")
    assert fired == [1, 3, 5]


def test_scheduled_event_can_mutate_world(tiny_game_factory):
    """The motivating use case: timed environmental change."""
    game = tiny_game_factory()

    def nightfall(g):
        g.locations["Field"].set_property("is_dark", True)

    game.schedule_event(1, nightfall)
    assert game.locations["Field"].get_property("is_dark") is False
    game.do_command("go north")
    assert game.locations["Field"].get_property("is_dark") is True


def test_schedule_event_is_trigger_sugar(tiny_game_factory):
    """schedule_event registers a non-repeatable trigger (issue #6 system)."""
    game = tiny_game_factory()
    trigger = game.schedule_event(3, lambda g: None)
    assert trigger in game.triggers
    assert trigger.name == "scheduled@turn3"
    assert trigger.repeatable is False


def test_schedule_event_accepts_custom_name(tiny_game_factory):
    game = tiny_game_factory()
    trigger = game.schedule_event(2, lambda g: None, name="nightfall")
    assert trigger.name == "nightfall"


def test_scheduled_event_is_recorded_in_event_log(tiny_game_factory):
    """Firing goes through the trigger react phase, so it lands in Game.events."""
    game = tiny_game_factory()
    game.schedule_event(1, lambda g: None, name="nightfall")

    game.do_command("go north")
    trigger_events = [e for e in game.events if e.actor == "trigger"]
    assert any(e.action == "nightfall" for e in trigger_events)


def test_schedule_event_validates_arguments(tiny_game_factory):
    game = tiny_game_factory()
    with pytest.raises(Exception, match="invalid schedule turn"):
        game.schedule_event(-1, lambda g: None)
    with pytest.raises(Exception, match="invalid schedule turn"):
        game.schedule_event("soon", lambda g: None)
    with pytest.raises(Exception, match="not callable"):
        game.schedule_event(1, "not a function")


# ----------------------------------------------------------------------
# Section D: serialization
# ----------------------------------------------------------------------


def test_clock_primitive_round_trip():
    clock = GameClock(
        start_hour=6,
        start_minute=30,
        minutes_per_turn=20,
        periods=[(6, "day"), (18, "evening")],
    )
    restored = GameClock.from_primitive(clock.to_primitive())
    assert restored.start_hour == 6
    assert restored.start_minute == 30
    assert restored.minutes_per_turn == 20
    assert restored.periods == [(6, "day"), (18, "evening")]
    assert restored.describe(0) == clock.describe(0)


def test_game_serializes_time_config(tiny_game_factory):
    game = tiny_game_factory(time_config={"start_hour": 9, "minutes_per_turn": 10})
    data = game.to_primitive()
    assert data["time_config"]["start_hour"] == 9
    assert data["time_config"]["minutes_per_turn"] == 10


def test_game_without_clock_serializes_none(tiny_game_factory):
    game = tiny_game_factory()
    assert game.to_primitive()["time_config"] is None


def test_game_round_trip_restores_clock(tiny_game_factory):
    game = tiny_game_factory(time_config={"start_hour": 9, "minutes_per_turn": 10})
    game.do_command("go north")
    restored = games.Game.from_json(game.to_json())
    assert restored.turn == 1
    assert isinstance(restored.clock, GameClock)
    assert restored.current_time() == "9:10 AM (morning)"


def test_game_round_trip_without_clock(tiny_game_factory):
    game = tiny_game_factory()
    restored = games.Game.from_json(game.to_json())
    assert restored.clock is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
