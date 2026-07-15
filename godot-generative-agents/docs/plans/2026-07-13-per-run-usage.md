# Per-Run Usage View (#526) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /usage` gains additive `run_calls`/`run_cost_usd` fields (this run's slice of the lifetime ledger), and RunStore run rows record run-scoped cost instead of the server's lifetime total.

**Architecture:** `PennStepper._build()` snapshots the ledger position (count + cost) at every world build — the same boundary that opens a RunStore run — and a new probed-optional `run_usage()` method reports the delta. The `/usage` handler merges that dict when the stepper offers it (the existing `ledger`/`drain_events` optional-attribute idiom); `_persist_tick` subtracts the baseline so run rows carry the run's own spend. The engine `UsageLedger` is untouched — the lifetime budget gate keeps its meaning.

**Tech Stack:** Python 3.12, pytest; fastapi TestClient (already gated by `pytest.importorskip` in the endpoint-test file).

**Spec:** `godot-generative-agents/docs/specs/2026-07-13-per-run-usage.md` (committed 6912c6d)

## Global Constraints

- Branch: `feat/per-run-usage-526` off `godot-ga-main`; PR targets `godot-ga-main` (backend + tests only).
- `text_adventure_games/usage.py` and the root `tests/` are UNTOUCHED — no engine change, no main-track files.
- All existing `/usage` fields (`calls`, `total_cost_usd`, `by_actor`, token totals, `over_budget`, `max_cost_usd`, `remaining_budget_usd`) stay byte-identical; the new fields are additive only.
- The no-ledger zeroed branch of `/usage` and steppers without `run_usage` serve today's response shape exactly (no `run_*` keys).
- Run tests from the repo root; `uv run black .` before every commit; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Never `git add -A` / `git add .` — add the named files explicitly.

---

### Task 1: Stepper baseline, `run_usage()`, and the run-scoped RunStore cost

**Files:**
- Modify: `godot-generative-agents/backend/penn/serve_penn.py` (`_build` tail ~line 397; a new method near the `run_id` property ~line 410; `_persist_tick` ~line 504)
- Modify: `godot-generative-agents/backend/README.md` (RunStore section, one sentence)
- Test: `godot-generative-agents/tests/test_penn_live.py`

**Interfaces:**
- Consumes: `self.ledger` (`UsageLedger`: `records` list, `total_cost_usd()`), the existing `_build()`/`reset()`/`_persist_tick()` structure.
- Produces: `PennStepper.run_usage() -> dict` returning exactly `{"run_calls": int, "run_cost_usd": float}` — Task 2's `/usage` merge and its docs rely on this name and shape. Also `self._run_ledger_calls_base: int` / `self._run_ledger_cost_base: float` set in `_build()`.

- [ ] **Step 1: Write the failing test**

In `godot-generative-agents/tests/test_penn_live.py`, add to the imports (after the `from backend.run_store import RunStore` line):

```python
from text_adventure_games.usage import CallRecord, Usage  # noqa: E402
```

Add after `test_stepper_persists_game_events` (keep the persistence tests together):

