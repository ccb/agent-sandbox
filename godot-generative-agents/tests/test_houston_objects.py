"""#466: the boil-water props are visible map data and addressable at the
game_object tier -- the matrix half of #300 (the engine items live in the
world YAML, PR #465)."""

import json
import os

from backend.world_map import WorldMap

UPENN = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "backend", "penn", "the_upenn"
)
TMJ = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "godot",
    "maps",
    "upenn_core_urban.tmj",
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


def test_houston_kitchen_strip_sprites_are_painted():
    """#466: the hand-painted kitchen strip survives in the committed tmj.

    furnish_houston.py strips and rebuilds houston_furniture on rerun and
    would silently drop these cells -- if this fails after a Houston regen,
    re-apply the strip (docs/plans/2026-07-09-houston-boilwater-props.md).
    """
    with open(TMJ) as fh:
        tmj = json.load(fh)
    layer = next(L for L in tmj["layers"] if L["name"] == "houston_furniture")
    W = tmj["width"]
    expected = {
        (117, 247): 1821,
        (117, 248): 1837,  # pedestal sink
        (118, 247): 1255,
        (118, 248): 1287,  # counter
        (119, 247): 1261,
        (119, 248): 1293,  # stove/oven
        (120, 247): 991,
        (120, 248): 1287,  # cooking pot on counter
    }
    for (x, y), gid in expected.items():
        assert layer["data"][y * W + x] == gid, (x, y)
