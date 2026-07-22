"""Re-run bridge (#715): a persisted run records a cassette + seed + engine sha,
and re-runs offline byte-identically. Uses --brain scripted -- free, key-free,
deterministic, and (unlike --brain mock) it routes through the real client seam
the cassette taps."""

import json
import os
import sys
from pathlib import Path

import pytest

from text_adventure_games.transcript import RunRecord, file_sha256

# The Penn sim modules live in the Godot tree and are imported the way the
# scripts import each other -- flat, off the sim directory (serve_penn.py does
# `from scripted_brain import ...`), NOT as backend.penn.serve_penn. This
# mirrors godot-generative-agents/tests/test_penn_live.py:26-47. `backend.*`
# and `text_adventure_games.*` still import normally (editable install +
# PYTHONPATH=.:godot-generative-agents in the run command).
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from serve_penn import SCRIPTED, PennStepper  # noqa: E402

# NOTE (#715 Task 2 vs Task 4): the brief's Step 1 header also names
# `reproduce_run`, but that symbol is added in Task 4 -- importing it here
# would ImportError before this task's own TypeError check ever runs (proven
# empirically; cross-checked against task-3/4-brief.md, neither of which
# expects it importable yet either). Left out here; Task 4 adds it back.
from penn_world import build_penn_world  # noqa: E402
from backend.run_store import RunStore  # noqa: E402

RERUN_STEPS = 6  # enough for several scripted decides; fast under the mock clock


def _scripted_stepper(tmp_path, steps=RERUN_STEPS):
    """A persisted scripted stepper on a fresh store rooted at tmp_path."""
    return PennStepper(
        num_steps=steps,
        world=build_penn_world(),
        monitor=None,
        llm=SCRIPTED,
        run_store=RunStore(tmp_path / "runs"),
        seed=0,
        decide_workers=0,
    )


def test_persisted_run_manifest_carries_seed_and_engine_sha(tmp_path):
    stepper = _scripted_stepper(tmp_path)
    run_id = stepper._run_id
    manifest = json.loads((tmp_path / "runs" / run_id / "manifest.json").read_text())
    assert manifest["seed"] == 0
    assert isinstance(manifest["engine_sha"], str) and manifest["engine_sha"]


def test_scripted_run_records_a_nonempty_cassette(tmp_path):
    stepper = _scripted_stepper(tmp_path)
    for _ in range(RERUN_STEPS):
        stepper.tick()
    cassette = tmp_path / "runs" / stepper._run_id / "cassette.jsonl"
    assert cassette.exists()
    lines = [l for l in cassette.read_text().splitlines() if l.strip()]
    assert lines, "the scripted decides should have been recorded"
    # Every line is a decodable cassette entry with a method tag.
    assert all("method" in json.loads(l) for l in lines)


def test_finish_run_writes_run_record_with_matching_cassette_sha(tmp_path):
    stepper = _scripted_stepper(tmp_path)
    for _ in range(RERUN_STEPS):
        stepper.tick()
    stepper._finish_run()

    run_dir = tmp_path / "runs" / stepper._run_id
    record = RunRecord.load(str(run_dir / "run.yaml"))
    assert record.game == "penn"
    assert record.seed == 0
    assert record.engine_version and record.engine_version != "unknown"
    assert record.cassette["path"] == "cassette.jsonl"
    assert record.cassette["sha256"] == file_sha256(str(run_dir / "cassette.jsonl"))


def test_resume_after_reset_does_not_crash_on_a_scripted_run(tmp_path):
    # Regression: a skipped (resume) build must reset the primary clients to
    # raw, not leave them wrapping a closed cassette (would ValueError on the
    # next decide). Existing resume tests use the mock brain, which skips the
    # recording hook, so they never exercised this.
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(
        num_steps=RERUN_STEPS,
        world=build_penn_world(),
        monitor=None,
        llm=SCRIPTED,
        run_store=store,
        seed=0,
        decide_workers=0,
    )
    run_a = stepper._run_id
    stepper.tick()
    stepper.tick()
    stepper.reset()  # opens run B, closes run A's cassette writer
    stepper.tick()
    stepper.tick()
    stepper.resume_run(run_a)  # skipped-hook build: clients must reset to raw
    stepper.tick()  # the decide that used to crash on the closed file
    # If we got here without ValueError, the primary clients were live.


def test_mock_run_persists_provenance_without_a_cassette(tmp_path):
    # --brain mock: no funnel client, so no cassette, but seed+engine_sha still land.
    stepper = PennStepper(
        num_steps=RERUN_STEPS,
        world=build_penn_world(),
        monitor=None,
        llm=None,
        run_store=RunStore(tmp_path / "runs"),
        seed=0,
        decide_workers=0,
    )
    for _ in range(RERUN_STEPS):
        stepper.tick()
    stepper._finish_run()
    run_dir = tmp_path / "runs" / stepper._run_id
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["seed"] == 0 and manifest["engine_sha"]
    assert not (run_dir / "cassette.jsonl").exists()
    assert not (run_dir / "run.yaml").exists()
