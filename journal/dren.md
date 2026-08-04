# Dren's research journal

Daily lab notebook — see [README.md](README.md) for the convention. Newest entry
on top; copy the template block each working day.

<!-- Template (copy to the top each day):
## YYYY-MM-DD
**Focus:** <the issue/topic you're on>
**Done today:**
- ...
**Blockers / questions:**
- ... (write "none" if none)
**Next:**
- ...
-->
## 2026-08-04
**Focus:** Give Sleep a real place to be reached from, then unify its gate (#931)

**Done today:**
- Tagged Houston Hall's Reading Room `sleepable` in `world_data_upenn.yaml`
  (its armchairs double as the nap spot) -- the campus block has no
  dorm/residence in frame, so `Sleep` (`REQUIRED_AFFORDANCES =
  ("sleepable",)`) had nowhere to be reached from outside of tests until now.
- Added `test_live_penn_world_has_a_sleepable_location` to
  `test_sleep_action.py`, mirroring `test_eat_energy.py`'s live-world wiring
  checks. Full suite still green, no new failures.
- Noticed (via Claude poking at it) that `Sleep` had its own hardcoded
  `SLEEP_ENERGY_THRESHOLD = 50` raw-energy check, completely disconnected
  from `accrue_energy`'s `IS_SLEEPY` flag (threshold 20) -- two independent
  numbers claiming to mean "tired," which disagreed by ~100 sim-ticks in a
  live run. Removed the separate threshold; `Sleep.check_preconditions` now
  just reads `Property.IS_SLEEPY` directly, so accrue_energy is the single
  source of truth for tiredness. Updated `test_sleep_action.py`'s tests to
  set `IS_SLEEPY` instead of raw `ENERGY`, and added a test driving
  `accrue_energy` to confirm `Sleep` becomes reachable exactly when it flips
  `IS_SLEEPY`, not before.

**Blockers / questions:**
- none

**Next:**
- `uv sync --extra server` in this env so the fastapi-gated test files
  actually collect, and re-check they're really unaffected.

## 2026-08-03
**Focus:** Finish the SleepPenn/EatPenn/DrinkPenn test suite (#931)

**Done today:**
- `DrinkPenn` never actually restored energy (only `EatPenn` did) -- added
  the same `energy_value` restore, unconditional like `EatPenn`'s (separate
  from the sickness/boil twist), and gave the Houston Hall drink + the boil
  scenario's murky/boiled pots an `energy_value`, mirroring Action Castle's
  water.
- Renamed `SleepPenn` -> `Sleep` and rebuilt its gating to match
  `test_sleep_action.py`'s scaffold: `REQUIRED_AFFORDANCES = ("sleepable",)`
  (the Study precedent) plus a raw-energy "tired enough" threshold, instead
  of the unreachable `is_sleepy`-flag gate it had before.
- Found and fixed a real bug breaking most of the step-loop test suite:
  `drives.sleep_accumulation` called `get_property` with a stray second
  arg (TypeError, since the engine's `get_property` takes only one) --
  every `run_simulation.step()` call was crashing on it. Also fixed its
  recovery math (was nearly doubling energy each tick instead of shrinking
  the deficit from 100) and an `"Is_sleepy"`/`"is_sleepy"` casing mismatch
  that silently made `accrue_energy`'s sleepy-flag never readable.
- Fixed the test file bugs blocking `test_eat_energy.py`'s drink tests: a
  duplicate `test_energy_is_capped_at_max_energy` definition silently
  shadowing the eat version, `"eat soda"` where it meant `"drink soda"`,
  and two tests asserting/using the wrong action.
- Resolved the `Set_energy` 50-vs-70 test blocker (open since 2026-07-30):
  kept the 70 behavior, updated the two stale assertions.
- Full suite: `uv run pytest tests/ godot-generative-agents/tests/` now
  green except pre-existing, unrelated failures (confirmed via `git stash`
  that they fail identically without today's changes): the superseded
  `tests/test_energy.py`, and a handful of `godot-generative-agents/tests/`
  files that need `uv sync --extra server` (fastapi) to even collect.
- Cleanup pass: removed `accrue_hunger` (dead -- never opted into, never
  actually accumulated hunger even when called) and the unused `Property`
  enum members that went with it (`HUNGER`, `HUNGER_RATE`, `THIRST`,
  `THIRST_RATE`, `SLEPT_AT_TIME`, `ATE_AMOUNT`, `DRANK_AMOUNT`), plus stale
  TDD-scaffold docstrings/self-note comments now that the feature is
  implemented and green.
- Committed and opened PR #969 (`food-system-branch` -> `main`) for #931 --
  left the `Set_energy` Action Castle test fix out of it, uncommitted, per
  request.

**Blockers / questions:**
- none

**Next:**
- `uv sync --extra server` in this env so the fastapi-gated test files
  actually collect, and re-check they're really unaffected.
- world_data_upenn.yaml still has no `sleepable`-tagged location, so `Sleep`
  is reachable in tests but not yet in the live/bake world.

## 2026-07-31
**Focus:** Port Action Castle's eat/energy system onto Penn (issue #931)

**Done today:**
- Filed #931 for the Penn-side port. Added `EatPenn` (`backend/actions.py`,
  mirrors `DrinkPenn`): restores `Property.ENERGY` from a meal's
  `energy_value`, capped at `MAX_ENERGY`; wired into `PENN_EXTRA_ACTIONS` and
  gave Houston Hall's meals `energy_value`.
- Added `accrue_energy` to `drives.py` (mirrors `accrue_thirst`: opt-in via
  `energy_decay_rate`, floors at 0, flips `is_low_energy`), wired into
  `run_simulation.py`'s per-step loop next to `accrue_thirst`.
- Wrote `world_data_eat.yaml` (one persona, Houston Hall, get/eat sandwich
  arc) and wired a `--scenario eat` into `generate_penn_replay.py`. Baked it
  end-to-end and confirmed the `eat` event fires and energy is restored.
- Wrote/extended `test_eat_energy.py` (6 tests) and confirmed the existing
  `test_energy_drive.py` scaffold (4 tests) now passes unmodified.
- Wrote `penn-eatpenn-plan.md`: the full remaining design (16h eat-again
  cooldown via `Property.NOT_HUNGRY_TIME` + `game.turn`, surfacing
  `is_low_energy` to the live LLM brain via `cognition.py`, Sleep as a
  separate follow-up).

**Blockers / questions:**
- Noticed `text_adventure_games/actions/consume.py`'s `Eat.apply_effects`
- Yesterday's `Set_energy` blocker (broke `test_action_castle_energy.py` /
  `test_action_castle_eat.py`, expects 50 vs new 70) is still open.

**Next:**
- Cooldown + LLM-surfacing halves of #931 (both still unimplemented, see the
  plan doc).
