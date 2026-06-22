# Tingen Mystery Game — Engine Gap Analysis

**Context:** The Tingen GDD asks Yumina to serve as both a shipping mystery-simulation title AND a reusable engine for narrative sims. This doc maps the GDD's system requirements against what the engine has today, and scopes the work needed to close the gap.

**Status as of 2026-04-20:** Phase B tile library (~7,700 assets) + resolver deployed. Structure regen finishing. NPC intelligence Phase I.4 in progress on a parallel agent. Phase C (tile integration into scene-gen) planned at `docs/superpowers/plans/2026-04-20-phase-c-tile-system-integration.md`.

---

## 0. For implementers — how to use this doc

This section is READ FIRST if you're picking up work from this document.

### Who this doc is for

- Claude agents (and humans) picking up engine work on the Tingen scope test
- Sister doc: `tingen_engine_extensibility_plan.md` (plugin architecture)
- Sister doc: `tingen_ui_panel_authoring_plan.md` (React UI authoring surface)
- Sister doc: `docs/superpowers/plans/2026-04-20-phase-c-tile-system-integration.md` (Phase C execution plan)

### Reading order

1. **`CLAUDE.md`** — project conventions, tech stack, hard requirements. Non-negotiable baseline.
2. **This doc, Sections 0-3** — strategic context, scorecard, milestone list.
3. **This doc, Section 11** — detailed implementation plan for YOUR milestone (jump to the right sub-section).
4. **This doc, Sections 8 + 12** — file paths + handoff prompt for your milestone.
5. **Any engine files the plan references** — read before writing to understand existing patterns.

You can skim Sections 4-10; they are context for humans making prioritization calls.

### How to pick a milestone

Each milestone is scoped to roughly 1-4 days of focused work. Check:

- **File-conflict awareness** block at the end of each milestone in Section 11 — tells you whether another agent's work will overlap with yours
- **Dependencies** — milestones have a DAG; some can't start until others land
- **Hot zones** (below) — files claimed by ongoing work; don't touch

The recommended starter milestone is **M1 (Game Clock)** — it has near-zero file overlap with every other tracked work stream.

### Hot zones (files claimed by ongoing work — don't touch unless you're the owner)

| File | Owner | Why |
|---|---|---|
| `packages/bridge/src/ai-director.ts` | NPC intelligence agent (Phase I.4) | Active refactoring |
| `packages/bridge/src/world-room.ts` | NPC intelligence agent (NPC tick paths) | Active refactoring |
| `packages/bridge/src/scene-generator.ts` | Phase C agent | Adding compileSceneFromBlueprint call |
| `packages/bridge/src/blueprint-generator.ts` | Phase C agent | Adding biomesHint + structureRequests to prompt |
| `packages/sdk-core/src/scene-blueprint.ts` | Phase C agent | Schema extension |
| `packages/engine/src/spatial/sceneCompiler.ts` | Phase C agent | New file |
| `packages/app/public/buildings/`, `config/tile-prompts/`, `scripts/generate-tile-biome.py` | Tile regen (background) | Don't edit during regen |

If you MUST edit a hot-zone file, coordinate via a git branch + PR rather than direct commit to the shared working branch.

### Output requirements for any milestone

Before declaring a milestone done, you MUST:

1. ✅ Typecheck clean: `pnpm --filter @yumina/{affected-package} typecheck` for every package you touched
2. ✅ Tests pass: `pnpm --filter @yumina/{affected-package} test` — existing tests unbroken + your new tests added
3. ✅ Build clean: `pnpm --filter @yumina/{affected-package} build`
4. ✅ Verification checklist for your milestone (in its Section 11 sub-section) — all items checked
5. ✅ Log to `RECENT_CHANGES.md` under a 2026-MM-DD header summarizing what shipped
6. ✅ DO NOT commit unless user explicitly asks

Do NOT:
- Create files outside what the milestone plan says — get approval for scope changes first
- Skip tests — TDD or test-after is fine, but tests must exist
- Edit hot-zone files without the owner's coordination
- Touch the tile regen pipeline (see Hot Zones above)

### How to ask for help

If you hit something the plan doesn't cover, ask the user via `AskUserQuestion` rather than guessing. Quote the exact ambiguity.

### Where to write the detailed plan if you extend scope

If a milestone grows beyond what's in Section 11, add a dedicated plan file at `docs/superpowers/plans/2026-MM-DD-m{N}-{kebab-name}.md` matching the depth of the Phase C plan. Link it from the milestone's Section 11 block.

---

## 1. Summary Scorecard

Legend: ✅ ready  •  🟡 partial / needs extension  •  ❌ absent

### Simulation core

| GDD system | Status | Notes |
|---|---|---|
| Scenes + zones + entities + exits | ✅ | `packages/engine/src/spatial/*` — fully tile-based |
| Multi-tile enterable buildings | ✅ | `spriteSize` + `interactionPoints` + `change_scene` action |
| Tile compilation (layout compiler) | ✅ | `spatial/layoutCompiler.ts` — biome-hint driven |
| Building placer | ✅ | `spatial/buildingPlacer.ts` — pure function, tested |
| Pathfinding (A*) | ✅ | `spatial/pathfinding.ts` — 4-cardinal, cost grid |
| Event bus + reactions | ✅ | `events/event-bus.ts`, `reactions/reaction-evaluator.ts` |
| Variables + Rules 2.0 | ✅ | Triggers, conditions, actions; editor UI in `editor/sections/rules-section.tsx` |
| NPC dialogue (ai_say) | ✅ | `bridge/ai-director.ts` — perception-aware, memory, undercover |
| NPC autonomy (ai_decide) | ✅ | 90-180s jitter idle tick; zone/NPC context; goal line |
| Entity tiers (A/B/C) | 🟡 | Schema defined, distance-based promoter wired in bridge, no author UI |
| NPC relationship + fatigue | ✅ | `relationshipScore`, `fatigueLevel` (fresh/fatigued/annoyed) |
| Combat (turn-based) | 🟡 | Single enemy, basic attack/flee. No party, no abilities, no boss phases |
| Inter-NPC exchanges | 🟡 | `recentlyTalkedTo` tracked, `heardFromOthers` in prompt — handler in flight (Phase I.4) |
| Lorebook (knowledge / rumors) | ✅ | `lorebook-matcher.ts` — keyword + fuzzy + recursive; `knowsVariables` / `hiddenVariables` per NPC |
| Timer system | ✅ | `timer/runtime.ts` — countdown + interval, events |
| Game clock / time of day | ❌ | No in-engine clock, no day phases, no schedules |
| NPC schedules (daily loop) | ❌ | No morning/afternoon/dusk/night behavior swap |
| NPC goal stack / plans | 🟡 | `currentGoalLine` transient; no persistent stack, no pre-computed plans |
| Cutscene / intro system | ❌ | Audio fading exists; no timeline, camera pan, or scripted sequence framework |
| Directional sprite animation | ❌ | Per-entity sprite is a single URL; directional + state-machine handled (partially) by Unity renderer |
| Animation event hooks | ❌ | No frame-X-fires-event wiring in engine |
| Positional audio | ❌ | BGM is global + conditional; no distance attenuation, no per-zone ambient layers |
| Save / load game sessions | ✅ | `session-manager.ts`, `game_sessions` DB table, file + DB persistence |
| Entity movement persistence | ❌ | Entities are static spawns; NPC drift via ai_decide isn't saved |

### Mystery-simulation specific

| GDD system | Status | Notes |
|---|---|---|
| World Manager (stages + pressure) | ❌ | Variables can approximate, but no stage state machine, no offscreen resolution tick |
| Pressure variables (corruption / panic / fatigue / cult readiness / attention) | 🟡 | Trivial to declare as variables; no dedicated system, no pressure-driven event spawner |
| Dynamic slotting (primary site, fallback, first victim, courier, etc.) | ❌ | No slot system. Could be faked via variables + authored alternatives |
| Rumor propagation | 🟡 | Lorebook entries can act as rumors; no spread / decay / district-scoped model |
| Investigation board UI | ❌ | No node-link graph component. `UIBlueprint` can't express drag-connect edges natively |
| Clue collection / evidence model | ❌ | No explicit `Clue` schema. Could piggy-back on variables or inventory |
| Hypothesis mechanics | ❌ | No data model for player-authored hypotheses |
| Interview / contradiction system | 🟡 | Dialogue has `knowsVariables` / `hiddenVariables` filtering; no contradiction-detection, no topic panel |
| Tail / stakeout mechanics | 🟡 | Proximity + perception exists; no formal "follow target" behavior |
| Divination / occult tools | ❌ | Could be implemented as UI components + Rules; no built-in framework |
| Day/night ritual escalation | ❌ | Depends on time-of-day (absent) + World Manager (absent) |
| Ally deployment / squad | ❌ | No "send ally to district" mechanic. Combat is solo |
| Main quest + side incidents | 🟡 | `worldBlueprint.storyline` with milestones exists in editor; no dynamic incident spawner |
| Authoring tools for schedules / incidents / clues | ❌ | Rules + reactions + lorebook are authorable; scheduling/clues/incidents are not |

### Asset pipeline + rendering

| GDD system | Status | Notes |
|---|---|---|
| Tile manifest (100 biomes) | ✅ | `TILE_MANIFEST_DATA` — 7,682 assets, resolver-queryable |
| Building manifest | ✅ | `BUILDING_MANIFEST` — 256×256 sprites, cell footprint metadata |
| Sprite embedding search | ✅ | `resolveBuildingSprite`, `resolveTile`, `sprite-library.ts` |
| Audio BGM + SFX + conditional tracks | ✅ | `ConditionalBGM`, `BGMPlaylist`, `AudioEffect` |
| Victorian-city biome | ✅ | Added 2026-04-20, regen in progress |
| Unity WebGL renderer | ✅ | `sdks/unity/My project/Assets/Yumina/Scripts/**` — canvas also present |
| Custom sprite upload via editor | 🟡 | Asset picker accepts uploads (images/audio); not wired for new sprite library entries |

### UI architecture (the React / Unity split)

