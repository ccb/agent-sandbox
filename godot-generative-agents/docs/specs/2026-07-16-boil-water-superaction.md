# Spec: `boil water` superaction — a test scaffold for the self-coding experiment (issue #300 / #299)

**Track:** godot-ga-main (backend-local, per the #464 precedent — Penn-local verbs
live in `godot-generative-agents/backend/actions.py`, not the shared engine).
**Date:** 2026-07-16

> **Superseded (2026-07-17).** The bespoke `BoilWater` action described below was
> replaced by modelling boiling as an engine crafting `Recipe` (the `make boiled
> water` craft verb), which produces a real `pot of boiled water` item instead of
> flipping `is_boiled` in place — a declarative, discoverable, learnable transform an
> LLM interacts with. See [`2026-07-17-boil-water-crafting.md`](2026-07-17-boil-water-crafting.md).

> **Update (2026-07-16) — full watchable arc.** The delivered build extends the
> minimal scaffold below into a complete, verifiable arc so the behavior reads on
> the Godot timeline. Changes vs. the original spec:
> - **Reusable pot, not cups.** Houston holds one `pot of murky water` with
>   `portions` (drinking keeps the vessel), replacing the two `cup`s + empty `pot`.
> - **Cure added** (reverses the original "no cure" non-goal, intentionally):
>   `DrinkPenn` now clears `is_sick` and logs a `recovery` event when a sick agent
>   drinks the *boiled* water — so the arc is drink → **sickness** → boil →
>   **boiled** → drink → **recovery**, three timeline events.
> - **Sofia's schedule** runs the arc across same-place Houston Hall stops.
> These are backend-local (still #464 for the engine lift). The sections below
> describe the original minimal design.
>
> **Update (2026-07-16) — #590 review response (@aking526).** Rebased onto the
> post-#581/#586 pacing rewrite and reworked per the review:
> - **No rename.** Boiling keeps the vessel's name and carries the change on
>   `is_boiled` + the description + the `boiled` event, instead of mutating
>   `.name` and hand-re-keying its owner/location dict (fragile for worn/container
>   items, and it would break another agent's authored `drink pot of murky water`
>   once the shared pot were renamed). The same `drink pot of murky water` command
>   therefore sickens while raw and cures once boiled.
> - **Cure gated on `is_boiled`** (not "any safe drink") + a survived-the-drink
>   guard, so the #301 "did it learn to boil?" comparison stays meaningful and a
>   poisoned drink can't log a recovery on a corpse.
> - **Sickness emoji via the pron authority chain** (`_resting_pron`), a low
>   priority overlay under a model's explicit pick — not a frame-time override
>   that masked a real brain's emoji for the whole sick window.
> - **De-clumped without `wait` filler:** the arc is three same-place Houston
>   stops whose `steps:` gaps space the events, so no `wait` commands flood the
>   card with 1.0 memories / events. `boil` is remembered at 6.0 (the arc's
>   hinge); `wait` is never remembered nor offered as a real-brain tool (retired
  by #614: a chosen `wait` is now offered with pacing slots and, when
  settled, remembered).
> - **`boil` takes npc.py's free-text slot** (dropped the advisory-but-ignored
>   `target` schema); single-vessel effect + scalar `item` event payload.

## Problem

The boil-water world exists (#300 / #465): Houston Hall holds two `cup of murky water`
items (`requires_boiling: True`, `is_boiled: False`), a `pot`, and `sink`/`stove`
devices; `DrinkPenn` sickens whoever drinks unboiled water. But **nothing in the world
can flip `is_boiled` to `True`** — that capability gap is deliberate, reserved for the
self-coding experiment (#301), where the agent is meant to *write* the boil action
itself.

That leaves a gap in the *other* direction: we can't yet run an end-to-end test of the
question "when an agent is sick from raw water and a pot + stove are right there, does
it decide to boil the water before drinking?" — because there is no boil capability for
the agent to choose *at all*. We want to observe that decision behavior **now**, with a
hand-authored boil action, before (and independently of) building the #301 seam that
lets the agent author its own.

This spec is explicitly a **test scaffold**, not the research payoff. It is the
known-good "correct answer" boil capability against which #301's agent-authored version
can later be compared.

## Non-goals (YAGNI — this is a test scaffold)

- **No multi-step recipe.** We are *not* building `fill pot from sink`, container-state
  on the pot, a stove heat-process, or a `SEQUENCE`-style expansion. Those test whether
  the agent can *assemble* a recipe — which is the #301/self-coding question, and much
  heavier. This scaffold tests only whether the agent *chooses to boil* when it can.
- **No new objects.** The existing `pot` is the container (we do not add a "kettle");
  the `sink` stays a plain on/off device. Water is the pre-filled cups already in the
  room.
- **No cure semantics beyond prevention.** Boiling makes water safe to drink; it does
  not cure an already-sick agent. (Matches the world's existing "no cure" stance,
  `DrinkPenn` docstring.)
- **No shared-engine change.** Stays backend-local on `godot-ga-main`; upstreaming the
  boil-water verbs to `text_adventure_games/` remains tracked in #464.

## Approach (decided): one self-contained `BoilWater` action

A single `Action` subclass in `godot-generative-agents/backend/actions.py`, registered
alongside `Activate`/`Deactivate`. It gates on the real props being present and, in one
atomic `apply_effects`, marks the room's unboiled water safe.

### `BoilWater(base.Action)`

- `ACTION_NAME = "boil"`
- `ACTION_DESCRIPTION = "Boil water on a stove to make it safe to drink"`

**Command shape.** `boil water` (the object word is matched loosely; the action does not
require the agent to name a specific cup — see effects). The acting character is
resolved with `acting_character(command, hint="cook")`, mirroring `Activate`.

**Preconditions** (`check_preconditions`), each with a distinct `parser.fail` reason so
a failed attempt feeds a usable message back through the ReAct retry seam:

1. A character is acting (`was_matched`), and has a location.
2. A `pot` is in scope at the character's location — else *"There's no pot here to boil
   water in."*
3. A `stove` (an `is_device` item named `stove`) is in scope — else *"There's no stove
   here to heat it on."*
4. At least one item at the location has `requires_boiling` and not `is_boiled` — else
   *"There's nothing here that needs boiling."*

Scope is resolved with `parser.get_items_in_scope(self.character)`, the same call
`Activate` uses, so "in scope" means the room's items (the props are location fixtures,
not inventory).

**Effects** (`apply_effects`):

- Set the `stove`'s `is_on` to `True` (the visible fixture state change — the burner is
  running).
