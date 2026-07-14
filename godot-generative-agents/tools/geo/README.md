# `godot-generative-agents/tools/geo` — real-world map → Tiled tilemap

Proof-of-concept for [#164](https://github.com/ccb/agent-sandbox/issues/164):
import real-world map data (OpenStreetMap / GeoJSON) and turn it into a **Tiled**
tilemap (`.tmj`). Tiled is the one format both renderers we care about consume:

```
OSM/GeoJSON ─► project ─► rasterize ─► Tiled (.tmj) ─┬─► Phaser  (native tilemapTiledJSON loader)
                                                      └─► Godot 4 (YATI importer, github.com/Kiamo2/YATI)
```

The shipped example is the **University of Pennsylvania campus**
([OSM relation 2594845](https://www.openstreetmap.org/relation/2594845)).

> ## For LLMs / agents: use the tile catalog — do not guess tiles
>
> When furnishing, decorating, or parsing the tilemap, **resolve every tile
> through `godot-generative-agents/tools/geo/furniture_catalog.json`** — the single source of truth for
> "what tile is what" (name → sheet, `(col,row)`, `w×h`, category, label,
> `verified`). **Never invent raw atlas coordinates or gids**; reference tiles by
> their catalog **name** (`block_named("bookshelf")` / `tile_named("wall_brick")`
> in `furnish_building.py`).
>
> **Prefer the active preset.** `godot-generative-agents/tools/geo/tile_presets.json` holds the
> human-curated subsets a person chose for the LLM to use. Before picking tiles,
> load the menu with `uv run python godot-generative-agents/tools/geo/tile_presets.py --menu` (active
> preset) and **use only those tiles**; in code, `tile_presets.objects(name)`
> returns the catalog filtered to a preset. If no preset is active, fall back to
> the full catalog but still go through it by name.
>
> **Respect the budgets** in the catalog's `_llm_guidance` block: ≤ 12 tile
> options per category and ≤ 30 per prompt — pre-filter by sheet/category/room.
> Prefer `verified: true` tiles; treat `verified: false` as candidates to confirm
> (visually, via `catalog_web.py`) before relying on them.

## Run

```bash
uv run python godot-generative-agents/tools/geo/osm_to_tiled.py                 # full campus (default)
uv run python godot-generative-agents/tools/geo/osm_to_tiled.py --area core     # small prototyping subset
uv run python godot-generative-agents/tools/geo/osm_to_tiled.py --area all      # both
uv run python godot-generative-agents/tools/geo/osm_to_tiled.py --theme urban   # real Kenney CC0 art (not flat colours)
uv run python godot-generative-agents/tools/geo/osm_to_tiled.py --refresh       # re-download from Overpass
uv run python godot-generative-agents/tools/geo/osm_to_tiled.py --mpt 2         # finer grid (2 m per tile)
uv run python godot-generative-agents/tools/geo/osm_to_tiled.py --rotate none   # keep north up (skip grid alignment)
```

By default the map is **rotated so the street grid lines up with the X/Y axes**
(`--rotate auto`): planned cities sit on a grid that's a few degrees off true
north (Penn's is ~8.6°), and a slanted grid looks wrong in a top-down game. The
tool measures that offset from the road geometry and spins the whole map to
cancel it; `--rotate none` keeps north up, `--rotate <deg>` rotates by a fixed
amount. The applied angle is saved in the map's `rotation_deg` property.

No third-party dependencies — only the Python stdlib (`zlib` writes the PNGs).

## Agent world (Smallville matrix)

`osm_to_tiled.py` makes a *picture*; `osm_to_ville.py` makes the *world data* the
generative-agents backend can actually walk. It emits the same `the_ville` matrix
format that `backend/world_map.py` already loads — collision +
sector/arena CSVs + block tables — derived from the same OSM features:

```bash
uv run python godot-generative-agents/tools/geo/osm_to_ville.py            # core area -> the_upenn matrix
uv run python godot-generative-agents/tools/geo/osm_to_ville.py --area campus
```

- **collision** = building footprints + water → walls; streets/paths/lawns walkable.
- **sectors** = each *named* OSM building (College Hall, Van Pelt, …). The footprint
  is a wall, so its walkable "apron" (the doorstep ring) is tagged too, so the
  pathfinder can route to `UPenn:<building>:grounds`.
- **arenas** = one per building (`grounds`); objects/spawns are empty (OSM has no
  interiors).

Output lands in the tracked `generative-agents/frontend_overrides/static_dirs/assets/the_upenn/`
(setup.sh rsyncs it into `frontend/`). Then bake a replay for the Godot viewer to
render the real campus (or serve it live — see `godot-generative-agents/README.md`):

```bash
# from the repo root -- bakes godot/maps/penn_replay.json for "Play the bundled replay":
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --steps 400
```

## Themes (the tile art)

`--theme` picks what the six categories are drawn with. The `.tmj` structure is
identical either way (GIDs just point at a different tileset).

| `--theme` | Tileset | Looks like | License |
|-----------|---------|-----------|---------|
| `placeholder` *(default)* | a generated 6-colour strip (`tileset.png`) | flat colour blocks | n/a |
| `urban` | Kenney **RPG Urban Pack** packed sheet (`tilemap_packed.png`, referenced whole) | real streets, brick buildings, lawns | **CC0** |

`urban` writes `<stem>_urban.tmj` and copies the Kenney sheet next to it, so the
placeholder maps are left untouched. The six base tiles chosen from the sheet live
in `URBAN_TILES` at the top of the script (index = row × 27 + col). The pack is
committed under [`assets/kenney/`](assets/kenney/README.md) — CC0 is what makes it
safe to redistribute and bake from (unlike the non-commercial Cute Fantasy pack).

On top of those six flat fills, the `urban` theme adds **per-feature variety** so
the campus doesn't read as one uniform block (all deterministic — same OSM in,
same map out; the placeholder theme is unaffected):

- **Roofs** — each building footprint gets a brick tile from `ROOF_TILES` (red and
  orange brick, picked by the OSM way id), instead of every roof being the same red.
- **Roads** — *major* roads (`MAJOR_ROADS`) get a dashed centreline stamped down
  the middle (`DASH_H`/`DASH_V`); minor/service roads stay plain asphalt.
- **Trees** — a seventh `trees` layer drawn on top. Every tree is a **multi-tile
  stand of foliage**, never a single cell (a lone 16px tile just reads as a green
  square; at the fine 1 m grid even a 1×2 sapling is a speck). The Kenney sheet has
  one coherent multi-tile tree — a 3×3 grove — but its nine tiles *tile* (a top /
  interior / trunk-base row, a left / interior / right column), so `make_stand(w, h)`
  stamps a canopy of any size from them. The 3×3 grove is the standard street tree;
  bigger `TREE_STAND`/`TREE_WOOD` stands fill the open greens. They're placed
  deterministically from three sources: any OSM `natural=tree` nodes, a set-back
  lining of the footways (so Locust Walk becomes a tree-lined avenue), and a
  mixed-size scatter across the lawns — never overlapping a built, paved or watery
  cell, or another tree. The generic renderer paints them with no changes.

## Areas

Defined in the `AREAS` dict at the top of the script. Each writes its own files
and caches its own Overpass response, so they never clobber each other.

| `--area` | Stem | Covers |
|----------|------|--------|
| `campus` *(default)* | `upenn` | the full UPenn campus (~1 km × 1.2 km) |
| `core` | `upenn_core` | **34th–36th St between Spruce & Walnut** (~300 m × 400 m) — College Green, College Hall, Van Pelt, Meyerson, the Locust Walk core. The tight two-block heart of campus, for prototyping. |

Each area may pin its own resolution: `core` carries `"mpt": 1.0` (so it renders at a
fine **1 m/tile** — ~352×440 tiles — giving features, multi-tile tree stands
especially, room to read; and because the area is only two blocks, the whole frame
*is* the middle of campus, no camera zoom needed), while `campus` uses the 4 m/tile
default. An explicit `--mpt` overrides either. Whatever resolution you build the map
at, regenerate the matrix to match (`osm_to_ville.py` reads the same per-area `mpt`)
or the agent replay will be misaligned.

The `core` bbox was derived from the real street-centreline geometry in the campus
OSM data (the Philadelphia grid is rotated ~8°, so the axis-aligned box is the
tight rectangle that still contains all four bounding streets).

## Outputs (`godot-generative-agents/tools/geo/out/`)

| File | What it is |
|------|------------|
| `<stem>.tmj` | the Tiled map — orthogonal, 6 layers, **embedded** tileset, **uncompressed** layer data (so Phaser can read it) |
| `tileset.png` | the 6-tile palette image every `.tmj` references (shared) |
| `<stem>_preview.png` | a flattened render so you can eyeball the result without opening Tiled |
| `<stem>_osm.json` | cached raw Overpass response (git-ignored; delete or `--refresh` to refetch) |

## How it works

1. **Fetch** — one Overpass query pulls buildings, highways, footways, water,
   and landuse/leisure for the area's bounding box (see `AREAS` at the top of the
   script). `out geom;` gives each way's node coordinates inline.
2. **Project** — `Projector` maps lon/lat → metres (local equirectangular, fine
   for a ~1 km frame), optionally **rotates** the plane so the street grid is
   axis-aligned (see `--rotate` above), then → fractional tile coordinates.
3. **Rasterize** — closed areas (buildings, water, parks) are scanline-filled;
   ways (roads, footways, rivers) are drawn as Bresenham lines with a per-class
   width. Each category paints into one of six bottom-to-top layers: `ground`,
   `landuse`, `water`, `paths`, `roads`, `buildings`.
4. **Emit** — write the `.tmj` (+ geo-referencing in custom map properties so it
   round-trips), the tileset PNG, and the preview PNG.

## Tuning

- **`AREAS`** — add a new frame (any place on Earth) or tweak an existing bbox.
- **`METRES_PER_TILE`** (`--mpt`) — smaller = more detail and a bigger grid.
- **`PALETTE`** — the six categories and their colours; swap in a real art
  tileset later by keeping the same GIDs (1–6) and replacing `tileset.png`.

## Furnishing interiors (`furnish_building.py`)

`furnish_building.py` opens the roof of a building on the baked urban `.tmj` and
paints a furnished floor plan (see its module docstring for the run order). What
tile is what now lives in **`furniture_catalog.json`** — a labeled manifest of
the four sheets the catalog can address: the three interior sheets wired into the
map (`franuka`, `school`, `bath`) plus `kenney`, the base outdoor tileset (street
lamps, signs, trees) already present at firstgid 1. Each entry carries
`(sheet, col, row)`, a footprint `w×h`, a `category`
(floor/wall/window/door/furniture/prop/tree) and a `room`/context tag.

- The script loads the catalog and exposes `block_named("bed_single")` /
  `tile_named("wall_brick")`, so **an LLM furnishing a room references objects by
  name** instead of raw atlas coordinates. The `_llm_guidance` block in the JSON
  records how many options to show an LLM at once (≤ 12 per category, ≤ 30 per
  prompt) — past that, selection quality drops, so pre-filter by sheet/category.

Three ways to look at / verify the catalog (all dev-only; the game and the
furnish step never import them):

- **Interactive web grid (recommended):**
  `uv run python godot-generative-agents/tools/geo/catalog_web.py --serve` opens a browser editor — flip
  each tile verified/unverified, browse **every** tile on all four sheets, click a
  cell to add a new entry, and **Save** writes straight back to
  `furniture_catalog.json`. Drop `--serve` to instead emit a portable
  `out/catalog.html` whose Save downloads an updated JSON.
- **Static contact sheet:**
  `uv run --with pillow python godot-generative-agents/tools/geo/preview_catalog.py` renders
  `out/furniture_catalog_preview.png`; `"verified": false` entries get a `?` badge.
- **Coordinate finder:** `uv run --with pillow python godot-generative-agents/tools/geo/region_grid.py
  <sheet.png> 16 [--cols c0 c1] [--rows r0 r1] [--scale N]` renders an enlarged,
  (col,row)-labeled grid of any sheet/region — handy for reading off coordinates
  before adding catalog entries.

### Tile-usage presets (`tile_presets.py` + the web UI)

The full catalog is bigger than you'd hand an LLM at once. A **preset** is a named
subset — "these are the tiles to use when furnishing/parsing the tilemap" — with
optional per-tile placement hints, stored in `tile_presets.json` (`active` names
the default). This is the save/load seam between human curation and the LLM:

- **Create/edit visually:** in `catalog_web.py`, the *LLM preset* bar — pick or
  name a preset, star tiles into it (☆/★ on each card), add per-tile notes, tick
  *active for LLM*, and **Save preset** (writes `tile_presets.json` in `--serve`,
  downloads it otherwise). "Preview LLM menu" shows exactly what the LLM will get.
- **Consume it (the LLM side):**
  `uv run python godot-generative-agents/tools/geo/tile_presets.py --menu` prints the budget-aware tile
  menu (active preset, or `--menu NAME`) to paste into a furnishing prompt;
  `--list` shows presets, `--use NAME` sets the active one. In code,
  `tile_presets.objects(name)` returns the catalog filtered to the preset, so
  `block_named()`/`tile_named()` can be restricted to it.

## Doors & enterable interiors (`add_entrances.py`)

`add_entrances.py` makes campus buildings **enterable** — agents can walk inside,
but only through a door. Out of the box every footprint is a solid wall and agents
stop at the edge; this post-process hollows each in-frame building so the inside is
walkable floor and the 1-tile perimeter stays a wall, then opens a door wherever a
footway leads in. Because the backend pathfinder is a BFS over the collision grid,
a wall ring whose only gaps are doors means "enter/exit through a door" is enforced
by the map itself — **no movement-code changes**. Doors are found by marking every
perimeter cell that a `paths` tile sits *directly against* (`PATH_REACH` = 1, so a
walk merely passing a couple of tiles away doesn't punch a door onto blank ground)
and grouping those into contiguous runs: each run is one door, as wide as and
aligned with its walk (capped at `MAX_DOOR_WIDTH`). A building reached by several
walks therefore gets **several doors** (College Hall has many); one reached by none
falls back to a single door at the nearest path.

It edits both halves of the world in step:

- **Matrix** (`the_upenn/matrix`): carves `collision_maze` (interior → walkable,
  perimeter → wall, door → open) and tags the interior as a new arena, so the
  address `UPenn:<building>:lobby` resolves and a `world_data` location can send an
  agent inside (`:grounds` still means the outside edge). It also names the few
  footprints OSM left unnamed (by street address) and drops the stale "phantom"
  sector rows whose footprints fell outside the cropped frame.
- **Picture** (`upenn_core_urban.tmj`): opens the roof and paints a plain cutaway
  (floor + wall, with each door left as an open gap in the wall ring) using the same
  interior tiles as `furnish_building.py`. Williams Hall already has a *furnished*
  cutaway, so its picture is left alone and only its collision is carved (door lined
  up with its art).

Run it after the bake + Williams furnish (it's idempotent — recomputes every
footprint from an invariant mask, so re-runs are byte-stable):

```bash
uv run python godot-generative-agents/tools/geo/osm_to_tiled.py --area core --theme urban   # bake the map
uv run python godot-generative-agents/tools/geo/osm_to_ville.py --area core --out godot-generative-agents/backend/penn/the_upenn
uv run python godot-generative-agents/tools/geo/furnish_building.py                          # Williams interior
uv run python godot-generative-agents/tools/geo/add_entrances.py                             # doors + interiors
uv run python godot-generative-agents/tools/geo/block_grass.py                               # lawns become un-walkable
uv run python godot-generative-agents/tools/geo/block_furniture.py                           # seal furniture into collision
uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py                      # furniture_maze + furniture_blocks + furniture_spots (#537)
# add --debug-overlay to also write tools/geo/out/upenn_furniture_debug.tmj —
# open it in Tiled and toggle the furniture_debug layer to eyeball placements.
uv run python godot-generative-agents/backend/penn/generate_building_labels.py
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py
```

`--dry-run` reports each building's footprint/interior size and chosen door cell
without writing.

## Keeping agents off the lawns (`block_grass.py`)

`block_grass.py` walls off the grass so the pathfinder routes agents onto the
sidewalks instead of cutting straight across the lawns. The backend pathfinder is
a BFS over `collision_maze.csv` (a tile is walkable iff its cell is `"0"`), and
the bake only made building footprints + water walls — lawns stayed walkable. This
post-process flips every **visible** grass tile to a wall, so it's enforced by the
map itself with **no movement-code changes** (same trick `add_entrances.py` uses).

"Visible" grass is a `landuse` cell on the `.tmj` with no walkable surface painted
on top: a lawn tile that has a `paths`, `roads`, `entrance_floor`, or
`williams_floor` tile over it reads as pavement and stays walkable, and tiles that
are already walls (buildings, water) are left untouched. The grid lines up
tile-for-tile with the `.tmj`, so its layers index the same cells as the matrix.

```bash
uv run python godot-generative-agents/tools/geo/block_grass.py --dry-run   # report, change nothing
uv run python godot-generative-agents/tools/geo/block_grass.py             # wall the lawns
```

Idempotent: grass is detected from the (unchanged) `landuse` layer, not from the
collision it writes, so re-running is a no-op. Run it after `add_entrances.py` so
the carved interiors/doors are already in the collision it extends.

## Outlining a building's exterior (`wall_building.py`)

`wall_building.py` is the exterior counterpart to `furnish_building.py`: another
post-process for the baked urban `.tmj`. `osm_to_tiled.py` paints each building
footprint as one **flat brick field tile**, so a building has no defined edge — the
brick just stops at the street. Real campus buildings read as a massed block with a
cornice along the roofline and pilasters down the corners.

The script **autotiles the footprint perimeter** with the Kenney pack's brick wall
frame (4 corners + 4 edges, picked so the trim faces outward), leaving the interior
fill untouched:

```bash
# A single brick wall ring (the thin edge line comes free from the ground_edges layer):
uv run python godot-generative-agents/tools/geo/wall_building.py --sector "Van Pelt Library" --wall wall_brick_red --reset-fill
uv run python godot-generative-agents/tools/geo/wall_building.py --sector "Houston Hall"     --color grey --reset-fill   # grey stone
uv run python godot-generative-agents/tools/geo/wall_building.py --seed 202,144 --sector "Fisher Fine Arts" --wall wall_brick_red --reset-fill
```

- It reads the same footprint the furnisher does (sector ∩ collision in the sim
  matrix), so cells map 1:1 to the map grid.
- **Only the perimeter ring is written** — the interior fill is left untouched
  (it sits under the roof-off cutaway, so its colour doesn't matter). The map's
  existing `ground_edges` layer already draws a thin stone trim just *outside* the
  footprint, so a single brick ring reads as "brick wall + thin outer wall" with no
  second full tile.
- `--wall` chooses the wall art. The default `kenney` lays the Kenney urban brick
  **autotile frame**. Naming a `wall` object from `furniture_catalog.json` instead
  (e.g. `--wall wall_brick_red`) bands the perimeter with that single **Franuka**
  brick tile — a more detailed brick texture. The Franuka tileset is auto-registered
  on the `.tmj` if it isn't already.
- `--color` picks the Kenney autotile colour (used when `--wall kenney`): `red`/
  `orange` are brick; `grey` is the limestone-trimmed grey **stone** block, for
  non-brick collegiate-gothic buildings (Houston Hall); `auto` matches the fill.
- `--seed x,y` targets an **unnamed** building (one with no sim-matrix sector, e.g.
  the Furness Fisher Fine Arts library) by flood-filling the connected run of
  buildings-layer cells around that seed. Overrides `--sector`. The `buildings`
  layer draws *every* OSM footprint, but only *named* buildings get a sector.
- `--thin-edge` draws **only** a thin grey kerb (the `lawn_edges` stroke) on the
  apron ring just outside the footprint, hugging the building — a thin outer wall on
  the `edges` layer. It leaves the `buildings` layer untouched, so it's additive on
  top of an already-walled building.
- `--reset-fill` repaints the footprint with its base fill first — use it when
  re-running with a different layout so an earlier run's wall tiles don't linger.
- `--outer-frame` (optional) keeps a thicker look: a Kenney frame on the outermost
  ring with the `--wall` band just inside it.

### Walling every building at once

`wall_all_buildings.py` is a driver over `wall_building.py`'s primitives: it finds
*every* connected footprint on the `buildings` layer (named **and** unnamed) and
gives each a single brick ring, the colour picked from the roof tint (red roof →
terracotta, orange roof → brown). Footprints that already carry a deliberate wall
(any Franuka brick, or the grey stone frame) are left untouched, so hand-matched
colours survive. Re-run safe.

```bash
uv run python godot-generative-agents/tools/geo/wall_all_buildings.py --dry-run   # list what it'd do
uv run python godot-generative-agents/tools/geo/wall_all_buildings.py             # apply
```
- It's idempotent: the perimeter is re-derived and only perimeter cells are
  rewritten, so it's safe to re-run after a fresh `osm_to_tiled.py` bake.

### `validate_tmj.py` — tmj ↔ matrix validator

Detect-and-report checks that the authored `upenn_core_urban.tmj` and the
generative-agents matrix (`backend/penn/the_upenn/matrix`) agree, plus tmj
internal-integrity checks. Prints a grouped report; exits non-zero on any
**error** finding not listed in `validate_tmj_baseline.json` (the ledger of
currently-accepted drift, e.g. Cohen/Alumni rooms drawn in the tmj but not yet
wired into `add_entrances.ROOM_SUBDIVIDE`).

    uv run python godot-generative-agents/tools/geo/validate_tmj.py           # human report
    uv run python godot-generative-agents/tools/geo/validate_tmj.py --json    # findings as JSON

`test_validate_tmj.py` runs it as a CI gate: all integrity checks must pass and
no new error drift may appear beyond the baseline.

## Notes / limitations

- Map data © OpenStreetMap contributors, **ODbL** — attribution required if
  reused. Google Maps is *not* a viable bulk source (its ToS forbids extracting
  map data); OSM/Overpass is the open path. See #164 for the licensing rationale.
- This is a stylized POC: solid-colour placeholder tiles, no building-name
  labels, no mapping yet onto the backend's collision/sector/arena CSVs
  (`backend/world_map.py`) — those are the natural next steps.
