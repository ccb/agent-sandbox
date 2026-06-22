# University Archives Vertical Slice — Design Spec

**Date:** 2026-06-11
**Status:** Approved design (room = University Archives; payoff = contamination chain;
art = warm scholarly library; Approach A — confirmed 2026-06-11).
**Repo policy:** kept local under `docs/superpowers/` (gitignored) — do **not** commit this doc.

## Goal

Add a third playable indoor scene — the Tingen University archive reading room — reusing the
finished IntroRoom/HQ recipe (baked-photo background + invisible `Solids` colliders +
`Interactable` hotspots). The player can wander in from the City hub, talk to an anxious
records clerk, examine a few research points, and — if curious — uncover the notebook's
**contamination chain** (its earlier owners and how each died). The room records what it finds
as clues and surfaces internal thoughts; it **never forces** a next objective. **No new
GDScript** — scene + JSON data + asset work only.

## Narrative context

GDD §6.2.3 frames the University / Archive district as *research*, the *"original incident
root,"* slower tempo with *strong clue density*. The HQ Captain's lead already points here
("Search the Tingen University archives for Antigonus"). The archive pays that off: the player
learns Antigonus was a real figure, discovers a restricted volume is **missing** (a cultist took
it — the clerk is covering for it), and in abandoned marginalia finds the **chain of prior
owners** — Welch and his circle, each driven mad and dead. That chain softly suggests Welch's
lodging as a place the player *could* investigate next. This advances the existing clue chain
rather than inventing a parallel one.

## Approach

**Approach A (chosen):** Reuse the IntroRoom/HQ pattern verbatim; the clerk **Ledger Finch** is
an `Interactable` with `dialogue_id = "finch"` and real character art (exactly how the HQ Captain
works).

- **Rejected B — Finch as a full `NPC.tscn`:** sources its def/dialogue from `NpcDB.gd`
  (animation-agent-owned, off-limits) and hardcodes `icon.svg`, so it renders a placeholder
  square; a schedule inside one static room buys nothing. Higher cost, no benefit.
- **Rejected C — examine-only, no NPC:** simplest, but discards the canon archivist and his
  missing-volume hook — the room's strongest thread.

## Simulation framing (no forced objective)

Per the project's system-driven principle (story doc Part 3) and Mark's explicit steer, the room
**surfaces, never commands**:

- Each examine **collects a clue** (`ClueDB.collect`) and **emits an internal thought**
  (`WorldState.thought_requested`). Both are recorded/transient — not gates.
- The Welch's-lodging thread is delivered as a **thought only**. The room makes **no
  `set_lead` / `lead_on_use` call** — it does not overwrite the player's tracked lead with a
  "go to Welch" objective. (If we later want a soft HUD line, it stays phrased as a *possibility*,
  decided at review — default is thought-only.)
- The City→University door is just there to enter or ignore; nothing pushes the player through it.

## Connectivity (City hub)

- **City.tscn:** add one `UniversityDoor` `Interactable`
  (`target_scene = res://scenes/UniversityArchive.tscn`, `prompt_text = "Enter the University
  archive"`) at a free spot not overlapping existing nodes (exact position chosen at build;
  current occupied points: Player 600,400 · Nighthawk 820,320 · HQDoor 300,500 · Orin 400,240 ·
  Dalia 820,220).
- **UniversityArchive.tscn → City:** the exit door targets `City.tscn`; return spawn = City's
  default player position (acceptable for the slice).
- **IntroRoom.tscn / NighthawksHQ.tscn are NOT modified.**

## Scene tree — `scenes/UniversityArchive.tscn` (mirrors NighthawksHQ)

