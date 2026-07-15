# Spec: Viewer fan-out for co-located agents (issue #560)

**Track:** godot-ga-main (viewer). Related: #537.
**Date:** 2026-07-15

## Problem

In live/replay runs, two or more agents sometimes occupy the **exact same tile**,
so their sprites stack and only the top one is visible. The viewer draws every
sprite at the tile centre (`_tile_to_world(x,y) → ((x+0.5)*tile, (y+0.5)*tile)`,
`viewer.gd:1190`) and positions it each frame with no per-agent offset
(`viewer.gd:1766`, `node.position = pa.lerp(pb, frac)`).

**This is a rendering issue, not a functional one** (verified while scoping #560):
agent interactions key on the engine `Location` (room/arena), never on tile
proximity. Conversation eligibility flows through `maybe_converse` →
`find_conversation_pairs` → `audience_for`, which Penn implements as
"characters in the speaker's perceivable *locations*" (`penn_world.py:237`; the
engine default at `games.py:1077` is "every character in the speaker's location").
There is no view radius or tile-distance check anywhere in the backend. So two
agents on the same tile converse/perceive exactly as they would a few tiles apart —
only the *sprites* overlap. A viewer-side fan-out is therefore the complete fix
(backend occupancy-aware routing was considered and deferred — more work, partial
coverage, and it would perturb the byte-pinned deterministic replay).

## Design

Mirror the #372 thinking-indicator pattern: extract the pure logic into its own
small script and headless-unit-test it, then call it from `viewer.gd`.

### New script: `godot/scripts/agent_fanout.gd`

Pure, dependency-free static functions (no scene/node state), so they unit-test in
isolation:

- `static func groups(tiles: Dictionary) -> Dictionary`
  Input `tiles`: `{name(String): Vector2i}` — each agent's integer tile this step.
  Returns `{Vector2i: PackedStringArray}` — the names sharing each tile, **sorted by
  name** (so an agent's index within its group is stable frame-to-frame,
  independent of iteration order). Tiles with a single occupant may be omitted or
  included; callers only act on groups of size ≥ 2.
- `static func offset(index: int, count: int, tile_px: float) -> Vector2`
  The sub-tile displacement for agent `index` of `count` co-located agents.
  - `count <= 1` → `Vector2.ZERO` (the overwhelmingly common case; no cost).
  - Otherwise a point on a ring: angle `TAU * index / count`, radius
    `min(BASE + STEP * count, CAP)` where the constants are expressed as fractions
    of `tile_px` and `CAP` keeps sprites on/near the tile (≈ `0.35 * tile_px`, i.e.
    ~5–6 px on the 16 px campus tile). Deterministic; same inputs → same point.

### Wiring in `viewer.gd`

In the playback loop (~`viewer.gd:1760`):
1. Once per frame, build `tiles = {name: Vector2i(a.x, a.y)}` from `_frames[i]` and
   call `AgentFanout.groups(tiles)` (preloaded `const`).
2. In the per-name loop, after `agent["node"].position = pa.lerp(pb, frac)`, if the
   agent's tile group has ≥ 2 members, add
   `AgentFanout.offset(index_in_group, group_size, _tile_px)` to `node.position`.
   The sprite, name label, and chat bubble are children of the agent node, so they
   move together.

Grouping is by the **step tile** (`_frames[i]`'s integer coords): settled agents
(the reported symptom — stacked at a shared destination) have a stable tile and get
a stable ring for as long as they're co-located. Transient one-step corridor
crossings are de-overlapped the moment both agents share a step tile.

## Out of scope (YAGNI)

- **Stacked-count badge** — the ring reads fine for the realistic 2–5 co-located
  case; add later only if crowding shows up.
- **Backend occupancy-aware routing** — deferred (see Problem); tracked as a
  possible follow-up if a range-based interaction model ever needs distinct tiles.
- Any change to replay data, the backend, or determinism fixtures.

## Testing

- **`godot/tests/test_agent_fanout.gd`** — headless unit test, same shape as
  `test_thinking_indicator.gd` (`extends SceneTree`, `_check(cond, name)`, prints a
  `test_agent_fanout: all checks passed` sentinel, exit 0). Assert:
  - `offset(0, 1, 16)` == `Vector2.ZERO` (and any `count <= 1`).
  - For `count == 3`: three **distinct** offsets, each `length()` ≤ the cap, roughly
    evenly spaced (pairwise angles ≈ `TAU/3`).
  - `offset` is deterministic (same inputs → equal result).
  - `groups({...})` buckets co-located names together, sorted, and separates
    distinct tiles.
- **`run_smoke_test.sh`** runs the new test and greps its sentinel (add it alongside
  the `test_thinking_indicator.gd` invocation), and still loads every scene (exit 0).
- No Python/backend tests affected; the replay artifact is unchanged.

## Verification

- `test_agent_fanout.gd` passes headless; `run_smoke_test.sh` exits 0 with the new
  sentinel present.
- Manual: launch a replay with a known co-located moment (e.g. a shared destination)
  and confirm N sprites fan into a legible ring, all visible, labels/bubbles moving
  with them; single agents are unmoved (no offset).
- `git status` shows only the new script + test + the `viewer.gd` wiring +
  `run_smoke_test.sh` — no replay/backend files.

## Risks

- **Offset applied to a moving agent looks like drift (low):** the offset is a
  constant per step added to the lerp, so a co-located moving agent's whole path
  shifts by a few px — reads as "walking slightly off-centre," acceptable, and only
  while it shares a tile.
- **Group flicker at step boundaries (low):** an agent's offset can pop when it
  joins/leaves a shared tile between steps; bounded by the small radius and
  unavoidable without smoothing (out of scope).
