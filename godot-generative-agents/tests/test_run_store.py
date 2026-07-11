"""RunStore unit tests (issue #304). Fully offline; every store lives in tmp_path."""

import json
import re

import pytest

from backend.run_store import RunStore

MANIFEST = {
    "schema_version": 1,
    "personas": [{"name": "Ada"}],
    "llm": {"provider": "anthropic", "model": "claude-haiku-4-5"},
}


def test_create_get_list_roundtrip(tmp_path):
    store = RunStore(tmp_path / "runs")
    a = store.create_run(MANIFEST, run_id="run-a")
    b = store.create_run(dict(MANIFEST, llm=None), run_id="run-b")
    assert (a, b) == ("run-a", "run-b")
    run = store.get_run("run-a")
    assert run["manifest"] == MANIFEST
    assert run["status"] == "running"
    assert run["model"] == "claude-haiku-4-5"
    assert run["cost"] == 0.0 and run["steps"] == 0
    assert store.get_run("run-b")["model"] is None  # mock brain -> no model
    assert store.get_run("missing") is None
    # Newest first; same-second creations fall back to the id tiebreak.
    assert [r["id"] for r in store.list_runs()] == ["run-b", "run-a"]
    # The on-disk mirrors exist: manifest.json + an empty frames.jsonl.
    assert (tmp_path / "runs" / "run-a" / "frames.jsonl").read_text() == ""
    on_disk = json.loads((tmp_path / "runs" / "run-a" / "manifest.json").read_text())
    assert on_disk == MANIFEST


def test_create_run_rejects_duplicate_id(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    with pytest.raises(ValueError):
        store.create_run(MANIFEST, run_id="run-a")


def test_default_run_id_shape(tmp_path):
    store = RunStore(tmp_path / "runs")
    run_id = store.create_run(MANIFEST)
    assert re.fullmatch(r"run-\d{8}-\d{6}-[0-9a-f]{6}", run_id)


def test_update_run_partial_and_unknown(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    store.update_run("run-a", status="finished")
    store.update_run("run-a", cost=0.25, steps=40)
    run = store.get_run("run-a")
    assert (run["status"], run["cost"], run["steps"]) == ("finished", 0.25, 40)
    with pytest.raises(KeyError):
        store.update_run("missing", status="reset")
