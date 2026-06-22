# Tilemap Hub & Walkable World — Design Spec

**Date:** 2026-06-08
**Status:** Approved design (free-roam tilemap + HD-2D cohesion), ready for implementation planning
**Engine:** Godot 4.6 (GDScript; `CharacterBody2D` top-down; `TileMapLayer`)
**Scope:** Replace the placeholder `scenes/City.tscn` with a real **walkable, art-filled
district hub** built from Godot TileMapLayers (floor + per-tile collision), a Y-sorted
object/entity layer, and the existing entity scenes repointed to real sprites. Establish
the pattern on a **Klein's bedroom (IntroRoom) vertical slice**, then stamp it across the
five districts. **Out of scope:** item pickups / inventory (see
`2026-06-08-inventory-system-design.md`), the occult tools + hypothesis board
(`2026-06-06-occult-tools-hypothesis-board-design.md`), the `WorldManager` story/pressure
sim (unchanged), and real pathfinding (NPCs keep their simple waypoint steering).

---

## 1. Intent

The GDD calls for a roamable Tingen the player explores district by district. The engine
*skeleton* for that already exists — `Player.gd` is free-roam 8-direction top-down with a
smoothed follow camera, NPCs walk `Clock`-phase waypoints, and the dialogue / clue / board /
district-map systems run — but the **spatial layer is entirely placeholder**: `City.tscn`
is two flat `Polygon2D` rectangles plus a "stub city scene" label, every sprite is the
default `icon.svg` tinted via `modulate`, and none of the 91 generated assets are imported
(`tingen/assets/*` is empty).

This spec turns that stub into a real walkable hub and wires the art in, per the chosen
movement model: **free-roam tile maps** — real TileMapLayers with per-tile collision and
Y-sorted objects (Stardew-style roaming) — with the painted gpt-image-1 backgrounds
demoted to **establishing art**, never the walkable floor.

---

## 2. Current state (grounding)

| Concern | Today | Target |
|---|---|---|
| Movement | `Player.gd` free-roam 8-dir + smoothed `Camera2D` ✓ | unchanged |
| Hub geometry | `City.tscn`: 2 flat `Polygon2D` + label | TileMapLayer floor + collision + Y-sorted objects |
| Floor art | solid-color polygon | 7 seamless RD tiles |
| Objects | none | RD props on a Y-sorted layer |
| Player / NPC art | `icon.svg` + `modulate` tint | real anime sprites, Nearest filter |
| Backgrounds | n/a | establishing art (intro card / district map / dialogue backdrop) |
| Districts | 5 polygons in `districts.json` (used by `DistrictMap` UI) | one hub scene per district, same pattern |

---

## 3. Decision & non-goals

**Decision.** Build each district as a Godot **TileMapLayer hub**. Floor and walls are
grid-authored tiles with per-tile collision; scenery + interactables + NPCs + the player sit
on a **Y-sorted** layer so depth/occlusion is automatic; entities use real **HD-2D** sprites
kept crisp over palette-matched pixel tiles. Painted backgrounds are establishing art only.

**HD-2D cohesion (chosen).** The high-fidelity anime character sprites stay sharp and
deliberately "pop" over the 384px pixel-art floor/props (think Octopath Traveler). This is
**reversible**: the hi-fi sprite originals are retained, so a later downscale+quantize pass
can unify everything into one pixel grid if the seam reads wrong once it's in motion.

**Non-goals.** Not isometric — we keep orthographic top-down, matching `Player.gd`. Not
painted-floor hubs (rejected when "free-roam tile maps" was chosen). Not touching
`WorldManager`'s story/pressure sim. Not building inventory/pickup logic (separate spec).
Not real navmesh/A* (NPCs keep `move_and_slide` waypoint steering).

---

## 4. Architecture — the district hub scene

