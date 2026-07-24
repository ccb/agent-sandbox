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
