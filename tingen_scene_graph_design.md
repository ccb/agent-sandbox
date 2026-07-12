# Scene Graph & Off-Scene Simulation — Design

**Status:** v1 design. Phase 1 (cross-scene NPC traversal) **and** Phase 1.5 (the `RoomView` spawner,
§5) are implemented, plus a working slice of Phase 2: a per-room ground-item store (`RoomItems`, §6),
capacity-gated `gather_item`, and a materials-gated rite — the cult now grabs offerings off a City
supply cache, carries them down to the crypt altar, lays them, and only then can the rite advance.
Verified end-to-end with the live LLM brain (the descent completes only after the offerings are laid).
Still deferred: validated `put_down` as a first-class verb (deposit is folded into `perform_ritual_step`
for now), the off-scene resolution tick (§7), and batch hydration (§8). Companion to
[`tingen_engine_gap_analysis.md`](tingen_engine_gap_analysis.md) (§7.2 "Offscreen resolution") and
`DESIGN_DECISIONS.md §8.6`.

---

## 1. The problem

The renderer is **single-protagonist / single-scene**: [`GameController._swap_world`](tingen/src/GameController.gd)
frees the entire `World` subtree and instantiates the next scene, so only **one room is ever loaded**.
Scene transitions are **player-only** — [`Portal._on_body_entered`](tingen/src/Portal.gd) fires solely
for `is_in_group("player")`.

But the simulation is **many-agent / many-place**: the cult must be able to travel from a warehouse,
through the cathedral, to a crypt altar, and work a rite there — whether or not the player is watching.
The player's real route is two scene swaps:

```
City  --[chapel-steps portal]-->  CathedralNave  --[crypt-door portal]-->  CathedralCrypt
```

Today's MVP **cheats**: `cathedral_crypt` is a single coordinate `(2118, 5015)` on the *City surface*
(the chapel footprint). The cult walks there on the City map and "performs the rite" at that flat point.
They never cross a portal, never load `CathedralCrypt.tscn`, never enter the real crypt. This made the
demo watchable but does not solve cross-scene agency, and it can't ever — portals are player-only and
agents have no representation in a scene that isn't loaded.

## 2. The principle

> **Authoritative state is DATA; a scene (`.tscn`) is a VIEW of that data.**

Rooms, the agents in them, and the objects on their altars all live in a persistent store keyed by
`room_id`, independent of whether the scene is instantiated. A scene is *populated from* that store on
load. Once this holds, **validation and simulation never touch the scene tree**, so they run identically
on-screen and off — which is the whole game.

This is the same discipline as the propose-time hard veto already shipped in the cognition layer
(`agent-sidecar/cognition/governance.py`): `actor_at_rite_site` is a predicate over world *data*, not a
raycast against a loaded node. We generalize that.

## 3. The room graph

```
Room      { id, scene_path, bounds? }
Portal    { from_room, to_room, from_pos, to_pos }   # directed; from_pos in from_room space, to_pos in to_room space
RoomGraph { rooms[], portals[],  next_hop(from, to) -> room_id,  portal(from, to) -> Portal }
```

`next_hop` is a BFS over the portal edges (the graph is tiny — a handful of rooms), precomputed/cached.
v1 hardcodes the cathedral path; later it is **derived from the scenes** by scanning `Portal` nodes
(each `Portal.target_scene` is an edge; its world position is `from_pos`; the target scene's reciprocal
portal gives `to_pos`).

Concrete v1 edges (from the actual `.tscn` portals):

| from | to | from_pos (approx) | to_pos |
|---|---|---|---|
| `city` | `cathedral_nave` | chapel steps ≈ (2118, 5015) | (920, 1180) |
| `cathedral_nave` | `cathedral_crypt` | (1680, 160) | (1260, 200) |
| `cathedral_crypt` | `cathedral_nave` | (1260, 120) | (1680, 320) |
| `cathedral_nave` | `city` | (920, 1200) | (2118, 5120) |

