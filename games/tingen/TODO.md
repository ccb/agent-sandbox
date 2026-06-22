# Tingen — Game TODO

Living task list for the Godot game in [`tingen/`](tingen/). Grounded in
[`tingen_mystery_pixel_game_gdd.md`](tingen_mystery_pixel_game_gdd.md) (GDD),
[`tingen_story_and_system_md.md`](tingen_story_and_system_md.md) (story/system),
[`tingen_npc_roster.md`](tingen_npc_roster.md) (cast),
[`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) (running decisions log — the freshest
source of truth), and the two engine docs
([`tingen_engine_gap_analysis.md`](tingen_engine_gap_analysis.md),
[`tingen_engine_extensibility_plan.md`](tingen_engine_extensibility_plan.md)).
Section refs like "§8.3" point at the GDD; "M3" refs point at the gap-analysis
milestones.

The **NPC-agent architecture** is grounded in a separate sibling repo,
`../agent-sandbox` — the shared LLM-agent research framework (Generative Agents +
ReAct) that Tingen is the Godot game application of. See
[NPC agent architecture](#npc-agent-architecture--align-with-agent-sandbox).

---

## Read this first — the pivot, and how the docs map

- **Godot 4.6 (GDScript) is the build target.** The engine docs describe a
  web/TypeScript "Yumina" engine with milestones M1–M11; none of those packages or
  file paths exist here. Treat the milestones as a **system-design bible** — the
  contracts (state shapes, enums, thresholds, event names, build order) port to
  Godot; the TS/Unity/React specifics do not.
- **The project pivoted on 2026-06-08** (GDD §0.1) from a *fixed detective mystery*
  to an **open-world, real-time LLM-agent simulation**: no scripted mystery line, a
  cult that genuinely tries to summon a descending god and *succeeds if unopposed*,
  per-NPC autonomous agents, and a deterministic Godot sim + external Python sidecar
  for the LLM brains. **Where the GDD body text (§9/§11/§19 detective framing)
  conflicts with §0.1, §0.1 wins.**
- **The Gray-Fog Hypothesis / deduction board is CUT** (§0.1). Occult tools +
  inventory survive but are demoted to *perception + action*. Do not rebuild the
  "submit your conclusion" board (see [Cut / out of scope](#explicitly-cut--out-of-scope)).
- **The NPC agents descend from `../agent-sandbox`.** That sibling repo is the
  shared research framework (Stanford *Generative Agents* / "Smallville" + the
  **ReAct** Reason+Act pattern); its roadmap names Tingen's track as the **2D Godot
  front end**. Tingen already re-implements the framework's core contracts in
  GDScript — when extending the agent layer, mirror agent-sandbox rather than
  inventing a parallel design (see the dedicated section below).

---

## Where we are (2026-06-17)

The data-driven **backend is real and well-tested** — `tests/run_tests.gd` is a
dependency-free headless runner with **500+ assertions across ~80 tests, no skips**.
The thin spots are almost all **presentation, integration, and content**, not core
systems.

**Reachable world today:** boot is [`scenes/Main.tscn`](tingen/scenes/Main.tscn) →
`GameController` mounts **CityBlocks** (hand-authored ~50-building hub) + **HUD**.
Door graph is just:

```
CityBlocks ⇄ NighthawksHQ   (Captain dialogue, case board, records)
CityBlocks ⇄ UniversityArchive   (Finch dialogue, archive clues)
```

**System status snapshot** (DONE = real & wired · PARTIAL = backend exists, surface
thin/orphaned · MISSING):

| System | Status | Notes |
|---|---|---|
| World sim + 6 stages + pressures + seeded slots (≈M3) | DONE | `WorldManager.gd`, 60 s refresh |
| Game clock + day-phase + day/night tint (≈M1) | DONE | `Clock.gd`, `DayNightTint.gd` |
| NPC schedules + navmesh pathfinding (≈M2) | DONE | `NPC.gd`, baked nav region |
| Dialogue (topic/clue/faction-gated, effects) (≈M4) | DONE | `DialogueManager.gd`, 4 trees |
| Clues + Investigation Board | PARTIAL | flat gallery only (board OK; deduction CUT) |
| Occult tools framework (4) (≈M7) | PARTIAL | gating/cost real; **readings are canned strings** |
| Combat (≈M8) | PARTIAL | headless `auto_resolve()` only; **no interactive scene** |
| Prayer / ritual panels | DONE | `PrayerService.gd`, `RitualPanel.gd` |
| Cult summoning countdown + climax | DONE | `SummoningPlan.gd`, drives endgame |
| Agent runtime + LLM sidecar substrate | PARTIAL | ReAct-style beat loop real, mirrors agent-sandbox; **brain not fed the live player**; no memory/knowledge/reflect yet (see [agent section](#npc-agent-architecture--align-with-agent-sandbox)) |
| Inventory / items | DONE | 11 items, save/load tested |
| Map / district panel | DONE* | `DistrictMap.gd` (*tracker reads a stale pos — see T1.3) |
| Save / load | DONE | 11 subsystems round-tripped |
| Dev console + debug log (≈M10) | DONE | backtick console, `L` log |
| Toasts / notifications | DONE | wired to `event_fired` + pressure-threshold + stage signals, mounted in HUD; now tested (`a13590b`) |
| Endgame (3 bands) | DONE | pure `EndGameResolver.gd` |
| Cutscene / intro (≈M6) | PARTIAL | `IntroCard` + `IntroRoom.tscn` built but **orphaned** |
| Rumor propagation (≈M5) | MISSING | research-flavored, deferred |

---

## Design canon — locked constraints any task must respect

These are settled in [`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md); don't relitigate
without a reason:

