# Spec: Boil-from-aversive-memory experiment + minimal thirst stakes (issues #595, #594)

**Track:** godot-ga-main (Penn-local, per the #300/#464 backend-local precedent).
**Date:** 2026-07-17

## Problem

The boil-water scaffold (PR #590) gives the Penn world a `boil` crafting recipe and a
`sicken → boil → recover` arc, but it is driven by the **mock** brain replaying authored
`commands` — it cannot *reason*. The open research question (#595, precursor to #301
self-coding) is whether a **live LLM** brain, carrying an aversive memory of getting
sick, will **choose to boil the water before drinking it** — connecting "the raw water
here made me ill" + "there is a stove and pot" → "boil first".

Two gaps block a clean experiment:

1. **No motivation to drink.** Under a live brain the authored `commands` do nothing
   (`cognition.attach_agents` treats them as a mock-only concept), so nothing makes the
   agent drink at all. The engine has an `IS_THIRSTY` boolean and `Drink` clears it, but
   **nothing raises it**, so there is no drive.
2. **Sickness is invisible to the brain.** `DrinkPenn` sets `is_sick` + logs a
   `sickness` event, but nothing makes being sick *perceivable in the decide prompt*, so
   a live brain cannot reason about avoiding it.

## Goal

A reproducible standalone experiment reporting a **boil-before-drink rate** for a live
Haiku brain on the seeded-aversion scenario, clearly above a no-memory control — backed
by the *minimal* thirst/sickness stakes the experiment needs, and an **authoritative,
action-recorded outcome signal** (not a downstream event-log classifier).

## Framing (decided)

- **The experiment (#595) is the deliverable; thirst (#594) is minimal stakes.** Build
  only as much of #594 as the experiment needs; a fuller drives system (accumulation
  curves, incapacitation, generic-engine lift) is explicitly out of scope here.
- **Penn-local, on `godot-ga-main`.** The thirst/sickness wiring and the outcome
  recording live in `godot-generative-agents/backend/`, next to the existing Penn boil
  verbs — the same backend-local pattern the boil scaffold shipped under (#300/#464). A
  generic engine lift can follow later, as #464 follows #300.
- **The outcome is recorded by the actions at the point of effect**, not reconstructed
  from the event log — the action that applies the effect is the authority on what
  happened.

## Approach

### 1. Minimal thirst drive (Penn-local)

A per-tick `thirst` counter on each persona; past a threshold it flips the existing
`Property.IS_THIRSTY` (`enums.py:56`), which `Drink` already clears
(`consume.py:128`). Wired into the Penn step loop next to the existing pacing hooks, so
every tick nudges thirst up and re-evaluates the flag. Surfaced as one line in the
decide observation when thirsty ("You are thirsty."), so the brain is motivated to seek
and drink water.

**Scope guard:** no incapacitation, energy, or death. Max thirst simply holds
`IS_THIRSTY` true (a persistent drive). One rate + one threshold, authored as constants
(tunable per persona later if needed).

### 2. Perceivable sickness (Penn-local)

`DrinkPenn` already sets `is_sick` on drinking unboiled water. Add one strong-negative
line to the decide observation when `is_sick` ("You feel violently ill — your stomach is
cramping."), so the brain perceives the state it should learn to avoid. The existing
recovery arc (#590) is unchanged.

**Scope guard:** sickness is *prompt-legible only* — no movement degradation, blocked
actions, or energy penalty. Perceivability is all the experiment needs.

### 3. Authoritative outcome recording (in the actions)

The causal outcome is stamped as first-class character state where the effect is
applied — the harness reads state, never parses events:

- **`DrinkPenn.apply_effects`** already branches on `requires_boiling` / `is_boiled`. It
  stamps the drink's causal outcome on the drinker: increment `drank_unboiled` when the
  water needed boiling and was not boiled, `drank_boiled` when it drinks safe water
  (boiled, or water that never required boiling). (A `last_drink_outcome` string may
  accompany the counters for readability.)
- **The boil recipe** (the engine `Craft` producing boiled water) stamps that boiling
  happened on the actor (`has_boiled` / a `boiled` count) — used for the "neither" vs
  "boiled but didn't drink" distinction.

These are plain boolean/int properties on the `Character` (properties are a
`defaultdict(bool)`; any name can be set), default-absent so a non-experiment run is
byte-unchanged.

### 4. Seeded aversion + control

A t=0, high-importance memory added via `memory.add_observation(text, turn=0,
importance=...)` at or above the seeded day-plan memory's importance (5.0, the value
`attach_agents` already uses for `add_plan`) so retrieval ranks it highly (the
`backend/seed.py` pattern) — *"Last time I drank the unboiled water at Houston Hall I
got violently ill."* Toggleable per persona (a `seed_memories:`
list on the boil-world persona, consumed in `attach_agents`, or an experiment flag). The
**control arm omits it; everything else is identical.**

**Retrieval risk (verify):** the seeded memory must actually be *retrieved* into the
Houston decide prompt (the #595 open risk; ties to the #580 context block). If default
keyword/importance retrieval does not surface it, nudge via importance and/or a tag —
documented in the experiment's findings, not hidden.

### 5. Scenario / fixture

Reuse the single-persona `world_data_boil.yaml` (Houston Hall, murky water + stove + pot
+ boil recipe already present, PR #592) as a **live variant with the authored
`drink`/`boil` `commands` removed**, so the brain decides freely. The persona starts
thirsty (or thirst accrues quickly) at Houston. Whether this is a new YAML or the
experiment strips `commands` in-memory is an implementation detail for the plan.

### 6. Experiment harness

`godot-generative-agents/backend/penn/experiments/boil_from_memory.py` (new). For each
arm (**seeded** / **control**) × N trials:

1. Build the boil-scenario world; attach a **live Haiku** client (reuse
   `serve_penn.resolve_llm` / the stepper, or `run_simulation.simulate(llm_client=...)`).
2. Seed thirst so drinking is motivated; seed the aversion memory (seeded arm only).
3. Run headless for a bounded number of steps.
4. Read the per-trial outcome **directly from the action-recorded state**:
   `drank_unboiled == 0 and drank_boiled > 0` → **boiled-then-drank** (success);
   `drank_unboiled > 0` → **drank-raw**; no drink → **neither**.
5. Aggregate and print a per-arm **boil-before-drink rate** + the run's ledger spend.

Small N (≈5–10 per arm) to bound spend; trials vary via temperature and/or per-trial
seed. `ANTHROPIC_API_KEY` in-env only, never written to disk.

## Data flow

experiment script → builds Penn boil world + live client → per-tick thirst hook raises
`IS_THIRSTY` → brain observes (thirst + sickness-if-any + murky-water affordance +
retrieved aversion memory) → decides (boil-then-drink vs drink-raw) → `DrinkPenn` /
boil recipe stamp the authoritative outcome on the character → harness reads that state
→ per-arm rate report.

## Testing

- **Offline (CI, no key):**
  - Unit: thirst accumulation raises `IS_THIRSTY` at the threshold and `Drink` clears
    it; the sick / thirsty observation lines render when (and only when) the flags are
    set; a seeded memory is added at t=0 and is retrieved into the decide prompt.
  - Unit: the outcome flags — `DrinkPenn` stamps `drank_unboiled` vs `drank_boiled`
    correctly for boiled/unboiled/never-required water; the boil recipe stamps
    `has_boiled`.
  - End-to-end smoke: the experiment script runs to completion under the **scripted
    brain** (`--brain scripted`, #563) with no key, exercising the full harness plumbing
    and the outcome-reading path (asserts the report is produced and the outcome fields
    populate) — the research *claim* is not asserted here.
- **Live measurement:** gated, manual, needs a key + small spend — not in CI. Its output
  (the rate report) is the #595 acceptance artifact.

## Acceptance

- A reproducible live-brain run of `boil_from_memory.py` prints a boil-before-drink rate
  per arm, with the seeded-aversion arm clearly above the no-memory control (#595
  acceptance).
- Offline suite green (`pytest godot-generative-agents/tests/`), `black` clean; the
  default mock bake stays byte-identical (no thirst/sickness/outcome state on a
  non-experiment persona).

## Out of scope

- A generic engine drive / needs system in `text_adventure_games/` (Penn-local first;
  lift later like #464).
- Mechanical sickness effects (movement/energy/blocked actions) — prompt-legible only.
- Incapacitation, death, or thirst accumulation curves beyond one rate + threshold.
- Record/replay cassettes for free re-runs (#197) — a later reproducibility upgrade.
- The self-coding step (#301) — this only shows the model can *choose* the existing
  tool; inventing it is #301.

## Relates to

- Follow-up from PR #590 (boil-as-crafting-recipe); precursor to #301 (self-coding),
  home epic #579 (Smallville-parity cognition).
- #594 (thirst drive) — this builds its minimal Penn-local slice.
- #580 (decide-context block) — where thirst/sickness/aversion must be legible.
- #563 (scripted brain) — the offline smoke's key-free driver.
- #464 / #300 — the backend-local-then-lift precedent this follows.
