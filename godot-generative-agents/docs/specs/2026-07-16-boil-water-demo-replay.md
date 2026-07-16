# Spec: de-clumped boil-water demo replay (issue #592)

**Track:** godot-ga-main (replay/world-data + viewer menu; no engine change).
**Date:** 2026-07-16
**Follows:** [`2026-07-16-boil-water-superaction.md`](2026-07-16-boil-water-superaction.md) (PR #590)

## Problem

The full boil-water arc (drink → **sickness** → boil → **boiled** → drink →
**recovery**) is authored on **Sofia's** schedule, whose day is a long
gallery (220) → Irvine (60) → Houston preamble. In a bundled bake the three
timeline events don't fire until ~step 945 of an ~1100-step replay — they cluster
in the last ~13% of the scrubber, and a viewer has to scrub past Sofia's whole day
to reach the demo. Widening the in-arc `wait` spacers only separates the events
locally; it can't move the arc off the far-right end.

## Goal

A legible, self-contained boil-water demo where the arc starts early and spreads
across most of a short replay, leaving Sofia's curated day and the bundled replay
untouched.

## Design (approach 1 — dedicated short replay)

The world factory `build_penn_world(world_data=…)` is already parameterized on the
world YAML, and `_furnish_boil_water()` unconditionally stocks Houston Hall with the
props inside the shared `_build`. So a scenario needs only a new YAML + a bake flag:

1. **`world_data_boil.yaml`** — one persona (`Nadia Okafor`) **homed at Houston
   Hall** (so `build_world` places her at the props from step 0, no commute), plus
   the two locations she references (`Penn campus` hub + `Houston Hall`). No
   meetings/relationships.

2. **Multi-stop spacing, not `wait` spacers.** The arc is four Houston Hall stops
   (lead-in → drink → boil → drink → recovered tail) whose `steps:` gaps space the
   events. This matters because the engine parser logs a `GameEvent` **per command**
   (`parsing.py`), so explicit `wait` commands become one timeline marker *each*
   (Sofia's arc logged ~54 wait markers); a `perform` block driven by `steps:` logs
   **one** marker for the whole window. Result: 12 events total, of which the three
   arc events are the only interesting markers.
   - The #590 note that "multi-stop breaks" was a mis-diagnosis: `MockPlanner` builds
     one `Stop` per schedule entry with **no merging** (`planner.py`), and
     `ScheduleMockClient.replace_schedule` re-attaches each stop's dropped `commands`
     positionally by `(place, activity)`. The real failure was a **verb in the
     `activity`** string: `perform "drinking the boiled water"` was re-parsed as a
     bare `drink` (the #535 "Diego's 'late' → EAT" hazard). Fix: every demo activity
     is verb-free prose (guarded by a test).

3. **`--scenario {penn,boil}` flag** on `generate_penn_replay.py` — selects
   `{world YAML, default step budget, output file}` from a `SCENARIOS` table.
   `boil` → `world_data_boil.yaml`, 90 steps, `maps/penn_replay_boil.json`.
   `--steps`/`--out` still override. `penn` (default) is the unchanged bundled bake.

4. **Viewer menu** — `main_menu.gd` shows a **"Play the boil-water demo"** button
   pointing at `penn_replay_boil.json`. Like the bundled replay it's a git-ignored
   artifact, so the button **self-hides until baked** (the bundled button stays,
   being the primary entry point).

## Acceptance

- A bake where sickness/boiled/recovery start early and spread across the timeline,
  clearly separated: default 90-step bake fires them at ~12% / ~44% / ~76%, ~29
  steps apart, with a healthy lead-in and a recovered tail (🤢 reverts).
- The timeline is not flooded (≤ 20 events; no `wait` markers).
- Sofia's meetings + the bundled replay are unaffected (the default scenario and the
  full-cast world are unchanged).

## Verification

`tests/test_boil_demo.py`: scenario-table wiring, single-Houston-persona + props,
verb-free-activity guard, and a mock bake asserting the arc fires in order, early,
separated, quiet, with the sick emoji showing then reverting — plus that the full
world still carries Sofia's arc. Full Penn suite green; `black` clean; headless
smoke test passes (menu still builds).

## Out of scope / follow-ups

- **#593** — distinct per-event-type marker colors (this demo makes the three events
  the *only* interesting markers, but they still render one color).
- **#595** — the connect-the-dots LLM experiment; this replay doubles as its fixture.