| GDD system | Status | Notes |
|---|---|---|
| Screen-space HUD (clock, pressure meter, health) | 🟡 | Currently Unity `GameHUD.cs` (441 LOC); should migrate to React `hud-overlay` |
| Menus / pause / settings | 🟡 | Currently Unity `GameUI.cs` (870 LOC); should migrate to React `modal` |
| Inventory panel | 🟡 | Currently Unity `InventoryUI.cs` (235 LOC); should migrate to React `sidebar` |
| Dialogue choice buttons | 🟡 | Currently Unity `DialogueUI.cs` partial; should migrate to React `modal` |
| World-anchored speech bubbles (follow NPC head) | ✅ | Unity `DialogueUI.cs` — stays Unity (camera-synced) |
| Floating damage numbers, hit flashes, screen shake | ✅ | Unity `VfxManager.cs` — stays Unity |
| Positional audio | ✅ | Unity `AudioManager.cs` — stays Unity; React triggers via events |
| Custom TSX game shells (Kochuu-style) | ✅ | `CustomUIComponent` surface `app`; renderer exists |
| Custom TSX message bubbles | ✅ | `CustomUIComponent` surface `message` |
| Custom TSX hud/modal/sidebar | ❌ | Not yet a surface — see `tingen_ui_panel_authoring_plan.md` |
| Panel Router (event-driven panel mounting) | ❌ | Needs implementation as part of UI Panel Authoring Phase 1 |
| World→screen projection for React overlays | ❌ | Needed only if we want React-side world-anchored UI (damage numbers etc.) — optional; Unity handles this fine today |

### Editor / authoring

| GDD system | Status | Notes |
|---|---|---|
| Scene creation + tile painting | ✅ | `paint-canvas.tsx` + toolbar + biome palette + tile gallery |
| Entity placement | ✅ | `entity-canvas.tsx`, `entity-palette.tsx`, `entity-inspector.tsx` |
| Behavior library templates | ✅ | `behavior-library-panel.tsx` — greeter, merchant, wanderer, guard, hostile |
| Rules editor (WHEN/IF/THEN) | ✅ | `rules-section.tsx` with all 9 trigger types + 8 action types |
| Reactions editor (event-driven) | ✅ | `reactions-section.tsx` |
| Variables editor | ✅ | CRUD, categories |
| Lorebook editor | ✅ | Unified entries (keywords, conditions, positions, tags, folders) |
| Custom UI (TSX) | ✅ | `components.tsx` with live compile |
| Quest editor | 🟡 | Flat milestone list, no visual flowchart, no quest-event triggers UI |
| NPC state inspector (debug) | ❌ | AI prompt inspector is read-only; no live NPC state panel |
| Dialogue tree editor | ❌ | Dialogue is LLM-driven — no visual tree authoring |
| Exit connector UI (drag scene→scene) | ❌ | `addSceneExit()` exists, no canvas UI |
| Schedule authoring UI | ❌ | Depends on schedule system (absent) |
| Clue / evidence authoring | ❌ | Depends on clue system (absent) |
| Incident / event-chain authoring | ❌ | Only reactions (atomic). No multi-step authored chains |

---

## 2. What's genuinely missing (the work list)

Ordered roughly by "blocks the Tingen slice / unblocks everything else."

### M1 — Game clock + day phases (foundational)

Tingen lives on morning/afternoon/dusk/night/late-night. Without a clock, NPC schedules, ritual timers, and ambient escalation all fall apart.

- **New**: `packages/engine/src/clock/` — `Clock` runtime tracking game minutes, day count, phase enum
- **Emits** `clock:phase_change` (morning → afternoon → dusk → night → late-night) and `clock:day_rolled`
- **Authoring**: editor variables like `@clock.phase`, `@clock.day`, `@clock.hour`
- **UI**: top-bar clock + phase indicator in playtest

Scope: ~1 day. Piggybacks on the existing `TimerRuntime`.

### M2 — NPC schedule system (routines)

Tingen needs merchants at market mornings, labourers at docks days, patrons at taverns nights. Requires:

- **New**: schedule authoring on `SceneEntity` — `schedule: { phase: DayPhase; location: SceneId+zone; action: string }[]`
- **Engine layer**: on `clock:phase_change`, director reassigns NPC zones / behaviors
- **60-second strategic refresh**: already exists as `ai_decide` idle tick — extend so that the prompt includes "your scheduled location/role right now"
- **Authoring UI**: `scenes-panel.tsx` + `entities-panel.tsx` — per-NPC schedule grid (rows = phases, columns = location + action)
- **Memory**: persist schedule execution in `EntityRuntimeState.scheduleState`

Scope: ~2-3 days. Unlocks observation gameplay (stakeouts, tailing).

### M3 — World Manager + pressure variables

- **New**: `packages/engine/src/world-manager/` — `WorldManager` runtime with stage enum (Stage1_Disturbance..Stage6_RitualNight) + continuous pressure variables (corruption, panic, fatigue, cultReadiness, attention)
- **Stage transitions**: a DSL of conditions (clue found, ritual delivery succeeded, time passed, corruption > threshold) — compile to reactions
- **Offscreen tick**: every N minutes, resolve ambient progression (courier delivered → cultReadiness +=1, panic drains fatigue, etc.)
- **Dynamic slots**: declare slot roles (`primary_ritual_site`, `first_corrupted_civilian`, `decoy_courier`) and pre-authored candidates; at stage start, World Manager picks via weighted random
- **Authoring UI**: new editor section `world-manager-section.tsx` with stage graph + pressure config + slot definitions

Scope: ~3-4 days. This is the BIG system that makes Tingen feel alive and replayable.

### M4 — Clue / evidence / investigation board

- **Data model**: `Clue { id, name, description, type: physical|behavioral|occult, layer, discoveredAt, linkedEntities[], linkedVariables[] }`
- **Clue store**: session-scoped; `addClue()` / `getDiscoveredClues()` effects
- **Board UI**: brand-new component `components/investigation-board.tsx` — drag-connect clues, pin hypotheses. Skip drag-connect in v1; render as a flat gallery + suspect-focused lists.
- **Dialogue integration**: a clue can unlock a topic in dialogue ("ask about the ledger")
- **Authoring UI**: clue library + clue placement on scenes + clue-reveal rules

Scope: ~3-4 days. The investigation board itself is the hardest part; flat gallery + topic-unlock can ship in ~1 day as MVP.

### M5 — Inter-NPC exchanges + rumor propagation

Phase I.4 agent is already on the NPC exchange handler. On top of that:

- **Rumor model**: `Rumor { topic, districtOfOrigin, truthfulness, spreadStrength, valence, attachedEntities[] }`
- **Spread tick**: when two NPCs exchange, rumor ledger on each NPC updates; spread decays with distance
- **Listen-in mechanic**: player within proximity → snippets appear in HUD
- **Authoring**: rumor authoring UI in the lorebook section (new "rumors" folder treated specially)

Scope: ~2 days. Builds on the inter-NPC exchange work in flight.

### M6 — Cutscene / intro system

Tingen opens with a scripted video → black screen → wake up. Needs:

- **New**: `packages/engine/src/cutscene/` — Cutscene runtime with timeline (camera pan, fade, text, image, audio, wait, branch)
- **Format**: JSON array of `CutsceneStep` objects; authorable as a new editor section
- **Playback**: client-side runtime that orchestrates Unity camera / canvas fades + text box + image-embed parser
- **Video playback**: support an mp4/webm `<video>` step with pre-computed duration

Scope: ~2-3 days.

### M7 — Occult tool framework

- **Pattern**: each occult tool is a UI component + rule set
- **Divination**: modal that queries `WorldManager.getStageHint()` → outputs ambiguous symbolic hint
- **Residue sight**: overlay layer on scene showing `clue_visibility_modifier` variables
- **Dream fragments**: triggered by sleep at safehouse → injects a directive into next turn's system prompt
- **Gray-fog reconstruction**: opens investigation board with inference panel, `resolveHypothesisSupport()` returning confidence 0-1

Scope: ~3-4 days, assuming M4 investigation board exists.

### M8 — Combat v2 (tactical real-time with pause)

Current `resolve-turn.ts` is 1v1 turn-based attack/flee. Tingen needs:

- **Party**: 1-3 allies with own HP, abilities, fatigue
- **Real-time-with-pause**: tick-driven but `world.paused=true` freezes NPC AI + clock
- **Abilities**: revolver, paper charm, decoy, spirit sight, emergency retreat
- **Objectives**: "interrupt ritual" / "cleanse anchor" / "hold chokepoint" — encoded as combat-scope variables + reactions
- **Enemy types**: corrupted human, cult operative, ritual spawn, partial descent — schema extension of `SceneEntity`

Scope: ~4-5 days. Could ship a lighter v2 with party-of-2 + just revolver+charm.

### M9 — Authoring tools for the above

For each new system, editor UI:

- Schedule grid editor (M2)
- Stage graph editor + pressure-variable panel + slot assignment UI (M3)
- Clue library + board placement (M4)
- Rumor folder + spread preview (M5)
- Cutscene timeline editor (M6)
- Occult tool inspector + ritual anchor editor (M7)
- Combat encounter editor + ability picker (M8)

Scope: bundled with each system. Total authoring time ≈ 1-2 days per system on top of the runtime.

### M10 — Observability / debug tools

GDD 36.4 explicitly flags: "Without this, AI is unusable for devs." Needed:

- **NPC state inspector**: live panel showing current goal, schedule state, memory, perception, stance, fatigue, recent decisions
- **Path visualizer**: overlay showing pathfinding result + cost grid
- **Rule trace**: for each rule fire, log trigger + condition results + action output
- **Event log**: streaming event bus view in studio
- **Time-travel debugger (stretch)**: scrub through last N turns, replay

Scope: ~2-3 days. High ROI — required for external devs to use the engine.

### M11 — Unity UI migration (thin-renderer boundary)

**Why**: Today Unity owns ~2,800 LOC across 7 UI scripts. Most of it (HUD, menus, inventory, dialogue choices) is screen-space and should live in React so it benefits from TSX authoring, AI generation, plugin registration, and hot reload. Only world-anchored UI should stay in Unity.

**Migration table** (more detail in `TODO.md` under "Unity UI migration"):

| File | LOC | Direction |
|---|---:|---|
| `GameHUD.cs` | 441 | → React `hud-overlay` |
| `GameUI.cs` | 870 | → React `modal` / `sidebar` |
| `InventoryUI.cs` | 235 | → React `sidebar` |
| `DialogueUI.cs` (choices) | ~150 | → React `modal` |
| `DialogueUI.cs` (speech bubbles) | ~250 | **Stays Unity** (world-anchored) |
| `VfxManager.cs` | 405 | **Stays Unity** (particles, flashes) |
| `AudioManager.cs` | 231 | **Stays Unity** (positional audio) |
| `PreviewControls.cs` | 177 | **Stays Unity** (Unity editor tool) |

**End-state**: Unity is a near-pure renderer (tiles + sprites + animations + particles + world-anchored UI + positional audio + camera). React owns every screen-space UI surface.

**Phases** (~2-3 weeks, parallel-shippable):
- **Week 1**: Build `hud-overlay` surface + Panel Router (bundled with UI Panel Authoring Phase 1). Migrate `GameHUD.cs` → React. Parallel-ship behind feature flag.
- **Week 2**: Migrate `GameUI.cs` menus → React modals. Migrate `InventoryUI.cs` → React sidebar. Migrate dialogue choice buttons (keep world-anchored bubbles in Unity).
- **Week 3**: Deprecate migrated Unity scripts, update Unity build, final playtest sweep. Document the thin-renderer boundary in `CLAUDE.md`.