```python
def _spend(ledger, cost):
    # Synthetic spend: the mock brain bills $0, so tests inject priced
    # records to make the per-run arithmetic visible.
    ledger.record(
        CallRecord(
            usage=Usage(provider="mock", model="mock", input_tokens=10),
            cost_usd=cost,
            actor="Diego Torres",
        )
    )


def test_run_usage_rebaselines_on_reset_and_run_rows_carry_run_cost(tmp_path):
    # The #526 per-run view: run_usage() is this run's slice of the ledger,
    # reset() re-baselines it, and the lifetime ledger (the budget gate's
    # basis) keeps counting. The RunStore row now records the RUN's spend --
    # pre-#526 it stored the lifetime total, so run #2 included run #1.
    # NOTE: mock-brain ticks append $0 CallRecords (the schedule clients ARE
    # the brains), so exact run_calls values are only pinned at tick-free
    # points; across ticks the test pins COST, which $0 records never move.
    store = RunStore(tmp_path / "runs")
    stepper = PennStepper(num_steps=3, world=build_penn_world(), run_store=store)
    assert stepper.run_usage() == {"run_calls": 0, "run_cost_usd": 0.0}
    _spend(stepper.ledger, 0.25)
    _spend(stepper.ledger, 0.05)
    assert stepper.run_usage() == {"run_calls": 2, "run_cost_usd": 0.3}
    stepper.tick()
    first = stepper.run_id
    assert stepper.run_usage()["run_cost_usd"] == pytest.approx(0.3)
    assert store.get_run(first)["cost"] == pytest.approx(0.3)
    lifetime_calls = stepper.ledger.summary()["calls"]  # spends + mock records
    stepper.reset()
    # The new run starts from zero...
    assert stepper.run_usage() == {"run_calls": 0, "run_cost_usd": 0.0}
    # ...while the lifetime ledger keeps everything, so a tripped cost
    # ceiling stays tripped across the reset.
    assert stepper.ledger.summary()["calls"] == lifetime_calls
    assert stepper.ledger.total_cost_usd() == pytest.approx(0.3)
    stepper.ledger.max_cost_usd = 0.2
    assert stepper.ledger.over_budget()
    stepper.ledger.max_cost_usd = None  # disarm so ticks keep running below
    _spend(stepper.ledger, 0.1)
    assert stepper.run_usage() == {"run_calls": 1, "run_cost_usd": 0.1}
    stepper.tick()
    second = stepper.run_id
    assert stepper.run_usage()["run_cost_usd"] == pytest.approx(0.1)
    assert store.get_run(second)["cost"] == pytest.approx(0.1)  # not 0.4
    # No store required: a bare stepper offers the same view.
    assert PennStepper(num_steps=1, world=build_penn_world()).run_usage() == {
        "run_calls": 0,
        "run_cost_usd": 0.0,
    }
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_penn_live.py::test_run_usage_rebaselines_on_reset_and_run_rows_carry_run_cost -v`
Expected: FAIL with `AttributeError: 'PennStepper' object has no attribute 'run_usage'`

- [ ] **Step 3: Implement**

In `godot-generative-agents/backend/penn/serve_penn.py`:

3a. In `_build()`, directly after `self._step_idx = 0` (line ~397) and before the run-open block (`# Open this day's run in the store (#304)...`), insert:

```python
        # Per-run ledger baseline (#526): the ledger itself survives resets
        # on purpose (the cost ceiling is lifetime -- money spent stays
        # spent), so the per-run view SUBTRACTS this snapshot instead of
        # rebasing anything. Same boundary as the store's run id above.
        self._run_ledger_calls_base = len(self.ledger.records)
        self._run_ledger_cost_base = self.ledger.total_cost_usd()
```

3b. Add the method directly after the `run_id` property (line ~412):

```python
    def run_usage(self) -> dict:
        """This run's slice of the lifetime ledger (#526).

        ``GET /usage`` probes for this optional method and merges the dict
        beside the (unchanged) lifetime totals, so the dashboard's run strip
        can agree with its per-run call log. The budget gate stays lifetime.
        """
        return {
            "run_calls": len(self.ledger.records) - self._run_ledger_calls_base,
            "run_cost_usd": round(
                self.ledger.total_cost_usd() - self._run_ledger_cost_base, 6
            ),
        }
```

3c. In `_persist_tick()`, change the `update_run` cost argument (line ~506):

```python
        self.run_store.update_run(
            self._run_id,
            # The RUN's spend, not the server's lifetime total (#526) -- a
            # post-reset run's row no longer includes earlier runs' cost.
            cost=self.ledger.total_cost_usd() - self._run_ledger_cost_base,
            steps=self._step_idx + 1,
        )
```

3d. In `godot-generative-agents/backend/README.md`, in the "## RunStore: durable runs (#304)" section, append one sentence to the paragraph that starts "Two opt-in producers:" (after "...a persisted bake equals its replay file."):

```markdown
A live run row's `cost` is that run's own spend (per-run ledger baseline,
#526); the budget gate (`max_cost_usd`) stays lifetime.
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest godot-generative-agents/tests/test_penn_live.py -q`
Expected: all pass (the new test plus the existing persistence/byte-identity pins — `test_stepper_persists_frames_memories_and_finish` asserts `run["cost"] == 0.0` for a mock run, which stays true since baseline and total are both ~0 there).

- [ ] **Step 5: Format and commit**

