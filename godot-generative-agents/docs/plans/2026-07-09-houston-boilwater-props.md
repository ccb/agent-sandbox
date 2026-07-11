# Houston Hall Boil-Water Props (#466) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the boil-water props (sink, stove, pot) visible in Houston Hall and addressable as `UPenn:Houston Hall:lobby:{sink,stove,pot}`, per the approved spec `godot-generative-agents/docs/specs/2026-07-09-houston-boilwater-props.md`.

**Architecture:** The Fisher pipeline from PR #402, applied to Houston Hall: a surgical text edit paints a 4-piece kitchen strip into the existing `houston_furniture` layer and inserts a 3-rect `houston_objects` objectgroup (the committed tmj is Tiled-pretty; the geo scripts serialize minified, so no script may rewrite the tmj). `add_game_objects.py` is generalized from the hardcoded `fisher_objects` layer to a `*_objects` scan with per-sector id numbering, then the script-owned CSVs regenerate.

**Tech Stack:** Python 3.12, pytest, Tiled JSON (.tmj) text surgery, the `tools/geo` pipeline (`block_furniture.py`, `add_game_objects.py`, `validate_tmj.py`).

## Global Constraints

- Branch `feat/houston-objects-466` off `godot-ga-main`; PR targets `godot-ga-main`. **Independent of PR #465** — do not touch `world_data_upenn.yaml`, `backend/actions.py`, or anything #465 changed.
- **The tmj is never rewritten by a script that reserializes JSON.** Only the one-off surgical text edit in Task 2 touches `godot-generative-agents/godot/maps/upenn_core_urban.tmj`, and its diff must span only: the `houston_furniture` data line, the inserted `houston_objects` block, and the `nextlayerid`/`nextobjectid` lines. A `.bak` copy is made first and never committed.
- **Fisher stays byte-identical:** after the generalized `add_game_objects.py` run, the 19 Fisher rows in `game_object_blocks.csv` and every Fisher cell in `game_object_maze.csv` are unchanged (verified baseline: a dry-run today paints exactly `19 game objects (19 cells)` and `block_furniture` seals `0` tiles).
- Exact placement and tiles (verified visually against the sheets, 2026-07-09):
  - map grid 16 px; franuka firstgid **519** (32 cols); bath firstgid **1799** (16 cols); gid = firstgid + row·cols + col
  - kitchen strip on the lobby corridor's north wall: decorative tops on wall row **y=247**, solid bodies on floor row **y=248**, use-tiles on walking row **y=249** (rows 248–249 are the corridor; 250 is the south wall)
  - sink (bath 6,1 + 6,2): (117,247)=**1821**, (117,248)=**1837**
  - counter (franuka 0,23 + 0,24): (118,247)=**1255**, (118,248)=**1287**
  - stove (franuka 6,23 + 6,24 — the dark counter range; the catalog's old (8,24) entry was a mislabeled prep counter): (119,247)=**1261**, (119,248)=**1293**
  - pot (franuka 24,14) on a counter base: (120,247)=**991**, (120,248)=**1287**
  - object ids: sink=**114000**, stove=**114001**, pot=**114002** (100000 + 14·1000 + per-sector idx)
- All suites green before every commit: `uv run pytest tools/geo -q`, `uv run pytest godot-generative-agents/tests -q`; `uv run black --check .` clean (black does not touch .tmj/.csv/.json data files).
- Commit only files this plan names. Work from the worktree root `/Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/houston-objects-466`.

---

### Task 1: Generalize `add_game_objects.py` to a `*_objects` scan with per-sector ids

**Files:**
- Modify: `tools/geo/add_game_objects.py` (module docstring, `OBJECT_LAYER` const line 32, `read_objects` lines 69-85, `paint_objects` lines 97-125)
- Modify: `tools/geo/test_add_game_objects.py` (fixtures reference `ago.OBJECT_LAYER`; two new tests)

**Interfaces:**
- Consumes: nothing new.
- Produces: `OBJECT_LAYER_SUFFIX = "_objects"`; `read_objects(tmj)` returns named rects from **every** objectgroup layer whose name ends with `_objects`, in tmj layer order; `paint_objects(...)` numbers goids **per sector** (`100000 + sector*1000 + per_sector_idx`). Task 2's pipeline run and its regen-consistency test rely on both.

- [ ] **Step 1: Update the fixtures and write the failing tests**

In `tools/geo/test_add_game_objects.py`, replace every `ago.OBJECT_LAYER` reference (the strip filters in `_tmj_with_object` line 48 and `test_read_objects_absent_layer_is_empty` line 71) with the suffix rule, and add a Houston-cell helper plus two tests. The changed/new code:

```python
def _houston_lobby_cell():
    """A known walkable Houston-lobby cell (arena 1014) for a synthetic object."""
    arena = _flat("arena_maze.csv")
    coll = _flat("collision_maze.csv")
    for i, a in enumerate(arena):
        if a == "1014" and coll[i] == "0":
            return i % W, i // W
    raise AssertionError("no walkable Houston lobby cell found")


def _strip_object_layers(tmj):
    tmj["layers"] = [
        L
        for L in tmj["layers"]
        if not (L.get("name") or "").endswith(ago.OBJECT_LAYER_SUFFIX)
    ]


def _object_layer(name, objects):
    return {
        "type": "objectgroup",
        "name": name,
        "objects": [
            {"name": n, "x": x * 16, "y": y * 16, "width": 16, "height": 16}
            for n, x, y in objects
        ],
    }


def _tmj_with_object(x, y):
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    # The real map carries authored *_objects layers; drop them so this
    # fixture exercises exactly one synthetic object (idx 0 -> id 134000).
    _strip_object_layers(tmj)
    tmj["layers"].append(_object_layer("fisher_objects", [("bookshelf", x, y)]))
    return tmj


def test_read_objects_absent_layer_is_empty():
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    _strip_object_layers(tmj)
    assert ago.read_objects(tmj) == []


def test_multi_layer_scan_assigns_per_sector_ids():
    """#466: two *_objects layers scan in order; ids number per sector, so
    adding a building never renumbers another building's objects."""
    x_f, y_f = _fisher_interior_cell()
    x_h, y_h = _houston_lobby_cell()
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    _strip_object_layers(tmj)
    tmj["layers"].append(_object_layer("fisher_objects", [("bookshelf", x_f, y_f)]))
    tmj["layers"].append(_object_layer("houston_objects", [("sink", x_h, y_h)]))
    coll, arena, sector = (
        _flat("collision_maze.csv"),
        _flat("arena_maze.csv"),
        _flat("sector_maze.csv"),
    )
    _, obj_maze, rows = ago.paint_objects(
        tmj, coll, arena, sector, _sector_names(), W, H
    )
    assert [r[0] for r in rows] == ["134000", "114000"]
    assert obj_maze[y_f * W + x_f] == "134000"
    assert obj_maze[y_h * W + x_h] == "114000"
    assert rows[1][2] == "Houston Hall"
    assert rows[1][-1] == "sink"
```

(Keep `test_paint_assigns_id_and_reopens_use_tile` and `test_object_cells_share_one_arena_containment` exactly as they are — they must still pass, pinning Fisher's `134000` under the new numbering.)

- [ ] **Step 2: Run to verify the new test fails**

Run: `uv run pytest tools/geo/test_add_game_objects.py -v`
Expected: `test_multi_layer_scan_assigns_per_sector_ids` FAILS (`AttributeError: module 'add_game_objects' has no attribute 'OBJECT_LAYER_SUFFIX'`); others error the same way after the fixture edit.

- [ ] **Step 3: Implement the generalization**

In `tools/geo/add_game_objects.py`:

(a) Replace `OBJECT_LAYER = "fisher_objects"` (line 32) with:

```python
OBJECT_LAYER_SUFFIX = "_objects"
```

(b) Replace `read_objects` (lines 69-85) with:

```python
def read_objects(tmj: dict) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Named rects from every ``*_objects`` objectgroup, in tmj layer order."""
    out = []
    for layer in tmj["layers"]:
        if layer.get("type") != "objectgroup":
            continue
        if not (layer.get("name") or "").endswith(OBJECT_LAYER_SUFFIX):
            continue
        for o in layer.get("objects", []):
            name = o.get("name") or ""
            if name:
                out.append((name, _obj_rect(o)))
    return out
```

(c) In `paint_objects`, switch the goid numbering from the global `enumerate` to a per-sector counter — replace the loop head and goid line:

```python
    per_sector: Counter = Counter()
    for name, rect in read_objects(tmj):
        cells = _rect_cells(rect, W, H)
        sid_counts = Counter(sector[y * W + x] for (x, y) in cells)
        sid = sid_counts.most_common(1)[0][0] if sid_counts else FISHER_SECTOR
        goid = str(GAME_OBJECT_BASE + int(sid) * 1000 + per_sector[sid])
        per_sector[sid] += 1
```

(the rest of the loop body is unchanged).

(d) Update the module docstring: first line becomes "Paint interactable furniture into the game_object matrix layer."; replace the sentence naming the `fisher_objects` layer with "Reads every hand-authored ``*_objects`` object layer of upenn_core_urban.tmj (``fisher_objects``, ``houston_objects``, ...)"; replace "No-ops if the `fisher_objects` layer is absent" with "No-ops if no ``*_objects`` layer is present"; note the id scheme is per sector: "id = 100000 + sector*1000 + idx, idx numbered per sector so buildings never renumber each other".

- [ ] **Step 4: Run the geo suite**

Run: `uv run pytest tools/geo -q`
Expected: all pass (124 + 1 new). Then run the real-data check: `uv run python tools/geo/add_game_objects.py --dry-run` — expected output exactly `painted 19 game objects (19 cells)` (Fisher only, unchanged).

- [ ] **Step 5: Format + commit**

Run `uv run black --check .` (clean).

```bash
git add tools/geo/add_game_objects.py tools/geo/test_add_game_objects.py
git commit -m "feat(geo): add_game_objects scans all *_objects layers, per-sector ids (#466)"
```

---

### Task 2: The map edit + matrix regen + resolution tests

This task is one logical change (map + matrix must land in the same commit or the regen-consistency test would fail between commits).

**Files:**
- Modify: `godot-generative-agents/godot/maps/upenn_core_urban.tmj` (surgical text edit only)
- Modify: `tools/geo/furniture_catalog.json` (`stove` + `pot` entries)
- Modify (regenerated): `godot-generative-agents/backend/penn/the_upenn/matrix/maze/collision_maze.csv`, `.../maze/game_object_maze.csv`, `.../special_blocks/game_object_blocks.csv`
- Create: `godot-generative-agents/tests/test_houston_objects.py`
- Modify: `tools/geo/test_add_game_objects.py` (append the regen-consistency test)
- Create (scratchpad only, NOT committed): `<scratchpad>/edit_houston_tmj.py`

**Interfaces:**
- Consumes: Task 1's generalized scan; the exact gids/cells/ids from Global Constraints.
- Produces: routable `UPenn:Houston Hall:lobby:{sink,stove,pot}` addresses; committed CSVs exactly reproducible by the tools.

- [ ] **Step 1: Write the two failing tests**

Create `godot-generative-agents/tests/test_houston_objects.py`:

```python
"""#466: the boil-water props are visible map data and addressable at the
game_object tier -- the matrix half of #300 (the engine items live in the
world YAML, PR #465)."""

import os

from backend.world_map import WorldMap

UPENN = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "backend", "penn", "the_upenn"
)


def _collision():
    path = os.path.join(UPENN, "matrix", "maze", "collision_maze.csv")
    return open(path).read().strip().split(", ")


def test_houston_boilwater_objects_resolve_and_are_routable():
    wm = WorldMap(UPENN)
    coll = _collision()
    for obj in ("sink", "stove", "pot"):
        tiles = wm.address_tiles.get(f"UPenn:Houston Hall:lobby:{obj}")
        assert tiles, f"no tiles resolve for {obj}"
        for x, y in tiles:
            assert (
                coll[y * wm.width + x] == "0"
            ), f"{obj} use-tile ({x},{y}) is not walkable"
```

Append to `tools/geo/test_add_game_objects.py`:

```python
def test_real_map_paint_matches_committed_matrix():
    """The committed game-object CSVs are exactly what a re-run would paint --
    catches hand-edit drift, and pins Fisher's ids byte-stable under the
    multi-layer scan (#466)."""
    with open(SRC_MAP) as fh:
        tmj = json.load(fh)
    coll, arena, sector = (
        _flat("collision_maze.csv"),
        _flat("arena_maze.csv"),
        _flat("sector_maze.csv"),
    )
    new_coll, obj_maze, rows = ago.paint_objects(
        tmj, coll, arena, sector, _sector_names(), W, H
    )
    assert new_coll == coll  # every use-tile already open in the committed maze
    assert obj_maze == _flat("game_object_maze.csv")
    assert [r for r in rows] == _blocks("game_object_blocks.csv")
```

- [ ] **Step 2: Run to verify the state of each**

Run: `uv run pytest godot-generative-agents/tests/test_houston_objects.py tools/geo/test_add_game_objects.py -v`
Expected: `test_houston_boilwater_objects_resolve_and_are_routable` FAILS (`no tiles resolve for sink`); `test_real_map_paint_matches_committed_matrix` PASSES (the map has no Houston objects yet — it will guard the regen below).

- [ ] **Step 3: The surgical tmj edit**

Write this one-off editor to the scratchpad (do NOT commit it) and run it once from the worktree root:

```python
#!/usr/bin/env python3
"""One-off surgical edit (#466): paint the Houston kitchen strip into
houston_furniture and insert the houston_objects layer, preserving the
committed Tiled-pretty formatting everywhere else."""
import json
import re
import shutil

TMJ = "godot-generative-agents/godot/maps/upenn_core_urban.tmj"
W = 245
CELLS = {  # (x, y) -> gid, per the plan's Global Constraints
    (117, 247): 1821, (117, 248): 1837,  # pedestal sink (bath 6,1 / 6,2)
    (118, 247): 1255, (118, 248): 1287,  # counter (franuka 0,23 / 0,24)
    (119, 247): 1261, (119, 248): 1293,  # stove/oven (franuka 6,23 / 6,24)
    (120, 247): 991,  (120, 248): 1287,  # cooking pot (franuka 24,14) on counter
}
OBJECTS = [  # name, object id, use-tile (x, y)
    ("sink", 285, 117, 249),
    ("stove", 286, 119, 249),
    ("pot", 287, 120, 249),
]

shutil.copy2(TMJ, TMJ + ".bak")
text = open(TMJ).read()

# --- 1. houston_furniture data line: in-place integer swaps ---------------
m = re.search(
    r'"data":\[([^\]]*)\],\n(\s*)"height":279,\n\s*"id":101,\n\s*'
    r'"name":"houston_furniture"',
    text,
)
assert m, "houston_furniture data block not found"
cells = m.group(1).split(", ")
assert len(cells) == W * 279, f"unexpected cell count {len(cells)}"
for (x, y), gid in CELLS.items():
    i = y * W + x
    assert cells[i] == "0", f"cell ({x},{y}) already occupied: {cells[i]}"
    cells[i] = str(gid)
text = text[: m.start(1)] + ", ".join(cells) + text[m.end(1) :]

# --- 2. insert houston_objects after the fisher_objects layer -------------
OBJ_TMPL = """                {{
                 "height":16,
                 "id":{oid},
                 "name":"{name}",
                 "opacity":1,
                 "rotation":0,
                 "type":"",
                 "visible":true,
                 "width":16,
                 "x":{x},
                 "y":{y}
                }}"""
objs = ", \n".join(
    OBJ_TMPL.format(oid=oid, name=name, x=x * 16, y=y * 16)
    for name, oid, x, y in OBJECTS
)
LAYER = (
    "        {\n"
    '         "draworder":"topdown",\n'
    '         "id":124,\n'
    '         "name":"houston_objects",\n'
    '         "objects":[\n'
    f"{objs}],\n"
    '         "opacity":1,\n'
    '         "type":"objectgroup",\n'
    '         "visible":true,\n'
    '         "x":0,\n'
    '         "y":0\n'
    "        }, \n"
)
anchor = text.index('"name":"fisher_objects"')
close = text.index("\n        }, \n", anchor) + len("\n        }, \n")
text = text[:close] + LAYER + text[close:]

# --- 3. bump the stale Tiled counters --------------------------------------
# (they were already stale: fisher_objects uses layer id 123 / object ids
# 266-284, so the correct next values are 125 and 288)
text = text.replace('"nextlayerid":123,', '"nextlayerid":125,', 1)
text = text.replace('"nextobjectid":266,', '"nextobjectid":288,', 1)

open(TMJ, "w").write(text)

# --- verify: parses, and carries exactly what we meant ---------------------
tmj = json.load(open(TMJ))
layer = next(L for L in tmj["layers"] if L["name"] == "houston_objects")
assert [o["name"] for o in layer["objects"]] == ["sink", "stove", "pot"]
furn = next(L for L in tmj["layers"] if L["name"] == "houston_furniture")
for (x, y), gid in CELLS.items():
    assert furn["data"][y * W + x] == gid, (x, y)
assert tmj["nextlayerid"] == 125 and tmj["nextobjectid"] == 288
print("tmj edit OK")
```

Run: `uv run python <scratchpad>/edit_houston_tmj.py`
Expected: `tmj edit OK`.

Then check the diff is surgical: `git diff --stat godot-generative-agents/godot/maps/upenn_core_urban.tmj` — expected: 1 file, small line count (the one data line + ~40 inserted lines + 2 counter lines). Spot-check with `git diff godot-generative-agents/godot/maps/upenn_core_urban.tmj | head -80`: no reformatting outside the three regions.

- [ ] **Step 4: Update the furniture catalog**

In `tools/geo/furniture_catalog.json` (JSON data file — edit the two entries under `"objects"`, keep everything else byte-identical):

- `"stove"`: set `"col": 6, "row": 23, "w": 1, "h": 2`, `"label": "kitchen stove / oven, dark counter range"`, `"verified": true` (the old (8,24) coords were a mislabeled prep counter with a food bowl).
- `"pot"`: set `"verified": true` (eyeballed 2026-07-09: round open cooking pot).

- [ ] **Step 5: Regenerate the script-owned CSVs**

In pipeline order, from the worktree root:

```bash
uv run python tools/geo/block_furniture.py     # expected: "sealed 4 furniture tiles" (the four y=248 bodies; y=247 cells are already walls)
uv run python tools/geo/add_game_objects.py    # expected: "painted 22 game objects (22 cells)" and 22 rows written
uv run python tools/geo/validate_tmj.py        # expected: all checks pass, exit 0
```

Verify the matrix diff is exactly ours:

```bash
git diff --stat godot-generative-agents/backend/penn/the_upenn/matrix/
```

Expected: exactly 3 files — `collision_maze.csv` (4 cells 0→1), `game_object_maze.csv` (3 cells 0→goid), `game_object_blocks.csv` (+3 rows: `114000, UPenn, Houston Hall, 1014, sink` / `114001, ..., stove` / `114002, ..., pot`; the 19 Fisher rows byte-identical). If `collision_maze.csv` or `game_object_maze.csv` shows changes beyond those cells, STOP and report — the baseline assumption broke.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_houston_objects.py tools/geo -q`
Expected: all pass, including both Step-1 tests.

- [ ] **Step 7: Full suites + format, then commit**

Run: `uv run pytest godot-generative-agents/tests -q` (all pass) and `uv run black --check .` (clean). Confirm `git status` shows NO `.bak` file staged (it must stay untracked).

```bash
git add godot-generative-agents/godot/maps/upenn_core_urban.tmj \
        tools/geo/furniture_catalog.json \
        godot-generative-agents/backend/penn/the_upenn/matrix/maze/collision_maze.csv \
        godot-generative-agents/backend/penn/the_upenn/matrix/maze/game_object_maze.csv \
        godot-generative-agents/backend/penn/the_upenn/matrix/special_blocks/game_object_blocks.csv \
        godot-generative-agents/tests/test_houston_objects.py \
        tools/geo/test_add_game_objects.py
git commit -m "feat(map): Houston Hall boil-water kitchen strip + game_object tier (#466)"
```

---

### Task 3: Smoke test, visual check, push, PR

**Files:** none committed (verification + PR). One scratchpad render script.

- [ ] **Step 1: Headless smoke test**

Run: `./godot-generative-agents/run_smoke_test.sh`
Expected: exit 0 (every scene loads, campus map painted). Requires Godot 4.6 on PATH or in the standard macOS app bundle; if Godot is unavailable in this environment, report that explicitly rather than skipping silently.

- [ ] **Step 2: Render the kitchen strip for the visual check**

Write to the scratchpad (not committed) and run:

```python
#!/usr/bin/env python3
"""Composite the Houston lobby corridor from the tmj so the new props can be
eyeballed without launching Godot (#466)."""
import json

from PIL import Image

TMJ = "godot-generative-agents/godot/maps/upenn_core_urban.tmj"
MAPS = "godot-generative-agents/godot/maps"
X0, Y0, X1, Y1 = 110, 243, 130, 252  # corridor window around the strip

tmj = json.load(open(TMJ))
W = tmj["width"]
sheets = []
for ts in sorted(tmj["tilesets"], key=lambda t: t["firstgid"]):
    img = Image.open(f"{MAPS}/{ts['image'].split('/')[-1]}").convert("RGBA")
    sheets.append((ts["firstgid"], ts["columns"], img))

def blit(canvas, gid, dx, dy):
    first, cols, img = next(
        (f, c, i) for f, c, i in reversed(sheets) if gid >= f
    )
    n = gid - first
    sx, sy = (n % cols) * 16, (n // cols) * 16
    canvas.alpha_composite(img.crop((sx, sy, sx + 16, sy + 16)), (dx, dy))

canvas = Image.new("RGBA", ((X1 - X0) * 16, (Y1 - Y0) * 16), (30, 30, 30, 255))
for L in tmj["layers"]:
    if L.get("type") != "tilelayer":
        continue
    for y in range(Y0, Y1):
        for x in range(X0, X1):
            gid = L["data"][y * W + x]
            if gid:
                blit(canvas, gid & 0x0FFFFFFF, (x - X0) * 16, (y - Y0) * 16)
out = canvas.resize((canvas.width * 5, canvas.height * 5), Image.NEAREST)
out.save("<scratchpad>/houston_kitchen_render.png")
print("render OK")
```

Run: `uv run --with pillow python <scratchpad>/render_houston.py`
Expected: `render OK`. Report the output path — the controller views the image (sink / counter / stove / pot-on-counter along the north wall, corridor row below them clear).

- [ ] **Step 3: Full suites once more**

```bash
uv run pytest tools/geo -q                        # expected: all pass
uv run pytest godot-generative-agents/tests -q    # expected: all pass
uv run pytest tests -q                            # expected: all pass (root suite; matrix data feeds backend tests)
uv run black --check .                            # expected: clean
```

- [ ] **Step 4: Push and open the PR**

```bash
git -c credential.helper='!gh auth git-credential' push -u https://github.com/ccb/agent-sandbox.git feat/houston-objects-466

gh pr create --repo ccb/agent-sandbox --base godot-ga-main \
  --title "feat(map): Houston Hall boil-water props — sprites + game_object tier (#466)" \
  --body "$(cat <<'EOF'
Implements #466 per the approved spec
(`godot-generative-agents/docs/specs/2026-07-09-houston-boilwater-props.md`)
— the matrix half of #300 (the engine-item half is PR #465; the two are
independent and share no files).

- **Sprites:** a kitchen strip on the Houston Hall lobby corridor's north
  wall — pedestal sink, counter, stove/oven, cooking pot on a counter —
  painted into the existing `houston_furniture` layer by a surgical text
  edit that preserves the committed Tiled-pretty formatting (the geo
  scripts serialize minified, so no script regen of the tmj).
- **Addresses:** a new `houston_objects` objectgroup (3 use-tile rects) +
  `add_game_objects.py` generalized from the hardcoded `fisher_objects`
  layer to scanning every `*_objects` layer, with **per-sector** id
  numbering so buildings never renumber each other (Fisher's 19 objects
  stay byte-identical — pinned by a new regen-consistency test).
  `UPenn:Houston Hall:lobby:{sink,stove,pot}` now resolve to walkable
  use-tiles (ids 114000-114002), pinned by a new WorldMap test.
- **Collision:** exactly 4 deliberate seals (the strip's floor-row bodies);
  use-tiles stay walkable; `validate_tmj.py` fully green (orphans,
  use-tile walkability, containment, reachability).
- **Catalog:** `furniture_catalog.json`'s `stove` entry repointed to the
  real range tile at franuka (6,23) — the old (8,24) coords were a
  mislabeled prep counter — and `pot` marked verified after eyeballing.

Routing Sofia's dinner stop to the sink's object address is deliberately
deferred until this and #465 both merge (her stop's YAML lives on #465).

Closes #466. Refs #300, #402, #299.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Notes

- Spec coverage: tile verification (done at plan time, results baked into Global Constraints + catalog task), surgical tmj edit (Task 2 Step 3), tool generalization + Fisher byte-identity (Task 1 + regen-consistency test), CSV regen + validator (Task 2 Step 5), WorldMap resolution test (Task 2 Step 1), smoke + visual + suites (Task 3). Sofia routing and cup sprites: explicitly out of scope (spec non-goals).
- The regen-consistency test passes both before Task 2 (Fisher-only) and after (Fisher+Houston), and fails only in an inconsistent tree — which is why the tmj edit and CSV regen share one commit.
- Type/value consistency: gids 1821/1837/1255/1287/1261/1293/991, cells x=117-120 y=247-249, goids 114000-114002, layer id 124, object ids 285-287, counters 125/288 — identical in Global Constraints, the edit script, and both tests.