- **Architecture:** autoload singletons + data-driven JSON in [`tingen/data/`](tingen/data/).
  Everything must stay **headless-testable** and **save/load-serializable**.
- **`ActionCommit` is the single seam** agents mutate the world through;
  **`EventBus`** is the single append-only log. New mechanics belong there.
- **Invariant:** "the cult is never exposed by chance" — exposure gates on player
  involvement, enforced in `Critic.review` + `Overseer.allows_exposure()`.
- **Pressure vars are canon (5):** `corruption, panic, fatigue, cult_readiness,
  attention` (0–100). `stability` is *derived*, not stored. `player_trust` /
  `cult_affinity` were dropped.
- **Coordinates:** map-image space is canonical; world space derives via
  `CITY_SCALE = 3.5`. `WAREHOUSE_MAP (515,372)` (the rite site) is a locked anchor —
  geometry bends to it.
- **The world is hand-authored in the editor** (`CityBlocks.tscn`), not procedural.
  Everything should be viewport-editable.
- **LLM nondeterminism is quarantined** in the Python sidecar; the engine sends
  snapshots, holds no API key, re-validates every action, and **boots offline**
  (`AmbientSidecar`).
- **No new third-party addons;** the test runner is the bespoke `tests/run_tests.gd`,
  not GUT.
- **No git commits without the user's explicit OK.**

---

## Next up (prioritized)

