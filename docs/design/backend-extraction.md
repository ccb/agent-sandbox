# Shared `gen_agents` package + simulation config (tracking note)

**Status:** tracking note only — *no code change in this PR.* The work is
**blocked on [PR #166](https://github.com/ccb/agent-sandbox/pull/166)** ("Penn
agent world") landing first, so it doesn't balloon that PR's diff or disturb its
"the_ville stays byte-identical / 50 GA tests pass" guarantee. This doc exists so
the plan isn't lost; delete it (or move it under `implemented/`) when the move ships.

Once #166 lands, this PR delivers **two** things:

1. **Extract** `generative-agents/backend` into a shared top-level `gen_agents`
   package so both frontends import it by one canonical path.
2. **Fold in [PR #100](https://github.com/ccb/agent-sandbox/pull/100)
   (`SimulationConfig`).** #100 adds `backend/sim_config.py` — a file that lives
   *inside the very directory being moved* — so it rides along with the extraction
   instead of fighting it for the same paths and import surface. #100 is superseded
   by, and closed in favor of, this PR.

## Why

`godot-generative-agents` and `generative-agents` (Smallville) both run the **same**
agent simulation, but they reach the code two different ad-hoc ways:

- `generative-agents`' own tests/runners import `backend.*` by running with the
  working directory set to `generative-agents/`.
- `godot-generative-agents/sim/generate_penn_replay.py` reaches it with
  `sys.path.insert(0, "../generative-agents")` — a path hack into a sibling
  consumer.

So the shared code physically lives *inside one of its two consumers*, and there's
no single canonical import path. That's the wart to fix.

## What's already separated (so we scope this correctly)

There are three layers; two are already clean:

| Layer | Where it lives today | Shared? |
|---|---|---|
| **Engine** — `Game`, `Character`, actions, ReAct loop, embeddings | `text_adventure_games/` (repo root, pip-installed editable) | ✅ already the shared core |
| **Gen-agents app layer** — `world_map`, `build_world`, `run_simulation`, `smallville_agents`, `actions`, `path_finder` | `generative-agents/backend/` | ⚠️ shared by reference via the hacks above |
| **Frontend** — Phaser/Django viewer | `generative-agents/frontend/` | doesn't import the backend at all (file-based replay) |

The genuine shared engine is **already** `text_adventure_games`. What this move
extracts is the **gen-agents application layer** (`backend/`) so it stops living
inside `generative-agents/`.

## Plan (when #166 has landed)

**Minimal, high-value version:**

1. `git mv generative-agents/backend → gen_agents/` (top-level package).
2. Add it to the packaged set in the root `pyproject.toml` so it installs
   alongside `text_adventure_games` (no CWD assumptions, no `sys.path.insert`).
3. Update imports: `generative-agents` tests/runners and
   `godot-generative-agents/sim/generate_penn_replay.py` → `import gen_agents...`.
4. Update READMEs / `CLAUDE.md` references to the old `backend/` path.

**Fold in #100 (`SimulationConfig`):**

5. Rebase #100 onto the moved tree (or cherry-pick its single `feat` commit), so
   `sim_config.py` lands as `gen_agents/sim_config.py` with the rest of the package.
   `SimulationConfig` composes the engine's `GameConfig` and every field defaults to
   today's behavior, so this stays behavior-preserving like the move itself.
6. Close #100 in favor of this PR once its commit is incorporated here.

**Deferred wrinkle (own follow-up, optional):** `backend/` is still lightly
*Smallville-flavored* — `world_data.yaml`, `seed.py` (reads the_ville CSVs), and
the `PERSONAS` default all assume the_ville. The parameterization in #166 made the
*functions* world-agnostic, but the package still ships Smallville as the default
world. A fully clean split would separate **engine code** from **world data**
(`the_ville/`, `the_upenn/`). Worth doing once, but not required for the import-path
cleanup above.

## Acceptance

- One canonical import path for the shared sim code; the `sys.path.insert` hack in
  the Godot generator is gone.
- `SimulationConfig` (from #100) lives in the new package as `gen_agents/sim_config.py`.
- All 50 generative-agents tests still pass; the_ville sim output unchanged.
- Both frontends (Phaser replay + Godot replay) still run.