- Resolve the `Set_energy` test blocker from 2026-07-30.

## 2026-07-30
**Focus:** Finish the Eat/Drink cooldown system; sleep recovery tuning

**Done today:**
- Finished `Drink` (mirrors `Eat`), gated both on `ate_food`/`drank_water`
  cooldown flags that clear via a new 16-hour reset trigger (same
  timestamp-and-check shape as `Sleep`'s 8-hour wake-up). Added water/soda
  items to the Garden. Wrote `tests/test_action_castle_food_cooldown.py` (6
  tests, all passing).
- Lowered the sleep recovery rate: `SLEEP_RECOVERY_DECAY` 0.8 -> 0.9 (less of
  the energy deficit clears per half hour, so overnight recovery is slower).
- Changed `Set_energy` ("energy mode") to reset to 70 instead of 50.

**Blockers / questions:**
- The `Set_energy` change broke 2 existing tests that assert energy == 50
  after "energy mode" (`test_action_castle_energy.py` and
  `test_action_castle_eat.py`) -- need to decide: update the assertions to 70,
  or revert the reset value.

**Next:**
- Fix the 2 broken `Set_energy` tests.

## 2026-07-29
**Focus:** Action Castle sleep recovery bugfix

**Done today:**
- Fixed `recover_and_wake_up`: it multiplied *current* energy by a recovery
  rate each half hour, so the lower your energy, the less sleep helped
  (energy 1 -> only 5.89 after a full night). Now shrinks the deficit from
  100 by a constant factor instead, so recovery converges to ~93+ overnight
  regardless of starting energy. Renamed `SLEEP_RECOVERY_RATE` ->
  `SLEEP_RECOVERY_DECAY`. All 25 sleep/energy/eat tests still pass.

**Blockers / questions:**
- none

**Next:**
- Commit this fix + yesterday's uncommitted `enums.py`/Godot scaffold work.

## 2026-07-28
**Focus:** Action Castle sleep/energy bugfixes + scoping the Penn/Godot port

**Done today:**
- Fixed several sleep/energy bugs in Action Castle (uninitialized energy
  crashing `build_game()`, broken `Sleep.__init__`, `is_sleeping` naming
  mismatch, uncapped recovery). `Sleep` now fast-forwards through the night
  in one command; added a `SleepGate` mixin blocking actions while asleep.
- Added `tests/test_action_castle_sleep.py` and fixed/filled in the rest of
  `test_action_castle_energy.py`/`test_action_castle_eat.py`. Suite green,
  committed as `f1fffed`.
- Started scoping the same system for the Penn/Godot sim: added
  `IS_SLEEPING`/`TIRED`/`SLEPT_AT_TIME` to `enums.Property` and wrote 3 TDD
  scaffold test files under `godot-generative-agents/tests/` (not committed,
  expected to fail until `EatPenn`/`Sleep`/`accrue_energy` exist).

**Blockers / questions:**
- Open question: should Penn's `Sleep` fast-forward turns like Action
  Castle's, or let a tick-driven drive restore energy instead? Penn's loop
  is externally ticked, so the Action Castle answer may not transfer.
- No `sleepable`-tagged location in `world_data_upenn.yaml` yet.

**Next:**
- Settle the Penn `Sleep` semantics question, implement `EatPenn`/`Sleep`/
  `accrue_energy` to turn the scaffolds green.
- Commit the `enums.py` change and the new test files.

## 2026-07-24
**Focus:** Git branching workflow, plus time-based energy decay

**Done today:**
- Practiced the branch → commit → push → PR workflow, incl. resolving a real
  merge conflict against `main` (backend restructuring).
- Filled in the 5 `TODO` test stubs left in `test_action_castle_eat.py` from
  yesterday; fixed 2 real bugs surfaced while getting them passing (a
  non-callable-`Character` typo, wrong `is_in_inventory` usage). All 10 pass.
- Wired a `GameClock` into `ActionCastle` (fixed a couple bugs along the way;
  also caught and restored some accidentally-deleted block serialization code).
- Implemented exponential energy decay via `triggers.py`'s `every(n)`:
  `Energy(t hours) = 100 * 0.9085^t`, converted to a per-turn multiplier —
  verified 100 -> ~10 after 24 in-game hours.
- Added a death trigger for energy <= 0.

**Blockers / questions:**
- Decay broke 4 exact-value assertions in `test_action_castle_energy.py`
  (assumed zero decay) — left as TODOs in `action_castle.py`.
- Energy is now a `float`; display formatting needs rounding.

**Next:**
- Fix the 4 broken energy tests (account for decay, `pytest.approx`).
- Decide on display rounding and whether NPCs should decay too.

## 2026-07-23
**Focus:** Energy/food system, scoped to Action Castle only

**Done today:**
- Implemented `Eat`/`Check_energy`/`Set_energy` as custom actions directly in
  `adventures/action_castle.py` (registered via `custom_actions`), plus a
  `Garden` location with `bread`/`tuna` food items.
- Debugged several real bugs: item name case-sensitivity in `match_item`
  (`"Tuna"` never matched since commands are lowercased first), a repeated
  `self.acting_character` missing-call bug, `games.Game(...)` vs. calling the
  `games` module directly, and a botched `Action` subclass reference.
- Verified end-to-end with live scripted playthroughs (not just reading the
  diff) — eating correctly restores/caps energy, items are discarded after.
- Wrote `tests/test_action_castle_energy.py` (7 passing, `build_game()` +
  `scenario.py` helpers) and `tests/test_action_castle_eat.py` (a synthetic
  `tiny_game` fixture with a custom `Excercise` action; 5 passing + 5 `TODO`
  stubs left to fill in).
- Full suite: 1337 passed, 7 failed (all pre-existing, in the now-superseded
  `tests/test_energy.py`), 3 skipped.

**Blockers / questions:**
- `tests/test_energy.py` still tests the abandoned engine-wide approach —
  needs retiring/rewriting.

**Next:**
- Retire `tests/test_energy.py`.
- Fill in the 5 `TODO` tests in `test_action_castle_eat.py`.

## 2026-07-22

**Focus:** Energy/food system — pivoted from engine-wide to Action-Castle-only

**Done today:**
- Ran the engine-wide energy implementation, found and fixed real bugs
  (floor-at-zero in `do_command`'s per-action deduction, several test typos).
- Decided the engine-wide scope was wrong for this — reverted the shared
  changes (`Character.__init__` default, `do_command`'s per-action cost) so
  every other game (Tomb, Smallville, Action Castle 2/3/4) is unaffected.
- Learned the `custom_actions` override mechanism (`Game.set_parser` +
  `Parser.add_action` overwrite by `ACTION_NAME`) as the way to scope a
  same-named action (`Eat`) to one specific game via Python subclassing.
- Read the third paper on Alistair's reading list (Text Worlds survey).

**Blockers / questions:**
- None blocking.

**Next:**
- Write the Action-Castle-scoped `Eat` override and register it.

## 2026-07-21

**Focus:** Energy/food system design for Action Castle

**Done today:**
- Scoped the design: properties bag, `Character` defaults, `Property` enum,
  `Eat`/`Drink`, and `end_turn()` cover it with no other engine changes needed.
- Wrote `energy-system-plan.md` — 5-step plan (enum → Character default →
  per-turn decay in `end_turn()` → `Eat` restores energy → per-action cost as
  a stretch goal).
- Wrote a TDD scaffold `tests/test_energy.py` (fails as expected — nothing
  implemented yet).

**Blockers / questions:**
- None blocking.

**Next:**
- Implement in order: `enums.py` → `Character.__init__` → `Eat.apply_effects`
  → `end_turn()` decay, running the tests after each step.

## 2026-07-20
**Focus:** Design choice for food system
**Done today:**
- Researched a few papers using Notebook LM on how food is incorporated in text world simulations
- Made a decsion on implementing food as an energy system, starting and 50 and maxing at 100.
**Blockers / questions:**
- ... none
**Next:**
- Edit Enums to add energy property and energy food
- Write a test suite for the implementation of the food system
-->
## 2026-07-17
**Focus:** Meeting with CCB
**Done today:**
- Meet with CCB and the rest of the team
- Looked at the codebase and thought of ways to implement a food system
**Blockers / questions:**
- Need to familiarize myself better with the code
**Next:**
- Implement a food system in Action Castle
- Read Text world survey paper.
## 2026-07-16
**Focus:** Godot Tutorial and more codebase analysis
**Done today:**
- Re-read the code base in order as described in the roadmap
- Looked at a godot tutorial online halfway build a game on godot.
**Blockers / questions:**
- Some bugs on the godot game, will vibe code the rest
**Next:**
- Finish Godot tutorial
- Grab an issue to work on
-->
## 2026-07-15
**Focus:** Finished debugging hw1 Continue Reading codebase
**Done today:**
- Finished Debugging HW1
- finished reading things.py, game and others files in order as described in the roadmap.
**Blockers / questions:**
- none
**Next:**
- Watch a Godot Tutorial
- Re-read the game to understand it better.
-->
## 2026-07-14

**Focus:** HW1 (Action Castle) — custom actions + Darkness block

**Done today:**
- Mostly debugged `Read_Runes` and `Propose` — few bugs left,
- Implemented all blocks
- Read the Generative Agents ("Human Simulacra") paper

**Blockers / questions:**
- Command/movement mixup bug to `input()`.

**Next:**
- Finish debugging HW1 
- Read `npc.py`/`memory.py`/`triggers.py`
- Read REACT paper.

## 2026-07-13

**Focus:** HW1 (Action Castle) — custom actions + Darkness block

**Done today:**
- Fixed graphviz `dot` PATH issue for the map visualization
- Implemented `Unlock_Door`, `Wear_Crown`, `Sit_On_Throne` — workingw

**Blockers / questions:**
- None blocking
**Next:**
- Finish remaining HW1 

Still need your first name for the journal/<firstname>.md filename if you want me to create it.
## 2026-07-10

**Focus:** onboarding — finished environment setup and got oriented on the plan.

**Done today:**
- Onboarding step 2: set up the project (`uv sync --extra dev`).
- Onboarding step 3: confirmed the suite is green — `uv run pytest -q` → 1423 passed, 4 skipped.
- Onboarding step 4: played the Tomb game to feel the engine from the outside.
- Skimed through ROADMAP.md to understand the phased plan (Phase 0 onboarding → Phase 1 agents → Phase 2 memory/planning → Phase 3 Godot).

**Blockers / questions:**
- Need to learn more about git commands and the command line in general.

**Next:**
- Do HW1: Action Castle (`notebooks/hw1.ipynb`) — the four core concepts (Locations, Items/Characters, Actions, Blocks).
- Start reading README + `docs/game-development-guide.md`.

## 2026-07-02

**Focus:** onboarding — getting set up and oriented.

**Done today:**
- Joined the project; accepting the GitHub invite to `ccb/agent-sandbox`.

**Blockers / questions:**
- none yet

**Next:**
- Follow [docs/student-onboarding.md](../docs/student-onboarding.md): set up with `uv sync --extra dev`, confirm `uv run pytest -q` is green, play the Tomb game, and start reading the README + game-development guide.
