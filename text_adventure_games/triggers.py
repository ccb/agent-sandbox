"""Triggers: condition/action rules fired in the game's post-round react phase.

A Trigger pairs a condition (game -> bool) with an action (game -> None). The
game evaluates triggers after every round (see Game._run_triggers); a trigger
whose condition is true runs its action. This module also provides small factory
functions for the common conditions and a from_command action helper. See
docs/superpowers/specs/2026-06-02-trigger-system-design.md (issue #6).
"""

MAX_CASCADE_PASSES = 2  # initial pass + one cascade level, then stop


class Trigger:
    def __init__(self, name, condition, action, repeatable=False):
        self.name = name
        self.condition = condition      # (game) -> bool
        self.action = action            # (game) -> None
        self.repeatable = repeatable
        self.fired = False


# --- condition factories: each returns a callable (game) -> bool ---


def at_turn(n):
    """True once the game has reached turn n (turn >= n)."""
    return lambda game: game.turn >= n


def every(n):
    """True on every nth turn (turn > 0 and turn % n == 0)."""
    return lambda game: n > 0 and game.turn > 0 and game.turn % n == 0


def in_location(character, location):
    """True when the character is in the given location."""
    return lambda game: character.location is location


def has_property(thing, name, value=True):
    """True when thing's property matches value, compared by truthiness.

    Truthiness handling means an unset property (get_property returns None)
    reads as False instead of mismatching.
    """
    return lambda game: bool(thing.get_property(name)) == bool(value)


def all_of(*conditions):
    """True when every given condition is true."""
    return lambda game: all(c(game) for c in conditions)


def any_of(*conditions):
    """True when any given condition is true."""
    return lambda game: any(c(game) for c in conditions)


# --- action factory: returns a callable (game) -> None ---


def from_command(command):
    """An action that runs a game command through the parser.

    Because it goes through parse_command, the command passes the normal
    precondition gate and is recorded in the event log like any other action.
    """
    return lambda game: game.parser.parse_command(command)
