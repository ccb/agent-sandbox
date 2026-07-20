# Spec: boil water as an engine crafting Recipe (supersedes the bespoke BoilWater) — #300 / #299

**Track:** godot-ga-main (Penn-local: recipe + Craft wiring in
`godot-generative-agents/backend/`; **no** `text_adventure_games/` change, so it
stays off `main`).
**Date:** 2026-07-17
**Supersedes:** the `BoilWater` half of
[`2026-07-16-boil-water-superaction.md`](2026-07-16-boil-water-superaction.md) (PR #590).

## Why change a working action

The delivered #590 models boiling as a bespoke `BoilWater` action that flips
`is_boiled` on the pot **in place** (no rename). It works, but:

- **It reads wrong.** The pot keeps the name `pot of murky water` after boiling, so
  the recovery narration says *"recovered after drinking pot of murky water"* and the
  demo drinks "murky water" twice. The state change is a hidden flag, invisible on
  screen (the symptom that prompted this).
- **It's a one-off, not a capability.** A hand-written `Action` subclass is opaque to
  an LLM: it can't discover it, reason about its inputs/outputs, or *learn* it. The
  payoff this whole thread feeds — #595 (does a model *choose* to boil from an
  aversive memory), #301 (does it *invent* the fix), #299 (LLM-modifiable loop) — is
  about an agent **reasoning over and acquiring capabilities**.

The engine already has the right primitive: the **crafting system** (`crafting.py` +
the `Craft` action, #135/#184). A `Recipe` is a *declarative* transform
(`inputs + tools → output`), resolved through the standard `Craft` verb, discoverable
("what can I make here?"), and **learnable** via `Game.learn_recipe` /
`learned_recipes`. That is precisely the surface an LLM interacts with, and data is a
far easier synthesis/modification target for a model than an `Action` class.

## Design

Model boiling as a registered `Recipe`, drop `BoilWater`, and drive it through the
engine `Craft` action:

- **Recipe (Penn-local, `penn_world.py`):**
  `Recipe(inputs=["pot of murky water"], tools=["stove"], output=<produce a "pot of
  boiled water" Item>, name="boiled water", result_text="You set the pot on the stove
  and boil it until the water runs clear.")`. `inputs` are **consumed** from the
  crafter's held items; `tools` must be **present** (the stove) but are not consumed.
- **Produced item (`make_boiled_pot`):** a real, distinctly-named `pot of boiled water`
  with `DRINKABLE`, `is_boiled=True`, `portions`. So the transform is a genuine object
  swap — the murky pot is gone, a boiled pot exists — legible everywhere.
- **Verb:** the existing crafting verb **`make boiled water`** (resolves the recipe by
  output name). No new engine verb; `Craft` is added to `PENN_EXTRA_ACTIONS`, and
  `make`/`craft` are already the discoverable crafting interface an LLM uses. (A
  literal `boil`→craft-verb alias is an optional tiny `main` follow-up, out of scope.)
- **Registration:** `game.add_recipe(_boil_recipe())` in the Penn `build_world_fn`,
  next to `_furnish_boil_water`.
- **Contamination + cure unchanged (`DrinkPenn`):** drinking raw `requires_boiling`
  water → sick; drinking water whose `is_boiled` is set (the *produced* pot) while sick
  → recovery. Recovery text now correctly reads *"…drinking pot of boiled water."*
- **Timeline event:** the recipe's `output` factory logs the `boiled` event the viewer
  marks, so the on-screen arc is unchanged.

## Non-goals / accepted limitations

- **Event redundancy (accepted, follow-up):** `Craft.apply_effects` logs its own
  `craft` event and the parser logs a per-command `craft` event, so a boil emits the
  `boiled` marker **plus** two `craft` records. Deduping the parser/Craft double-log is
  an engine (`main`) concern; for now the viewer shows an extra marker at the boil step
  (harmless; folds into the #593 per-event-marker work).
- **`learn_recipe` gating** (start unknown → learn it) is where #301 goes; here the
  recipe is `known` from the start (deterministic baseline).
- Lifting the Penn verbs (`Craft` registration pattern, DrinkPenn) into the shared
  engine stays **#464**.

## Acceptance

- Boiling **consumes** the murky pot and **produces** a `pot of boiled water`
  (assertable on the game state), the `boiled` event fires, and drinking the produced
  pot while sick recovers with narration/memory that say **"boiled water"**.
- The full mock arc still fires in order (sickness → boiled → recovery) in both the
  full cast (Sofia) and the #599 demo, with the demo's boil command updated to
  `make boiled water` and its recovery drink to `drink pot of boiled water`.
- No `text_adventure_games/` change; full Penn suite green; `black` clean; headless
  smoke passes.

## Verification

Rework `tests/test_boil_water.py`: replace the `BoilWater` unit tests with
recipe/`Craft` tests (murky consumed + boiled produced; `make boiled water` resolves;
the produced pot is drinkable/`is_boiled`), keep the DrinkPenn sicken/recover tests
(recovery now asserts the "boiled water" naming), and keep the end-to-end mock-run arc
test. Re-bake the #599 demo to confirm the arc + correct recovery wording.
