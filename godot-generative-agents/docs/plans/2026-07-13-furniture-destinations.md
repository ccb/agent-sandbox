# Furniture-Aware Destinations (#537) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the sim first-class furniture data (`furniture_maze.csv` + `furniture_blocks.csv`), derive per-arena seat spots at load time, and make building routing prefer them — with a Tiled-openable debug overlay for visual verification.

**Architecture:** A new geo script joins the tmj's `*_furniture` layers with `furniture_catalog.json` (GIDs → names) and emits the maze/blocks pair in the existing matrix conventions (plus, with `--debug-overlay`, a git-ignored overlay tmj). `WorldMap.__init__` optionally loads `furniture_maze.csv` and derives `furniture_spots[address]` (walkable cells on or 4-adjacent to furniture, row-major). `_pin_building_meeting_points` prefers the k-nearest spots to its approach-offset point, round-robin per address, falling back to today's centroid pick. Rendezvous pinning, collision, and the committed tmj are untouched.

**Tech Stack:** Python 3.12 stdlib (json, csv, argparse); the existing geo/pytest conventions.

**Spec:** `godot-generative-agents/docs/specs/2026-07-13-furniture-destinations.md` (committed 02b9eff)

## Global Constraints

- Branch: `feat/furniture-spots-537` off `godot-ga-main`; PR targets `godot-ga-main`.
- The committed tmj (`godot-generative-agents/godot/maps/upenn_core_urban.tmj`) is READ-ONLY — never write it (geo scripts minify; repo tracks Tiled-pretty). The overlay goes to `tools/geo/out/` (git-ignored).
- `collision_maze.csv`, `walkable_furniture.json`, `_pin_meeting_rendezvous`, and the viewer are untouched.
- Matrix formats match existing conventions exactly: maze CSV = one row, cells joined `", "`, no trailing newline; blocks CSV rows = `id, world, sector, arena, name` (spaces after commas).
- `test_stepper_matches_simulate_prefix` and the scripted-meeting tests must stay green (run the full godot suite each task).
- Run from the repo root; `uv run black .` before every commit; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`; never `git add -A`.

---

### Task 1: `gen_furniture_matrix.py` — pure core + writers + overlay

**Files:**
- Create: `godot-generative-agents/tools/geo/gen_furniture_matrix.py`
- Create: `godot-generative-agents/tools/geo/test_furniture_matrix.py`

**Interfaces:**
- Consumes: `block_furniture.py`'s conventions (`GID_MASK = 0x1FFFFFFF`, `_solid_layers` suffix rule, `read_flat`/`write_flat`), `furniture_catalog.json` (`{"sheets": {name: {cols, rows, ...}}, "objects": {key: {sheet, col, row, w, h, category, ...}}}`), tmj `tilesets[].firstgid`/`name`.
- Produces (Task 2 runs it; Task 3 reads its output): CLI writing `<matrix>/maze/furniture_maze.csv` (flat, per-cell piece id or `0`) and `<matrix>/special_blocks/furniture_blocks.csv` (`id, world, sector, arena, name`); `--debug-overlay` additionally writes `tools/geo/out/upenn_furniture_debug.tmj`. Pure functions: `pieces(tmj, excluded=frozenset()) -> list[dict]` (each `{"cells": [(x, y), ...], "anchor_gid": int, "gids": [int, ...]}`; cells whose base gid is in `excluded` are treated as empty), `gid_names(catalog, tilesets) -> dict[int, str]`, `excluded_gids(catalog, tilesets) -> set[int]` (every footprint gid of catalog entries whose category is in `EXCLUDED_CATEGORIES = {"wall", "window", "door"}` — the spec's verified need: `williams_furniture` carries 46 window tiles that must not become furniture), `spots(furn_flat, collision, width, height) -> list[tuple[int, int]]`.

- [ ] **Step 1: Write the failing tests**

Create `godot-generative-agents/tools/geo/test_furniture_matrix.py`:

```python
"""gen_furniture_matrix unit tests (#537): synthetic tmj fixtures, no files."""

from gen_furniture_matrix import gid_names, pieces, spots

