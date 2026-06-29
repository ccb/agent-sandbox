# Van Pelt Interior Transplant — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transplant the hand-designed 25-room Van Pelt Library interior from the abandoned branch onto `godot-ga-main`, wired into the door-gated system so every room is a navigable arena.

**Architecture:** A one-time extractor freezes the old branch's 6 interior tile layers + 25 room rectangles + partition-wall cells into `tools/geo/van_pelt_interior.json`. A new `furnish_van_pelt.py` grafts the detailed layers onto the picture (above `entrance_floor`). `add_entrances.py` — the authoritative matrix builder — gains an opt-in per-room subdivision (read from the same asset) that produces per-room arenas + partition collision instead of one lobby. `furnish_building.py` is untouched.

**Tech Stack:** Python 3.12 (stdlib only for the tools; Pillow only for optional rendering), `uv`, Tiled `.tmj` JSON maps, the `the_upenn/matrix` CSV sim grid.

## Global Constraints

- Map is `245 × 279 = 68355` cells; `maze_width`/`maze_height` are `245`/`279`. Matrix mazes are flat `", "`-joined, row-major by width 245.
- Tilesets are identical between the old branch and `godot-ga-main` (same `firstgid`s; `interior_franuka` at 519), so the old branch's tile GIDs are valid as-is.
- Write `.tmj` with `json.dump(tmj, fh, separators=(",", ":"))` (compact, matches the repo).
- Branch: `feat/furnish-van-pelt` (already created off `godot-ga-main`). Commit after every task.
- Run tools with `uv run python tools/geo/<tool>.py`. Run tests with `uv run --extra dev pytest tools/geo/<test>.py -v`.
- Filter shell noise by appending ` 2>/dev/null` is unnecessary; the zoxide banner on stderr is harmless.
- **Cardinal rule:** never place part of a multi-tile sprite. A clipped/cut sprite is always a bug.
- Van Pelt is sector `30`; its lobby arena is `1030`. Williams is sector `32` (lobby `1032`) and must stay unchanged.

---

## File Structure

- `tools/geo/extract_van_pelt_interior.py` — **create.** One-time generator: reads the 6 layers + `arenas` from commit `f5219ce` via `git show`, emits the asset. Documents provenance.
- `tools/geo/van_pelt_interior.json` — **create (committed asset).** The frozen design: layers, wall cells, 25 room rects.
- `tools/geo/test_van_pelt_asset.py` — **create.** Validates the asset.
- `tools/geo/furnish_van_pelt.py` — **create.** Picture transplant (6 layers above `entrance_floor`, clipped to the interior).
- `tools/geo/test_furnish_van_pelt.py` — **create.** Validates the transplant.
- `tools/geo/add_entrances.py` — **modify.** Add opt-in room subdivision.
- `tools/geo/test_van_pelt_arenas.py` — **create.** Validates the matrix subdivision + BFS connectivity.
- `godot-generative-agents/maps/upenn_core_urban.tmj` + `…/the_upenn/matrix/*` — **regenerate** in Task 4.

---

## Task 1: Freeze the interior asset

**Files:**
- Create: `tools/geo/extract_van_pelt_interior.py`
- Create: `tools/geo/van_pelt_interior.json`
- Test: `tools/geo/test_van_pelt_asset.py`

**Interfaces:**
- Produces: `tools/geo/van_pelt_interior.json` with keys `width:int`, `height:int`, `layer_order:list[str]` (6 names), `layers:{name: {cell_index_str: gid_int}}`, `wall_cells:list[int]`, `rooms:list[{name:str, rect:[c0,r0,c1,r1]}]` (inclusive tile rect).

- [ ] **Step 1: Write the failing test**

