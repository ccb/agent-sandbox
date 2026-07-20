# Boil-from-Aversive-Memory Experiment + Minimal Thirst Stakes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone experiment that measures whether a live Haiku brain, carrying a seeded aversive memory, chooses to boil murky water before drinking it — reported as a boil-before-drink rate vs a no-memory control — backed by minimal Penn-local thirst/sickness stakes and an authoritative, action-recorded outcome signal.

**Architecture:** All Penn-local under `godot-generative-agents/backend/`. A tiny `drives` helper accrues thirst per tick (opt-in per character, so non-experiment runs are byte-identical); `DrinkPenn` stamps the causal drink outcome as first-class character state; `observe_and_decide` surfaces thirst/sickness in the decide prompt *after* retrieval (so the mock bake stays byte-identical); `attach_agents` seeds an opt-in aversion memory at t=0; a new `experiments/boil_from_memory.py` runs N live trials per arm and reads the outcome flags directly.

**Tech Stack:** Python 3.12 (uv), pytest, the existing `run_simulation.simulate` / `build_penn_world` / `MockLlmClient` / `create_llm_client`. No new dependencies.

**Spec:** `godot-generative-agents/docs/specs/2026-07-17-boil-from-memory-experiment.md`

## Global Constraints

- Branch: `feat/boil-from-memory-595` (off `godot-ga-main`; worktree `.claude/worktrees/boil-from-memory-595`). Review track: **godot-ga-main** (Penn-local, backend-only).
- Touch ONLY under `godot-generative-agents/` (`backend/…` + `tests/…` + `docs/…`). Do NOT touch `text_adventure_games/` or root `tests/` — the mechanics stay Penn-local.
- NEVER `git add -A` / `git add .` — stage exact paths only.
- Every commit message ends with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Comment/docstring style uses double-hyphen `--`, not em dashes; match the surrounding files.
- **Byte-identical guard:** the default mock bake must not change. A character with no `thirst_rate` never accrues thirst; the thirst/sickness prompt lines append *after* retrieval so the retrieved-memory list is unaffected; `seed_memories` is absent on every existing persona. `generate_penn_replay.py` (default `--scenario penn`) and the determinism suite pin this.
- Offline tests use the scripted/mock brain — no `ANTHROPIC_API_KEY`, no network. The live measurement is a manual, gated run.
- Run commands from the repo root: `/Users/yh/Documents/GitHub/agent-sandbox`; Python via `uv run`. Use `uv sync --extra dev` before pytest/black.

---

### Task 1: `drives.accrue_thirst` — opt-in per-tick thirst → `IS_THIRSTY`

**Files:**
- Create: `godot-generative-agents/backend/drives.py`
- Test: `godot-generative-agents/tests/test_drives.py`

