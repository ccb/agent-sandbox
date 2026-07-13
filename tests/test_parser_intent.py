"""Parser intent routing (#536): a command-initial registered verb wins over
the keyword substrings, and (Task 2) the keyword branches match whole words.

Minimal one-room games (the tests/test_give_word_order.py pattern) so routing
is independent of any shipped adventure. determine_intent is called directly:
these are routing tests, no effects run.
"""

from text_adventure_games import actions, games, things
from text_adventure_games.enums import ActionName


class Perform(actions.Action):
    """A free-text verb, shaped like the Penn backend's perform action."""

    ACTION_NAME = "perform"
    ACTION_DESCRIPTION = "Do a scheduled activity described in free text"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        pass


class Taste(actions.Action):
    """Registers 'taste' so the gated taste branch is live in tests."""

    ACTION_NAME = "taste"
    ACTION_DESCRIPTION = "Taste something"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        pass


def _intent(command, custom_actions=()):
    room = things.Location("Room", "A bare stone room.")
    player = things.Character("player", "an adventurer", "I explore.")
    game = games.Game(room, player, characters=[], custom_actions=list(custom_actions))
    return game.parser.determine_intent(command, actor=game.player)


def test_perform_free_text_routes_to_perform():
    # The Diego freeze (#536): "l-ate- into" hijacked this command to EAT,
    # which precondition-blocked the agent every turn for the rest of its day.
    intent = _intent("perform refining the model late into the day", (Perform,))
    assert intent == "perform"


def test_perform_wins_over_a_genuine_verb_word_in_the_argument():
    # Word-boundary hardening alone would NOT fix this one: "eating" is a
    # real verb word inside the free text. Only initial-verb precedence does.
    assert _intent("perform eating lunch with friends", (Perform,)) == "perform"


def test_unregistered_first_word_falls_through():
    # Without a registered perform, the old chain applies unchanged (the
    # command is then genuinely ambiguous and lands on EAT via "eating").
    assert _intent("perform eating lunch with friends") == ActionName.EAT


def test_prefix_special_cases_still_outrank_the_initial_verb():
    # Everything above the insertion point keeps its win.
    assert _intent("get off the horse") == ActionName.DISMOUNT
    assert _intent("take off the hat") == ActionName.TAKE_OFF
    assert _intent("hint light") == "hint"
    assert _intent("taste crate of dates", (Taste,)) == "taste"


def test_plain_verbs_route_as_before():
    # Same actions as today -- now via the initial-verb check, one branch
    # earlier (StrEnum members compare equal to their name strings).
    assert _intent("get the axe") == ActionName.GET
    assert _intent("eat fish") == ActionName.EAT
    assert _intent("drop sword") == ActionName.DROP
    assert _intent("light lamp") == ActionName.LIGHT


def test_give_is_carved_out_for_word_order_resolution():
    # give/hand must fall through to the give branch so _match_give_action
    # (#171) keeps resolving custom give-actions; with no custom give
    # registered the built-in GIVE wins, exactly as before.
    assert _intent("give wizard the gem") == ActionName.GIVE
