# Furnish Williams Hall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subdivide Williams Hall's single lobby into 5 room arenas, seal its interior walls, and route Professor Tanaka into a classroom — the rooms are already painted by `furnish_building.py`, so this wires them into the matrix + relayers walls/windows onto a proper layer.

**Architecture:** A new `furnish_williams.py` (a) relayers `wall_brick`/window tiles off `williams_floor`/`williams_furniture` onto a new `williams_walls` layer and seeds a `williams_arenas` object layer, writing the committed tmj via a **format-preserving text-splice** (only changed rows + 2 new layers differ); (b) provides `read_sections`/`grouped_sections`/`williams_wall_cells` that `add_entrances.load_williams_plan` consumes to subdivide the interior. Matrices regenerate from the mutated tmj; `world_data_upenn.yaml` gains one schedulable classroom.

**Tech Stack:** Python 3.12, `uv run pytest`, the `tools/geo` matrix pipeline (`add_entrances.py`, `block_furniture.py`, `gen_furniture_matrix.py`), Tiled `.tmj`.

## Global Constraints

- **Branch/track:** `feat/furnish-williams-538` off `godot-ga-main`; PR targets `godot-ga-main` (geo change). Work in the worktree at `.claude/worktrees/furnish-williams-538/`.
- **Grid:** `W, H = 245, 279`. Williams sector id `32`; lobby arena `1032`; room arenas `ROOM_ARENA_BASE(10000) + 32*100 + idx` → `13200..13204`.
- **Palette (reuse `furnish_building` constants, do not hardcode):** `WALL_GID = furnish_building.WALL` (543 `wall_brick`), `WINDOW_GID = furnish_building.WINDOW` (737 window), `FLOOR_GID = furnish_building.FLOOR` (`floor_wood_light`). `GID_MASK = 0x1FFFFFFF`.
- **tmj is Tiled-format:** never `json.dump` the whole tmj (reformats 11 MB). Only splice changed/new layers; `data` arrays wrap at W values per line. Back up the tmj (`.bak`) before writing.
- **Never** `git add -A`/`git add .` — add explicit paths. Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Verified facts:** `williams_floor` = 1059 floor + 386 `wall_brick`; `williams_furniture` = 165 furniture + 46 window (gid 737, all on perimeter wall cells) + 5 prop; footprint 1445. The Tanaka↔Sofia meeting is at Irvine (not Williams) — do not touch meetings.

---

### Task 1: `furnish_williams.py` — arena parsing + grouping helpers

**Files:**
- Create: `godot-generative-agents/tools/geo/furnish_williams.py`
- Test: `godot-generative-agents/tools/geo/test_furnish_williams.py`

**Interfaces:**
- Produces: `_group(name) -> str`, `read_sections(tmj) -> dict[str, tuple[int,int,int,int]]` (name → inclusive `(c0,r0,c1,r1)` tile rect), `grouped_sections(tmj) -> dict[str, tuple[int,int,int,int]]` (numbered sub-boxes merged to one bbox per group; `Lobby*` groups excluded).

- [ ] **Step 1: Write the failing test**

```python
# test_furnish_williams.py
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import furnish_williams as fw


def _tmj_with_arenas(objects):
    return {
        "width": 245, "height": 279,
        "layers": [
            {"type": "objectgroup", "name": "williams_arenas", "objects": objects},
        ],
    }


def _obj(name, x, y, w, h, t=""):
    return {"name": name, "type": t, "x": x, "y": y, "width": w, "height": h}


def test_read_sections_rounds_px_to_tiles():
    tmj = _tmj_with_arenas([_obj("Classroom A", 208, 3648, 160, 224)])
    secs = fw.read_sections(tmj)
    assert secs["Classroom A"] == (13, 228, 21, 241)


def test_grouped_sections_merges_numbered_and_drops_lobby():
    tmj = _tmj_with_arenas([
        _obj("Classroom B 1", 832, 3776, 240, 80),
        _obj("Classroom B 2", 912, 3712, 160, 64),
        _obj("Lobby 1", 560, 3776, 256, 192),
        _obj("Office", 224, 3952, 208, 144),
    ])
    g = fw.grouped_sections(tmj)
    assert "Lobby" not in g and "Lobby 1" not in g
    assert set(g) == {"Classroom B", "Office"}
    # Classroom B bbox spans both sub-boxes
    c0, r0, c1, r1 = g["Classroom B"]
    assert (c0, r0) == (52, 232) and c1 == 66 and r1 == 240
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd godot-generative-agents/tools/geo && uv run pytest test_furnish_williams.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'furnish_williams'`.

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""Wire Williams Hall's already-painted rooms into the matrix: read the
`williams_arenas` object layer, relayer walls/windows onto `williams_walls`, and
provide the room rects + wall cells `add_entrances` subdivides from. The floor
and furniture art already exist (furnish_building.py) -- this does NOT repaint.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import furnish_building as fb

