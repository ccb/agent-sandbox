# `deciding` Feed Record + Per-Agent Thinking Bubbles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit a first-class `deciding` begin/end change-feed record per agent, and drive the Godot viewer's live "thinking" indicator from it as per-agent bubbles (migrating #372 off its global stall-inference), keeping the global badge as a smart fallback.

**Architecture:** The decision entry point `run_simulation._decide_for` (called exactly once per decision — inline on the serial path, submitted on the #366 concurrent path, and never re-called for a parked future) gains an optional `deciding_sink` and emits `begin` at entry / `end` at exit. `PennStepper` buffers those records (gated so only a real/scripted brain emits — the pure mock feed stays byte-identical), and `live.run_loop` drains the buffer onto the feed exactly where it appends `engine` records. The viewer routes the new record into a pure `DecidingState` helper that a per-agent bubble and the global badge read.

**Tech Stack:** Python 3.12 + pytest (backend, `uv run`); GDScript / Godot 4.6 (viewer, headless unit tests via `run_smoke_test.sh`).

## Global Constraints

- **Track:** `godot-ga-main` (backend under `godot-generative-agents/backend/` + viewer under `godot-generative-agents/godot/`). Branch `feat/deciding-feed-551`, worktree `.claude/worktrees/deciding-551` (off current `godot-ga-main` = df7f55b).
- **`--brain mock` feed stays BYTE-IDENTICAL:** the pure schedule mock emits **no** `deciding` records. Gate emission on `self.llm_client is not None` (true for real + scripted brains, false for mock). The determinism suite (`test_penn_live.py`) must stay green.
- **Never append to the feed off a #366 worker thread.** `_decide_for` calls only a lightweight sink (a GIL-atomic list append); the feed `log.append` happens on the event loop via the drain, mirroring the `engine`-record path.
- **Record shape (verbatim):** `{"kind": "deciding", "agent": <str>, "state": "begin"|"end", "step": <int>}`, plus `"elapsed_ms": <int>` on `end`.
- **Additive-safe:** feed records are not persisted; unknown kinds are ignored by consumers. No `backend/contract.py` / RunStore change.
- **`run_simulation` stays determinism-safe:** it must not read wall-clock; all timing lives in the stepper's sink. The bake (`simulate`) passes `deciding_sink=None`.
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Stage explicit paths only — never `git add -A`.
- GDScript indents with **tabs** (match the existing files exactly).
- Run backend tests from the repo root: `uv run pytest <path> -v`. Run viewer tests via `./godot-generative-agents/run_smoke_test.sh`.

---

### Task 1: `_decide_for` / `step` emit begin/end through a `deciding_sink`

**Files:**
- Modify: `godot-generative-agents/backend/run_simulation.py` (`_decide_for` ~55; `step` signature ~114-131; the concurrent submit ~263 and serial `_decide_for` call ~315)
- Test: `godot-generative-agents/tests/test_deciding_feed.py` (new)

**Interfaces:**
- Produces: `_decide_for(game, char, step_idx, retrieval, clock=None, stop_since=0, deciding_sink=None)`. When `deciding_sink` is not None it calls `deciding_sink(char.name, "begin", step_idx)` before deciding and `deciding_sink(char.name, "end", step_idx)` in a `finally`. `step(..., deciding_sink=None)` threads it into every `_decide_for` call. The sink signature is `(agent: str, state: "begin"|"end", step: int) -> None`.

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/tests/test_deciding_feed.py`:

```python
"""The deciding lifecycle feed record (#551): begin/end around each real decide.
Fully offline. Run from the repo root:
    uv run pytest godot-generative-agents/tests/test_deciding_feed.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend import run_simulation  # noqa: E402


def test_decide_for_emits_begin_then_end_around_the_decision(monkeypatch):
    calls = []
    # Stub the decision so the test is independent of a real brain.
    monkeypatch.setattr(run_simulation, "observe_and_decide", lambda *a, **k: "look")

    class _Char:
        class agent:
            llm_client = None
        name = "Maya"

    result = run_simulation._decide_for(
        game=None, char=_Char(), step_idx=7, retrieval=None,
        deciding_sink=lambda name, state, step: calls.append((name, state, step)),
    )
    assert result == "look"
    assert calls == [("Maya", "begin", 7), ("Maya", "end", 7)]


def test_decide_for_emits_end_even_if_the_decision_raises(monkeypatch):
    calls = []

    def _boom(*a, **k):
        raise RuntimeError("brain down")

    monkeypatch.setattr(run_simulation, "observe_and_decide", _boom)

    class _Char:
        class agent:
            llm_client = None
        name = "Diego"

    import pytest
    with pytest.raises(RuntimeError):
        run_simulation._decide_for(
            game=None, char=_Char(), step_idx=3, retrieval=None,
            deciding_sink=lambda n, s, st: calls.append((n, s, st)),
        )
    # begin fired, and end fired via finally so a crashed decide can't strand a bubble.
    assert calls == [("Diego", "begin", 3), ("Diego", "end", 3)]


def test_no_sink_is_a_noop(monkeypatch):
    monkeypatch.setattr(run_simulation, "observe_and_decide", lambda *a, **k: "look")

    class _Char:
        class agent:
            llm_client = None
        name = "Sofia"

    # Default deciding_sink=None: no error, decision returned unchanged.
    assert run_simulation._decide_for(None, _Char(), 0, None) == "look"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_deciding_feed.py -v`
Expected: FAIL — `_decide_for()` got an unexpected keyword argument `deciding_sink`.

- [ ] **Step 3: Add `deciding_sink` to `_decide_for`**

In `run_simulation.py`, change the `_decide_for` signature and wrap the decide. Current:
```python
def _decide_for(game, char, step_idx, retrieval, clock=None, stop_since=0):
```
becomes:
```python
def _decide_for(game, char, step_idx, retrieval, clock=None, stop_since=0, deciding_sink=None):
```
and change the body's final `return observe_and_decide(...)` into a begin/decide/end wrap:
```python
    if deciding_sink is not None:
        deciding_sink(char.name, "begin", step_idx)
    try:
        return observe_and_decide(
            game, char, step_idx, retrieval=retrieval, clock=clock, stop_since=stop_since
        )
    finally:
        if deciding_sink is not None:
            deciding_sink(char.name, "end", step_idx)
```
(The context-stamp block above it is unchanged.)

- [ ] **Step 4: Thread `deciding_sink` through `step`**

In `step`'s signature add the param after `decide_info`:
```python
    decide_info: dict | None = None,
    deciding_sink=None,
) -> tuple[dict, int]:
```
Pass it into the **concurrent submit** call (the `decide_executor.submit(_decide_for, ...)` block ~263):
```python
            futs[name] = decide_executor.submit(
                _decide_for,
                game,
                chars[name],
                step_idx,
                retrieval,
                clock=clock,
                stop_since=state[name].get("stop_since", 0),
                deciding_sink=deciding_sink,
            )
```
and into the **serial inline** call (the `else _decide_for(...)` in the resolve loop ~315):
```python
                else _decide_for(
                    game,
                    char,
                    step_idx,
                    retrieval,
                    clock=clock,
                    stop_since=st.get("stop_since", 0),
                    deciding_sink=deciding_sink,
                )
```
(The parked-future paths at ~257/~261 do **not** call `_decide_for`, so they correctly emit nothing — the original decision already emitted its begin/end when its `_decide_for` ran.)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest godot-generative-agents/tests/test_deciding_feed.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Guard the deterministic path — determinism suite still green**

Run: `uv run pytest godot-generative-agents/tests/test_penn_live.py -v`
Expected: PASS (the bake/serial path passes `deciding_sink=None`, so behavior is unchanged).

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/backend/run_simulation.py godot-generative-agents/tests/test_deciding_feed.py
git commit -m "feat(backend): _decide_for/step emit deciding begin/end via a sink (#551)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `PennStepper` buffers deciding records (gated) + `drain_deciding`

**Files:**
- Modify: `godot-generative-agents/backend/penn/serve_penn.py` (`PennStepper.__init__`/`_build` buffer init; the `step(...)` call ~760; a new sink method + `drain_deciding`)
- Test: `godot-generative-agents/tests/test_deciding_feed.py` (extend)

**Interfaces:**
- Consumes: `step(..., deciding_sink=...)` from Task 1.
- Produces: `PennStepper._deciding_sink(name, state, step)` (records begin timestamps, appends `{"agent","state","step"[,"elapsed_ms"]}` to `self._deciding_buf`); `PennStepper.drain_deciding() -> list[dict]` (returns + clears the buffer). Emission is gated: the `step()` call passes the sink only when `self.llm_client is not None`.

- [ ] **Step 1: Write the failing test**

Append to `test_deciding_feed.py` (drives a real PennStepper with a fake tool-calling brain — reuse the fake from `test_penn_live_llm.py`):

```python
def test_stepper_drains_deciding_records_under_a_real_brain(monkeypatch):
    # Reuse the live-llm fake-client stepper helper.
    import test_penn_live_llm as tll
    stepper = tll._llm_stepper(monkeypatch)  # --brain llm mode, fakes swapped in
    # Tick until at least one agent hits a decision point and emits records.
    seen = []
    for _ in range(6):
        stepper.tick()
        seen.extend(stepper.drain_deciding())
        if seen:
            break
    assert seen, "no deciding records emitted under a real brain"
    kinds = {(r["state"]) for r in seen}
    assert "begin" in kinds
    for r in seen:
        assert set(r) >= {"agent", "state", "step"}
        if r["state"] == "end":
            assert isinstance(r["elapsed_ms"], int) and r["elapsed_ms"] >= 0
    # Draining twice is idempotent (buffer cleared).
    assert stepper.drain_deciding() == []


def test_mock_stepper_emits_no_deciding_records():
    sys.path.insert(0, str(_SIM_DIR))
    from serve_penn import PennStepper
    from penn_world import build_penn_world

    stepper = PennStepper(num_steps=5, world=build_penn_world())  # --brain mock
    for _ in range(5):
        stepper.tick()
    assert stepper.drain_deciding() == []  # byte-identical mock feed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_deciding_feed.py -k stepper -v`
Expected: FAIL — `PennStepper` has no attribute `drain_deciding`.

- [ ] **Step 3: Add the buffer, sink, and drain to `PennStepper`**

In `serve_penn.py`, in `__init__` beside the other cross-reset state (near `self.last_deciders = None`, ~369), add:
```python
        # Per-agent decision lifecycle records for the live feed (#551), buffered
        # here and drained each tick by backend.live. Only populated under a
        # real/scripted brain (see the tick() gate); the pure mock never fills it,
        # so its feed stays byte-identical. _deciding_started holds per-agent
        # begin timestamps to compute elapsed_ms on end (distinct keys per agent
        # -> safe to write from concurrent #366 decide workers).
        self._deciding_buf: list = []
        self._deciding_started: dict = {}
```

Add the sink method and drain (near `drain_events`, ~849):
```python
    def _deciding_sink(self, name: str, state: str, step: int) -> None:
        """Called by run_simulation._decide_for at a decision's start/finish
        (issue #551). Buffers a feed record; backend.live drains it per tick and
        appends it as a `kind: "deciding"` change-feed record. A plain list
        append + distinct-key dict writes are GIL-atomic, so this is safe to call
        from a #366 decide worker thread."""
        if state == "begin":
            self._deciding_started[name] = time.monotonic()
            self._deciding_buf.append({"agent": name, "state": "begin", "step": step})
        else:  # "end"
            started = self._deciding_started.pop(name, None)
            rec = {"agent": name, "state": "end", "step": step}
            if started is not None:
                rec["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            self._deciding_buf.append(rec)

    def drain_deciding(self) -> list:
        """New `deciding` records formed since the last drain (#551). backend.live
        probes this optional method after each tick and appends each as a
        `kind: "deciding"` feed record (beside the `engine` rows). Empty under the
        pure mock brain."""
        rows = self._deciding_buf
        self._deciding_buf = []
        return rows
```

Reset the buffer in `_build` (so a `POST /reset` starts clean) — add near the other per-build resets (e.g. beside `self._decide_pending = {}`, ~499):
```python
        self._deciding_buf = []
        self._deciding_started = {}
```

- [ ] **Step 4: Wire the gated sink into the `step()` call**

In `tick()`, in the `step(...)` call (~760), add the gated sink argument after `decide_info=decide_info,`:
```python
            decide_info=decide_info,
            # #551: emit the deciding lifecycle only under a real/scripted brain
            # (self.llm_client set) -- the pure mock feed stays byte-identical.
            deciding_sink=(self._deciding_sink if self.llm_client is not None else None),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_deciding_feed.py -v`
Expected: PASS (Task 1's 3 + the 2 new).

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_deciding_feed.py
git commit -m "feat(backend): PennStepper buffers + drains deciding records, gated to real brains (#551)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `live` publishes `deciding` records on the feed

**Files:**
- Modify: `godot-generative-agents/backend/live.py` (`LiveRunController.tick_once` ~215-228; `run_loop` ~297-308)
- Test: `godot-generative-agents/tests/test_deciding_feed.py` (extend)

**Interfaces:**
- Consumes: an optional `drain_deciding() -> list[dict]` on the stepper (Task 2).
- Produces: `tick_once()`'s result dict gains `"deciding": list[dict]`; `run_loop` appends each as `log.append("deciding", **rec)`.

- [ ] **Step 1: Write the failing test**

Append to `test_deciding_feed.py` (uses the in-repo `ScriptedStepper` + `EventLog`; drives one tick through the controller):

```python
def test_live_feed_publishes_deciding_records():
    import asyncio
    from backend.live import EventLog, LiveRunController, ScriptedStepper, run_loop

    class _Stepper(ScriptedStepper):
        def __init__(self):
            super().__init__(frames=[{"Maya": {"x": 0, "y": 0}}])  # one frame then finished
            self._drained = False

        def drain_deciding(self):
            if self._drained:
                return []
            self._drained = True
            return [
                {"agent": "Maya", "state": "begin", "step": 0},
                {"agent": "Maya", "state": "end", "step": 0, "elapsed_ms": 12},
            ]

    log = EventLog()
    controller = LiveRunController(_Stepper())

    async def _drive():
        task = asyncio.create_task(run_loop(controller, log, tick_seconds=0.0))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_drive())
    deciding = [r for r in log.since(-1) if r.get("kind") == "deciding"]
    assert {"agent": "Maya", "state": "begin", "step": 0} in [
        {k: r[k] for k in ("agent", "state", "step")} for r in deciding
    ]
    assert any(r["state"] == "end" and r.get("elapsed_ms") == 12 for r in deciding)
```

> Note for the implementer: confirm `ScriptedStepper`'s constructor kwarg (`frames=`) and `EventLog.since(...)` / the cursor accessor against `backend/live.py` (the explore reported `_records`/`since`); adjust the harness call to the real API if it differs — the assertion (a `deciding` begin+end appears on the feed) is what matters.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_deciding_feed.py -k live_feed -v`
Expected: FAIL — no `deciding` records on the feed (run_loop doesn't emit them yet).

- [ ] **Step 3: Collect deciding records in `tick_once`**

In `live.py` `tick_once`, beside the `drain_events` probe (~219-221):
```python
            drain = getattr(self._stepper, "drain_events", None)
            events = list(drain()) if drain is not None else []
            deciders = getattr(self._stepper, "last_deciders", None)
            drain_dec = getattr(self._stepper, "drain_deciding", None)
            deciding = list(drain_dec()) if drain_dec is not None else []
```
and add it to the returned dict:
```python
        return {
            "generation": generation,
            "step": step,
            "agents": agents,
            "events": events,
            "deciders": deciders,
            "deciding": deciding,
        }
```

- [ ] **Step 4: Append them in `run_loop`**

In `run_loop`, right after the `engine` append loop (~307-308):
```python
            for event in result["events"]:
                log.append("engine", step=result["step"], event=event)
            for rec in result.get("deciding", ()):
                log.append("deciding", **rec)
```
(Uses `result.get` so an older stepper/result shape without the key is harmless.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_deciding_feed.py -v`
Expected: PASS (all backend deciding tests).

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/backend/live.py godot-generative-agents/tests/test_deciding_feed.py
git commit -m "feat(backend): live feed publishes deciding begin/end records (#551)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `DecidingState` pure helper + headless test

**Files:**
- Create: `godot-generative-agents/godot/scripts/deciding_indicator.gd`
- Create: `godot-generative-agents/godot/tests/test_deciding_indicator.gd`
- Modify: `godot-generative-agents/run_smoke_test.sh` (register the new test)

**Interfaces:**
- Produces: a `RefCounted` with `apply(rec: Dictionary) -> void`, `is_deciding(agent: String) -> bool`, `any_deciding() -> bool`, `seen_signal() -> bool`, `clear() -> void`. This is the state machine the viewer (Task 5) reads.

- [ ] **Step 1: Write the failing test** (tabs, matching `test_thinking_indicator.gd`)

Create `godot-generative-agents/godot/tests/test_deciding_indicator.gd`:

```gdscript
extends SceneTree
## Headless unit tests for scripts/deciding_indicator.gd (issue #551). Run:
##   godot --headless --path godot-generative-agents/godot \
##     --script res://tests/test_deciding_indicator.gd
## Exit 0 = all checks pass; run_smoke_test.sh runs this and greps the sentinel.

const DecidingState := preload("res://scripts/deciding_indicator.gd")

var _failures := 0


func _check(cond: bool, name: String) -> void:
	if cond:
		print("  ok: %s" % name)
	else:
		_failures += 1
		push_error("FAIL: %s" % name)


func _rec(agent: String, state: String) -> Dictionary:
	return {"kind": "deciding", "agent": agent, "state": state, "step": 0}


func _initialize() -> void:
	var s = DecidingState.new()
	_check(not s.seen_signal(), "no signal seen before any record")
	_check(not s.any_deciding(), "nobody deciding initially")

	s.apply(_rec("Maya", "begin"))
	_check(s.is_deciding("Maya"), "begin -> agent is deciding")
	_check(s.any_deciding(), "begin -> any_deciding true")
	_check(s.seen_signal(), "a record arrived -> signal seen")
	_check(not s.is_deciding("Diego"), "other agent unaffected")

	s.apply(_rec("Maya", "end"))
	_check(not s.is_deciding("Maya"), "end -> agent no longer deciding")
	_check(not s.any_deciding(), "end -> any_deciding false")

	# Unmatched end (no prior begin) is safely ignored, no error.
	s.apply(_rec("Ghost", "end"))
	_check(not s.is_deciding("Ghost"), "unmatched end -> not deciding")

	# A record missing the agent is ignored.
	s.apply({"kind": "deciding", "state": "begin"})
	_check(not s.any_deciding(), "agent-less record ignored")

	# clear() drops all state (teardown / backend restart).
	s.apply(_rec("Sofia", "begin"))
	s.clear()
	_check(not s.any_deciding(), "clear -> nobody deciding")
	_check(not s.seen_signal(), "clear -> signal reset (new run may be mock)")

	if _failures == 0:
		print("test_deciding_indicator: all checks passed")
	quit(1 if _failures > 0 else 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `godot --headless --path godot-generative-agents/godot --script res://tests/test_deciding_indicator.gd` (or via the smoke script after Step 4)
Expected: FAIL — cannot load `res://scripts/deciding_indicator.gd` (does not exist).

- [ ] **Step 3: Implement the helper** (tabs)

Create `godot-generative-agents/godot/scripts/deciding_indicator.gd`:

```gdscript
extends RefCounted
## Pure per-agent decision-lifecycle state (issue #551), driven by the backend's
## `{kind:"deciding", agent, state:"begin"|"end", step, elapsed_ms?}` feed records.
## viewer.gd feeds it each record and reads is_deciding()/any_deciding() to drive
## per-agent "thinking" bubbles and the global badge fallback. No scene, no sim
## knowledge. Headless-tested (tests/test_deciding_indicator.gd). The authoritative
## per-agent signal #372 could only infer globally from a frame stall.

var _deciding := {}   # agent name -> true while mid-decision
var _seen := false    # has any `deciding` record arrived this run?


func apply(rec: Dictionary) -> void:
	var agent := String(rec.get("agent", ""))
	if agent == "":
		return  # malformed record: ignore
	_seen = true
	match String(rec.get("state", "")):
		"begin":
			_deciding[agent] = true
		"end":
			_deciding.erase(agent)


func is_deciding(agent: String) -> bool:
	return _deciding.get(agent, false)


func any_deciding() -> bool:
	return not _deciding.is_empty()


func seen_signal() -> bool:
	# True once a real `deciding` record has arrived -> the viewer prefers this
	# authoritative signal over #372's stall-inference for the global badge.
	return _seen


func clear() -> void:
	# Teardown / backend restart (#549): drop all in-flight state so a dropped
	# `end` across a reconnect can't strand a bubble, and reset _seen so the badge
	# falls back to stall-inference until the (possibly mock) new run signals.
	_deciding.clear()
	_seen = false
```

- [ ] **Step 4: Register the test in the smoke script**

In `godot-generative-agents/run_smoke_test.sh`, beside the existing `test_thinking_indicator.gd` line (~49-52), add:
```bash
"$GODOT" --headless --path "$PROJECT_DIR" --script res://tests/test_deciding_indicator.gd 2>&1 \
  | tee /dev/stderr | grep -q "all checks passed"
```

- [ ] **Step 5: Run the smoke test to verify green**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: exit 0; output contains `test_deciding_indicator: all checks passed`.

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/godot/scripts/deciding_indicator.gd godot-generative-agents/godot/tests/test_deciding_indicator.gd godot-generative-agents/run_smoke_test.sh
git commit -m "feat(viewer): DecidingState per-agent lifecycle helper + headless test (#551)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Wire the viewer — per-agent bubbles + global-badge smart fallback

**Files:**
- Modify: `godot-generative-agents/godot/scripts/viewer.gd` (record dispatch `_apply_record` ~742; agent spawn `_spawn_agent` ~1106-1187; the `_deciding_state` member + init near ~322; the badge detection loop ~1765; teardown `_teardown_cast` and the #549 restart path ~668-677; `_process` for bubble animation)
- Modify: `godot-generative-agents/README.md` (note the new `deciding` feed kind)

**Interfaces:**
- Consumes: `DecidingState` (Task 4); the backend `deciding` feed record (Task 3).
- Produces: viewer behavior only (validated by the headless smoke test loading the scene). No new public API.

> This task is integration wiring in a large existing file; the smoke test (scene loads, no script errors) is the gate. Read each anchor before editing — line numbers are approximate. Use **tabs**.

- [ ] **Step 1: Add the `DecidingState` member + preload**

Near the top-of-file `const`/preload block and the `_thinking_badge` member (the explore found the badge instantiated ~322), add a member:
```gdscript
const DecidingState := preload("res://scripts/deciding_indicator.gd")
```
and in the same place the badge is created (~322), initialize:
```gdscript
	_deciding_state = DecidingState.new()
```
with the member declaration beside `_thinking` / `_thinking_badge` (~134 area):
```gdscript
var _deciding_state  # DecidingState: per-agent "deciding" lifecycle (#551)
```

- [ ] **Step 2: Route the `deciding` record in `_apply_record`**

In the `match String(record.get("kind", "")):` block (~742), add a case beside `"engine"`:
```gdscript
		"deciding":
			# Per-agent thinking lifecycle (#551): update state, refresh the
			# one affected agent's bubble.
			_deciding_state.apply(record)
			_refresh_deciding(String(record.get("agent", "")))
```

- [ ] **Step 3: Give each agent a "thinking" bubble node in `_spawn_agent`**

In `_spawn_agent` (~1106-1187), mirroring the existing speech `bubble` Label, add a second Label for the thinking cue as a child of `node`, hidden by default, and store it in the agent dict. After the speech-bubble block:
```gdscript
	# A "thinking…" bubble parked above the nameplate, shown only while this agent
	# is mid-decision (#551, driven by the backend `deciding` feed record). Styled
	# as a status cue, distinct from the #245 white speech balloon.
	var think := Label.new()
	think.add_theme_color_override("font_color", Color(0.96, 0.95, 0.90))
	think.add_theme_font_size_override("font_size", 13)
	think.visible = false
	think.mouse_filter = Control.MOUSE_FILTER_IGNORE
	node.add_child(think)
```
and extend the stored dict (the `_agents[name] = {...}` line ~1187) to include `think`:
```gdscript
	_agents[name] = {"node": node, "sprite": spr, "label": label, "bubble": bubble, "trail": trail, "think": think}
```
> Position `think` above the nameplate the same way the speech `bubble` is positioned in `_spawn_agent` — copy the bubble's offset/anchor lines and adjust the vertical offset so the two don't overlap. Match the surrounding code.

- [ ] **Step 4: Implement `_refresh_deciding` + animate in `_process`**

Add a helper (near `_refresh_bubble`, ~1900):
```gdscript
func _refresh_deciding(name: String) -> void:
	# Show/hide this agent's thinking bubble from the authoritative signal.
	if not _agents.has(name):
		return
	var think: Label = _agents[name]["think"]
	think.visible = _deciding_state.is_deciding(name)
```
and in `_process`, animate the ellipsis for every visible thinking bubble (reuse `ThinkingIndicator.ellipsis`, already preloaded for the badge):
```gdscript
	# Animate per-agent thinking bubbles (#551).
	var _dots := ThinkingIndicator.ellipsis(Time.get_ticks_msec())
	for _n in _agents:
		var _t: Label = _agents[_n]["think"]
		if _t.visible:
			_t.text = _dots
```
> If `ThinkingIndicator` isn't already preloaded in `viewer.gd`, add `const ThinkingIndicator := preload("res://scripts/thinking_indicator.gd")` beside the other consts.

- [ ] **Step 5: Global badge — prefer the real signal, fall back to stall-inference**

In the badge detection loop (~1765), replace the single `should_show(...)` assignment with a preference for the real signal when it has arrived:
```gdscript
	var stalled: bool
	if _deciding_state.seen_signal():
		stalled = _deciding_state.any_deciding()  # authoritative (#551)
	else:
		stalled = ThinkingIndicator.should_show(
			_is_live, _backend_run_state, i >= last,
			Time.get_ticks_msec() - _last_frame_ms, THINKING_STALL_MS)
	if stalled != _thinking:
		_thinking = stalled
		_thinking_badge.set_active(stalled)
		if _backend_run_state == "running":
			_panel.set_live_status("thinking…" if stalled else "following backend")
```

- [ ] **Step 6: Clear deciding state on teardown / restart**

In `_teardown_cast()` add (so a dropped `end` across a reconnect can't strand a bubble; the per-agent `think` nodes are freed with the cast):
```gdscript
	if _deciding_state != null:
		_deciding_state.clear()
```
The #549 restart path (~668-677) already calls `_teardown_cast()`, so it inherits the clear — confirm it does; if that path doesn't route through `_teardown_cast`, add the same `_deciding_state.clear()` there.

- [ ] **Step 7: Run the smoke test**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: exit 0 — every scene loads with no GDScript error (the viewer parses/instantiates the new nodes and members), and both indicator unit tests pass.

- [ ] **Step 8: Document the new feed kind**

In `godot-generative-agents/README.md`, in the live-feed/record section, add a one-line entry:
> `deciding` — a per-agent decision lifecycle record (`{agent, state: "begin"|"end", step, elapsed_ms?}`, #551), emitted under a real/scripted brain; the viewer shows a per-agent "thinking" bubble from it (and the global badge prefers it over stall-inference).

- [ ] **Step 9: Commit**

```bash
git add godot-generative-agents/godot/scripts/viewer.gd godot-generative-agents/README.md
git commit -m "feat(viewer): per-agent thinking bubbles from the deciding feed; badge smart fallback (#551)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (before opening the PR)

- [ ] `uv run pytest godot-generative-agents/tests/test_deciding_feed.py -v` — all green.
- [ ] `uv run pytest godot-generative-agents/tests/test_penn_live.py godot-generative-agents/tests/test_replay_contract.py -v` — the **byte-identical mock feed** + determinism still green.
- [ ] `uv run pytest godot-generative-agents/tests/ -q` — full backend suite green.
- [ ] `./godot-generative-agents/run_smoke_test.sh` — exit 0 (viewer loads; `test_deciding_indicator` + `test_thinking_indicator` pass).
- [ ] `uv run black --check godot-generative-agents/backend/run_simulation.py godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/backend/live.py godot-generative-agents/tests/test_deciding_feed.py` — clean.
- [ ] Manual, no key: `unset ANTHROPIC_API_KEY; uv run python godot-generative-agents/backend/penn/serve_penn.py --tick-seconds 0 --steps 30` (mock) then `GET /events` shows **no** `deciding` records; a scripted/real run shows begin/end pairs.
- [ ] `git status` — only the files this plan names, no minified tmj, no unrelated files.

## Self-Review notes (reconciled against the spec)

- **Spec coverage:** emit via `_decide_for` sink (Task 1) · stepper buffer + gate + drain (Task 2) · `live` feed publish (Task 3) · viewer `DecidingState` + test (Task 4) · viewer per-agent bubbles + smart-fallback badge + README (Task 5). #525 web companion + #359/#368 attribution are out of scope per the spec (no task). The per-tick `deciders` count is untouched.
- **Refinement noted:** the spec described "begin at submit / end at collect"; the plan realizes the same lifecycle by emitting **inside `_decide_for`** (begin at entry, end in `finally`), which is called exactly once per decision and never for a parked future — cleaner, and it fires `end` even if the brain raises (no stranded bubble).
- **Byte-identical guard** is an explicit test step in Tasks 1 and 2 and the final checks.
- **Type consistency:** `deciding_sink(name, state, step)`, `drain_deciding() -> list`, record keys `{agent, state, step, elapsed_ms?}`, and the GDScript `DecidingState.apply/is_deciding/any_deciding/seen_signal/clear` are used identically across tasks.
- **Implementer confirmations flagged inline:** the `ScriptedStepper`/`EventLog` test-harness API (Task 3 Step 1 note) and the exact viewer bubble-positioning/anchor lines + the #549 restart routing (Task 5 Steps 3/6) — read the real code, adjust to match, assertions/behavior are what matter.