```python
# tools/geo/test_van_pelt_asset.py
import json, os

ASSET = os.path.join(os.path.dirname(__file__), "van_pelt_interior.json")

def _load():
    with open(ASSET) as fh:
        return json.load(fh)

def test_dimensions():
    a = _load()
    assert (a["width"], a["height"]) == (245, 279)

def test_layers_present_with_expected_counts():
    a = _load()
    counts = {n: len(cells) for n, cells in a["layers"].items()}
    assert counts == {
        "westwing_floors": 1685, "eastwing_floors": 2962,
        "westwing_walls": 257, "eastwing_walls": 251,
        "westwing_furniture": 457, "eastwing_furniture": 1080,
    }
    assert a["layer_order"] == [
        "westwing_floors", "eastwing_floors",
        "westwing_walls", "eastwing_walls",
        "westwing_furniture", "eastwing_furniture",
    ]

def test_25_unique_named_rooms():
    a = _load()
    names = [r["name"] for r in a["rooms"]]
    assert len(names) == 25 and len(set(names)) == 25
    for must in ("113", "114", "Kamin Gallery", "Moelis Family Grand Reading Room",
                 "Study Booths", "Entrance"):
        assert must in names

def test_wall_cells_is_union_of_wall_layers():
    a = _load()
    assert len(a["wall_cells"]) == 501
    # every wall cell index is < W*H
    assert all(0 <= i < 245 * 279 for i in a["wall_cells"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --extra dev pytest tools/geo/test_van_pelt_asset.py -v`
Expected: FAIL — `FileNotFoundError: van_pelt_interior.json`.

- [ ] **Step 3: Write the extractor**

```python
# tools/geo/extract_van_pelt_interior.py
#!/usr/bin/env python3
"""Freeze the hand-designed Van Pelt interior from commit f5219ce into
van_pelt_interior.json. One-time generator (provenance); the JSON is the
committed artifact the runtime tools read. Re-run only to re-extract."""
import json, math, os, subprocess

SRC = "f5219ce"
MAP = "godot-generative-agents/maps/upenn_core_urban.tmj"
LAYER_ORDER = [
    "westwing_floors", "eastwing_floors",
    "westwing_walls", "eastwing_walls",
    "westwing_furniture", "eastwing_furniture",
]
WALL_LAYERS = ["westwing_walls", "eastwing_walls"]


def git_show(ref, path):
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True, check=True,
    ).stdout


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    m = json.loads(git_show(SRC, MAP))
    W, H = m["width"], m["height"]
    by_name = {L["name"]: L for L in m["layers"] if L.get("type") == "tilelayer"}

    asset = {
        "source_commit": SRC, "width": W, "height": H,
        "layer_order": LAYER_ORDER, "layers": {}, "wall_cells": [], "rooms": [],
    }
    for name in LAYER_ORDER:
        data = by_name[name]["data"]
        asset["layers"][name] = {str(i): v for i, v in enumerate(data) if v}

    wall = set()
    for name in WALL_LAYERS:
        for i, v in enumerate(by_name[name]["data"]):
            if v:
                wall.add(i)
    asset["wall_cells"] = sorted(wall)

    arenas = next(L for L in m["layers"] if L["name"] == "arenas")
    rooms = []
    for o in arenas["objects"]:
        if o.get("name") and o["width"] > 0 and o["height"] > 0:
            c0, r0 = int(o["x"] // 16), int(o["y"] // 16)
            c1 = math.ceil((o["x"] + o["width"]) / 16) - 1
            r1 = math.ceil((o["y"] + o["height"]) / 16) - 1
            rooms.append({"name": o["name"], "rect": [c0, r0, c1, r1]})
    asset["rooms"] = sorted(rooms, key=lambda r: r["name"])

    out = os.path.join(here, "van_pelt_interior.json")
    with open(out, "w") as fh:
        json.dump(asset, fh, indent=1)
    print(f"wrote {out}: {len(asset['layers'])} layers, "
          f"{len(asset['rooms'])} rooms, {len(asset['wall_cells'])} wall cells")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Generate the asset**

Run: `uv run python tools/geo/extract_van_pelt_interior.py`
Expected: `wrote …/van_pelt_interior.json: 6 layers, 25 rooms, 501 wall cells`

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run --extra dev pytest tools/geo/test_van_pelt_asset.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add tools/geo/extract_van_pelt_interior.py tools/geo/van_pelt_interior.json tools/geo/test_van_pelt_asset.py
git commit -m "feat(geo): freeze hand-designed Van Pelt interior as an asset"
```

---

## Task 2: Picture transplant — `furnish_van_pelt.py`

**Files:**
- Create: `tools/geo/furnish_van_pelt.py`
- Test: `tools/geo/test_furnish_van_pelt.py`