GID_MASK = 0x1FFFFFFF
WALL_GID = fb.WALL      # wall_brick (543)
WINDOW_GID = fb.WINDOW  # window 4-pane (737)
FLOOR_GID = fb.FLOOR    # floor_wood_light


def _group(name):
    """Room-group name: boxes differing only by a trailing number are one room
    ('Classroom B 1'/'Classroom B 2' -> 'Classroom B'). Mirrors furnish_irvine."""
    return re.sub(r"\s*\d+$", "", name).strip() or name


def _arenas_layer(tmj):
    return next(
        (L for L in tmj["layers"]
         if L.get("name") == "williams_arenas" and L.get("type") == "objectgroup"),
        None,
    )


def read_sections(tmj):
    """name -> (c0,r0,c1,r1) inclusive tile rect, from the williams_arenas object
    layer (px/16 rounded, same idiom as furnish_college_hall.read_sections)."""
    layer = _arenas_layer(tmj)
    secs = {}
    if not layer:
        return secs
    for o in layer["objects"]:
        name = o.get("name") or ""
        if not name:
            continue
        c0 = round(o["x"] / 16)
        r0 = round(o["y"] / 16)
        c1 = round((o["x"] + o["width"]) / 16) - 1
        r1 = round((o["y"] + o["height"]) / 16) - 1
        secs[name] = (c0, r0, c1, r1)
    return secs


def grouped_sections(tmj):
    """Merge numbered sub-boxes into one bbox per group (Irvine idiom) and drop
    the `Lobby*` group -- those cells stay the lobby arena (the general-seating
    atrium), like furnish_college_hall drops `rug` objects."""
    groups = {}
    for nm, (c0, r0, c1, r1) in read_sections(tmj).items():
        g = _group(nm)
        if g == "Lobby":
            continue
        if g in groups:
            a, b, cc, dd = groups[g]
            groups[g] = (min(a, c0), min(b, r0), max(cc, c1), max(dd, r1))
        else:
            groups[g] = (c0, r0, c1, r1)
    return groups
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd godot-generative-agents/tools/geo && uv run pytest test_furnish_williams.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/tools/geo/furnish_williams.py godot-generative-agents/tools/geo/test_furnish_williams.py
git commit -m "feat(geo): furnish_williams arena parsing + grouping helpers (#538)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: relayer computation + `williams_wall_cells`

**Files:**
- Modify: `godot-generative-agents/tools/geo/furnish_williams.py`
- Test: `godot-generative-agents/tools/geo/test_furnish_williams.py`

**Interfaces:**
- Consumes: `WALL_GID`, `WINDOW_GID`, `FLOOR_GID`, `GID_MASK` (Task 1).
- Produces: `compute_relayer(tmj) -> (new_walls, new_floor, new_furn)` (flat gid lists), `williams_wall_cells(tmj) -> set[tuple[int,int]]`.

- [ ] **Step 1: Write the failing test**

