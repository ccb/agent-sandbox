"""Generic, game-agnostic helpers for scenario-based integration tests (#26).

A *scenario* plays a specific game instance through a sequence of commands and
asserts on the resulting **world state**. These helpers are the shared
vocabulary for writing such assertions: run a command sequence (`play`), then
read state by name (`blocked`, `prop`, `at`, `has_item`) instead of by holding
object references.

They are deliberately game-agnostic so any game's tests -- and a future
agent-planning evaluation -- can reuse them. Game-specific *goal predicates*
(e.g. "the troll is fed") are built by composing these and live with the game or
the test, not here.
"""


def play(game, commands):
    """Run a list of player commands, in order, via ``game.do_command``.

    Returns the list of per-command success booleans, so a caller may assert a
    command landed (or was rejected) when that matters.
    """
    return [game.do_command(command) for command in commands]


def _character(game, name):
    """Resolve a character by name. ``Game.__init__`` registers the player in
    ``game.characters`` alongside the NPCs, so the player resolves here too."""
    return game.characters[name]


def _thing(game, name):
    """Resolve any thing by name, in precedence order: a location, then a
    character (the player is among ``game.characters``), then an item sitting in
    a location or in some character's inventory.

    Names are assumed unique across these categories; on a collision the earlier
    category wins (e.g. a character named "guard" shadows an item named "guard").
    """
    if name in game.locations:
        return game.locations[name]
    if name in game.characters:
        return game.characters[name]
    for location in game.locations.values():
        if name in location.items:
            return location.items[name]
    for character in game.characters.values():
        if name in character.inventory:
            return character.inventory[name]
    raise KeyError(f"No location, character, or item named {name!r}")


def blocked(game, location, direction):
    """Whether ``location`` (by name) is blocked in ``direction``."""
    return game.locations[location].is_blocked(direction)


def prop(game, thing, key):
    """Read a property ``key`` off any thing (location/character/item) by name."""
    return _thing(game, thing).get_property(key)


def at(game, character, location):
    """Whether ``character`` (by name) is currently in ``location`` (by name)."""
    return _character(game, character).location is game.locations[location]


def has_item(game, character, item):
    """Whether ``character`` (by name) has ``item`` (by name) in inventory."""
    return item in _character(game, character).inventory
