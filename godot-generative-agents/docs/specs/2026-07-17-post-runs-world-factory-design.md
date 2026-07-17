# `POST /runs` — world-factory seam (#568)

**Issue:** #568 (`[backend] POST /runs — create a run over HTTP; #306's last deliverable`)
**Review track:** `godot-ga-main` (backend now lives under `godot-generative-agents/`)
**Status:** design approved 2026-07-17

## Goal

Add `POST /runs` — create a run over HTTP and adopt it as the live one, choosing
the world by name. This is the one #306 deliverable still unshipped, and it
introduces the **world-factory seam**: a named-world registry the backend resolves
instead of stepping only the single Penn world configured at `serve_penn` launch.

## Scope

**In v1:** request body `{world, steps?}`. The chosen world is built fresh, a run
is opened in the store, and it is adopted as the live run (reusing the #543
adoption machinery). The Penn world is the registry's first (and only) entry.

**Deferred (documented, not built):**

- **`model` override** — a per-run model means re-entering `resolve_llm` /
  `create_llm_client` mid-process, which re-touches the budget-gate, the monitor
  wiring, and the per-agent clients that today are built once in `PennStepper.__init__`
  and deliberately survive `_build()` across resets. All the real risk of #568 lives
  here, and the "Done when" does not require it. v1 reuses the launch-configured
  brain, so `meta()` already stamps the manifest correctly. The registry seam is
  shaped so a `model` argument can slot into `create_run` later.
- **`cast` override** — with one Penn world and one authored persona list, a second
  cast does not exist to select; speculative today.

Both were explicitly deferred by the #543 run-resume spec
(`2026-07-15-run-resume.md`, "Out of scope") and the #306 registry spec
(`2026-07-13-run-registry.md`).

## Why (and why not urgently)

A create-run API is what a web run-browser needs to start days with different
worlds/models without SSHing to the server. Until that UI (or a second world)
exists, `POST /reset` + CLI flags cover every real workflow — so this ships the
forward-looking seam cleanly rather than the speculative model/cast surface.

## Architecture

Approach A (chosen): the registry is a **stepper-owned optional capability**,
consistent with how every other world-specific capability (`run_store`,
`resume_run`, `run_usage`) is a `PennStepper` attribute the route probes via
`getattr`. `api.py` stays game-agnostic — it never learns how to build a world.

Rejected alternatives:

- **B — `create_app`-level registry** (`create_app(..., world_builders=...)`):
  couples the game-agnostic `api.py` to world-building, breaking the
  optional-capability pattern.
- **C — no registry, rebuild the current world**: simplest, but does not build the
  named-world seam the "Done when" requires, so it does not close #568.

### 1. The world-factory registry

A module-level mapping in `serve_penn.py`, name → zero-arg builder returning a
fresh `PennWorld`:

```python
WORLD_BUILDERS = {"penn": build_penn_world}
```

`build_penn_world()` already returns a fresh world (fresh `WorldMap`, fresh patch
state) on every call, which is exactly what a per-run build needs. Adding a second
world later is one dict entry.

### 2. `PennStepper.create_run` capability

Mirrors `resume_run`'s **guard-before-teardown** discipline — the world is built
*before* any teardown, so a failed build never strands the live run:

```python
def create_run(self, world: str, *, steps: int | None = None) -> str:
    """Build a named world, open a fresh run in the store, adopt it live (#568).

    Caller holds the app lock. Mirrors resume_run's teardown-before-rebuild order,
    but builds a fresh world instead of re-hydrating a stored one.
    """
    if self.run_store is None:
        raise ValueError("this server has no run store (--persist)")
    builder = WORLD_BUILDERS.get(world)
    if builder is None:
        raise KeyError(f"unknown world: {world}")
    world_obj = builder()                       # build first -- no teardown yet
    self._persist_pending_events()              # -- same teardown as resume_run --
    if self._run_id is not None and not self._run_finished:
        self.run_store.update_run(self._run_id, status="reset")
    if steps is not None:
        self.num_steps = steps
    self._build(world=world_obj)                # non-resume _build -> create_run(meta()) -> fresh run_id
    return self._run_id
```

