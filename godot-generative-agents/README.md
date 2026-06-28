# godot-generative-agents

A tiny [Godot 4.6](https://godotengine.org) sandbox that renders the **real
University of Pennsylvania campus** in Godot and plays back a generative-agents
simulation walking across it. It's a *viewer*: the simulation runs offline in Python
(the rest of this repo) and Godot draws the world + the agents moving through it.

## What's in the scene

Two scenes render the same campus — the academic core block (34th–36th ×
Spruce–Walnut), built from OpenStreetMap data by the repo's geo tool
(`tools/geo/osm_to_tiled.py`) and drawn with **Kenney's RPG Urban Pack (CC0)**:

- **`scenes/campus_urban.tscn`** — the campus on its own (the **default** scene):
  brick buildings, asphalt streets, tan paving for Locust Walk, green lawns. Pan and
  zoom to explore it.
- **`scenes/penn_replay.tscn`** — the same campus with a **generative-agents
  simulation** playing on top: a few Penn personas walking between real buildings on
  their daily schedules (see *Watching the Penn agent simulation* below).

Both share a generic map renderer (`scripts/tiled_map.gd`) and a pan/zoom camera
(`scripts/camera_controls.gd`).

## How it works

**`tiled_map.gd`** (the `Map` node in both scenes). A *generic* renderer for any Tiled
map whose tileset is one packed image: it reads the `.tmj`, loads the referenced
sheet, registers every tile, and paints each layer by GID. We use it to show the
campus drawn with **real art** — `maps/upenn_core_urban.tmj`, baked with **Kenney's
RPG Urban Pack (CC0)** by the geo tool (`--theme urban`): brick buildings, asphalt
streets, tan paving for Locust Walk, green for the lawns. The geo tool rotates the map
so Penn's streets run **straight along the X/Y axes** (the real grid is ~8.6° off
north) instead of on a slant, and the renderer uses nearest filtering + tile padding
so there are **no seams** between tiles. This is the no-plugin equivalent of importing
that `.tmj` with the [YATI](https://github.com/Kiamo2/YATI) addon, and the same file
also loads natively in Phaser. (`maps/tilemap_packed.png` is the CC0 sheet it
references.)

`scripts/penn_replay.gd` drives the agent replay on top of that map — see *Watching
the Penn agent simulation* below.

### Regenerating / swapping the campus map

`maps/upenn_core_urban.tmj` is a **copy** of the geo tool's output. To refresh it, or
to render the full campus instead of the 34th–38th × Spruce–Walnut core subset:

```bash
uv run python tools/geo/osm_to_tiled.py --area core --theme urban   # Kenney CC0 map + sheet
cp tools/geo/out/upenn_core_urban.tmj  godot-generative-agents/maps/
cp tools/geo/out/tilemap_packed.png    godot-generative-agents/maps/
```

`scripts/snapshot.gd` / `scenes/snapshot.tscn` are a small dev utility: run that scene
(optionally with `-- <scene.tscn> <out.png>`) to save a screenshot of a map, used to
verify the render.

## Running it

Open the project folder in the Godot 4.6 editor and press **Play** (F5), or from a
terminal:

```bash
# The campus in real Kenney CC0 urban art (the default scene):
/Applications/Godot.app/Contents/MacOS/Godot --path .

# Watch the agent simulation replay on the campus:
/Applications/Godot.app/Contents/MacOS/Godot --path . res://scenes/penn_replay.tscn

# Headless smoke test — load every scene and check its map painted (exit 0 = OK):
./run_smoke_test.sh
```

`run_smoke_test.sh` loads each content scene headless and fails (non-zero exit) if a
scene can't load or its campus map painted zero cells — so a broken `.tmj` / tileset
regen is caught in CI or before you push, instead of silently rendering an empty
world. It needs no GPU (it reads the tilemap's cell data, not pixels). `uv run pytest
tests/test_godot_smoke.py` runs the same check and skips cleanly when Godot isn't
installed.

The first run regenerates the `.godot/` import cache (git-ignored); the committed
`*.import` / `*.uid` sidecars let Godot recognize the assets without re-importing
everything.

## Watching the Penn agent simulation

`scenes/penn_replay.tscn` plays a **generative-agents simulation on the real
campus**: a few Penn personas (a student, a professor, an architecture grad)
walking between real buildings on their daily schedules. Godot is just the
*viewer* — the simulation runs offline in Python and writes a replay file the
scene reads (the same split as the upstream Phaser replay):

```bash
# 1. Run the sim -> maps/penn_replay.json (from the repo root, so uv finds the env):
uv run python godot-generative-agents/sim/generate_penn_replay.py --steps 400

# 2. Watch it:
/Applications/Godot.app/Contents/MacOS/Godot --path . res://scenes/penn_replay.tscn
```

The Penn world lives in [`sim/`](sim/): `world_data_upenn.yaml` (the cast) and
`the_upenn/` (the OSM-derived navigation grid from `tools/geo/osm_to_ville.py`).
The agent *engine* (deciding, pathfinding) is reused from `generative-agents/backend`,
so this is the same simulation that runs there — just rendered here instead of in
Phaser. `scripts/penn_replay.gd` eases each persona tile-to-tile along the path the
sim chose, with a name + activity label above each sprite. (`sim/` carries a
`.gdignore` so Godot leaves the Python alone.)

## Where this fits — the full-port proposals

This is a **mock**: a standalone proof that the Godot-native tilemap + sprite path works.
Two design docs in the repo sketch the road from here to a fully-wired Godot frontend:

- [`../docs/design/custom-world-authoring.md`](../docs/design/custom-world-authoring.md) —
  authoring our own world + sprites (map layers, semantic maze CSVs, personas, licensing).
- [`../generative-agents/NEXT-STEPS.md`](../generative-agents/NEXT-STEPS.md) (bottom section,
  "porting the replay frontend to Godot") — turning the file-based replay export into a Godot
  4 renderer.

## Assets & license

- **Campus tiles** — Kenney's [RPG Urban Pack](https://kenney.nl) (CC0, public
  domain), baked into `maps/tilemap_packed.png` by the geo tool. Interior cutaway art
  is credited separately in `maps/INTERIOR_CREDITS.md`.
- **Agent sprites** — the **Cute Fantasy (Free)** pack by Kenmi, kept under
  `Cute_Fantasy_Free/` with its original `read_me.txt`. Per that license it is **free
  for non-commercial use and may be modified, but not redistributed or resold**. It
  lives here only for this private research repo.
