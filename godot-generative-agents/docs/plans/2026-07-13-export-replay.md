# Live→Replay Export (#307) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the `GameEvent` log into the #304 RunStore and add `backend/penn/export_replay.py` — a `build_replay()` + CLI that turns any persisted run back into a viewer-loadable `penn_replay.json`.

**Architecture:** Three producers/consumers around the existing store: (1) `RunStore` grows a third artifact, `<run_id>/events.jsonl`, mirroring the frames pattern (structural keys-only validation — the base env has no pydantic); (2) `PennStepper` flushes `game.events` on an **independent cursor** (the feed's `_events_seen` must keep seeing every event exactly once) with a tail flush at finish/reset for `POST /world/event` stragglers; the bake's `--persist` adds one `append_events` call; (3) a new exporter module assembles `{meta, frames, memory_streams, events}` from the store — the guardrail is dict-equality between a persisted bake's export and the bake's own file.

**Tech Stack:** Python 3.12, stdlib only in `backend/run_store.py` / `export_replay.py` (sqlite3, json, argparse, pathlib); pytest + pydantic contract models in tests only.

**Spec:** `godot-generative-agents/docs/specs/2026-07-13-export-replay.md`

## Global Constraints

- Branch: `feat/export-replay-307` off `godot-ga-main` (backend + tests only).
- No pydantic outside tests: `run_store.py`/`export_replay.py` import only stdlib + `backend.contract` constants + existing backend/engine modules.
- No changes to `api.py`, `live.py`, the viewer, the engine (`text_adventure_games/`), or `backend/exporter.py` (legacy Django format — NOT this feature's writer).
- All tests offline (mock brain, no keys); every store lives in `tmp_path`.
- Run tests from the **repo root** `/Users/yh/Documents/GitHub/agent-sandbox`.
- Format with `uv run black .` before every commit; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- The simulate-mirror byte-identity test (`test_penn_live.py::test_stepper_matches_simulate_prefix`) must stay green and untouched.

---

### Task 1: RunStore events — `append_events` / `read_events` / `_validate_event`

**Files:**
- Modify: `godot-generative-agents/backend/run_store.py`
- Test: `godot-generative-agents/tests/test_run_store.py`

**Interfaces:**
- Consumes: existing `RunStore` (`create_run`, `_validate_frame` pattern), `backend.contract.EVENT_STATE_FIELDS` = `("turn", "actor", "action", "summary", "payload")`.
- Produces: `RunStore.append_events(run_id: str, events: list[dict]) -> None` (validates every dict — all five `EVENT_STATE_FIELDS` required, nothing else, keys only; whole batch validated before anything hits disk; empty list is a no-op; unknown run raises `KeyError`); `RunStore.read_events(run_id: str) -> list[dict]` (append order; `[]` when the run has no events file; unknown run raises `KeyError`). Tasks 2–5 rely on these exact names.

- [ ] **Step 1: Write the failing tests**

Append to `godot-generative-agents/tests/test_run_store.py`, after `test_append_frame_validates_the_contract_shape` (line 103) and before the `_record` helper:

```python
EVENT = {
    "turn": 0,
    "actor": "Ada",
    "action": "world_event",
    "summary": "a siren wails",
    "payload": {},
}


def test_append_and_read_events_in_order(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    # No events yet: no file on disk, and read_events is [] -- not an error.
    assert store.read_events("run-a") == []
    assert not (tmp_path / "runs" / "run-a" / "events.jsonl").exists()
    first = [dict(EVENT, turn=0), dict(EVENT, turn=1, actor=None)]  # None: /world/event
    second = [dict(EVENT, turn=2, summary="last call")]
    store.append_events("run-a", first)
    store.append_events("run-a", [])  # a no-op, not an error
    store.append_events("run-a", second)
    assert store.read_events("run-a") == first + second


def test_append_events_validates_and_rejects_unknown_runs(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    with pytest.raises(KeyError):
        store.append_events("missing", [EVENT])
    with pytest.raises(KeyError):
        store.read_events("missing")
    with pytest.raises(ValueError):
        store.append_events("run-a", [{"turn": 0, "actor": "Ada"}])  # missing fields
    with pytest.raises(ValueError):
        store.append_events("run-a", [dict(EVENT, mood="tense")])  # unpinned field
    # A bad event anywhere in the batch keeps the WHOLE batch off disk.
    with pytest.raises(ValueError):
        store.append_events("run-a", [EVENT, "not-a-dict"])
    assert store.read_events("run-a") == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_run_store.py -q -k events`
Expected: 2 FAIL with `AttributeError: 'RunStore' object has no attribute 'read_events'`

- [ ] **Step 3: Implement**

In `godot-generative-agents/backend/run_store.py`:

3a. Change the import at line 35 to:

```python
from backend.contract import AGENT_FRAME_FIELDS, EVENT_STATE_FIELDS
```

3b. In the module docstring's layout block (lines 7–12), add one line after the `frames.jsonl` line:

```
        events.jsonl            # the run's GameEvent log (EventState dicts, #467)
```

3c. Insert a new section between the frames section (`_frames_path`, ends line 202) and the memories section (line 204):

```python
    # --- events ---------------------------------------------------------------

    def append_events(self, run_id: str, events: list[dict]) -> None:
        """Append ``GameEvent.to_primitive()`` dicts to the run's events.jsonl.

        Unlike frames there is no step == line invariant: a step can log zero
        or many events and each carries its own ``turn`` -- order is append
        order. The whole batch is validated first (#305 EventState, keys
        only), so one bad event keeps the batch off disk. An empty list is a
        no-op: a run with no events never grows a file.
        """
        path = self._events_path(run_id)
        for event in events:
            _validate_event(event)
        if not events:
            return
        with path.open("a", encoding="utf-8") as fh:
            for event in events:
                fh.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
                fh.write("\n")

    def read_events(self, run_id: str) -> list[dict]:
        """The run's persisted GameEvent log, in append order ([] when none)."""
        path = self._events_path(run_id)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def _events_path(self, run_id: str) -> Path:
        run_dir = self.root / run_id
        if not run_dir.is_dir():
            raise KeyError(f"unknown run id: {run_id}")
        return run_dir / "events.jsonl"
```

3d. Add the validator at module level, after `_validate_frame` (line 389):

```python
def _validate_event(event: dict) -> None:
    """Structural #305 EventState check: the five pinned fields, keys only.

    Same rationale as ``_validate_frame`` -- and keys only on purpose:
    ``POST /world/event`` records legitimately carry ``actor=None``.
    """
    if not isinstance(event, dict):
        raise ValueError("event must be a dict of EventState fields")
    unpinned = sorted(set(event) - set(EVENT_STATE_FIELDS))
    if unpinned:
        raise ValueError(f"event has unpinned fields: {unpinned}")
    missing = [k for k in EVENT_STATE_FIELDS if k not in event]
    if missing:
        raise ValueError(f"event is missing {missing}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_run_store.py -q`
Expected: all pass (11 existing + 2 new)

- [ ] **Step 5: Format and commit**

```bash
uv run black godot-generative-agents/backend/run_store.py godot-generative-agents/tests/test_run_store.py
git add godot-generative-agents/backend/run_store.py godot-generative-agents/tests/test_run_store.py
git commit -m "feat(backend): RunStore events — validated events.jsonl append/read (#307)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Live wiring — event-persistence cursor + tail flush in `PennStepper`

**Files:**
- Modify: `godot-generative-agents/backend/penn/serve_penn.py` (`_build` ~line 343, `_persist_tick` ~line 490, `_finish_run` ~line 510, `reset` ~line 551)
- Test: `godot-generative-agents/tests/test_penn_live.py`

**Interfaces:**
- Consumes: Task 1's `RunStore.append_events` / `read_events`; existing `self.game.events` (list of `text_adventure_games.events.GameEvent`), `self._events_seen` (the feed cursor — MUST NOT be touched), `self.run_store` / `self._run_id`.
- Produces: `PennStepper._persist_pending_events()` (no-op without a store); persisted `events.jsonl` per live run. No public API change.

- [ ] **Step 1: Write the failing tests**

In `godot-generative-agents/tests/test_penn_live.py`:

1a. Add to the imports (after the `from backend.run_store import RunStore` line, line 32):

```python
from text_adventure_games.events import GameEvent  # noqa: E402
```

1b. Add after `test_stepper_persists_frames_memories_and_finish` (line 248):

```python
def test_stepper_persists_game_events(tmp_path):
    # The #307 live wiring: GameEvents flush to events.jsonl on a cursor of
    # their own -- draining the change feed must not starve persistence --
    # and the day's close catches events logged after the final tick (the
    # POST /world/event window).
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=2, world=build_penn_world(), run_store=store)
    run_id = stepper.run_id
    stepper.tick()
    # An intervention lands between ticks (api.py's /world/event shape).
    stepper.game.events.append(
        GameEvent(stepper.game.turn, None, "world_event", summary="a siren wails")
    )
    stepper.drain_events()  # the feed reads first; persistence must still see all
    stepper.tick()
    assert store.read_events(run_id) == [
        e.to_primitive() for e in stepper.game.events
    ]
    assert "a siren wails" in {e["summary"] for e in store.read_events(run_id)}
    # A straggler after the last tick is flushed by the day's close.
    stepper.game.events.append(
        GameEvent(stepper.game.turn, None, "world_event", summary="last call")
    )
    assert stepper.tick() is None  # end of day -> _finish_run tail-flushes
    assert store.read_events(run_id) == [
        e.to_primitive() for e in stepper.game.events
    ]
    assert store.read_events(run_id)[-1]["summary"] == "last call"
```

1c. Extend `test_stepper_reset_closes_the_run_and_opens_a_new_one` (line 250): replace its body between `first = stepper.run_id` and `stepper.reset()` so the test reads:

```python
def test_stepper_reset_closes_the_run_and_opens_a_new_one(tmp_path):
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=3, world=build_penn_world(), run_store=store)
    first = stepper.run_id
    stepper.tick()
    # An event logged after the tick still belongs to the first run --
    # reset() tail-flushes before closing the row (#307).
    stepper.game.events.append(
        GameEvent(stepper.game.turn, None, "world_event", summary="bell rings")
    )
    stepper.reset()
    second = stepper.run_id
    assert first != second
    assert store.get_run(first)["status"] == "reset"
    assert store.get_run(second)["status"] == "running"
    assert {r["id"] for r in store.list_runs()} == {first, second}
    assert store.read_events(first)[-1]["summary"] == "bell rings"
    assert store.read_events(second) == []  # the new day starts clean
    # The default stays storeless (and byte-identical -- the simulate-mirror
    # test above pins it): a bare stepper has no run id.
    assert PennStepper(num_steps=1, world=build_penn_world()).run_id is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_penn_live.py -q -k "game_events or reset_closes"`
Expected: both FAIL — `read_events` returns `[]` (nothing persists events yet)

- [ ] **Step 3: Implement**

In `godot-generative-agents/backend/penn/serve_penn.py`:

3a. In `_build`, directly after `self._events_seen = 0` (line 343), add:

```python
        # ...and how much the #307 persistence hook has flushed to the store.
        # Its own cursor: --persist must never steal rows from the feed above.
        self._persist_events_seen = 0
