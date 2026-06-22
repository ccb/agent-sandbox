# Old Neil's Home — Design Spec

**Date:** 2026-06-17
**Status:** Approved design (room = Old Neil's home/workshop; character = canon Old Neil,
a NEW character separate from the roster's "Old Neille"; two states **normal ↔ 失控**;
**Approach A** — one scene, live state-swap — confirmed 2026-06-17).
**Repo policy:** kept local under `docs/superpowers/` — do **not** commit this doc (matches
the existing HQ / University specs).

## Goal

Add a playable indoor scene — **Old Neil's home/workshop** — that renders in two
simulation-driven states (a grieving alchemist's parlor, and the blood-and-flesh **失控**
aftermath) and can **swap live** while the player is present. Reuses the finished
IntroRoom / HQ / Archive recipe (baked-photo background + invisible `Solids` colliders +
`Interactable` hotspots), plus **one small new script** (`RoomState.gd`) to drive the
state swap. The room **surfaces clues and thoughts, never forces an objective**.

The room's "purpose" is **emergent, not scripted**: Old Neil is a goal-driven agent (revive
Celeste), and 失控 is what that pursuit becomes under pressure. v1 ships the playable
two-state shell plus a simple state hook; the full LLM-agent layer is deferred.

## Canon context (LotM) — factual summary

Old Neil is a Tingen Beyonder who spent ~20 years trying to resurrect his fiancée
**Celeste**, who died of illness. The **Hidden Sage** (a Sequence 0 of the Mystery Pryer
Pathway) taught him a forbidden resurrection method — **"Alchemical Life"** — which needs
large amounts of fresh human blood; to stay humane he drained and stored *his own* blood
over the years rather than kill anyone. He never fully grasped the method; the player /
Klein's advancement pressures him to rush, the Hidden Sage's corruption takes hold, and he
**loses control (失控)**, becoming a monster. Captain Dunn Smith mercy-kills him while he
is still lucid. (Anime Ep. 9.)

Naming note: the contamination-chain figure "Welch" is a **game invention** (not canon);
**Old Neil is canon**. The day-roster's **"Old Neille"** (newspaper hawker, rumor node,
[tingen_npc_roster.md:54](../../../tingen_npc_roster.md)) is a *separate, ordinary*
character — this scene is the canon alchemist, added as his own person/location.

## Simulation framing (not a thread)

Per the project's system-driven principle (and Mark's explicit steer), this is a simulation
of goal-oriented agents, not a clue thread:

- The room **reflects Old Neil's agent state** — normal while he grieves and works, 失控
  once his pursuit collapses under pressure.
- Each examine **collects a clue** (`ClueDB.collect`) and **emits an internal thought**
  (`WorldState.thought_requested`) — recorded/transient, never gates.
- The room makes **no `set_lead` / forced objective**. Whatever the player finds is whatever
  the agent did.
- v1 ships the two-state shell + a simple state hook; the full LLM-driven Neil is deferred.

## Approach

**Approach A (chosen):** a single `NeilHome.tscn` whose state is driven by a small
`RoomState.gd`. This is the only option that lets the room **transform live** (watch Neil
lose control at the piano in front of you) — the moment the scene exists for.

- **Rejected B — two separate scenes** (`NeilHomeNormal` / `NeilHomeLostControl`, chosen at
  entry): zero in-scene logic, but duplicated colliders/props and **no live transformation**.
- **Rejected C — one background + toggleable gore overlay**: cheapest art, but can't deliver
  the **whole-room-transformed** look the 失控 reference sells.

## State mechanic

- `room_state` enum: `normal` | `lost_control`.
- **`src/RoomState.gd`** (new, small, parameterized via exports so it can be reused for future
  variant rooms): on `room_state` change it (1) swaps `RoomPhoto.texture`
  (`neil_home_normal` ↔ `neil_home_lost_control`), (2) swaps Old Neil's sprite
  (gentleman ↔ monster), (3) shows/hides a `LostControl` node group (gore decals + monster).
