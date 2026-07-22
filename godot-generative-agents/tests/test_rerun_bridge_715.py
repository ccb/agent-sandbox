"""Re-run bridge (#715): a persisted run records a cassette + seed + engine sha,
and re-runs offline byte-identically. Uses --brain scripted -- free, key-free,
deterministic, and (unlike --brain mock) it routes through the real client seam
the cassette taps."""

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from text_adventure_games.transcript import RunRecord, file_sha256

# The Penn sim modules live in the Godot tree and are imported the way the
# scripts import each other -- flat, off the sim directory (serve_penn.py does
# `from scripted_brain import ...`), NOT as backend.penn.serve_penn. This
# mirrors godot-generative-agents/tests/test_penn_live.py:26-47. `backend.*`
# and `text_adventure_games.*` still import normally (editable install +
# PYTHONPATH=.:godot-generative-agents in the run command).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SIM_DIR = _REPO_ROOT / "godot-generative-agents" / "backend" / "penn"
sys.path.insert(0, str(_SIM_DIR))

from serve_penn import (  # noqa: E402
    SCRIPTED,
    PennStepper,
    ReproResult,
    _GameProxy,
    reproduce_run,
)
from penn_world import build_penn_world  # noqa: E402
from backend.api import create_app  # noqa: E402
from backend.run_store import RunStore  # noqa: E402


def _GameProxy_for(stepper):
    return _GameProxy(stepper)


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


def _record_a_run(tmp_path):
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
    for _ in range(RERUN_STEPS):
        stepper.tick()
    stepper._finish_run()
    return store, stepper._run_id


def test_rerun_is_byte_identical(tmp_path):
    store, run_id = _record_a_run(tmp_path)
    result = reproduce_run(store, run_id)
    assert isinstance(result, ReproResult)
    assert result.match is True
    assert result.first_divergence is None
    assert result.steps == RERUN_STEPS


def test_rerun_uses_a_replayclient_not_a_real_client(tmp_path):
    # Zero-network proof: the re-run brain is a ReplayClient (offline by
    # construction), and create_llm_client is never reached.
    store, run_id = _record_a_run(tmp_path)
    import serve_penn as sp

    def _boom(*a, **k):
        raise AssertionError("re-run must not build a live client")

    orig = sp.create_llm_client
    sp.create_llm_client = _boom
    try:
        result = reproduce_run(store, run_id)
    finally:
        sp.create_llm_client = orig
    assert result.match is True


def test_rerun_unknown_run_raises_keyerror(tmp_path):
    store = RunStore(tmp_path / "runs")
    with pytest.raises(KeyError):
        reproduce_run(store, "run-does-not-exist")


def test_rerun_without_cassette_raises(tmp_path):
    # A mock run has no cassette -> not reproducible via the bridge.
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(
        num_steps=RERUN_STEPS,
        world=build_penn_world(),
        monitor=None,
        llm=None,
        run_store=store,
        seed=0,
        decide_workers=0,
    )
    for _ in range(RERUN_STEPS):
        stepper.tick()
    stepper._finish_run()
    with pytest.raises(ValueError, match="no cassette"):
        reproduce_run(store, stepper._run_id)


def test_rerun_reports_divergence_instead_of_crashing_on_a_cassette_miss(tmp_path):
    # A re-run that asks for a response the cassette never recorded IS a
    # divergence (e.g. an engine change altered a decide prompt so the request
    # key no longer matches), not a crash. reproduce_run must report
    # match=False -- NOT let CassetteMiss (neither KeyError nor ValueError)
    # escape, which the CLI/HTTP handlers would surface as a traceback / 500.
    store, run_id = _record_a_run(tmp_path)
    # Blank the cassette in place: the file still exists (so we clear the
    # no-cassette guard), but the first recorded decide now misses.
    open(tmp_path / "runs" / run_id / "cassette.jsonl", "w").close()

    result = reproduce_run(store, run_id)  # must not raise
    assert result.match is False
    assert result.first_divergence is not None


