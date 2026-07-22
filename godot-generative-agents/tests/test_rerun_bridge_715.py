"""Re-run bridge (#715): a persisted run records a cassette + seed + engine sha,
and re-runs offline byte-identically. Uses --brain scripted -- free, key-free,
deterministic, and (unlike --brain mock) it routes through the real client seam
the cassette taps."""

import json
import sys
from pathlib import Path

import pytest

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
