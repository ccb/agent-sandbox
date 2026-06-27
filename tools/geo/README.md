# `tools/geo` — real-world map → Tiled tilemap

Proof-of-concept for [#164](https://github.com/ccb/agent-sandbox/issues/164):
import real-world map data (OpenStreetMap / GeoJSON) and turn it into a **Tiled**
tilemap (`.tmj`). Tiled is the one format both renderers we care about consume:

```
OSM/GeoJSON ─► project ─► rasterize ─► Tiled (.tmj) ─┬─► Phaser  (native tilemapTiledJSON loader)
                                                      └─► Godot 4 (YATI importer, github.com/Kiamo2/YATI)
```

The shipped example is the **University of Pennsylvania campus**
([OSM relation 2594845](https://www.openstreetmap.org/relation/2594845)).

## Run

```bash
uv run python tools/geo/osm_to_tiled.py                 # full campus (default)
uv run python tools/geo/osm_to_tiled.py --area core     # small prototyping subset
uv run python tools/geo/osm_to_tiled.py --area all      # both
uv run python tools/geo/osm_to_tiled.py --theme urban   # real Kenney CC0 art (not flat colours)
uv run python tools/geo/osm_to_tiled.py --refresh       # re-download from Overpass
uv run python tools/geo/osm_to_tiled.py --mpt 2         # finer grid (2 m per tile)
uv run python tools/geo/osm_to_tiled.py --rotate none   # keep north up (skip grid alignment)
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
format that `gen_agents/world_map.py` already loads — collision +
sector/arena CSVs + block tables — derived from the same OSM features:

```bash
uv run python tools/geo/osm_to_ville.py            # core area -> the_upenn matrix
uv run python tools/geo/osm_to_ville.py --area campus
```

- **collision** = building footprints + water → walls; streets/paths/lawns walkable.
- **sectors** = each *named* OSM building (College Hall, Van Pelt, …). The footprint
  is a wall, so its walkable "apron" (the doorstep ring) is tagged too, so the
  pathfinder can route to `UPenn:<building>:grounds`.
- **arenas** = one per building (`grounds`); objects/spawns are empty (OSM has no
  interiors).

Output lands in the tracked `generative-agents/frontend_overrides/static_dirs/assets/the_upenn/`
(setup.sh rsyncs it into `frontend/`). Then run the existing sim on the real campus:

```bash
cd generative-agents && uv run python -m gen_agents.run_upenn   # 3 personas walk Penn
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

## Outputs (`tools/geo/out/`)

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
  `uv run python tools/geo/catalog_web.py --serve` opens a browser editor — flip
  each tile verified/unverified, browse **every** tile on all four sheets, click a
  cell to add a new entry, and **Save** writes straight back to
  `furniture_catalog.json`. Drop `--serve` to instead emit a portable
  `out/catalog.html` whose Save downloads an updated JSON.
- **Static contact sheet:**
  `uv run --with pillow python tools/geo/preview_catalog.py` renders
  `out/furniture_catalog_preview.png`; `"verified": false` entries get a `?` badge.
- **Coordinate finder:** `uv run --with pillow python tools/geo/region_grid.py
  <sheet.png> 16 [--cols c0 c1] [--rows r0 r1] [--scale N]` renders an enlarged,
  (col,row)-labeled grid of any sheet/region — handy for reading off coordinates
  before adding catalog entries.

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
uv run python tools/geo/wall_building.py --sector "Van Pelt Library" --wall wall_brick_red --reset-fill
uv run python tools/geo/wall_building.py --sector "Houston Hall"     --color grey --reset-fill   # grey stone
uv run python tools/geo/wall_building.py --seed 202,144 --sector "Fisher Fine Arts" --wall wall_brick_red --reset-fill
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
uv run python tools/geo/wall_all_buildings.py --dry-run   # list what it'd do
uv run python tools/geo/wall_all_buildings.py             # apply
```
- It's idempotent: the perimeter is re-derived and only perimeter cells are
  rewritten, so it's safe to re-run after a fresh `osm_to_tiled.py` bake.

## Notes / limitations

- Map data © OpenStreetMap contributors, **ODbL** — attribution required if
  reused. Google Maps is *not* a viable bulk source (its ToS forbids extracting
  map data); OSM/Overpass is the open path. See #164 for the licensing rationale.
- This is a stylized POC: solid-colour placeholder tiles, no building-name
  labels, no mapping yet onto the backend's collision/sector/arena CSVs
  (`gen_agents/world_map.py`) — those are the natural next steps.
