# Authoring our own world + sprites (research notes)

**Status:** research / scoping notes, not an implementation spec. Seeds the tracked task in
issue **[GA] Research: author our own world + sprites**. Companion to the Godot reference
survey [`godot-multi-agent-playground.md`](godot-multi-agent-playground.md) and the port
survey [`generative-agents-port.md`](generative-agents-port.md).

## Why

Today the Smallville sim borrows its **entire** world and cast art from the upstream
Stanford repo [`joonspk-research/generative_agents`](https://github.com/joonspk-research/generative_agents).
[`generative-agents/setup.sh`](../../generative-agents/setup.sh) rsyncs the `the_ville` map
+ 25 character sprites + the `base_the_ville_n25` base sim out of a manually-cloned
`external/generative_agents/` into the git-ignored `frontend/`. We want to eventually stand
up **our own** world + characters. The good news: the backend is **fully data-driven** — a
custom world is an asset/data authoring job, **not** an engine code change (see
[`build_world.py`](../../generative-agents/backend/build_world.py) /
[`world_map.py`](../../generative-agents/backend/world_map.py)).

## What "a world" actually is — the author-your-own checklist

To replace `the_ville` you author three layers. The hard part is **not the art** — it's
keeping the *semantic* maze CSVs aligned with the *visual* tilemap, and sourcing
license-clean assets.

### 1. MAP — semantic grid (what the backend reads)
Read by [`world_map.py`](../../generative-agents/backend/world_map.py). Lives under
`assets/the_ville/matrix/` (git-ignored / fetched by `setup.sh`):

| File | Format / contract |
| --- | --- |
| `matrix/maze_meta_info.json` | `{ "maze_width": W, "maze_height": H, "sq_tile_size": 32 }` |
| `matrix/maze/collision_maze.csv` | flat row of `W·H` cells; `"0"` = walkable, non-`0` = wall |
| `matrix/maze/sector_maze.csv` | per-tile sector id → resolves `the Ville:Hobbs Cafe` |
| `matrix/maze/arena_maze.csv` | per-tile arena id → `the Ville:Hobbs Cafe:cafe` |
| `matrix/maze/game_object_maze.csv` | per-tile object id → `…:behind the cafe counter` |
| `matrix/maze/spawning_location_maze.csv` | per-tile spawn id → `<spawn_loc>sp-A` |
| `matrix/special_blocks/{world,sector,arena,game_object,spawning_location}_blocks.csv` | id → human-readable label maps |

These encode the **4-level `world:sector:arena:object` address hierarchy** the sim uses for
locations and pathing. `the_ville` is 140×100 @ 32px — a custom world can be **any** grid
size (smaller is much easier; see the 2025 lesson below).

### 2. MAP — visuals (what the Phaser frontend draws)
Lives under `assets/the_ville/visuals/`:

- `the_ville_jan7.json` — a **Tiled** map export (10 layers: grounds, walls, interior
  furniture, foreground). Imports natively into Godot too.
- `map_assets/.../*.png` — the tileset PNGs the Tiled map references (CuteRPG, Room_Builder,
  interiors, blocks, …).

### 3. SPRITES — characters
Lives under `assets/characters/`:

- One `First_Last.png` sprite sheet **per persona** (filename matches the display name in
  `world_data.yaml`).
- A **single shared** Phaser atlas `atlas.json` used by every character PNG; frame names
  follow `down`/`up`/`left`/`right` + `…-walk.000/001/…` (e.g. `down-walk.000`).
- `profile/*.png` portraits for the agent card.

### 4. PERSONAS — the cast + locations
- **Committed** here: [`backend/world_data.yaml`](../../generative-agents/backend/world_data.yaml)
  — personas (`name`, `home`, first-person `persona` text, `destination`, `activity`,
  `emoji`, `start_tile: [x,y]`) + locations (`name`, `description`, 4-level `address`, `hub`).
  This is the one cast/world file that lives in **our** repo.
- **Git-ignored / fetched** (from the upstream `base_the_ville_n25`): per-persona
  `bootstrap_memory/scratch.json` (identity + cognition knobs) and `spatial_memory.json`
  (partial known-places tree), plus `agent_history_init_n25.csv` (seed relationships). These
  are folded in by [`backend/seed.py`](../../generative-agents/backend/seed.py) and tolerate
  being absent.

### Committed vs. fetched (at a glance)
- **In our repo:** `world_data.yaml`, `frontend_overrides/` (UI), `backend/` code.
- **Fetched by `setup.sh` / git-ignored:** the whole `frontend/` tree — all `the_ville`
  matrix CSVs, tilemap + tilesets, character sprites, and the base-sim bootstrap memories.

So a custom world means **replacing the fetched assets** with our own and pointing the run
at them (the backend reads paths; no code edits required to swap the data).

## What the 2025 project did (and its biggest gotcha)

From [`godot-multi-agent-playground.md`](godot-multi-agent-playground.md):

- **World:** a *single house* (≈8 rooms), built **directly in Godot `TileMapLayer`s — not
  Tiled**, and modeled in the Python backend rather than the renderer. They deliberately
  stayed **house-scale**, not a 140×100 town, for tractability.
- **Characters:** `AnimatedSprite2D` with idle/walk × 4 directions; pathfinding via
  `NavigationAgent2D`. Interactable objects (fridge, oven, …) driven by an
  `InteractableComponent` signal system.
- **Assets:** sourced from **itch.io** packs — *not* custom-drawn.
- **⚠️ Licensing is the headline caveat.** Only a few assets are confirmed clean (Alex
  Kovacs food icons = **CC BY 4.0**, Noto Color Emoji = **OFL**). The most polished art —
  inferred to be **LimeZu "Modern Interiors"** and similar **paid** packs — ships with **no
  license file** in their repo. Treat all such assets as **unverified**; confirm ownership
  before reusing anything from that project.

**Takeaways for us:** (1) start **small** — a few buildings beats a town; (2) **verify every
asset license** up front and keep attribution files in-repo; (3) the Godot-native authoring
path is real, but it diverges from our current Phaser/Tiled + maze-CSV contract.

## Options for authoring our own (not deciding here)

- **A — Smaller Tiled map + matching maze CSVs.** Author a compact map in Tiled with
  license-clean tile packs, then produce the five maze CSVs + `special_blocks` label maps to
  match. Keeps the current Phaser frontend + exporter contract intact. Lowest-risk for the
  existing replay.
- **B — Godot-native authoring** (like the 2025 project). Build the world directly in Godot
  `TileMapLayer`s and skip Tiled. Pairs naturally with the Godot frontend port (see
  [`NEXT-STEPS.md`](../../generative-agents/NEXT-STEPS.md) bottom section + PR #146), but
  means re-homing the semantic grid.
- **C — A small CSV-from-Tiled tool.** Write a converter that derives
  collision/sector/arena/object CSVs from a Tiled map's layers/object groups, so the visual
  map and the semantic grid can't drift. Useful regardless of A vs B.

The recurring constraint across all three: the **semantic maze CSVs must stay in lockstep
with the visual map**, and **sprite/tileset licensing must be clean**.

## Open questions / next steps

- **Scale & theme:** a few buildings vs. a town? what setting/cast?
- **Art pipeline:** which license-clean packs (CC BY / OFL / CC0), or commission/draw our
  own? Where do source files (`.aseprite`, `.tmx`) live?
- **Licensing policy:** keep an attribution file per asset pack from day one.
- **Cast size:** how many personas, and do we author full `scratch.json`/`spatial_memory`
  or start minimal?
- **Sequencing:** author for the current Phaser replay now (A), or wait for the Godot port
  (B) and author once? Relates to the Godot frontend-port guidance in PR #146.

## References

- Upstream asset source: https://github.com/joonspk-research/generative_agents
- 2025 Godot reference + asset/licensing survey: [`godot-multi-agent-playground.md`](godot-multi-agent-playground.md)
- Port survey (world, cast, cognitive loop): [`generative-agents-port.md`](generative-agents-port.md)
- Backend world model: [`backend/world_map.py`](../../generative-agents/backend/world_map.py),
  [`backend/build_world.py`](../../generative-agents/backend/build_world.py),
  [`backend/seed.py`](../../generative-agents/backend/seed.py),
  [`backend/world_data.yaml`](../../generative-agents/backend/world_data.yaml)
- Asset pipeline: [`generative-agents/setup.sh`](../../generative-agents/setup.sh),
  [`generative-agents/README.md`](../../generative-agents/README.md)
- Related: issue #108 (Tingen custom game on the engine), and the Godot frontend-port
  guidance at the bottom of [`NEXT-STEPS.md`](../../generative-agents/NEXT-STEPS.md) (PR #146).
