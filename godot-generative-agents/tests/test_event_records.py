"""Offline tests for persisting the GameEvent log into run records (#467).

The record shape everywhere is ``GameEvent.to_primitive()`` — the #305
``EventState`` contract: {turn, actor, action, summary, payload}. The live
feed's rows additionally carry ``kind: "game_event"`` (see serve_penn's
``drain_events``); the bake artifacts carry the dict verbatim.
"""

import datetime
import json
import sys

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
    import os

    # Add penn directory to sys.path so generate_penn_replay can import penn_world
    penn_dir = os.path.join(os.path.dirname(__file__), "..", "backend", "penn")
    monkeypatch.syspath_prepend(penn_dir)

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
