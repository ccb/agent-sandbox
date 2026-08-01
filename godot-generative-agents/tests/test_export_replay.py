"""Live->replay exporter unit tests (issue #307). Synthetic stores in tmp_path;
the bake-based end-to-end equality lives in test_event_records.py."""

import json
import sys

import pytest

from backend.penn.export_replay import build_replay, main
from backend.replay_codec import fatten_frames, slim_frames
from backend.run_store import RunStore
from text_adventure_games.memory import MemoryKind, MemoryRecord

MANIFEST = {
    "schema_version": 1,
    "personas": [{"name": "Ada"}, {"name": "Bea"}],
    "llm": {"provider": "anthropic", "model": "claude-haiku-4-5"},
}

FRAME = {
    "Ada": {"x": 1, "y": 2, "act": "reading", "e": "book"},
    "Bea": {"x": 3, "y": 4, "act": "walking", "e": "walk"},
}

EVENT = {
    "turn": 0,
    "actor": "Ada",
    "action": "world_event",
    "summary": "a siren wails",
    "payload": {},
}

WISH = {
    "actor": "Ada",
    "turn": 0,
    "location": None,
    "desired": "a working printer",
    "reason": "",
    "trigger": "proposed",
    "goals": [],
    "scope": [],
    "raw_command": "propose a working printer",
    "meta": {},
}


def _seed_run(store, run_id):
    store.create_run(MANIFEST, run_id=run_id)
    for i in range(2):
        store.append_frame(run_id, i, FRAME)
    store.append_events(run_id, [EVENT])
    store.append_wishes(run_id, [WISH])
    store.record_memories(
        run_id,
        "Ada",
        [
            MemoryRecord(
                id=0,
                kind=MemoryKind("observation"),
                text="saw a book",
                created_turn=0,
                last_accessed_turn=0,
                importance=3.0,
            ).to_primitive()
        ],
    )
    return run_id


def test_build_replay_assembles_the_five_keys(tmp_path):
    store = RunStore(tmp_path / "runs")
    run_id = _seed_run(store, "run-a")
    replay = build_replay(store, run_id)
    # Key order matches the bake's file exactly (#305 Replay; "wishes" #622).
    assert list(replay) == ["meta", "frames", "memory_streams", "events", "wishes"]
    # A live manifest has no steps -> filled from the frame count; the llm
    # key rides along untouched.
    assert replay["meta"]["steps"] == 2
    assert replay["meta"]["llm"] == MANIFEST["llm"]
    # build_replay hands back FAT frames (#941): carry-forward fields are
    # rehydrated so in-process consumers see full rows.
    assert replay["frames"] == fatten_frames([FRAME, FRAME])
    assert replay["events"] == [EVENT]
    assert replay["wishes"] == [WISH]
    assert replay["memory_streams"]["Ada"] == store.memories_for(run_id, "Ada")
    assert replay["memory_streams"]["Bea"] == []  # every persona present


def test_build_replay_keeps_a_bake_style_steps_count(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(dict(MANIFEST, steps=40), run_id="run-b")
    store.append_frame("run-b", 0, FRAME)
    # A manifest that already knows steps (the bake's) passes through
    # untouched -- the round-trip guardrail depends on it.
    assert build_replay(store, "run-b")["meta"]["steps"] == 40


def test_build_replay_unknown_run_raises(tmp_path):
    store = RunStore(tmp_path / "runs")
    with pytest.raises(ValueError):
        build_replay(store, "missing")


def _as_written(replay: dict) -> dict:
    """What the CLI writes (#941): slim frames, and meta.schema_version
    stamped with the encoding version this writer used (not whatever version
    the run was recorded under)."""
    from backend.contract import SCHEMA_VERSION

    return dict(
        replay,
        meta=dict(replay["meta"], schema_version=SCHEMA_VERSION),
        frames=slim_frames(replay["frames"]),
    )


def test_cli_exports_the_newest_run_by_default(tmp_path, monkeypatch, capsys):
    store = RunStore(tmp_path / "runs")
    _seed_run(store, "run-a")
    _seed_run(store, "run-b")  # same-second create -> the id tiebreak picks run-b
    monkeypatch.setattr(
        sys, "argv", ["export_replay", "--runs-dir", str(tmp_path / "runs")]
    )
    assert main() == 0
    out = tmp_path / "runs" / "run-b" / "penn_replay.json"
    assert json.loads(out.read_text()) == _as_written(build_replay(store, "run-b"))
    assert str(out.resolve()) in capsys.readouterr().out  # the picker-ready path


def test_cli_explicit_run_and_out_path(tmp_path, monkeypatch):
    store = RunStore(tmp_path / "runs")
    _seed_run(store, "run-a")
    out = tmp_path / "exported" / "replay.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_replay",
            "run-a",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--out",
            str(out),
        ],
    )
    assert main() == 0
    assert json.loads(out.read_text()) == _as_written(build_replay(store, "run-a"))


def test_cli_errors_clearly(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["export_replay", "--runs-dir", str(tmp_path / "runs")]
    )
    assert main() == 2  # empty store
    assert "No runs" in capsys.readouterr().out
    RunStore(tmp_path / "runs").create_run(MANIFEST, run_id="run-a")
    monkeypatch.setattr(
        sys, "argv", ["export_replay", "missing", "--runs-dir", str(tmp_path / "runs")]
    )
    assert main() == 2  # unknown id
    assert "missing" in capsys.readouterr().out
