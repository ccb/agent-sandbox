"""Tests for the HELP command (lists the actions a player can take).

Help reads the parser's live action registry, so every registered verb -- the
engine's built-ins and any game-defined action -- shows up automatically, each
with its description and aliases.
"""

from text_adventure_games import games, things
from text_adventure_games.actions import base as base_actions
from text_adventure_games.reporting import CaptureRenderer, Channel


def _world():
    """A one-room game with a player, wired to a CaptureRenderer."""
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I look around.")
    game = games.Game(room, player)
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, player, cap


def _help_text(cap):
    """The most recent narration emitted by a help command."""
    return cap.texts(Channel.NARRATION)[-1]


def test_help_lists_registered_actions():
    game, player, cap = _world()
    game.parser.parse_command("help")
    text = _help_text(cap)
    # A sampling of built-in verbs every game registers.
    for verb in ("go", "get", "drop", "examine", "inventory", "help"):
        assert verb in text


def test_help_shows_descriptions_and_aliases():
    game, player, cap = _world()
    game.parser.parse_command("help")
    text = _help_text(cap)
    assert "List the commands you can use" in text  # help's own description
    assert "(look, l)" in text  # describe's aliases are surfaced


def test_help_aliases_route_to_the_same_listing():
    game, player, cap = _world()
    game.parser.parse_command("help")
    canonical = _help_text(cap)
    for alias in ("h", "commands", "?"):
        game.parser.parse_command(alias)
        assert _help_text(cap) == canonical


def test_help_hides_the_internal_sequence_action():
    game, player, cap = _world()
    game.parser.parse_command("help")
    text = _help_text(cap)
    # The comma-sequence wrapper is engine plumbing, not a verb a player types.
    assert "sequence" not in text


def test_help_hides_npc_only_actions():
    game, player, cap = _world()

    class Growl(base_actions.Action):
        ACTION_NAME = "growl"
        ACTION_DESCRIPTION = "Growl menacingly"
        PLAYER_VISIBLE = False  # an NPC's verb

        def check_preconditions(self):
            return True

        def apply_effects(self):
            self.parser.npc_ok("Grrr.")

    game.parser.add_action(Growl)
    game.parser.parse_command("help")
    assert "growl" not in _help_text(cap)


def test_help_lists_game_defined_actions():
    game, player, cap = _world()

    class Dance(base_actions.Action):
        ACTION_NAME = "dance"
        ACTION_DESCRIPTION = "Dance a jig"

        def check_preconditions(self):
            return True

        def apply_effects(self):
            self.parser.ok("You dance.")

    game.parser.add_action(Dance)
    game.parser.parse_command("help")
    text = _help_text(cap)
    assert "dance" in text and "Dance a jig" in text
