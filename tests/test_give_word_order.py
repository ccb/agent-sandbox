"""Parser routing for give word-order variants (issue #171).

A custom give-action ("give gem to wizard") must be reached regardless of how
the give is phrased -- "give wizard the gem", "hand wizard the gem" -- not just
by its canonical literal phrase. Otherwise the built-in Give swallows the
command, moving the item but skipping the game's special effect.

Uses a minimal one-room game so the test is independent of any shipped adventure
(per the issue's "minimal test game" acceptance criterion).
"""

from text_adventure_games import actions, games, things


class GiveGemToWizard(actions.Action):
    ACTION_NAME = "give gem to wizard"
    ACTION_DESCRIPTION = "Give the gem to the wizard"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = game.player
        self.wizard = self.parser.get_character("wizard")

    def check_preconditions(self) -> bool:
        return self.wizard is not None and "gem" in self.player.inventory

    def apply_effects(self):
        self.wizard.set_property("got_gem", True)


def _give_game():
    room = things.Location("Room", "A bare stone room.")
    player = things.Character("player", "an adventurer", "I explore.")
    wizard = things.Character("wizard", "an old wizard", "I ponder.")
    gem = things.Item("gem", "a gem", "A glittering gem.")
    gem.set_property("gettable", True)
    player.add_to_inventory(gem)
    room.add_character(wizard)
    return games.Game(
        room, player, characters=[wizard], custom_actions=[GiveGemToWizard]
    )


def _routed(command):
    """Name of the Action class a command would route to (no effects run)."""
    return type(_give_game().parser.peek_action(command)).__name__


def test_canonical_give_routes_to_custom_action():
    # "give <item> to <recipient>" already worked (literal-phrase match).
    assert _routed("give gem to wizard") == "GiveGemToWizard"


def test_reversed_give_routes_to_custom_action():
    # "give <recipient> the <item>" used to fall through to the built-in Give.
    assert _routed("give wizard the gem") == "GiveGemToWizard"


def test_hand_reversed_routes_to_custom_action():
    # "hand <recipient> the <item>" used to match nothing at all (None).
    assert _routed("hand wizard the gem") == "GiveGemToWizard"


def test_hand_canonical_routes_to_custom_action():
    assert _routed("hand gem to wizard") == "GiveGemToWizard"


def test_give_with_no_matching_custom_action_uses_builtin_give():
    # No custom give-action matches (wrong item word) -> built-in Give, as before.
    assert _routed("give wizard the rock") == "Give"


def test_plain_give_still_routes_to_builtin_give():
    # A bare give with neither token of a custom action present.
    assert _routed("give wizard something") == "Give"