**Dependencies**: UI Panel Authoring Phase 1 must land first (Panel Router + schema + `hud-overlay` / `modal` / `sidebar` surfaces).

**Open questions**:
- Unity camera transform → bridge streaming: is it already available, or add a lightweight `camera_update` protocol message on every Unity scene frame?
- React-side floating damage numbers (world-anchored via world→screen projection) vs Unity-side: Unity is simpler for v1; React gets more theming flexibility later.
- Positional audio: confirm React → Unity event `audio:play-at({ x, y, trackId })` is the cleanest boundary (AudioManager handles positioning, React just declares intent).

---

## 3. Milestone plan (rough time order)

Aligning with GDD §38 milestones:

```
Milestone 0 — Current state                             [DONE]
  ✅ Scenes, tile/building pipeline, NPC dialogue,
     autonomy, behavior triggers, rules 2.0, reactions

Milestone 1 — Clock + schedules                         [4-6 days]
  M1 Game clock + day phases
  M2 NPC schedule system + schedule authoring UI
  → first "living city" feel: NPCs move between work/home

Milestone 2 — World Manager + pressure                  [5-7 days]
  M3 WorldManager + stages + pressure + dynamic slots
  → stage progression + offscreen resolution

Milestone 3 — Investigation systems                     [5-7 days]
  M4 Clue model + simple board UI
  M5 Rumor propagation (on top of inter-NPC work)
  → mystery gameplay is playable end-to-end

Milestone 4 — Polish layer                              [7-10 days]
  M6 Cutscene system (for intro + stage reveals)
  M7 Occult tool framework
  M10 NPC debug inspector + rule trace

Milestone 5 — Combat v2                                 [4-5 days]
  M8 Tactical real-time with pause + party

Milestone X — Unity UI migration                        [10-15 days, parallel]
  M11 Migrate Unity GameHUD / GameUI / InventoryUI /
      DialogueUI choices → React surfaces
  → thin-renderer boundary locked in; all screen-space
    UI becomes authorable / plugin-extensible
  Can run PARALLEL to Milestones 2-4 once UI Panel
  Authoring Phase 1 lands.

Milestone 6 — Vertical slice polish                     [7-10 days]
  Audio positional + district-specific ambient
  Directional sprite animations (Unity + canvas)
  Final integration test (45-90min playtime)
```

**Total engineering for vertical slice: ~8-10 weeks** with one engineer + the NPC agent running in parallel. Compressed further with focused scope.

---

## 4. What unblocks what

```
game clock
  └─ NPC schedules
       └─ rumor propagation
            └─ investigation board
                 └─ occult tools

world manager
  └─ stage progression
       └─ dynamic slots
            └─ ritual timers (uses clock)
            └─ investigation escalation

inter-NPC exchange (Phase I.4, in flight)
  └─ rumor propagation
  └─ NPC-to-NPC memory bleed

cutscene system
  └─ intro sequence
  └─ stage reveals ("the fog thickens...")
  └─ ritual catastrophe cinematic

combat v2
  └─ warehouse raid
  └─ ritual night finale

observability tools
  └─ unblocks ALL of the above for external devs
  └─ critical for shipping engine

UI Panel Authoring (Phase 1 — surfaces + Panel Router)
  ├─ React hud-overlay + modal + sidebar surfaces
  ├─ event-driven panel mounting
  └─ Unity UI migration (M11)
       ├─ GameHUD.cs → React hud-overlay
       ├─ GameUI.cs → React modals
       ├─ InventoryUI.cs → React sidebar
       └─ DialogueUI choice buttons → React modal
          (speech bubbles stay Unity)
```

---

## 5. Recommended immediate next steps (for the Tingen effort)

**Right now (while structure regen is finishing):**
- Nothing to change. Regen + Phase C runtime integration of `compileLayout` + `placeBuildings` is still prereq.

**Next sprint (assuming structure regen lands clean):**
1. **M1 — Game clock** (2 days). Smallest bite, unblocks the most.
2. **M2 — NPC schedules** (3 days). Plug straight into the Phase I.4 intelligence work.
3. **M10 (slice) — NPC state inspector panel** (2 days). Makes M2 debuggable while building it.

**After that:**
4. **M4 MVP — Clue model + flat board** (2 days) — skip drag-connect, just a list with tags and linked NPCs/scenes.
5. **M3 MVP — WorldManager with 1 pressure var + stage advance rules** (3 days) — prove the pattern on one variable before generalizing.
6. **UI Panel Authoring Phase 1 + M11 Week 1** (5 days combined) — build `hud-overlay` + `modal` + `sidebar` surfaces + Panel Router, then migrate `GameHUD.cs` → React as the first validation. Unblocks M4's investigation board UI shape (can be a real React modal, not a fork-blocking engine change).

That's ~17 days of work that would let us start the Tingen vertical slice proper AND begin the Unity → React migration in the same sprint.

---

## 6. What the Tingen project should AVOID doing right now

- Don't try to build the full investigation board (drag-connect + hypothesis slots) in v1 — ship the flat gallery first.
- Don't build a bespoke combat system — extend the existing resolver with party + objectives; full real-time-with-pause is a stretch goal.
- Don't author all 100 biomes' Tingen-style content — Tingen uses ~3 districts × ~3 sub-scenes. Victorian-city + 2-3 interior scenes is enough.
- Don't build positional 3D audio — district-keyed BGM + SFX triggered by `clock:phase_change` covers 80% of the atmosphere.
- Don't chase sprite state-machines + animation hooks in Yumina engine — the Unity renderer should own that side; engine emits `entity:action` events the renderer subscribes to.
- Don't build a visual dialogue tree — LLM-driven dialogue with lorebook + topic-unlock already maps to "layered questioning with clue references."
- Don't build Ink/Yarn scripting support — our rule/reaction/lorebook system already replaces it.

---

## 7. What's genuinely new / research-flavoured

These are the parts that aren't solved by extending existing systems:

1. **Dynamic slot assignment** — at stage start, picking primary ritual site / first victim / decoy via weighted config. Needs a small DSL.
2. **Offscreen resolution** — the world manager ticking forward without the player. Requires determinism + idempotency so scene-gen doesn't conflict.
3. **Hypothesis confidence** (gray-fog) — how do we compute "player believes X with confidence Y based on clues Z"? Needs a Bayesian-ish (or rule-sum) scoring function.
4. **Rumor truthfulness + spread** — modelling a rumor as a node that mutates as it propagates through NPCs. Novel for Yumina.
5. **Inter-NPC dialogue archiving** — `heardFromOthers` already captures intent, but full transcript replay isn't there yet.

All tractable, none blockers.

---

## 8. File paths to touch for each milestone (draft)

```
M1 clock:
  NEW  packages/engine/src/clock/types.ts
  NEW  packages/engine/src/clock/runtime.ts
  NEW  packages/engine/src/clock/system.ts
  NEW  packages/engine/src/__tests__/clock.test.ts
  EDIT packages/engine/src/index.ts (export Clock)
  EDIT packages/bridge/src/game-session.ts (instantiate + tick)
  EDIT packages/app/src/features/studio/panels/playtest-panel.tsx (show phase)

M2 schedules:
  EDIT packages/engine/src/spatial/schemas.ts (add schedule[] to sceneEntitySchema)
  EDIT packages/engine/src/spatial/types.ts
  EDIT packages/bridge/src/ai-director.ts (inject scheduled role into ai_decide prompt)
  EDIT packages/bridge/src/world-room.ts (on phase_change → reassign idle zones)
  NEW  packages/app/src/features/editor/sections/schedules-section.tsx
  NEW  packages/app/src/features/studio/panels/schedule-panel.tsx

M3 world manager:
  NEW  packages/engine/src/world-manager/types.ts
  NEW  packages/engine/src/world-manager/runtime.ts
  NEW  packages/engine/src/world-manager/stage-machine.ts
  NEW  packages/engine/src/world-manager/pressure.ts
  NEW  packages/engine/src/world-manager/slots.ts
  NEW  packages/engine/src/__tests__/world-manager.test.ts
  EDIT packages/engine/src/index.ts
  NEW  packages/app/src/features/editor/sections/world-manager-section.tsx

M4 clues:
  NEW  packages/engine/src/clues/types.ts
  NEW  packages/engine/src/clues/runtime.ts
  NEW  packages/engine/src/world/clue-schema.ts
  EDIT packages/engine/src/rules/rules-engine.ts (add discover_clue action)
  NEW  packages/app/src/features/editor/sections/clues-section.tsx
  NEW  packages/app/src/features/studio/panels/investigation-board-panel.tsx

M5 rumors:
  NEW  packages/engine/src/rumor/types.ts
  NEW  packages/engine/src/rumor/propagation.ts
  EDIT packages/bridge/src/ai-director.ts (inject rumor beliefs into ai_decide)

M6 cutscenes:
  NEW  packages/engine/src/cutscene/types.ts
  NEW  packages/engine/src/cutscene/runtime.ts
  NEW  packages/app/src/features/game-play/cutscene-player.tsx
  NEW  packages/app/src/features/editor/sections/cutscenes-section.tsx

M8 combat v2:
  EDIT packages/engine/src/combat/resolve-turn.ts (party support)
  NEW  packages/engine/src/combat/abilities.ts
  NEW  packages/engine/src/combat/objectives.ts

M10 observability:
  NEW  packages/app/src/features/studio/panels/npc-state-inspector-panel.tsx
  NEW  packages/app/src/features/studio/panels/event-log-panel.tsx
  EDIT packages/bridge/src/game-session.ts (expose via WS channel)

M11 Unity UI migration (parallel with M4-M7):
  NEW  packages/app/src/features/game-play/panel-router.tsx
  NEW  packages/app/src/features/game-play/surfaces/hud-overlay.tsx
  NEW  packages/app/src/features/game-play/surfaces/modal-host.tsx
  NEW  packages/app/src/features/game-play/surfaces/sidebar-host.tsx
  EDIT packages/engine/src/types/index.ts (expand CustomUIComponent.surface enum)
  EDIT packages/engine/src/world/schema.ts (backward-compat migration)
  NEW  packages/app/src/features/game-play/panels/default-hud.tsx  (replaces GameHUD.cs)
  NEW  packages/app/src/features/game-play/panels/default-menu.tsx (replaces GameUI.cs menus)
  NEW  packages/app/src/features/game-play/panels/default-inventory.tsx (replaces InventoryUI.cs)
  NEW  packages/app/src/features/game-play/panels/default-dialogue-choices.tsx (replaces DialogueUI.cs choice part)
  DELETE sdks/unity/My project/Assets/Yumina/Scripts/UI/GameHUD.cs
  DELETE sdks/unity/My project/Assets/Yumina/Scripts/UI/GameUI.cs
  DELETE sdks/unity/My project/Assets/Yumina/Scripts/UI/InventoryUI.cs
  EDIT  sdks/unity/My project/Assets/Yumina/Scripts/UI/DialogueUI.cs (strip choice-list; keep speech bubbles)
  EDIT  sdks/unity/My project/Assets/Yumina/Scripts/Core/YuminaClient.cs (emit camera_update + remove HUD message handling)
  EDIT  packages/sdk-core/src/protocol.ts (new camera_update + ui_event messages)
  EDIT  CLAUDE.md (document thin-renderer boundary)
```