- **v1 trigger:** `room_state` is settable from the **dev console**, and also flips to
  `lost_control` when `WorldState.corruption ≥ LOST_CONTROL_THRESHOLD` (default `60.0`,
  tunable). Both demoable and headless-testable. The architecture supports a live flip while
  the player is in the room.
- **Deferred:** the *real* agent-driven trigger (Neil's own corruption rising as he's
  pressured), wired when the agent layer lands.

## Scene tree — `scenes/NeilHome.tscn` (mirrors NighthawksHQ + the state script)

- Root `Node2D` with `RoomState.gd`.
- `Background` `Polygon2D` (dark fill).
- `RoomPhoto` `Sprite2D`: `texture = assets/backgrounds/neil_home_normal.png`,
  `centered = false`, scale tuned so the room fills the same play box as the other interiors
  (measured at build).
- `Solids` `StaticBody2D`: wall boxes + furniture footprints (Celeste's piano, Neil's
  desk/workbench, alchemy apparatus, shelving). Target **≥8 shapes** (tuned via the
  collider-overlay harness). Colliders stay identical across states (same footprint).
- `OldNeil` (`Interactable`): `icon = assets/characters/old_neil.png`, `dialogue_id =
  "old_neil"`, `prompt_text = "Speak to the old alchemist"`. At the piano / his desk.
- `LostControl` (Node2D group, hidden in `normal`): `NeilMonster` `Sprite2D`
  (`neil_monster.png`) + gore overlay decals. Shown only in `lost_control`.
- Examine hotspots (invisible `Interactable`s, `tint` alpha 0; each collects a clue + emits a
  thought):
  - `CelestePiano` → `clue_id = "celeste_grief"` (her portrait above the piano; the dead
    fiancée; the whole room is a shrine to her).
  - `BloodVials` → `clue_id = "stored_blood"` (rows of his own stored blood — he bled himself
    to spare others).
  - `RitualDiagram` → `clue_id = "alchemical_life_ritual"` (the Hidden Sage's forbidden
    Alchemical-Life method).
  - `LettersDesk` → `clue_id = "neils_obsession"` (20 years of letters to Celeste; failed
    attempt after attempt).
- `Door` (`Interactable`): `prompt_text = "Leave"`, `target_scene = res://scenes/City.tscn`.
- `RoomCam` `Camera2D` (centered, zoom ~1.2 like the other interiors).
- `Player` instance near the entrance; Player's own `Camera2D` disabled (RoomCam drives view).
- `Hint` `Label` (top): "WASD / Arrows to move   .   E to interact".

## Data additions

### `data/clues.json` — add four clues (schema matches existing; `type` ∈
behavioral/occult/physical/testimony, `importance` ∈ pivotal/supporting/flavor)

- `celeste_grief` — testimony/supporting — "Every surface is a shrine to a woman named
  Celeste. Old Neil never stopped mourning her."
- `stored_blood` — physical/supporting — "Racks of carefully dated vials — his own blood,
  drawn in small amounts over years. He bled himself rather than anyone else."
- `alchemical_life_ritual` — occult/pivotal — "A forbidden 'Alchemical Life' diagram, copied
  from something that calls itself the Hidden Sage. A method to make the dead live again."
- `neils_obsession` — testimony/supporting — "Twenty years of letters to Celeste, each
  describing another failed attempt. The hope curdles into something that isn't sane."

`linked_entities`: `old_neil` / `celeste`. `topics`: `old_neil`, `the_resurrection`.

### `data/dialogue.json` — add `"old_neil"` (PLACEHOLDER tree; LLM-driven later)

A short tree (normal state): a courteous, grief-worn old man, evasive about his "work".
Topics: about Celeste; about what he's building; about the player intruding. Not clue-gated;
depth deferred to the agent layer.

### `data/npcs.json` — **deferred**

Old Neil's full agent record (`day_identity`, `public_goal`, `secret_goal = "revive Celeste
via Alchemical Life"`, `reveal_trigger = corruption / 失控`, `combat_form = neil_monster`)
lands with the sim layer — and only after confirming `npcs.json` is not on the
animation-agent-owned list. v1 uses the `Interactable` + dialogue approach (like Finch).

