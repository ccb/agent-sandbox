# POST /runs — world-factory seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /runs` — create a run over HTTP by naming a world, then adopt it as the live run — backed by a stepper-owned world-factory registry.

**Architecture:** A module-level `WORLD_BUILDERS` registry in `serve_penn.py` maps a world name to a zero-arg builder. `PennStepper.create_run(world, *, steps=None)` is a new optional capability that builds the named world, closes the current run, and rebuilds on it (reusing the existing non-resume `_build` path, which opens a fresh run in the store). The `POST /runs` route in the game-agnostic `api.py` probes that capability via `getattr` — exactly like `run_store` / `resume_run` — and adopts the new run the same way `POST /runs/{id}/resume` does (bump `controller.generation`, publish a `status(reason="reset", run_id=...)` record).

**Tech Stack:** Python 3.12, FastAPI + pydantic, Starlette `TestClient`, pytest, uv. Backend under `godot-generative-agents/backend/`.

## Global Constraints

- **v1 request body is `{world, steps?}` only.** No `model` or `cast` override — those are documented follow-ups. v1 reuses the launch-configured brain untouched.
- **Guard-before-teardown:** an unknown world or a failed world build must leave the current live run intact (build the world *before* closing the old run), mirroring `resume_run`.
- **Reuse the adoption wire signal:** create publishes the *same* `status(reason="reset", run_id=...)` feed record that `runs_resume` emits, so both frontends need zero changes.
- **Plain-dict response** for the route (a pydantic response model would strip the additive `run_id` key), matching the rest of the `/runs` registry family.
- **Status codes consistent with the registry family:** 200 (created+adopted), 422 (invalid body, from pydantic), 404 (no store / unknown world), 501 (stepper lacks the capability). `409` is intentionally not emitted (no "already live" analog).
- **All tests offline, no API key** (mock brain). Review track: **`godot-ga-main`** (backend lives under `godot-generative-agents/`).

---

### Task 1: World-factory registry + `PennStepper.create_run`

**Files:**
- Modify: `godot-generative-agents/backend/penn/serve_penn.py` (add `WORLD_BUILDERS` near the module constants ~line 75–91; add `create_run` method right after `reset()`, which ends at line 958)
- Test: `godot-generative-agents/tests/test_penn_live.py` (add next to `test_stepper_reset_closes_the_run_and_opens_a_new_one`, line 411)

**Interfaces:**
- Consumes: `build_penn_world` (already imported at `serve_penn.py:66`); `PennStepper._build(world=...)` (line 492, its non-resume path opens `self._run_id = self.run_store.create_run(self.meta())` at line 611); `PennStepper._persist_pending_events()`; `self.run_store`, `self._run_id`, `self._run_finished`, `self.num_steps`.
- Produces: `WORLD_BUILDERS: dict[str, Callable[[], PennWorld]]` and `PennStepper.create_run(self, world: str, *, steps: int | None = None) -> str` — builds+adopts a named world, returns the new run id; raises `KeyError` on an unknown world name and `ValueError` when the stepper has no run store.

- [ ] **Step 1: Write the failing stepper tests**

Add to `godot-generative-agents/tests/test_penn_live.py` (it already imports `PennStepper`, `build_penn_world`, `RunStore`, and `pytest`):

```python
# ------------------------------------------------ create (#568, world factory)


def test_stepper_create_run_builds_and_adopts_a_named_world(tmp_path):
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=3, world=build_penn_world(), run_store=store)
    first = stepper.run_id
    new_id = stepper.create_run("penn", steps=7)
    assert new_id != first  # a fresh run id
    assert stepper.run_id == new_id  # adopted as the live run
    assert stepper.num_steps == 7  # the step-budget override took
    assert store.get_run(first)["status"] == "reset"  # old run closed
    assert store.get_run(new_id)["status"] == "running"  # new run open
    assert {r["id"] for r in store.list_runs()} == {first, new_id}


def test_stepper_create_run_unknown_world_keeps_the_live_run(tmp_path):
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=3, world=build_penn_world(), run_store=store)
    first = stepper.run_id
    with pytest.raises(KeyError):
        stepper.create_run("atlantis")
    # Guard-before-teardown: the live run is untouched, still running.
    assert stepper.run_id == first
    assert store.get_run(first)["status"] == "running"
    assert {r["id"] for r in store.list_runs()} == {first}


def test_stepper_create_run_needs_a_store(tmp_path):
    stepper = PennStepper(num_steps=1, world=build_penn_world())  # storeless
    with pytest.raises(ValueError):
        stepper.create_run("penn")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_penn_live.py -k create_run -v`
