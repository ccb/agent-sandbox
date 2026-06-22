"""Scenario-based integration tests (issue #26).

Unlike the unit suites, these play a *specific instance* of a game through a
**sequence of actions** and assert on the resulting **world state** (properties,
block state, inventory) -- never on printed message text.

They also lay the foundation for testing AI-agent planning: a scenario splits
into the *command sequence* (how you reach the goal) and a *goal predicate*
(whether you got there). Here we author both; a future agent eval would let an
agent generate the commands and reuse the same `game -> bool` predicates below to
score success.

The generic, game-agnostic helpers (`play`, `blocked`, `prop`, `at`, `has_item`)
live in `text_adventure_games.scenario` so an agent eval can import them too.
"""

from text_adventure_games.adventures.action_castle import build_game
from text_adventure_games.blocks import Darkness
from text_adventure_games import games, things
from text_adventure_games.scenario import at, blocked, has_item, play, prop

# ----------------------------------------------------------------------
# Goal predicates -- the reusable seam between scripted tests and a future
# agent-planning eval. Each is a plain `game -> bool` function.
# ----------------------------------------------------------------------


def troll_fed(game):
    return not prop(game, "troll", "is_hungry")


def drawbridge_open(game):
    return not blocked(game, "Drawbridge", "east")


def rose_picked(game):
    return has_item(game, "The player", "rose") and not prop(
        game, "rosebush", "has_rose"
    )


# ----------------------------------------------------------------------
# S1 -- Feed the troll (the motivating example): blocked -> unblocked,
# hungry -> fed, on the real Action Castle.
# ----------------------------------------------------------------------

FEED_TROLL_COMMANDS = [
    "get pole",
    "go out",  # garden path
    "go south",  # fishing pond
    "catch fish with pole",
    "go north",  # garden path
    "go north",  # winding path
    "go east",  # drawbridge (troll is here, hungry)
]


def test_feed_troll_unblocks_drawbridge():
    game = build_game()  # no LLM client -> deterministic scripted NPCs

    # Blocked BEFORE: the hungry troll bars the way east off the drawbridge.
    assert not troll_fed(game)
    assert blocked(game, "Drawbridge", "east")

    play(game, FEED_TROLL_COMMANDS)
    assert at(game, "The player", "Drawbridge")
    assert has_item(game, "The player", "fish")

    play(game, ["give fish to troll"])

    # Unblocked AFTER: the fed troll stands down and the drawbridge opens.
    assert troll_fed(game)
    assert drawbridge_open(game)


# ----------------------------------------------------------------------
# S2 -- Pick the rose: a property/inventory transition (no block), two
# commands from the start, on the real Action Castle.
# ----------------------------------------------------------------------


def test_pick_rose_transfers_rose_to_inventory():
    game = build_game()

    # Before: the rosebush has its rose, the player does not.
    assert prop(game, "rosebush", "has_rose")
    assert not has_item(game, "The player", "rose")

    play(game, ["go out", "pick rose"])  # garden path has the rosebush

    # After: the rose has moved from bush to inventory.
    assert rose_picked(game)


# ----------------------------------------------------------------------
# S3 -- Light the lamp to dispel darkness: a different block mechanic, in a
# tiny purpose-built world (the shape an agent-planning eval would use).
# ----------------------------------------------------------------------


def _dark_cave_game():
    """Cave Entrance --down--> Dark Cave, the descent blocked by Darkness.
    The player starts at the entrance carrying an (unlit) lamp."""
    entrance = things.Location("Cave Entrance", "The mouth of a cave.")
    cave = things.Location("Dark Cave", "A pitch-black cavern.")
    entrance.add_connection("down", cave)
    player = things.Character("The player", "a spelunker", "I explore caves.")
    lamp = things.Item("lamp", "a lamp", "A LAMP.")
    lamp.set_property("flammable", True)
    lamp.set_property("is_lit", False)
    player.add_to_inventory(lamp)
    game = games.Game(entrance, player, characters=[])
    entrance.add_block("down", Darkness(entrance))
    return game


def test_light_lamp_dispels_darkness():
    game = _dark_cave_game()

    # Before: it's too dark to descend.
    assert blocked(game, "Cave Entrance", "down")

    play(game, ["light lamp"])

    # After: the lit lamp clears the darkness block.
    assert not blocked(game, "Cave Entrance", "down")