# A 4x3 map, one furniture layer. Layout (gids):
#   0 5 6 0
#   0 7 8 0
#   0 0 0 9
# -> one 2x2 piece (gids 5,6,7,8, anchor 5) + one 1x1 piece (gid 9).
_TMJ = {
    "width": 4,
    "height": 3,
    "layers": [
        {
            "type": "tilelayer",
            "name": "demo_furniture",
            "data": [0, 5, 6, 0, 0, 7, 8, 0, 0, 0, 0, 9],
        },
        {"type": "tilelayer", "name": "demo_floor", "data": [1] * 12},
    ],
    "tilesets": [{"firstgid": 1, "name": "franuka"}],
}

_CATALOG = {
    "sheets": {"franuka": {"cols": 2, "rows": 4}},
    "objects": {
        "_comment": "ignored",
        "desk_big": {"sheet": "franuka", "col": 0, "row": 2, "w": 2, "h": 2},
        "stool": {"sheet": "franuka", "col": 0, "row": 4, "w": 1, "h": 1},
        "window_a": {
            "sheet": "franuka", "col": 1, "row": 4, "w": 1, "h": 1,
            "category": "window",
        },
    },
}


def test_excluded_gids_covers_wall_window_door_footprints():
    from gen_furniture_matrix import excluded_gids

    # window_a at (col 1, row 4) on a 2-col sheet with firstgid 1 -> gid 10.
    assert excluded_gids(_CATALOG, _TMJ["tilesets"]) == {10}


def test_pieces_skips_excluded_cells():
    # A window gid (10) beside the stool must not merge into (or become) a
    # piece: williams_furniture paints windows on the furniture layer so
    # block_furniture seals them; they are NOT furniture (#537 spec §1).
    tmj = dict(_TMJ)
    tmj["layers"] = [
        {
            "type": "tilelayer",
            "name": "demo_furniture",
            "data": [0, 5, 6, 0, 0, 7, 8, 0, 10, 10, 0, 9],
        }
    ]
    got = pieces(tmj, excluded={10})
    assert len(got) == 2  # the desk and the stool; no window piece
    assert all((0, 2) not in p["cells"] and (1, 2) not in p["cells"] for p in got)


def test_pieces_groups_by_contiguity_not_gid():
    got = pieces(_TMJ)
    assert len(got) == 2
    big, small = sorted(got, key=lambda p: len(p["cells"]), reverse=True)
    assert sorted(big["cells"]) == [(1, 0), (1, 1), (2, 0), (2, 1)]
    assert big["anchor_gid"] == 5  # top-left cell's base gid
    assert small["cells"] == [(3, 2)] and small["anchor_gid"] == 9


def test_gid_names_expands_footprints_and_resolves_anchor():
    # desk_big anchors at (col 0, row 2) on a 2-col sheet with firstgid 1:
    # gid = 1 + row*cols + col -> anchor 5, footprint covers gids 5,6,7,8.
    names = gid_names(_CATALOG, _TMJ["tilesets"])
    assert names[5] == "desk_big" and names[8] == "desk_big"
    assert names[9] == "stool"


def test_spots_are_walkable_cells_on_or_beside_furniture():
    # Collision: the 2x2 desk is solid; the stool (gid 9) is a walkable seat.
    furn = ["0", "1", "1", "0", "0", "1", "1", "0", "0", "0", "0", "2"]
    coll = ["0", "1", "1", "0", "0", "1", "1", "0", "0", "0", "0", "0"]
    got = spots(furn, coll, 4, 3)
    # Row-major: (0,0)/(3,0) flank the desk, (0,1)/(3,1) flank it, (1,2)/(2,2)
    # sit below it, and (3,2) IS the walkable stool.
    assert got == [(0, 0), (3, 0), (0, 1), (3, 1), (1, 2), (2, 2), (3, 2)]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furniture_matrix.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'gen_furniture_matrix'` (the geo tests run with the geo dir on sys.path — match how the neighboring geo tests import their modules; if they use a conftest/sys.path insert, mirror it).

- [ ] **Step 3: Implement**

Create `godot-generative-agents/tools/geo/gen_furniture_matrix.py`:

```python
#!/usr/bin/env python3
"""Export furniture as first-class matrix data (#537).

The tmj's `*_furniture` layers know where furniture is; furniture_catalog.json
knows what the tiles are. The sim sees neither: block_furniture.py seals
furniture into collision_maze.csv, byte-identical to walls. This script joins
the two and emits, in the existing matrix conventions:

    <matrix>/maze/furniture_maze.csv            per-cell piece id, 0 elsewhere
    <matrix>/special_blocks/furniture_blocks.csv  id, world, sector, arena, name

so WorldMap can derive furniture-aware destinations (seat spots), and #446's
future sit/use verbs have identities to name. `--debug-overlay` also writes a
git-ignored Tiled overlay (labeled rectangle per piece + a point per derived
seat spot) for eyeballing placements:

    uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py
    uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py --debug-overlay

Reads the committed tmj (never writes it). Idempotent: output depends only on
the tmj + catalog + arena/collision matrices.
"""