**Interfaces:**
- Consumes: `van_pelt_interior.json` (Task 1); `add_entrances.read_flat`, `add_entrances.split_footprint`.
- Produces: `load_asset(here)->dict`, `van_pelt_interior_cells(matrix_dir, W, H, entrance_cells)->set[(x,y)]`, `apply(tmj, asset, matrix_dir)->int` (count of clipped cells). Inserts the 6 layers (names from `layer_order`) immediately after `entrance_floor`.

- [ ] **Step 1: Write the failing test**

```python
# tools/geo/test_furnish_van_pelt.py
import copy, json, os
import furnish_van_pelt as fv

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAP = os.path.join(REPO, "godot-generative-agents", "maps", "upenn_core_urban.tmj")
MATRIX = os.path.join(REPO, "godot-generative-agents", "sim", "the_upenn", "matrix")
ORDER = ["westwing_floors", "eastwing_floors", "westwing_walls",
         "eastwing_walls", "westwing_furniture", "eastwing_furniture"]

def _fresh_tmj():
    with open(MAP) as fh:
        return json.load(fh)

def test_inserts_six_layers_after_entrance_floor():
    tmj = _fresh_tmj()
    fv.apply(tmj, fv.load_asset(HERE), MATRIX)
    names = [L.get("name") for L in tmj["layers"]]
    for n in ORDER:
        assert n in names
    ef = names.index("entrance_floor")
    # the six interior layers are a contiguous block right after entrance_floor
    assert names[ef + 1: ef + 7] == ORDER

def test_no_transplanted_cell_outside_interior():
    tmj = _fresh_tmj()
    W, H = tmj["width"], tmj["height"]
    ef = next(L for L in tmj["layers"] if L.get("name") == "entrance_floor")
    entrance_cells = {(i % W, i // W) for i, v in enumerate(ef["data"]) if v}
    interior = fv.van_pelt_interior_cells(MATRIX, W, H, entrance_cells)
    fv.apply(tmj, fv.load_asset(HERE), MATRIX)
    for n in ORDER:
        L = next(x for x in tmj["layers"] if x.get("name") == n)
        for i, v in enumerate(L["data"]):
            if v:
                assert (i % W, i // W) in interior, f"{n} cell {(i%W,i//W)} outside interior"

def test_clips_the_throat_seam_cells():
    tmj = _fresh_tmj()
    clipped = fv.apply(tmj, fv.load_asset(HERE), MATRIX)
    assert 1 <= clipped <= 50  # ~20 (10 throat cells x 2 layers); never zero, never large

def test_furniture_never_clipped_cardinal_rule():
    # The clip only ever touches floor/wall cells at the throat seam. If ANY
    # furniture cell were outside the interior it would be clipped -> a cut sprite.
    tmj = _fresh_tmj()
    W, H = tmj["width"], tmj["height"]
    ef = next(L for L in tmj["layers"] if L.get("name") == "entrance_floor")
    entrance_cells = {(i % W, i // W) for i, v in enumerate(ef["data"]) if v}
    interior = fv.van_pelt_interior_cells(MATRIX, W, H, entrance_cells)
    asset = fv.load_asset(HERE)
    for fname in ("westwing_furniture", "eastwing_furniture"):
        for idx_s in asset["layers"][fname]:
            idx = int(idx_s)
            assert (idx % W, idx // W) in interior, f"{fname} {idx} would be clipped"

def test_idempotent():
    a = _fresh_tmj(); fv.apply(a, fv.load_asset(HERE), MATRIX)
    b = copy.deepcopy(a); fv.apply(b, fv.load_asset(HERE), MATRIX)
    da = {L["name"]: L["data"] for L in a["layers"] if L["name"] in ORDER}
    db = {L["name"]: L["data"] for L in b["layers"] if L["name"] in ORDER}
    assert da == db
    # re-applying did not add duplicate layers
    assert [L["name"] for L in a["layers"]] == [L["name"] for L in b["layers"]]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --extra dev pytest tools/geo/test_furnish_van_pelt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'furnish_van_pelt'`.

- [ ] **Step 3: Write the tool**

