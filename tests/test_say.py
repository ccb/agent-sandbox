from text_adventure_games import games, things
from text_adventure_games.npc import _route


def _say_game():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    guard = things.Character("guard", "a guard", "I guard.")
    thief = things.Character("thief", "a thief", "I sneak.")
    game = games.Game(room, player, characters=[guard, thief])
    room.add_character(guard)
    room.add_character(thief)
    return game, guard, thief


def _history_text(game):
    return " ".join(e["content"] for e in game.parser.command_history)


def test_say_broadcast_lands_in_history():
    game, guard, thief = _say_game()
    ok = game.parser.parse_command("say hello there", actor=guard)
    assert ok is True
    assert "guard says: hello there" in _history_text(game)


def test_say_directed_to_colocated_character():
    game, guard, thief = _say_game()
    ok = game.parser.parse_command("say to thief hello", actor=guard)
    assert ok is True
    assert "guard says to thief: hello" in _history_text(game)


def test_say_empty_message_fails():
    game, guard, thief = _say_game()
    ok = game.parser.parse_command("say", actor=guard)
    assert ok is False


def test_say_to_absent_character_fails():
    room = things.Location("Room", "A plain room.")
    cell = things.Location("Cell", "A dark cell.")
    room.add_connection("south", cell)
    player = things.Character("player", "the player", "I explore.")
    guard = things.Character("guard", "a guard", "I guard.")
    thief = things.Character("thief", "a thief", "I sneak.")
    game = games.Game(room, player, characters=[guard, thief])
    room.add_character(guard)
    cell.add_character(thief)
    ok = game.parser.parse_command("say to thief secret", actor=guard)
    assert ok is False


def test_say_speak_alias_routes():
    game, guard, thief = _say_game()
    ok = game.parser.parse_command("speak greetings", actor=guard)
    assert ok is True
    assert "guard says: greetings" in _history_text(game)


def test_say_message_with_command_keyword_is_not_hijacked():
    game, guard, thief = _say_game()
    ok = game.parser.parse_command("say drop it now", actor=guard)
    assert ok is True
    assert "guard says: drop it now" in _history_text(game)


def test_route_attributes_say_to_actor_not_named_target():
    game, guard, thief = _say_game()
    _route(guard, game, "say to thief hello")
    assert "guard says to thief: hello" in _history_text(game)


def test_say_broadcast_preserves_casing():
    """Bug fix: the spoken message must keep the player original capitalization."""
    game, guard, thief = _say_game()
    ok = game.parser.parse_command("say Hello There", actor=guard)
    assert ok is True
    assert "guard says: Hello There" in _history_text(game)


def test_say_to_unknown_name_is_broadcast():
    """Bug fix: 'to <unknown>' falls through to a broadcast, message preserved."""
    game, guard, thief = _say_game()
    # No character named "arms" exists, so this is a broadcast.
    ok = game.parser.parse_command("say to arms everyone", actor=guard)
    assert ok is True
    assert "guard says: to arms everyone" in _history_text(game)


def test_say_word_boundary_recipient_match():
    """Bug fix: 'thief' must NOT match a word that merely starts with 'thief'."""
    game, guard, thief = _say_game()
    # 'thiefery' is not a known character name, so this is a broadcast.
    ok = game.parser.parse_command("say to thiefery is doomed", actor=guard)
    assert ok is True
    # Must be a broadcast (not directed at thief) with the full message intact.
    assert "guard says: to thiefery is doomed" in _history_text(game)
