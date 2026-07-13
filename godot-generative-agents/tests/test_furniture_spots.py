"""Furniture-aware destinations (#537): spots derived at load, preferred by
the building routing, centroid fallback for bare arenas (Williams)."""

import sys
from pathlib import Path

_PENN = Path(__file__).resolve().parent.parent / "backend" / "penn"
sys.path.insert(0, str(_PENN.parent))
sys.path.insert(0, str(_PENN))

from penn_world import build_penn_world  # noqa: E402

HOUSTON = "UPenn:Houston Hall:lobby"
WILLIAMS = "UPenn:Williams Hall:lobby"


def _world_map():
    return build_penn_world().world_map


def test_spots_are_walkable_and_furnished_arenas_have_them():
    wm = _world_map()
    assert wm.furniture_spots.get(HOUSTON), "Houston lobby derived no spots"
    for address, tiles in wm.furniture_spots.items():
        for t in tiles:
            assert not wm.is_blocked(t), f"blocked spot {t} in {address}"
            assert t in wm.tiles_for(address), f"spot {t} outside {address}"


def test_williams_blackboards_are_spots():
    # Task 2's contact-sheet pass corrected the spec's premise: Williams'
    # furniture layer carries BLACKBOARDS in the lobby (its 46 window tiles
    # sit on the grounds and are category-excluded). Tanaka's problem
    # session should land AT a blackboard, so the lobby has spots.
    assert _world_map().furniture_spots.get(WILLIAMS)


def test_arenas_without_furniture_fall_back_to_centroid():
    # SOME arena-level addresses genuinely have no furniture spots (bare
    # rooms, most grounds) — routing to one must keep today's behavior.
    wm = _world_map()
    # (100, 300) was out of bounds (world is 245x279). Using (100, 50) instead,
    # a walkable outdoor point south of campus.
    start = (100, 50)
    assert not wm.is_blocked(start), f"start {start} is blocked"
    bare = [
        a
        for a in wm.address_tiles
        if a.count(":") == 2
        and a not in wm.furniture_spots
        and any(not wm.is_blocked(t) for t in wm.tiles_for(a))
    ]
    assert bare, "every arena has spots?! the fallback path would be dead code"
    path = wm.walk_path(start, bare[0])
    if path:  # unreachable bare arenas (no door) are allowed to no-path
        assert path[-1] in wm.tiles_for(bare[0])


def test_routing_prefers_a_spot_in_furnished_buildings():
    wm = _world_map()
    # (100, 300) was out of bounds (world is 245x279). Using (100, 50) instead,
    # a walkable outdoor point south of campus.
    start = (100, 50)
    assert not wm.is_blocked(start), f"start {start} is blocked"
    path = wm.walk_path(start, HOUSTON)  # approach from campus south
    assert path, "no path into Houston Hall"
    assert path[-1] in wm.furniture_spots[HOUSTON]


def test_co_arrivals_spread_across_spots():
    wm = _world_map()
    # (100, 300) was out of bounds (world is 245x279). Using (100, 50) instead,
    # a walkable outdoor point south of campus.
    start = (100, 50)
    assert not wm.is_blocked(start), f"start {start} is blocked"
    a = wm.walk_path(start, HOUSTON)[-1]
    b = wm.walk_path(start, HOUSTON)[-1]
    assert a != b, "round-robin should hand co-arrivals different spots"
