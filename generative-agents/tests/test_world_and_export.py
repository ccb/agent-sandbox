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
from backend.build_world import (
    _ALL_PERSONAS,
    MAX_ACTIVE_PERSONAS,
    PERSONAS,
    build_world,
)
from backend.run_simulation import _print_cost_summary, simulate
from backend.smallville_agents import attach_agents
from backend.world_map import WorldMap
from synthetic_ville import build_synthetic_ville
from text_adventure_games.reporting import CaptureRenderer, Channel
from text_adventure_games.usage import UsageLedger


@pytest.fixture(scope="module")
def world_map(tmp_path_factory):
    ville = build_synthetic_ville(str(tmp_path_factory.mktemp("ville")))
    return WorldMap(ville)


# --------------------------------------------------------------------------
# Library world + agents
# --------------------------------------------------------------------------


def test_build_world_places_cast_at_home():
    game, chars = build_world()
    # The full 25-resident roster still loads (nothing deleted), but we run a
    # smaller active subset so the demo's memory/reasoning panels stay readable.
    assert len(_ALL_PERSONAS) == 25
    assert len(PERSONAS) == MAX_ACTIVE_PERSONAS == 5
    # Every active persona is a character in the game...
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


def test_simulate_advances_through_schedule(world_map):
    # With a multi-stop schedule, an agent no longer freezes after its first
    # activity: once a stop's duration elapses it travels on. Over a longer run
    # Isabella's description should show both her first stop and a later one.
    frames = simulate(world_map, num_steps=350)
    activities = {
        f["Isabella Rodriguez"]["description"].split(" @ ")[0] for f in frames
    }
    assert "tending the cafe counter" in activities  # first scheduled stop
    assert "buying fresh milk for the cafe" in activities  # a later stop -> advanced


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

    # Each retrieved memory carries its created_turn and a wall-clock time stamped
    # by the exporter, so the agent card can show when the memory formed. At step 0
    # every memory was created at turn 0, i.e. the 08:00 start time.
    mems0 = mv0["persona"]["Isabella Rodriguez"]["memories"]
    assert mems0, "expected the seeded plan to be retrieved at step 0"
    for mem in mems0:
        assert mem["created_turn"] == 0
        assert mem["time"] == "08:00"

    with open(os.path.join(sim_dir, "reverie", "meta.json")) as f:
        meta = json.load(f)
    assert meta["step"] == 5
    assert meta["maze_name"] == "the_ville"

    with open(os.path.join(sim_dir, "environment", "0.json")) as f:
        env0 = json.load(f)
    assert env0["Isabella Rodriguez"]["x"] == 72


def test_exporter_surfaces_populated_chat(tmp_path):
    """Issue #87: a populated chat field must survive the exporter into the
    movement JSON the frontend's ``chat__<name>`` slot renders -- the "surface
    chat end to end" contract. The other tests only cover the null/mock case
    (chat stays None); this guards the positive case so a future exporter
    refactor can't silently drop a conversation from the replay.

    The frame shape mirrors what ``run_simulation``/``maybe_converse`` produce:
    chat is None until a pair talks, then the ``[speaker, line]`` transcript
    persists on both participants' cards.
    """
    import datetime

    transcript = [
        ["Isabella Rodriguez", "Morning, Maria!"],
        ["Maria Lopez", "Morning! The usual?"],
    ]

    def cell(chat):
        return {
            "movement": [72, 14],
            "pronunciatio": "💬",
            "description": "at the cafe @ the Ville:Hobbs Cafe:cafe",
            "chat": chat,
        }

    frames = [
        {"Isabella Rodriguez": cell(None), "Maria Lopez": cell(None)},
        {"Isabella Rodriguez": cell(transcript), "Maria Lopez": cell(transcript)},
    ]
    start_tiles = {"Isabella Rodriguez": (72, 14), "Maria Lopez": (73, 14)}

    sim_dir = exporter.write_simulation(
        storage_root=str(tmp_path),
        sim_code="chat_sim",
        frames=frames,
        start_dt=datetime.datetime(2023, 2, 13, 8, 0, 0),
        start_tiles=start_tiles,
        base_personas_dir=str(tmp_path / "does_not_exist"),
    )

    with open(os.path.join(sim_dir, "movement", "0.json")) as f:
        before = json.load(f)
    with open(os.path.join(sim_dir, "movement", "1.json")) as f:
        after = json.load(f)

    # Before the conversation the slot is null (renders "None at the moment");
    # after, the whole transcript is present verbatim for BOTH participants.
    assert before["persona"]["Isabella Rodriguez"]["chat"] is None
    for name in ("Isabella Rodriguez", "Maria Lopez"):
        assert after["persona"][name]["chat"] == transcript


