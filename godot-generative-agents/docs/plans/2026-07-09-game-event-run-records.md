# GameEvent Run-Record Persistence (#467) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the engine's `game.events` log into both run records — the baked replay artifacts and the live change feed — per the approved spec `godot-generative-agents/docs/specs/2026-07-09-game-event-run-records.md`.

**Architecture:** Three additive seams, all inside `godot-generative-agents/backend/`: (1) `simulate()` gains an `out_events` out-parameter (same convention as `out_memories`); (2) both bake writers persist it (top-level `"events"` in the Penn replay JSON; `events.json` in the generic exporter's sim folder); (3) `PennStepper.drain_events()` additionally yields new `game.events` entries as `kind: "game_event"` rows, which the existing tick-boundary publish in `backend.live` carries through `GET /events?since=` and the WS door unchanged.

**Tech Stack:** Python 3.12, pytest, FastAPI TestClient (server extra). Everything offline/mock — no API keys, no spend.

## Global Constraints

- **Backend-only:** every change lives under `godot-generative-agents/`. The engine (`text_adventure_games/`), `backend/live.py`, `backend/api.py`, and all viewer `.gd` files are **untouched**.
- **Record shape:** persisted records are `GameEvent.to_primitive()` dicts verbatim — `{"turn", "actor", "action", "summary", "payload"}` (the #305 `EventState` contract). The live feed alone adds `"kind": "game_event"`, mirroring the existing `llm_call` re-stamp.
- **No reshaping, filtering, or truncation** of events anywhere.
- All tests run offline under the mock brain; suites green (`uv run pytest godot-generative-agents/tests -q` and root `uv run pytest tests -q`); `uv run black .` clean before every commit.
- Commit only files this plan names. Work from the worktree root `/Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/events-record-467`.
- Branch `feat/events-record-467` is **stacked on `feat/boil-water-300`** (PR #465). Do not rebase onto anything else.

---

### Task 1: `simulate(out_events=...)` — the bake source

**Files:**
- Modify: `godot-generative-agents/backend/run_simulation.py` (signature ~line 315-334, docstring ~line 408, end-of-run block ~line 544-548)
- Create: `godot-generative-agents/tests/test_event_records.py`

**Interfaces:**
- Consumes: `game.events` (list of engine `GameEvent`s; `game, chars = build_world_fn(world_map)` at run_simulation.py:426) and `GameEvent.to_primitive()` (`text_adventure_games/events.py:39`).
- Produces: `simulate(..., out_events: list | None = None)` — after the run, the caller's list holds one `to_primitive()` dict per logged event, in log order. Tasks 2 and 3 rely on this exact keyword name.

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/tests/test_event_records.py`:

```python
"""Offline tests for persisting the GameEvent log into run records (#467).

The record shape everywhere is ``GameEvent.to_primitive()`` — the #305
``EventState`` contract: {turn, actor, action, summary, payload}. The live
feed's rows additionally carry ``kind: "game_event"`` (see serve_penn's
``drain_events``); the bake artifacts carry the dict verbatim.
"""

import datetime
import json
import sys

from backend.build_world import _normalize_personas, build_world
from backend.exporter import write_simulation
from backend.penn.penn_world import (
    PENN_EXTRA_ACTIONS,
    _furnish_boil_water,
    build_penn_world,
)
from backend.run_simulation import simulate


def _testa_sip_world():
    """The #300 acceptance scenario (mirrors test_boil_water.py's e2e test):
    a persona homed at Houston Hall whose first stop gets-and-drinks the
    murky water, so a ``sickness`` GameEvent is logged within ~5 steps."""
    pw = build_penn_world()
    persona = {
        "name": "Testa Sip",
        "home": "Houston Hall",
        "persona": "I am Testa Sip, a thirsty test persona.",
        "emoji": "🥤",
        "start_tile": [25, 109],
        "schedule": [
            {
                "place": "Houston Hall",
                "activity": "getting a drink of water",
                "emoji": "🥤",
                "steps": 3,
                "commands": ["get cup of murky water", "drink cup of murky water"],
            }
        ],
    }
    personas = _normalize_personas([persona])

    def build_fn(wm):
        game, characters = build_world(
            wm, personas, pw.locations, extra_actions=PENN_EXTRA_ACTIONS
        )
        _furnish_boil_water(game)
        return game, characters

    return pw, personas, build_fn


def test_simulate_out_events_carries_sickness_record():
    """#467 acceptance, bake source: the run's GameEvent log comes back
    through ``out_events`` with the sickness cause payload intact."""
    pw, personas, build_fn = _testa_sip_world()
    events: list = []
    simulate(
        pw.world_map,
        10,
        personas=personas,
        build_world_fn=build_fn,
        out_events=events,
    )
    sickness = [e for e in events if e["action"] == "sickness"]
    assert sickness, f"no sickness event in {events}"
    record = sickness[0]
    assert record["payload"] == {
        "item": "cup of murky water",
        "location": "Houston Hall",
    }
    assert record["actor"] == "Testa Sip"
    assert {"turn", "summary"} <= set(record)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py -v`
Expected: FAIL — `TypeError: simulate() got an unexpected keyword argument 'out_events'`.

- [ ] **Step 3: Implement `out_events`**

In `godot-generative-agents/backend/run_simulation.py`:

(a) Add the keyword to `simulate()`'s signature, directly after `out_plans: dict | None = None,` (~line 333):

```python
    out_events: list | None = None,
```

(b) In the docstring, after the `out_plans` paragraph (~line 408), add:

```python
    Pass an ``out_events`` list to collect the run's full ``GameEvent`` log
    (issue #467) as ``to_primitive()`` dicts — the #305 ``EventState`` shape
    the bake artifacts persist and the live feed publishes.
```

(c) After the `out_memories` hand-back block (currently lines 544-546, just before `return frames`), add:

```python
    # Hand back the run's full GameEvent log, if the caller asked for it
    # (issue #467). Already-serialized EventState dicts, so bake artifacts
    # and the live feed carry the identical record.
    if out_events is not None:
        out_events.extend(event.to_primitive() for event in game.events)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Regression + format, then commit**

Run: `uv run pytest godot-generative-agents/tests -q` (expected: all pass) and `uv run black .` (expected: reformats nothing outside your changes; run `uv run black --check .` after to confirm clean).

```bash
git add godot-generative-agents/backend/run_simulation.py godot-generative-agents/tests/test_event_records.py
git commit -m "feat(backend): simulate() out_events exposes the GameEvent log (#467)"
```

---

### Task 2: Penn replay bake — top-level `"events"` key

**Files:**
- Modify: `godot-generative-agents/backend/penn/generate_penn_replay.py` (the `memory_streams`/`simulate(...)` block ~line 179-186 and the `replay = {...}` dict ~line 191-220)
- Test: `godot-generative-agents/tests/test_event_records.py` (append)

**Interfaces:**
- Consumes: `simulate(..., out_events=events)` from Task 1.
- Produces: the baked replay JSON gains a top-level `"events"` array, parallel to `"frames"`/`"memory_streams"`. The Godot viewer reads only keys it knows (`viewer.gd:449`), so this is invisible to it by design.

- [ ] **Step 1: Write the failing test**

Append to `godot-generative-agents/tests/test_event_records.py`:

```python
def test_penn_replay_bake_writes_events_key(tmp_path, monkeypatch):
    """#467 acceptance, bake artifact: the replay JSON carries the run's
    event log as a top-level ``events`` array (empty is fine for a short
    run — presence and shape are the contract; the sickness *content* is
    pinned at the simulate() seam above)."""
    from backend.penn import generate_penn_replay

    out = tmp_path / "penn_replay.json"
    monkeypatch.setattr(
        sys, "argv", ["generate_penn_replay", "--steps", "8", "--out", str(out)]
    )
    assert generate_penn_replay.main() == 0
    replay = json.loads(out.read_text())
    assert isinstance(replay["events"], list)
    for record in replay["events"]:
        assert {"turn", "actor", "action", "summary", "payload"} <= set(record)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py::test_penn_replay_bake_writes_events_key -v`
Expected: FAIL — `KeyError: 'events'`.

- [ ] **Step 3: Implement the bake key**

In `godot-generative-agents/backend/penn/generate_penn_replay.py`, extend the collection block (~line 179) so the simulate call reads:

```python
    memory_streams: dict = {}
    events: list = []
    frames = simulate(
        pw.world_map,
        args.steps,
        personas=pw.personas,
        build_world_fn=pw.build_world_fn,
        out_memories=memory_streams,
        out_events=events,
        extra_action_names=PENN_ACTION_VERBS,
    )
```

and in the `replay = {...}` dict, directly after the `"memory_streams": memory_streams,` line, add:

```python
        # The run's GameEvent log (#467): EventState-shaped records straight
        # from GameEvent.to_primitive(). The viewer ignores unknown top-level
        # keys; post-hoc metrics (#299) read this instead of the memory stream.
        "events": events,
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Regression + format, then commit**

Run: `uv run pytest godot-generative-agents/tests -q` and `uv run black --check .` (both clean).

```bash
git add godot-generative-agents/backend/penn/generate_penn_replay.py godot-generative-agents/tests/test_event_records.py
git commit -m "feat(backend): Penn replay bake persists the GameEvent log (#467)"
```

---

### Task 3: Generic exporter — `events.json` + Smallville main threading

**Files:**
- Modify: `godot-generative-agents/backend/exporter.py` (`write_simulation` signature ~line 69-78, docstring, body just before `return sim_dir` ~line 169)
- Modify: `godot-generative-agents/backend/run_simulation.py` (`main()`: the `simulate(...)` call ~line 814-832 and the `exporter.write_simulation(...)` call ~line 849-859)
- Test: `godot-generative-agents/tests/test_event_records.py` (append)

**Interfaces:**
- Consumes: `simulate(..., out_events=...)` from Task 1; `_dump(path, obj)` (exporter.py:172).
- Produces: `write_simulation(..., events: list | None = None)`; when `events` is not None (even `[]`), the sim folder contains `events.json` holding exactly that array.

- [ ] **Step 1: Write the failing test**

Append to `godot-generative-agents/tests/test_event_records.py`:

```python
def test_write_simulation_writes_events_json(tmp_path):
    """#467: the generic exporter persists the event log beside the other
    run artifacts. frames=[] keeps the fixture minimal — write_simulation
    tolerates a missing base personas dir and zero steps."""
    events = [
        {
            "turn": 1,
            "actor": "A",
            "action": "sickness",
            "summary": "A got sick drinking cup",
            "payload": {"item": "cup", "location": "Houston Hall"},
        }
    ]
    sim_dir = write_simulation(
        storage_root=str(tmp_path),
        sim_code="test_sim",
        frames=[],
        start_dt=datetime.datetime(2023, 2, 13, 8, 0, 0),
        start_tiles={"A": (0, 0)},
        base_personas_dir=str(tmp_path / "no_such_dir"),
        events=events,
    )
    with open(f"{sim_dir}/events.json") as fh:
        assert json.load(fh) == events
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py::test_write_simulation_writes_events_json -v`
Expected: FAIL — `TypeError: write_simulation() got an unexpected keyword argument 'events'`.

- [ ] **Step 3: Implement `events.json`**

In `godot-generative-agents/backend/exporter.py`:

(a) Add to `write_simulation`'s signature after `plans: dict | None = None,`:

```python
    events: list | None = None,
```

(b) Add to the docstring, after the `plans` paragraph:

```python
    ``events`` (a list of ``GameEvent.to_primitive()`` dicts, from
    ``simulate(out_events=...)``) is the run's engine event log (issue #467);
    we write it to ``events.json`` so post-hoc metrics (#299) can count events
    and their causes from the run record alone.
    """
```

(c) In the body, directly before `return sim_dir`, add:

```python
    # The run's GameEvent log (#467): one JSON array of EventState-shaped
    # records, so a sickness (or any future event) is queryable after the
    # fact with its cause payload.
    if events is not None:
        _dump(os.path.join(sim_dir, "events.json"), events)
```

(d) In `run_simulation.py`'s `main()`: immediately before the `simulate(` call (~line 814), the surrounding code already collects `memory_streams` and `plans`; add beside them:

```python
    events: list = []
```

then add `out_events=events,` to the `simulate(...)` call (after `out_plans=plans,`), and add `events=events,` to the `exporter.write_simulation(...)` call (after `plans=plans,`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Regression + format, then commit**

Run: `uv run pytest godot-generative-agents/tests -q`, root `uv run pytest tests -q` (main()'s callers live under root tests too), and `uv run black --check .` — all clean.

```bash
git add godot-generative-agents/backend/exporter.py godot-generative-agents/backend/run_simulation.py godot-generative-agents/tests/test_event_records.py
git commit -m "feat(backend): exporter writes events.json; Smallville bake threads it (#467)"
```

---

### Task 4: Live feed — `PennStepper.drain_events()` publishes `game_event` rows

**Files:**
- Modify: `godot-generative-agents/backend/penn/serve_penn.py` (`_build` ~line 318, `drain_events` ~line 446-459)
- Modify: `godot-generative-agents/README.md` (~line 262-265, the run-monitor feed sentence)
- Test: `godot-generative-agents/tests/test_event_records.py` (append) and `godot-generative-agents/tests/test_live_seam.py` (append)

**Interfaces:**
- Consumes: `self.game` (set in `_build`, serve_penn.py:318); `GameEvent.to_primitive()`; `backend.live`'s existing drain-and-publish (`live.py:187-202` drains under the app lock; `run_loop` publishes each row as a `kind: "engine"` envelope at the tick boundary, `live.py:253-255` — **do not modify live.py**).
- Produces: `drain_events()` returns the monitor's `llm_call` rows **plus** one `dict(event.to_primitive(), kind="game_event")` per `game.events` entry logged since the last drain; `reset()` restarts the cursor with the rebuilt game.

- [ ] **Step 1: Write the failing unit tests**

Append to `godot-generative-agents/tests/test_event_records.py`:

```python
def _game_event_rows(rows):
    return [r for r in rows if r.get("kind") == "game_event"]


def test_penn_stepper_drains_game_events_exactly_once():
    """#467 live half: drain_events yields each GameEvent once, stamped
    kind=game_event, alongside (not instead of) the llm_call rows."""
    from backend.penn.serve_penn import PennStepper

    stepper = PennStepper(num_steps=2)
    turn = stepper.game.turn
    stepper.game.log_event(
        "Sofia Ramirez", "sickness", summary="felt awful", payload={"item": "cup"}
    )
    assert _game_event_rows(stepper.drain_events()) == [
        {
            "turn": turn,
            "actor": "Sofia Ramirez",
            "action": "sickness",
            "summary": "felt awful",
            "payload": {"item": "cup"},
            "kind": "game_event",
        }
    ]
    assert _game_event_rows(stepper.drain_events()) == []


def test_penn_stepper_reset_restarts_event_cursor():
    from backend.penn.serve_penn import PennStepper

    stepper = PennStepper(num_steps=2)
    stepper.game.log_event("a", "narration", summary="before reset")
    stepper.drain_events()
    stepper.reset()
    stepper.game.log_event("b", "narration", summary="after reset")
    rows = _game_event_rows(stepper.drain_events())
    assert [r["actor"] for r in rows] == ["b"]
```

Append to `godot-generative-agents/tests/test_live_seam.py` (uses that file's existing `_walker`, `_live_client`, `_wait_for_events` helpers):

```python
# --- game_event rows on the engine feed (#467) ------------------------------


def test_game_event_rows_ride_the_engine_feed():
    """#467: a stepper's drained game_event rows come out of GET /events inside
    the ``engine`` envelope, exactly like llm_call rows (#398). serve_penn's
    PennStepper produces these rows for real (test_event_records.py); here a
    scripted stepper pins the transport."""
    record = {
        "turn": 1,
        "actor": "Sofia Ramirez",
        "action": "sickness",
        "summary": "Sofia Ramirez got sick drinking cup of murky water",
        "payload": {"item": "cup of murky water", "location": "Houston Hall"},
        "kind": "game_event",
    }
    stepper = _walker(on_tick=lambda step: [dict(record)] if step == 0 else [])
    with _live_client(stepper=stepper) as c:
        events = _wait_for_events(
            c,
            lambda evs: any(
                e["kind"] == "engine" and e["event"].get("kind") == "game_event"
                for e in evs
            ),
        )
    rows = [
        e["event"]
        for e in events
        if e["kind"] == "engine" and e["event"].get("kind") == "game_event"
    ]
    assert rows == [record]
```

- [ ] **Step 2: Run them to verify the unit tests fail**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py -v`
Expected: the two new tests FAIL (no `game_event` rows drained). Note: `test_game_event_rows_ride_the_engine_feed` PASSES already — it exercises the existing transport with a scripted stepper; it belongs to this task as the transport pin.

- [ ] **Step 3: Implement the drain**

In `godot-generative-agents/backend/penn/serve_penn.py`:

(a) In `_build`, directly after `self.game, self.chars = self.world.build_world_fn(self.world.world_map)` (~line 318), add:

```python
        # How much of game.events drain_events() has already published
        # (#467). Lives in _build so reset() restarts it with the new game.
        self._events_seen = 0
```

(b) Replace the whole `drain_events` method with:

```python
    def drain_events(self) -> list:
        """New change-feed rows formed during the last ``tick()`` (#398, #467).

        ``backend.live`` probes this optional method after every tick and
        publishes each returned dict as a ``kind: "engine"`` change-feed
        record. Two row types ride it, told apart by their inner ``kind``:

        * ``"llm_call"`` -- the request monitor's kept records (a flattened
          :class:`~text_adventure_games.usage.CallRecord` plus ``role``/
          ``call_no``/``cum_cost_usd``/``time``), so the viewer's run monitor
          shows the same one-line-per-request log the terminal prints (#398).
        * ``"game_event"`` -- the engine ``GameEvent``s logged since the last
          drain (#467), ``to_primitive()`` dicts (the #305 EventState shape,
          identical to what the replay bake persists), e.g. the boil-water
          ``sickness`` events (#465).
        """
        rows = []
        if self.monitor is not None:
            rows.extend(dict(rec, kind="llm_call") for rec in self.monitor.drain())
        new_events = self.game.events[self._events_seen :]
        self._events_seen = len(self.game.events)
        rows.extend(
            dict(event.to_primitive(), kind="game_event") for event in new_events
        )
        return rows
```

(c) In `godot-generative-agents/README.md`, the run-monitor paragraph ends with the sentence "The rows ride the live event feed (`serve_penn`'s `drain_events()` publishes the monitor's records as `llm_call` events), so the box needs no extra polling — and `--no-monitor` silences it together with the terminal." Append one sentence directly after it:

```markdown
Engine `GameEvent`s (e.g. the boil-water `sickness` event) ride the same feed
as `game_event` records (#467), rendered as plain rows in the same box.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_event_records.py godot-generative-agents/tests/test_live_seam.py -v`
Expected: PASS (all, including the two pre-existing-suite files' tests).

- [ ] **Step 5: Regression + format, then commit**

Run: `uv run pytest godot-generative-agents/tests -q` and `uv run black --check .` — clean.

```bash
git add godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_event_records.py godot-generative-agents/tests/test_live_seam.py godot-generative-agents/README.md
git commit -m "feat(backend): live feed publishes GameEvents as game_event rows (#467)"
```

---

### Task 5: Full verification, push, stacked PR

**Files:** none created/modified (verification + PR only).

- [ ] **Step 1: Full suites**

From the worktree root:

```bash
uv run pytest godot-generative-agents/tests -q   # expected: all pass (90+)
uv run pytest tests -q                            # expected: 1342+ passed, 2 skipped
uv run black --check .                            # expected: clean
```

- [ ] **Step 2: Push the branch**

```bash
git -c credential.helper='!gh auth git-credential' push -u https://github.com/ccb/agent-sandbox.git feat/events-record-467
```

- [ ] **Step 3: Open the stacked PR**

Base is **`feat/boil-water-300`** (GitHub retargets to `godot-ga-main` automatically when #465 merges):

```bash
gh pr create --repo ccb/agent-sandbox --base feat/boil-water-300 \
  --title "feat(backend): persist the GameEvent log into run records (#467)" \
  --body "$(cat <<'EOF'
Implements #467 per the approved spec
(`godot-generative-agents/docs/specs/2026-07-09-game-event-run-records.md`).

- **Bake:** `simulate()` gains an `out_events` out-parameter (the
  `out_memories` convention); the Penn replay JSON gains a top-level
  `"events"` array and the generic exporter writes `events.json`.
- **Live:** `PennStepper.drain_events()` additionally yields new
  `game.events` entries as `kind: "game_event"` rows — the existing
  tick-boundary publish carries them through `GET /events?since=` and the
  WS door with zero changes to `live.py`/`api.py`; the viewer's run monitor
  already renders non-`llm_call` engine rows generically (#394).
- **Shape:** `GameEvent.to_primitive()` verbatim — the #305 `EventState`
  contract; no reshaping, filtering, or truncation.

**Stacked on #465** (uses its `sickness` event as the acceptance scenario);
GitHub will retarget to `godot-ga-main` when #465 merges.

Closes #467. Refs #299, #300, #305, #349, #465.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Notes

- Spec coverage: simulate seam (Task 1), Penn replay key (Task 2), exporter + Smallville threading (Task 3), live drain + viewer-docs sentence (Task 4), acceptance/verification (Tasks 1-4 tests + Task 5). All spec sections have a task.
- The live transport test predates the drain implementation by design (it pins the unchanged envelope path with a scripted stepper); the failing-first TDD cycle in Task 4 is carried by the two PennStepper unit tests.
- Type consistency: `out_events: list | None` (Tasks 1-3), `events: list | None` (Task 3 exporter), `kind: "game_event"` literal (Task 4 + tests) — names match across tasks.