```python
# tools/geo/furnish_van_pelt.py
#!/usr/bin/env python3
"""Transplant the hand-designed Van Pelt interior (van_pelt_interior.json) onto
the campus map as its own tile layers, stacked above entrance_floor. PICTURE
ONLY -- the matrix (arenas / collision) is owned by add_entrances.py.

    uv run python tools/geo/furnish_van_pelt.py

Idempotent: strips its own layers before re-inserting; backs up the .tmj first.
Cells that fall outside Van Pelt's walkable interior (the throat-seam slivers)
are clipped, so no sprite is placed on a wall or outside the building."""
import argparse, json, os, shutil

from add_entrances import read_flat, split_footprint

ASSET = "van_pelt_interior.json"
SECTOR = "30"  # Van Pelt Library


def load_asset(here):
    with open(os.path.join(here, ASSET)) as fh:
        return json.load(fh)


def van_pelt_interior_cells(matrix_dir, W, H, entrance_cells):
    """Van Pelt's walkable interior as a set of (x, y), order-independent of
    add_entrances: the sector-30 footprint (sector cells that are part of the
    painted building, i.e. in entrance_floor) minus its 1-tile perimeter ring."""
    sector = read_flat(os.path.join(matrix_dir, "maze", "sector_maze.csv"))
    foot = {(i % W, i // W) for i, s in enumerate(sector) if s == SECTOR} & entrance_cells
    _perimeter, interior = split_footprint(foot, W, H)
    return interior


def _strip(tmj, names):
    tmj["layers"] = [L for L in tmj["layers"] if L.get("name") not in names]


def apply(tmj, asset, matrix_dir):
    """Insert the 6 interior layers above entrance_floor, clipped to the
    interior. Returns the number of clipped (out-of-interior) cell entries."""
    W, H = tmj["width"], tmj["height"]
    order = asset["layer_order"]
    _strip(tmj, set(order))

    ef = next((L for L in tmj["layers"]
               if L.get("name") == "entrance_floor" and L.get("type") == "tilelayer"), None)
    entrance_cells = ({(i % W, i // W) for i, v in enumerate(ef["data"]) if v}
                      if ef else set())
    interior = van_pelt_interior_cells(matrix_dir, W, H, entrance_cells)

    next_id = max([L.get("id", 0) for L in tmj["layers"]] + [0]) + 1
    clipped = 0
    new_layers = []
    for k, name in enumerate(order):
        data = [0] * (W * H)
        for idx_s, g in asset["layers"][name].items():
            idx = int(idx_s)
            if (idx % W, idx // W) in interior:
                data[idx] = g
            else:
                clipped += 1
        new_layers.append({
            "type": "tilelayer", "name": name, "id": next_id + k,
            "x": 0, "y": 0, "width": W, "height": H,
            "opacity": 1, "visible": True, "data": data,
        })
    if "nextlayerid" in tmj:
        tmj["nextlayerid"] = max(tmj["nextlayerid"], next_id + len(order))

    names = [L.get("name") for L in tmj["layers"]]
    at = names.index("entrance_floor") + 1 if "entrance_floor" in names else len(tmj["layers"])
    tmj["layers"][at:at] = new_layers
    return clipped


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tmj", default=os.path.join(
        repo, "godot-generative-agents", "maps", "upenn_core_urban.tmj"))
    ap.add_argument("--matrix", default=os.path.join(
        repo, "godot-generative-agents", "sim", "the_upenn", "matrix"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    asset = load_asset(here)
    tmj = json.load(open(args.tmj))
    clipped = apply(tmj, asset, args.matrix)
    print(f"transplanted {len(asset['layer_order'])} layers; clipped {clipped} cells")
    if args.dry_run:
        return
    shutil.copy2(args.tmj, args.tmj + ".bak")
    with open(args.tmj, "w") as fh:
        json.dump(tmj, fh, separators=(",", ":"))
    print(f"wrote {args.tmj} (backup {args.tmj}.bak)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --extra dev pytest tools/geo/test_furnish_van_pelt.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/geo/furnish_van_pelt.py tools/geo/test_furnish_van_pelt.py
git commit -m "feat(geo): transplant Van Pelt interior layers onto the picture"
```

---

## Task 3: Matrix subdivision in `add_entrances.py`

**Files:**
- Modify: `tools/geo/add_entrances.py` (constants near line 66; new helper; carve loop ~506–557; arena-row merge ~564–567)
- Test: `tools/geo/test_van_pelt_arenas.py`

