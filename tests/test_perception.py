"""Tests for vision-radius perception (issue #80).

Two halves:

  A. ``Game.perceivable_locations`` -- the spatial visibility seam (the sight
     counterpart to ``audience_for``). BFS over room connections out to a
     character's ``vision_r``, ignoring blocks, and overridable per world.
  B. The simultaneous turn mode (``turns.gather_intents``) now runs the same
     perceive -> retrieve -> augment Observe step as the sequential ReAct loop,
     so agents in either mode accumulate and use memory.

Deterministic and offline (ScriptedAgent / a fixed mock); no network.

    pytest tests/test_perception.py -v
"""

import pytest

from text_adventure_games import games, things
from text_adventure_games.blocks import Block
from text_adventure_games.memory import AgentMemory
from text_adventure_games.npc import ScriptedAgent
from text_adventure_games.webapp.web_parser import WebParser

# ----------------------------------------------------------------------
# A. Game.perceivable_locations
# ----------------------------------------------------------------------


def _chain(*names):
    """A west-to-east chain of rooms; returns {name: Location} and the game.

    Room[0] holds the player and a 'seer' character whose vision we vary.
    """
    locs = [things.Location(n, f"Room {n}.") for n in names]
    for left, right in zip(locs, locs[1:]):
        left.add_connection("east", right)  # auto-wires the reverse 'west'
    player = things.Character("player", "the hero", "I act.")
    seer = things.Character("seer", "a watcher", "I watch.")
    game = games.Game(locs[0], player, characters=[seer])
    locs[0].add_character(seer)
    return {l.name: l for l in locs}, game, seer


def _names(locations):
    return {l.name for l in locations}


def test_radius_zero_is_current_room_only():
    rooms, game, seer = _chain("A", "B", "C")
    seer.vision_r = 0
    assert _names(game.perceivable_locations(seer)) == {"A"}


def test_radius_one_includes_directly_connected():
    rooms, game, seer = _chain("A", "B", "C")
    seer.vision_r = 1
    assert _names(game.perceivable_locations(seer)) == {"A", "B"}


def test_radius_two_includes_two_hops_but_not_three():
    rooms, game, seer = _chain("A", "B", "C", "D")
    seer.vision_r = 2
    seen = _names(game.perceivable_locations(seer))
    assert seen == {"A", "B", "C"}
    assert "D" not in seen  # three hops away


def test_radius_exceeding_map_returns_all_reachable_without_duplicates():
    rooms, game, seer = _chain("A", "B", "C")
    seer.vision_r = 99
    result = game.perceivable_locations(seer)
    assert _names(result) == {"A", "B", "C"}
    assert len(result) == 3  # each room visited once


def test_sight_crosses_blocks():
    # A block stops walking through a door, not seeing through it.
    rooms, game, seer = _chain("A", "B")
    rooms["A"].add_block("east", Block("a locked gate", "The gate is locked."))
    seer.vision_r = 1
    assert _names(game.perceivable_locations(seer)) == {"A", "B"}


def test_no_location_returns_empty():
    rooms, game, seer = _chain("A", "B")
    rooms["A"].remove_character(seer)  # seer.location becomes None
    assert game.perceivable_locations(seer) == []


def test_override_is_honored_by_perceive():
    # A world that defines its own notion of "nearby" (here: every room) is
    # honored by AgentMemory.perceive without touching the memory layer.
    class OmniscientGame(games.Game):
        def perceivable_locations(self, character):
            return list(self.locations.values())

    a = things.Location("A", "Room A.")
    b = things.Location("B", "Room B.")
    a.add_connection("east", b)
    b.add_item(things.Item("relic", "an ancient relic"))
    player = things.Character("player", "the hero", "I act.")
    seer = things.Character("seer", "a watcher", "I watch.")
    seer.vision_r = 1  # presence is gated on vision_r > 0, not on the radius math
    game = OmniscientGame(a, player, characters=[seer])
    a.add_character(seer)

    mem = AgentMemory(owner="seer")
    mem.perceive(game, seer)
    # The relic in room B is seen because the override puts every room in view.
    assert any(r.text == "I see relic nearby." for r in mem.records)


# ----------------------------------------------------------------------
# B. Simultaneous mode now perceives + retrieves (turns.gather_intents)
# ----------------------------------------------------------------------


def _simultaneous_world():
    """Field (player + alice) --north--> Forest (owl), simultaneous mode."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)
    player = things.Character("player", "the hero", "I act.")
    alice = things.Character("alice", "a curious npc", "I look around.")
    owl = things.Character("owl", "a watchful owl", "I observe.")
    game = games.Game(field, player, characters=[alice, owl], turn_mode="simultaneous")
    field.add_character(alice)
    forest.add_character(owl)
    game.set_parser(WebParser(game))
    return game, player, alice, owl


def test_simultaneous_mode_perceives_into_memory():
    game, player, alice, owl = _simultaneous_world()
    alice.vision_r = 1  # the Forest (and the owl) is one hop north
    alice.set_agent(ScriptedAgent(lambda obs: None))  # decline to act; still observes

    assert game.do_command("look")  # advance one simultaneous round

    presence = [r for r in alice.agent.memory.records if "presence" in r.tags]
    # Co-located player + the owl one hop north are both noticed.
    assert {r.text for r in presence} == {"I see player nearby.", "I see owl nearby."}


def test_simultaneous_mode_feeds_retrieved_memory_into_the_prompt():
    game, player, alice, owl = _simultaneous_world()

    seen = []
    agent = ScriptedAgent(lambda obs: seen.append(obs) or None)
    alice.set_agent(agent)
    # A salient prior memory should be retrieved and folded into the gather prompt.
    agent.memory.owner = "alice"
    agent.memory.add_observation("The player gave me a fish.", turn=0, importance=9)

    assert game.do_command("look")

    assert seen, "the agent was never consulted during gather"
    assert "Relevant memories:" in seen[-1]
    assert "The player gave me a fish." in seen[-1]