**Scope note (2026-06-17):** the LLM/agent-brain work is **deferred** (see
[NPC agent architecture](#npc-agent-architecture--align-with-agent-sandbox)). Tiers
1–3 below are **all Godot-game-specific and need no NPC intelligence** — NPCs run on
their deterministic schedule/ambient layer, which carries the entire vertical slice.
This is the near-term roadmap.

### Tier 1 — Close the loop (make the slice playable end-to-end)

1. ✅ **DONE — landed `5ccf236` (archive content) + `fb7bea0` (player facing).**
   Ledger Finch dialogue + 4 archive clues + the 4-way player texture swap; suite
   green at 533. (`UniversityArchive.tscn` + its wiring test were already committed
   in `f9d9c94`.)

2. **Wire the intro — IN PROGRESS (yours, uncommitted; not landable yet).** You're
   already migrating the boot to `IntroRoom → City.tscn → interiors` (new
   [`City.tscn`](tingen/scenes/City.tscn) + [`Portal.gd`](tingen/src/Portal.gd), and
   `Main.tscn` now boots IntroRoom whose door targets City). **Blocker to landing:**
   `City.tscn` is an early sketch — placeholder `*_test` art, only a chapel→cathedral
   `Portal`, and **no doors to NighthawksHQ / UniversityArchive and no warehouse/rite
   site**. Committing it as the live hub would regress the playable loop. To finish:
   add City portals to the two interiors (+ the rite site), and repoint the interiors'
   return doors `CityBlocks → City`. (`CityBlocks` stays as the NPC-AI sandbox.)

3. ✅ **DONE — landed `a13590b`.** `GameController._process` now pushes the live
   player position into `AgentRuntime.player_position` (`sync_player_position`), so
   the District-map dot follows the player and the near-player active set is pre-wired
   for the deferred agent brain. Covered by `_test_player_position_sync`.

4. ✅ **Already wired — verified + tested in `a13590b`.** Correction: the earlier
   audit was **wrong**. [`Toasts.gd`](tingen/src/Toasts.gd) already subscribes to
   `EventManager.event_fired` and `WorldManager.pressure_threshold_crossed` /
   `stage_advanced` and is mounted in HUD, so events, threshold crossings, and stage
   advances **already surface as toasts**. The only gap was test coverage — now added
   (`_test_toasts`: connections + one-card-per-signal + the `MAX_VISIBLE` cap).

### Tier 2 — Make existing systems real (presentation depth)

5. **Occult tool readings should read true world state (≈M7).** All four
   `_perform()` bodies return hard-coded flavor; only Divination reads the resolved
   slot. Make Residue Sight surface clues at the player's location, Dream Fragments
   inject a real next-turn directive, and Gray-Fog Reconstruction summarize from
   *collected clues* (this is the surviving, demoted use of gray fog — a lead hint,
   **not** the cut deduction board). Keep §12.3 in mind: hint, don't hand over the
   answer.

6. **Interactive combat scene over the headless backbone (≈M8).**
   `CombatEncounter.auto_resolve()` and agent strikes exist but there's no playable
   fight. Wrap it in a real-time-with-pause scene: party-of-1–3, objective-driven
   (interrupt the ritual / hold a chokepoint, *not* kill-all), the §16 tool set
   (revolver / barrier / decoy / spirit-sight / retreat). Ship the light party-of-2
   first (§16 "avoid" — not a bespoke engine).

7. **Investigation Board polish within the flat-gallery scope.** Type/topic filters,
   clue→topic unlock feedback, importance styling. Stay inside the shipped flat
   gallery — the drag-connect node graph is v2.

### Tier 3 — Content & world (the vertical slice)

8. **Finish + wire the Cathedral / Crypt location.** Untracked WIP (`CathedralNave`,
   `CathedralCrypt`, Klein/cathedral asset-gen scripts) is the current active art
   front but isn't in the door graph or any committed plan. Decide its role (likely
   the `ritual_night` setpiece — Brother Cassian) and connect it.

9. **Build one full summoning thread, `disturbance → ritual_night`.** Wire the cast
   into a single **escalating-reveal cell** — `npcs.json` has Voss/Dalia/Orin/Pell;
   the roster adds Crane → Vire → Kell → Cassian (butcher→physician→deaconess→curate).
   Follow "**schedules first, secrets later**": ship them as public schedule-walkers,
   then layer reveal triggers. Orin is the designed turnable waverer.

10. **Author the clues + dialogue that make that thread traceable,** plus the
    end-night escalation beat that pushes `cult_readiness`/`attention` toward the
    climax. This is the §5.2 / §24.1 vertical slice: ~3 reachable interiors, one
    suspect chain, one rite-night, end-to-end in 45–90 min.

### Tier 4 — Bigger bets / research-flavored (tracked, deferred)

- **Real LLM sidecar wiring.** `HttpSidecar` is ready (threaded, 1-beat latency) and
  the Python `agent-sidecar/sidecar.py` scaffold works (stdlib HTTP, Haiku, schema-
  validated, safe-idle fallback, no key logged). Stand it up, set `TINGEN_SIDECAR_URL`
  + `ANTHROPIC_API_KEY`, and harden the prompt (see agent section A4). Prerequisite:
  Tier 1.3 (feed the live player position) so near-player agents actually deliberate.
- **Rumor propagation (≈M5)** — `Rumor { topic, truthfulness, district,
  spread_strength, valence, heard_by[] }`, decay + truthfulness mutation on
  retelling, "overhear" HUD fragment. Research-flavored.
- **Offscreen district resolution (§8.6 / ≈M3)** — tick districts the player isn't
  in; needs determinism + idempotency.
- **Cutscene system (≈M6)** — data-driven `CutsceneStep` timeline for the opening and
  stage-reveal beats (`IntroCard` is a seed).
- **District-keyed ambient audio (§21)** — BGM/SFX on `phase_changed`; skip
  positional 3D audio (§6 "avoid").

---

## Asset pipeline / art production

Art is produced through the Python image pipeline in `asset-gen/` (many in-flight
untracked scripts) and lands in `tingen/assets/` — pixel art, nearest-neighbor
filtering. Sequencing per §6 "avoid": author only the **slice** cast and locations
first, not the whole city. Character sprite-sheet workflow is specced in
[`docs/superpowers/specs/2026-06-08-character-animation-pipeline-design.md`](docs/superpowers/specs/2026-06-08-character-animation-pipeline-design.md)
(4-direction sheets → Godot `SpriteFrames`). These tasks **unblock Tier 3 content**
(NPC cast, cathedral).

**Characters**
- **Klein style redo.** Finalize the canonical look for the protagonist (Klein). The
  in-progress `asset-gen/klein_canon_*.py` scripts (chibi / directions / forward /
  right / fullbody) are this effort; once locked it replaces the current
  `klein_{down,left,right,up}.png` the player now uses (commit `fb7bea0`) and sets the
  house style every other character follows. **Do this first — it's the style anchor.**
- **NPC sprites.** Per-character art for the cast (roster townsfolk + the
  Crane/Vire/Kell/Cassian cult cell), replacing placeholder tinted-`icon.svg` / rect
  NPCs. Must match the locked Klein style. Start with the slice cast only.
- **NPC sprite-sheet creation.** Turn each NPC into a 4-direction (and, where needed,
  animated) sheet and slice into Godot `SpriteFrames`, per the character-animation
  spec. `asset-gen/klein_sheet_4way.py` / `klein_spriteset.py` are the templates to
  generalize from Klein to the cast.

**Environments**
- **Inner-room style redos.** Restyle the interior backgrounds (Klein's room,
  Nighthawks HQ, University Archive) to one consistent look; `klein_room_pipeline.py` /
  `compose_klein_room.py` are the room-composition path.
- **Building separation from the map ref.** Extract individual buildings as discrete
  sprites out of the `tingen_map.png` reference, so the authored world places real
  building art instead of one baked-in map image (`asset-gen/key_building.py` is the
  seed).
- **Building self-segmenting.** Decompose each building image into its layers —
  ground, building body, fence, roof, props — so they can be placed, **Y-sorted**, and
  collided independently (the depth/collision substrate the IntroRoom Y-sort upgrade
  established). `asset-gen/_collidermap.py` / `_quad.py` look like the seeds.

*(Also still pending from the original asset list: swap any remaining stub sprites →
final PNGs, real tileset street/room art, and dialogue portraits. Ambient audio lives
under Tier 4.)*

---

## NPC agent architecture — align with agent-sandbox

> **DEFERRED (decision 2026-06-17).** Hold the LLM agent brain and the A1–A6 ports
> below until `../agent-sandbox` is fully built, then port its finished design
> instead of chasing a moving target. **Until then NPCs run on the existing
> deterministic layer** — `AmbientSidecar` goal-seek + `Agent.tick_fallback`
> schedule-walking — which is enough to populate the city, progress the cult rite,
> and ship the vertical slice. This whole section is *later*; the near-term roadmap
> is the Godot-specific work in Tiers 1–3.

Tingen is the **Godot game application of `../agent-sandbox`** (the shared research
framework: Stanford *Generative Agents* + ReAct). Tingen already re-implements the
framework's core contracts in GDScript — `tingen/data/action_schema.json` is even
shared **verbatim** with the Python sidecar and parity-tested
(`agent-sidecar/schema_parity_check.py`). When growing the agent layer, **port from
agent-sandbox; don't invent a parallel design.**

**What already lines up:**

| agent-sandbox (Python) | Tingen (GDScript) |
|---|---|
| `Agent.decide(observation) → command` | `SidecarBridge.propose(snaps)` per `AgentRuntime` beat |
| `build_npc_context()` / `describe_for()` | `Perception.build_snapshot()` |
| `check_preconditions() → apply_effects()` | `ActionSchema.validate()` + `ActionCommit.commit()` |
| precondition gate + reflect-retry | `Critic.review()` approve/amend/veto + `Overseer` directives |
| `MockReActClient` (offline) | `MockSidecar` / `AmbientSidecar` (offline boot default) |
| `Game.events` / `clock.py` / `to_primitive` | `EventBus` / `Clock` / `to_dict` |

Tingen is in places *ahead* (a narrative `Overseer`/`Critic` director with the
"cult never exposed by chance" invariant; pressures/stages/slots). The ports below
are where agent-sandbox is ahead and Tingen should follow.

**Ports — prioritized:**

- **A1. Per-character knowledge / belief layer.** *Implemented* in agent-sandbox
  (`knowledge.py`, issue #45; design in `docs/design/agent-knowledge.md`): private,
  fallible beliefs that can be incomplete or wrong, plus `secret_topic` **perception
  gating** so a character only perceives what it knows. Tingen's `Perception.build_snapshot`
  is currently omniscient about nearby agents/events. This maps **directly** onto
  Tingen's design: civilians would *genuinely not perceive* cult activity until they
  learn it, instead of the `Critic` blocking exposure after the fact — a cleaner
  expression of the no-chance-exposure invariant and asymmetric knowledge. Port
  `knowledge.py` → a GDScript `Knowledge`/`Belief` on `Agent`, filter
  `build_snapshot`, serialize via `to_dict`.

- **A2. Generative-Agents memory stream.** *Designed* in agent-sandbox
  (`docs/design/agent-memory.md`, Phase 2): `observation / reflection / plan`
  records retrieved by **recency × importance × relevance**, with a reflection
  threshold. Tingen's `Agent` has only a flat `short_memory` (cap 20) + a `plan`
  array — no scoring, no retrieval, no reflection. Port the memory module to
  GDScript; feed retrieved memories into `Perception.build_snapshot`. Biggest single
  uplift to NPC believability.

- **A3. ReAct reflect-retry.** On a schema-reject or `Critic` veto, `AgentRuntime`
  just drops the agent to schedule fallback. agent-sandbox's `decide_and_route`
  instead feeds the failure reason back and re-decides (1 + `max_retries`). Add a
  reflect-retry loop in `AgentRuntime._resolve_proposal` so a rejected proposal gets
  one informed retry before falling back.

- **A4. Constrain the sidecar to legal verbs at generation time.**
  `agent-sidecar/sidecar.py` today sends a text "verb menu" and validates the JSON
  *after* the model replies. agent-sandbox uses a closed-`enum` tool schema
  (`build_choose_action_tool`) so the model can only emit a known verb. Switch the
  sidecar to Anthropic tool-use with an enum over `action_schema.json` verbs;
  keep the post-hoc `validate_action` as the safety net.

- **A5. Tiered goals + persuasion.** agent-sandbox has structured `Goal`s
  (`SHORT/MEDIUM/LONG`) and goal-influencing dialogue (a `heard` buffer that can
  shift goals only if they fit persona). Tingen's `Agent` has a single
  `intent: String`. Promote to tiered goals so the cult cell can hold long-horizon
  aims while reacting short-term; wire dialogue effects to nudge them.

- **A6. Simultaneous resolution + contested resources** *(lower priority — for
  multi-NPC scenes / combat ordering).* agent-sandbox's `turns.py` runs a
  gather → resolve round with phase ordering (`say < go < get < attack`), initiative
  tiebreak, and first-class `conflict` events when two agents claim the same target
  (winner keeps it; loser gets a ranked fallback or informed retry). Tingen's beat
  loop resolves proposals independently with no contention model — adopt this when
  two cultists could race for the same ingredient or when combat needs ordering.

**Prerequisite:** Tier 1.3 (feed the live player position into
`AgentRuntime.player_position`) — without it the near-player active-agent set never
includes the real player, so A1–A5 only ever run on the ambient fallback cast.

**Reference, in `../agent-sandbox`:** `text_adventure_games/npc.py` (the ReAct
core), `knowledge.py`, `turns.py`, `llm_client.py`; design docs under
`docs/design/`; `ROADMAP.md` (the text→agents→memory→Godot ladder).

---

## Explicitly CUT / out of scope (do NOT rebuild)

- **Gray-Fog Hypothesis / deduction board** — CUT (§0.1). Gray fog survives as a
  lead-hint reading (T2.5) and as lore, not a "submit a conclusion" UI.
- **Drag-connect clue node-graph** — v2; the flat gallery is the shipped board.
- **Procedural / true-to-scale city tracing from `tingen_map.png`** — discarded in
  favor of the hand-authored `CityBlocks` grid.
- **Ritual recipe/crafting engine** (ingredient slots only), **carry/weight limits**
  (unlimited chosen), **CJK on-screen labels**, **BBCode escaping of LLM text**, and
  the **full LotM pantheon** — all deferred/declined.

---

## Open questions (tuning — unresolved)

From `DESIGN_DECISIONS.md`, still open: the `stability` formula; whether to force the
intro clock to late-night; whether the 60 s refresh is too slow; the pressure-curve
balance target; one event per refresh vs. several; whether to ever restore
`player_trust` / `cult_affinity`. (The "swap to GUT?" question is effectively
answered: no — bespoke runner stays.)

---

## Repo hygiene (decide keep vs. cull)

- **Dead code:** `CityLayout.gd` + [`data/city_layout.json`](tingen/data/city_layout.json)
  became unused when `LiveDistrict` was retired — kept only as harmless headless
  seams. The `2026-06-15-city-world-to-scale.md` and `2026-06-10-tingen-map-and-districts.md`
  plans are now **stale** relative to what shipped.
- **Orphaned scenes:** `City.tscn`, `CathedralNave/Crypt`, `MapScaleTest.tscn`,
  `ChapelComposeTest.tscn` — none reachable from the live graph (Cathedral is
  intended; the rest are likely cull candidates).
- **~40 untracked `asset-gen/` experiment scripts** + stray `_*.png` captures in the
  working tree — sort into "keep in pipeline" vs. delete.

---

## Milestone traceability (Yumina M1–M11 → Godot status)

| M | System | Status |
|---|---|---|
| M1 | Clock + day phases | DONE |
| M2 | NPC schedules | DONE |
| M3 | World manager + pressure + slots | DONE (offscreen resolution deferred) |
| M4 | Clue model + board (flat) | DONE (deduction board CUT) |
| M5 | Rumor propagation | MISSING (deferred) |
| M6 | Cutscene / intro | PARTIAL (`IntroCard`, orphaned room) |
| M7 | Occult tool framework | PARTIAL (readings canned — T2.5) |
| M8 | Combat v2 | PARTIAL (no interactive scene — T2.6) |
| M9 | Authoring UIs | N/A (use the Godot editor) |
| M10 | Observability / debug | DONE (dev console + log) |
| M11 | UI/renderer split | N/A (single Godot project) |

---

## If we ever go the Yumina route instead

The extensibility plan argues Tingen's systems should ship as a **Yumina plugin** (11
extension points: state stores, events, effect handlers, rule triggers/actions,
behavior actions, entity components, prompt fragments, tick functions, message
handlers, editor sections, UI components), via **Option C**: build clock + schedules
in-engine, extract them as the first example plugins, then build the rest as plugins.
Only relevant if the build target switches from Godot to Yumina — noted so the option
isn't lost. For the Godot build, treat the 11 points as a "keep these seams
pluggable" checklist, nothing more.