```python
# append to test_furnish_williams.py
def _grid(pairs, W=245, H=279):
    d = [0] * (W * H)
    for (x, y), g in pairs.items():
        d[y * W + x] = g
    return d


def _tmj_tiles(floor, furn, walls=None):
    layers = [
        {"type": "tilelayer", "name": "williams_floor", "data": floor},
        {"type": "tilelayer", "name": "williams_furniture", "data": furn},
    ]
    if walls is not None:
        layers.insert(1, {"type": "tilelayer", "name": "williams_walls", "data": walls})
    return {"width": 245, "height": 279, "layers": layers}


def test_compute_relayer_moves_walls_and_windows():
    floor = _grid({(5, 5): fw.WALL_GID, (6, 5): 100})   # a wall + a floor tile
    furn = _grid({(5, 5): fw.WINDOW_GID, (7, 5): 200})  # window over the wall + furniture
    walls, new_floor, new_furn = fw.compute_relayer(_tmj_tiles(floor, furn))
    W = 245
    assert walls[5 * W + 5] == fw.WINDOW_GID        # window wins on the walls layer
    assert new_floor[5 * W + 5] == fw.FLOOR_GID     # floor painted under the moved wall
    assert new_floor[5 * W + 6] == 100              # untouched floor tile stays
    assert new_furn[5 * W + 5] == 0                 # window removed from furniture
    assert new_furn[5 * W + 7] == 200               # real furniture stays


def test_compute_relayer_idempotent():
    floor = _grid({(5, 5): fw.WALL_GID})
    furn = _grid({(5, 5): fw.WINDOW_GID})
    walls, nf, nfu = fw.compute_relayer(_tmj_tiles(floor, furn))
    # feed the result back in as an existing williams_walls layer + cleaned floor/furn
    walls2, nf2, nfu2 = fw.compute_relayer(_tmj_tiles(nf, nfu, walls=walls))
    assert walls2 == walls and nf2 == nf and nfu2 == nfu


def test_williams_wall_cells_reads_walls_layer():
    floor = _grid({})
    furn = _grid({})
    walls = _grid({(5, 5): fw.WALL_GID, (6, 5): fw.WINDOW_GID})
    cells = fw.williams_wall_cells(_tmj_tiles(floor, furn, walls=walls))
    assert cells == {(5, 5), (6, 5)}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd godot-generative-agents/tools/geo && uv run pytest test_furnish_williams.py -q`
Expected: FAIL — `AttributeError: module 'furnish_williams' has no attribute 'compute_relayer'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to furnish_williams.py
def _tile_layers(tmj):
    return {L["name"]: L for L in tmj["layers"] if L.get("type") == "tilelayer"}


def compute_relayer(tmj):
    """Return (new_walls, new_floor, new_furn) flat gid arrays: move wall_brick
    off williams_floor and window off williams_furniture onto williams_walls,
    painting floor under the moved walls. Windows win over walls on the walls
    layer. Idempotent -- an existing williams_walls layer seeds the geometry, so
    a second run (floor/furniture already cleaned) reproduces the same arrays."""
    layers = _tile_layers(tmj)
    floor = layers["williams_floor"]["data"]
    furn = layers["williams_furniture"]["data"]
    existing = layers.get("williams_walls")
    new_walls = list(existing["data"]) if existing else [0] * len(floor)
    new_floor = list(floor)
    new_furn = list(furn)
    for i, g in enumerate(floor):
        if (g & GID_MASK) == WALL_GID:
            new_walls[i] = WALL_GID
            new_floor[i] = FLOOR_GID
    for i, g in enumerate(furn):
        if (g & GID_MASK) == WINDOW_GID:
            new_walls[i] = WINDOW_GID
            new_furn[i] = 0
    return new_walls, new_floor, new_furn


def williams_wall_cells(tmj):
    """The {(x,y)} cells on williams_walls -- the authoritative wall geometry
    (the tiles furnish_building painted, relayered). add_entrances seals the
    interior subset; the perimeter is sealed by the main carve loop."""
    W = tmj["width"]
    layers = _tile_layers(tmj)
    wl = layers.get("williams_walls")
    if not wl:
        return set()
    return {(i % W, i // W) for i, g in enumerate(wl["data"]) if g}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd godot-generative-agents/tools/geo && uv run pytest test_furnish_williams.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/tools/geo/furnish_williams.py godot-generative-agents/tools/geo/test_furnish_williams.py
git commit -m "feat(geo): furnish_williams wall/window relayer + wall-cell provider (#538)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: tmj text-splice writer + apply to the committed tmj

**Files:**
- Modify: `godot-generative-agents/tools/geo/furnish_williams.py`
- Modify (generated, via running the script): `godot-generative-agents/godot/maps/upenn_core_urban.tmj`

**Interfaces:**
- Consumes: `compute_relayer` (Task 2), `WILLIAMS_ARENA_OBJECTS`.
- Produces: `apply_to_file(tmj_path)`; a `main()` CLI. The committed tmj gains `williams_walls` (tile layer, between `williams_floor` and `williams_furniture`) + `williams_arenas` (objectgroup); `williams_floor`/`williams_furniture` data updated.

- [ ] **Step 1: Add the arena objects constant + splice writer**

Copy the 8 objects the user drew/tweaked in Tiled (verbatim — float coords preserved). Then add the splice functions.

```python
# add to furnish_williams.py
WILLIAMS_ARENA_OBJECTS = [
    {"name": "Classroom A", "type": "classroom", "x": 208, "y": 3648, "width": 158, "height": 224.666666666667},
    {"name": "Classroom B 1", "type": "classroom", "x": 830.666666666667, "y": 3777.33333333333, "width": 242.666666666667, "height": 76.6666666666665},
    {"name": "Office", "type": "office", "x": 224, "y": 3952, "width": 205.333333333333, "height": 145.333333333333},
    {"name": "Restroom", "type": "restroom", "x": 493.333333333333, "y": 3981.33333333333, "width": 162.666666666667, "height": 114},
    {"name": "Classroom C", "type": "classroom", "x": 897.333333333333, "y": 3954, "width": 174, "height": 141.333333333333},
    {"name": "Classroom B 2", "type": "classroom", "x": 911.999833333333, "y": 3712.99998333333, "width": 159.333666666667, "height": 62.0000333333335},
    {"name": "Lobby 1", "type": "", "x": 560.666666666667, "y": 3778, "width": 254, "height": 190.666666666667},
    {"name": "Lobby 2", "type": "", "x": 674.666666666667, "y": 3971.33333333333, "width": 203.333333333333, "height": 138.666666666667},
]


