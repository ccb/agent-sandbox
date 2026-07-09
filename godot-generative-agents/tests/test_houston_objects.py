"""#466: the boil-water props are visible map data and addressable at the
game_object tier -- the matrix half of #300 (the engine items live in the
world YAML, PR #465)."""

import os

from backend.world_map import WorldMap

UPENN = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "backend", "penn", "the_upenn"
)


def _collision():
    path = os.path.join(UPENN, "matrix", "maze", "collision_maze.csv")
    return open(path).read().strip().split(", ")


def test_houston_boilwater_objects_resolve_and_are_routable():
    wm = WorldMap(UPENN)
    coll = _collision()
    for obj in ("sink", "stove", "pot"):
        tiles = wm.address_tiles.get(f"UPenn:Houston Hall:lobby:{obj}")
        assert tiles, f"no tiles resolve for {obj}"
        for x, y in tiles:
            assert (
                coll[y * wm.width + x] == "0"
            ), f"{obj} use-tile ({x},{y}) is not walkable"