**Interfaces:**
- Consumes: `van_pelt_interior.json` (Task 1); existing `read_flat`, `read_blocks`, `split_footprint`.
- Produces: arenas `13000`–`13024` for Van Pelt's rooms (id = `ROOM_ARENA_BASE 10000 + sector_id*100 + room_index`), kept lobby `1030`, partition-wall collision. New module-level `ROOM_ARENA_BASE`, `ROOM_SUBDIVIDE`, `load_room_plan()`, `subdivide_rooms(...)`.

- [ ] **Step 1: Write the failing test**

```python
# tools/geo/test_van_pelt_arenas.py
import collections, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC_MATRIX = os.path.join(REPO, "godot-generative-agents", "sim", "the_upenn", "matrix")
SRC_MAP = os.path.join(REPO, "godot-generative-agents", "maps", "upenn_core_urban.tmj")
W, H = 245, 279

def _run(tmp):
    """Copy map+matrix into tmp, run add_entrances against them, return paths."""
    mdir = os.path.join(tmp, "matrix")
    shutil.copytree(SRC_MATRIX, mdir)
    tmap = os.path.join(tmp, "map.tmj")
    shutil.copy2(SRC_MAP, tmap)
    subprocess.run([sys.executable, os.path.join(HERE, "add_entrances.py"),
                    "--tmj", tmap, "--matrix", mdir],
                   check=True, cwd=HERE)
    return mdir

def _read_flat(p):
    return open(p).read().strip().split(", ")

def _arena_blocks(mdir):
    rows = []
    with open(os.path.join(mdir, "special_blocks", "arena_blocks.csv")) as fh:
        for line in fh:
            if line.strip():
                rows.append([p.strip() for p in line.split(",")])
    return rows

def test_25_van_pelt_room_arenas_present(tmp_path):
    mdir = _run(str(tmp_path))
    rows = _arena_blocks(mdir)
    vp_rooms = [r for r in rows if r[2] == "Van Pelt Library" and r[3] not in ("grounds", "lobby")]
    assert len(vp_rooms) == 25
    ids = sorted(int(r[0]) for r in vp_rooms)
    assert ids == list(range(13000, 13025))
    names = {r[3] for r in vp_rooms}
    assert "Moelis Family Grand Reading Room" in names and "Kamin Gallery" in names
    # lobby retained for leftover circulation
    assert any(r[2] == "Van Pelt Library" and r[3] == "lobby" for r in rows)

def test_williams_unchanged(tmp_path):
    mdir = _run(str(tmp_path))
    rows = _arena_blocks(mdir)
    will = [r for r in rows if r[2] == "Williams Hall"]
    kinds = sorted(r[3] for r in will)
    assert kinds == ["grounds", "lobby"]  # no room subdivision

def test_every_room_arena_reachable_from_a_door(tmp_path):
    mdir = _run(str(tmp_path))
    coll = _read_flat(os.path.join(mdir, "maze", "collision_maze.csv"))
    arena = _read_flat(os.path.join(mdir, "maze", "arena_maze.csv"))
    # BFS over all walkable cells from every map-border walkable cell; collect arenas.
    seen = [False] * (W * H)
    q = collections.deque()
    for x in range(W):
        for y in (0, H - 1):
            i = y * W + x
            if coll[i] == "0" and not seen[i]:
                seen[i] = True; q.append((x, y))
    for y in range(H):
        for x in (0, W - 1):
            i = y * W + x
            if coll[i] == "0" and not seen[i]:
                seen[i] = True; q.append((x, y))
    reached = set()
    while q:
        x, y = q.popleft()
        reached.add(arena[y * W + x])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H:
                j = ny * W + nx
                if coll[j] == "0" and not seen[j]:
                    seen[j] = True; q.append((nx, ny))
    for rid in range(13000, 13025):
        assert str(rid) in reached, f"room arena {rid} unreachable through the door"

def test_idempotent(tmp_path):
    mdir = _run(str(tmp_path))
    a = open(os.path.join(mdir, "maze", "arena_maze.csv")).read()
    c = open(os.path.join(mdir, "maze", "collision_maze.csv")).read()
    subprocess.run([sys.executable, os.path.join(HERE, "add_entrances.py"),
                    "--tmj", os.path.join(str(tmp_path), "map.tmj"), "--matrix", mdir],
                   check=True, cwd=HERE)
    assert open(os.path.join(mdir, "maze", "arena_maze.csv")).read() == a
    assert open(os.path.join(mdir, "maze", "collision_maze.csv")).read() == c
```