## Assets (generated via the pipeline; the fan-art 失控 reference is *inspiration*, output is original)

- `assets/backgrounds/neil_home_normal.png` — top-down melancholic parlor/workshop: Celeste's
  **piano** + her portrait, alchemy apparatus, racks of vials, worn elegance, candlelight,
  muted cold palette, quiet dread.
- `assets/backgrounds/neil_home_lost_control.png` — the same room transformed: blood-flooded
  floor, the Alchemical-Life horror, the piano drowned in red — grounded in the provided 失控
  reference, generated original. The **piano is the anchor** that reads across both states.
- `assets/characters/old_neil.png` — an aged, refined, sorrowful gentleman-alchemist.
- `assets/enemies/neil_monster.png` — the 失控 form (skull-and-tendril horror).

Top-down treatment matching the other interiors; brightness tuned in post; iterated on the
real Godot render.

## Connectivity (City hub)

- **City.tscn:** add one `NeilHome` door `Interactable` (`target_scene =
  res://scenes/NeilHome.tscn`) at a free spot. Exact map placement of the building is
  **deferred**.
- **NeilHome → City:** the `Door` targets `City.tscn`.
- Transitions route through **`WorldState.request_transition`**, so they work both under
  `Main` (HUD persists) and standalone (F6).

## Verification (manual-first)

- **Headless wiring test** `tests/test_neil_home.gd` (mirror `test_nighthawks_hq.gd`):
  `RoomPhoto` default → `neil_home_normal.png`; `RoomState` script present; `OldNeil`
  `dialogue_id == "old_neil"` with `old_neil.png` icon; the four hotspots present with their
  `clue_id`s; `Door.target_scene == City.tscn`; `RoomCam` is a `Camera2D`; Player sprite →
  `klein_down.png`. **Plus state-swap asserts:** set `room_state = lost_control` →
  `RoomPhoto` becomes `neil_home_lost_control.png`, `NeilMonster` visible, `OldNeil` sprite
  swapped. Data asserts: `dialogue.json` has `"old_neil"`; `clues.json` has the four ids;
  `City.tscn` `NeilHome` door points to `NeilHome.tscn`.
- **Collider-overlay harness** (temp): translucent `Solids` boxes over the photo.
- **Screenshot harness** (temp): full room + Neil close-up, both states.
- **Playtest harness** (temp): proximity on each hotspot; talk opens `old_neil`; each examine
  collects its clue + thought; door requests the City transition; toggling `room_state`
  transforms the room live. All temp harnesses deleted before finishing.

## Files touched — ownership safety

- **CREATE:** `scenes/NeilHome.tscn`, `src/RoomState.gd`, `tests/test_neil_home.gd`, the four
  asset PNGs (+ `.import` sidecars).
- **EDIT:** `data/clues.json` (add 4), `data/dialogue.json` (add `"old_neil"`), `scenes/City.tscn`
  (add one `NeilHome` door) — none animation-agent-owned.
- **Untouched:** `NpcDB.gd`, `items.json`, `action_schema.json`, `Main.tscn`,
  `ui/HUD.tscn` + sub-scenes. `npcs.json` agent record deferred.

## Scope

- **In:** the scene; two background states + live swap (`RoomState.gd`); Old Neil
  (`Interactable` normal + monster sprite 失控); the four hotspots; door; data; art; headless
  test.
- **Out (deferred):** combat in 失控; Old Neil as a full `npcs.json` LLM agent; the real
  agent-driven 失控 trigger (v1 = dev toggle + corruption threshold); map placement of the
  building; the Celeste resurrection / afterlife payoff.

## Deferred / future

- The full LLM-agent Old Neil (goal = revive Celeste), with the real corruption-driven 失控
  trigger and a Dunn-style mercy-kill beat.
- Combat / confrontation in the 失控 state.
- Map placement of Neil's home on the city map.
- The Celeste payoff (the canon hint that her resurrection ultimately succeeds).
- `old_neil` dialogue becomes LLM-driven (the static tree is a stand-in).