def _fmt_data(data, W, wrap_indent):
    """Render a flat gid array as Tiled does: W values per line (one map row),
    `, ` between values, `,\\n<wrap_indent>` between rows."""
    rows = [", ".join(str(g) for g in data[r:r + W]) for r in range(0, len(data), W)]
    return (",\n" + wrap_indent).join(rows)


def _wrap_indent(text, dstart):
    """The continuation indent Tiled uses inside a layer's data array."""
    nl = text.find("\n", dstart)
    j = nl + 1
    while j < len(text) and text[j] == " ":
        j += 1
    return text[nl + 1:j]


def _replace_layer_data(text, layer_name, new_data, W):
    """Replace the data array of one named tile layer, preserving Tiled's
    W-per-line wrapping so unchanged rows stay byte-identical."""
    nidx = text.find(f'"name":"{layer_name}"')
    if nidx < 0:
        raise ValueError(f"layer {layer_name} not found")
    bstart = text.rfind("{", 0, nidx)
    dstart = text.find('"data":[', bstart)
    dend = text.find("]", dstart)
    wi = _wrap_indent(text, dstart)
    return text[:dstart] + '"data":[' + _fmt_data(new_data, W, wi) + text[dend:]


def _tile_layer_block(data, layer_id, name, W, H, k9):
    """Tiled-format tile layer object text (alphabetical keys, inline W-wrapped
    data); k9 is the 9-space field indent from a sibling layer."""
    k8 = k9[:-1]
    arr = _fmt_data(data, W, k9 + "   ")
    return (
        "{\n"
        f'{k9}"data":[{arr}],\n'
        f'{k9}"height":{H},\n'
        f'{k9}"id":{layer_id},\n'
        f'{k9}"name":"{name}",\n'
        f'{k9}"opacity":1,\n'
        f'{k9}"type":"tilelayer",\n'
        f'{k9}"visible":true,\n'
        f'{k9}"width":{W},\n'
        f'{k9}"x":0,\n'
        f'{k9}"y":0\n'
        f"{k8}}}"
    )


def _object_layer_block(objects, layer_id, name, next_obj, k9):
    """Tiled-format objectgroup text with rectangle objects (matches the sibling
    *_arenas layers: objects indented 7 spaces past the layer fields)."""
    k8 = k9[:-1]
    ko = k9 + "       "
    kof = ko + " "
    parts = []
    oid = next_obj
    for o in objects:
        parts.append(
            "{\n"
            f'{kof}"height":{o["height"]},\n'
            f'{kof}"id":{oid},\n'
            f'{kof}"name":"{o["name"]}",\n'
            f'{kof}"opacity":1,\n'
            f'{kof}"rotation":0,\n'
            f'{kof}"type":"{o.get("type", "")}",\n'
            f'{kof}"visible":true,\n'
            f'{kof}"width":{o["width"]},\n'
            f'{kof}"x":{o["x"]},\n'
            f'{kof}"y":{o["y"]}\n'
            f"{ko}}}"
        )
        oid += 1
    objs = (", \n" + ko).join(parts)
    return (
        "{\n"
        f'{k9}"draworder":"topdown",\n'
        f'{k9}"id":{layer_id},\n'
        f'{k9}"name":"{name}",\n'
        f'{k9}"objects":[\n{ko}{objs}\n{k9}],\n'
        f'{k9}"opacity":1,\n'
        f'{k9}"type":"objectgroup",\n'
        f'{k9}"visible":true,\n'
        f'{k9}"x":0,\n'
        f'{k9}"y":0\n'
        f"{k8}}}"
    )