def test_http_rerun_reports_a_diverged_run_as_200_not_500(tmp_path):
    # The route maps only KeyError->404 / ValueError->409, so before the fix a
    # CassetteMiss on a diverged run 500'd. reproduce_run now folds the miss
    # into the verdict, so the route returns 200 with match=False.
    store, run_id = _record_a_run(tmp_path)
    open(tmp_path / "runs" / run_id / "cassette.jsonl", "w").close()
    stepper = PennStepper(
        num_steps=RERUN_STEPS,
        world=build_penn_world(),
        monitor=None,
        llm=SCRIPTED,
        run_store=store,
        seed=0,
        decide_workers=0,
    )
    app = create_app(_GameProxy_for(stepper), stepper=stepper, start_paused=True)
    client = TestClient(app)
    resp = client.post(f"/runs/{run_id}/rerun")
    assert resp.status_code == 200
    assert resp.json()["match"] is False


def test_manifest_persists_resolved_cognition_config(tmp_path):
    # Finding 1 (#715 review): react/plan_mode were never coupled to the
    # SCRIPTED sentinel the way cognition_tools is (serve_penn.py:540), so a
    # run recorded with --react must persist that fact for a re-run to
    # reconstruct it -- not just inherit it from scripted's hard-wired default.
    stepper = PennStepper(
        num_steps=RERUN_STEPS,
        world=build_penn_world(),
        monitor=None,
        llm=SCRIPTED,
        run_store=RunStore(tmp_path / "runs"),
        seed=0,
        decide_workers=0,
        react=True,
    )
    run_id = stepper._run_id
    manifest = json.loads((tmp_path / "runs" / run_id / "manifest.json").read_text())
    assert manifest["react"] is True
    assert manifest["cognition_tools"] is True  # resolved: scripted forces it on
    assert manifest["plan_mode"] == "schedule"


def test_rerun_of_a_react_run_reproduces(tmp_path):
    # Finding 1 (#715 review): a run recorded with --react must re-run with
    # react reconstructed from the manifest, not the DEFAULT config -- else
    # the offered tool set / decide path can diverge (CassetteMiss or
    # match=False). Exercises the config-passing re-run path end to end.
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(
        num_steps=RERUN_STEPS,
        world=build_penn_world(),
        monitor=None,
        llm=SCRIPTED,
        run_store=store,
        seed=0,
        decide_workers=0,
        react=True,
    )
    for _ in range(RERUN_STEPS):
        stepper.tick()
    stepper._finish_run()

    result = reproduce_run(store, stepper._run_id)
    assert result.match is True
    assert result.first_divergence is None
    assert result.steps == RERUN_STEPS


def test_reproduce_run_rejects_a_plan_mode_llm_run(tmp_path):
    # Task 4 review, Addition A: a run recorded with --plan llm makes the
    # re-run PennStepper's OWN guard raise SystemExit (llm=None is never
    # "paid") before reproduce_run's replay branch ever executes. SystemExit
    # is a BaseException that, inside the HTTP route's run_in_executor worker
    # thread, is silently swallowed by threading's bootstrap and HANGS the
    # request instead of failing cleanly. reproduce_run must refuse this case
    # itself, with its established ValueError vocabulary (the route maps
    # ValueError -> 409, the CLI catches it too).
    store, run_id = _record_a_run(tmp_path)
    manifest = store.get_run(run_id)["manifest"]
    manifest["plan_mode"] = "llm"
    con = sqlite3.connect(store.root / "sim.db")
    con.execute(
        "UPDATE runs SET manifest = ? WHERE id = ?",
        (json.dumps(manifest), run_id),
    )
    con.commit()
    con.close()

    with pytest.raises(ValueError, match="plan llm"):
        reproduce_run(store, run_id)


