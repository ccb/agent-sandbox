# Seal `entrance_floor` on `FORCED_CLOSED` + ghost-door guard (#556)

**Issue:** #556 · **Branch:** `feat/entrance-floor-seal-556` off `godot-ga-main` ·
**Review track:** godot-ga-main (geo tooling + map + geo tests).
**Related:** #270 / PR #468 (Van Pelt entrance routing — introduced the hand-seal
this makes reproducible).

## Goal

`add_entrances.py`'s `FORCED_CLOSED` seals a door in the **collision matrix**
only, never repainting the `entrance_floor` **tile layer**. So a re-carved door
stays drawn *open* (`FLOOR` = 621) while being un-walkable (`collision = 1`) — a
cosmetic "ghost door" — and any hand-seal of the tile is **reverted on the next
regen** (which is how a manual pipeline re-run just re-opened Van Pelt's east
door). Fix the tool so closing a door also repaints its tile, repair the one
ghost door already committed (Sweeten Alumni), and add a `validate_tmj.py` guard
so this drift class fails CI instead of lurking.

## Current state (verified)

- **`FORCED_CLOSED`** (`add_entrances.py:142`) maps building name → set of
  perimeter cells to keep walled past the auto-carved door. Applied at
  `add_entrances.py:835-836` as `collision[fy*W+fx] = "1"` — collision only.
- **`entrance_floor`** tile data (`floor`) is painted with the `FLOOR` (621,
  open) / `WALL` (543, closed) gid constants (`add_entrances.py:103-104`,
  `:441-445`); `FORCED_CLOSED` never touches it. The layer is rebuilt each run
  by `strip_entrance_layers` + `insert_entrance_layers` (`:405-429`).
- **Committed-map consistency at every `FORCED_CLOSED` cell** (checked against
  the live `collision_maze.csv` + committed tmj):
  - `Sweeten Alumni Building (46,99)`: `entrance_floor=621`, `collision=1` →
    **GHOST DOOR** (drawn open, sealed). Live in the committed map now.
  - `Van Pelt Library (156,56/57/58)`: `entrance_floor=543`, `collision=1` →
    consistent (the #270 hand-seal).
- **`validate_tmj.py`** is a checker class: check methods append
  `Finding(severity, category, building, code, message)`; `errors()` are the
  `severity=="error"` findings; `main` exits non-zero on un-baselined errors. It
  reads `self.w.tile_layers["entrance_floor"]` and `self.w.collision`. The geo
  CI drift-gate runs it plus the `tools/geo/` pytest suite.
- **Minify hazard:** `add_entrances.py` writes the tmj minified; the repo tracks
  Tiled-pretty. Never commit a regen — edits to the committed tmj are surgical.

## Design

Three coordinated changes.

### 1. `add_entrances.py` — repaint on close

Where `FORCED_CLOSED` seals collision, also set the `entrance_floor` tile to
`WALL`. Concretely, the loop that today does:

```python
for fx, fy in FORCED_CLOSED.get(name, set()):
    collision[fy * W + fx] = "1"
```

also assigns the entrance_floor `floor` array `floor[fy * W + fx] = WALL` at the
same cells (uses the existing `WALL`/`FLOOR` constants — no hardcoded gid), so a
closed door is drawn as wall and matches its collision. The exact insertion
point threads `floor` into scope alongside the `FORCED_CLOSED` application (the
plan pins it); the invariant is: **after processing a building, every
`FORCED_CLOSED` cell has `floor==WALL` and `collision=="1"`.** This makes a regen
idempotent for those cells (no more reverting hand-seals).

### 2. Committed tmj — surgical seal of Sweeten Alumni (46,99)

Repair the one committed ghost door: `entrance_floor` at `(46,99)` 621 → 543,
applied **by hand to the pretty tmj** (the surgical approach #270 used for Van
Pelt — the writer minifies, so a regen is not committable). Van Pelt is already
consistent → no change there. After this edit the committed map has no ghost
doors, so the guard (§3) passes clean.

### 3. `validate_tmj.py` — ghost-door guard

A new check method: for every cell drawn as `FLOOR` (621) in `entrance_floor`
whose `collision` is `1`, append an `error` Finding (category e.g.
`entrance_floor`, code e.g. `ghost_door`, message naming the cell). This is the
**one direction that is a real defect** (drawn-open but sealed). The reverse
(walkable cell not drawn as `entrance_floor` floor) is deliberately **not**
checked — legitimately-walkable cells get their floor art from other layers, so
the reverse would false-positive. Runs in the existing drift-gate; passes on the
committed map after §2.

## Verification

- **Geo pytest** (`tools/geo/`):
  - Repaint: after running the `FORCED_CLOSED` step on the real inputs (or a
    small fixture), assert a `FORCED_CLOSED` cell has `entrance_floor` `floor`
    == `WALL` **and** `collision` == `"1"` (extends the Van Pelt geo tests, e.g.
    `test_van_pelt_asset.py`, or a focused new test).
  - Guard: a synthetic tmj with a `FLOOR`-drawn cell at a `collision==1` position
    yields a `ghost_door` error Finding; a consistent one yields none
    (`test_validate_tmj.py`).
- **Real map:** `validate_tmj.py` on the committed tmj exits 0 (no un-baselined
  errors) after the Sweeten seal; `add_entrances.py` re-run no longer flips the
  `entrance_floor` door cells (idempotent for Sweeten + Van Pelt), confirmed via
  a JSON-normalized content compare of the door cells. **Revert the minified
  regen afterward** — the tmj's only committed change is the 1-cell Sweeten seal.
- **Commit discipline:** commit the `add_entrances.py` change, the
  `validate_tmj.py` guard + its test, the repaint test, and the surgical 1-cell
  tmj seal. Do **not** commit a regenerated (minified) tmj; the collision matrix
  is unchanged by this work, so no matrix regen is expected.
- **Full geo suite** + `uv run black .`.

## Out of scope

- The layer-id churn (`insert_entrance_layers` assigns `max(id)+1` each run) —
  regen-only noise; regens aren't committed, and the guard checks committed
  content, not regen byte-identity.
- Teaching the tmj writer to pretty-print (would remove the surgical-edit dance;
  separate concern).
- Any change to collision/matrix content, other buildings' doors, `FORCED_DOORS`,
  or the sim.