Expected: FAIL — `AttributeError: 'PennStepper' object has no attribute 'create_run'`.

- [ ] **Step 3: Add the `WORLD_BUILDERS` registry**

In `godot-generative-agents/backend/penn/serve_penn.py`, add near the other module-level constants (just after `DEFAULT_STEPS = 1200` at line 75, or alongside `SCRIPTED = "scripted"` at line 91). `build_penn_world` is already imported at line 66:

```python
# The world-factory registry (#568): a world name -> a zero-arg builder that
# returns a FRESH PennWorld. build_penn_world already hands back a fresh world
# (fresh WorldMap + patch state) on every call, which is what a per-run build
# needs. Penn is the first (and today only) entry; a second world is one line.
WORLD_BUILDERS = {"penn": build_penn_world}
```

- [ ] **Step 4: Add the `create_run` method**

In `godot-generative-agents/backend/penn/serve_penn.py`, add immediately after `reset()` (which ends at line 958), so it sits beside `resume_run()`:

```python
    def create_run(self, world: str, *, steps: int | None = None) -> str:
        """Build a NAMED world from the factory registry, open a fresh run in
        the store, and adopt it as the live one (#568); caller holds the app
        lock, like reset()/resume_run().

        The world is built BEFORE any teardown (guard-before-teardown, like
        resume_run): an unknown world name or a failed build leaves the live
        run intact. v1 chooses only the world and an optional step budget --
        the launch-configured brain is reused, so the LLM clients (built once
        in __init__, surviving _build on purpose) are untouched and meta()
        stamps the new run's manifest correctly.
        """
        if self.run_store is None:
            raise ValueError("this server has no run store (--persist)")
        builder = WORLD_BUILDERS.get(world)
        if builder is None:
            raise KeyError(f"unknown world: {world}")
        world_obj = builder()  # build first -- no teardown yet
        # Close the current day the way reset() does (a finished day keeps
        # "finished"), then rebuild on the new world -- _build's non-resume
        # path opens the next run row via create_run(self.meta()).
        self._persist_pending_events()
        if self._run_id is not None and not self._run_finished:
            self.run_store.update_run(self._run_id, status="reset")
        if steps is not None:
            self.num_steps = steps  # attach_agents reads num_steps inside _build
        self._build(world=world_obj)
        return self._run_id
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_penn_live.py -k create_run -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Format and commit**

```bash
uv run black godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_penn_live.py
git add godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_penn_live.py
git commit -m "feat(backend): world-factory registry + PennStepper.create_run (#568)"
```

---

### Task 2: `POST /runs` route + `CreateRunRequest`

**Files:**
- Modify: `godot-generative-agents/backend/api.py` (add `CreateRunRequest` model near the other request models ~line 148–165; add the `runs_create` route in the run-registry block, after `runs_index` at line 1131; update the deferred-POST comment at lines 1106)
- Test: `godot-generative-agents/tests/test_live_seam.py` (add a `_creatable_stepper` fixture beside `_resumable_stepper` at line 407, and the route tests beside the resume tests)

**Interfaces:**
- Consumes: `PennStepper.create_run(world, *, steps=None) -> str` (Task 1); the route helpers `_run_store()` and `_current_run_id()` (`api.py:1108–1112`); `lock`, `controller`, `log` closed over by `create_app`; `runs_resume` as the structural template (`api.py:1186–1239`); pydantic `BaseModel`, `Field` (already imported at `api.py:93`).
- Produces: `POST /runs` accepting `{"world": str, "steps": int | None}` → `{**controller.status(), "cursor": int, "run_id": str}`.

- [ ] **Step 1: Write the failing route tests**

Add to `godot-generative-agents/tests/test_live_seam.py` (it already imports `create_app`, `TestClient`, `pytest`, and defines `_walker`, `_live_client`, `_stepper_with_store`). Place after `test_resume_endpoint_without_capability_is_501` (line 460):

```python
# --- POST /runs create + adopt (#568) --------------------------------------


