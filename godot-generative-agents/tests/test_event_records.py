"""Offline tests for persisting the GameEvent log into run records (#467).

The record shape everywhere is ``GameEvent.to_primitive()`` — the #305
``EventState`` contract: {turn, actor, action, summary, payload}. The live
feed's rows additionally carry ``kind: "game_event"`` (see serve_penn's
``drain_events``); the bake artifacts carry the dict verbatim.
"""

import datetime
import json
import os
import sys
from pathlib import Path

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); tests import them the way the scripts import each other -- off the
# sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.build_world import _normalize_personas, build_world
from backend.exporter import write_simulation
from backend.penn.penn_world import (
    PENN_EXTRA_ACTIONS,
    _furnish_boil_water,
    build_penn_world,
)
from backend.run_simulation import simulate


def _testa_sip_world():
    """The #300 acceptance scenario (mirrors test_boil_water.py's e2e test):
    a persona homed at Houston Hall whose first stop gets-and-drinks the
    murky water, so a ``sickness`` GameEvent is logged within ~5 steps."""
    pw = build_penn_world()
    persona = {
        "name": "Testa Sip",
        "home": "Houston Hall",
        "persona": "I am Testa Sip, a thirsty test persona.",
        "emoji": "🥤",
        "start_tile": [25, 109],
        "schedule": [
            {
                "place": "Houston Hall",
                "activity": "getting a drink of water",
                "emoji": "🥤",
                "steps": 3,
                "commands": ["get cup of murky water", "drink cup of murky water"],
            }
        ],
    }
    personas = _normalize_personas([persona])

    def build_fn(wm):
        game, characters = build_world(
            wm, personas, pw.locations, extra_actions=PENN_EXTRA_ACTIONS
        )
        _furnish_boil_water(game)
        return game, characters

    return pw, personas, build_fn


def test_simulate_out_events_carries_sickness_record():
    """#467 acceptance, bake source: the run's GameEvent log comes back
    through ``out_events`` with the sickness cause payload intact."""
    pw, personas, build_fn = _testa_sip_world()
    events: list = []
    simulate(
        pw.world_map,
        10,
        personas=personas,
        build_world_fn=build_fn,
        out_events=events,
    )
    sickness = [e for e in events if e["action"] == "sickness"]
    assert sickness, f"no sickness event in {events}"
    record = sickness[0]
    assert record["payload"] == {
        "item": "cup of murky water",
        "location": "Houston Hall",
    }
    assert record["actor"] == "Testa Sip"
    assert {"turn", "summary"} <= set(record)


def test_penn_replay_bake_writes_events_key(tmp_path, monkeypatch):
    """#467 acceptance, bake artifact: the replay JSON carries the run's
    event log as a top-level ``events`` array (empty is fine for a short
    run — presence and shape are the contract; the sickness *content* is
    pinned at the simulate() seam above)."""
    from backend.penn import generate_penn_replay

    out = tmp_path / "penn_replay.json"
    monkeypatch.setattr(
        sys, "argv", ["generate_penn_replay", "--steps", "8", "--out", str(out)]
    )
    assert generate_penn_replay.main() == 0
    replay = json.loads(out.read_text())
    assert isinstance(replay["events"], list)
    for record in replay["events"]:
        assert {"turn", "actor", "action", "summary", "payload"} <= set(record)


def test_write_simulation_writes_events_json(tmp_path):
    """#467: the generic exporter persists the event log beside the other
    run artifacts. frames=[] keeps the fixture minimal — write_simulation
    tolerates a missing base personas dir and zero steps."""
    events = [
        {
            "turn": 1,
            "actor": "A",
            "action": "sickness",
            "summary": "A got sick drinking cup",
            "payload": {"item": "cup", "location": "Houston Hall"},
        }
    ]
    sim_dir = write_simulation(
        storage_root=str(tmp_path),
        sim_code="test_sim",
        frames=[],
        start_dt=datetime.datetime(2023, 2, 13, 8, 0, 0),
        start_tiles={"A": (0, 0)},
        base_personas_dir=str(tmp_path / "no_such_dir"),
        events=events,
    )
    with open(f"{sim_dir}/events.json") as fh:
        assert json.load(fh) == events


