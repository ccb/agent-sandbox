# End-Game Endings — Design Spec

**Date:** 2026-06-10
**Status:** Approved ("go ahead")
**Goal:** Replace the placeholder climax (a 4.5s thought banner with a guaranteed-win auto-fight) with a canon-faithful end sequence that has three distinct endings and a real win/lose screen with Restart/Quit.

---

## Canon reframing (the bug this fixes)

Per *Lord of the Mysteries* (诡秘之主) canon, **a completed descent (降临) kills the entire city** — there is no heroic fight against a fully manifested outer god (外神). The fight only happens *after* the descent has been **stopped**, against the residual/partial manifestation. The current code is wrong: it runs `CombatEncounter` unconditionally at the climax, even at full descent strength, and the player always wins.

This reframes the climax into **two gates**:

1. **Gate 1 — Was the descent stopped?** Compare `manifestation_strength` at the deadline to `STOP_THRESHOLD`.
   - `strength > STOP_THRESHOLD` → the descent completes → **CITY DIES** (no fight).
   - `strength ≤ STOP_THRESHOLD` → the descent fails to fully manifest → proceed to Gate 2.
2. **Gate 2 — Did the player survive?** Run `CombatEncounter(residual strength)` **only here**.
   - win → **ALL-GOOD** (descent stopped *and* you live).
   - lose → **NEAR-GOOD** (descent stopped, but you die holding the line).

So the player's interference (sabotage / turning a waverer) is what drives strength below the stop threshold (Gate 1), and *further* interference is what tips the residual fight from lethal to survivable (Gate 2).

---

## Tuning

`STOP_THRESHOLD = 60.0`.

`manifestation_strength = clamp(100 * (ingredients_left / 8) - impede_score, 8, 100)`.

Player levers (unchanged from current code):
- **Sabotage** (`PlayerActions.sabotage`): −1 ingredient **and** +10 impede per item.
- **Turn Orin** (`PlayerActions.social_influence`): +12 impede (no ingredient change).

### CombatEncounter retune

The fight only ever runs at residual strength ≤ 60, so it must be tuned so that strength in the mid-50s is **lethal** and the low-40s is **survivable**. Player is unchanged (100 HP, 18 basic / 30 occult every 3rd round).

| Constant | Old | New |
|---|---|---|
| `enemy_max_hp` | `strength` | `strength * 2.5` |
| `enemy_damage` | `strength * 0.12` | `strength * 0.40` |

Win/lose crossover lands at strength ≈ 49–50 (simulated): 49 → win with ~2 HP, 50 → lose. This sits cleanly between the 55 (lose) and 43 (win) table rows below, giving comfortable separation.

### Ending table (derived from the lever math)

| Player actions | ingredients | impede | strength | Gate 1 | Gate 2 | Ending |
|---|---|---|---|---|---|---|
| nothing | 8 | 0 | 100 | descent completes | — | **city dies** |
| 1 sabotage | 7 | 10 | 77.5 | descent completes | — | **city dies** |
| 2 sabotages | 6 | 20 | 55 | stopped | lose | **near-good** (you die) |
| 2 sabotages + turn Orin | 6 | 32 | 43 | stopped | win (~14 HP) | **all-good** |
| 3 sabotages | 5 | 30 | 32.5 | stopped | win (~61 HP) | **all-good** |

The narrative beat: **two sabotages stop the descent but cost you your life; turning Orin (邪教 waverer) is what buys back your survival** — a clean, legible payoff for the social lever.

---

## Components

### 1. `CombatEncounter` retune (`tingen/src/CombatEncounter.gd`)
Change the two constants in `_init`. Nothing else changes; `auto_resolve()` keeps its `{win, rounds, player_hp_left}` shape.

### 2. `EndGameResolver` (new — `tingen/src/EndGameResolver.gd`)
`class_name EndGameResolver extends RefCounted`. Pure, static, deterministic — the testable seam.

```
const STOP_THRESHOLD: float = 60.0

static func resolve(strength: float) -> Dictionary:
    if strength > STOP_THRESHOLD:
        return {outcome="city_dies", win=false, rounds=0, player_hp_left=0.0, strength=strength}
    var r := CombatEncounter.new(strength).auto_resolve()
    return {outcome = ("all_good" if r.win else "near_good"),
            win=r.win, rounds=r.rounds, player_hp_left=r.player_hp_left, strength=strength}
```
`outcome ∈ {"city_dies", "near_good", "all_good"}`.

### 3. `EndGame` autoload (new — `tingen/src/EndGame.gd`)
`extends CanvasLayer`, `process_mode = PROCESS_MODE_ALWAYS` (so it works while the tree is paused, mirroring `DevConsole`). Registered in `project.godot` `[autoload]`.