Note: the BFS reaches the interior only if at least one building door connects outside to the rooms. If `test_every_room_arena_reachable_from_a_door` fails, the entrance reconciliation is needed — see Step 3b.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --extra dev pytest tools/geo/test_van_pelt_arenas.py -v`
Expected: FAIL — `test_25_van_pelt_room_arenas_present` finds 0 room arenas (only the lobby today).

- [ ] **Step 3a: Add constants + the room-plan loader + subdivision helper**

Add near the existing arena constants (after line 68, `INTERIOR_ARENA_BASE = 1000`):

```python
ROOM_ARENA_BASE = 10000  # room arena id = base + sector*100 + index (clears lobby range)
ROOM_SUBDIVIDE = {"Van Pelt Library"}  # buildings whose interior is split into rooms


def load_room_plan():
    """(rooms, wall_cells) from van_pelt_interior.json: the 25 room rects and the
    partition-wall cell set. Returns ([], set()) if the asset is missing."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "van_pelt_interior.json")
    if not os.path.exists(path):
        return [], set()
    with open(path) as fh:
        a = json.load(fh)
    W = a["width"]
    rooms = a["rooms"]
    wall_cells = {(i % W, i // W) for i in a["wall_cells"]}
    return rooms, wall_cells


def subdivide_rooms(sid, name, interior, door_cells, collision, arena_m,
                    room_rows, W, room_plan):
    """Turn one building's lobby interior into per-room arenas + partition walls.
    Stamps over the already-written lobby base, so cells in no room stay lobby."""
    rooms, wall_cells = room_plan
    # partition walls become collision (but never seal the building door)
    for (x, y) in (wall_cells & interior) - door_cells:
        collision[y * W + x] = "1"
    walk = {(x, y) for (x, y) in interior if collision[y * W + x] == "0"}
    for idx, room in enumerate(rooms):
        rid = str(ROOM_ARENA_BASE + int(sid) * 100 + idx)
        c0, r0, c1, r1 = room["rect"]
        for y in range(r0, r1 + 1):
            for x in range(c0, c1 + 1):
                if (x, y) in walk:
                    arena_m[y * W + x] = rid
        room_rows.append([rid, WORLD, name, room["name"]])
```

- [ ] **Step 3b: Wire subdivision into the carve loop**

In `main()`, before the carve loop (near `arena_lobby_rows = []`, ~line 503) add a sibling list and load the plan once:

```python
    arena_lobby_rows = []  # (lobby_id, world, sector, "lobby")
    arena_room_rows = []   # (room_id, world, sector, room_name) for subdivided buildings
    room_plan = load_room_plan()
    picture_jobs = []
```

In the loop, replace the lobby-stamp block (the current lines):

```python
        sid = sid_by_name[name]
        lobby_id = str(INTERIOR_ARENA_BASE + int(sid))
        for x, y in interior:
            arena_m[y * W + x] = lobby_id
        arena_lobby_rows.append([lobby_id, WORLD, name, LOBBY])

        if name != WILLIAMS:  # Williams' picture is already its furnished cutaway
            picture_jobs.append((name, foot, perimeter, door_cells))
```

with:

```python
        sid = sid_by_name[name]
        lobby_id = str(INTERIOR_ARENA_BASE + int(sid))
        for x, y in interior:
            arena_m[y * W + x] = lobby_id
        arena_lobby_rows.append([lobby_id, WORLD, name, LOBBY])

        if name in ROOM_SUBDIVIDE:
            subdivide_rooms(sid, name, interior, door_cells, collision, arena_m,
                            arena_room_rows, W, room_plan)

        if name != WILLIAMS:  # Williams' picture is already its furnished cutaway
            picture_jobs.append((name, foot, perimeter, door_cells))
```

Then extend the arena-row merge (after `new_arena_rows += sorted(arena_lobby_rows, …)`, ~line 567):

```python
    new_arena_rows += sorted(arena_lobby_rows, key=lambda r: int(r[0]))
    new_arena_rows += sorted(arena_room_rows, key=lambda r: int(r[0]))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --extra dev pytest tools/geo/test_van_pelt_arenas.py -v`
Expected: PASS (4 tests). **If `test_every_room_arena_reachable_from_a_door` fails:** the carved east door does not connect to every room through the designed doorways. Resolve the entrance (the spec's open item): inspect with the rendering in Task 4, then either (a) special-case Van Pelt's door at the designed `Entrance` room's perimeter (mirror the `WILLIAMS_DOOR_X` block at line ~514), or (b) widen/add the missing internal doorway. Re-run until green, and record the choice in the PR description.

- [ ] **Step 5: Commit**

```bash
git add tools/geo/add_entrances.py tools/geo/test_van_pelt_arenas.py
git commit -m "feat(geo): subdivide Van Pelt into per-room navigable arenas"
```

---

## Task 4: Regenerate artifacts + QA

**Files:**
- Modify (regenerate): `godot-generative-agents/maps/upenn_core_urban.tmj`
- Modify (regenerate): `godot-generative-agents/sim/the_upenn/matrix/maze/{arena_maze,collision_maze}.csv`, `…/special_blocks/arena_blocks.csv`

**Interfaces:** none (runs the Task 2 + Task 3 tools against the real files).

- [ ] **Step 1: Run the matrix subdivision on the real files**

Run: `uv run python tools/geo/add_entrances.py`
Expected: summary lists `Van Pelt Library` with an interior count; matrix CSVs written.

- [ ] **Step 2: Run the picture transplant on the real files**

Run: `uv run python tools/geo/furnish_van_pelt.py`
Expected: `transplanted 6 layers; clipped ~20 cells`; `wrote … (backup ….bak)`.

- [ ] **Step 3: Re-run the full geo test suite against the regenerated files**

Run: `uv run --extra dev pytest tools/geo/test_van_pelt_asset.py tools/geo/test_furnish_van_pelt.py tools/geo/test_van_pelt_arenas.py -v`
Expected: all PASS. (Note: `test_van_pelt_arenas.py` runs on temp copies, so it is independent of Step 1/2.)

- [ ] **Step 4: Visual check in Godot (cardinal rule)**

The cut-sprite guarantee is already automated by
`test_furniture_never_clipped_cardinal_rule` (Task 2) — this step is the final
human eyeball. `tiled_map.gd` reads the `.tmj` live each launch, so:

```bash
# Launch the Godot project (fully quit any running instance first — no import cache).
open -a Godot godot-generative-agents/project.godot   # or: godot --path godot-generative-agents
```
Pan to Van Pelt (cols 17–157, rows 17–68). Confirm: the detailed floors/walls/
furniture fill the interior; the perimeter + single door read at the edges; no
multi-tile sprite is cut at the throat seam (cols 66–67). If anything is cut,
stop and fix the asset/clip before committing.

- [ ] **Step 5: Sanity-check the matrix addressing**

Run: `grep "Van Pelt Library" godot-generative-agents/sim/the_upenn/matrix/special_blocks/arena_blocks.csv`
Expected: 27 lines — `grounds`, `lobby`, and 25 named rooms with ids `13000`–`13024`.

- [ ] **Step 6: Commit the regenerated artifacts**

```bash
git add godot-generative-agents/maps/upenn_core_urban.tmj \
        godot-generative-agents/sim/the_upenn/matrix/maze/arena_maze.csv \
        godot-generative-agents/sim/the_upenn/matrix/maze/collision_maze.csv \
        godot-generative-agents/sim/the_upenn/matrix/special_blocks/arena_blocks.csv
git commit -m "feat(geo): regenerate map + matrix with furnished, navigable Van Pelt"
```

---

## Notes for the implementer

- `furnish_van_pelt.py` and `add_entrances.py` both `import` from `add_entrances` / are run with `tools/geo` as the script dir, so module imports resolve without packaging.
- The two tools are order-independent (both derive Van Pelt's footprint from `entrance_floor` + `sector_maze`, which neither mutates in the other's domain). Task 4 runs matrix-then-picture by convention.
- Do **not** commit `*.bak` files (the transplant writes `upenn_core_urban.tmj.bak`).
- The entrance reconciliation (Task 3 Step 4) is the one genuinely open decision; surface the chosen option in the PR for review.
