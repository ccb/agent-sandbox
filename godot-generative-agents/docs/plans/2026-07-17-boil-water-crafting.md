# Plan: boil water as a crafting Recipe (rework #590)

Spec: [`../specs/2026-07-17-boil-water-crafting.md`](../specs/2026-07-17-boil-water-crafting.md).
Branch: `feat/boil-superaction` (rework #590 in place); the #599 demo branch
(`feat/boil-demo-592`) gets a small follow-on edit. **All godot-ga-main.**

## Steps

1. **`backend/penn/penn_world.py` — the recipe.**
   - Imports: `from text_adventure_games.actions.things import Craft`,
     `from text_adventure_games.crafting import Recipe`; drop `BoilWater`.
   - Add `make_boiled_pot()` → a `pot of boiled water` Item (`DRINKABLE`,
     `is_boiled=True`, `portions=3`).
   - Add `_boil_recipe()` → `Recipe(inputs=["pot of murky water"], tools=["stove"],
     output=_produce, name="boiled water", result_text=…)`, where `_produce(game)`
     builds `make_boiled_pot()` and logs the `boiled` event.
   - `PENN_EXTRA_ACTIONS`: replace `BoilWater` with `Craft`.
   - `PENN_ACTION_VERBS`: replace `"boil"` with `"make"` (the crafting verb the brain
     may choose).
   - In `build_world_fn._build`: `game.add_recipe(_boil_recipe())` after
     `_furnish_boil_water(game)`.

2. **`backend/actions.py` — drop `BoilWater`.** Remove the class (keep `DrinkPenn`,
   `Activate`, `Deactivate`). Confirm `DrinkPenn`'s recovery gate stays
   `is_sick and item.is_boiled` — the produced pot satisfies it, and its name drives
   the now-correct "boiled water" narration. No other change to DrinkPenn.

3. **`backend/penn/world_data_upenn.yaml` — Sofia's arc.** `boil water` →
   `make boiled water`; recovery drink `drink pot of murky water` →
   `drink pot of boiled water` (the produced item). Update the inline comment.

4. **`tests/test_boil_water.py` — rework.**
   - Remove the `BoilWater` import + its unit tests (registration, in-place flip,
     precondition failures).
   - Add crafting tests: `make boiled water` consumes the murky pot and produces a
     `pot of boiled water`; the produced pot is `DRINKABLE`/`is_boiled`; the recipe is
     registered; boiling with no stove / no murky water fails cleanly.
   - Keep DrinkPenn sicken/recover unit tests; update the recovery assertion to expect
     the "boiled water" item name.
   - Keep the end-to-end mock-run arc test (sickness→boiled→recovery in order); update
     any `boil water` command → `make boiled water`.
   - Keep the Houston-Hall stocking + Sofia-schedule tests; update the arc-command
     assertions (`make boiled water`, `drink pot of boiled water`).

5. **Spec bookkeeping.** Add a short "superseded by 2026-07-17-boil-water-crafting"
   pointer atop the #590 superaction spec.

6. **#599 demo follow-on (separate commit on `feat/boil-demo-592` after this lands /
   rebases):** `world_data_boil.yaml` boil command → `make boiled water`, recovery →
   `drink pot of boiled water`; `test_boil_demo.py` verb-free-activity guard + the
   scenario assertions updated; re-bake to confirm the arc + correct wording. (The
   proto worktree already proved this bake path works.)

## Verification (run from the worktree)

- `uv run pytest godot-generative-agents/tests/ -q` — full Penn suite green.
- `uv run black --check` on the touched files.
- `./godot-generative-agents/run_smoke_test.sh` — viewer still builds.
- `LLM_PROVIDER=mock … generate_penn_replay.py --steps 1100` (full) and, on the demo
  branch, `--scenario boil`: assert `sickness`/`boiled`/`recovery` fire in order and
  the recovery event/memory read "boiled water".
- Confirm **no** file under `text_adventure_games/` changed (`git diff --stat`).

## PR

Update #590 in place (same branch): retitle to
"feat(boil): boil water as a crafting recipe (#300)", rewrite the body around the
recipe design, link the new spec. #599 rebases and gets its follow-on commit.