```

3b. In `_persist_tick` (line 490), insert one call between the memory-sync loop and the `self.run_store.update_run(...)` call:

```python
        self._persist_pending_events()
```

3c. Add the helper method directly after `_persist_tick`:

```python
    def _persist_pending_events(self) -> None:
        # GameEvents logged since the last flush -> events.jsonl (#307).
        # Also called by _finish_run() and reset(): POST /world/event can
        # land an event between the last tick and the day's close, where
        # the per-tick flush would never see it.
        if self.run_store is None or self._run_id is None:
            return
        pending = self.game.events[self._persist_events_seen :]
        if pending:
            self.run_store.append_events(
                self._run_id, [event.to_primitive() for event in pending]
            )
        self._persist_events_seen = len(self.game.events)
```

3d. In `_finish_run` (line 510), add a tail flush as the first statement (before the existing `if` guard — the flush is idempotent on its own, the status flip keeps its guard):

```python
    def _finish_run(self) -> None:
        # Idempotent: the live loop keeps ticking a finished day (every tick
        # returns None) and only the first one flips the status. The tail
        # flush catches events logged after the final tick (#307).
        self._persist_pending_events()
        if (
```

3e. In `reset()` (line 551), add the same tail flush as the first statement of the method body (before the `if self.run_store is not None ...` block that marks the run `"reset"`):

```python
        self._persist_pending_events()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_penn_live.py -q`
Expected: all pass — including the untouched `test_stepper_matches_simulate_prefix` (byte-identity) and `test_stepper_persists_frames_memories_and_finish`

- [ ] **Step 5: Format and commit**

```bash
uv run black godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_penn_live.py
git add godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_penn_live.py
git commit -m "feat(backend): persist live GameEvents — independent cursor + tail flush (#307)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Bake wiring — persist the bake's events

**Files:**
- Modify: `godot-generative-agents/backend/penn/generate_penn_replay.py` (the `--persist` block, lines 265–275)
- Test: `godot-generative-agents/tests/test_event_records.py` (extend `test_persisted_bake_round_trips_the_store`, line 172)

**Interfaces:**
- Consumes: Task 1's `store.append_events`; the existing `replay["events"]` (filled by `simulate(out_events=...)`).
- Produces: a persisted bake whose store copy carries the events too — Task 5's round-trip equality depends on it.

- [ ] **Step 1: Write the failing test**

In `test_persisted_bake_round_trips_the_store`, after the frames equality (line 204: `assert store.read_frames(run["id"]) == replay["frames"]`), add:

```python
    # Events: the store's copy == the file's GameEvent log (#307).
    assert store.read_events(run["id"]) == replay["events"]
```

- [ ] **Step 2: Run it to verify the current state**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py::test_persisted_bake_round_trips_the_store -q`
Expected: PASSES VACUOUSLY if the mock bake logs zero events (`[] == []`) — or FAILS if it logs any. Either way proceed: the wiring line below is what makes the equality *guaranteed* rather than accidental, and the non-empty case is pinned by Task 2's live test.

- [ ] **Step 3: Implement**

In `generate_penn_replay.py`'s persist block, insert between the `record_memories` loop (line 271) and `store.update_run(...)` (line 272):

```python
        store.append_events(run_id, replay["events"])
```

And update the closing print (line 275) to mention it:

```python
        print(f"Persisted run {run_id} to {store.root} (frames + events + sim.db).")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py -q`
Expected: all pass

- [ ] **Step 5: Format and commit**

```bash
uv run black godot-generative-agents/backend/penn/generate_penn_replay.py godot-generative-agents/tests/test_event_records.py
git add godot-generative-agents/backend/penn/generate_penn_replay.py godot-generative-agents/tests/test_event_records.py
git commit -m "feat(backend): bake --persist records the GameEvent log too (#307)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: The exporter — `backend/penn/export_replay.py` (`build_replay` + CLI)

**Files:**
- Create: `godot-generative-agents/backend/penn/export_replay.py`
- Create: `godot-generative-agents/tests/test_export_replay.py`

**Interfaces:**
- Consumes: `RunStore.get_run/list_runs/read_frames/read_events/memories_for`, `backend.run_store.DEFAULT_RUNS_DIR`.
- Produces: `build_replay(store: RunStore, run_id: str) -> dict` (the four-key #305 `Replay` dict; `ValueError` on unknown id) and `main() -> int` (argv CLI, exit 0 ok / 2 on empty store or unknown id). Task 5 imports both.

- [ ] **Step 1: Write the failing tests**

Create `godot-generative-agents/tests/test_export_replay.py`:

```python
"""Live->replay exporter unit tests (issue #307). Synthetic stores in tmp_path;
the bake-based end-to-end equality lives in test_event_records.py."""

import json
import sys

import pytest

from backend.penn.export_replay import build_replay, main
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


def _seed_run(store, run_id):
    store.create_run(MANIFEST, run_id=run_id)
    for i in range(2):
        store.append_frame(run_id, i, FRAME)
    store.append_events(run_id, [EVENT])
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


def test_build_replay_assembles_the_four_keys(tmp_path):
    store = RunStore(tmp_path / "runs")
    run_id = _seed_run(store, "run-a")
    replay = build_replay(store, run_id)
    # Key order matches the bake's file exactly (#305 Replay).
    assert list(replay) == ["meta", "frames", "memory_streams", "events"]
    # A live manifest has no steps -> filled from the frame count; the llm
    # key rides along untouched.
    assert replay["meta"]["steps"] == 2
    assert replay["meta"]["llm"] == MANIFEST["llm"]
    assert replay["frames"] == [FRAME, FRAME]
    assert replay["events"] == [EVENT]
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


def test_cli_exports_the_newest_run_by_default(tmp_path, monkeypatch, capsys):
    store = RunStore(tmp_path / "runs")
    _seed_run(store, "run-a")
    _seed_run(store, "run-b")  # same-second create -> the id tiebreak picks run-b
    monkeypatch.setattr(
        sys, "argv", ["export_replay", "--runs-dir", str(tmp_path / "runs")]
    )
    assert main() == 0
    out = tmp_path / "runs" / "run-b" / "penn_replay.json"
    assert json.loads(out.read_text()) == build_replay(store, "run-b")
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
    assert json.loads(out.read_text()) == build_replay(store, "run-a")


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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_export_replay.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'backend.penn.export_replay'`

- [ ] **Step 3: Implement**

Create `godot-generative-agents/backend/penn/export_replay.py`:

```python
"""Export a persisted run back into ``penn_replay.json`` (issue #307).

The live->replay bridge: ``serve_penn --persist`` (or a persisted bake)
records a run into the #304 RunStore; this module reads it back out as the
exact four-key replay the bake writes -- ``{meta, frames, memory_streams,
events}``, every shape pinned by the #305 contract -- so a recorded live run
re-opens in the Godot viewer ("Open a local replay file" in the landing
menu) with bubbles, memory streams, and timeline markers intact.

    uv run python -m backend.penn.export_replay              # newest run
    uv run python -m backend.penn.export_replay <run_id> --out replay.json

Read-side only: no simulation, no store writes. (``backend/exporter.py`` is
NOT this writer -- it emits the legacy Django folder format.)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.run_store import DEFAULT_RUNS_DIR, RunStore


def build_replay(store: RunStore, run_id: str) -> dict:
    """Assemble the #305 ``Replay`` dict for *run_id* from the store.

    ``meta`` is the run's manifest with ``steps`` filled from the frame
    count when absent -- a live manifest doesn't know it up front, while a
    bake's already does and must pass through untouched (the round-trip
    test pins exported == baked file). Raises ``ValueError`` on an unknown
    run id.
    """
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"unknown run id: {run_id}")
    meta = run["manifest"]
    frames = store.read_frames(run_id)
    meta.setdefault("steps", len(frames))
    return {
        "meta": meta,
        "frames": frames,
        "memory_streams": {
            p["name"]: store.memories_for(run_id, p["name"])
            for p in meta["personas"]
        },
        "events": store.read_events(run_id),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export a persisted run (#304 RunStore) to penn_replay.json."
    )
    ap.add_argument("run_id", nargs="?", default=None, help="default: the newest run")
    ap.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR),
        help="RunStore root (default: godot-generative-agents/runs/)",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="output path (default: <runs-dir>/<run_id>/penn_replay.json)",
    )
    args = ap.parse_args()

    store = RunStore(args.runs_dir)
    run_id = args.run_id
    if run_id is None:
        runs = store.list_runs()
        if not runs:
            print(f"No runs in {store.root} -- record one with --persist first.")
            return 2
        run_id = runs[0]["id"]
    try:
        replay = build_replay(store, run_id)
    except ValueError as exc:
        print(exc)
        return 2

    out = Path(args.out) if args.out else store.root / run_id / "penn_replay.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(replay, fh, ensure_ascii=False)
    print(
        f"Wrote {out.resolve()} ({len(replay['frames'])} steps, "
        f"{len(replay['meta']['personas'])} personas, "
        f"{len(replay['events'])} events). Open it in the viewer via "
        '"Open a local replay file".'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_export_replay.py -q`
Expected: 6 pass

- [ ] **Step 5: Format and commit**

```bash
uv run black godot-generative-agents/backend/penn/export_replay.py godot-generative-agents/tests/test_export_replay.py
git add godot-generative-agents/backend/penn/export_replay.py godot-generative-agents/tests/test_export_replay.py
git commit -m "feat(backend): export_replay — RunStore run -> penn_replay.json, build_replay + CLI (#307)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: End-to-end guardrail + docs

**Files:**
- Modify: `godot-generative-agents/tests/test_event_records.py` (extend `test_persisted_bake_round_trips_the_store`)
- Modify: `godot-generative-agents/backend/README.md` (lines 1205–1208 and the `## RunStore: durable runs (#304)` section, lines 1210–1227)

**Interfaces:**
- Consumes: Task 4's `build_replay` / `main`; `backend.contract_models.Replay` (pydantic — test env only).
- Produces: the bridge's strongest guarantee — a persisted bake's export equals the bake's own file, dict-for-dict, and validates against the pinned contract.

- [ ] **Step 1: Write the failing test additions**

At the END of `test_persisted_bake_round_trips_the_store` (after the query-parity assert, line 219), add:

```python
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
```

- [ ] **Step 2: Run it to verify it passes (it should — the machinery all exists)**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py::test_persisted_bake_round_trips_the_store -q`
Expected: PASS. If `exported == replay` fails, the diff is a real fidelity bug in Tasks 1–4 — fix THAT, never loosen this assert.

- [ ] **Step 3: Update the docs**

In `godot-generative-agents/backend/README.md`:

3a. Replace lines 1205–1208 (the paragraph starting "The RunStore (`backend/run_store.py`, #304) writes..."):

```markdown
The RunStore (`backend/run_store.py`, #304) writes `frames.jsonl` lines in the
`dict[str, AgentFrame]` shape and `events.jsonl` lines in the `EventState`
shape — both checked structurally at write time, since the base env has no
pydantic — and the #307 exporter (`backend/penn/export_replay.py`) emits a
full `Replay`-shaped file back out of the store.
```

3b. In the `## RunStore: durable runs (#304)` section, add one line to the layout block after the `frames.jsonl` line:

```
      <run_id>/events.jsonl              # the run's GameEvent log (#467 EventState)
```

3c. Replace the section's final two sentences (from "Reads: `read_frames`, ..." through "...#306 run-lifecycle endpoints.") with:

```markdown
Reads: `read_frames`, `read_events`, `memories_for` (the lean wire
projection), and `query_memories`, which rehydrates rows into engine
`MemoryRecord`s and delegates to `AgentMemory.retrieve` — store queries score
exactly like the sim. The #307 live→replay bridge reads all of it back out:

    uv run python -m backend.penn.export_replay              # newest run
    uv run python -m backend.penn.export_replay <run_id> --out my_run.json

writes a `penn_replay.json` (default: beside the run, in
`<runs-dir>/<run_id>/`) that the viewer opens via the landing menu's "Open a
local replay file" — a recorded real-LLM day replays offline with bubbles,
memory streams, and timeline markers intact. A round-trip test pins that a
persisted bake's export equals its replay file exactly. Consumers on deck:
the #306 run-lifecycle endpoints.
```

- [ ] **Step 4: Run the full offline gate**

Run: `uv run pytest godot-generative-agents/tests/ -q`
Expected: all pass, no skips beyond the suite's usual ones
Run: `uv run black --check .`
Expected: clean (nothing reformatted)

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/tests/test_event_records.py godot-generative-agents/backend/README.md
git commit -m "test(backend): pin exported == baked replay + contract validation; README exporter docs (#307)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
