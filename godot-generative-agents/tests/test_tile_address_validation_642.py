"""build_world validates a Location's tile_address against the matrix (#642).

A typo'd address used to build cleanly and fail only as silent motion: walk_path
returns [] for an address with no tiles, so the agent re-issues `travel` forever
-- no error, no event, a frozen sprite burning live spend. build_world now
fail-loud rejects a non-empty tile_address that resolves to no tiles, mirroring
its existing home/place name validation.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_tile_address_validation_642.py -v
"""

import pytest

from backend.build_world import build_world


class _StubMap:
    """Duck-typed WorldMap exposing only what the #642 guard reads: tiles_for()
    and address_tiles (the known-address universe for the nearest-match hint).
    tiles_for mirrors the real WorldMap -- an unknown address yields no tiles."""

    def __init__(self, addresses):
        self.address_tiles = {a: {(0, 0)} for a in addresses}

    def tiles_for(self, address):
        return self.address_tiles.get(address, set())


def _locations(library_address):
    # A two-location world: a label-only hub (address: null, like Penn's) plus a
    # Library whose tile_address is the value under test.
    return [
        {
            "name": "The Green",
            "description": "the central lawn",
            "address": None,
            "hub": True,
        },
        {
            "name": "Library",
            "description": "a small library",
            "address": library_address,
        },
    ]


def _personas():
    # Only the keys build_world reads: name, persona, home, schedule[].place.
    return [
        {
            "name": "Ada",
            "persona": "I am Ada, a curious first-year.",
            "home": "The Green",
            "schedule": [{"place": "Library"}],
        }
    ]


def test_unresolved_address_raises_and_names_it():
    # No address in the map is close to the typo, so the message names the bad
    # address with no (misleading) suggestion.
    world_map = _StubMap(["UPenn:Houston Hall:lobby"])
    with pytest.raises(ValueError) as exc:
        build_world(world_map, _personas(), _locations("XX:Totally:Bogus"))
    msg = str(exc.value)
    assert "XX:Totally:Bogus" in msg
    assert "Did you mean" not in msg


def test_near_match_address_suggests_the_real_one():
    real = "UPenn:Van Pelt Library:Moelis Family Grand Reading Room"
    typo = "UPenn:Van Pelt Library:Moelis Reading Room"
    world_map = _StubMap([real])
    with pytest.raises(ValueError) as exc:
        build_world(world_map, _personas(), _locations(typo))
    assert f"Did you mean '{real}'" in str(exc.value)


def test_no_world_map_skips_validation():
    # A tileless world perceives by room and never paths on tile_address, so the
    # guard must not fire without a matrix -- even for a bogus address.
    build_world(None, _personas(), _locations("XX:Totally:Bogus"))


def test_label_only_none_address_is_not_flagged():
    # The hub carries address: null (world_data_upenn.yaml); tiles_for(None) is
    # empty, but that is an intentional label-only location, not a typo. With the
    # Library resolving, build must not raise on the None-address hub.
    real = "UPenn:Van Pelt Library:lobby"
    world_map = _StubMap([real])
    build_world(world_map, _personas(), _locations(real))