**Interfaces:**
- Consumes: `text_adventure_games.things.Character` (has `get_property`/`set_property`; properties default to `False`/absent); `text_adventure_games.enums.Property.IS_THIRSTY` (value `"is_thirsty"`).
- Produces: `accrue_thirst(char) -> None` — reads the character's own `thirst_rate` (int, default 0 = off) and `thirst_threshold` (int, default 3) properties, adds `thirst_rate` to a `thirst` counter, and sets `IS_THIRSTY` true once `thirst >= thirst_threshold`. A no-op when `thirst_rate` is 0/absent.

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/tests/test_drives.py`:

```python
"""Minimal Penn-local thirst drive (#594): a per-tick accrual that flips the
engine's IS_THIRSTY once a threshold is crossed. Opt-in per character so
non-experiment runs never accrue. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_drives.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.drives import accrue_thirst  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402
from text_adventure_games.things import Character  # noqa: E402


def _char():
    return Character("Maya", "a student", "A thirsty student.")


def test_no_thirst_rate_is_a_noop():
    c = _char()
    accrue_thirst(c)
    assert not c.get_property(Property.IS_THIRSTY)
    assert not c.get_property("thirst")  # nothing accrued


def test_thirst_accrues_and_flips_is_thirsty_at_threshold():
    c = _char()
    c.set_property("thirst_rate", 1)
    c.set_property("thirst_threshold", 3)
    accrue_thirst(c)  # 1
    accrue_thirst(c)  # 2
    assert not c.get_property(Property.IS_THIRSTY)
    accrue_thirst(c)  # 3 -> threshold
    assert c.get_property(Property.IS_THIRSTY)
    assert c.get_property("thirst") == 3


def test_thirst_rate_greater_than_one_reaches_threshold_faster():
    c = _char()
    c.set_property("thirst_rate", 3)
    c.set_property("thirst_threshold", 3)
    accrue_thirst(c)
    assert c.get_property(Property.IS_THIRSTY)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_drives.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.drives'`.

- [ ] **Step 3: Write the module**

Create `godot-generative-agents/backend/drives.py`:

```python
"""Minimal Penn-local needs/drives (#594).

A first, deliberately small slice: a thirst counter that rises per tick and, past
a threshold, flips the engine's ``Property.IS_THIRSTY`` (which ``Drink`` already
clears). It is **opt-in per character** -- a character with no ``thirst_rate`` never
accrues, so the default mock bake is byte-identical. No incapacitation, energy, or
death: max thirst simply holds ``IS_THIRSTY`` true (a persistent drive). A generic
engine drive can be lifted later (as #464 follows #300); this stays backend-local.
"""

from text_adventure_games.enums import Property

_DEFAULT_THRESHOLD = 3


def accrue_thirst(char) -> None:
    """Advance *char*'s thirst by its ``thirst_rate`` and flip ``IS_THIRSTY`` at
    the threshold. A no-op when ``thirst_rate`` is 0/absent (the default), so a
    non-experiment persona is untouched."""
    rate = char.get_property("thirst_rate") or 0
    if not rate:
        return
    threshold = char.get_property("thirst_threshold") or _DEFAULT_THRESHOLD
    thirst = (char.get_property("thirst") or 0) + rate
    char.set_property("thirst", thirst)
    if thirst >= threshold:
        char.set_property(Property.IS_THIRSTY, True)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest godot-generative-agents/tests/test_drives.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Format + commit**

```bash
uv run black godot-generative-agents/backend/drives.py godot-generative-agents/tests/test_drives.py
git add godot-generative-agents/backend/drives.py godot-generative-agents/tests/test_drives.py
git commit -m "feat(backend): opt-in per-tick thirst drive (#594)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Wire thirst accrual into the step loop

**Files:**
- Modify: `godot-generative-agents/backend/run_simulation.py` (the per-step per-agent loop in `simulate`)
- Test: `godot-generative-agents/tests/test_drives.py` (extend)

**Interfaces:**
- Consumes: `accrue_thirst(char)` (Task 1); the per-step loop in `simulate` that iterates characters and calls `observe_and_decide` (search `observe_and_decide(` in `run_simulation.py` to find the callsite).
- Produces: after `simulate` runs N steps, a persona with `thirst_rate > 0` has accrued thirst and (past threshold) `IS_THIRSTY`; a persona without `thirst_rate` is unchanged.

- [ ] **Step 1: Write the failing test**

Append to `test_drives.py`:

```python
def test_simulate_accrues_thirst_for_an_opted_in_persona():
    # A persona with thirst_rate accrues over a short run; the default personas
    # (no thirst_rate) never do -> the bake stays byte-identical.
    from backend.run_simulation import simulate
    from penn_world import build_penn_world

    pw = build_penn_world()

    def _opt_in(personas):
        personas[0]["thirst_rate"] = 1
        personas[0]["thirst_threshold"] = 2
        return personas

    personas = _opt_in([dict(p) for p in pw.personas])
    chars_out: dict = {}

    def build_capture(world_map):
        game, chars = pw.build_world_fn(world_map)
        chars_out.update(chars)
        return game, chars

    simulate(
        pw.world_map, 5, personas=personas, build_world_fn=build_capture
    )
    target = chars_out[personas[0]["name"]]
    assert target.get_property("thirst") >= 2
    assert target.get_property("is_thirsty")
```

> If threading `thirst_rate` from the persona spec onto the built `Character` is not already done by `build_world`/`attach_agents`, this test also drives Task 2's second half: the loop must read the rate from the character. The simplest wiring is that `attach_agents` copies `spec.get("thirst_rate")`/`spec.get("thirst_threshold")` onto the character as properties (mirroring how it copies `vision_r`). Add that copy in `attach_agents` (cognition.py) if absent, guarded so absent keys set nothing.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_drives.py::test_simulate_accrues_thirst_for_an_opted_in_persona -v`
Expected: FAIL (thirst not accrued — no hook yet).

- [ ] **Step 3: Copy the thirst config onto the character in `attach_agents`**

In `godot-generative-agents/backend/cognition.py` `attach_agents`, near where it sets `char.vision_r = spec.get("vision_r", vision_r)`, add (guarded so absent keys set nothing):

```python
        # Opt-in thirst drive (#594): copy the per-persona rate/threshold onto the
        # character as properties the step loop's accrue_thirst reads. Absent keys
        # set nothing, so a normal persona never accrues -> byte-identical bake.
        if spec.get("thirst_rate"):
            char.set_property("thirst_rate", spec["thirst_rate"])
        if spec.get("thirst_threshold"):
            char.set_property("thirst_threshold", spec["thirst_threshold"])
```

- [ ] **Step 4: Call `accrue_thirst` per tick in `simulate`**

In `run_simulation.py`, add the import near the other `backend` imports:

```python
from backend.drives import accrue_thirst
```

Find the per-step loop over characters (the one that calls `observe_and_decide(game, char, ...)`). Immediately before the decision for each living character that step, add:

```python
            accrue_thirst(char)
```

(Place it so it runs once per character per step, before that character decides — so the raised `IS_THIRSTY` is visible to the same tick's decide.)

- [ ] **Step 5: Run to verify it passes + byte-identical guard**

```bash
uv run pytest godot-generative-agents/tests/test_drives.py -v
uv run pytest godot-generative-agents/tests/test_penn_live.py::test_stepper_matches_simulate_prefix -v
```
Expected: drives tests PASS; the simulate-equivalence test still PASS (no default persona has `thirst_rate`, so the loop's `accrue_thirst` is a no-op → byte-identical).

- [ ] **Step 6: Format + commit**

```bash
uv run black godot-generative-agents/backend/run_simulation.py godot-generative-agents/backend/cognition.py godot-generative-agents/tests/test_drives.py
git add godot-generative-agents/backend/run_simulation.py godot-generative-agents/backend/cognition.py godot-generative-agents/tests/test_drives.py
git commit -m "feat(backend): accrue thirst per tick for opted-in personas (#594)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `DrinkPenn` stamps the authoritative drink outcome

**Files:**
- Modify: `godot-generative-agents/backend/actions.py` (`DrinkPenn.apply_effects`, ~line 154)
- Test: `godot-generative-agents/tests/test_boil_water.py` (extend — it already builds tiny worlds with `DrinkPenn`)

**Interfaces:**
- Consumes: `DrinkPenn` (subclass of `consume.Drink`); character properties default absent.
- Produces: after a drink, the drinker carries authoritative counters — `drank_unboiled` (incremented when the item `requires_boiling` and is not `is_boiled`) and `drank_boiled` (incremented on any other successful, non-fatal drink: boiled water, or water that never required boiling). The harness reads these; no event-log parsing.

- [ ] **Step 1: Write the failing test**

In `godot-generative-agents/tests/test_boil_water.py`, add (mirror the file's existing tiny-world setup helpers):

```python
def test_drink_stamps_authoritative_outcome_counters():
    # DrinkPenn records the causal outcome as first-class state so the #595
    # harness reads it directly (not from the event log).
    game, chars = _tiny_boil_world()  # existing helper: a drinker + murky + boiled water
    maya = chars["Maya"]

    game.parser.parse_command("drink cup of murky water", actor=maya)
    assert maya.get_property("drank_unboiled") == 1
    assert not maya.get_property("drank_boiled")
    assert maya.get_property("is_sick")

    # A later safe drink (boiled water) increments the safe counter, not the raw one.
    game.parser.parse_command("drink pot of boiled water", actor=maya)
    assert maya.get_property("drank_unboiled") == 1  # unchanged
    assert maya.get_property("drank_boiled") == 1
```

> Adapt the world-builder / item names to whatever `test_boil_water.py` already exposes (it builds worlds with the murky + boiled water items). If there is no `_tiny_boil_world` helper, reuse the file's existing fixture that registers `DrinkPenn` and has a murky-water and a boiled-water item in scope.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_boil_water.py -k authoritative_outcome -v`
Expected: FAIL (`drank_unboiled` is absent/`False`).

- [ ] **Step 3: Stamp the counters in `apply_effects`**

In `DrinkPenn.apply_effects` (`godot-generative-agents/backend/actions.py`), after the `if self.character.get_property("is_dead"): return` guard, and inside the effect logic, record the outcome. Add the raw-drink counter in the sickening branch and the safe-drink counter otherwise:

```python
        if self.item.get_property("requires_boiling") and not self.item.get_property(
            "is_boiled"
        ):
            # Authoritative outcome (#595): this drink was raw water -> the agent
            # did NOT boil first. The harness reads this instead of parsing events.
            self.character.set_property(
                "drank_unboiled", (self.character.get_property("drank_unboiled") or 0) + 1
            )
            self.character.set_property("is_sick", True)
            # ... (existing just_sickened + parser.ok + log_event unchanged) ...
        else:
            # A safe drink: boiled water, or water that never required boiling.
            self.character.set_property(
                "drank_boiled", (self.character.get_property("drank_boiled") or 0) + 1
            )
            # ... existing recovery branch (elif is_sick and is_boiled) folds in here;
            # keep its body, just nested under this else. See note below.
```

> **Care with the existing branch structure.** Today the method is `if raw: sicken  elif is_sick and is_boiled: recover`. Restructure minimally: keep the `if raw:` branch (add `drank_unboiled`), and turn the `elif` into an `else:` block that (a) increments `drank_boiled` and (b) preserves the existing `if self.character.get_property("is_sick") and self.item.get_property("is_boiled"):` recovery block verbatim inside it. Do not change the recovery narration/event. Verify by re-reading the method after editing.

- [ ] **Step 4: Run to verify it passes + no regression**

```bash
uv run pytest godot-generative-agents/tests/test_boil_water.py -v
```
Expected: the new test PASSES and every existing boil-water test still PASSES (sicken/recover arc unchanged).

- [ ] **Step 5: Format + commit**

```bash
uv run black godot-generative-agents/backend/actions.py godot-generative-agents/tests/test_boil_water.py
git add godot-generative-agents/backend/actions.py godot-generative-agents/tests/test_boil_water.py
git commit -m "feat(backend): DrinkPenn records the authoritative drink outcome (#595)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Thirst/sickness legibility in the decide observation

**Files:**
- Modify: `godot-generative-agents/backend/cognition.py` (`observe_and_decide`, after `base = game.describe_for(char)` at ~line 832, alongside the #580 context append at ~854)
- Test: `godot-generative-agents/tests/test_cognition_wiring.py` (extend — it already exercises `observe_and_decide`)

**Interfaces:**
- Consumes: `observe_and_decide(game, char, step, ...)`; character `is_thirsty` / `is_sick` properties.
- Produces: the decide observation string contains "You are thirsty." iff `is_thirsty`, and "You feel violently ill -- your stomach is cramping." iff `is_sick`. Both are appended **after** the retrieval step (like the #580 context block), so `agent.last_retrieved` is unchanged by their presence.

- [ ] **Step 1: Write the failing test**

Append to `test_cognition_wiring.py` (reuse its `_world()` helper and a scripted brain, or inspect the observation another way — the goal is to assert the lines appear only when the flags are set, and retrieval is unaffected):

```python
def test_decide_observation_surfaces_thirst_and_sickness():
    from backend.cognition import observe_and_decide

    game, ada = _world()  # existing single-persona helper (mock brain)
    ada.set_property("is_thirsty", True)
    ada.set_property("is_sick", True)
    observe_and_decide(game, ada, 0)
    obs = ada.agent.last_observation  # see note
    assert "You are thirsty." in obs
    assert "violently ill" in obs


def test_thirst_sickness_lines_do_not_shift_retrieval():
    from backend.cognition import observe_and_decide

    game, ada = _world()
    observe_and_decide(game, ada, 0)
    healthy = list(ada.agent.last_retrieved)
    game2, ada2 = _world()
    ada2.set_property("is_thirsty", True)
    ada2.set_property("is_sick", True)
    observe_and_decide(game2, ada2, 0)
    # Same seeded memories surface regardless of the appended state lines,
    # because they append AFTER retrieve ran on the plain base.
    assert [r.text for r in ada2.agent.last_retrieved] == [r.text for r in healthy]
```

> **`last_observation`:** if the agent does not already stash the final observation string, add `agent.last_observation = observation` in `observe_and_decide` right after `observation` is built (a plain attribute on the port's `LLMAgent`, mirroring `agent.last_retrieved`) — small and useful for the harness/tests. If a stash already exists, use it and drop this note.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_cognition_wiring.py -k "thirst or sickness" -v`
Expected: FAIL (lines absent).

- [ ] **Step 3: Append the state lines after retrieval**

In `observe_and_decide` (cognition.py), find the block that appends the #580 context (`context = decide_context_block(...)` then `if context: base = f"{base}\n\n{context}"`, ~854). Immediately after it (still before `observation = format_observation_with_memories(base, relevant)`), add:

```python
    # Perceivable needs/consequences (#594): surface thirst + sickness in the
    # decide prompt so a live brain can reason about them. Appended AFTER the
    # retrieve above (like the #580 block), so these lines never shift which
    # memories surface -- the mock/scripted bake stays byte-identical. Absent
    # flags add nothing.
    state_lines = []
    if char.get_property("is_thirsty"):
        state_lines.append("You are thirsty.")
    if char.get_property("is_sick"):
        state_lines.append("You feel violently ill -- your stomach is cramping.")
    if state_lines:
        base = base + "\n\n" + "\n".join(state_lines)
```

If Step 1 needed it, also add after `observation = format_observation_with_memories(base, relevant)`:

```python
    agent.last_observation = observation
```

- [ ] **Step 4: Run to verify it passes + byte-identical guard**

```bash
uv run pytest godot-generative-agents/tests/test_cognition_wiring.py -v
uv run pytest godot-generative-agents/tests/test_penn_live.py::test_stepper_matches_simulate_prefix -v
```
Expected: new tests PASS; simulate-equivalence still PASS (no default persona is thirsty/sick at t=0, and the lines append after retrieval → the retrieved list, which frames embed, is unchanged).

- [ ] **Step 5: Format + commit**

```bash
uv run black godot-generative-agents/backend/cognition.py godot-generative-agents/tests/test_cognition_wiring.py
git add godot-generative-agents/backend/cognition.py godot-generative-agents/tests/test_cognition_wiring.py
git commit -m "feat(backend): surface thirst + sickness in the decide prompt (#594)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Opt-in seeded aversion memory

**Files:**
- Modify: `godot-generative-agents/backend/cognition.py` (`attach_agents`, near the existing `agent.memory.add_plan(...)` / `seed.seed_relationships(...)` seeding, ~line 393-409)
- Test: `godot-generative-agents/tests/test_cognition_wiring.py` (extend)

**Interfaces:**
- Consumes: `attach_agents(characters, personas, ...)`; `agent.memory.add_observation(text, turn, importance)` (`memory.py:304`); a persona spec's optional `seed_memories: list[str]`.
- Produces: each string in a persona's `seed_memories` is added as a t=0 OBSERVATION at importance 5.0 (the value `add_plan` already uses), retrievable at decision time. Absent key → nothing seeded (byte-identical).

- [ ] **Step 1: Write the failing test**

Append to `test_cognition_wiring.py`:

```python
def test_seed_memories_are_added_and_retrievable():
    from backend.build_world import build_world
    from backend.cognition import attach_agents

    personas = _personas()  # existing helper (single persona Ada)
    personas[0]["seed_memories"] = [
        "Last time I drank the unboiled water here I got violently ill."
    ]
    game, chars = build_world(None, personas, LOCATIONS)  # existing LOCATIONS
    attach_agents(chars, personas)
    mem = chars["Ada"].agent.memory
    texts = [r.text for r in mem.retrieve(query="unboiled water sick", turn=1)]
    assert any("violently ill" in t for t in texts)


def test_no_seed_memories_key_adds_nothing_extra():
    from backend.build_world import build_world
    from backend.cognition import attach_agents

    personas = _personas()
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas)
    kinds = [r for r in chars["Ada"].agent.memory.all()]
    # Only the t=0 plan memory (add_plan) -- no extra seeded observation.
    assert all("violently ill" not in r.text for r in kinds)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_cognition_wiring.py -k seed_memories -v`
Expected: FAIL (`seed_memories` not consumed).

- [ ] **Step 3: Seed the memories in `attach_agents`**

In `attach_agents` (cognition.py), after the existing `agent.memory.add_plan(...)` seed block (~line 393-402) and near `seed.seed_relationships(...)`, add:

```python
        # Opt-in seeded memories (#595): author t=0 observations (e.g. an aversive
        # "the unboiled water made me sick" memory) so a live brain can retrieve
        # and reason from them. Importance 5.0 matches the plan-memory seed so it
        # ranks highly. Absent key -> nothing added (byte-identical).
        for text in spec.get("seed_memories") or []:
            agent.memory.add_observation(text, turn=0, importance=5.0)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest godot-generative-agents/tests/test_cognition_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Format + commit**

```bash
uv run black godot-generative-agents/backend/cognition.py godot-generative-agents/tests/test_cognition_wiring.py
git add godot-generative-agents/backend/cognition.py godot-generative-agents/tests/test_cognition_wiring.py
git commit -m "feat(backend): opt-in t=0 seeded memories for personas (#595)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: The experiment harness + offline smoke

**Files:**
- Create: `godot-generative-agents/backend/penn/experiments/__init__.py` (empty)
- Create: `godot-generative-agents/backend/penn/experiments/boil_from_memory.py`
- Test: `godot-generative-agents/tests/test_boil_from_memory.py`

**Interfaces:**
- Consumes: `build_penn_world(world_data=WORLD_DATA_BOIL)` (`penn_world.py:423`, `WORLD_DATA_BOIL` at `:48`); `run_simulation.simulate(world_map, num_steps, *, personas, build_world_fn, llm_client=None, reflector_client=None, extra_action_names=None, ledger=None)`; the drink outcome counters `drank_unboiled`/`drank_boiled` (Task 3); `seed_memories` (Task 5) + `thirst_rate` (Task 2); a brain: `MockLlmClient`/`build_scripted_brains` (offline) or `create_llm_client(LlmConfig(provider="anthropic", model=...))` (live); `text_adventure_games.usage.UsageLedger`.
- Produces:
  - `classify_outcome(char) -> str` — `"boiled_then_drank"` if `drank_boiled > 0 and drank_unboiled == 0`; `"drank_raw"` if `drank_unboiled > 0`; else `"neither"`.
  - `run_arm(*, seeded: bool, trials: int, steps: int, make_client) -> dict` — runs `trials` trials, returns `{"boiled_then_drank": n, "drank_raw": n, "neither": n, "rate": float}` where `rate = boiled_then_drank / trials`.
  - `main()` — argparse (`--trials`, `--steps`, `--model`, `--offline`), prints a per-arm report + ledger spend.

- [ ] **Step 1: Write the failing smoke test**

Create `godot-generative-agents/tests/test_boil_from_memory.py`:

```python
"""Offline smoke for the #595 experiment harness: it runs end-to-end under the
scripted brain (no key), the outcome classifier is exercised, and a report is
produced. The research CLAIM (rate above control) is a manual, keyed run -- not
asserted here. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_boil_from_memory.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.penn.experiments.boil_from_memory import (  # noqa: E402
    classify_outcome,
    run_arm,
)
from backend.penn.scripted_brain import build_scripted_brains  # noqa: E402


class _C:
    def __init__(self, **props):
        self._p = props

    def get_property(self, k):
        return self._p.get(k, False)


def test_classify_outcome_reads_the_authoritative_flags():
    assert classify_outcome(_C(drank_boiled=1, drank_unboiled=0)) == "boiled_then_drank"
    assert classify_outcome(_C(drank_unboiled=1)) == "drank_raw"
    assert classify_outcome(_C()) == "neither"


def test_run_arm_smoke_with_scripted_brain():
    # A single scripted trial runs the whole harness plumbing offline.
    result = run_arm(
        seeded=True,
        trials=1,
        steps=20,
        make_client=lambda ledger: build_scripted_brains(ledger=ledger)[0],
    )
    assert set(result) >= {"boiled_then_drank", "drank_raw", "neither", "rate"}
    assert result["boiled_then_drank"] + result["drank_raw"] + result["neither"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_boil_from_memory.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the harness**

Create `godot-generative-agents/backend/penn/experiments/__init__.py` (empty), then `godot-generative-agents/backend/penn/experiments/boil_from_memory.py`:

```python
"""#595 experiment: does a live LLM choose to boil from an aversive memory?

Runs N trials per arm on the single-persona boil world:
  * seeded   -- the persona carries a t=0 "the unboiled water made me sick" memory;
  * control  -- identical, minus that memory.
Each trial reads the AUTHORITATIVE drink outcome DrinkPenn stamped
(drank_unboiled / drank_boiled) -- never the event log -- and classifies it. The
per-arm boil-before-drink rate is printed; the seeded arm clearly above control is
the #595 result.

Offline: pass a scripted/mock make_client (no key). Live: default make_client builds
an Anthropic Haiku client -- needs ANTHROPIC_API_KEY (in-env only) and small spend.
"""

import argparse
import sys
from pathlib import Path

_SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SIM_DIR))

from backend.run_simulation import simulate  # noqa: E402
from penn_world import WORLD_DATA_BOIL, build_penn_world  # noqa: E402
from text_adventure_games.llm_client import LlmConfig, create_llm_client  # noqa: E402
from text_adventure_games.usage import UsageLedger  # noqa: E402

_AVERSION = "Last time I drank the unboiled water at Houston Hall I got violently ill."


def classify_outcome(char) -> str:
    """The trial outcome, read from DrinkPenn's authoritative counters."""
    if (char.get_property("drank_unboiled") or 0) > 0:
        return "drank_raw"
    if (char.get_property("drank_boiled") or 0) > 0:
        return "boiled_then_drank"
    return "neither"


def _configure(personas, *, seeded):
    """Return a fresh personas list configured for one arm: the boil persona is
    thirsty (so drinking is motivated) and -- in the seeded arm -- carries the
    aversion memory. Authored commands are left as-is: a live brain ignores them
    (attach_agents treats commands as mock-only), so nothing needs stripping."""
    out = [dict(p) for p in personas]
    p = out[0]
    p["thirst_rate"] = 1
    p["thirst_threshold"] = 2
    p["seed_memories"] = [_AVERSION] if seeded else []
    return out


def run_arm(*, seeded, trials, steps, make_client):
    """Run `trials` trials of one arm; return the outcome tally + boil-before-drink
    rate. `make_client(ledger)` builds the decide brain for a trial."""
    tally = {"boiled_then_drank": 0, "drank_raw": 0, "neither": 0}
    for _ in range(trials):
        pw = build_penn_world(world_data=WORLD_DATA_BOIL)  # fresh world per trial
        personas = _configure(pw.personas, seeded=seeded)
        ledger = UsageLedger()
        captured: dict = {}

        def build_capture(world_map):
            game, chars = pw.build_world_fn(world_map)
            captured.update(chars)
            return game, chars

        simulate(
            pw.world_map,
            steps,
            ledger=ledger,
            personas=personas,
            build_world_fn=build_capture,
            llm_client=make_client(ledger),
        )
        char = captured[personas[0]["name"]]
        tally[classify_outcome(char)] += 1
    rate = tally["boiled_then_drank"] / trials if trials else 0.0
    return {**tally, "rate": rate}


def _live_client(ledger):
    return create_llm_client(
        LlmConfig(provider="anthropic", model="claude-haiku-4-5-20251001"),
        ledger=ledger,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="#595 boil-from-memory experiment.")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--steps", type=int, default=80)
    ap.add_argument(
        "--offline",
        action="store_true",
        help="use the scripted brain (no key, no spend) -- plumbing check only, "
        "not a real measurement",
    )
    args = ap.parse_args()

    if args.offline:
        from backend.penn.scripted_brain import build_scripted_brains

        make_client = lambda ledger: build_scripted_brains(ledger=ledger)[0]  # noqa: E731
    else:
        make_client = _live_client

    for arm in ("seeded", "control"):
        result = run_arm(
            seeded=(arm == "seeded"),
            trials=args.trials,
            steps=args.steps,
            make_client=make_client,
        )
        print(
            f"[{arm:8}] boil-before-drink rate: {result['rate']:.0%}  "
            f"({result['boiled_then_drank']} boiled / {result['drank_raw']} raw / "
            f"{result['neither']} neither of {args.trials})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

> If `simulate`'s keyword names differ from those in the Interfaces block, match the actual signature in `run_simulation.py` (verified via `grep -n "^def simulate" -A20`). Do not pass `reflector_client`/`cognition` unless the experiment needs reflection (it does not — keep the call minimal).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest godot-generative-agents/tests/test_boil_from_memory.py -v`
Expected: PASS (2 tests). If `run_arm` errors under the scripted brain, debug the `build_capture`/`simulate` wiring until the smoke trial completes and classifies.

- [ ] **Step 5: Format + commit**

```bash
uv run black godot-generative-agents/backend/penn/experiments/ godot-generative-agents/tests/test_boil_from_memory.py
git add godot-generative-agents/backend/penn/experiments/__init__.py godot-generative-agents/backend/penn/experiments/boil_from_memory.py godot-generative-agents/tests/test_boil_from_memory.py
git commit -m "feat(backend): #595 boil-from-memory experiment harness + offline smoke

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Verify the seeded aversion is retrieved at the Houston decision (the #595 risk)

**Files:**
- Test: `godot-generative-agents/tests/test_boil_from_memory.py` (extend)
- Modify (only if the check fails): `godot-generative-agents/backend/cognition.py` (nudge seed importance/tag)

**Interfaces:**
- Consumes: everything above. This task closes the spec's explicit open risk: "the seeded sick memory is *retrieved* at the Houston decision."

- [ ] **Step 1: Write the retrieval-at-decision test**

Append to `test_boil_from_memory.py` — build the seeded boil world, run one scripted trial, and assert the aversion memory surfaces in the boil persona's retrieved block at the Houston step (inspect `agent.last_retrieved` / `last_observation`):

```python
def test_seeded_aversion_is_retrieved_at_the_water_decision():
    # The #595 prerequisite: the seeded memory must actually reach the decide
    # prompt near the water, or the live brain can't reason from it.
    import sys
    from pathlib import Path

    sim = Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
    sys.path.insert(0, str(sim))
    from backend.run_simulation import simulate
    from penn_world import WORLD_DATA_BOIL, build_penn_world
    from backend.penn.experiments.boil_from_memory import _AVERSION, _configure
    from backend.penn.scripted_brain import build_scripted_brains

    pw = build_penn_world(world_data=WORLD_DATA_BOIL)
    personas = _configure(pw.personas, seeded=True)
    captured = {}

    def build_capture(world_map):
        game, chars = pw.build_world_fn(world_map)
        captured.update(chars)
        return game, chars

    simulate(pw.world_map, 40, personas=personas, build_world_fn=build_capture,
             llm_client=build_scripted_brains()[0])
    agent = captured[personas[0]["name"]].agent
    # By the end of a Houston-centred run the aversion has surfaced at least once.
    assert any("violently ill" in r.text for r in agent.last_retrieved), (
        "seeded aversion never retrieved -- raise its importance or tag it"
    )
```

- [ ] **Step 2: Run it**

Run: `uv run pytest godot-generative-agents/tests/test_boil_from_memory.py -k retrieved -v`
Expected: PASS if importance-5.0 + keyword overlap surfaces it. If FAIL: the seeded memory is not being retrieved — apply the nudge below, then re-run.

- [ ] **Step 3 (only if Step 2 failed): Nudge retrieval**

In Task 5's seed block (cognition.py), raise the seeded importance above the plan memory (e.g. `importance=8.0`) and/or add a tag matching the water context, then re-run Step 2 until green. Record what was needed in the experiment module's docstring (the spec asked for this to be documented, not hidden).

- [ ] **Step 4: Commit (only if files changed)**

```bash
uv run black godot-generative-agents/tests/test_boil_from_memory.py godot-generative-agents/backend/cognition.py
git add godot-generative-agents/tests/test_boil_from_memory.py godot-generative-agents/backend/cognition.py
git commit -m "test(backend): pin that the seeded aversion reaches the water decision (#595)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Full offline suite + docs note

**Files:**
- Modify: `godot-generative-agents/README.md` (a short note on the experiment)

- [ ] **Step 1: Add the README note**

Under the Penn/live-mode section, add a short paragraph:

> **Boil-from-memory experiment (#595).** `uv run python -m backend.penn.experiments.boil_from_memory --trials 5` (from `godot-generative-agents/`, needs `ANTHROPIC_API_KEY`) runs a live Haiku brain on the single-persona boil world with vs without a seeded "the unboiled water made me sick" memory, and prints the boil-before-drink rate for each arm. Add `--offline` for a key-free plumbing check (scripted brain, not a real measurement).

- [ ] **Step 2: Run the full offline suite + formatter + byte-identical guard**

```bash
uv run pytest godot-generative-agents/tests/ -q
uv run pytest godot-generative-agents/tests/test_penn_live.py::test_stepper_matches_simulate_prefix -v
uv run black --check godot-generative-agents/backend/drives.py godot-generative-agents/backend/actions.py godot-generative-agents/backend/cognition.py godot-generative-agents/backend/run_simulation.py godot-generative-agents/backend/penn/experiments/boil_from_memory.py
```
Expected: all green; the simulate-equivalence test green (byte-identical bake); nothing to reformat.

- [ ] **Step 3: Commit**

```bash
git add godot-generative-agents/README.md
git commit -m "docs(backend): document the #595 boil-from-memory experiment

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for the implementer

- **Byte-identical is the tripwire.** Everything opt-in: no `thirst_rate` → no accrual; no `seed_memories` → no memory; thirst/sickness lines append after retrieval. `test_stepper_matches_simulate_prefix` must stay green after every task.
- **The outcome is authoritative, not inferred.** The whole point of Task 3 is that `DrinkPenn` (which applies the effect) records what happened; the harness never parses events. If you find yourself scanning the event log for boil/drink ordering, stop — read the counters.
- **The live measurement is out of CI.** Tasks 6–7 prove the plumbing offline with the scripted brain. The actual research run (`main()` without `--offline`) needs a key + spend and is run by hand; its printed rate report is the #595 acceptance artifact.
- **Don't touch `text_adventure_games/` or root `tests/`.** This is the Penn-local slice; the generic engine lift is deliberately deferred (like #464 follows #300).
