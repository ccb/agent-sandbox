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

from text_adventure_games.blocks import Darkness
from text_adventure_games import games, things
from text_adventure_games.scenario import blocked, play

# ----------------------------------------------------------------------
# Light the lamp to dispel darkness in a tiny purpose-built world.
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
