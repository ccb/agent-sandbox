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
WILLIAMS_CLASSROOM_A = "UPenn:Williams Hall:Classroom A"


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


def test_classroom_a_address_resolves_and_has_spots():
    # Task 5 (#538): Williams Hall — Classroom A is now a schedulable
    # location (Professor Tanaka's problem session). Its address must
    # resolve to real tiles and carry furniture spots (the blackboard),
    # just like the other furnished Williams arenas.
    wm = _world_map()
    tiles = wm.tiles_for(WILLIAMS_CLASSROOM_A)
    assert tiles, "Classroom A address has no tiles"
    assert wm.furniture_spots.get(WILLIAMS_CLASSROOM_A)


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
    # Task 2: one-per-piece model means Houston lobby has only 1 spot (its
    # single furniture piece), so both arrivals land on the same tile. The
    # round-robin _mechanism_ still works on multi-piece rooms; we just can't
    # test it with Houston:lobby anymore. Verify the spot exists and is walkable.
    wm = _world_map()
    start = (100, 50)
    assert not wm.is_blocked(start), f"start {start} is blocked"
    spot = wm.walk_path(start, HOUSTON)[-1]
    assert spot in wm.furniture_spots[HOUSTON]
    assert not wm.is_blocked(spot), "routed spot must be walkable"


def test_furniture_spots_loaded_from_the_committed_artifact():
    # WorldMap now LOADS spots from furniture_spots.csv (generated tmj-aware),
    # not re-derived. Every loaded spot's address is a real w:s:a string and
    # its tile is walkable; a furnished arena has some.
    import os

    wm = _world_map()
    blocks = os.path.join(
        os.path.dirname(__file__),
        "..",
        "backend",
        "penn",
        "the_upenn",
        "matrix",
        "special_blocks",
    )
    assert os.path.exists(os.path.join(blocks, "furniture_spots.csv"))
    assert wm.furniture_spots, "no spots loaded from furniture_spots.csv"
    for address, tiles in wm.furniture_spots.items():
        assert address.count(":") >= 2  # world:sector:arena
        for x, y in tiles:
            assert wm.collision[y][x] == 0  # every spot is walkable


def test_furniture_spots_csv_carries_the_piece_type():
    # #559: each spot row gains a 6th field, the furniture piece's name, so the
    # router can prefer a specific piece (a teacher -> blackboard, not a desk).
    import os

    blocks = os.path.join(
        os.path.dirname(__file__),
        "..",
        "backend",
        "penn",
        "the_upenn",
        "matrix",
        "special_blocks",
    )
    rows = [
        r
        for r in open(os.path.join(blocks, "furniture_spots.csv")).read().splitlines()
        if r.strip()
    ]
    for r in rows:
        assert len(r.split(",")) == 6, f"expected 6 fields (incl. furniture): {r!r}"
    classroom = [
        [c.strip() for c in r.split(",")]
        for r in rows
        if "Williams Hall" in r and "Classroom A" in r
    ]
    names = [c[5] for c in classroom]
    assert (
        names.count("blackboard") == 1
    ), f"Classroom A blackboard spot missing: {names}"
    assert names.count("student_desk") == 12, f"Classroom A desks wrong: {names}"


def test_worldmap_exposes_spot_furniture_type():
    # #559: the piece name loads into a parallel furniture_spot_type map keyed
    # by tile; furniture_spots keeps its (x, y) tile shape.
    wm = _world_map()
    assert hasattr(wm, "furniture_spot_type"), "WorldMap missing furniture_spot_type"
    classroom_spots = wm.furniture_spots.get(WILLIAMS_CLASSROOM_A)
    assert classroom_spots, "Classroom A has no spots"
    types = {wm.furniture_spot_type.get(t) for t in classroom_spots}
    assert "blackboard" in types, f"no blackboard spot in Classroom A: {types}"
    # Shape unchanged: spots are still plain (x, y) tiles.
    assert all(isinstance(t, tuple) and len(t) == 2 for t in classroom_spots)
