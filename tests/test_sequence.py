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


def test_sequence_fires_triggers_between_commands():
    # A trigger keyed to a TRANSIENT intermediate state (being in the woods) must
    # still fire when the woods is only passed through inside a comma-sequence --
    # each sub-command takes its own turn, so the react phase runs per step, not
    # once at the end.
    game, player, cap = _world()
    game.add_trigger(
        "saw_woods",
        lambda g: g.player.location.name == "Woods"
        and not g.player.get_property("saw_woods"),
        lambda g: g.player.set_property("saw_woods", True),
        repeatable=True,
    )
    # Into the woods and back to the field, as one comma-sequence. The player is
    # never *in* the woods at the end -- only midway through.
    game.do_command("west, east")
    assert player.location.name == "Field"
    assert player.get_property("saw_woods")


def test_sequence_takes_one_turn_per_command():
    game, player, cap = _world()
    start = game.turn
    game.do_command("west, east")  # two real moves
    assert game.turn == start + 2


def test_sequence_stops_at_game_over():
    game, player, cap = _world()
    game.add_trigger(
        "end_in_woods",
        lambda g: g.player.location.name == "Woods",
        lambda g: setattr(g, "game_over", True),
        repeatable=True,
    )
    # "east" after "west" should never run -- the game ends in the woods.
    game.do_command("west, east")
    assert game.is_game_over()
    assert player.location.name == "Woods"