- Root `Node2D`, `y_sort_enabled = false`.
- `Background` `Polygon2D` (dark fill).
- `RoomPhoto` `Sprite2D`: `texture = assets/backgrounds/university_archive.png`,
  `centered = false`, `scale` set so the room fills the same on-screen play box as the HQ
  (factor measured from the PNG's native size at build; HQ used `0.5833` for a 1536×1024 source).
- `Solids` `StaticBody2D`: 4 wall `CollisionShape2D` boxes over the painted walls + furniture
  footprints (the wall-lining bookshelves/stacks, the central reading tables, the card-catalog
  cabinet, Finch's desk, and a small box under Finch's feet). Target **≥8 shapes** (final count
  measured against the photo via the collider-overlay harness).
- `Finch` (`Interactable`): `icon = assets/characters/archive_clerk_finch.png`, `icon_px`
  ~90 (tuned in playtest; match Klein's ~76px on-screen), `dialogue_id = "finch"`,
  `prompt_text = "Speak to the records clerk"`. Positioned at his desk.
- `CardCatalog` (`Interactable`): invisible examine hotspot (`tint` alpha 0) over the painted
  catalog cabinet; `clue_id = "archive_antigonus"`; `thought` flavor (Antigonus is real; the call
  number is here but the book is not).
- `RestrictedShelf` (`Interactable`): invisible hotspot over a wall shelf with a visible gap;
  `clue_id = "restricted_volume_missing"`; `thought` flavor (fresh dust-shadow; taken just ahead
  of the player).
- `ReadingDeskNotes` (`Interactable`): invisible hotspot over a reading table with abandoned
  papers; `clue_id = "contamination_chain"`; `thought` flavor (Welch & circle, each mad then
  dead; the list ends at Welch's lodging — *the soft "could-do"*).
- `Door` (`Interactable`): invisible hotspot over the painted exit;
  `prompt_text = "Leave — back to the quad"`, `target_scene = res://scenes/City.tscn`.
- `RoomCam` `Camera2D` (centered, `zoom` ~1.2 like the HQ).
- `Player` instance: spawn near the entrance; `Sprite2D` scale `0.073` (match HQ); Player's own
  `Camera2D` disabled (RoomCam drives the view).
- `Hint` `Label` (top): "WASD / Arrows to move   .   E to interact".

## Data additions

### `data/clues.json` — add four clues (schema matches existing; enums in use: `type` ∈ behavioral/occult/physical/testimony, `importance` ∈ pivotal/supporting)

```json
{ "id": "archive_antigonus", "name": "Antigonus in the Catalogue",
  "description": "The card catalogue confirms Antigonus was real — a long-dead devotee whose key volume has a call number but no book on the shelf.",
  "type": "occult", "importance": "supporting", "location": "university_archive",
  "topics": ["antigonus_notebook", "the_university"], "linked_entities": ["antigonus"] }

{ "id": "restricted_volume_missing", "name": "The Missing Volume",
  "description": "The restricted shelf has one empty slot, its dust-shadow still fresh. Someone removed Antigonus' volume only recently.",
  "type": "physical", "importance": "supporting", "location": "university_archive",
  "topics": ["antigonus_notebook", "the_theft"], "linked_entities": ["ledger_finch"] }

{ "id": "contamination_chain", "name": "The Chain of Owners",
  "description": "Abandoned marginalia traces the notebook through Welch and his circle — each reader driven mad, then dead. The list ends at Welch's lodging.",
  "type": "testimony", "importance": "pivotal", "location": "university_archive",
  "topics": ["antigonus_notebook", "the_contamination"], "linked_entities": ["welch"] }

{ "id": "finch_cover", "name": "The Clerk's Excuse",
  "description": "The records clerk insists the restricted volume is 'out for rebinding' — a shade too quickly. He is covering for its disappearance.",
  "type": "testimony", "importance": "supporting", "location": "university_archive",
  "topics": ["the_theft"], "linked_entities": ["ledger_finch"] }
```

### `data/dialogue.json` — add `"finch"` (PLACEHOLDER tree; LLM-driven later)

A ~4-node tree (literal JSON authored in the implementation plan):

- **root** — Finch, jumpy, asks if the player needs the records desk. Options: "Anything on
  Antigonus?" → `antigonus`; "What happened to the restricted volume?" → `volume`; "(Leave)" →
  `end`.
- **antigonus** — he stiffens: that section is restricted, he "really couldn't say." Back to
  `root`.
- **volume** — he claims it is "out for rebinding," too fast; `effects: [{ collect: finch_cover }]`.
  Back to `root` / "Understood." → `end`.

Not clue-gated; depth is deferred to the LLM agent layer.

## Assets

- **Background (new):** generate `assets/backgrounds/university_archive.png` — top-down warm
  Victorian reading room (dark mahogany shelving lining the walls, tall stacks, green-shaded brass
  lamps, leather books, arched windows, warm candlelight, worn central carpet + reading tables).
  Grounded in the red-brick gothic of `asset-gen/ref/uni.png`. Generated via Mark's
  `generate_tingen_image2.py` (`--treatment topdown`), brightness tuned in post like `hq_interior`,
  then the finished PNG copied into `tingen/assets/`. Iterated on the real Godot render.
- **Finch figure (reuse):** `asset-gen/out/characters/archivist_0.png` is an elderly bespectacled
  scholar in a black Victorian coat — an ideal Finch. Clean the yellow halo backdrop to a clean
  transparent alpha (PIL mask, or regenerate if needed) → `assets/characters/archive_clerk_finch.png`.
- **Portrait (reuse, unused for now):** `asset-gen/out/portraits/portrait_archivist_0.png` exists;
  the `DialoguePanel` is text-only HUD we don't own, so the portrait stays unused this slice.

## Verification (manual-first)

- **Headless wiring test** `tests/test_university_archive.gd` (mirror `test_nighthawks_hq.gd`):
  `RoomPhoto` → `university_archive.png`; `Solids` is a `StaticBody2D` with ≥8 shapes;
  `Finch.dialogue_id == "finch"` and its icon ends `archive_clerk_finch.png`; `CardCatalog`,
  `RestrictedShelf`, `ReadingDeskNotes` present with their `clue_id`s; `Door.target_scene ==
  "res://scenes/City.tscn"`; `RoomCam` is a `Camera2D`; Player sprite → `klein_down.png`; plus
  data asserts: `dialogue.json` parses and has a `"finch"` key; `clues.json` has all four new ids;
  `City.tscn` `UniversityDoor.target_scene` points to `UniversityArchive.tscn`.
- **Collider-overlay harness** (temp): render each `Solids` box translucent over the photo to
  eyeball furniture alignment.
- **Non-headless screenshot harness** (temp): full room + Finch close-up; verify figure
  scale/placement, no floating art, player reaches the talk zone, colliders block.
- **Playtest harness** (temp): proximity detection on each hotspot; talk collects `finch_cover`
  and opens the `finch` tree; each examine collects its clue + surfaces a thought; door requests
  the City transition. All temp harnesses deleted before finishing.

## Files touched — ownership safety

- **CREATE:** `scenes/UniversityArchive.tscn`, `tests/test_university_archive.gd`.
- **EDIT:** `data/dialogue.json` (add `"finch"`), `data/clues.json` (add 4 clues) — neither is on
  the animation-agent-owned list (`items.json` / `action_schema.json` are; these are not).
- **EDIT:** `scenes/City.tscn` (add one optional `UniversityDoor`).
- **ADD ASSETS:** `assets/backgrounds/university_archive.png`,
  `assets/characters/archive_clerk_finch.png` (+ `.import` sidecars generated on first import).
- **Untouched:** `NpcDB.gd`, `Main.tscn`, `ui/HUD.tscn` + sub-scenes, `items.json`,
  `action_schema.json`, and all other animation-agent-owned files. No GDScript changes at all.

## Deferred / future

- **Welch's lodging** scene — the contamination chain's "could-do" target; a later slice.
- Finch becomes LLM-driven (the static `"finch"` tree is a stand-in); add Finch + Welch +
  Antigonus to `npcs.json` for the sim layer.
- Precise return-spawn in City; real City street art.