def apply_to_file(tmj_path):
    """Splice williams_walls + williams_arenas into the committed tmj and update
    williams_floor/williams_furniture data, preserving Tiled formatting (only the
    changed rows + the two new layers differ). Backs up to <path>.bak first."""
    tmj = json.load(open(tmj_path))
    W, H = tmj["width"], tmj["height"]
    new_walls, new_floor, new_furn = compute_relayer(tmj)
    maxid = max(L.get("id", 0) for L in tmj["layers"])
    walls_id, arenas_id = maxid + 1, maxid + 2
    next_obj = tmj.get("nextobjectid", 1)

    text = open(tmj_path).read()
    shutil.copy2(tmj_path, tmj_path + ".bak")
    text = _replace_layer_data(text, "williams_floor", new_floor, W)
    text = _replace_layer_data(text, "williams_furniture", new_furn, W)

    fidx = text.find('"name":"williams_furniture"')
    fstart = text.rfind("{", 0, fidx)
    line0 = text.rfind("\n", 0, fstart) + 1
    k8 = text[line0:fstart]
    k9 = k8 + " "
    walls_block = _tile_layer_block(new_walls, walls_id, "williams_walls", W, H, k9)
    arenas_block = _object_layer_block(
        WILLIAMS_ARENA_OBJECTS, arenas_id, "williams_arenas", next_obj, k9
    )
    insertion = walls_block + ",\n" + k8 + arenas_block + ",\n" + k8
    text = text[:line0] + k8 + insertion + text[line0 + len(k8):]

    text = re.sub(r'"nextlayerid":\d+', f'"nextlayerid":{maxid + 3}', text, count=1)
    text = re.sub(
        r'"nextobjectid":\d+',
        f'"nextobjectid":{next_obj + len(WILLIAMS_ARENA_OBJECTS)}',
        text, count=1,
    )
    with open(tmj_path, "w") as fh:
        fh.write(text)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tmj", default=os.path.join(
        repo, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"))
    args = ap.parse_args()
    apply_to_file(args.tmj)
    print(f"spliced williams_walls + williams_arenas into {args.tmj}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add a splice test (content + layer order)**

```python
# append to test_furnish_williams.py
import json, shutil


def test_apply_to_file_content_and_order(tmp_path):
    src = os.path.join(
        os.path.dirname(os.path.dirname(HERE)), "godot", "maps", "upenn_core_urban.tmj"
    )
    # note: HERE is tools/geo; the committed tmj is under godot/maps
    repo_map = os.path.normpath(os.path.join(HERE, "..", "..", "godot", "maps", "upenn_core_urban.tmj"))
    dst = str(tmp_path / "map.tmj")
    shutil.copy2(repo_map, dst)
    fw.apply_to_file(dst)
    t = json.load(open(dst))  # must parse
    layers = {L["name"]: L for L in t["layers"] if L.get("type") == "tilelayer"}
    W = t["width"]
    walls = layers["williams_walls"]["data"]
    from collections import Counter
    wc = Counter(g & fw.GID_MASK for g in walls if g)
    assert wc == {fw.WALL_GID: 340, fw.WINDOW_GID: 46}
    assert sum(1 for g in layers["williams_floor"]["data"] if (g & fw.GID_MASK) == fw.WALL_GID) == 0
    assert sum(1 for g in layers["williams_furniture"]["data"] if (g & fw.GID_MASK) == fw.WINDOW_GID) == 0
    ar = next(L for L in t["layers"] if L.get("name") == "williams_arenas")
    assert len(ar["objects"]) == 8
    names = [L["name"] for L in t["layers"]]
    assert names.index("williams_floor") < names.index("williams_walls") < names.index("williams_furniture")
```

- [ ] **Step 3: Run the splice test**

Run: `cd godot-generative-agents/tools/geo && uv run pytest test_furnish_williams.py -q`
Expected: PASS (6 passed).

- [ ] **Step 4: Apply to the real committed tmj + verify diff is minimal**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/furnish-williams-538
uv run python godot-generative-agents/tools/geo/furnish_williams.py
python3 -c "import json; json.load(open('godot-generative-agents/godot/maps/upenn_core_urban.tmj')); print('parses OK')"
git --no-pager diff --stat godot-generative-agents/godot/maps/upenn_core_urban.tmj
rm -f godot-generative-agents/godot/maps/upenn_core_urban.tmj.bak
```
Expected: `parses OK`; diff touches only the tmj, ~500 lines (changed williams rows + the two new layers), no other layers.

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/tools/geo/furnish_williams.py godot-generative-agents/tools/geo/test_furnish_williams.py godot-generative-agents/godot/maps/upenn_core_urban.tmj
git commit -m "feat(geo): relayer Williams walls/windows + seed williams_arenas via tmj splice (#538)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: wire Williams into `add_entrances`, regenerate matrices, arena test

**Files:**
- Modify: `godot-generative-agents/tools/geo/add_entrances.py` (add `WILLIAMS` to `ROOM_SUBDIVIDE`; add `load_williams_plan`; dispatch it)
- Test: `godot-generative-agents/tools/geo/test_williams_arenas.py`
- Modify (generated): `backend/penn/the_upenn/matrix/maze/{collision,arena}_maze.csv`, `.../special_blocks/arena_blocks.csv`, `.../maze/furniture_maze.csv`, `.../special_blocks/furniture_blocks.csv`

**Interfaces:**
- Consumes: `furnish_williams.grouped_sections`, `furnish_williams.williams_wall_cells` (Tasks 1–2), the committed tmj with `williams_walls`/`williams_arenas` (Task 3).
- Produces: room arenas `13200..13204` in `arena_blocks.csv`; sealed interior walls in `collision_maze.csv`.

- [ ] **Step 1: Write the failing arena test** (modeled on `test_houston_arenas.py`)

```python
# test_williams_arenas.py
import collections, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SRC_MATRIX = os.path.join(REPO, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix")
SRC_MAP = os.path.join(REPO, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj")
W, H = 245, 279
WILLIAMS = "Williams Hall"
ROOM_IDS = list(range(13200, 13205))
ROOMS = {"Classroom A", "Classroom B", "Classroom C", "Office", "Restroom"}


def _run(tmp):
    mdir = os.path.join(tmp, "matrix")
    shutil.copytree(SRC_MATRIX, mdir)
    tmap = os.path.join(tmp, "map.tmj")
    shutil.copy2(SRC_MAP, tmap)
    subprocess.run([sys.executable, os.path.join(HERE, "add_entrances.py"),
                    "--tmj", tmap, "--matrix", mdir], check=True, cwd=HERE)
    return mdir, tmap


def _flat(p):
    return open(p).read().strip().split(", ")


def _arena_blocks(mdir):
    rows = []
    with open(os.path.join(mdir, "special_blocks", "arena_blocks.csv")) as fh:
        for line in fh:
            if line.strip():
                rows.append([p.strip() for p in line.split(",")])
    return rows


def test_williams_room_arenas_present(tmp_path):
    mdir, _ = _run(str(tmp_path))
    rows = _arena_blocks(mdir)
    wr = [r for r in rows if r[2] == WILLIAMS and r[3] not in ("grounds", "lobby")]
    assert sorted(int(r[0]) for r in wr) == ROOM_IDS
    assert {r[3] for r in wr} == ROOMS
    assert any(r[2] == WILLIAMS and r[3] == "lobby" for r in rows)  # atrium stays lobby


def test_williams_partition_walls_sealed(tmp_path):
    import furnish_williams as fw
    import json
    mdir, tmap = _run(str(tmp_path))
    tmj = json.load(open(tmap))
    coll = _flat(os.path.join(mdir, "maze", "collision_maze.csv"))
    # interior partition wall cells must be blocking (fixes walk-through-walls)
    walls = fw.williams_wall_cells(tmj)
    arena = _flat(os.path.join(mdir, "maze", "arena_maze.csv"))
    interior_walls = [(x, y) for (x, y) in walls if arena[y * W + x] != "32"]  # not grounds
    sealed = sum(1 for (x, y) in interior_walls if coll[y * W + x] == "1")
    assert sealed >= 380, f"only {sealed} williams wall cells sealed"


def test_every_williams_room_reachable(tmp_path):
    mdir, _ = _run(str(tmp_path))
    coll = _flat(os.path.join(mdir, "maze", "collision_maze.csv"))
    arena = _flat(os.path.join(mdir, "maze", "arena_maze.csv"))
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
    for rid in ROOM_IDS:
        assert str(rid) in reached, f"Williams room {rid} unreachable"


def test_no_windows_left_on_furniture(tmp_path):
    import furnish_building as fb
    import json
    _, tmap = _run(str(tmp_path))
    tmj = json.load(open(tmap))
    furn = next(L for L in tmj["layers"] if L.get("name") == "williams_furniture")
    assert not any((g & 0x1FFFFFFF) == fb.WINDOW for g in furn["data"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd godot-generative-agents/tools/geo && uv run pytest test_williams_arenas.py -q`
Expected: FAIL — `test_williams_room_arenas_present` (Williams not subdivided yet, no 13200-series rows).

- [ ] **Step 3: Wire Williams into `add_entrances.py`**

In `add_entrances.py`, add `WILLIAMS` to the `ROOM_SUBDIVIDE` set:

```python
ROOM_SUBDIVIDE = {
    VAN_PELT,
    FISHER,
    HOUSTON,
    IRVINE,
    COLLEGE,
    COHEN,
    ALUMNI,
    MEYERSON,
    WILLIAMS,
}
```

Add the plan loader near the other `load_*_plan` functions:

```python
def load_williams_plan(tmj, W, H, interior):
    """(rooms, wall_cells) for Williams from the williams_arenas object layer +
    the relayered williams_walls tiles. Rooms are the grouped sections (numbered
    sub-boxes merged, Lobby* excluded so the atrium stays lobby); wall_cells is
    the authoritative painted wall geometry, so collision matches the picture.
    Returns ([], set()) if williams_arenas is absent."""
    import furnish_williams as fw

    grouped = fw.grouped_sections(tmj)
    if not grouped:
        return [], set()
    rooms = [{"name": nm, "rect": list(rect)} for nm, rect in grouped.items()]
    return rooms, fw.williams_wall_cells(tmj)
```

Add the dispatch branch in `main()` alongside the others (after the `COHEN`/`ALUMNI`/`MEYERSON` branches, before the `else`):

```python
            elif name == WILLIAMS:
                plan = load_williams_plan(tmj, W, H, interior)
```

- [ ] **Step 4: Regenerate the matrices in order + verify only Williams changed**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/furnish-williams-538/godot-generative-agents/tools/geo
uv run python add_entrances.py
uv run python block_furniture.py
uv run python gen_furniture_matrix.py
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/furnish-williams-538
git --no-pager diff --stat godot-generative-agents/backend/penn/the_upenn/matrix/
```
Expected: `add_entrances` prints Williams with 5 room arenas; the 4 CSVs (`collision_maze`, `arena_maze`, `arena_blocks`, `furniture_maze`/`furniture_blocks`) change. Sanity-check no other building's arena row count changed:
```bash
grep -c "," godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/arena_blocks.csv
```
Expected: previous count + 5 (the new Williams rooms).

- [ ] **Step 5: Run the arena test to verify it passes**

Run: `cd godot-generative-agents/tools/geo && uv run pytest test_williams_arenas.py test_furnish_williams.py -q`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/furnish-williams-538
git add godot-generative-agents/tools/geo/add_entrances.py godot-generative-agents/tools/geo/test_williams_arenas.py godot-generative-agents/backend/penn/the_upenn/matrix/
git commit -m "feat(geo): subdivide Williams into 5 room arenas + seal interior walls (#538)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: surface Classroom A, route Tanaka, final verification

**Files:**
- Modify: `godot-generative-agents/backend/penn/world_data_upenn.yaml`
- Modify (if pinned): `godot-generative-agents/tools/geo/validate_tmj_baseline.json`
- Test: `godot-generative-agents/tests/test_penn_world.py` (or the existing Penn addressing test — add one case)

**Interfaces:**
- Consumes: room arena `Classroom A` (address `UPenn:Williams Hall:Classroom A`) from Task 4.

- [ ] **Step 1: Add the location + re-point Tanaka**

In `world_data_upenn.yaml`, add after the `Williams Hall` location entry (currently ending `address: UPenn:Williams Hall:lobby`):

```yaml
- name: Williams Hall — Classroom A
  description: A Williams Hall classroom with a blackboard, where problem sessions meet.
  address: UPenn:Williams Hall:Classroom A
```

Change Tanaka's second schedule stop from `place: Williams Hall` to:

```yaml
  - place: Williams Hall — Classroom A
    activity: holding a problem session for her physics class
    emoji: 🧮
```

- [ ] **Step 2: Write a failing addressing + enum test**

```python
# add to godot-generative-agents/tests/test_penn_world.py (create if absent, mirroring existing penn tests)
def test_classroom_a_address_resolves_and_has_spots():
    from backend.penn.penn_world import build_penn_world
    game, world_map = build_penn_world()  # match the project's actual builder signature
    tiles = world_map.tiles_for("UPenn:Williams Hall:Classroom A")
    assert tiles, "Classroom A address has no tiles"
    assert world_map.furniture_spots.get("UPenn:Williams Hall:Classroom A")


def test_decide_location_enum_within_budget():
    from backend.cognition import DECIDE_MAX_ENUM
    from backend.penn.penn_world import load_penn_locations  # match actual loader
    locs = load_penn_locations()
    assert len(locs) == 18 <= DECIDE_MAX_ENUM
```

> **Implementer note:** before writing, `grep -rn "tiles_for\|furniture_spots\|def build_penn_world\|locations" godot-generative-agents/tests/ godot-generative-agents/backend/penn/penn_world.py` to use the real builder/loader names and the existing Penn test file. Adjust imports to match; keep the two assertions (address resolves + enum == 18).

- [ ] **Step 3: Run to verify it fails, then passes**

Run: `cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/furnish-williams-538 && uv run pytest godot-generative-agents/tests/test_penn_world.py -q`
Expected: was FAIL before the yaml edit (enum 17 / no Classroom A tiles); PASS after.

- [ ] **Step 4: Refresh the validate_tmj baseline if the drift gate pins layer counts**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/furnish-williams-538/godot-generative-agents/tools/geo
uv run python validate_tmj.py || true   # inspect failures
# If it fails only on the two new williams layers / new arena rows, regenerate the baseline:
grep -n "baseline" validate_tmj.py   # find the --update-baseline flag or regen entrypoint
```

> **Implementer note:** `validate_tmj.py` compares tmj↔matrix consistency against `validate_tmj_baseline.json`. If it fails, confirm the only deltas are the Williams layers/arenas, then regenerate the baseline via the script's documented mechanism (read its `--help`/top docstring) and commit the updated baseline.

- [ ] **Step 5: Full verification gate**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/furnish-williams-538
uv run black --check godot-generative-agents/tools/geo/furnish_williams.py godot-generative-agents/tools/geo/test_furnish_williams.py godot-generative-agents/tools/geo/test_williams_arenas.py godot-generative-agents/tools/geo/add_entrances.py
uv run pytest godot-generative-agents/tools/geo -q
uv run pytest godot-generative-agents/tests -q
./godot-generative-agents/run_smoke_test.sh
```
Expected: black clean; geo suite PASS; backend suite PASS; smoke exit 0.

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/backend/penn/world_data_upenn.yaml godot-generative-agents/tests/test_penn_world.py
# add validate_tmj_baseline.json only if it was regenerated:
git add -u godot-generative-agents/tools/geo/validate_tmj_baseline.json 2>/dev/null || true
git commit -m "feat(geo): surface Williams Classroom A + route Tanaka's problem session (#538)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §1 furnish_williams (arena layer + relayer + wall cells) → Tasks 1–3. ✓
- §2 add_entrances subdivision → Task 4. ✓
- §3 world_data classroom + Tanaka → Task 5. ✓
- §4 regen matrices + surgical tmj → Task 3 (tmj splice) + Task 4 (matrices). ✓
- §5 tests (furnish, arena reachability, walls sealed, no stray windows, backend addressing, enum) → Tasks 1–5. ✓
- Bug 1 (walk-through walls) → Task 4 `test_williams_partition_walls_sealed`. ✓
- Bug 2 (stray windows) → Task 3 relayer + Task 4 `test_no_windows_left_on_furniture`. ✓

**Placeholder scan:** two "Implementer note" callouts (Task 5 backend test + validate_tmj baseline) intentionally defer exact symbol names to a `grep` because they depend on the current Penn test/loader signatures — the assertions and expected values are fixed. All geo code is complete and prototype-verified.

**Type consistency:** `compute_relayer` returns `(new_walls, new_floor, new_furn)` used consistently; `williams_wall_cells`/`grouped_sections`/`read_sections` signatures match between `furnish_williams.py`, `load_williams_plan`, and the tests. Arena ids `13200..13204` consistent across Task 4 test + expected `arena_blocks` rows.
