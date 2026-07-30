"""Travel resolution to sub-places, and walks that actually arrive (issue #904).

Batch 10's best social thread died to two routing defects that compounded:

* Theo's ``travel(Van Pelt — Study Booths)`` picked the Euclidean-closest
  booth tile, which sits -- with every booth furniture spot -- in a walled-off
  collision pocket, so ``walk_path`` came back empty and he "arrived" without
  moving a tile.
* Maya re-phrased the room she saw him leave for as "Van Pelt Library — Study
  Booths"; the longest-substring destination match can only see the
  *building's* name in that hybrid, and walked her to the lobby anchor, 80
  tiles from the man she was following.

Pins: hybrid room phrasings resolve to the room (not its building), and
``walk_path`` routes to the nearest *reachable* tile of an address -- on the
real campus, every location address must be arrivable.

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_travel_resolution_904.py -v
"""

import sys
from pathlib import Path

import pytest

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.actions import Travel  # noqa: E402
from backend.build_world import build_world  # noqa: E402

LOCATIONS = [
    {
        "name": "Penn campus",
        "description": "the campus hub",
        "address": None,
        "hub": True,
    },
    {
        "name": "Van Pelt Library",
        "description": "the lobby",
        "address": "UPenn:Van Pelt Library:lobby",
    },
    {
        "name": "Van Pelt — Study Booths",
        "description": "quiet booths",
        "address": "UPenn:Van Pelt Library:Study Booths",
    },
    {
        "name": "Houston Hall",
        "description": "the student union",
        "address": "UPenn:Houston Hall:lobby",
    },
    {
        "name": "Houston Hall — Reception Hall",
        "description": "the food court",
        "address": "UPenn:Houston Hall:Reception Hall",
    },
]

PERSONA = {
    "name": "Ada",
    "home": "Penn campus",
    "persona": "I am Ada.",
    "emoji": "\U0001f4d6",
    "start_tile": [0, 0],
    "destination": "Van Pelt Library",
    "activity": "studying",
    "schedule": [
        {
            "place": "Van Pelt Library",
            "activity": "studying",
            "emoji": "\U0001f4d6",
            "steps": 5,
        },
    ],
}


@pytest.fixture()
def game():
    game, _chars = build_world(None, [PERSONA], LOCATIONS)
    return game


def _resolved(game, command):
    action = Travel(game, command)
    return action.destination.name if action.destination else None


# ------------------------------------------------- name -> Location matching


def test_exact_room_and_building_names_still_resolve_as_before(game):
    assert _resolved(game, "travel to Van Pelt — Study Booths") == (
        "Van Pelt — Study Booths"
    )
    assert _resolved(game, "travel to Van Pelt Library") == "Van Pelt Library"
    assert _resolved(game, "travel to Houston Hall") == "Houston Hall"
    assert _resolved(game, "travel to Houston Hall — Reception Hall") == (
        "Houston Hall — Reception Hall"
    )


def test_hybrid_phrasings_resolve_to_the_room_not_its_building(game):
    # Every phrasing below embeds the literal "Van Pelt Library", which the
    # room's own name ("Van Pelt — ...") is not a substring of -- before #904
    # each one walked the agent to the lobby.
    for command in (
        "travel to Van Pelt Library — Study Booths",
        "travel to Van Pelt Library Study Booths",
        "travel to Study Booths, Van Pelt Library",
    ):
        assert _resolved(game, command) == "Van Pelt — Study Booths", command


def test_a_room_suffix_from_another_building_does_not_hijack(game):
    # "Reception Hall" belongs to Houston Hall; naming it alongside Van Pelt
    # must not teleport the match across buildings.
    assert _resolved(game, "travel to Van Pelt Library Reception Hall") == (
        "Van Pelt Library"
    )


def test_unknown_destinations_still_resolve_to_none(game):
    assert _resolved(game, "travel to home") is None


# ------------------------------------------- walks arrive on the real campus


@pytest.fixture(scope="module")
def penn():
    from backend.penn.penn_world import build_penn_world

    return build_penn_world()


# A Moelis Reading Room tile -- exactly where Theo stood all afternoon.
MOELIS_TILE = (147, 50)
BOOTHS = "UPenn:Van Pelt Library:Study Booths"


def test_walk_path_reaches_the_study_booths_pocket_neighbours(penn):
    # The address's Euclidean-closest tile and all its furniture spots are in
    # a disconnected pocket; the walk must route to a *reachable* booth tile
    # instead of silently returning no path.
    path = penn.world_map.walk_path(MOELIS_TILE, BOOTHS)
    assert path, "travel to the Study Booths must produce a walk"
    tiles = set(map(tuple, penn.world_map.tiles_for(BOOTHS)))
    assert tuple(path[-1]) in tiles
    # 4-neighbour steps only -- the field descent must produce a real walk.
    hops = [MOELIS_TILE, *map(tuple, path)]
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(hops, hops[1:]))


def test_every_campus_address_is_arrivable(penn):
    # The #642 build guard rejects an address with zero tiles, but an address
    # whose tiles are all walled off passed every check before #904. Pin the
    # stronger invariant: every location can actually be walked to.
    for loc in penn.locations:
        address = loc.get("address")
        if not address:
            continue  # the hub has no walkable target by design
        path = penn.world_map.walk_path(MOELIS_TILE, address)
        tiles = set(map(tuple, penn.world_map.tiles_for(address)))
        assert path or MOELIS_TILE in tiles, f"{loc['name']} is unreachable"
        if path:
            assert tuple(path[-1]) in tiles, f"{loc['name']} walk ends off-address"