def test_reproduce_run_threads_manifest_config_into_the_rerun_stepper(
    tmp_path, monkeypatch
):
    # Prove reproduce_run threads the reconstructed config (react/
    # cognition_tools/plan_mode, Finding 1) into the re-run PennStepper's
    # kwargs directly -- independent of whether maybe_react actually fires
    # in a short run (emergent, not guaranteed).
    store = RunStore(tmp_path / "runs")
    rec = PennStepper(
        num_steps=RERUN_STEPS,
        world=build_penn_world(),
        monitor=None,
        llm=SCRIPTED,
        run_store=store,
        seed=0,
        decide_workers=0,
        react=True,
    )
    run_id = rec._run_id
    for _ in range(RERUN_STEPS):
        rec.tick()
    rec._finish_run()

    captured = {}
    orig = PennStepper.__init__

    def spy(self, *a, **kw):
        captured.update(kw)
        return orig(self, *a, **kw)

    monkeypatch.setattr(PennStepper, "__init__", spy)
    reproduce_run(store, run_id)
    assert captured["react"] is True
    assert captured["cognition_tools"] is True  # scripted forces it on
    assert captured["plan_mode"] == "schedule"


def test_http_rerun_route_reports_match(tmp_path):
    store, run_id = _record_a_run(tmp_path)
    stepper = PennStepper(
        num_steps=RERUN_STEPS,
        world=build_penn_world(),
        monitor=None,
        llm=SCRIPTED,
        run_store=store,
        seed=0,
        decide_workers=0,
    )
    app = create_app(_GameProxy_for(stepper), stepper=stepper, start_paused=True)
    client = TestClient(app)
    resp = client.post(f"/runs/{run_id}/rerun")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_id
    assert body["match"] is True
    assert body["steps"] == RERUN_STEPS


def test_http_rerun_unknown_run_is_404(tmp_path):
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
    app = create_app(_GameProxy_for(stepper), stepper=stepper, start_paused=True)
    client = TestClient(app)
    resp = client.post("/runs/run-nope/rerun")
    assert resp.status_code == 404
    # Proves the route actually ran and 404'd on an unknown run id -- not
    # FastAPI's generic "no matching route" 404 (a store exists here, so this
    # exercises reproduce_run's KeyError -> the route's KeyError handler).
    assert "unknown run id" in resp.json()["detail"]


# A self-contained snippet: record a short scripted run, re-run it, and print
# "<match>:<sha-of-rerun-frames>". Run under three PYTHONHASHSEEDs; all three
# must report match=True AND the same frame hash -> reproduction is stable
# across processes, not just within one (mirrors #545's determinism guard).
_HASHSEED_SNIPPET = textwrap.dedent("""
    import hashlib, json, sys, tempfile
    from pathlib import Path
    sys.path.insert(0, str(Path.cwd() / "godot-generative-agents" / "backend" / "penn"))
    from serve_penn import SCRIPTED, PennStepper, reproduce_run
    from penn_world import build_penn_world
    from backend.run_store import RunStore

    STEPS = 6
    tmp = tempfile.mkdtemp()
    store = RunStore(tmp + "/runs")
    s = PennStepper(num_steps=STEPS, world=build_penn_world(), monitor=None,
                    llm=SCRIPTED, run_store=store, seed=0, decide_workers=0)
    run_id = s._run_id
    for _ in range(STEPS):
        s.tick()
    s._finish_run()
    result = reproduce_run(store, run_id)
    frames = store.read_frames(run_id)
    digest = hashlib.sha256(
        json.dumps(frames, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    print(f"{result.match}:{digest}")
    """)


def test_rerun_is_stable_across_hashseeds():
    env = dict(os.environ)
    env["PYTHONPATH"] = ".:godot-generative-agents"
    outputs = []
    for seed in ("0", "1", "2"):
        env["PYTHONHASHSEED"] = seed
        out = (
            subprocess.run(
                [sys.executable, "-c", _HASHSEED_SNIPPET],
                capture_output=True,
                text=True,
                env=env,
                # Pin cwd to the repo root so the snippet's Path.cwd()-relative
                # import path and the cwd-relative PYTHONPATH resolve no matter
                # what directory pytest was invoked from (the rest of this file
                # keys off Path(__file__), which is already cwd-independent).
                cwd=str(_REPO_ROOT),
                check=True,
            )
            .stdout.strip()
            .splitlines()[-1]
        )
        outputs.append(out)
    # Every run reproduced, and produced the identical frame hash.
    assert all(o.startswith("True:") for o in outputs), outputs
    assert len(set(outputs)) == 1, outputs
