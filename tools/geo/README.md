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
the three interior sheets wired into the map (`franuka`, `school`, `bath`), each
entry carrying `(sheet, col, row)`, a footprint `w×h`, a `category`
(floor/wall/window/door/furniture) and a `room` tag.

- The script loads the catalog and exposes `block_named("single_bed")` /
  `tile_named("wall_brick")`, so **an LLM furnishing a room references objects by
  name** instead of raw atlas coordinates.
- Verify a coordinate before trusting it:
  `uv run --with pillow python tools/geo/preview_catalog.py` renders a labeled
  contact sheet to `out/furniture_catalog_preview.png`; entries with
  `"verified": false` get a `?` badge (the verified ones come from the original
  working palette). Pillow is dev-only — neither the game nor the furnish step
  imports it.

## Notes / limitations

- Map data © OpenStreetMap contributors, **ODbL** — attribution required if
  reused. Google Maps is *not* a viable bulk source (its ToS forbids extracting
  map data); OSM/Overpass is the open path. See #164 for the licensing rationale.
- This is a stylized POC: solid-colour placeholder tiles, no building-name
  labels, no mapping yet onto the backend's collision/sector/arena CSVs
  (`gen_agents/world_map.py`) — those are the natural next steps.
