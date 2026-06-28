"""Comma-separated command sequences: each segment runs in turn, and empty
segments (a trailing comma, a doubled comma, stray whitespace) are skipped
rather than firing "I'm not sure what you want to do" on a blank command."""

from text_adventure_games import games, things
from text_adventure_games.reporting import CaptureRenderer, Channel


def _world():
    field = things.Location("Field", "An open field. Woods lie west.")
    woods = things.Location("Woods", "Shady woods. The field is east.")
    field.add_connection("west", woods)  # also wires woods --east--> field
    player = things.Character("you", "a walker", "I walk.")
    game = games.Game(field, player, characters=[])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, player, cap


def _confused(cap):
    return any("not sure" in t for t in cap.texts(Channel.BLOCKED))


def test_sequence_runs_each_command():
    game, player, cap = _world()
    game.parser.parse_command("west, east")
    assert player.location.name == "Field"  # west then back east
    assert not _confused(cap)


def test_trailing_comma_is_ignored():
    game, player, cap = _world()
    game.parser.parse_command("west,")
    assert player.location.name == "Woods"
    assert not _confused(cap)


def test_doubled_and_whitespace_commas_are_ignored():
    game, player, cap = _world()
    game.parser.parse_command("west, , east,  ,")
    assert player.location.name == "Field"
    assert not _confused(cap)
