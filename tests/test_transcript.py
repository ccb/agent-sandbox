"""Tests for the run transcript and provenance records (reproducible-runs, #197).

The data records -- StepRecord / RunRecord -- round-trip through their primitive
form and save/load as JSON and YAML (the human-readable run file), and the
provenance helpers (file hash, git sha) behave. record_step is a safe no-op when
no recorder is attached.

The ReAct-loop capture hook (PR #61's npc.py/games.py edits) is deferred by scope,
so this suite covers the module in isolation, not live capture.

Run with pytest::

    uv run pytest tests/test_transcript.py -v
"""

import pytest

from text_adventure_games.transcript import (
    RunRecord,
    StepRecord,
    TranscriptRecorder,
    file_sha256,
    git_sha,
    record_step,
)


def _step(**overrides):
    """A fully-populated StepRecord for round-trip tests."""
    fields = dict(
        turn=2,
        actor="troll",
        observation="You are on a drawbridge...",
        system_prompt="You are an NPC...",
        raw_response="Reasoning: hungry\nAction: eat fish",
        reasoning="hungry",
        command="eat fish",
        route_ok=True,
        fail_reason=None,
        world_delta={},
    )
    fields.update(overrides)
    return StepRecord(**fields)


def test_steprecord_round_trips():
    step = _step()
    assert StepRecord.from_primitive(step.to_primitive()) == step


def test_runrecord_round_trips():
    run = RunRecord(
        game="action_castle.build_game",
        seed=0,
        cassette={"path": "run.jsonl", "sha256": "abc123"},
        engine_version="deadbee",
        steps=[_step(turn=1, route_ok=False, fail_reason="no weapon"), _step(turn=2)],
        result={"goal": "troll_fed", "success": True},
    )
    assert RunRecord.from_primitive(run.to_primitive()) == run


def test_runrecord_save_load_json(tmp_path):
    path = str(tmp_path / "run.json")
    run = RunRecord(game="g", seed=7, engine_version="v1", steps=[_step()])
    run.save(path)
    assert RunRecord.load(path) == run


def test_runrecord_save_load_yaml(tmp_path):
    pytest.importorskip("yaml")
    path = str(tmp_path / "run.yaml")
    run = RunRecord(game="g", seed=7, engine_version="v1", steps=[_step()])
    run.save(path)
    loaded = RunRecord.load(path)
    assert loaded == run
    text = open(path, encoding="utf-8").read()
    assert "seed: 7" in text
    assert "eat fish" in text


def test_file_sha256_and_git_sha(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text("hello\n", encoding="utf-8")
    h = file_sha256(str(f))
    assert isinstance(h, str) and len(h) == 64
    assert file_sha256(str(f)) == h
    assert isinstance(git_sha(), str)  # best-effort, never raises


def test_transcript_recorder_collects_steps():
    rec = TranscriptRecorder()
    assert rec.steps == []
    rec.add_step(_step())
    assert len(rec.steps) == 1


def test_record_step_is_a_noop_without_a_recorder():
    class Bare:  # no `transcript` attribute
        pass

    record_step(Bare(), turn=0, actor="x")  # must not raise
