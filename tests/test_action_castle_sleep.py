"""Scenario tests for the Action-Castle sleep mechanism: falling asleep
(Sleep), being blocked from other actions while asleep (SleepGate), energy
recovery while asleep, and waking automatically after 8 in-game hours.
Same pattern as tests/test_action_castle_energy.py -- play the real
build_game() through the parser rather than mocking pieces of it.

The game clock starts at 8:00 AM with 15 minutes/turn (see build_game), so
turn 48 is 8:00 PM -- the earliest the Sleep action allows sleeping. A single
"sleep" command now fast-forwards through the whole night in one go (Sleep's
apply_effects loops game.end_turn() until the recovery_per_turn trigger clears
is_sleeping 8 hours later), so these tests check before/after the full
command rather than mid-sleep state.
"""

from text_adventure_games.adventures.action_castle import build_game
from text_adventure_games.scenario import play, prop

LATE_TURN = 48  # 8:00 PM -- Sleep's check_preconditions requires >= 720 min
EIGHT_HOURS_IN_TURNS = 32  # 8h * 60 / 15 min-per-turn


def test_sleep_fails_when_not_tired():
    game = build_game()
    game.turn = LATE_TURN
    game.player.set_property("energy", 50)
    result = play(game, ["sleep"])
    assert result[0] is False
    assert prop(game, "The player", "is_sleeping") is False


def test_sleep_fails_when_too_early():
    game = build_game()
    game.turn = 0
    game.player.set_property("energy", 5)
    result = play(game, ["sleep"])
    assert result[0] is False
    assert prop(game, "The player", "is_sleeping") is False


def test_sleep_records_when_it_started_and_wakes_by_itself():
    game = build_game()
    game.turn = LATE_TURN
    game.player.set_property("energy", 5)
    result = play(game, ["sleep"])
    assert result[0] is True
    assert prop(game, "The player", "slept_at") == LATE_TURN
    # The command fast-forwards through the whole night, so it's already
    # woken up (is_sleeping cleared) by the time do_command returns.
    assert prop(game, "The player", "is_sleeping") is False
    assert game.turn >= LATE_TURN + EIGHT_HOURS_IN_TURNS


def test_sleep_gate_blocks_other_actions_while_asleep():
    # Sleep itself is atomic now, so there's no external moment to observe
    # "mid-sleep" through play(). Set is_sleeping directly to unit-test the
    # SleepGate mixin that every custom action is wrapped in.
    game = build_game()
    game.player.set_property("is_sleeping", True)
    result = play(game, ["show energy"])
    assert result[0] is False


def test_energy_recovers_over_a_night_of_sleep():
    game = build_game()
    game.turn = LATE_TURN
    game.player.set_property("energy", 5)
    before = prop(game, "The player", "energy")
    play(game, ["sleep"])
    after = prop(game, "The player", "energy")
    assert after > before


def test_energy_does_not_exceed_100_while_recovering():
    game = build_game()
    game.turn = LATE_TURN
    game.player.set_property("energy", 5)
    play(game, ["sleep"])
    assert prop(game, "The player", "energy") <= 100


def test_can_act_again_after_waking():
    game = build_game()
    game.turn = LATE_TURN
    game.player.set_property("energy", 5)
    play(game, ["sleep"])
    result = play(game, ["show energy"])
    assert result[0] is True


def test_tired_resets_to_baseline_after_waking():
    # Regression test: tired used to compound down forever since waking never
    # reset it, so a second sleep-wake cycle decayed energy faster than the
    # first ever could. Two identical cycles from the same starting energy
    # should now leave "tired" at the same value both times.
    game = build_game()
    game.turn = LATE_TURN
    game.player.set_property("energy", 5)
    play(game, ["sleep"])
    tired_after_first_cycle = prop(game, "The player", "tired")

    play(game, ["wait"] * 20)
    game.player.set_property("energy", 5)
    play(game, ["sleep"])
    tired_after_second_cycle = prop(game, "The player", "tired")

    assert tired_after_second_cycle == tired_after_first_cycle
