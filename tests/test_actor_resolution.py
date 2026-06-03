from text_adventure_games import games, things
from text_adventure_games.actions.base import Action


def _two_char_game():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    alice = things.Character("alice", "a guard", "I guard.")
    bob = things.Character("bob", "a thief", "I sneak.")
    game = games.Game(room, player, characters=[alice, bob])
    room.add_character(alice)
    room.add_character(bob)
    return game


def test_acting_character_returns_explicit_actor():
    game = _two_char_game()
    alice = game.characters["alice"]
    action = Action(game, actor=alice)
    assert action.acting_character("anything at all") is alice


def test_acting_character_falls_back_to_command_scan():
    game = _two_char_game()
    action = Action(game)  # actor=None
    assert action.acting_character("get key") is game.player
    assert action.acting_character("alice get key") is game.characters["alice"]


def test_get_character_exclude_skips_named_candidate():
    game = _two_char_game()
    alice = game.characters["alice"]
    bob = game.characters["bob"]
    assert game.parser.get_character("alice and bob") is alice
    assert game.parser.get_character("alice and bob", exclude=alice) is bob