Reuses the existing non-resume `_build` path, which already calls
`run_store.create_run(self.meta())` and sets `self._run_id`. `num_steps` is
consumed by `attach_agents` inside `_build`, so a `steps` override must be applied
before the `_build` call. Because v1 keeps the launch brain, the LLM clients are
untouched (they survive `_build`).

### 3. Route + contract (`POST /runs`)

Structurally a twin of `runs_resume`: probe the capability, run the swap in the
executor under the app lock, bump `controller.generation` to drop the in-flight
tick, publish the adoption signal.

Request body (a pydantic model, so an invalid body is an automatic 422 — the
run-registry spec's "plain dict responses" rule is about response shapes, not
request validation):

```python
class CreateRunRequest(BaseModel):
    world: str
    steps: int | None = Field(default=None, gt=0)
```

Response (mirrors `runs_resume`): `{**controller.status(), "cursor": int, "run_id": str}`,
and a `status(reason="reset", run_id=...)` feed record so followers refetch `/live`
+ `/world_state`. This is the *same* wire signal `runs_resume` already emits when it
adopts a run, so **no viewer change is needed** — a follower keys on
`reason == "reset"` and reads the `run_id`.

Status codes (consistent with the `/runs` registry family — same codes for the same
meanings, not an obligation to emit all of them):

| Code | When |
|------|------|
| 200  | run created + adopted; body carries the new `run_id` |
| 422  | invalid body (missing `world`, `steps <= 0`, wrong types) — from pydantic |
| 404  | no run store on this server, or unknown world name (`KeyError`) |
| 501  | this stepper has no `create_run` capability |

`409` is **not** triggered by create: there is no "already live" analog (that guard
is resume-specific), and concurrency with an in-flight tick is handled by the app
lock plus the `controller.generation` bump, exactly as resume handles it.

## Error handling

- `create_run` raises `KeyError` for an unknown world → route maps to 404 (matching
  resume's unknown-id → 404).
- `create_run` raises `ValueError` only for a missing store, but the route's own
  `_run_store() is None` check pre-empts that with a 404, so the store `ValueError`
  is defensive.
- A builder that fails to construct the world (e.g. corrupt world YAML) raises
  before any teardown; the live run is untouched and the failure surfaces as a 500
  (a genuine server fault, not a client error).

## Testing (offline `TestClient`, no API key)

All coverage is offline, matching the existing `/runs` route tests in
`godot-generative-agents/tests/test_live_seam.py`.

**Route-level** — a fake stepper exposing a canned `create_run` (like the resume
fakes already in `test_live_seam.py`):

- success → 200, body has a new `run_id`, `GET /runs` `current` moves to it, and a
  `status` feed record with `reason == "reset"` and the new `run_id` is emitted;
- unknown world → 404;
- invalid body (missing `world`; `steps == 0` / negative) → 422;
- server with no run store → 404;
- stepper without the `create_run` capability → 501.

**Stepper-level** — a real `PennStepper(world=build_penn_world())` with a `RunStore`
under `tmp_path`, mock brain (the #551 deciding-feed tests already build a
`PennStepper` this way offline, no key):

- `create_run("penn")` returns a fresh run id distinct from the launch run, opens a
  new store row, and marks the previous unfinished run `"reset"`;
- a `steps` argument sets `num_steps` for the created run;
- an unknown world name raises `KeyError` and tears nothing down (the previous
  `run_id` is unchanged).

## Done when

A named-world registry exists on the backend seam, `POST /runs` creates + adopts a
run from it with 404/422/501 semantics consistent with the registry family, the
Penn world is its first (only) entry, and the offline `TestClient` coverage matches
the other `/runs` routes.

## References

- Issue #568; parent epic #306; run-resume #543; registry #306 registry-half.
- Specs: `2026-07-15-run-resume.md`, `2026-07-13-run-registry.md`.
- Code anchors: `backend/api.py` (`create_app`, `runs_resume` at the `/runs`
  family), `backend/penn/serve_penn.py` (`PennStepper.__init__`/`_build`/`meta`/
  `resume_run`/`_resumable_row`, `resolve_llm`), `backend/run_store.py`
  (`RunStore.create_run`), `backend/penn/penn_world.py` (`build_penn_world`).
