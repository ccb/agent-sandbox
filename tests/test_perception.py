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
from tests.support import BufferedParser

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
    game.set_parser(BufferedParser(game))
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


# ----------------------------------------------------------------------
# C. Perceive by where it happened + loud events carry to adjacent rooms
# ----------------------------------------------------------------------

from text_adventure_games.actions import base  # noqa: E402
from text_adventure_games.reporting import CaptureRenderer, Channel  # noqa: E402


def _origin_world(npc_room):
    field = things.Location("Field", "An open field.")
    forest = things.Location("Forest", "A dark forest.")
    field.add_connection("north", forest)  # also wires forest --south--> field
    player = things.Character("player", "the player", "I explore.")
    npc = things.Character("troll", "a troll", "I lurk.")
    game = games.Game(field, player, characters=[npc])
    {"Field": field, "Forest": forest}[npc_room].add_character(npc)
    return game, player, npc, field, forest


def test_departure_is_perceived_from_the_origin_room():
    game, player, troll, field, forest = _origin_world("Field")
    mem = AgentMemory(owner="troll")
    game.do_command("north")  # the player leaves the Field
    added = mem.ingest_events(game, troll)  # the troll is still in the Field
    assert [r.text for r in added] == ["player left to the north"]


def test_arrival_is_perceived_from_the_destination_room():
    game, player, troll, field, forest = _origin_world("Forest")
    mem = AgentMemory(owner="troll")
    game.do_command("north")  # the player walks into the Forest, where the troll is
    added = mem.ingest_events(game, troll)
    assert [r.text for r in added] == ["player arrived from Field"]


def test_audible_rooms_walks_the_graph_with_direction_back_to_source():
    game, *_ = _origin_world("Field")
    assert game.audible_rooms("Field", 1) == {"Forest": "south"}
    assert game.audible_rooms("Field", 0) == {}  # silence stays in its room


def test_npc_hears_a_loud_event_from_an_adjacent_room():
    game, player, troll, field, forest = _origin_world("Forest")
    mem = AgentMemory(owner="troll")
    game.log_event(
        "player",
        "scream",
        summary="scream",
        payload={"location": "Field", "heard_radius": 1, "sound": "a scream"},
    )
    added = mem.ingest_events(game, troll)
    assert [r.text for r in added] == ["From the south: a scream"]
    assert added[0].importance == 0.5  # fainter than a witnessed event


def test_actor_less_world_event_is_perceived_at_its_payload_importance():
    """A world-level stimulus (actor=None) that declares where it happened is
    witnessed by a co-located agent, and carries the importance its emitter
    chose -- not the old hardcoded 1.0 that made every injected stimulus
    maximally forgettable regardless of what was injected (#631)."""
    game, player, troll, field, forest = _origin_world("Field")
    mem = AgentMemory(owner="troll")
    game.log_event(
        None,  # world-level: no single actor
        "boiled",
        summary="the pot is boiled clear on the stove",
        payload={"location": "Field", "importance": 8.0},
    )
    added = mem.ingest_events(game, troll)  # the troll is in the Field
    assert len(added) == 1
    assert added[0].importance == 8.0


def test_actor_less_world_event_defaults_to_mundane_importance():
    """No declared importance -> the mundane 1.0 default is preserved, so
    existing world events are unchanged (#631)."""
    game, player, troll, field, forest = _origin_world("Field")
    mem = AgentMemory(owner="troll")
    game.log_event(
        None, "boiled", summary="the pot boiled", payload={"location": "Field"}
    )
    added = mem.ingest_events(game, troll)
    assert len(added) == 1 and added[0].importance == 1.0


def test_a_loud_world_event_is_heard_at_its_scaled_importance():
    """A declared importance also lifts the fainter HEARD case above the flat
    0.5, while an event with no importance still heard at exactly 0.5 (#631)."""
    game, player, troll, field, forest = _origin_world("Forest")
    mem = AgentMemory(owner="troll")
    game.log_event(
        None,
        "explosion",
        summary="a deafening blast",
        payload={"location": "Field", "heard_radius": 1, "importance": 9.0},
    )
    added = mem.ingest_events(game, troll)  # troll is in the Forest, one hop away
    assert len(added) == 1
    assert added[0].importance == 4.5  # 9.0 attenuated by the heard half-weight


class _Scream(base.Action):
    ACTION_NAME = "scream"
    AUDIBLE_RADIUS = 2

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = actor or game.player

    def check_preconditions(self):
        return True

    def apply_effects(self):
        self.parser.ok(f"{self.character.name} screams.")

    def sound_description(self):
        return "a scream"


def test_player_overhears_a_loud_action_from_afar():
    game, player, ranger, field, forest = _origin_world("Field")  # ranger in the Field
    game.parser.add_action(_Scream)
    player.location = forest  # the player is one room north
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.parser.parse_command("scream", actor=ranger)  # ranger screams in the Field
    assert any(
        "From the south you hear a scream" in t for t in cap.texts(Channel.NARRATION)
    )