Responsibilities:
- On `_ready`, connect to `SummoningPlan.summoning_climax(strength)` (guard with `is_connected`, matching `LiveDistrict`'s pattern).
- On climax: `var res := EndGameResolver.resolve(strength)`; store it; `get_tree().paused = true`; build the overlay; `emit_signal("ending_reached", res.outcome, res)`; log an `endgame` EventBus event.
- Overlay: a full-screen dim `ColorRect` + a `VBoxContainer` with a title, a body line, and two `Button`s (**Restart**, **Quit**). Title/body text keyed off `outcome`:
  - `city_dies` → "Tingen Falls" / "The descent (降临) completes. The city is consumed."
  - `near_good` → "The Line Holds" / "You break the summoning — and it breaks you. (N rounds)"
  - `all_good` → "Dawn Over Tingen" / "The summoning shatters and you walk away. (X HP left)"
- **Restart** → `restart()`: hide overlay, `get_tree().paused = false`, `_reset_world_state()`, then reload the world.
- **Quit** → `get_tree().quit()`.

`_reset_world_state()` (the testable part of restart): `SummoningPlan.reset()`, `Overseer.reset()`, `OccultToolManager.rebuild()`, `Agents.rebuild()`, `Clock.set_time(1, 480)`, `EventBus.clear()`.

Scene reload: `restart()` calls `get_tree().reload_current_scene()` **only when** `get_tree().current_scene != null` (the headless `-s` harness has no current scene, so this guard keeps `restart()` safe to unit-test).

Signals: `signal ending_reached(outcome: String, result: Dictionary)`.

### 4. Remove the fight from `LiveDistrict` (`tingen/src/LiveDistrict.gd`)
Delete `_on_climax` and its `summoning_climax` connection (lines ~55-56, ~214-220). `EndGame` now owns the climax. The `combat_resolved` EventBus event is superseded by the `endgame` event (and the resolver result carries the same fields).

---

## Testing (TDD, RED→GREEN per component)

All in `tingen/tests/run_tests.gd`, registered in `_init()`.

1. **CombatEncounter retune** — update `_test_combat_scaled_by_impede`: assert the new ratios (`enemy_max_hp == strength * 2.5`, `enemy_damage == strength * 0.40`) and the crossover (`CombatEncounter.new(55).auto_resolve().win == false`, `CombatEncounter.new(43).auto_resolve().win == true`).
2. **`_test_endgame_resolver`** — `resolve(100).outcome == "city_dies"`; `resolve(77.5).outcome == "city_dies"`; `resolve(60).outcome != "city_dies"` (boundary: 60 is *stopped*); `resolve(55).outcome == "near_good"`; `resolve(43).outcome == "all_good"`; `resolve(32.5).outcome == "all_good"`. Assert the result dict carries `win`/`rounds`/`player_hp_left`/`strength`.
3. **`_test_endgame_ending_bands`** — integration: drive `PlayerActions` levers from a fresh `SummoningPlan` (0 / 2 / 3 sabotages, ± turn Orin), feed `manifestation_strength()` to `EndGameResolver.resolve`, assert the ending-table outcomes. This guards the *whole chain* (levers → strength → ending), not just the resolver in isolation.
4. **`_test_endgame_autoload`** — fire `SummoningPlan.summoning_climax` at a city-dies strength and at an all-good strength; assert `EndGame` emits `ending_reached` with the right `outcome`, that `get_tree().paused` becomes true, and that an `endgame` EventBus event is logged. Then call `EndGame._reset_world_state()` and assert `SummoningPlan` is back to defaults and `paused` is cleared by `restart()`'s unpause path. (Unpause the tree in test teardown so later tests aren't affected.)

Existing climax tests (`_test_summoning_countdown_and_climax`, `_test_summoning_advance_rite`, `_test_summoning_progress_readouts`) are unaffected — they test `SummoningPlan` countdown/strength, not the climax *consumer*. They must stay GREEN.

Then: full headless suite GREEN + smoke run (`--quit-after 180`).

---

## Alternatives considered (rejected)

- **Make the climax fight losable at full strength** (my first proposal). *Rejected:* contradicts canon — a completed descent has no survivors, there is no fight. The user corrected this directly.
- **Binary ending (cache bare = win, else lose), no fight.** *Rejected:* throws away the existing `CombatEncounter` and the survival dimension; gives only two outcomes and no role for the social lever.
- **Cult-neutralized trigger (end when all cultists downed).** *Rejected:* conflates the combat sandbox with the summoning clock; the doomsday countdown is the dramatic spine, so the climax should resolve on *the clock reaching zero*, with strength deciding the outcome.
- **`STOP_THRESHOLD` on `SummoningPlan`.** *Rejected:* the threshold is end-game gate logic, not summoning bookkeeping — it belongs with the resolver that uses it.
- **EndGame builds the fight directly (no resolver seam).** *Rejected:* the pure `EndGameResolver` is the deterministic, headless-testable seam; the autoload stays a thin UI/pause shell around it.
- **Restart via full `SaveManager`/new-game flow.** *Rejected as overkill:* resetting the handful of stateful singletons + `reload_current_scene()` is the minimal correct restart; a guarded reload keeps it unit-testable.
