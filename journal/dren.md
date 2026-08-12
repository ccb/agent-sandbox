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
## 2026-08-11
**Focus:** Making sleep actually happen (#931 follow-up), then splitting tiredness off hunger entirely, then a wage system for job personas

**Done today:**
- Root-caused "agents never sleep": the mock brain only ever follows scripted `commands:` stops, never reads `IS_SLEEPY`; and hunger/tiredness shared one `ENERGY` resource, so eating silently cured tiredness. Decoupled the clearing (`clear_low_energy_if_recovered` stopped touching `IS_SLEEPY`), stamped `activity="sleeping"` in `Sleep.apply_effects`, and taught `run_simulation.py`'s settle branch to treat `sleep` like `perform` (unbounded, since it's drive-governed, not schedule-bound). Added authored bedtime stops to diego/tanaka/sofia. Confirmed via bake; found but left alone (per advisor) a pre-existing bug this exposes: routing everyone to the one shared sleepable room can hijack the meeting-injector's longest-co-location heuristic.
- Added reactive sleep: `attach_agents(game=...)` (opt-in, default off) lets `ScheduleMockClient` override the schedule the moment "You are sleepy." appears in the observation and walk to the nearest sleepable spot. Hardest part: a reactive nap needed a new pre-pass wake-unlatch or the character froze "performing" forever after waking. Gated behind `CognitionConfig.reactive_sleep` + a `--reactive-sleep` flag on `generate_penn_replay.py`.
- Split tiredness off `ENERGY` into its own `"restedness"` resource (`accrue_tiredness`/retargeted `sleep_accumulation`), mirroring thirst's independent-counter pattern — makes the eat-cures-sleep bug structurally impossible instead of just correctly-ordered. `accrue_energy` dropped its `IS_SLEEPING` gate (hunger now accrues while asleep, like thirst). New `test_tiredness_drive.py`.
- Added a wage system for the 10 job-flavored personas (Rosa, Walt, Debra, Gus, Leon, Marcus, Ellis, Tanaka, Ravi, Nadia): `accrue_wage`, opt-in `wage_rate` + per-stop `is_work` tag, paid only while actually on-site and settled on a tagged stop. Hit a real bug: added `wage_rate` to the YAMLs but forgot to wire `attach_agents` to copy it onto the character (mirrors `thirst_rate`) — wages silently never accrued until I traced it with a direct simulation check. New `test_wage_drive.py`.
- Full suite stayed at the same 2 pre-existing unrelated failures (stale `test_config_api_732.py` pins) all day; nothing committed.

