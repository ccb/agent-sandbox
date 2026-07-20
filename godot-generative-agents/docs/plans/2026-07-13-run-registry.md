# Run Registry (#306, registry half) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four HTTP endpoints over the #304 RunStore — list the run history, fetch a run, download its #307 replay, delete a run — plus the `RunStore.delete_run()` they need.

**Architecture:** The store is probed off the stepper per request (`getattr(stepper, "run_store", None)` — the `ledger`/`drain_events` idiom), so `api.py` gains no constructor surface and a storeless server degrades to `available: false` / 404s. `delete_run` removes the row + memories in one transaction, then sweeps the directory (`ignore_errors=True` — the row is the source of truth). The replay endpoint lazy-imports `backend.penn.export_replay.build_replay` (flagged in the spec: Penn is the only replay dialect today).

**Tech Stack:** Python 3.12 stdlib (`shutil` joins run_store's imports); fastapi TestClient in tests (already importorskip-gated in `test_live_seam.py`).

**Spec:** `godot-generative-agents/docs/specs/2026-07-13-run-registry.md` (committed 08d5d0d)

## Global Constraints

- Branch: `feat/run-registry-306` off `godot-ga-main`; PR targets `godot-ga-main`.
- Only four files change across the plan: `godot-generative-agents/backend/run_store.py`, `godot-generative-agents/backend/api.py`, `godot-generative-agents/tests/test_run_store.py`, `godot-generative-agents/tests/test_live_seam.py`.
- No engine change, no root `tests/` change, no viewer/web change, no `create_app` signature change.
- `run_store.py` stays stdlib-only (no pydantic, no fastapi).
- Status codes exactly: 404 unknown-id-or-no-store on every id route; 409 deleting the current live run; `GET /runs` never errors (`available: false` shape when storeless).
- Run tests from the repo root; `uv run black .` before every commit; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Never `git add -A` / `git add .` — add the named files explicitly.

---

### Task 1: `RunStore.delete_run()`

**Files:**
- Modify: `godot-generative-agents/backend/run_store.py` (imports ~line 29; new method after `update_run`/`_run_row`, i.e. at the end of the `# --- runs ---` section ~line 171)
- Test: `godot-generative-agents/tests/test_run_store.py`

**Interfaces:**
- Consumes: existing `_db()` transaction contextmanager, `update_run`'s KeyError precedent.
- Produces: `RunStore.delete_run(run_id: str) -> None` — Task 2's DELETE endpoint calls it and maps `KeyError` → 404.

- [ ] **Step 1: Write the failing test**

Append to `godot-generative-agents/tests/test_run_store.py` (after the events tests, before the `_record` helper — `MANIFEST`, `FRAME`, `_record` already exist in the file):

```python
def test_delete_run_removes_row_memories_and_dir(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    store.create_run(MANIFEST, run_id="run-b")
    store.append_frame("run-a", 0, FRAME)
    store.record_memories("run-a", "Ada", [_record(0, "saw a book")])
    store.record_memories("run-b", "Ada", [_record(0, "kept")])
    store.delete_run("run-a")
    assert store.get_run("run-a") is None
    assert not (tmp_path / "runs" / "run-a").exists()
    assert store.last_memory_id("run-a", "Ada") == -1  # memories rows gone
    # Nothing else was touched: run-b's row, dir, and memories survive.
    assert store.get_run("run-b") is not None
    assert (tmp_path / "runs" / "run-b" / "frames.jsonl").exists()
    assert store.last_memory_id("run-b", "Ada") == 0
    # Idempotence is NOT silent: a second delete (or an unknown id) raises.
    with pytest.raises(KeyError):
        store.delete_run("run-a")
```

Place this test at the END of the file (after the memory/query tests), so the `_record` helper it uses is defined above it.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_run_store.py::test_delete_run_removes_row_memories_and_dir -v`
Expected: FAIL with `AttributeError: 'RunStore' object has no attribute 'delete_run'`

- [ ] **Step 3: Implement**

3a. Add `import shutil` to `run_store.py`'s imports (alphabetical: after `import sqlite3`... actually between `secrets` and `sqlite3` per alphabetical order — match the existing sorted block: `json`, `secrets`, `shutil`, `sqlite3`, `struct`).

3b. Add the method at the end of the runs section (after `_run_row`, before the `# --- frames ---` banner):

```python
    def delete_run(self, run_id: str) -> None:
        """Remove a run everywhere: its row, its memories, its directory.

        The row is the source of truth, so it and the memories go first in
        one transaction; the directory sweep ignores errors -- a half-removed
        dir can be re-swept, but a lingering row would resurrect the run in
        every listing. Unknown id raises KeyError (the update_run precedent).
        Refusing to delete the CURRENT live run is the API layer's job (409)
        -- the store itself has no notion of "live".
        """
        with self._db() as con:
            cur = con.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            if cur.rowcount == 0:
                raise KeyError(f"unknown run id: {run_id}")
            con.execute("DELETE FROM memories WHERE run_id = ?", (run_id,))
        shutil.rmtree(self.root / run_id, ignore_errors=True)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest godot-generative-agents/tests/test_run_store.py -q`
Expected: all pass (existing 13 + 1 new = 14).

- [ ] **Step 5: Format and commit**

```bash
uv run black godot-generative-agents/backend/run_store.py godot-generative-agents/tests/test_run_store.py
git add godot-generative-agents/backend/run_store.py godot-generative-agents/tests/test_run_store.py
git commit -m "feat(backend): RunStore.delete_run — row + memories + directory (#306)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: The four registry endpoints

**Files:**
- Modify: `godot-generative-agents/backend/api.py` (insert the block after the `/usage` handler ends and before `@app.post("/command", ...)` — locate by content)
- Test: `godot-generative-agents/tests/test_live_seam.py`

**Interfaces:**
- Consumes: Task 1's `delete_run` (KeyError on unknown); `store.list_runs()/get_run()`; `backend.penn.export_replay.build_replay(store, run_id)` (#307, lazy import); create_app's in-scope `stepper`, `lock`, `require_auth`, `HTTPException` (all already used by neighboring handlers).
- Produces: `GET /runs`, `GET /runs/{run_id}`, `GET /runs/{run_id}/replay`, `DELETE /runs/{run_id}` — the contract the future web run-browser consumes.

- [ ] **Step 1: Write the failing tests**

Append to `godot-generative-agents/tests/test_live_seam.py`:

```python
# --- run registry (#306) -----------------------------------------------------


def _stepper_with_store(tmp_path):
    """A fake live stepper carrying a real store with one finished and one
    'live' run. Ids chosen so the same-second id-DESC tiebreak lists the
    live run first (list_runs orders by created DESC, id DESC)."""
    from backend.run_store import RunStore

    store = RunStore(tmp_path / "runs")
    manifest = {"schema_version": 1, "personas": [{"name": "a"}], "llm": None}
    store.create_run(manifest, run_id="run-1-old")
    store.append_frame(
        "run-1-old", 0, {"a": {"x": 0, "y": 0, "act": "walk", "e": "@"}}
    )
    store.update_run("run-1-old", status="finished", steps=1)
    store.create_run(manifest, run_id="run-2-live")
    stepper = _walker()
    stepper.run_store = store
    stepper.run_id = "run-2-live"
    return stepper, store


def test_run_registry_lists_gets_exports_and_deletes(tmp_path):
    stepper, store = _stepper_with_store(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        listing = client.get("/runs").json()
        assert listing["available"] is True
        assert listing["current"] == "run-2-live"
        assert [r["id"] for r in listing["runs"]] == ["run-2-live", "run-1-old"]
        assert all("manifest" not in r for r in listing["runs"])
        row = client.get("/runs/run-1-old").json()
        assert row["manifest"]["personas"] == [{"name": "a"}]
        assert row["status"] == "finished"
        assert row["current"] is False
        from backend.penn.export_replay import build_replay

        assert client.get("/runs/run-1-old/replay").json() == build_replay(
            store, "run-1-old"
        )
        assert client.get("/runs/missing").status_code == 404
        assert client.get("/runs/missing/replay").status_code == 404
        assert client.delete("/runs/run-2-live").status_code == 409  # live run
        assert client.delete("/runs/run-1-old").json() == {
            "ok": True,
            "deleted": "run-1-old",
        }
        assert client.get("/runs/run-1-old").status_code == 404


def test_run_registry_without_a_store_is_available_false():
    with _live_client(_walker(), start_paused=True) as client:
        assert client.get("/runs").json() == {
            "available": False,
            "current": None,
            "runs": [],
        }
        assert client.get("/runs/any").status_code == 404
        assert client.get("/runs/any/replay").status_code == 404
        assert client.delete("/runs/any").status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_live_seam.py -q -k registry`
Expected: both FAIL with 404s from FastAPI (routes don't exist yet — `/runs` returns 404, so `.json()` shape asserts fail).

- [ ] **Step 3: Implement**

In `godot-generative-agents/backend/api.py`, insert after the `/usage` handler's `return summary` (and its enclosing function) and before `@app.post("/command", response_model=CommandResponse)`:

```python
    # ---------------------------------------------------------- run registry
    # The #306 registry half: browse/fetch/export/delete the #304 RunStore's
    # run history. The store is probed off the stepper per request (the
    # ledger/run_usage idiom), so a storeless server -- no --persist, or no
    # stepper at all -- answers available:false here and 404 on every id
    # route instead of erroring. Create/resume stay with #306's second half.

    def _run_store():
        return getattr(stepper, "run_store", None)

    def _current_run_id():
        return getattr(stepper, "run_id", None)

    @app.get("/runs")
    def runs_index(_: None = Depends(require_auth)) -> dict:
        """The run history, newest first: row summaries WITHOUT the manifest
        blob (a hundred-run history shouldn't ship a hundred manifests --
        fetch one run for its manifest), plus which id is live right now."""
        store = _run_store()
        if store is None:
            return {"available": False, "current": None, "runs": []}
        with lock:
            current = _current_run_id()
        return {
            "available": True,
            "current": current,
            "runs": [
                {k: v for k, v in row.items() if k != "manifest"}
                for row in store.list_runs()
            ],
        }

    @app.get("/runs/{run_id}")
    def runs_get(run_id: str, _: None = Depends(require_auth)) -> dict:
        """One run's full row, parsed manifest included, plus whether it is
        the live one."""
        store = _run_store()
        row = store.get_run(run_id) if store is not None else None
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown run id: {run_id}")
        with lock:
            row["current"] = run_id == _current_run_id()
        return row

    @app.get("/runs/{run_id}/replay")
    def runs_replay(run_id: str, _: None = Depends(require_auth)) -> dict:
        """The run as a viewer-loadable replay: #307's build_replay served
        over HTTP. Save the body as penn_replay.json and open it via the
        landing menu's "Open a local replay file"."""
        store = _run_store()
        if store is None or store.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown run id: {run_id}")
        # Lazy on purpose: api.py stays importable without the Penn package,
        # and Penn's is the only replay dialect today. A second world's
        # format is the cue to promote a replay_builder= seam on create_app.
        from backend.penn.export_replay import build_replay

        return build_replay(store, run_id)

    @app.delete("/runs/{run_id}")
    def runs_delete(run_id: str, _: None = Depends(require_auth)) -> dict:
        """Remove a persisted run (row + memories + directory). The CURRENT
        live run is refused with a 409: the stepper is still appending
        frames to it -- reset or stop the run first."""
        store = _run_store()
        if store is None:
            raise HTTPException(status_code=404, detail=f"unknown run id: {run_id}")
        with lock:
            if run_id == _current_run_id():
                raise HTTPException(
                    status_code=409,
                    detail="run is live; reset or stop it before deleting",
                )
            try:
                store.delete_run(run_id)
            except KeyError:
                raise HTTPException(
                    status_code=404, detail=f"unknown run id: {run_id}"
                )
        return {"ok": True, "deleted": run_id}
```

(The `lock` use is deliberate: `_current_run_id` must be read consistently with `reset()` — which swaps `run_id` under the same lock — so the 409 check can't race a reset that makes a doomed run current mid-delete.)

- [ ] **Step 4: Run the tests, then the full godot suite**

Run: `uv run pytest godot-generative-agents/tests/test_live_seam.py -q`
Expected: all pass.
Run: `uv run pytest godot-generative-agents/tests/ -q`
Expected: all pass.
Run: `uv run black --check .`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/api.py godot-generative-agents/tests/test_live_seam.py
git commit -m "feat(backend): run registry endpoints — GET/DELETE /runs over the RunStore (#306)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