from __future__ import annotations

import argparse
import json
import os

from block_furniture import GID_MASK, _solid_layers, read_flat

CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "furniture_catalog.json"
)


EXCLUDED_CATEGORIES = {"wall", "window", "door"}


def excluded_gids(catalog: dict, tilesets: list[dict]) -> set[int]:
    """Every footprint gid of catalog entries whose category is structural
    (wall/window/door). Painted on `*_furniture` layers only so
    block_furniture seals them (williams_furniture carries 46 window tiles);
    they are NOT furniture and must not grow seat spots along the walls."""
    firstgid = {ts.get("name"): ts["firstgid"] for ts in tilesets}
    out: set[int] = set()
    for key, obj in catalog.get("objects", {}).items():
        if key.startswith("_") or not isinstance(obj, dict):
            continue
        if obj.get("category") not in EXCLUDED_CATEGORIES:
            continue
        sheet = catalog["sheets"].get(obj.get("sheet"), {})
        base = firstgid.get(obj.get("sheet"))
        cols = sheet.get("cols")
        if base is None or cols is None:
            continue
        for dy in range(int(obj.get("h", 1))):
            for dx in range(int(obj.get("w", 1))):
                out.add(base + (obj["row"] + dy) * cols + (obj["col"] + dx))
    return out


