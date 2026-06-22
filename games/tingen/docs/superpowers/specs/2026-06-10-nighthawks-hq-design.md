# Nighthawks HQ Vertical Slice — Design Spec

**Date:** 2026-06-10
**Status:** Approved design (connectivity + captain-depth forks chosen 2026-06-10).
**Repo policy:** kept local under `docs/superpowers/` (gitignored) — do **not** commit this doc.

## Goal

Add a second playable indoor scene — the Nighthawks' records HQ — reusing the finished
IntroRoom recipe (baked-photo background + invisible `Solids` colliders + `Interactable`
hotspots). The player enters from the City hub, talks to the Nighthawk Captain (a thin
placeholder dialogue for now — LLM-driven later), examines a couple of atmosphere points,
receives the next investigative lead, and leaves. **No new GDScript** — scene + JSON data
+ asset copy only.

## Narrative context

The IntroRoom door's lead is "线索：寻找值夜者 (Find the Nighthawks)." City (Iron Cross
Street stub) already hosts a street Nighthawk who warns the player and collects the
`nighthawk_warning` clue. The HQ is the next beat: the Captain names the threat (Antigonus'
notebook / Church of Evernight) and points the player onward (default: the University
archives). This advances the existing clue/lead chain rather than inventing a parallel one.

## Approach

Reuse the IntroRoom pattern verbatim. **Rejected alternative:** the full `NPC.tscn` node —
it sources its def/dialogue from `NpcDB.gd` (animation-agent-owned, off-limits) and hardcodes
`icon.svg` as its sprite, so it would render a placeholder square, not the captain art. The
`Interactable`-with-`dialogue_id` path (already used by City's street Nighthawk) is lighter,
needs no owned files, and shows the real figure.

## Connectivity (fork: **City hub**)

- **IntroRoom → City:** unchanged (door still targets `City.tscn`).
- **City.tscn:** add one `HQDoor` Interactable (`target_scene = res://scenes/NighthawksHQ.tscn`,
  `prompt_text = "Enter the Nighthawks' HQ"`). Optional: add a one-line `lead` effect to City's
  existing `"nighthawk"` dialogue pointing at the HQ door so the route is legible.
- **NighthawksHQ.tscn → City:** the HQ exit door targets `City.tscn` (you leave the office onto
  the street). Return spawn = City's default player position (acceptable for the slice).
- **IntroRoom.tscn is NOT modified.**

## Scene tree — `scenes/NighthawksHQ.tscn` (mirrors IntroRoom)

- Root `Node2D`, `y_sort_enabled = false`.
- `Background` `Polygon2D` (dark fill, like IntroRoom).
- `RoomPhoto` `Sprite2D`: `texture = assets/backgrounds/hq_interior.png`, `centered = false`,
  `scale` set so the room fills a play box matched to IntroRoom's on-screen scale (exact factor
  measured from the PNG's native size at build time).
- `Solids` `StaticBody2D`: 4 wall `CollisionShape2D` boxes + furniture footprints (filing
  cabinets down both walls, the central tables) + a small box under the Captain's feet so he's
  solid. Target **≥8 shapes** (final count measured against the photo).
- `Captain` (`Interactable`): `icon = assets/characters/nighthawk_captain.png`, `icon_px`
  ~110–130 (tuned in playtest), `dialogue_id = "captain"`, `prompt_text = "Speak to the Captain"`.
  Positioned at the central table.
- `CaseBoard` (`Interactable`): invisible examine hotspot over the back-wall pinned board;
  `thought` flavor (pinned disappearances, a circled warehouse — foreshadow). Optional `clue_id`.
- One cabinet/table examine `Interactable`: `thought` flavor.
- `Door` (`Interactable`): invisible hotspot over the painted exit; `target_scene = res://scenes/City.tscn`.
- `RoomCam` `Camera2D` (centered on the room, `zoom` ~1.2 like IntroRoom).
- `Player` instance: spawn near the entrance; `Sprite2D` scale `0.073` (match IntroRoom); the
  Player's own `Camera2D` disabled (RoomCam drives the view).

## Data additions

### `data/dialogue.json` — add `"captain"` (PLACEHOLDER; LLM-driven later)

Minimal ~3-node tree: greet → a `charge` branch that fires `collect: captain_briefing` +
`lead: <next objective>`, plus a "who are the Nighthawks?" flavor branch. **Not** clue-gated —
depth is deliberately deferred (the captain will be driven by the LLM agent layer). Literal JSON
lives in the implementation plan.

### `data/clues.json` — add `captain_briefing`

```json
{
  "id": "captain_briefing",
  "name": "The Captain's Charge",
  "description": "The Nighthawk captain set you on the trail: Antigonus' notebook is a key the Church will kill for, and the University archives hold his name.",
  "type": "testimony",
  "importance": "pivotal",
  "location": "nighthawk_hq",
  "topics": ["the_nighthawks", "antigonus_notebook"],
  "linked_entities": ["nighthawk_captain"]
}
```

### Default next lead

`"线索：前往廷根大学档案馆，查清安提哥努斯其人 (Search the Tingen University archives for Antigonus)."`
— flavor text in the dialogue's `lead` effect; trivially redirectable. No new scene required.

## Assets to copy into `tingen/assets` (finished PNGs only; `.import` generated on first Godot import)

- `asset-gen/out_image2/backgrounds/hq_interior.png` → `assets/backgrounds/hq_interior.png`
- `asset-gen/out_image2/characters/nighthawk_captain.png` → `assets/characters/nighthawk_captain.png`

(`portrait_captain.png` exists, but the `DialoguePanel` is text-only and is HUD-adjacent UI we
don't own/modify — the portrait is unused for now.)

## Verification (manual-first)

- **Headless wiring test** `tests/test_nighthawks_hq.gd` (mirror `test_intro_room.gd`):
  `RoomPhoto`→`hq_interior.png`; `Solids` is a `StaticBody2D` with ≥N shapes; `Captain.dialogue_id == "captain"`
  and its icon ends `nighthawk_captain.png`; `CaseBoard` present; `Door.target_scene == "res://scenes/City.tscn"`;
  `RoomCam` is a `Camera2D`; Player sprite → `klein_down.png`; plus data asserts: `dialogue.json` parses
  and has a `"captain"` key; `clues.json` has `captain_briefing`; `City.tscn` `HQDoor.target_scene`
  points to `NighthawksHQ.tscn`.
- **Non-headless screenshot harness:** full room + captain close-up; verify figure scale/placement,
  no floating art, player reaches the talk zone, colliders block.
- **Playtest:** IntroMain → City → HQDoor → HQ; talk (captain_briefing collected, lead updates,
  Tab board shows it), examine, door back to City.

## Files touched — ownership safety

- **CREATE:** `scenes/NighthawksHQ.tscn`, `tests/test_nighthawks_hq.gd`.
- **EDIT:** `data/dialogue.json`, `data/clues.json` (NOT on the animation-agent owned list —
  `items.json`/`action_schema.json` are; these are not).
- **EDIT:** `scenes/City.tscn` (add `HQDoor`; optional lead).
- **COPY:** 2 PNGs into `assets/`.
- **Untouched:** `NpcDB.gd`, `Main.tscn`, `ui/HUD.tscn` + sub-scenes, `items.json`,
  `action_schema.json`, and all other animation-agent-owned files. No GDScript changes at all.

## Deferred / future

- Captain conversation becomes LLM-driven (the static `"captain"` tree is a stand-in).
- Precise return-spawn in City; real City street art; the archives scene the lead points to.
