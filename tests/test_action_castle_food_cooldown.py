"""Scenario tests for the eat/drink cooldown gate and its 16-hour reset
trigger: eating (or drinking) again is blocked until ate_food/drank_water
clears, which happens automatically 16 in-game hours later -- same
"record a timestamp, check the gap via game.clock" shape as Sleep's 8-hour
wake-up (see test_action_castle_sleep.py).
"""

from text_adventure_games.adventures.action_castle import Drink, build_game
from text_adventure_games.scenario import has_item, play, prop

TO_GARDEN = ["out", "east"]  # Cottage -> Garden Path -> Garden
SIXTEEN_HOURS_IN_TURNS = 64  # 16h * 60 / 15 min-per-turn


def test_drink_registered_and_restores_energy():
    game = build_game()
    assert game.parser.actions["drink"] is Drink
    play(game, TO_GARDEN + ["get water"])
    game.player.set_property("energy", 50)
    game.turn = 0
    play(game, ["drink water"])
    assert prop(game, "The player", "energy") == 60


def test_drunk_item_is_removed_from_inventory():
    game = build_game()
    play(game, TO_GARDEN + ["get water", "drink water"])
    assert not has_item(game, "The player", "water")


def test_eating_again_right_away_is_blocked():
    game = build_game()
    play(game, TO_GARDEN + ["get bread", "get tuna"])
    game.player.set_property("energy", 50)
    game.turn = 0
    play(game, ["eat bread"])
    energy_after_first_eat = prop(game, "The player", "energy")
    results = play(game, ["eat tuna"])
    assert results[-1] is False
    assert prop(game, "The player", "energy") == energy_after_first_eat


def test_drinking_again_right_away_is_blocked():
    game = build_game()
    play(game, TO_GARDEN + ["get water", "get soda"])
    game.player.set_property("energy", 50)
    game.turn = 0
    play(game, ["drink water"])
    energy_after_first_drink = prop(game, "The player", "energy")
    results = play(game, ["drink soda"])
    assert results[-1] is False
    assert prop(game, "The player", "energy") == energy_after_first_drink


def test_ate_food_flag_clears_after_16_hours_and_eating_works_again():
    game = build_game()
    play(game, TO_GARDEN + ["get bread", "get tuna"])
    game.player.set_property("energy", 50)
    game.turn = 0
    play(game, ["eat bread"])
    assert prop(game, "The player", "ate_food") is True

    for _ in range(SIXTEEN_HOURS_IN_TURNS):
        game.end_turn()
    assert prop(game, "The player", "ate_food") is False

    result = game.do_command("eat tuna")
    assert result is True
    assert prop(game, "The player", "ate_food") is True


def test_drank_water_flag_clears_after_16_hours_and_drinking_works_again():
    game = build_game()
    play(game, TO_GARDEN + ["get water", "get soda"])
    game.player.set_property("energy", 50)
    game.turn = 0
    play(game, ["drink water"])
    assert prop(game, "The player", "drank_water") is True

    for _ in range(SIXTEEN_HOURS_IN_TURNS):
        game.end_turn()
    assert prop(game, "The player", "drank_water") is False

    result = game.do_command("drink soda")
    assert result is True
    assert prop(game, "The player", "drank_water") is True