```bash
uv run black godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_penn_live.py
git add godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_penn_live.py godot-generative-agents/backend/README.md
git commit -m "feat(backend): per-run ledger baseline — PennStepper.run_usage() + run-scoped RunStore cost (#526)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `GET /usage` merges the run view + docs

**Files:**
- Modify: `godot-generative-agents/backend/api.py` (the `/usage` handler, lines ~1064-1091)
- Modify: `godot-generative-agents/backend/live.py` (the `SimStepper` docstring's optional-attribute list ~lines 49-57, and one sentence in `ScriptedStepper`'s docstring ~line 271)
- Test: `godot-generative-agents/tests/test_live_seam.py`

**Interfaces:**
- Consumes: Task 1's `run_usage() -> {"run_calls": int, "run_cost_usd": float}`; `create_app`'s in-scope `stepper` param; `ScriptedStepper` (supports post-construction attributes — its docstring already blesses `.ledger`).
- Produces: `/usage` responses carrying `run_calls`/`run_cost_usd` when the stepper offers `run_usage` — what the web strip will consume (out of scope here; noted on #526 after merge).

- [ ] **Step 1: Write the failing tests**

In `godot-generative-agents/tests/test_live_seam.py`, add to the imports (after the `from text_adventure_games import games, things` line):

```python
from text_adventure_games.usage import UsageLedger  # noqa: E402
```

Add at the end of the file:

```python
# --- GET /usage per-run view (#526) -----------------------------------------


def test_usage_merges_the_stepper_run_view():
    # A stepper offering run_usage() gets its per-run fields merged beside
    # the lifetime summary; the lifetime fields themselves are untouched.
    stepper = _walker()
    stepper.ledger = UsageLedger()
    stepper.run_usage = lambda: {"run_calls": 3, "run_cost_usd": 0.02}
    with _live_client(stepper, start_paused=True) as client:
        body = client.get("/usage").json()
    assert body["available"] is True
    assert body["calls"] == 0  # lifetime summary unchanged
    assert (body["run_calls"], body["run_cost_usd"]) == (3, 0.02)


def test_usage_without_run_view_keeps_todays_shape():
    # A stepper without run_usage (the generic case) serves the pre-#526
    # response exactly -- no run_* keys appear.
    stepper = _walker()
    stepper.ledger = UsageLedger()
    with _live_client(stepper, start_paused=True) as client:
        body = client.get("/usage").json()
    assert body["available"] is True
    assert "run_calls" not in body and "run_cost_usd" not in body
```

- [ ] **Step 2: Run them to verify one fails**

Run: `uv run pytest godot-generative-agents/tests/test_live_seam.py -q -k usage`
Expected: `test_usage_merges_the_stepper_run_view` FAILS (`KeyError: 'run_calls'`); `test_usage_without_run_view_keeps_todays_shape` PASSES (pins today's shape).

- [ ] **Step 3: Implement**

3a. In `godot-generative-agents/backend/api.py`, in the `/usage` handler, insert before `return summary` (after the `remaining_budget_usd` block, line ~1090):

```python
            # The per-run slice (#526): additive fields the dashboard's run
            # strip shows beside the (unchanged) lifetime totals + budget --
            # probed like `ledger`/`drain_events`, so steppers without it
            # serve exactly the pre-#526 shape.
            run_usage = getattr(stepper, "run_usage", None)
            if callable(run_usage):
                summary.update(run_usage())
            return summary
```

3b. In `godot-generative-agents/backend/live.py`, in the `SimStepper` docstring's optional-attribute list (after the `drain_events()` bullet, ~line 57), add:

```
    * ``run_usage() -> dict`` -- additive per-run usage fields
      (``run_calls``/``run_cost_usd``) merged into ``GET /usage`` beside the
      lifetime summary (#526); the ledger itself stays lifetime.
```

(Match the surrounding bullet indentation/reST style exactly.)

3c. In `ScriptedStepper`'s docstring, extend the last sentence (~line 271-272) from "Set ``.ledger`` after construction to back ``GET /usage``." to:

```
    Set ``.ledger`` (and optionally ``.run_usage``) after construction to
    back ``GET /usage``.
```

- [ ] **Step 4: Run the tests, then the full godot suite**

Run: `uv run pytest godot-generative-agents/tests/test_live_seam.py -q`
Expected: all pass.
Run: `uv run pytest godot-generative-agents/tests/ -q`
Expected: all pass.
Run: `uv run black --check .`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/api.py godot-generative-agents/backend/live.py godot-generative-agents/tests/test_live_seam.py
git commit -m "feat(backend): GET /usage merges the stepper's per-run view (#526)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
