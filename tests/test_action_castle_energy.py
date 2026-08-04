"""Scenario tests for the Action-Castle-scoped energy/food system.

Unlike tests/test_energy.py (which targeted an engine-wide approach that was
later reverted), these test the real thing: the custom Eat override,
Check_energy ("show energy"), and Set_energy ("energy mode") actions defined
in text_adventure_games/adventures/action_castle.py, played against the real
build_game() -- same pattern as test_scenarios.py.
"""

from text_adventure_games.adventures.action_castle import build_game
from text_adventure_games.scenario import has_item, play, prop

TO_GARDEN = ["out", "east"]  # Cottage -> Garden Path -> Garden


def test_eat_bread_restores_energy():
    game = build_game()
    play(game, TO_GARDEN + ["get bread"])
    game.player.set_property("energy", 50)
    game.turn = 0  # land the eat on a turn the energy-decay trigger skips
    play(game, ["eat bread"])
    assert prop(game, "The player", "energy") == 70


def test_eat_tuna_restores_energy():
    game = build_game()
    play(game, TO_GARDEN + ["get tuna"])
    game.player.set_property("energy", 50)
    game.turn = 0
    play(game, ["eat tuna"])
    assert prop(game, "The player", "energy") == 90


def test_energy_is_capped_at_100():
    game = build_game()
    play(game, TO_GARDEN + ["get bread"])
    game.player.set_property("energy", 90)
    game.turn = 0
    play(game, ["eat bread"])  # 90 + 20 would be 110
    assert prop(game, "The player", "energy") == 100


def test_eaten_item_is_removed_from_inventory():
    game = build_game()
    play(game, TO_GARDEN + ["get bread", "eat bread"])
    assert not has_item(game, "The player", "bread")


def test_show_energy_command_succeeds():
    game = build_game()
    results = play(game, ["show energy"])
    assert results[0] is True


def test_set_energy_resets_to_70():
    game = build_game()
    game.player.set_property("energy", 0)
    play(game, ["energy mode"])
    assert prop(game, "The player", "energy") == 70


def test_eating_non_edible_item_fails_and_does_not_change_energy():
    game = build_game()
    game.player.set_property("energy", 50)
    results = play(game, ["get pole", "eat pole"])
    assert results[-1] is False
    assert prop(game, "The player", "energy") == 50