- For **every** item at the location with `requires_boiling` and not `is_boiled`, set
  `is_boiled = True`. (Boils all raw water present in one go; keeps the test
  deterministic regardless of which cup the agent later drinks. The two-cup world means
  a later "drink" can't accidentally hit an un-boiled cup.)
- `parser.ok(...)` with a short narration, e.g. *"<Name> fills the pot at the stove and
  boils the water until it's safe to drink."*
- `self.game.log_event(character, "boiled", summary=..., payload={"location": ...,
  "items": [names]})` — mirrors the existing `sickness` event so the boil moment lands
  in the change feed and the run record (observable in the viewer / baked replay,
  parallel to how sickness already surfaces).

**Interaction with `DrinkPenn` (already correct, no change needed):** `DrinkPenn` only
sickens when the drunk item `requires_boiling and not is_boiled`. Once `BoilWater` flips
`is_boiled`, a subsequent `drink cup of murky water` takes the safe path — no `is_sick`,
no `sickness` event. This is the end-to-end signal the test asserts.

## Tool exposure (so a real brain can pick it)

Add an `ARGUMENTS_SCHEMA` to `BoilWater` following the `Travel`/`Act` pattern
(issues #356/#485) so a tool-calling brain sees `boil` as a typed action:

```python
ARGUMENTS_SCHEMA = {
    "target": {
        "type": "string",
        "description": "what to boil, e.g. 'water'",
        "required": False,
    },
}
```

`target` is optional and advisory — the action boils the room's raw water regardless of
the exact string (it does not resolve a specific cup), matching the loose command shape.
This keeps the mock-schedule command (`boil water`) and a tool brain's structured pick
parsing identically, the same way `Travel` reconciles both.

## Exercising it in a run

Extend the existing murky-water persona schedule (`world_data_upenn.yaml`, the Houston
Hall dinner stop currently running `get cup of murky water` → `drink cup of murky
water`). Add a **boil-first variant** so a mock run demonstrates the healthy path:

```yaml
  - place: Houston Hall
    activity: boiling water before dinner
    commands:
    - boil water
    - drink cup of murky water
```

Decision on which schedule ships as the default (sick path vs. healthy path) is a
one-line toggle and is called out in the plan; both are useful — the sick path is the
#300 motivation demo, the healthy path is this scaffold's demo. Default: keep the
existing sick-path stop and add the healthy-path variant as a commented alternative, so
#300's demo is unchanged and the boil path is one uncomment away. (The real *test* of
the behavior is the pytest below, which doesn't depend on the schedule.)

## Testing

Extend `godot-generative-agents/tests/test_boil_water.py` (same `_tiny_world` /
`_cup` fixtures; add a pot + stove to the tiny world helper):

1. **Registration:** `boil` resolves to `BoilWater` in `game.parser.actions`.
2. **Happy path:** in a room with pot + stove + an unboiled cup, `boil water`
   succeeds, flips the cup's `is_boiled` to `True`, and sets the stove `is_on`.
3. **Prevents sickness end-to-end:** after `boil water`, `drink cup of murky water`
   leaves `is_sick` unset and logs no `sickness` event — the core assertion.
4. **Precondition failures** (three cases): no pot / no stove / no unboiled water each
   fail with the specific message and change no state.
5. **Event:** a `boiled` GameEvent is logged with the location and item names.
6. **Idempotence:** boiling when all water is already boiled fails cleanly on
   precondition 4 (nothing to boil), not a crash.

All offline on the mock brain; no keys, no spend.

## Files touched (all `godot-generative-agents/`, all `godot-ga-main`)

- `backend/actions.py` — new `BoilWater` action.
- `backend/penn/penn_world.py` — register `BoilWater` in the Penn action set (beside
  `Activate`/`Deactivate`); no prop changes (pot/stove/cups already stocked).
- `backend/penn/world_data_upenn.yaml` — add the commented boil-first schedule variant.
- `tests/test_boil_water.py` — the assertions above.

## Success criteria

- `uv run pytest godot-generative-agents/tests/test_boil_water.py -q` green, including
  the new boil + no-sickness assertions.
- On a mock run with the boil-first stop active, the agent boils water and never trips
  `is_sick`; a `boiled` event appears in the feed/run record.
- The `is_boiled`-flipping capability lives **only** in this hand-authored action —
  #301's self-coding seam remains the (separate) path by which an agent could author its
  own equivalent, so this scaffold does not pre-empt the experiment.

## Relates to

- #300 (boil-water world slice — the props this action operates on), #299 (self-coding
  epic — this is the hand-authored baseline it will be compared against), #301 (the
  self-coding seam — deliberately *not* built here), #464 (upstreaming the boil-water
  verbs to the shared engine — still deferred).
