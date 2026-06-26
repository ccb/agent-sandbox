"""Offline tests for tile-distance perception in Smallville (issue #82).

Issue #80 gave the engine an overridable visibility seam,
``Game.perceivable_locations``. Here we test the Smallville override
(:class:`gen_agents.tiled_game.TiledGame`) that answers "what's nearby" with **tile
distance** on the map instead of room hops, so co-location on the map becomes
co-presence in the sim:

  * ``WorldMap.tile_gap`` measures the gap between two arenas in tiles, and
  * ``TiledGame.perceivable_locations`` keeps the arenas within ``vision_r`` of
    the viewer's current arena, which the engine's ``perceive`` then folds into
    memory.

All offline against the synthetic maze fixture (``synthetic_ville``); its six
arenas are deliberately spread out (cafe<->pub is 14 tiles), so the cross-arena
path is exercised by widening the radius. Run from ``generative-agents``::

    uv run pytest tests/test_tiled_perception.py -v
"""

import pytest

from gen_agents.build_world import PERSONAS, build_world
from gen_agents.world_map import WorldMap
from gen_agents.smallville_agents import attach_agents
from synthetic_ville import build_synthetic_ville

# Arena addresses in the synthetic ville (world:sector:arena). Footprints:
#   cafe (70-74, 26-29), pub (48-56, 10-16), store (70-80, 78-84).
CAFE = "the Ville:Hobbs Cafe:cafe"
PUB = "the Ville:The Rose and Crown Pub:pub"
STORE = "the Ville:The Willows Market and Pharmacy:store"


@pytest.fixture(scope="module")
def world_map(tmp_path_factory):
    ville = build_synthetic_ville(str(tmp_path_factory.mktemp("ville")))
    return WorldMap(ville)


def _move(game, char, location_name):
    """Move ``char`` into a named engine location (leaving its old room)."""
    if char.location is not None:
        char.location.remove_character(char)
    game.locations[location_name].add_character(char)


def _presence(char):
    return {r.text for r in char.agent.memory.records if "presence" in r.tags}


# --------------------------------------------------------------------------
# WorldMap.tile_gap
# --------------------------------------------------------------------------


def test_tile_gap_same_address_is_zero(world_map):
    assert world_map.tile_gap(CAFE, CAFE) == 0


def test_tile_gap_between_arenas_is_chebyshev(world_map):
    # cafe (70-74,26-29) vs pub (48-56,10-16): dx=14, dy=10 -> 14.
    assert world_map.tile_gap(CAFE, PUB) == 14
    # cafe vs store (70-80,78-84): x overlaps, dy=49 -> 49.
    assert world_map.tile_gap(CAFE, STORE) == 49
    assert world_map.tile_gap(PUB, CAFE) == 14  # symmetric


def test_tile_gap_unknown_address_is_never_nearby(world_map):
    # A home address (only ever a label) carves no tiles -> a big sentinel gap.
    gap = world_map.tile_gap(CAFE, "the Ville:Isabella Rodriguez's apartment:main room")
    assert gap >= world_map.width


# --------------------------------------------------------------------------
# TiledGame.perceivable_locations
# --------------------------------------------------------------------------


def test_radius_8_sees_only_its_own_arena(world_map):
    game, chars = build_world(world_map)
    char = chars[PERSONAS[0]["name"]]
    char.location = game.locations["Hobbs Cafe"]
    char.vision_r = 8  # nearest other arena (pub) is 14 tiles away
    assert {l.name for l in game.perceivable_locations(char)} == {"Hobbs Cafe"}


def test_wider_radius_reaches_near_arena_not_far(world_map):
    game, chars = build_world(world_map)
    char = chars[PERSONAS[0]["name"]]
    char.location = game.locations["Hobbs Cafe"]
    char.vision_r = 15  # pub is 14 away (in), store is 49 (out)
    names = {l.name for l in game.perceivable_locations(char)}
    assert "Hobbs Cafe" in names  # always the current room
    assert "The Rose and Crown Pub" in names
    assert "The Willows Market and Pharmacy" not in names


def test_no_world_map_falls_back_to_current_room():
    game, chars = build_world()  # vanilla fallback: no map
    char = chars[PERSONAS[0]["name"]]
    char.vision_r = 8
    assert game.perceivable_locations(char) == [char.location]


def test_hub_without_tiles_falls_back_to_current_room(world_map):
    game, chars = build_world(world_map)
    char = chars[PERSONAS[0]["name"]]
    char.location = game.start_at  # the hub: tile_address is None
    char.vision_r = 8
    assert game.perceivable_locations(char) == [char.location]


def test_no_location_perceives_nothing(world_map):
    game, chars = build_world(world_map)
    char = chars[PERSONAS[0]["name"]]
    char.location = None
    assert game.perceivable_locations(char) == []


# --------------------------------------------------------------------------
# End-to-end: tile proximity becomes co-presence in memory (the #82 win)
# --------------------------------------------------------------------------


def test_colocated_residents_perceive_each_other(world_map):
    game, chars = build_world(world_map)
    attach_agents(chars, PERSONAS)  # vision_r = 8 for every resident
    isabella, maria = chars["Isabella Rodriguez"], chars["Maria Lopez"]
    _move(game, isabella, "Hobbs Cafe")
    _move(game, maria, "Hobbs Cafe")

    isabella.agent.memory.perceive(game, isabella)
    assert "I see Maria Lopez nearby." in _presence(isabella)


def test_cross_arena_perception_within_radius(world_map):
    game, chars = build_world(world_map)
    attach_agents(chars, PERSONAS)
    isabella, maria = chars["Isabella Rodriguez"], chars["Maria Lopez"]
    _move(game, isabella, "Hobbs Cafe")
    _move(game, maria, "The Rose and Crown Pub")  # 14 tiles from the cafe
    isabella.vision_r = 15

    isabella.agent.memory.perceive(game, isabella)
    assert "I see Maria Lopez nearby." in _presence(isabella)


def test_no_perception_beyond_radius(world_map):
    game, chars = build_world(world_map)
    attach_agents(chars, PERSONAS)
    isabella, maria = chars["Isabella Rodriguez"], chars["Maria Lopez"]
    _move(game, isabella, "Hobbs Cafe")
    _move(game, maria, "The Rose and Crown Pub")
    isabella.vision_r = 8  # pub is 14 tiles away -> out of view

    isabella.agent.memory.perceive(game, isabella)
    assert "I see Maria Lopez nearby." not in _presence(isabella)
