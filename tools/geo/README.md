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
uv run python tools/geo/osm_to_tiled.py --refresh       # re-download from Overpass
uv run python tools/geo/osm_to_tiled.py --mpt 2         # finer grid (2 m per tile)
```

No third-party dependencies — only the Python stdlib (`zlib` writes the PNGs).

## Areas

Defined in the `AREAS` dict at the top of the script. Each writes its own files
and caches its own Overpass response, so they never clobber each other.

| `--area` | Stem | Covers |
|----------|------|--------|
| `campus` *(default)* | `upenn` | the full UPenn campus (~1 km × 1.2 km) |
| `core` | `upenn_core` | **34th–38th St between Spruce & Walnut** (~400 m × 650 m) — College Green, College Hall, Van Pelt, the Locust Walk core. A small frame for prototyping. |

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
   for a ~1 km frame) → fractional tile coordinates, north at row 0.
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

## Notes / limitations

- Map data © OpenStreetMap contributors, **ODbL** — attribution required if
  reused. Google Maps is *not* a viable bulk source (its ToS forbids extracting
  map data); OSM/Overpass is the open path. See #164 for the licensing rationale.
- This is a stylized POC: solid-colour placeholder tiles, no building-name
  labels, no mapping yet onto the backend's collision/sector/arena CSVs
  (`generative-agents/backend/world_map.py`) — those are the natural next steps.