def _creatable_stepper(tmp_path):
    """_stepper_with_store plus the #568 capability: a create_run spy that
    opens + adopts a NEW run id the way PennStepper.create_run does (attribute
    assignment is the blessed way to give a fake stepper optional capabilities)."""
    stepper, store = _stepper_with_store(tmp_path)
    calls = []

    def create_run(world, *, steps=None):
        calls.append((world, steps))
        if world != "penn":
            raise KeyError(f"unknown world: {world}")
        manifest = {"schema_version": 1, "personas": [{"name": "a"}], "llm": None}
        run_id = store.create_run(manifest)  # store picks a fresh id
        stepper.run_id = run_id
        return run_id

    stepper.create_run = create_run
    return stepper, store, calls


def test_create_run_builds_and_adopts_a_new_run(tmp_path):
    stepper, store, calls = _creatable_stepper(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        body = client.post("/runs", json={"world": "penn", "steps": 50}).json()
        assert calls == [("penn", 50)]
        new_id = body["run_id"]
        assert new_id not in ("run-1-old", "run-2-live")  # a fresh id
        assert body["paused"] is True  # create never touches the play button
        assert body["cursor"] >= 1
        # Adoption moved the registry's "current" marker to the new run.
        assert client.get("/runs").json()["current"] == new_id
        # Followers got the documented rebuild signal, stamped with the run.
        events = client.get("/events?since=0").json()["events"]
        newest = [e for e in events if e["kind"] == "status"][-1]
        assert newest["reason"] == "reset"
        assert newest["run_id"] == new_id


def test_create_run_unknown_world_is_404(tmp_path):
    stepper, store, calls = _creatable_stepper(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        assert client.post("/runs", json={"world": "atlantis"}).status_code == 404


def test_create_run_invalid_body_is_422(tmp_path):
    stepper, store, calls = _creatable_stepper(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        assert client.post("/runs", json={}).status_code == 422  # world required
        assert (
            client.post("/runs", json={"world": "penn", "steps": 0}).status_code == 422
        )
        assert calls == []  # validation fails before the stepper is touched


def test_create_run_without_a_store_is_404(tmp_path):
    with _live_client(_walker(), start_paused=True) as client:
        assert client.post("/runs", json={"world": "penn"}).status_code == 404


def test_create_run_without_capability_is_501(tmp_path):
    # A store alone isn't enough: only PennStepper can build a world today.
    stepper, _store = _stepper_with_store(tmp_path)
    with _live_client(stepper, start_paused=True) as client:
        assert client.post("/runs", json={"world": "penn"}).status_code == 501
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_live_seam.py -k create_run -v`
Expected: FAIL — the `POST /runs` route does not exist yet. `/runs` has only a GET handler, so a POST returns **405 Method Not Allowed**: the adopt test errors on `body["run_id"]` (405's body has no `run_id`), and the 404/422/501 tests fail because they see 405, not their expected code.

- [ ] **Step 3: Add the `CreateRunRequest` model**

In `godot-generative-agents/backend/api.py`, add near the other request models (e.g. after `CommandRequest`/`CommandResponse`, before `SayRequest` at line 166). `BaseModel` and `Field` are already imported at line 93:

```python
class CreateRunRequest(BaseModel):
    """POST /runs body (#568): pick a world from the factory registry, and
    optionally cap the run's steps. v1 chooses only the world -- a per-run
    model/cast override is a documented follow-up."""

    world: str = Field(
        ..., min_length=1, description="a name in the world registry, e.g. 'penn'"
    )
    steps: int | None = Field(
        default=None, gt=0, description="step budget; omit to keep the server default"
    )
```

- [ ] **Step 4: Add the `runs_create` route**

In `godot-generative-agents/backend/api.py`, add inside the run-registry block, right after `runs_index` (ends at line 1131) and before `runs_get`:

```python
    @app.post("/runs")
    async def runs_create(
        req: CreateRunRequest, _: None = Depends(require_auth)
    ) -> dict:
        """Create a run over HTTP and adopt it as the live one (#568, #306's
        last deliverable): build the named world from the backend's
        world-factory registry, open its run in the store, and swap it in
        exactly the way POST /runs/{id}/resume adopts a persisted run.

        Followers see the same ``status`` record with ``reason: "reset"`` and
        an additive ``run_id`` -- the documented "the world was rebuilt,
        refetch meta and follow from here" signal -- so both frontends handle a
        create with zero client changes. Plain dict like the rest of the
        registry: a response model would strip the ``run_id`` key.

        404 when the server has no run store, or the world is unknown; 501 when
        the stepper cannot build worlds (only PennStepper can today); 422 for a
        bad body (from the request model). There is no 409: unlike resume there
        is no "already live" run to clash with, and an in-flight tick is dropped
        by the generation bump, atomic with the swap under the lock."""
        store = _run_store()
        if store is None:
            raise HTTPException(status_code=404, detail="this server has no run store")
        create_run = getattr(stepper, "create_run", None)
        if not callable(create_run):
            raise HTTPException(
                status_code=501, detail="this stepper cannot create runs"
            )

        def _make():
            # Same pattern as runs_resume: build + adopt under the app lock in a
            # worker thread, bump the generation so an in-flight tick of the OLD
            # world is dropped instead of published.
            with lock:
                run_id = create_run(req.world, steps=req.steps)
                controller.generation += 1
                return run_id

        try:
            run_id = await asyncio.get_running_loop().run_in_executor(None, _make)
        except KeyError as exc:
            # exc.args[0] keeps the message unquoted (str() of a KeyError wraps
            # it in repr quotes), matching runs_resume.
            raise HTTPException(status_code=404, detail=str(exc.args[0]))
        record = log.append(
            "status", reason="reset", run_id=run_id, **controller.status()
        )
        return {**controller.status(), "cursor": record["cursor"], "run_id": run_id}
```

- [ ] **Step 5: Update the deferred-POST comment**

In `godot-generative-agents/backend/api.py`, the run-registry block comment (lines 1100–1106) ends with "POST /runs (create with a world-factory seam) stays deferred." Change that closing sentence to reflect that it now lands here:

Replace:
```python
    # answers available:false here and 404 on every id route instead of
    # erroring. POST /runs (create with a world-factory seam) stays deferred.
```
with:
```python
    # answers available:false here and 404 on every id route instead of
    # erroring. POST /runs (create + adopt via the world-factory seam, #568)
    # rides the same probe: 501 when the stepper cannot build worlds.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_live_seam.py -k create_run -v`
Expected: PASS (5 passed).

- [ ] **Step 7: Format and commit**

```bash
uv run black godot-generative-agents/backend/api.py godot-generative-agents/tests/test_live_seam.py
git add godot-generative-agents/backend/api.py godot-generative-agents/tests/test_live_seam.py
git commit -m "feat(backend): POST /runs creates + adopts a run from the world factory (#568)"
```

---

### Task 3: Full-suite guard + spec cross-check

**Files:** none changed — this task verifies the two feature commits don't regress the backend suite and that the "Done when" is met.

- [ ] **Step 1: Run the backend suite**

Run: `uv run pytest godot-generative-agents/tests/test_live_seam.py godot-generative-agents/tests/test_penn_live.py -v`
Expected: PASS — all existing tests plus the 8 new ones (3 stepper + 5 route).

- [ ] **Step 2: Confirm black is clean**

Run: `uv run black --check godot-generative-agents/backend/api.py godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_live_seam.py godot-generative-agents/tests/test_penn_live.py`
Expected: `All done!` — nothing to reformat.

- [ ] **Step 3: Cross-check the spec's "Done when"**

Confirm each holds and note it in the review ledger:
- named-world registry exists on the backend seam → `WORLD_BUILDERS` (Task 1);
- `POST /runs` creates + adopts from it → `runs_create` + `create_run` (Tasks 1–2);
- 404/422/501 semantics consistent with the registry family, no spurious 409 → route tests (Task 2);
- Penn is the first (only) entry → `WORLD_BUILDERS = {"penn": build_penn_world}`;
- offline `TestClient` coverage matching the other `/runs` routes → Task 2 tests.

No commit (verification only).

---

## Notes for the implementer

- **Do not** add a `model` or `cast` field to `CreateRunRequest`, and do not re-enter `resolve_llm` / rebuild LLM clients — that is out of scope (Global Constraints). `create_run` deliberately never touches `self.llm_client` / `self.reflector_client`.
- **Do not** catch `ValueError` in the route to emit 409: `create_run`'s only `ValueError` (no store) is pre-empted by the route's `_run_store() is None` 404 check, and a world-builder failure should surface as a 500 (a genuine server fault), not a client error.
- Build the world **before** the teardown lines in `create_run` — reordering breaks the guard-before-teardown invariant the unknown-world test pins.
