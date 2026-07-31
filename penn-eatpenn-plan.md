# Penn EatPenn — implementation plan (issue #931)

**Status as of writing:** `EatPenn` exists (`godot-generative-agents/backend/actions.py`) and
does exactly one thing — restore `Property.ENERGY` from the eaten item's
`energy_value`, capped at `MAX_ENERGY`, guarded so a poisoned/just-killed
character doesn't also get an energy "reward." It's wired into
`PENN_EXTRA_ACTIONS` in `penn_world.py`, Houston Hall's three meals
(sandwich/soup/apple) now carry `energy_value`, and
`godot-generative-agents/tests/test_eat_energy.py` has 6 green tests covering
that slice. This document is the plan for everything still outstanding: the
eat-again cooldown, the energy-decay drive that makes eating matter at all,
and surfacing hunger/energy to a live LLM brain. Each section is independently
implementable and testable — do them in order, since #2 depends on nothing
existing yet but #3 (surfacing) is only worth doing once #2 exists.

Mirrors, throughout: Action Castle's already-working version
(`text_adventure_games/adventures/action_castle.py`, `Eat`/`Drink`/the
`energy_consumed_per_turn`/`recovery_per_turn`/`hunger_resets_after_16_hours`
triggers in `build_game`) and the existing thirst drive
(`godot-generative-agents/backend/drives.py::accrue_thirst`, #594) — but
**not** a literal port, because Penn has neither `game.clock`/`add_trigger`
nor a turn-based `do_command` loop. Penn is externally ticked
(`run_simulation.py::step`, shared by both the bake and the live server via
`serve_penn.py`'s `from backend.run_simulation import step`), and time is
tracked as a plain step counter, not a `GameClock`. Every design decision
below follows from that difference.

---

## 1. What "time" means inside a Penn `Action` (already answered, load-bearing)

Every other section depends on this, so it's settled first: `run_simulation.py`
line 287 does

```python
game.turn = step_idx
```

once per step, before per-character resolution. That means **`self.game.turn`
inside any `Action.check_preconditions`/`apply_effects` is a live,
monotonically increasing step counter** — no different in kind from Action
Castle's `game.turn`, just not paired with a `GameClock`/`minutes_elapsed`.
Any cooldown or timestamp Penn code needs can be expressed purely in step
counts, converted to real time only via `penn_world.SEC_PER_STEP = 10`
(seconds of sim-time per step) when a duration needs to be human-legible in a
comment or constant name.

No further investigation needed here — this unblocks section 2 directly.

---

## 2. The eat-again cooldown

### 2.1 Design decision: `NOT_HUNGRY_TIME`, not a boolean + timestamp pair

Action Castle's shape is two properties: a boolean gate (`ate_food`) checked
in `check_preconditions`, plus a timestamp (`ate_at`) a *separate trigger*
(`hunger_resets_after_16_hours`) reads every turn to decide when to flip the
boolean back off. That two-property, trigger-driven design exists because
Action Castle's trigger system needs a boolean to gate on and a timestamp to
know when to clear it.

Penn has no trigger system, and doesn't need one for this: since
`check_preconditions` can read `self.game.turn` directly, a **single property
holding "the step at which hunger resumes"** collapses both Action Castle
properties into one, and needs no per-step trigger to clear it — the
comparison happens lazily, only when the character next tries to eat. This is
exactly what `Property.NOT_HUNGRY_TIME` (already added to `enums.py`) is
for — the name already describes the "resume-hunger-at" semantics.

- [ ] Confirm `Property.NOT_HUNGRY_TIME` reads correctly as "the step turn at
      which the character becomes eat-eligible again" (rename now if that
      reading feels wrong later — nothing else references it yet, so it's a
      free rename until section 2.2 ships).

### 2.2 The cooldown length constant

Action Castle's is `16 * 60` minutes. Penn has no minutes — convert using
`SEC_PER_STEP`:

```python
# backend/actions.py, near EatPenn
# 16 in-game hours, expressed in steps (SEC_PER_STEP=10 sim-seconds/step,
# penn_world.py): 16 * 3600 / 10 = 5760.
EAT_COOLDOWN_STEPS = 16 * 3600 // 10
```

- [ ] Decide whether this constant belongs in `backend/actions.py` (next to
      `EatPenn`, since it's only that action's concern) or `penn_world.py`
      (next to `SEC_PER_STEP`, since it's derived from it). Recommendation:
      `actions.py` — `SEC_PER_STEP` is a display/pacing constant for the
      exporter, and importing it into `actions.py` to derive a gameplay
      constant is a small one-way dependency that's easy to reason about;
      the reverse (gameplay constants living in the world-assembly file)
      would be more surprising to a future reader.
- [ ] Import `SEC_PER_STEP` from `penn_world` into `actions.py` if the above
      is chosen — check this doesn't create a circular import (`penn_world.py`
      already imports from `backend.actions`, so `actions.py` importing
      `SEC_PER_STEP` back from `penn_world` **would** be circular). **Given
      that, just hardcode `5760` in `actions.py` with a comment citing the
      derivation, or define `EAT_COOLDOWN_STEPS` as a bare constant with no
      import at all.** This is exactly the kind of thing that looks fine
      until you run it — verify with `uv run pytest` after making the choice.

### 2.3 `EatPenn.check_preconditions`

```python
class EatPenn(consume.Eat):
    def check_preconditions(self) -> bool:
        not_hungry_time = self.character.get_property(Property.NOT_HUNGRY_TIME)
        if not_hungry_time and self.game.turn < not_hungry_time:
            self.parser.fail(
                f"{self.character.name.capitalize()} isn't hungry -- "
                "they ate recently."
            )
            return False
        return super().check_preconditions()
```

Note this must override `check_preconditions`, not just `apply_effects` (which
is all `EatPenn` currently overrides) — `Eat` doesn't currently define
`check_preconditions` itself in `EatPenn`, so add the method rather than
editing the existing `apply_effects`.

### 2.4 `EatPenn.apply_effects`

Add one line to the existing method, after the energy restore:

```python
    def apply_effects(self):
        super().apply_effects()
        if self.character.get_property("is_dead"):
            return
        energy_value = self.item.get_property("energy_value") or 0
        current_energy = self.character.get_property(Property.ENERGY) or 0
        self.character.set_property(
            Property.ENERGY, min(MAX_ENERGY, current_energy + energy_value)
        )
        self.character.set_property(
            Property.NOT_HUNGRY_TIME, self.game.turn + EAT_COOLDOWN_STEPS
        )
```

### 2.5 Tests (add to `test_eat_energy.py`)

Mirrors `tests/test_action_castle_food_cooldown.py`'s two cooldown tests, but
advances `game.turn` directly instead of looping `game.end_turn()` (Penn has
no turn-advance method to call — the step loop, not the game object, owns
that):

- [ ] `test_eating_again_right_away_is_blocked` — eat once, then immediately
      try to eat a second item; assert the second `parse_command` call
      returns `False` and `Property.ENERGY` didn't change from the second
      attempt.
- [ ] `test_eating_again_after_cooldown_succeeds` — eat once, manually set
      `game.turn += EAT_COOLDOWN_STEPS` (or add 1 past it), then eat a second
      item; assert it succeeds and energy increases again.
- [ ] `test_cooldown_message_names_the_character` — sanity-check the failure
      string actually names the acting character (easy to typo when porting
      the f-string from Action Castle's `Eat`).

---

## 3. The energy-decay drive (`accrue_energy`)

### 3.1 Why this has to exist

Without decay, `Property.ENERGY` only ever goes up (from eating) or stays
flat. There is no mechanical reason for an agent — scripted or LLM-driven —
to ever eat, because nothing is ever lost. This is the same problem #594's
issue body identified for thirst before `accrue_thirst` existed: "nothing
makes an agent *want* to" engage with the mechanic.

### 3.2 The good news: the test file already specifies the exact shape

`godot-generative-agents/tests/test_energy_drive.py` exists today and is
**already written** against a precise API — it currently fails only with an
`ImportError` on `accrue_energy`. Implement to make it pass; don't redesign
around it. It expects:

- `accrue_energy(char)` is a no-op if `char` has no `energy_decay_rate` set
  (opt-in per character, exactly like `thirst_rate` — a persona that never
  sets it is byte-identical to today's bake).
- It decrements `Property.ENERGY` by `energy_decay_rate`, floored at 0 (never
  negative).
- Past an `energy_low_threshold` (property, default via a module constant
  mirroring `_DEFAULT_THRESHOLD` in `drives.py`), it sets `is_low_energy`
  True on the character.

### 3.3 Implementation (`backend/drives.py`)

Directly beneath the existing `accrue_thirst`:

```python
_DEFAULT_ENERGY_LOW_THRESHOLD = 20  # confirm against test_energy_drive.py's expectations


def accrue_energy(char) -> None:
    """Advance *char*'s energy decay by its ``energy_decay_rate`` and flip
    ``is_low_energy`` at the threshold. A no-op when ``energy_decay_rate`` is
    0/absent (the default), so a non-experiment persona is untouched."""
    rate = char.get_property("energy_decay_rate") or 0
    if not rate:
        return
    threshold = char.get_property("energy_low_threshold") or _DEFAULT_ENERGY_LOW_THRESHOLD
    energy = max(0, (char.get_property(Property.ENERGY) or 0) - rate)
    char.set_property(Property.ENERGY, energy)
    if energy <= threshold:
        char.set_property("is_low_energy", True)
```

- [ ] Run `uv run pytest godot-generative-agents/tests/test_energy_drive.py -v`
      and adjust the threshold constant / comparison operator (`<=` vs `<`)
      until all 4 existing tests pass without editing the test file — the
      test file is the spec here, not this snippet.
- [ ] Decide: should `is_low_energy` ever get cleared back to `False`? Today
      `accrue_thirst` never clears `is_thirsty` either — only `Drink`/`Eat`
      clear the boolean (`Property.IS_THIRSTY` in `Drink`, `Property.IS_HUNGRY`
      in `Eat`). Mirror that: have `EatPenn.apply_effects` clear
      `is_low_energy` alongside the existing `Property.IS_HUNGRY` clear
      that `consume.Eat.apply_effects` already does — add
      `self.character.set_property("is_low_energy", False)` there.

### 3.4 Wiring into the step loop

`run_simulation.py` line ~411, immediately after the existing call:

```python
        accrue_thirst(char)
        accrue_energy(char)  # #931 — same per-character, per-step placement
```

Add the import alongside the existing one:

```python
from backend.drives import accrue_thirst, accrue_energy
```

This single edit covers **both** the bake (`generate_penn_replay.py`, which
calls `run_simulation.simulate`) and the live server (`serve_penn.py`, which
imports `step` from the same module) — no separate live-path wiring needed,
which is the entire reason `penn_world.py`/`run_simulation.py` are structured
as shared factories in the first place.

- [ ] After wiring, re-run the full `test_energy_drive.py` suite plus
      `test_eat_energy.py` to confirm nothing regressed.

---

## 4. Surfacing hunger/energy to a live LLM brain

This is the part that's easy to forget — implementing #2 and #3 gives you a
mechanically correct drive that a **scripted** schedule can trigger (an
authored `"eat sandwich"` command works, cooldown and decay both fire), but a
live LLM brain has no way to *perceive* low energy and no way to opt a
persona into decaying at all, unless this section is also done. Thirst
(#594) already solved both halves — energy needs the identical two edits.

### 4.1 Opt a persona into the drive (persona-spec → character property copy)

`backend/cognition.py`, inside `attach_agents` (function starts at line 463),
right after the existing thirst block (~line 642-648):

```python
        # Opt-in energy-decay drive (#931): mirrors the thirst wiring above.
        if spec.get("energy_decay_rate"):
            char.set_property("energy_decay_rate", spec["energy_decay_rate"])
        if spec.get("energy_low_threshold"):
            char.set_property("energy_low_threshold", spec["energy_low_threshold"])
```

- [x] Confirmed: `_normalize_personas` (`backend/build_world.py`) never
      mentions `thirst_rate`/`thirst_threshold` — persona-spec keys pass
      through untouched (`grep -n thirst_rate backend/build_world.py` returns
      nothing), so `energy_decay_rate`/`energy_low_threshold` need no
      normalization-layer edit either.

### 4.2 Surface it in the decide prompt

`backend/cognition.py`, inside `observe_and_decide` (starts at line 1060),
right after the existing thirst line (~line 1152-1153):

```python
    if char.get_property("is_low_energy"):
        base = base + "\n\nYou are low on energy."
```

- [ ] Decide the exact wording — "low on energy" vs "hungry" vs "tired" is a
      real product choice, not a technical one: `Property.IS_HUNGRY` already
      exists and is cleared by `Eat`, so there's a case for surfacing
      `is_hungry`-equivalent language here instead of "energy," to keep the
      prompt's vocabulary matched to what `eat` (the verb) is *for*, even
      though the underlying mechanical flag is `is_low_energy`. This doesn't
      change any code — it's one string — but is worth a second look before
      shipping so the brain's self-talk reads naturally.

### 4.3 World YAML: give at least one persona a rate

Nothing accrues until some persona's spec sets `energy_decay_rate` in
`world_data_upenn.yaml` (or `world_data_boil.yaml` for a smaller
experiment). Mirror however `thirst_rate` is authored today — find that
persona (`grep -rn thirst_rate godot-generative-agents/backend/penn/`) and
add a sibling `energy_decay_rate`/`energy_low_threshold` pair to the same (or
a different) persona so the live/bake world actually exercises the new
drive rather than only the tiny synthetic test world in
`test_energy_drive.py`.

- [ ] Add a `test_live_penn_world...` style test (mirroring the one already
      added to `test_eat_energy.py` for meals) that builds the real world via
      `build_penn_world()` and asserts at least one persona actually carries
      `energy_decay_rate` after `attach_agents` runs — a wiring check, the
      same category of bug the meals' missing `energy_value` was.

---

## 5. Explicitly out of scope for #931 — file separately

- **`Sleep`/`is_sleeping`** (`godot-generative-agents/tests/test_sleep_action.py`,
  already written, currently red on `ImportError`). This needs a new
  `"sleepable"` world tag in `world_data_upenn.yaml` (none exists), and an
  open question Action Castle's answer may not transfer: Action Castle's
  `Sleep.apply_effects` fast-forwards by looping `game.end_turn()` internally
  until 8 hours pass; Penn's step loop is externally ticked (the bake/live
  server call `step()`, not the action), so an action can't "loop the clock"
  the same way without breaking the one-step-per-`step()`-call contract the
  rest of the sim relies on. Needs its own design pass — likely "set
  `is_sleeping` and let a per-step recovery function (mirroring
  `accrue_energy`, inverted) restore energy over subsequent real steps,"
  which is a different shape from Action Castle's answer, not a port of it.
- **Hunger as a rising drive** (an `IS_HUNGRY`-flips-true-over-time
  counterpart to thirst) is deliberately *not* part of section 3 above —
  section 3 only decays the numeric `ENERGY` resource, the same shape
  `test_energy_drive.py` already specifies. Whether Penn also wants a
  separate rising "hunger" counter (as opposed to just reading low energy as
  "hungry") is an open product question, not a technical gap — don't build it
  speculatively.

---

## 6. Suggested implementation order (checklist)

- [ ] Section 2: cooldown (`EatPenn.check_preconditions` + `apply_effects`,
      `EAT_COOLDOWN_STEPS`, 3 new tests)
- [ ] Section 3: `accrue_energy` in `drives.py`, wired into `run_simulation.py`
      (makes the 4 existing `test_energy_drive.py` tests pass)
- [ ] Section 4: `attach_agents` + `observe_and_decide` wiring, one world-YAML
      persona opted in, one new wiring test
- [ ] Full-suite pass: `uv run pytest tests/ godot-generative-agents/tests/ -q`
      plus `uv run black --check` on every touched file
- [ ] Update issue #931 with what shipped vs. what's still open (Sleep,
      hunger-as-rising-drive) before closing it, or split the remainder into
      a follow-up issue

## 7. Verification commands

```bash
# The two scaffolds this plan is written against:
uv run pytest godot-generative-agents/tests/test_eat_energy.py -v
uv run pytest godot-generative-agents/tests/test_energy_drive.py -v

# Regression check after each section:
uv run pytest tests/ godot-generative-agents/tests/ -q

# Formatting:
uv run black --check godot-generative-agents/backend/actions.py \
  godot-generative-agents/backend/drives.py \
  godot-generative-agents/backend/cognition.py \
  godot-generative-agents/backend/run_simulation.py
```
