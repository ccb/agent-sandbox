"""Offline tests for the Smallville port (no Django, no live LLM, no setup.sh).

Covers the three layers that must stay correct for a replay to render: the
library world + mock-driven agents, the spatial map/pathfinder, and the exporter
that writes the frontend's movement contract.

The spatial/export tests run against a small **synthetic** the_ville maze
(:mod:`synthetic_ville`) rather than the 38MB upstream assets, so the whole
suite passes on a fresh checkout and in CI -- no ``./setup.sh`` required.

Run from the ``generative-agents`` directory (``uv run`` uses the repo's
project env that has the engine installed)::

    uv run pytest tests/ -v
"""

import json
import os

import pytest

from backend import exporter
from backend.build_world import PERSONAS, build_world
from backend.run_simulation import simulate
from backend.smallville_agents import attach_agents
from backend.world_map import WorldMap
from synthetic_ville import build_synthetic_ville


@pytest.fixture(scope="module")
def world_map(tmp_path_factory):
    ville = build_synthetic_ville(str(tmp_path_factory.mktemp("ville")))
    return WorldMap(ville)


# --------------------------------------------------------------------------
# Library world + agents
# --------------------------------------------------------------------------


def test_build_world_places_cast_at_home():
    game, chars = build_world()
    # The full 25-resident town is present.
    assert len(PERSONAS) == 25
    # Every persona is a character in the game...
    for spec in PERSONAS:
        assert spec["name"] in game.characters
        # ...and starts in their home location.
        assert chars[spec["name"]].location.name == spec["home"]
    # The destinations exist as locations.
    assert "Hobbs Cafe" in game.locations
    assert "Oak Hill College" in game.locations


def test_agents_travel_then_perform():
    game, chars = build_world()
    attach_agents(chars, PERSONAS)
    for spec in PERSONAS:
        char = chars[spec["name"]]
        # First decision (at home) -> travel; routing moves the character.
        cmd1 = char.agent.decide(game.describe_for(char))
        assert cmd1.startswith("travel")
        assert game.parser.parse_command(cmd1, actor=char)
        assert char.location.name == spec["destination"]
        # Second decision (at destination) -> perform; sets the activity.
        cmd2 = char.agent.decide(game.describe_for(char))
        assert cmd2.startswith("perform")
        assert game.parser.parse_command(cmd2, actor=char)
        assert char.get_property("activity") == spec["activity"]


# --------------------------------------------------------------------------
# Spatial map + pathfinder
# --------------------------------------------------------------------------


def test_addresses_resolve_to_tiles(world_map):
    assert len(world_map.tiles_for("the Ville:Hobbs Cafe:cafe")) > 0
    assert len(world_map.tiles_for("the Ville:Oak Hill College:library")) > 0
    assert world_map.tiles_for("the Ville:Nowhere At All") == set()


def test_walk_path_is_contiguous_and_collision_free(world_map):
    # Isabella's spawn tile; the synthetic maze puts a wall between it and the
    # cafe, so a correct path has to detour around the wall.
    start = (72, 14)
    address = "the Ville:Hobbs Cafe:cafe"
    path = world_map.walk_path(start, address)
    assert path, "expected a non-empty path to the cafe"
    # Each step moves to an orthogonally-adjacent, non-blocked tile.
    prev = start
    for tile in path:
        dx = abs(tile[0] - prev[0])
        dy = abs(tile[1] - prev[1])
        assert dx + dy == 1, f"non-adjacent step {prev} -> {tile}"
        assert not world_map.is_blocked(tile), f"path crosses a wall at {tile}"
        prev = tile
    # The path ends on a tile of the target address.
    assert path[-1] in world_map.tiles_for(address)


# --------------------------------------------------------------------------
# Simulation driver + exporter contract
# --------------------------------------------------------------------------


def test_simulate_frames_match_contract(world_map):
    frames = simulate(world_map, num_steps=12)
    assert len(frames) == 12
    names = {p["name"] for p in PERSONAS}
    for frame in frames:
        assert set(frame.keys()) == names
        for entry in frame.values():
            assert isinstance(entry["movement"], list) and len(entry["movement"]) == 2
            assert all(isinstance(c, int) for c in entry["movement"])
            assert isinstance(entry["pronunciatio"], str) and entry["pronunciatio"]
            assert (
                isinstance(entry["description"], str) and " @ " in entry["description"]
            )
            assert entry["chat"] is None


def test_simulate_reaches_activity(world_map):
    # Isabella's cafe is a short walk from her spawn, so within 40 steps she
    # should have arrived and settled into tending the counter.
    frames = simulate(world_map, num_steps=40)
    last = frames[-1]["Isabella Rodriguez"]["description"]
    assert "tending the cafe counter" in last


def test_exporter_writes_replayable_layout(world_map, tmp_path):
    frames = simulate(world_map, num_steps=5)
    start_tiles = {p["name"]: tuple(p["start_tile"]) for p in PERSONAS}
    import datetime

    sim_dir = exporter.write_simulation(
        storage_root=str(tmp_path),
        sim_code="test_sim",
        frames=frames,
        start_dt=datetime.datetime(2023, 2, 13, 8, 0, 0),
        start_tiles=start_tiles,
        base_personas_dir=str(tmp_path / "does_not_exist"),
    )
    # movement files: one per step.
    movement_files = os.listdir(os.path.join(sim_dir, "movement"))
    assert len(movement_files) == 5

    with open(os.path.join(sim_dir, "movement", "0.json")) as f:
        mv0 = json.load(f)
    assert set(mv0["persona"].keys()) == {p["name"] for p in PERSONAS}
    assert mv0["meta"]["curr_time"] == "February 13, 2023, 08:00:00"

    with open(os.path.join(sim_dir, "reverie", "meta.json")) as f:
        meta = json.load(f)
    assert meta["step"] == 5
    assert meta["maze_name"] == "the_ville"

    with open(os.path.join(sim_dir, "environment", "0.json")) as f:
        env0 = json.load(f)
    assert env0["Isabella Rodriguez"]["x"] == 72


def test_exporter_honors_start_time_and_sec_per_step(world_map, tmp_path):
    # A custom start time and step length (the new CLI knobs) must flow into
    # meta.json *and* the per-step movement timestamps -- not the hardcoded
    # February-13 / 10-second defaults.
    import datetime

    frames = simulate(world_map, num_steps=3)
    start_tiles = {p["name"]: tuple(p["start_tile"]) for p in PERSONAS}

    sim_dir = exporter.write_simulation(
        storage_root=str(tmp_path),
        sim_code="custom_clock",
        frames=frames,
        start_dt=datetime.datetime(2026, 6, 18, 18, 30, 0),
        start_tiles=start_tiles,
        base_personas_dir=str(tmp_path / "does_not_exist"),
        sec_per_step=60,
    )

    with open(os.path.join(sim_dir, "reverie", "meta.json")) as f:
        meta = json.load(f)
    # start_date is derived from start_dt, so it tracks the flag (no stale default).
    assert meta["start_date"] == "June 18, 2026"
    assert meta["curr_time"] == "June 18, 2026, 18:30:00"
    assert meta["sec_per_step"] == 60

    # Step 2 is 2 * 60s = 2 minutes after the start.
    with open(os.path.join(sim_dir, "movement", "2.json")) as f:
        mv2 = json.load(f)
    assert mv2["meta"]["curr_time"] == "June 18, 2026, 18:32:00"