A hub (e.g. `scenes/IronCross.tscn`, generalizing today's `City.tscn`) is a `Node2D` with
`y_sort_enabled = true`:

| Node | Type | Role |
|---|---|---|
| `Floor` | `TileMapLayer` | walkable ground painted from the seamless tiles; **no collision**; drawn lowest |
| `Walls` | `TileMapLayer` | building edges / impassable border; tiles carry **physics collision polygons** |
| `Objects` | `Node2D` (Y-sorted) | props + interactables + NPCs + Player, depth-sorted by Y |
| `DayNight` | `CanvasModulate` (`DayNightTint.gd`) | existing tint, retained |
| `Bounds` | `StaticBody2D` | a few hand-placed colliders for irregular edges the tileset can't express |

**Tileset construction.** One `TileSet` resource, one atlas source per floor texture among
the 7 (`cobblestone_wet`, `brick_alley`, `dead_grass`, `wood_floor`, `archive_carpet`,
`warehouse_concrete`, `ritual_stone`). Each is a **seamless** 384px texture (generated with
`tile_x/tile_y`), so a single atlas tile repeated across `Floor` reads continuous. `Walls`
tiles get a collision polygon in the TileSet physics layer → **per-tile collision for free**,
grid-authored. This is exactly what removes the "hand-drawn polygons over ambiguous painted
geometry" problem that killed the earlier ¾-backdrop approach.

**Y-sort / depth.** `Objects` is Y-sorted: a node lower on screen (greater Y) draws in
front. Each entity/prop `Sprite2D` is **feet-anchored** (sprite offset up by ~half its
height) so the sort key is the figure's feet, and the body collider is a small box at the
feet. Result: the player walks behind a lamppost when above it, in front when below — true
Stardew occlusion, no manual layering.

**Entities (reuse existing scenes).** `Player.tscn`, `NPC.tscn`, `Interactable.tscn` keep
their structure (`CharacterBody2D`/`Area2D` + collider + `TalkArea`/prompt). We only
**repoint `Sprite2D.texture`** to real art, set `texture_filter = Nearest`, fix `scale`, and
resize the feet collider. NPC waypoint walking, talk-prompt areas, and dialogue all keep
working unchanged (`NPC.gd` / `Interactable.gd` untouched).

---

## 5. Asset integration

Copy the needed PNGs from `asset-gen/out*` into `tingen/assets/<category>/` (the project
README's documented drop-in target) so Godot imports them under `res://`, with import
**filter = Nearest** on every sprite/tile. The asset-gen *pipeline* stays external; only the
finished PNGs the game ships get copied in. Mapping for the Klein's-bedroom slice:

| Node | Asset (category/name) |
|---|---|
| Player `Sprite2D` | `characters/player_detective_*` |
| Notebook (Interactable) | `props/antigonus_notebook` |
| Gun (Interactable) | `props/revolver` |
| Mirror (Interactable) | `props/cracked_mirror` |
| Door (Interactable → City) | `props/door_wood` |
| `Floor` | `tiles/wood_floor` (warm interior) |
| `Objects` (furniture) | `props/simple_bed`, `writing_desk`, `bookshelf`, `oil_lamp`, `candle`, `blood_pool` |
| Establishing card | `backgrounds/klein_bedroom` (dialogue / intro backdrop) |

---

## 6. Style cohesion (HD-2D)

The one seam is an anime sprite standing on a pixel floor. Make it read **intentional**:
(a) palette-match the tiles to the STYLE_GUIDE §3 palette so floor and figure share a
cool-muted base + warm-gaslight accent; (b) Nearest-filter the whole frame so it shares one
crunch; (c) scale sprites so a character is ~2–3 floor-cells tall (grounded, not floating).
Escape hatch (reversible): the hi-fi originals are kept, so a downscale+quantize pass can
later snap sprites onto the tile grid for a fully unified pixel look — while inventory /
portrait / cutscene art keeps the hi-fi version regardless.

---

## 7. Vertical slice — Klein's bedroom / IntroRoom (build order)

The `IntroRoom` is already partly built: an 896×560 room with a `StaticBody2D` 4-wall box,
the player, and four wired interactables (Notebook→`antigonus_notebook` clue,
Gun→`spent_revolver`, Mirror→`wrong_reflection`, Door→`City.tscn`). The slice swaps
placeholder flats for real art and populates the canon-warm room — **no NPCs, no new logic.**

1. Copy slice assets into `tingen/assets/`; set Nearest import.
2. Author a one-tile `TileSet` from `wood_floor` (interior floor).
3. Replace the `Floor` `Polygon2D` with a `Floor` `TileMapLayer` of `wood_floor`; set the
   root `y_sort_enabled = true`; add a Y-sorted `Objects` layer. Keep the existing `Walls`
   `StaticBody2D` box (refine inset if needed).
4. Repoint `Player.tscn` `Sprite2D` → `player_detective` (Nearest, feet-anchored, small feet
   collider).
5. Repoint the four interactables' sprites → `antigonus_notebook`, `revolver`,
   `cracked_mirror`, `door_wood`; keep their clue / `target_scene` wiring intact.
6. Populate the warm room as Y-sorted props: `simple_bed`, `writing_desk`, `bookshelf`,
   `oil_lamp`, `candle`; keep the `Bloodstain` as the horror overlay beat (or swap to
   `blood_pool`). Give furniture small collider footprints so the player walks around it.
7. Verify occlusion: the player passes behind the bed/desk when above, in front when below.
8. Use `klein_bedroom` as the establishing / intro backdrop (not the floor).
9. Playtest: roam, collide with walls + furniture, examine all four interactables (clues
   fire), open the door → City. Tune cell size, sprite scale, collider sizes, camera limits.
10. Capture screenshots for review; decide whether the HD-2D seam holds or we pixelate.

---

## 8. Boundaries with other specs

- **Inventory (`2026-06-08-inventory-system-design.md`):** owns *what happens when you pick
  up / use* an item. This spec only *places* props in the world and routes their interact to
  the existing `Interactable`/dialogue or (later) an inventory pickup. Scenery props
  (barrel, crate, shelf, door) are decoration + collision only.
- **Occult tools & board (`2026-06-06-...`):** unaffected; those are UI layers over the hub.
- **DistrictMap UI / `districts.json`:** the 5 district polygons stay the fast-travel /
  overview model; each polygon's "enter" target becomes one of these hub scenes.
  Cross-district travel routing is deferred.

---

## 9. Open questions / deferred

- **Tile cell size** (96 vs 128 vs full-384) — settle empirically at step 9.
- **Wall expression** — how much is tile-collision vs hand-placed `StaticBody2D` for
  irregular building fronts.
- **NPC sprite mapping** — confirm exact filenames for Orin / Dalia / Nighthawk against the
  19-character set (some may need a best-match or a fresh gen).
- **Multi-district stamping & transitions** — turn the slice into a reusable hub template;
  decide how the player moves between districts (DistrictMap warp vs edge exits).
- **Animation** — sprites are single-frame idle for now; walk cycles are later polish.