---

## 9. Open design questions

These need decisions before we start coding the bigger milestones:

1. **Is the World Manager a single runtime class on the bridge, or a pure function over events?**
   - Pure function is testable and matches our existing engine style. Vote: pure function.
2. **Does the clock tick in real time, or is it advanced by the player via a "rest / end day" action?**
   - GDD implies real time during day, player-advanced at day end. Probably hybrid.
3. **How dynamic should "dynamic slots" be?**
   - For v1, pre-authored N candidates + weighted random at stage start. Runtime reshuffling deferred.
4. **Are rumors propagated eagerly (on every NPC exchange) or lazily (resolved when read)?**
   - Eager for small NPC counts (< 30) of the slice; lazy once we scale.
5. **Where does the investigation board render — inside the studio editor or as a game HUD component?**
   - Both. Editor authors it; runtime shows player-visible subset. `UIBlueprint` or standalone?
6. **Combat v2 — real-time-with-pause vs turn-based tactical (like Into-The-Breach)?**
   - Turn-based tactical is easier to ship but loses some of the horror flavor. GDD 16.2 leaves both open; picking is a separate discussion.

---

## 10. What's ALREADY aligned with the GDD

Worth highlighting how far we already are:

- The engine is **explicitly framework-agnostic** (GDD 31 requirement ✓).
- We have a **real Rules 2.0 engine** with triggers, conditions, actions, directives, cooldowns, max-fire counts (GDD 22.1 #4 ✓).
- We have a **working event bus** (GDD 22.2 ✓).
- We have a **knowledge system** with keyword matching + per-NPC filtering (supports rumor + clue gating layer; GDD 11, 13 foundations ✓).
- NPC dialogue uses **perception + memory + relationship + fatigue + undercover disguise** — this is 80% of GDD §9.
- We have a **tile + building asset library of ~7,700 sprites** with embedding-search resolver — covers GDD §33 sprite pipeline for everything except directional animation.
- We have an **authoring editor** with rules / variables / lorebook / entity inspector / scene painter / playtest (GDD §24.3 ✓ for the basics).
- Session **save/load with per-NPC runtime state** works today (GDD 22.4 ✓).

So the foundation is strong. What's missing is the mystery-sim-specific layer (clock, schedules, world manager, clues, rumors) + polish (cutscenes, combat v2, observability). Each piece is tractable in days, not weeks.

---

## 11. Detailed implementation plans (per milestone)

Each sub-section below is a ship-ready spec. Read the section for your milestone before writing code. Section 8 above has the raw file paths; here we add type contracts, pseudocode, test matrices, and verification gates.

---

### M1 — Game Clock + Day Phases

**Why this matters**: Tingen runs on morning/afternoon/dusk/night/late-night. Without a clock, schedules, rumors, ritual timers, and ambient escalation all fall apart. M1 is the foundation for M2, M3, M5, M6.

**Design decisions** (locked):
- Clock state lives in `GameState.variables` under namespaced keys (`clock.day`, `clock.minute`, `clock.phase`) — reachable by rules/reactions via existing `@`-path syntax. No new storage surface.
- Clock advances client-side via `requestAnimationFrame` loop in the app (avoids touching `world-room.ts` which is a hot zone).
- 1 real second = 1 game minute by default; per-world override via `world.settings.clockRealSecondsPerGameMinute`.
- Phase boundaries: `early-morning` 5:00-8:00, `morning` 8:00-12:00, `afternoon` 12:00-17:00, `dusk` 17:00-19:00, `night` 19:00-23:00, `late-night` 23:00-5:00. Hardcoded; revisit for plugin extensibility post-M1.
- Pause: when `world.paused === true`, clock halts. Useful for combat v2 later.

**Deliverables**:

| File | Action | ~LOC |
|---|---|---|
| `packages/engine/src/clock/types.ts` | NEW | 30 |
| `packages/engine/src/clock/runtime.ts` | NEW | 140 |
| `packages/engine/src/clock/system.ts` | NEW | 40 |
| `packages/engine/src/clock/phases.ts` | NEW | 30 |
| `packages/engine/src/__tests__/clock.test.ts` | NEW | 180 |
| `packages/engine/src/index.ts` | EDIT (add exports) | +10 |
| `packages/engine/src/systems/registry.ts` | EDIT (register CLOCK_SYSTEM) | +3 |
| `packages/app/src/features/game-play/use-clock-tick.ts` | NEW (RAF tick hook) | 50 |
| `packages/app/src/features/studio/panels/playtest-panel.tsx` | EDIT (render phase in playtest bar) | +15 |

**Type contracts**:

```typescript
// packages/engine/src/clock/types.ts
export type DayPhase =
  | "early-morning"
  | "morning"
  | "afternoon"
  | "dusk"
  | "night"
  | "late-night";

export interface ClockState {
  /** 1-indexed game day. */
  day: number;
  /** Minute of day, 0-1439. */
  minuteOfDay: number;
  /** Current phase, derived from minuteOfDay. */
  phase: DayPhase;
}

export interface ClockConfig {
  realSecondsPerGameMinute: number;  // default 1.0
  startingDay: number;                // default 1
  startingMinute: number;             // default 480 (= 8:00 morning)
}
```

**Implementation sketch** (`runtime.ts`):

```typescript
import { phaseForMinute, DAY_MINUTES } from "./phases.js";
import type { ClockState, ClockConfig } from "./types.js";

export class ClockRuntime {
  private state: ClockState;
  private config: ClockConfig;
  private accumulator = 0;

  constructor(config: Partial<ClockConfig> = {}) {
    this.config = {
      realSecondsPerGameMinute: 1.0,
      startingDay: 1,
      startingMinute: 480,
      ...config,
    };
    this.state = {
      day: this.config.startingDay,
      minuteOfDay: this.config.startingMinute,
      phase: phaseForMinute(this.config.startingMinute),
    };
  }

  /** Advance the clock by `dtSeconds` of real time.
   *  Returns list of events to emit. */
  tick(dtSeconds: number): ClockEvent[] {
    this.accumulator += dtSeconds;
    const secondsPerMinute = this.config.realSecondsPerGameMinute;
    const events: ClockEvent[] = [];

    while (this.accumulator >= secondsPerMinute) {
      this.accumulator -= secondsPerMinute;
      const prevPhase = this.state.phase;
      this.state.minuteOfDay += 1;

      if (this.state.minuteOfDay >= DAY_MINUTES) {
        this.state.minuteOfDay = 0;
        this.state.day += 1;
        events.push({ type: "clock:day-rolled", day: this.state.day });
      }

      this.state.phase = phaseForMinute(this.state.minuteOfDay);
      if (this.state.phase !== prevPhase) {
        events.push({
          type: "clock:phase-changed",
          phase: this.state.phase,
          day: this.state.day,
        });
      }
    }
    return events;
  }

  getState(): Readonly<ClockState> { return { ...this.state }; }
  setState(state: ClockState): void { this.state = { ...state }; }
}
```

**Phase mapping** (`phases.ts`):

```typescript
export const DAY_MINUTES = 1440;

const PHASE_BOUNDARIES: Array<[number, DayPhase]> = [
  [0,    "late-night"],
  [300,  "early-morning"],  // 5:00
  [480,  "morning"],        // 8:00
  [720,  "afternoon"],      // 12:00
  [1020, "dusk"],           // 17:00
  [1140, "night"],          // 19:00
  [1380, "late-night"],     // 23:00
];

export function phaseForMinute(minute: number): DayPhase {
  let phase: DayPhase = "late-night";
  for (const [bound, p] of PHASE_BOUNDARIES) {
    if (minute >= bound) phase = p;
    else break;
  }
  return phase;
}
```

**SystemRegistry entry** (`system.ts`):

```typescript
export const CLOCK_SYSTEM: SystemDefinition = {
  id: "clock",
  name: "Game Clock",
  description: "Day/time progression with phase transitions",
  category: "core",
  alwaysActive: true,
  events: [
    { type: "clock:phase-changed", dataFields: [
      { name: "phase", type: "string" }, { name: "day", type: "number" }
    ]},
    { type: "clock:day-rolled", dataFields: [
      { name: "day", type: "number" }
    ]},
  ],
  statePaths: [
    { path: "@clock.day", type: "number", readOnly: true },
    { path: "@clock.minute", type: "number", readOnly: true },
    { path: "@clock.phase", type: "string", readOnly: true },
    { path: "@clock.advance", type: "number", readOnly: false,
      description: "Set to advance the clock by N game minutes instantly" },
  ],
};
```

**Client-side tick hook** (app side):

```typescript
// packages/app/src/features/game-play/use-clock-tick.ts
export function useClockTick(clockRuntime: ClockRuntime, onEvents: (e: ClockEvent[]) => void) {
  useEffect(() => {
    let last = performance.now();
    let rafId: number;
    function loop() {
      const now = performance.now();
      const dt = (now - last) / 1000;
      last = now;
      const events = clockRuntime.tick(dt);
      if (events.length) onEvents(events);
      rafId = requestAnimationFrame(loop);
    }
    loop();
    return () => cancelAnimationFrame(rafId);
  }, [clockRuntime, onEvents]);
}
```

**Test matrix** (`__tests__/clock.test.ts`):

1. Default config starts at day 1, minute 480, phase `morning`
2. Tick with zero real seconds → no state change, empty events
3. Tick enough to cross one game minute → state advances, no phase event if still same phase
4. Tick across phase boundary → emits `clock:phase-changed`
5. Tick across day boundary (minute 1439 → 0) → emits `clock:day-rolled` AND probably `clock:phase-changed`
6. `realSecondsPerGameMinute = 0.1` (fast-forward) → correct minute count after 1 real second
7. `setState` restores state (round-trip for save/load)
8. `phaseForMinute` returns correct phase for boundary values (0, 299, 300, 480, 1140, 1380, 1439)
9. Accumulator handling — very small dt over many ticks correctly aggregates (no lost time)

**Dependencies**: none. M1 is the root.

**Unblocks**: M2 (schedules need `clock:phase-changed`), M5 (rumors tick on phase change), M6 (cutscenes can pause clock), M8 (combat can pause clock).

**File-conflict awareness**:
- Shares `packages/engine/src/index.ts` with Phase C (both add exports). Trivial merge; both agents append.
- Shares `packages/engine/src/systems/registry.ts` with M3, M5 (they'll register their own systems). Merge by appending.
- Nothing else overlaps.

**Verification checklist**:
- [ ] `pnpm --filter @yumina/engine typecheck build test` all clean
- [ ] 9/9 test cases pass
- [ ] Playtest panel shows "Day 1, morning" correctly at session start
- [ ] Advancing playtime shows phase transitions at expected times
- [ ] Save + reload session → clock state restored exactly
- [ ] A reaction with `when: { type: "clock:phase-changed", match: { phase: "night" } }` fires at dusk→night transition

**Out of scope**: schedules (M2), weather, lunar phases, in-world calendar events, cutscene-triggered pauses (M6).

---

### M2 — NPC Schedule System

**Why this matters**: Tingen needs merchants at market in mornings, labourers at docks in day, patrons at taverns at night. This makes the city feel alive and enables stakeouts/tailing gameplay.

**Design decisions** (locked):
- Schedule data lives on `SceneEntity` as a new optional field `schedule: ScheduleEntry[]`.
- On `clock:phase-changed`, a bridge reaction re-assigns `entity.behavior.idle.zoneId` to match the schedule.
- `ai_decide` prompt gets a new section: "Your scheduled location right now: {zoneId}. Your role right now: {role}."
- Schedule authoring: new editor section `schedules-section.tsx` with a phase × entity grid.
- Backward compat: entities without `schedule` behave as today.

**Deliverables**:

| File | Action | ~LOC |
|---|---|---|
| `packages/engine/src/spatial/schemas.ts` | EDIT (add schedule field to sceneEntitySchema) | +25 |
| `packages/engine/src/spatial/types.ts` | EDIT (add ScheduleEntry type) | +15 |
| `packages/bridge/src/ai-director.ts` | EDIT (inject scheduled role into ai_decide prompt) | +30 |
| `packages/bridge/src/schedule-runtime.ts` | NEW (reacts to clock:phase-changed) | 100 |
| `packages/engine/src/__tests__/schedule-runtime.test.ts` | NEW | 120 |
| `packages/app/src/features/editor/sections/schedules-section.tsx` | NEW | 220 |
| `packages/app/src/features/studio/panels/schedule-panel.tsx` | NEW | 180 |
| `packages/app/src/features/studio/studio-page-catalog.ts` | EDIT | +5 |

**Type contracts**:

```typescript
// packages/engine/src/spatial/types.ts (addition)
import type { DayPhase } from "../clock/types.js";

export interface ScheduleEntry {
  phase: DayPhase;
  zoneId?: string;           // where the NPC should be during this phase
  sceneId?: string;          // if different from current (NPC moves between scenes)
  role?: string;             // narrative role, e.g. "working the bar", "sleeping"
  activity?: string;         // mechanical idle behavior hint, e.g. "wanderer" | "patrol"
}

// Added to SceneEntity:
schedule?: ScheduleEntry[];
```

**Runtime** (`schedule-runtime.ts`):

```typescript
export class ScheduleRuntime {
  constructor(
    private getEntities: () => SceneEntity[],
    private updateEntity: (id: string, patch: Partial<SceneEntity>) => void,
  ) {}

  /** Called by bridge on every clock:phase-changed event. */
  applyPhase(phase: DayPhase, currentSceneId: string): void {
    for (const entity of this.getEntities()) {
      if (!entity.schedule) continue;
      const entry = entity.schedule.find(e => e.phase === phase);
      if (!entry) continue;

      // Scene transfer (cross-scene movement is deferred to spawn-on-demand pattern —
      // for v1 we only update entities in the current scene).
      if (entry.sceneId && entry.sceneId !== currentSceneId) continue;

      const patch: Partial<SceneEntity> = {};
      if (entry.zoneId) {
        patch.behavior = {
          ...entity.behavior,
          idle: { ...entity.behavior?.idle, zoneId: entry.zoneId },
        };
      }
      if (entry.role) {
        // Stored in a scratch field for the prompt builder; see ai-director.ts patch.
        patch.scheduledRole = entry.role;
      }
      if (Object.keys(patch).length > 0) {
        this.updateEntity(entity.id, patch);
      }
    }
  }
}
```

**Prompt injection** (in `ai-director.ts::buildAiDecidePrompt`):

```typescript
// After existing zone/NPC context:
if (entity.schedule && entity.scheduledRole) {
  sections.push(`
## Your routine
It is ${clockState.phase}. Your routine says you should be in zone "${entity.behavior?.idle?.zoneId ?? "anywhere"}" doing: ${entity.scheduledRole}.
Unless something urgent interrupts (player interaction, combat, a scripted event), prefer actions consistent with your routine.
`);
}
```

**Editor section** (`schedules-section.tsx`):

Grid UI:
- Rows: scene entities with `name` + sprite
- Columns: phases (early-morning, morning, afternoon, dusk, night, late-night)
- Cells: dropdown of zones in the entity's current scene + optional text input for `role`
- "Apply template" button: preset templates (9-5 worker / bartender / guard / farmer / student)

**Test matrix**:

1. `applyPhase("morning")` → entities with `phase: "morning"` entries get their `behavior.idle.zoneId` updated
2. Entity without schedule → untouched
3. Entry without zoneId → only `scheduledRole` updates (if present)
4. Cross-scene sceneId in schedule → skipped in v1 (logged)
5. Multiple entities, different schedules → all correctly applied in one pass
6. Phase-change with no matching schedule entry → entity keeps prior zone

**Dependencies**: M1 (clock emits phase-changed event).

**Unblocks**: M3 (World Manager uses schedules for ambient activity), rumor observability (NPCs seen at known location).

**File-conflict awareness**:
- `ai-director.ts` is NPC-intelligence-agent's hot zone. Coordinate via branch. The change is ~30 lines of prompt injection, isolated to `buildAiDecidePrompt` — easiest if NPC agent reviews before merging.
- `spatial/schemas.ts` + `spatial/types.ts` — safe; entity schema addition is non-breaking.
- `studio-page-catalog.ts` — shared with M4, M6 (each adds a panel entry). Merge by appending.

**Verification checklist**:
- [ ] Typecheck + tests pass
- [ ] Create a test entity with 2 schedule entries (morning → zone "shop", night → zone "home")
- [ ] Advance playtest from morning to night via debug "advance time" button → entity's `behavior.idle.zoneId` updates
- [ ] `ai_decide` prompt (checked via AI Prompt Inspector) includes "Your routine says you should be in zone X doing: Y."
- [ ] Schedule editor UI round-trips: edit → save → reload → data persists

**Out of scope**: cross-scene NPC movement (Phase 2 work), spawn/despawn logic, schedule override on combat (M8), calendar events per day-of-week.

---

### M3 — World Manager + Pressure + Dynamic Slots

**Why this matters**: The biggest single absent piece. Without a world manager, Tingen can't express "stage progression" (ritual escalation), "pressure variables" (cult readiness, panic, corruption), or "dynamic slots" (which location is the primary ritual site this playthrough).

**Design decisions** (locked):
- WorldManager state is a typed store (Zod schema) — NOT loose variables. Stored under `GameState.metadata["world-manager"]`.
- Stages are a fixed enum per world (declared in world definition). Tingen uses 6.
- Pressure: N named numeric variables, 0-100 range, with thresholds that emit events when crossed.
- Dynamic slots: at stage start, pick from a pool of candidates via weighted random (seeded).
- Offscreen tick: every N turns, `worldManager.tick()` runs to advance ambient progress without player action.

**Deliverables**:

| File | Action | ~LOC |
|---|---|---|
| `packages/engine/src/world-manager/types.ts` | NEW | 80 |
| `packages/engine/src/world-manager/runtime.ts` | NEW | 220 |
| `packages/engine/src/world-manager/stage-machine.ts` | NEW | 140 |
| `packages/engine/src/world-manager/pressure.ts` | NEW | 100 |
| `packages/engine/src/world-manager/slots.ts` | NEW | 90 |
| `packages/engine/src/world-manager/system.ts` | NEW (SystemDefinition) | 50 |
| `packages/engine/src/__tests__/world-manager.test.ts` | NEW | 250 |
| `packages/engine/src/index.ts` | EDIT (exports) | +8 |
| `packages/engine/src/systems/registry.ts` | EDIT | +3 |
| `packages/app/src/features/editor/sections/world-manager-section.tsx` | NEW | 300 |

**Type contracts**:

```typescript
// packages/engine/src/world-manager/types.ts
export interface StageDefinition {
  id: string;
  name: string;
  description?: string;
  /** Conditions that, when ALL true, advance to this stage. */
  enterWhen: StageCondition[];
  /** Actions that fire on stage enter (directives, events, variable sets). */
  onEnter?: StageAction[];
}

export interface StageCondition {
  type: "pressure-threshold" | "variable-equals" | "clue-discovered" | "stage-duration-turns";
  /** pressure name, variable id, clue id, etc. */
  target: string;
  /** required value — interpretation depends on type */
  value: number | string | boolean;
  /** for thresholds: "gte" | "lte" | "eq" */
  op?: "gte" | "lte" | "eq";
}

export interface PressureDefinition {
  id: string;
  label: string;
  min: number;
  max: number;
  initial: number;
  /** thresholds at which events emit */
  thresholds?: Array<{ at: number; eventType: string }>;
}

export interface SlotDefinition {
  id: string;
  label: string;
  /** Pool of candidates to pick from. Each has a weight. */
  candidates: Array<{ value: string; weight: number }>;
  /** When to resolve: "world-start" | "stage-enter:{stageId}". */
  resolveAt: string;
}

export interface WorldManagerConfig {
  stages: StageDefinition[];
  pressures: PressureDefinition[];
  slots: SlotDefinition[];
  /** How many player turns between offscreen ticks. Default 10. */
  offscreenTickInterval?: number;
}

export interface WorldManagerState {
  currentStageId: string;
  stageEnteredAtTurn: number;
  pressures: Record<string, number>;
  slots: Record<string, string>;  // slotId → resolved value
  lastOffscreenTickTurn: number;
}
```

**Runtime**:

```typescript
export class WorldManagerRuntime {
  private state: WorldManagerState;
  private seededRng: () => number;

  constructor(
    private config: WorldManagerConfig,
    private getTurnCount: () => number,
    private emitEvent: (e: GameEvent) => void,
    seed: string = "default",
  ) {
    this.seededRng = mulberry32(hashStringSeed(seed));
    this.state = this.initialState();
  }

  private initialState(): WorldManagerState {
    return {
      currentStageId: this.config.stages[0].id,
      stageEnteredAtTurn: 0,
      pressures: Object.fromEntries(
        this.config.pressures.map(p => [p.id, p.initial])
      ),
      slots: this.resolveSlots("world-start"),
      lastOffscreenTickTurn: 0,
    };
  }

  adjustPressure(id: string, delta: number): void {
    const def = this.config.pressures.find(p => p.id === id);
    if (!def) return;
    const prev = this.state.pressures[id];
    const next = clamp(prev + delta, def.min, def.max);
    this.state.pressures[id] = next;
    for (const t of def.thresholds ?? []) {
      if (prev < t.at && next >= t.at) this.emitEvent({ type: t.eventType, pressure: id, value: next });
    }
  }

  checkStageAdvance(): void {
    for (const stage of this.config.stages) {
      if (stage.id === this.state.currentStageId) continue;
      if (this.evaluateConditions(stage.enterWhen)) {
        const prev = this.state.currentStageId;
        this.state.currentStageId = stage.id;
        this.state.stageEnteredAtTurn = this.getTurnCount();
        this.emitEvent({ type: "stage:advanced", from: prev, to: stage.id });
        // Apply onEnter actions
        for (const action of stage.onEnter ?? []) {
          this.emitEvent({ type: "stage:action", stageId: stage.id, action });
        }
        // Resolve stage-enter slots
        this.state.slots = { ...this.state.slots, ...this.resolveSlots(`stage-enter:${stage.id}`) };
        break;  // one advancement per call
      }
    }
  }

  tick(): void {
    const turn = this.getTurnCount();
    if (turn - this.state.lastOffscreenTickTurn < (this.config.offscreenTickInterval ?? 10)) return;
    this.state.lastOffscreenTickTurn = turn;
    this.emitEvent({ type: "world-manager:tick", stage: this.state.currentStageId });
    // Callers wire reactions that adjust pressures on tick.
  }

  getState(): Readonly<WorldManagerState> { return { ...this.state }; }
}
```

**Test matrix**:

1. Fresh init → state has first stage, initial pressures, slots resolved from world-start pool
2. `adjustPressure("corruption", 10)` → value increases, no event if no threshold crossed
3. Threshold crossing → emits the configured event type once (not on further adjustments above threshold)
4. `checkStageAdvance()` with satisfied conditions → advances, emits `stage:advanced`, resolves new-stage slots
5. Deterministic slot resolution: same seed → same slot values
6. `tick()` respects offscreenTickInterval (no-op before interval, emits after)
7. State round-trip (save/load) preserves stage + pressures + slots exactly

**Dependencies**: M1 (clock ticks drive `tick()`), plugin architecture ideal but not required (works on current typed metadata).

**Unblocks**: M4 (clues can advance stage via condition), M5 (rumors modulate pressures), M6 (cutscenes fire on stage enter), M7 (occult tools read pressures).

**File-conflict awareness**: no shared files with Phase C or NPC agent beyond the index.ts export line. Self-contained.

**Verification checklist**:
- [ ] Typecheck + tests pass (aim for 12+ test cases)
- [ ] Configure a 3-stage test world via editor section
- [ ] Adjust pressure → see value change in inspector
- [ ] Cross a threshold → configured event fires (verify via event log panel)
- [ ] Manual "advance stage" debug → stage changes, onEnter actions fire
- [ ] Session save/reload → state preserved

**Out of scope**: UI for visualizing stage graph (deferred), player-facing pressure meter (comes with M10/UI Panel), offscreen scene-gen while player is elsewhere.

---

### M4 — Clue / Evidence Model + Investigation Board (MVP)

**Why this matters**: Mystery games need a clue model. Without it, authors can't wire "player found evidence X" into the narrative state.

**Design decisions** (locked):
- Clue data lives in `GameState.metadata["clues"]` as an array, typed via Zod schema.
- New behavior action `reveal_clue` and rule action `discover-clue` both append to the array.
- Topic-unlock: clues have a `topics` array; dialogue prompt injects "You may now ask about: {topics}".
- v1 board UI: flat gallery + tag filter + linked-entity list. No drag-connect edges (deferred).
- Authoring: new editor section for clue library.

**Deliverables**:

| File | Action | ~LOC |
|---|---|---|
| `packages/engine/src/clues/types.ts` | NEW | 40 |
| `packages/engine/src/clues/runtime.ts` | NEW | 120 |
| `packages/engine/src/__tests__/clues.test.ts` | NEW | 150 |
| `packages/engine/src/rules/rules-engine.ts` | EDIT (add `discover-clue` action) | +40 |
| `packages/bridge/src/behavior-evaluator.ts` | EDIT (add `reveal_clue` action) | +30 |
| `packages/bridge/src/ai-director.ts` | EDIT (inject clue topics into ai_say prompt) | +25 |
| `packages/engine/src/index.ts` | EDIT (exports) | +5 |
| `packages/app/src/features/editor/sections/clues-section.tsx` | NEW (library editor) | 280 |
| `packages/app/src/features/game-play/investigation-board.tsx` | NEW (flat gallery modal) | 260 |
| `packages/app/src/features/studio/studio-page-catalog.ts` | EDIT | +3 |

**Type contracts**:

```typescript
// packages/engine/src/clues/types.ts
export interface Clue {
  id: string;
  name: string;
  description: string;
  type: "physical" | "behavioral" | "occult" | "testimony";
  discoveredAtTurn?: number;
  location?: string;             // scene id or free-text
  linkedEntityIds?: string[];
  linkedVariables?: string[];
  topics: string[];              // unlocked dialogue topics
  tags?: string[];
  importance?: "pivotal" | "supporting" | "flavor";
}

export interface ClueLibrary {
  clues: Clue[];
}

export interface DiscoveredClue extends Clue {
  discoveredAtTurn: number;
  discoveredBy: "player-interact" | "dialogue" | "scripted" | "rule";
}
```

**Rule action addition**:

```typescript
// rules-engine.ts (pseudocode addition to action dispatch)
case "discover-clue": {
  const clueId = action.clueId;
  const library = context.world.clueLibrary;
  const clue = library.clues.find(c => c.id === clueId);
  if (!clue) return { applied: false, error: `Unknown clue: ${clueId}` };

  const state = context.state;
  const discovered = (state.metadata["clues"] as DiscoveredClue[]) ?? [];
  if (discovered.some(c => c.id === clueId)) return { applied: false, error: "Already discovered" };

  discovered.push({
    ...clue,
    discoveredAtTurn: state.turnCount,
    discoveredBy: action.source ?? "rule",
  });
  state.metadata["clues"] = discovered;
  context.emitEvent({ type: "clue:discovered", clueId, name: clue.name });
  return { applied: true };
}
```

**Prompt injection** (`ai-director.ts::buildAiSayPrompt`):

```typescript
// After knowledge section:
const discoveredClues = (state.metadata["clues"] as DiscoveredClue[]) ?? [];
const relevantTopics = discoveredClues
  .flatMap(c => c.topics)
  .filter((t, i, arr) => arr.indexOf(t) === i);
if (relevantTopics.length > 0) {
  sections.push(`
## Player's investigation topics
The player has uncovered clues that unlocked these topics: ${relevantTopics.join(", ")}.
If the player asks about these, you may acknowledge what's known. Do not volunteer unless prompted.
`);
}
```

**Investigation board UI** (flat MVP):

- Modal opens on `clue:board-open` event (player keypress "B" or toolbar button)
- Filter chips by type (physical/behavioral/occult/testimony) + tags
- Card per clue: name + description + discoveredAtTurn + linked entities (clickable → entity inspector)
- Sort: by turn (newest first) / by type / by importance

**Test matrix**:

1. `discover-clue` action with valid clueId → clue appended to state, event fired
2. Duplicate discovery → no-op + warning
3. Unknown clueId → error returned
4. `ai_say` prompt contains topic list only if player has discovered clues
5. Investigation board renders all discovered clues
6. Filter by type → only matching type shown
7. Filter by tag → only matching tag shown

**Dependencies**: ideally UI Panel Authoring Phase 1 (for a clean modal surface), but works standalone as a full-page route in v1.

**Unblocks**: M7 (occult tools reveal clues), gray-fog hypothesis (future).

**File-conflict awareness**:
- `ai-director.ts` — NPC agent hot zone. Same coordination pattern as M2.
- `behavior-evaluator.ts` — NPC agent hot zone. Same pattern.
- `rules-engine.ts` — less contested but coordinate.

**Verification checklist**:
- [ ] Typecheck + tests pass
- [ ] Author a test clue in editor section
- [ ] Configure a rule: when variable `inspected-warehouse === true`, discover clue
- [ ] Trigger the rule in playtest → clue appears in investigation board
- [ ] `ai_say` prompt (via AI Prompt Inspector) shows topics list
- [ ] Save + reload → discovered clues persist

**Out of scope**: node-link graph, hypothesis builder, contradiction detection, clue → LLM evidence inference, multi-player clue sharing.

---

### M5 — Inter-NPC Exchanges + Rumor Propagation

**Why this matters**: Tingen's city lives on overheard rumors. When NPCs exchange information, the player can stakeout a tavern and hear pieces that reveal the cult's movement. Rides on the in-flight NPC Phase I.4 work.

**Design decisions** (locked):
- Rumor is a first-class typed entity in `GameState.metadata["rumors"]`.
- On NPC-to-NPC exchange (NPC agent Phase I.4 feature), check if either has a rumor; with probability ~0.3 propagate to the other.
- Rumor truthfulness is a 0-1 float that can mutate (degrade or improve) on propagation.
- Player "overhears" when within proximity of two exchanging NPCs → fragment appears in HUD bubble.

**Deliverables**:

| File | Action | ~LOC |
|---|---|---|
| `packages/engine/src/rumor/types.ts` | NEW | 50 |
| `packages/engine/src/rumor/propagation.ts` | NEW | 140 |
| `packages/engine/src/__tests__/rumor.test.ts` | NEW | 180 |
| `packages/bridge/src/ai-director.ts` | EDIT (inject rumors into ai_say prompt) | +25 |
| `packages/bridge/src/world-room.ts` | EDIT (call propagate on npc-exchange events) | +20 |
| `packages/engine/src/index.ts` | EDIT | +4 |
| `packages/app/src/features/editor/sections/rumors-section.tsx` | NEW (rumor library editor) | 200 |
| `packages/app/src/features/game-play/overhear-bubble.tsx` | NEW (HUD fragment) | 80 |

**Type contracts**:

```typescript
export interface Rumor {
  id: string;
  topic: string;
  summary: string;                // one-sentence summary
  longForm?: string;              // expanded prompt-injection version
  district?: string;              // district of origin
  truthfulness: number;           // 0-1
  valence: "positive" | "negative" | "neutral";
  attachedEntityIds?: string[];
  attachedVariables?: string[];
  heardBy: string[];              // entity IDs who know it
  spreadStrength: number;         // 0-1, decays over time
  createdAtTurn: number;
}
```

**Propagation** (`propagation.ts`):

```typescript
export function propagateRumorOnExchange(
  rumors: Rumor[],
  speakerId: string,
  listenerId: string,
  rng: () => number,
): { updatedRumors: Rumor[]; propagated: Rumor[] } {
  const updated = [...rumors];
  const propagated: Rumor[] = [];
  for (const r of updated) {
    if (!r.heardBy.includes(speakerId)) continue;
    if (r.heardBy.includes(listenerId)) continue;
    // Propagation probability scales with rumor's spreadStrength.
    if (rng() > r.spreadStrength * 0.5) continue;
    r.heardBy.push(listenerId);
    // Truthfulness can degrade slightly on each retelling.
    r.truthfulness = Math.max(0, r.truthfulness - rng() * 0.05);
    propagated.push(r);
  }
  return { updatedRumors: updated, propagated };
}

export function decayRumors(rumors: Rumor[], decayPerTurn: number): Rumor[] {
  return rumors.map(r => ({
    ...r,
    spreadStrength: Math.max(0, r.spreadStrength - decayPerTurn),
  }));
}
```

**Prompt injection**:

```typescript
// ai-director.ts::buildAiSayPrompt addition
const npcRumors = (state.metadata["rumors"] as Rumor[] ?? [])
  .filter(r => r.heardBy.includes(entity.id))
  .slice(-3);  // Only most recent 3 to keep prompt budget in check

if (npcRumors.length > 0) {
  sections.push(`
## Rumors you've heard
${npcRumors.map(r => `- "${r.summary}" (you believe this is ${r.truthfulness > 0.7 ? "likely true" : r.truthfulness > 0.3 ? "uncertain" : "probably untrue"})`).join("\n")}
You may share or reference these rumors in conversation, if relevant.
`);
}
```

**Test matrix**:

1. Propagate from speaker with rumor to listener without → listener's heardBy includes them
2. Listener already knows rumor → no-op
3. Speaker doesn't know rumor → no propagation
4. RNG probability respected (mock rng=0.99 → no propagation; rng=0.01 → yes)
5. Truthfulness degrades on propagation
6. Decay: one turn of decay reduces spreadStrength by the decay rate
7. Player proximity detection → correct fragments emerge when both speakers near
8. Save/reload round-trips all rumor state

**Dependencies**: M1 (decay tick on clock), ideally NPC agent Phase I.4 (inter-NPC exchange events), M3 (pressure can rise from spreading rumors).

**Unblocks**: Tingen's overhear mechanic, M7 gray-fog hypothesis input.

**File-conflict awareness**:
- `ai-director.ts` + `world-room.ts` — NPC hot zones. Same coordination pattern as M2/M4.

**Verification checklist**:
- [ ] Typecheck + tests pass
- [ ] Author 2 rumors in editor
- [ ] Assign a rumor to NPC A
- [ ] Trigger an NPC exchange event A→B
- [ ] Verify B now has the rumor (via debug inspector)
- [ ] NPC B's `ai_say` prompt contains the rumor line
- [ ] Player standing next to both → overhear bubble appears

**Out of scope**: rumor deliberate-plant mechanic, player-fabricated rumors, rumor spread visualization (future), district-specific decay rates.

---

### M6 — Cutscene / Intro System

**Why this matters**: Tingen opens with a scripted video → black → wake up. Stage reveals ("the fog thickens…") need cinematic beats. Without a framework, authors must hand-roll each cutscene in TSX.

**Design decisions** (locked):
- Cutscenes are data: array of `CutsceneStep` objects.
- Step types: `wait`, `fade`, `text`, `image`, `audio`, `camera-pan`, `branch`, `variable-set`, `end`.
- Cutscene runtime lives on the app side, driven by `requestAnimationFrame`.
- Trigger: event-driven (reaction emits `cutscene:play` with cutsceneId).
- Authoring: timeline-ish editor section (list of steps, add/reorder/edit).
- Skip: player can skip (unless `unskippable: true`).

**Deliverables**:

| File | Action | ~LOC |
|---|---|---|
| `packages/engine/src/cutscene/types.ts` | NEW | 100 |
| `packages/engine/src/cutscene/runtime.ts` | NEW | 200 |
| `packages/engine/src/__tests__/cutscene.test.ts` | NEW | 180 |
| `packages/engine/src/index.ts` | EDIT | +5 |
| `packages/app/src/features/game-play/cutscene-player.tsx` | NEW | 250 |
| `packages/app/src/features/editor/sections/cutscenes-section.tsx` | NEW | 300 |
| `packages/app/src/features/studio/studio-page-catalog.ts` | EDIT | +3 |

**Type contracts**:

```typescript
export type CutsceneStep =
  | { type: "wait"; durationMs: number }
  | { type: "fade"; direction: "in" | "out"; durationMs: number; color?: string }
  | { type: "text"; content: string; speaker?: string; durationMs?: number; style?: TextStyle }
  | { type: "image"; url: string; durationMs: number; fit?: "cover" | "contain" | "fill" }
  | { type: "audio"; trackId: string; action: "play" | "stop"; fadeDuration?: number }
  | { type: "camera-pan"; toSceneId?: string; toX?: number; toY?: number; durationMs: number }
  | { type: "branch"; conditionVariableId: string; equals: string | number | boolean; steps: CutsceneStep[] }
  | { type: "variable-set"; variableId: string; value: string | number | boolean }
  | { type: "end" };

export interface Cutscene {
  id: string;
  name: string;
  description?: string;
  unskippable?: boolean;
  steps: CutsceneStep[];
}
```

**Runtime**:

```typescript
export class CutsceneRuntime {
  private cursor = 0;
  private elapsed = 0;
  private stepState: { startedAt: number; duration?: number } | null = null;

  constructor(
    private cutscene: Cutscene,
    private hooks: CutsceneHooks,
  ) {}

  tick(dt: number): void {
    if (this.cursor >= this.cutscene.steps.length) return;
    const step = this.cutscene.steps[this.cursor];
    if (!this.stepState) {
      this.stepState = { startedAt: this.elapsed, duration: (step as any).durationMs };
      this.executeStep(step);
    }
    this.elapsed += dt * 1000;
    if (this.stepState.duration != null && this.elapsed - this.stepState.startedAt >= this.stepState.duration) {
      this.cursor += 1;
      this.stepState = null;
    }
  }

  skip(): void {
    if (this.cutscene.unskippable) return;
    this.cursor = this.cutscene.steps.length;
  }

  isDone(): boolean { return this.cursor >= this.cutscene.steps.length; }

  private executeStep(step: CutsceneStep): void {
    switch (step.type) {
      case "text": this.hooks.onText?.(step); break;
      case "image": this.hooks.onImage?.(step); break;
      case "audio":
        if (step.action === "play") this.hooks.onAudioPlay?.(step.trackId, step.fadeDuration);
        else this.hooks.onAudioStop?.(step.trackId, step.fadeDuration);
        break;
      case "variable-set": this.hooks.onVariableSet?.(step.variableId, step.value); break;
      // ... etc
    }
  }
}
```

**Cutscene player component**:

React component that mounts a full-screen overlay, renders the current step's visual (text box, image, fade layer), calls `runtime.tick(dt)` on RAF. Dispatches `cutscene:done` event when runtime reports done. Renders skip button (unless unskippable).

**Test matrix**:

1. Empty cutscene → done immediately
2. Text step → fires `onText` with content
3. Wait step → advances after durationMs
4. Skip → advances to end unless unskippable
5. Variable-set → fires `onVariableSet`
6. Branch evaluates correctly (variable match / mismatch)
7. Audio play/stop → correct hook fires

**Dependencies**: M1 (can pause clock during cutscene), no other blockers.

**Unblocks**: Tingen intro sequence, stage-reveal cinematics, ritual-night finale.

**File-conflict awareness**: self-contained.

**Verification checklist**:
- [ ] Typecheck + tests pass
- [ ] Author a 5-step cutscene (text → wait → image → audio → text)
- [ ] Trigger via reaction in playtest
- [ ] Cutscene plays in order, audio fires, text boxes display
- [ ] Skip button advances to end
- [ ] `cutscene:done` event fires at end

**Out of scope**: character blocking/position (defer to Unity world-anchored UI), per-character voice acting, localized text rendering, cutscene branching from player choice (future).

---

### M7 — Occult Tool Framework

**Why this matters**: Tingen's "gray-fog reconstruction", "divination", "residue sight", "dream fragments" are all instances of the same pattern: a gated UI modal that reads world state and gives the player a new perspective. A framework lets authors add their own tools.

**Design decisions** (locked):
- Occult tools are plugin-like entries: `{ id, name, gated: condition, component: TSXRef, onInvoke: Action }`.
- UI is a right-click-accessible wheel (or key hotkey).
- Each tool component reads world state via `useYumina()` and produces a modal output.
- v1 ships 4 templates: divination (ambiguous hint), residue-sight (overlay clues on scene), dream (directive injection for next turn), gray-fog (investigation board with inference).

**Deliverables**:

| File | Action | ~LOC |
|---|---|---|
| `packages/engine/src/occult/types.ts` | NEW | 60 |
| `packages/engine/src/occult/runtime.ts` | NEW | 100 |
| `packages/engine/src/__tests__/occult.test.ts` | NEW | 120 |
| `packages/app/src/features/game-play/occult-wheel.tsx` | NEW (radial selector) | 180 |
| `packages/app/src/features/game-play/occult-tools/divination.tsx` | NEW | 120 |
| `packages/app/src/features/game-play/occult-tools/residue-sight.tsx` | NEW | 140 |
| `packages/app/src/features/game-play/occult-tools/dream.tsx` | NEW | 100 |
| `packages/app/src/features/game-play/occult-tools/gray-fog.tsx` | NEW | 200 |
| `packages/app/src/features/editor/sections/occult-tools-section.tsx` | NEW | 220 |

**Type contracts**:

```typescript
export interface OccultTool {
  id: string;
  name: string;
  icon?: string;
  gated?: {
    type: "variable-equals" | "clue-discovered" | "stage-reached";
    target: string;
    value: string | number | boolean;
  };
  componentId: string;   // maps to one of the built-in tool components
  cooldownTurns?: number;
  costVariableId?: string;
  costAmount?: number;
}
```

**Test matrix**: gating evaluation, cooldown tracking, cost deduction, event emission on invoke.

**Dependencies**: M3 (stages gate tools), M4 (clue discovery gates tools).

**Unblocks**: Tingen's core mystery-solving surface.

**File-conflict awareness**: self-contained, all new files.

**Verification checklist**:
- [ ] Typecheck + tests pass
- [ ] Register 4 default tools
- [ ] In playtest, keypress triggers wheel
- [ ] Ungated tool invokes correctly
- [ ] Gated tool is greyed out until condition met
- [ ] Cost deducts; cooldown blocks re-invoke

**Out of scope**: per-world custom tool TSX upload (lands when UI Panel Authoring ships), tool animation polish, audio cues.

---

### M8 — Combat v2 (Party + Objectives + Real-Time-with-Pause)

**Why this matters**: Tingen's ritual raid needs party tactics, ally deployment, objective-driven combat (interrupt the ritual, not kill everything). Current `resolveCombatTurn` is 1v1 attack/flee.

**Design decisions** (locked):
- Combat is real-time-with-pause: when `combat.paused === true`, NPC AI + clock halt; player plans actions; on resume, all units execute simultaneously over next N ticks.
- Party: 1-3 player-controlled units with abilities.
- Enemies: typed — `corrupted-civilian`, `cult-operative`, `ritual-spawn`, `partial-descent`.
- Abilities: `revolver`, `paper-charm`, `decoy`, `spirit-sight`, `emergency-retreat`.
- Objectives: combat-scope variables that define win/lose beyond HP (e.g. `ritual-progress < 100`).

**Deliverables**:

| File | Action | ~LOC |
|---|---|---|
| `packages/engine/src/combat/resolve-turn.ts` | EDIT (extend for party) | +150 |
| `packages/engine/src/combat/abilities.ts` | NEW | 180 |
| `packages/engine/src/combat/objectives.ts` | NEW | 120 |
| `packages/engine/src/combat/realtime.ts` | NEW | 200 |
| `packages/engine/src/__tests__/combat-v2.test.ts` | NEW | 250 |
| `packages/app/src/features/game-play/combat-abilities-bar.tsx` | NEW | 160 |
| `packages/app/src/features/editor/sections/combat-encounters-section.tsx` | NEW | 250 |

**Type contracts** (abbreviated):

```typescript
export interface PartyMember {
  id: string;
  name: string;
  stats: { hp: number; maxHp: number; attack: number; defense: number };
  abilities: string[];  // ability ids
  position?: { x: number; y: number };
}

export interface Ability {
  id: string;
  name: string;
  cooldownTurns: number;
  targetType: "self" | "ally" | "enemy" | "area";
  effect: AbilityEffect;  // damage, heal, buff, debuff
}

export interface CombatObjective {
  id: string;
  description: string;
  type: "kill-all" | "survive-turns" | "protect-entity" | "variable-threshold";
  target: string;
  value?: number;
}

export interface CombatState {
  party: PartyMember[];
  enemies: Enemy[];
  objectives: CombatObjective[];
  paused: boolean;
  currentTurn: number;
}
```

**Test matrix**: ability cooldowns, AoE targeting, objective win/lose conditions, pause halts AI tick, party death == lose, objective-complete == win.

**Dependencies**: M1 (clock pauses with combat), ideally M10 (debug visualization).

**Unblocks**: Tingen warehouse raid, ritual-night finale.

**File-conflict awareness**: edits to `resolve-turn.ts` need coordination with anyone using current combat.

**Verification checklist**:
- [ ] Typecheck + tests pass (25+ cases)
- [ ] Author a 3-party-member encounter with 2 objectives
- [ ] Combat triggers, pause halts AI, resume resumes all units
- [ ] Abilities fire with correct cooldowns
- [ ] Winning/losing objective ends combat with correct result

**Out of scope**: animation polish (Unity VFX), line-of-sight, terrain modifiers, multiplayer co-op combat.

---

### M9 — Authoring UIs (bundled with each milestone)

This isn't a standalone milestone; each milestone above includes its authoring UI. Tracked separately only for visibility.

**Per-milestone authoring deliverables** (restated):
- M1: playtest panel shows clock/phase (covered)
- M2: `schedules-section.tsx` (covered)
- M3: `world-manager-section.tsx` (covered)
- M4: `clues-section.tsx` + investigation board UI (covered)
- M5: `rumors-section.tsx` (covered)
- M6: `cutscenes-section.tsx` (covered)
- M7: `occult-tools-section.tsx` (covered)
- M8: `combat-encounters-section.tsx` (covered)

---

### M10 — Observability / Debug Tools

**Why this matters**: GDD 36.4 flags this as mandatory. Without it, authors can't debug NPC behavior. Parallel agents can't see what each other is producing.

**Design decisions** (locked):
- Read-only panels in studio editor.
- Subscribe to existing WS channel; server streams entity runtime state.
- No schema changes; just expose existing `EntityRuntimeState` to UI.

**Deliverables**:

| File | Action | ~LOC |
|---|---|---|
| `packages/bridge/src/game-session.ts` | EDIT (stream entity state over WS) | +60 |
| `packages/sdk-core/src/protocol.ts` | EDIT (add `SEntityState` message) | +30 |
| `packages/app/src/features/studio/panels/npc-state-inspector-panel.tsx` | NEW | 300 |
| `packages/app/src/features/studio/panels/event-log-panel.tsx` | NEW | 180 |
| `packages/app/src/features/studio/panels/rule-trace-panel.tsx` | NEW | 200 |

**NPC State Inspector content**: per-entity card showing `currentGoalLine`, schedule state, `fatigueLevel`, `stance`, `relationshipScore`, most-recent 3 observations, most-recent 3 heardFromOthers, most-recent `ai_decide` output + reasoning.

**Event Log**: streaming feed of all events with filterable types + source.

**Rule Trace**: for each rule fire, show WHEN matched, conditions result, actions fired, cooldown state.

**Dependencies**: none.

**Unblocks**: ALL other milestones for authors. External dev usability.

**File-conflict awareness**: `game-session.ts` is NPC hot zone. Coordinate.

**Verification checklist**:
- [ ] Typecheck + tests pass
- [ ] Studio panels render with no data in empty world
- [ ] Playtest with NPCs → inspector shows live state
- [ ] Advance NPC via `ai_decide` → state updates in inspector
- [ ] Fire a rule → appears in rule trace

**Out of scope**: time-travel debugger (scrub turns), distributed tracing, performance flamegraphs.

---

### M11 — Unity UI Migration (Thin-Renderer Boundary)

See the dedicated scope in TODO.md ("Unity UI migration to React") and the detailed breakdown in Section 2 M11 above. No duplication needed here — the whole spec is already written. Summary:

- ~2-3 weeks, three parallel-shippable weeks
- Depends on UI Panel Authoring Phase 1 landing first
- Migrates `GameHUD.cs` / `GameUI.cs` / `InventoryUI.cs` / dialogue-choice part of `DialogueUI.cs` → React
- Keeps world-anchored `DialogueUI.cs` speech bubbles + `VfxManager.cs` + `AudioManager.cs` in Unity

---

## 12. Handoff prompts (copy-paste to other agents)

### Handoff prompt — M1 (Game Clock)

Paste this into the other Claude agent's opening message:

---

> You are an engineer on the Yumina team. Pick up milestone M1 (Game Clock + Day Phases).
>
> **Read first, in order:**
> 1. `CLAUDE.md` — project conventions, tech stack, commands, hard requirements
> 2. `tingen_engine_gap_analysis.md` — **Section 0** "For implementers", then **Section 11, M1 sub-section**
> 3. `packages/engine/src/systems/types.ts` + `packages/engine/src/systems/registry.ts` — how to register a system
> 4. `packages/engine/src/timer/runtime.ts` — an existing runtime you're parallel to; use as reference pattern
> 5. `packages/engine/src/__tests__/timer-runtime.test.ts` — test patterns to match
>
> **Your deliverable:** M1 complete per the Section 11 plan. Full list of files in Section 8 `M1 clock:` block. Ship when all verification checklist items are green.
>
> **Hot zones — do not touch:**
> - `packages/bridge/src/ai-director.ts` — claimed by NPC intelligence agent
> - `packages/bridge/src/world-room.ts` — claimed by NPC intelligence agent
> - `packages/bridge/src/scene-generator.ts` + `blueprint-generator.ts` — claimed by Phase C agent
> - `packages/sdk-core/src/scene-blueprint.ts` — claimed by Phase C agent
> - `packages/engine/src/spatial/sceneCompiler.ts` — claimed by Phase C agent (doesn't exist yet)
> - `config/tile-prompts/`, `packages/app/public/buildings/`, `scripts/generate-tile-biome.py` — tile regen in progress
>
> **Safe files for you to touch:**
> - All new files listed in M1 section 11 deliverables
> - `packages/engine/src/index.ts` (only add export lines; Phase C agent is also adding lines — both appending is fine)
> - `packages/engine/src/systems/registry.ts` (only register CLOCK_SYSTEM)
> - `packages/app/src/features/studio/panels/playtest-panel.tsx` (only add a phase-display line)
>
> **Output requirements before declaring done:**
> - `pnpm --filter @yumina/engine typecheck build test` — all green, 9+ clock tests pass
> - `pnpm --filter @yumina/app typecheck` — clean (only your one-line edit)
> - Verification checklist items in Section 11 M1 — all checked
> - Log shipped work to `RECENT_CHANGES.md` under `## 2026-04-20 — M1 Game clock`
> - DO NOT commit unless explicitly asked
>
> **If stuck:** use `AskUserQuestion` to ask the user. Quote the exact ambiguity. Do not guess.
>
> **Before you start, confirm:**
> 1. You've read `CLAUDE.md` (reply with one sentence summarizing the key "Hard Requirements")
> 2. You've read Section 0 + Section 11 M1 of `tingen_engine_gap_analysis.md`
> 3. You understand the hot zone list and will not touch those files
>
> Then begin. Ship in ~1-2 focused days.

---

### Handoff prompt — M3 (World Manager)

*(Same structure as M1; swap milestone details, file lists, test case counts, hot zone info remains identical.)*

### Handoff prompt — other milestones

For M4 / M6 / M7 / M8 / M10, adapt the M1 prompt by:
- Swapping the milestone reference in Section 11
- Updating the "Read first" list to reference that milestone's key existing patterns
- Keeping the hot zones block identical
- Adjusting expected time budget per the Section 2 scope estimate

For M2 / M5 (NPC-agent-adjacent), add a coordination note: "This milestone edits `ai-director.ts` — coordinate the timing with the NPC intelligence agent before committing. Branch-based PR flow is mandatory."

---