def pieces(tmj: dict, excluded: frozenset | set = frozenset()) -> list[dict]:
    """Contiguous furniture pieces across all `*_furniture` layers.

    4-connected nonzero cells within one layer form a piece (multi-tile
    furniture is placed as a block of DIFFERENT atlas gids, so grouping by
    gid would shatter one desk into six instances). Cells whose base gid is
    in `excluded` (structural wall/window/door tiles) are treated as empty.
    Returns row-major-ordered pieces of {"cells": [(x, y)...], "anchor_gid":
    top-left cell's base gid, "gids": base gids row-major}.
    """
    width = tmj["width"]
    out: list[dict] = []
    for layer in _solid_layers(tmj):
        data = [0 if (g and (g & GID_MASK) in excluded) else g for g in layer["data"]]
        seen: set[int] = set()
        for start, g in enumerate(data):
            if not g or start in seen:
                continue
            stack, cells = [start], []
            seen.add(start)
            while stack:
                idx = stack.pop()
                cells.append(idx)
                x, y = idx % width, idx // width
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    n = ny * width + nx
                    if (
                        0 <= nx < width
                        and 0 <= ny < tmj["height"]
                        and n not in seen
                        and data[n]
                    ):
                        seen.add(n)
                        stack.append(n)
            cells.sort()  # row-major: the first cell is the top-left anchor
            out.append(
                {
                    "cells": [(i % width, i // width) for i in cells],
                    "anchor_gid": data[cells[0]] & GID_MASK,
                    "gids": [data[i] & GID_MASK for i in cells],
                }
            )
    return out


def gid_names(catalog: dict, tilesets: list[dict]) -> dict[int, str]:
    """gid -> catalog object key, every footprint cell covered.

    An object at (col, row) with footprint w x h on a sheet occupies the
    w*h gids of that atlas block; all of them map to the object's key so a
    piece can be named from any of its cells.
    """
    firstgid = {ts.get("name"): ts["firstgid"] for ts in tilesets}
    names: dict[int, str] = {}
    for key, obj in catalog.get("objects", {}).items():
        if key.startswith("_") or not isinstance(obj, dict):
            continue
        sheet = catalog["sheets"].get(obj.get("sheet"), {})
        base = firstgid.get(obj.get("sheet"))
        cols = sheet.get("cols")
        if base is None or cols is None:
            continue
        for dy in range(int(obj.get("h", 1))):
            for dx in range(int(obj.get("w", 1))):
                gid = base + (obj["row"] + dy) * cols + (obj["col"] + dx)
                names[gid] = key
    return names


def piece_name(piece: dict, names: dict[int, str]) -> str:
    """The anchor cell's catalog name; else any covered cell's; else tile-<gid>
    (emitted, not dropped -- the overlay makes catalog gaps visible)."""
    if piece["anchor_gid"] in names:
        return names[piece["anchor_gid"]]
    for gid in piece["gids"]:
        if gid in names:
            return names[gid]
    return f"tile-{piece['anchor_gid']}"


def spots(
    furn: list[str], collision: list[str], width: int, height: int
) -> list[tuple[int, int]]:
    """Walkable cells ON furniture (walkable seats) or 4-adjacent to it,
    row-major. The same rule WorldMap derives at load; duplicated ~10 lines
    by design so tools/geo never imports backend."""
    out = []
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if collision[idx] != "0":
                continue
            if furn[idx] != "0":
                out.append((x, y))
                continue
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    if furn[ny * width + nx] != "0":
                        out.append((x, y))
                        break
    return out


def _majority_label(cells, maze, table, width):
    counts: dict[str, int] = {}
    for x, y in cells:
        label = table.get(maze[y * width + x])
        if label:
            counts[label] = counts.get(label, 0) + 1
    return max(counts, key=counts.get) if counts else ""


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tmj",
        default=os.path.join(
            repo, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"
        ),
    )
    ap.add_argument(
        "--matrix",
        default=os.path.join(
            repo, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
        ),
    )
    ap.add_argument("--catalog", default=CATALOG_PATH)
    ap.add_argument(
        "--debug-overlay",
        action="store_true",
        help="also write tools/geo/out/upenn_furniture_debug.tmj",
    )
    args = ap.parse_args()

    tmj = json.load(open(args.tmj))
    catalog = json.load(open(args.catalog))
    W, H = tmj["width"], tmj["height"]
    names = gid_names(catalog, tmj.get("tilesets", []))
    skip = excluded_gids(catalog, tmj.get("tilesets", []))

    def rows(path):  # id -> label table, world row is single
        return {
            r.split(",")[0].strip(): r.split(",")[-1].strip()
            for r in open(path).read().strip().splitlines()
            if r.strip()
        }

    blocks_dir = os.path.join(args.matrix, "special_blocks")
    world = open(os.path.join(blocks_dir, "world_blocks.csv")).read().strip()
    world = world.split(",")[-1].strip()
    sector_t = rows(os.path.join(blocks_dir, "sector_blocks.csv"))
    arena_t = rows(os.path.join(blocks_dir, "arena_blocks.csv"))
    maze_dir = os.path.join(args.matrix, "maze")
    sector_m = read_flat(os.path.join(maze_dir, "sector_maze.csv"))
    arena_m = read_flat(os.path.join(maze_dir, "arena_maze.csv"))
    collision = read_flat(os.path.join(maze_dir, "collision_maze.csv"))

    n_skipped = sum(
        1
        for L in _solid_layers(tmj)
        for g in L["data"]
        if g and (g & GID_MASK) in skip
    )
    if n_skipped:
        print(f"excluded {n_skipped} wall/window/door cells (not furniture)")
    all_pieces = pieces(tmj, excluded=skip)
    furn = ["0"] * (W * H)
    block_rows = []
    for pid, piece in enumerate(all_pieces, start=1):
        for x, y in piece["cells"]:
            furn[y * W + x] = str(pid)
        block_rows.append(
            f"{pid}, {world}, "
            f"{_majority_label(piece['cells'], sector_m, sector_t, W)}, "
            f"{_majority_label(piece['cells'], arena_m, arena_t, W)}, "
            f"{piece_name(piece, names)}"
        )

    with open(os.path.join(maze_dir, "furniture_maze.csv"), "w") as fh:
        fh.write(", ".join(furn))
    with open(os.path.join(blocks_dir, "furniture_blocks.csv"), "w") as fh:
        fh.write("\n".join(block_rows))
    print(f"{len(all_pieces)} pieces -> furniture_maze.csv + furniture_blocks.csv")

    if args.debug_overlay:
        tile = tmj.get("tilewidth", 16)
        objects = []
        for pid, piece in enumerate(all_pieces, start=1):
            xs = [x for x, _ in piece["cells"]]
            ys = [y for _, y in piece["cells"]]
            sector = _majority_label(piece["cells"], sector_m, sector_t, W)
            arena = _majority_label(piece["cells"], arena_m, arena_t, W)
            objects.append(
                {
                    "id": pid,
                    "name": f"{piece_name(piece, names)} — {sector}: {arena}",
                    "type": "furniture",
                    "x": min(xs) * tile,
                    "y": min(ys) * tile,
                    "width": (max(xs) - min(xs) + 1) * tile,
                    "height": (max(ys) - min(ys) + 1) * tile,
                    "visible": True,
                }
            )
        for i, (x, y) in enumerate(spots(furn, collision, W, H)):
            objects.append(
                {
                    "id": len(all_pieces) + 1 + i,
                    "name": "spot",
                    "type": "spot",
                    "point": True,
                    "x": (x + 0.5) * tile,
                    "y": (y + 0.5) * tile,
                    "visible": True,
                }
            )
        overlay = dict(tmj)
        overlay["layers"] = list(tmj["layers"]) + [
            {
                "type": "objectgroup",
                "name": "furniture_debug",
                "id": max(L.get("id", 0) for L in tmj["layers"]) + 1,
                "objects": objects,
                "visible": True,
                "opacity": 1,
                "x": 0,
                "y": 0,
            }
        ]
        out_dir = os.path.join(here, "out")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "upenn_furniture_debug.tmj")
        json.dump(overlay, open(out_path, "w"))
        print(f"wrote {os.path.relpath(out_path, repo)} (open in Tiled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furniture_matrix.py -v`
Expected: 3 pass. Then the whole geo suite: `uv run pytest godot-generative-agents/tools/geo -q` — no regressions.

- [ ] **Step 5: Format and commit**

```bash
uv run black godot-generative-agents/tools/geo/gen_furniture_matrix.py godot-generative-agents/tools/geo/test_furniture_matrix.py
git add godot-generative-agents/tools/geo/gen_furniture_matrix.py godot-generative-agents/tools/geo/test_furniture_matrix.py
git commit -m "feat(geo): gen_furniture_matrix — furniture identity join + seat spots + debug overlay (#537)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Generate + commit the real artifacts, pin real-map invariants

**Files:**
- Create (generated): `godot-generative-agents/backend/penn/the_upenn/matrix/maze/furniture_maze.csv`, `godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_blocks.csv`
- Test: `godot-generative-agents/tools/geo/test_furniture_matrix.py` (append a real-map test)
- Modify: `godot-generative-agents/tools/geo/README.md` (regen command, after the block_furniture step)

**Interfaces:**
- Consumes: Task 1's CLI.
- Produces: the committed artifacts Task 3 loads.

- [ ] **Step 1: Run the generator (twice — idempotence check)**

```bash
uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py
git status --short godot-generative-agents/backend/penn/the_upenn/matrix/
uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py
git status --short godot-generative-agents/backend/penn/the_upenn/matrix/
```
Expected: two new files after the first run; byte-identical (no further diff) after the second. Note the piece count printed.

- [ ] **Step 2: Append the real-map invariants test**

```python
def test_real_map_artifacts_are_consistent():
    # The committed artifacts stay in lock-step with the tmj + matrices:
    # every furniture cell sits on a *_furniture layer cell, ids are dense,
    # and every id has exactly one blocks row.
    import json
    import os

    from block_furniture import _solid_layers, read_flat

    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    matrix = os.path.join(
        repo, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
    )
    tmj = json.load(
        open(
            os.path.join(
                repo, "godot-generative-agents", "godot", "maps",
                "upenn_core_urban.tmj",
            )
        )
    )
    furn = read_flat(os.path.join(matrix, "maze", "furniture_maze.csv"))
    assert len(furn) == tmj["width"] * tmj["height"]
    on_layers = [False] * len(furn)
    for layer in _solid_layers(tmj):
        for i, g in enumerate(layer["data"]):
            if g:
                on_layers[i] = True
    ids = set()
    for i, cell in enumerate(furn):
        if cell != "0":
            assert on_layers[i], f"cell {i} claims furniture off any layer"
            ids.add(int(cell))
    assert ids, "real map produced no furniture pieces"
    blocks = open(
        os.path.join(matrix, "special_blocks", "furniture_blocks.csv")
    ).read().strip().splitlines()
    block_ids = {int(r.split(",")[0]) for r in blocks}
    assert block_ids == ids == set(range(1, len(ids) + 1))
```

- [ ] **Step 3: Run the tests + the drift gate**

Run: `uv run pytest godot-generative-agents/tools/geo -q` — all pass.
Run: `uv run python godot-generative-agents/tools/geo/validate_tmj.py` — exit 0 (this feature adds files; it changes neither the tmj nor any validated matrix).

- [ ] **Step 4: README note**

In `godot-generative-agents/tools/geo/README.md`, after the `block_furniture.py` regen step, add:

```markdown
uv run python godot-generative-agents/tools/geo/gen_furniture_matrix.py   # furniture_maze + furniture_blocks (#537)
# add --debug-overlay to also write tools/geo/out/upenn_furniture_debug.tmj —
# open it in Tiled and toggle the furniture_debug layer to eyeball placements.
```

(Match the README's surrounding format; if the regen steps are prose rather than a block, add the equivalent sentence.)

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/penn/the_upenn/matrix/maze/furniture_maze.csv godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/furniture_blocks.csv godot-generative-agents/tools/geo/test_furniture_matrix.py godot-generative-agents/tools/geo/README.md
git commit -m "feat(geo): commit the real-map furniture matrix artifacts (#537)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `WorldMap.furniture_spots` + routing preference

**Files:**
- Modify: `godot-generative-agents/backend/world_map.py` (`__init__`, after the bbox precompute ~line 97)
- Modify: `godot-generative-agents/backend/penn/penn_world.py` (`_pin_building_meeting_points`, lines 68-121)
- Test: `godot-generative-agents/tests/test_furniture_spots.py` (new)

**Interfaces:**
- Consumes: Task 2's committed artifacts; `_read_flat`; the address assembly already in `WorldMap.__init__` (`f"{world}:{s}:{a}"`).
- Produces: `WorldMap.furniture_spots: dict[str, list[tuple[int, int]]]` (arena-level address → row-major spot list; `{}` when `furniture_maze.csv` is absent, so non-Penn maps are unchanged). Routing: spot-preferring `walk_path` wrapper.

- [ ] **Step 1: Write the failing tests**

Create `godot-generative-agents/tests/test_furniture_spots.py`:

```python
"""Furniture-aware destinations (#537): spots derived at load, preferred by
the building routing, centroid fallback for bare arenas (Williams)."""

import sys
from pathlib import Path

_PENN = Path(__file__).resolve().parent.parent / "backend" / "penn"
sys.path.insert(0, str(_PENN.parent))
sys.path.insert(0, str(_PENN))

from penn_world import build_penn_world  # noqa: E402

HOUSTON = "UPenn:Houston Hall:lobby"
WILLIAMS = "UPenn:Williams Hall:lobby"


def _world_map():
    return build_penn_world().world_map


def test_spots_are_walkable_and_furnished_arenas_have_them():
    wm = _world_map()
    assert wm.furniture_spots.get(HOUSTON), "Houston lobby derived no spots"
    for address, tiles in wm.furniture_spots.items():
        for t in tiles:
            assert not wm.is_blocked(t), f"blocked spot {t} in {address}"
            assert t in wm.tiles_for(address), f"spot {t} outside {address}"


def test_bare_shells_have_no_spots():
    # Williams Hall is unfurnished in the matrices (#538 will change that);
    # its routing must keep today's centroid behavior.
    assert not _world_map().furniture_spots.get(WILLIAMS)


def test_routing_prefers_a_spot_in_furnished_buildings():
    wm = _world_map()
    path = wm.walk_path((100, 300), HOUSTON)  # approach from campus south
    assert path, "no path into Houston Hall"
    assert path[-1] in wm.furniture_spots[HOUSTON]


def test_routing_falls_back_to_centroid_for_bare_shells():
    wm = _world_map()
    path = wm.walk_path((100, 300), WILLIAMS)
    assert path, "no path into Williams Hall"
    assert path[-1] in wm.tiles_for(WILLIAMS)


def test_co_arrivals_spread_across_spots():
    wm = _world_map()
    a = wm.walk_path((100, 300), HOUSTON)[-1]
    b = wm.walk_path((100, 300), HOUSTON)[-1]
    assert a != b, "round-robin should hand co-arrivals different spots"
```

(If `(100, 300)` is off-map or walled for this grid, pick any outdoor walkable tile south of both buildings — assert `not wm.is_blocked(start)` first and adjust; state the chosen tile in the test.)

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_furniture_spots.py -q`
Expected: `AttributeError: 'WorldMap' object has no attribute 'furniture_spots'`.

- [ ] **Step 3: Implement — WorldMap derivation**

In `godot-generative-agents/backend/world_map.py`, `__init__`, directly after the `address_bbox` loop (~line 97), insert:

```python
        # Furniture-aware seat spots (#537): walkable tiles ON furniture (the
        # walkable seats of walkable_furniture.json) or 4-adjacent to it,
        # grouped by arena address, row-major. furniture_maze.csv is optional
        # -- maps without it (every non-Penn world) get {} and behave exactly
        # as before.
        self.furniture_spots: dict[str, list[tuple[int, int]]] = {}
        furn_path = os.path.join(maze, "furniture_maze.csv")
        if os.path.exists(furn_path):
            furn = _read_flat(furn_path)
            if len(furn) != expected:
                raise ValueError(
                    f"furniture_maze has {len(furn)} cells, expected {expected}"
                )

            def _at_furniture(x: int, y: int) -> bool:
                if furn[y * self.width + x] != "0":
                    return True
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        if furn[ny * self.width + nx] != "0":
                            return True
                return False

            for y in range(self.height):
                for x in range(self.width):
                    idx = y * self.width + x
                    if collision[idx] != "0" or not _at_furniture(x, y):
                        continue
                    s = sector.get(sector_m[idx])
                    a = arena.get(arena_m[idx])
                    if s and a:
                        self.furniture_spots.setdefault(
                            f"{world}:{s}:{a}", []
                        ).append((x, y))
```

- [ ] **Step 4: Implement — routing preference**

In `godot-generative-agents/backend/penn/penn_world.py`, inside `_pin_building_meeting_points`, add a per-address cursor beside `centres` and a spot-preference block at the top of the wrapped `walk_path` (the centroid logic below it is UNCHANGED):

```python
    orig_walk_path = world_map.walk_path
    centres: dict = {}
    spot_cursor: dict = {}
```

and in `walk_path(from_tile, address)`, before the existing `info = centre_of(address)` logic:

```python
        # Furniture first (#537): when the arena has seat spots, walk to one
        # of the k nearest to the approach-offset point -- consumed
        # round-robin per address so co-arrivals spread across furniture
        # instead of stacking -- and only fall through to the centroid pick
        # (below) when every candidate is unreachable. Bare arenas
        # (Williams, grounds) have no spots and keep today's behavior.
        spots = getattr(world_map, "furniture_spots", {}).get(address)
        info = centre_of(address)
        if spots and info:
            cx, cy, _tiles = info
            dx, dy = from_tile[0] - cx, from_tile[1] - cy
            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
            tx, ty = cx + dx / dist * offset, cy + dy / dist * offset
            near = sorted(spots, key=lambda t: (t[0] - tx) ** 2 + (t[1] - ty) ** 2)
            near = near[:4]
            n = spot_cursor.get(address, 0)
            spot_cursor[address] = n + 1
            for j in range(len(near)):
                target = near[(n + j) % len(near)]
                if tuple(from_tile) == target:
                    return []
                path = path_finder.path_finder(
                    world_map.collision, tuple(from_tile), target, 1
                )
                if path and len(path) > 1:
                    return [tuple(t) for t in path[1:]]
```

(The existing body already computes `info = centre_of(address)` — reuse the single computation; do not call it twice. The rest of the function is byte-identical.)

- [ ] **Step 5: Run the new tests, then the full godot suite**

Run: `uv run pytest godot-generative-agents/tests/test_furniture_spots.py -v` — 5 pass.
Run: `uv run pytest godot-generative-agents/tests/ -q` — all pass, especially `test_stepper_matches_simulate_prefix` and the meeting/injector tests (rendezvous pinning owns meeting venues and is untouched).
Run: `uv run black --check .` — clean.

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/backend/world_map.py godot-generative-agents/backend/penn/penn_world.py godot-generative-agents/tests/test_furniture_spots.py
git commit -m "feat(backend): furniture seat spots — WorldMap derivation + routing preference (#537)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
