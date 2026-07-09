# Van Pelt Library: route the entrance to the labeled `Entrance` room (#270)

Follow-up to `furnish-van-pelt-interior.md`, which deferred this decision to #270
("Entrance reconciliation"). The hard requirement from that spec stands: **every
one of the 25 Van Pelt room arenas (`13000`–`13024`) must stay BFS-reachable from
the building's entrance.**

## Problem

`add_entrances.py` auto-carves Van Pelt's door where a campus footway meets the
wall — which lands on the **east** perimeter, opening straight into the **Moelis
Family Grand Reading Room** (a room *inside* Van Pelt occupying the east flank,
`x 139–155, y 31–66`). So an agent entering "Van Pelt Library" materializes in the
middle of the grand reading room at the far east, rather than at the hand-designed
front **`Entrance`** room (bottom-center, `x 95–136, y 60–65`), which today has no
opening to the outside. This is wrong both visually (a doorway punched through a
study hall's east wall) and semantically (the front door is ignored).

Footprint (sector `30`): `x 17–157, y 17–68`; south perimeter row `67–68`.

## Decision

**Single front entrance.** Add a door in the **south** perimeter at the `Entrance`
room and **seal** the auto-carved east door. Chosen over "keep the east door as a
side entrance" because the east opening is a hole in a reading room's wall, not a
real entrance, and the parent spec calls for reachability from "the single building
entrance." (Approved in brainstorming, 2026-07-09.)

## Approach

No new machinery — reuse the existing per-building overrides in `add_entrances.py`,
exactly as the Sweeten Alumni Building already does:

1. **`FORCED_DOORS["Van Pelt Library"]`** — one ~3-cell opening in the south
   perimeter wall under the `Entrance` room. Target cells `{(110,67),(111,67),(112,67)}`;
   the exact set is validated during implementation to (a) be south-perimeter cells
   with walkable interior directly to the north and outside to the south, and (b)
   connect north into the `Entrance` room (`y 60–65`). Derived from the `Entrance`
   rect in `van_pelt_interior.json`, recorded as an explicit cell set with a comment
   (the interior asset is frozen), matching the `FORCED_DOORS` idiom.
2. **`FORCED_CLOSED["Van Pelt Library"]`** — the auto-carved east door's perimeter
   cells, re-sealed after carving. The exact cells are **pinned from pipeline
   output**: run `add_entrances.py`, read the east-wall opening in Van Pelt's
   `collision_maze`, and list those cells (do not guess — `col 155` from the parent
   spec is an interior Moelis cell; the true perimeter is at `x 156/157`).

`FORCED_CLOSED` re-closes after door-carving, so the net effect is: south door open,
east door sealed. Both overrides are deterministic, preserving `add_entrances`'
idempotency.

## Regeneration order

Per `furnish-van-pelt-interior.md` §2 (order matters):

1. `uv run python tools/geo/add_entrances.py`
2. `uv run python tools/geo/furnish_van_pelt.py`
3. Re-bake the bundled replay (mock brain), per the godot README.

Back up the `.tmj` before any script rewrites it (the `backup_tmj` helper does this
automatically).

## Verification

- `uv run pytest tools/geo/test_van_pelt_arenas.py` — 25 arenas present with the
  expected ids/names, **all 25 BFS-reachable from the single (now south) door**, and
  idempotent (a second `add_entrances` run is byte-identical).
- `uv run python tools/geo/validate_tmj.py` — the `tmj ⇄ matrix` drift gate wired
  into CI in #421.
- Headless Godot eyeball of the entrance region (cols 17–157 / rows 17–68) — the
  second deferred item from #268: the south doorway reads as a front door and the
  old east opening is gone.

## Risks & safety net

- **Stranding the Moelis room by sealing the east door.** Moelis connects to the
  rest of the interior through designed partition doorways, so sealing the *exterior*
  east door should not isolate it — but if it did, `add_entrances`' existing
  `_punch_doorway` opens an interior partition doorway, and `test_van_pelt_arenas`'
  reachability assertion would fail loudly rather than silently ship a dead room.
- **South door not connecting to the `Entrance` room.** If the cell directly north of
  the chosen door column is a partition wall rather than walkable floor, the door
  won't reach the Entrance. Mitigation: validate the connection against the
  `collision_maze` when pinning the cells; shift columns within the Entrance x-span
  if needed.

## Acceptance (from #270)

- Entering Van Pelt deposits the agent in / adjacent to the `Entrance` room.
- `test_van_pelt_arenas.py` still passes (all rooms reachable).
- Headless in-Godot view of the entrance region looks right.
