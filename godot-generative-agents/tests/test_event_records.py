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