**Blockers / questions:**
- The meeting-injector bug (picks the longest co-location window with no check against a meeting's authored location) is real and will resurface if more sleepable locations land near where personas already meet.
- Root `tests/test_api.py` still fails to collect — a stale root-level `./backend` bytecode-only dir shadowing the real package, predates this session.

**Next:**
- Brainstormed, not built: a second real sleepable location (Sweeten Alumni Building's dorm rooms are already geo-baked on the map, just never exposed as a `location:` entry) plus per-persona "nearest spot" selection.
- Wage amounts are flavor-only, never balanced.

## 2026-08-10
**Focus:** Closing gaps in the sleep/hunger drive loop so a live LLM brain actually notices and acts on needs (#931 follow-ups)

**Done today:**
- Retuned sleepy/hungry onset from 5 hours to 1 hour (`_ENERGY_DECAY_CONSTANT`).
- Found hunger/sleepiness were never surfaced to the LLM at all (only thirst was) — added `"You are hungry."`/`"You are sleepy."` lines to both the decide and converse prompts.
- Added `marketplace`/`sleepable` to the nearby-affordances tag list (Houston Hall's marketplace tag and the Reading Room's sleepable tag were being silently dropped), plus a new campus-wide (not vision-limited) hint so an agent knows where to eat/sleep from anywhere on the map, not just once it's already nearby.
- Fixed two real bugs found while verifying the above: (1) eating/drinking restored energy but never cleared the hungry/sleepy flags — a one-way flag; (2) energy decay ran even while a character was asleep, so recovery asymptotically converged just *below* the wake threshold and characters never actually woke up.
- Added a need-driven interrupt so a long scheduled activity (e.g. an 800-step block) can break early the moment a need appears, instead of blocking any reaction until that activity finishes on its own. Gated to real LLM brains only after it broke two mock-brain tests.
- Environment: installed Godot 4.6.3 (Homebrew's 4.7.1 needs macOS 13+, we're on 12.3); fixed `uv sync` dropping dev tools when extras aren't all listed together.

**Blockers / questions:**
- Live `--brain llm` run showed 548 decide calls at $0 cost / 0 tokens each — never root-caused (network to the API checked fine from this machine).

**Next:**
- Sleep bug: agents don't actually go to sleep even when sleepy — needs investigation.
- Consider making more locations sleepable (or all of them?) — right now only Houston Hall's Reading Room qualifies.

## 2026-08-07
**Focus:** Finish Buy/Sell (#931/#932), a Houston Hall sandwich shop on top of it, sleep-gating sweep, and the energy-decay timing fix

**Done today:**
- Reviewed my own uncommitted Buy/Sell WIP in the Penn backend
  (`godot-generative-agents/backend/actions.py`) before building on it:
  `sell` crashed on construction (called a nonexistent `self.item()`
  matcher), `buy` was a copy-pasted `Sleep` that did nothing, and
  `REQUIRED_AFFORDANCES = ("marketplace")` was a bare string, not a tuple,
  so the affordance check silently iterated its characters. Also caught a
  design regression: the WIP had swapped the already-committed
  `Property.OWNER` (who's authorized to sell an item) for a boolean
  `Property.IS_OWNER` on the character, which can't express per-item
  ownership and broke `tests/test_commerce_scaffold.py`. Restored `OWNER`,
  rewrote `sell`/`buy` properly (kept the two-step dibs design: `sell`
  stamps a named buyer, `buy` completes the transfer), and wrote
  `tests/commerce_system_test.py` (14 tests: dibs, wrong-buyer, asleep,
  broke, marketplace-affordance gating, the full happy path).
- Reviewed the whole `food-system-branch` eat/sleep/energy commit chain
  (7 commits, #931) end to end rather than each commit in isolation, since
  later ones fix bugs the earlier ones introduced. Found a real one still
  live: `run_simulation.py`'s per-tick loop runs `accrue_energy` (decay)
  unconditionally even while `IS_SLEEPING`, with no exclusion like Action
  Castle's own sleep-decay gate has -- reproduced it directly: with any
  `energy_decay_rate` above ~0.11, the tick-by-tick decay-then-recover
  sequence converges to a fixed point below the wake threshold, so that
  character never wakes up. No shipped persona hits it today, but the
  knob is real and already exercised by a test. Also flagged (not fixed,
  just noted): `drives.py` hardcodes `100` instead of importing
  `MAX_ENERGY`, and `Set_energy`/`Check_energy` are an intentional,
  tested cheat console shipped in Action Castle's live action list.
- Swept `godot-generative-agents/backend/actions.py` for sleep-gating:
  11 of its action classes (`Travel`, `Act`, `WaitPenn`, `DrinkPenn`,
  `EatPenn`, `Activate`, `Deactivate`, `TalkTo`, `Study`, `CheckOutBook`,
  `ReadPenn`) had no `IS_SLEEPING` check at all, unlike Action Castle's
  `SleepGate` mixin, which already covers every one of its own actions.
  Added the check to each (three of them -- `WaitPenn`/`DrinkPenn`/
  `EatPenn`/`ReadPenn` -- needed a new `check_preconditions` override,
  since they'd been relying on the parent's).
- Wrote `docs/design/belief-graph-implementation-roadmap.md`: a concrete,
  chunked build plan against the existing (unbuilt) belief-graph proposal
  doc, scoped to just the "mechanism + database" phases the user wants
  first (data model, mock extraction, `AgentMemory` wiring, the
  fall-asleep trigger, real LLM extraction) -- deferring clustering/GraphRAG.
- Built the Houston Hall sandwich shop end to end: registered `Sell`/`Buy`
  into `PENN_EXTRA_ACTIONS`/`PENN_ACTION_VERBS`, tagged Houston Hall
  `marketplace`, removed the old free unowned "sandwich" (replaced by
  for-sale varieties carried by a worker, to avoid a same-name matching
  ambiguity). Reused `Rosa Delgado` from the persona library instead of
  inventing a redundant character (she was already "Houston Hall dining
  staff, never leaves") and added a second worker, `Walt Higgins`, for
  "a couple." Gave every persona a default starting `Property.MONEY`,
  added an opt-in restock drive, and typed `ARGUMENTS_SCHEMA` slots onto
  `Sell`/`Buy` so a tool-calling brain gets structured fields instead of
  free text. New `test_sandwich_shop.py` (6 tests); fixed two pre-existing
  tests that hardcoded "3 free meals at Houston Hall" (now 2) and a
  `get`/`eat sandwich` demo test (switched to `apple`).
- Fixed the sleep-onset timing (a person should get sleepy after 5
  in-game hours). Found the actual blocker first: Penn personas never had
  a starting `Property.ENERGY` set anywhere, so `accrue_energy`'s
  exponential decay was starting from 0/unset -- every persona was
  already `IS_SLEEPY` on tick one, regardless of the decay constant's
  value. Added `_furnish_starting_energy` (seeds `MAX_ENERGY`). Retuned
  `_ENERGY_DECAY_CONSTANT`; when the target turn duration I was given
  (15 sec/turn) turned out not to match what's actually configured
  everywhere (`SEC_PER_STEP = 10`), changed the real defaults
  (`penn_world.SEC_PER_STEP`, `exporter.SEC_PER_STEP`,
  `sim_config.sec_per_step`, `SimClock.sec_per_step`) to 15 rather than
  just quietly recomputing against 10 -- the goal was for the stated
  premise to actually be true in the system, not reinterpreted around it.
  That surfaced a few tests relying on `SimClock`'s implicit default
  instead of passing `sec_per_step` explicitly like their siblings; fixed
  those too.

**Blockers / questions:**
- none

**Next:**
- `uv sync --extra server` in this env so the fastapi-gated test files
  actually collect -- still haven't done this, several files stay
  uncollectible/excluded from every full-suite run this week.
- Start on the belief-graph roadmap's Chunk 1 (the `BeliefGraph` data
  model) if that's still the next priority.
- Consider whether `Sleep`'s own gate should read the new
  `_furnish_starting_energy`/retuned decay constant in a live bake to
  confirm the 5-hour onset holds up outside the unit-test math.

## 2026-08-04
**Focus:** Give Sleep a real place to be reached from, then unify its gate (#931); scaffold Buy/Sell (#932); dead-code sweep

**Done today:**
- Dead-code sweep over my own commits (not the shared engine code that
  predates me): removed a superseded, commented-out
  `deduct_energy_every_turn` trigger in `action_castle.py` (replaced by
  `exponential_decay_energy` right above it, never deleted); fixed a
  comment on that function that called it "linear decay" when it's
  literally the exponential one; dropped two genuinely unused imports
  (`action_castle`, `clock`) from `test_action_castle_eat.py`. Biggest
  find: deleted `tests/test_energy.py` outright -- the original
  engine-wide energy TDD scaffold from 2026-07-22, which I reverted that
  same week in favor of the Action-Castle-scoped version, and then flagged
  for retirement in the journal three separate times without ever doing
  it. Every test in it failed for that reason, not from bit-rot.
- Scaffolded a minimal money/commerce system (#932) for me to build out
  later: `Property.MONEY`/`IS_FOR_SALE`/`PRICE`/`OWNER`/`BUYER` in
  `enums.py` (fixed a `Owner` casing typo along the way, and noted
  `Property.OWNER` -- who's authorized to sell -- is deliberately NOT the
  same thing as the engine's existing `item.owner` attribute, which tracks
  whoever currently carries an item). Added `Buy`/`Sell` stub classes to
  `actions/base.py`, heavily commented, `check_preconditions`/
  `apply_effects` both `raise NotImplementedError` with a TODO checklist
  covering the four preconditions (for-sale, money, not asleep, owner
  present + same location) plus a `Property.BUYER` dibs-marker idea
  (mirrors `CheckOutBook.checked_out_by` in the Penn codebase). Wrote
  `tests/test_commerce_scaffold.py`: 8 tests, 1 green (registration), 7
  failing cleanly with `NotImplementedError` pointing at exactly what's
  missing -- the spec to implement against, once I get to it.
- While wiring that in, broke `Describe`'s room-printing for a bit: my
  edit landed `Buy`/`Sell` in the middle of `Describe.apply_effects`'s
  tail, displacing its final `self.parser.ok(self.game.describe())` line
  into dead code after `Sell`'s `raise` -- so EVERY `look`/room-description
  in the whole engine went silent. Caught it because the full suite
  suddenly had way more failures than the 7 I expected; `git stash` on
  each file in turn pinned it to `actions/base.py`, and a fresh look at
  `git show HEAD:...` (not just scrolling the edited file) showed where
  the real last line had been. Moved it back. Full suite green again
  except the same pre-existing failures as yesterday.
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