def test_exporter_writes_full_memory_stream(world_map, tmp_path):
    # The State Details panel needs each agent's FULL memory stream (not just the
    # per-step retrieved set the cards show). simulate(out_memories=...) collects
    # it and the exporter writes personas/<Name>/memory_stream.json: newest first,
    # each memory carrying the same created_turn + wall-clock time as the cards.
    import datetime

    memory_streams: dict = {}
    frames = simulate(world_map, num_steps=40, out_memories=memory_streams)

    # Every persona has a collected stream, and it grows past the seeded plan.
    assert set(memory_streams) == {p["name"] for p in PERSONAS}
    assert len(memory_streams["Isabella Rodriguez"]) > 1

    start_tiles = {p["name"]: tuple(p["start_tile"]) for p in PERSONAS}
    sim_dir = exporter.write_simulation(
        storage_root=str(tmp_path),
        sim_code="mem_stream_sim",
        frames=frames,
        start_dt=datetime.datetime(2023, 2, 13, 8, 0, 0),
        start_tiles=start_tiles,
        base_personas_dir=str(tmp_path / "does_not_exist"),
        memory_streams=memory_streams,
    )

    stream_path = os.path.join(
        sim_dir, "personas", "Isabella Rodriguez", "memory_stream.json"
    )
    assert os.path.exists(stream_path)
    with open(stream_path) as f:
        stream = json.load(f)
    assert stream["persona_name"] == "Isabella Rodriguez"
    mems = stream["memories"]
    assert mems, "expected a non-empty memory stream"

    # Newest first (created_turn descending) and each carries a wall-clock time
    # plus the same fields the cards render.
    turns = [m["created_turn"] for m in mems]
    assert turns == sorted(turns, reverse=True)
    for m in mems:
        assert "time" in m
        assert {"kind", "importance", "text", "created_turn"} <= set(m)

    # The retrieved set the card shows at a step is a subset of the full stream.
    with open(os.path.join(sim_dir, "movement", "39.json")) as f:
        frame39 = json.load(f)
    retrieved = frame39["persona"]["Isabella Rodriguez"]["memories"]
    stream_texts = {m["text"] for m in mems}
    assert {r["text"] for r in retrieved} <= stream_texts


def test_simulate_out_memories_is_optional(world_map):
    # Default behaviour is unchanged: collecting the streams is purely additive,
    # so the frames are byte-identical whether or not out_memories is passed.
    plain = simulate(world_map, num_steps=12)
    collected: dict = {}
    with_mem = simulate(world_map, num_steps=12, out_memories=collected)
    assert plain == with_mem
    assert collected and set(collected) == {p["name"] for p in PERSONAS}


def test_exporter_writes_daily_plan(world_map, tmp_path):
    # simulate(out_plans=...) collects each agent's generated plan and the exporter
    # writes personas/<Name>/daily_plan.json, so the plan a run used is an
    # inspectable artifact (compare_plans reads it back). With the mock planner the
    # plan is the static schedule, but the file contract is what matters here.
    import datetime

    from text_adventure_games.planning import DailyPlan

    plans: dict = {}
    frames = simulate(world_map, num_steps=12, out_plans=plans)
    assert set(plans) == {p["name"] for p in PERSONAS}

    start_tiles = {p["name"]: tuple(p["start_tile"]) for p in PERSONAS}
    sim_dir = exporter.write_simulation(
        storage_root=str(tmp_path),
        sim_code="plan_sim",
        frames=frames,
        start_dt=datetime.datetime(2023, 2, 13, 8, 0, 0),
        start_tiles=start_tiles,
        base_personas_dir=str(tmp_path / "does_not_exist"),
        plans=plans,
    )
    plan_path = os.path.join(
        sim_dir, "personas", "Isabella Rodriguez", "daily_plan.json"
    )
    assert os.path.exists(plan_path)
    with open(plan_path) as f:
        loaded = DailyPlan.from_primitive(json.load(f))
    # Round-trips to the same plan the agent was given (the static schedule here).
    assert [s.to_schedule_entry() for s in loaded.stops] == PERSONAS[0]["schedule"]


def test_simulate_out_plans_is_optional(world_map):
    # Collecting plans is additive: frames are byte-identical with or without it.
    plain = simulate(world_map, num_steps=12)
    collected: dict = {}
    with_plans = simulate(world_map, num_steps=12, out_plans=collected)
    assert plain == with_plans
    assert set(collected) == {p["name"] for p in PERSONAS}


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


# --------------------------------------------------------------------------
# LLM cost/observability wiring (usage.py)
# --------------------------------------------------------------------------


def test_simulate_records_per_agent_usage(world_map):
    # A shared ledger accumulates one record per persona decision, attributed by
    # name. The mock brain is free, so every record is $0 -- the plumbing is what
    # we assert (it lights up once a real client is wired in, NEXT-STEPS Phase A).
    ledger = UsageLedger()
    simulate(world_map, num_steps=6, ledger=ledger)

    assert ledger.records, "expected the personas' decisions to be recorded"
    assert all(rec.cost_usd == 0.0 for rec in ledger.records)
    by_actor = ledger.totals_by_actor()
    # Every persona that acted is attributed by name (not "(unattributed)").
    assert "(unattributed)" not in by_actor
    assert set(by_actor).issubset({p["name"] for p in PERSONAS})
    assert len(by_actor) > 0


def test_cost_summary_renders_through_reporting_seam(world_map):
    ledger = UsageLedger()
    simulate(world_map, num_steps=3, ledger=ledger)

    cap = CaptureRenderer()
    _print_cost_summary(ledger, renderer=cap)

    lines = cap.texts(Channel.SYSTEM)
    assert any("LLM cost: $" in line for line in lines)
    # One total line plus one per attributed actor.
    assert len(lines) == 1 + len(ledger.totals_by_actor())