## 4. Agent position becomes `(room, local_pos)`

Today `Agent.position` is a flat City Vector2. It becomes a **room id + a local position within that
room**. `move_to "cathedral_crypt"` resolves the target site to `(room=cathedral_crypt, altar)` and
pathfinds across the graph:

```
move_to(agent, target):
  (troom, tpos) = resolve_site(target)            # site -> (room, local_pos)
  if agent.room == troom:
      step agent.local_pos toward tpos             # existing in-room stepping
  else:
      hop  = next_hop(agent.room, troom)           # the next room on the path
      p    = portal(agent.room, hop)
      if agent at p.from_pos (within a step):
          agent.room      = hop                    # CROSS — a pure data update, no scene load
          agent.local_pos = p.to_pos               # arrive at the far side
      else:
          step agent.local_pos toward p.from_pos   # walk to the portal
```

Crossing a portal is the agent-equivalent of the player's scene transition, but it is **just a data
update** — no `.tscn` is loaded for it. An agent can be deep in the crypt while the player is in City.

## 5. Rendering follows the player's room (spawn / despawn)

The loaded scene is whichever room the player is in (`GameController.current_scene_path`). A room-aware
spawner reconciles bodies each beat:

- **Spawn** an `NPC` body for every agent whose `room == current room` that has no body yet, at its
  `local_pos`.
- **Despawn** the body of any agent whose `room != current room` (it crossed a portal away — it visibly
  walks to the cathedral door and is gone).
- On a scene swap, the new scene starts empty of NPCs and is populated from the agents in that room.

So when the player stays in City, the cult walks to the chapel steps and **vanishes into the cathedral**;
the rite proceeds off-scene in the crypt room; if the player follows through the portals, the cult bodies
spawn in the crypt mid-rite. The visible-convergence demo is replaced by the real, mysterious,
investigation-driven version.

## 6. Per-room object store (Phase 2)

Each room owns its objects as data, not scene nodes:

```
room.objects = { ritual_salt: {zone: altar, qty: 3}, consecrated_chalk: {...}, ... }
```

A step that touches objects is a **validated data transaction**, identical on- and off-scene:

- `pick_up(item)` — preconditions: `agent.room == item.room ∧ agent at item.zone ∧ qty > 0` → decrement
  room qty, increment agent inventory.
- `put_down(item, zone)` — preconditions: `agent.room == zone.room ∧ agent holds item ∧ zone exists` →
  move item the other way.

These predicates are **the same shape as the veto invariants** and read only data, so they validate an
off-scene NPC's step with no scene loaded. `ActionCommit` already does this for `gather_item` against
`Agent.inventory`; Phase 2 keys it on `(room, zone)` and adds the per-room object set. On scene load, the
room's object data is **rendered into** `Prop`/`Interactable` nodes; the scene is a view of the store.

## 7. Off-scene resolution tick (Phase 3) — determinism + idempotency

Rooms the player isn't in still advance, on a bounded catch-up boundary (the gap analysis'
`lastOffscreenTickTurn` / `offscreenTickInterval`):

- **Coarse tier** (what `DESIGN_DECISIONS §8.6` ships today): distant rooms advance by cheap aggregate
  rules (`cult_readiness += stage_coefficient`) — no per-item moves. Cheap, deterministic.
- **Fine tier**: *hot* rooms (the rite site; rooms adjacent to the player in the graph) run the brain at
  a reduced cadence and commit **validated** item transactions to the room store.

The contract the gap analysis names: the tick must be **deterministic** (seeded RNG, persisted seed) and
**idempotent** (re-running a tick across the same turn span cannot double-apply), so that "hydrate on
enter" never conflicts with what already ran. Each room stores `last_resolved_turn`.

## 8. Batch hydration on player enter (Phase 4)

When the player crosses a portal into room R, the engine does **resolve-once-then-render**, not replay:

1. **Fast-forward R** from `R.last_resolved_turn` to the current turn (bounded, deterministic,
   idempotent). R's data now reflects everything its NPCs did while away — items moved, altar prepared,
   rite advanced.
2. **Instantiate `R.scene`** and **populate from data**: spawn NPC bodies for agents in R at their
   `local_pos`; place object nodes from `R.objects`; set room state (e.g. 失控 if corruption crossed).
3. The player sees the **result** — the cult mid-rite at a half-prepared altar — never a cutscene of each
   step.

## 9. What changes where

| Layer | Change |
|---|---|
| **Cognition / veto** (`agent-sidecar`) | Almost none. `move_to {target}` is unchanged; perception gains `room`; `world_state.actor_at_rite_site` is computed in room space. The veto predicates already read data — they port as-is. |
| **Engine / substrate** (Godot) | The work: `RoomGraph`, `Agent.(room, local_pos)`, portal-aware `move_to`, room-aware spawn/despawn, per-room object store, the off-scene tick with its idempotency boundary. |
| **Yumina** | Maps onto the existing `WorldRoom` abstraction (rooms are already first-class in the bridge). The room graph + validated transactions port as the same contract. |

This split is the project's thesis: **cognition is portable; the spatial/render substrate is per-engine.**

## 10. Phased implementation plan

- **Phase 1 — Cross-scene NPC traversal (DONE).** `Agent.room`; a `RoomGraph` for the cathedral path;
  portal-aware `move_to`; `actor_at_rite_site` computed in the crypt room. The cult genuinely walks
  City → Nave → Crypt and works the rite *in* `CathedralCrypt.tscn`. Headless-tested.
- **Phase 1.5 — `RoomView` spawner (DONE).** A room-aware autoload that spawns/follows/despawns NPC
  bodies for tracked agents in the player's *current* room and renders that room's ground items —
  working in both boot modes (Main.tscn's `World` swap and StandaloneBoot's whole-scene swap). Follow
  the cult into the crypt and they're there; the offerings render at the cache and at the altar.
- **Phase 2 — Per-room object store + capacity + gather/deposit (PARTIAL — DONE for the rite loop).**
  `RoomItems` ground store (§6); `Agent.carry_capacity` + inventory; `gather_item` consumes from the
  ground (capacity-gated); the rite requires the offerings *deposited* at the altar
  (`SummoningPlan.ritual_requirement`/`deposited`) before `advance_rite` bites — deposit is currently
  folded into `perform_ritual_step`. **Ritual offerings can't be foraged** — anything in
  `ritual_requirement` must be picked up off a real `RoomItems` pile (no fabricating it from thin air),
  so the gather→carry journey is mandatory and emptying the cache genuinely starves the rite (the
  player can sabotage it). Non-ritual items still forage (per-agent fieldwork). **Still TODO:** a
  first-class validated `put_down` verb, and keying the store on `(room, zone)` with on-load
  reconciliation for arbitrary props.
- **Phase 3 — Off-scene resolution tick** (coarse + fine tiers, determinism/idempotency). §7.
- **Phase 4 — Batch hydration on enter.** §8.

## 11. Open questions

1. **Derive the room graph from scenes vs hardcode?** Phase 1 hardcodes the cathedral path; deriving it by
   scanning `Portal` nodes is cleaner but needs each scene's reciprocal portal positions. Lean: derive in
   Phase 2.
2. **Do off-scene cultists still need LLM calls, or a cheap scripted "advance the rite" behavior when no
   player can observe them?** Cost vs fidelity — probably scripted-coarse until the player is one room
   away, then fine. (§7 two-tier.)
3. **Does despawning the cult from the City surface hurt the demo's readability?** It's more faithful but
   less immediately legible. A compromise: surface *clues* (a Nighthawk reports "robed figures entered the
   cathedral") so the player has a trail. (Pairs with the rumor system.)