def _game_event_rows(rows):
    return [r for r in rows if r.get("kind") == "game_event"]


def test_penn_stepper_drains_game_events_exactly_once():
    """#467 live half: drain_events yields each GameEvent once, stamped
    kind=game_event, alongside (not instead of) the llm_call rows."""
    from backend.penn.serve_penn import PennStepper

    stepper = PennStepper(num_steps=2)
    turn = stepper.game.turn
    stepper.game.log_event(
        "Sofia Ramirez", "sickness", summary="felt awful", payload={"item": "cup"}
    )
    assert _game_event_rows(stepper.drain_events()) == [
        {
            "turn": turn,
            "actor": "Sofia Ramirez",
            "action": "sickness",
            "summary": "felt awful",
            "payload": {"item": "cup"},
            "kind": "game_event",
        }
    ]
    assert _game_event_rows(stepper.drain_events()) == []


def test_penn_stepper_reset_restarts_event_cursor():
    from backend.penn.serve_penn import PennStepper

    stepper = PennStepper(num_steps=2)
    stepper.game.log_event("a", "narration", summary="before reset")
    stepper.drain_events()
    stepper.reset()
    stepper.game.log_event("b", "narration", summary="after reset")
    rows = _game_event_rows(stepper.drain_events())
    assert [r["actor"] for r in rows] == ["b"]


def test_persisted_bake_round_trips_the_store(tmp_path, monkeypatch):
    # The #304 determinism guardrail: the store's copy of a bake equals the
    # replay file, and store-side memory queries score like the engine.
    from backend.penn import generate_penn_replay
    from backend.run_store import RunStore
    from text_adventure_games.memory import AgentMemory, MemoryRecord

    out = tmp_path / "penn_replay.json"
    runs = tmp_path / "runs"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_penn_replay",
            "--steps",
            "8",
            "--out",
            str(out),
            "--persist",
            "--runs-dir",
            str(runs),
        ],
    )
    assert generate_penn_replay.main() == 0
    replay = json.loads(out.read_text())
    store = RunStore(runs)
    (run,) = store.list_runs()
    assert run["status"] == "finished"
    assert run["steps"] == len(replay["frames"])
    assert run["cost"] == 0.0
    assert run["manifest"] == replay["meta"]
    # Frames: byte-equal to the file's (persisted AFTER meeting injection).
    assert store.read_frames(run["id"]) == replay["frames"]
    # Events: the store's copy == the file's GameEvent log (#307).
    assert store.read_events(run["id"]) == replay["events"]
    # Memory streams: the store's lean projection == the file's, per persona.
    for name, stream in replay["memory_streams"].items():
        assert store.memories_for(run["id"], name) == stream
    # Query parity: the store's retrieve delegation == a direct engine call
    # over the same rehydrated records.
    name = next(iter(replay["memory_streams"]))
    engine = AgentMemory(owner=name)
    engine.records = [
        MemoryRecord.from_primitive(r) for r in store.full_records(run["id"], name)
    ]
    expected = [r.text for r in engine.retrieve("campus day plan", 8, touch=False)]
    got = [
        m["text"] for m in store.query_memories(run["id"], name, "campus day plan", 8)
    ]
    assert got == expected
    # #307: the exported replay IS the baked file -- the whole live->replay
    # bridge is byte-faithful -- and it validates against the pinned contract.
    from backend.contract_models import Replay
    from backend.penn import export_replay

    exported = export_replay.build_replay(store, run["id"])
    assert exported == replay
    Replay.model_validate(exported)
    # The CLI writes the same thing.
    out_path = tmp_path / "exported.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["export_replay", run["id"], "--runs-dir", str(runs), "--out", str(out_path)],
    )
    assert export_replay.main() == 0
    assert json.loads(out_path.read_text()) == replay
