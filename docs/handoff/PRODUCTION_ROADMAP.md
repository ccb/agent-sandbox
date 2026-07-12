# Tingen — Production Roadmap to a Polished Game (2026-07-03)

> ⚠️ **DIRECTION CHANGE (2026-07-03):** Tingen is now an **occult-noir action-RPG roguelite**
> (RPG + open-world + roguelite) per **`tingen_game_direction_v2.md`** — NOT a detective game.
> The **investigation system is DROPPED**. Track D below is being realigned to the v2 direction
> (Sequence/pathway progression, the four-meter push-your-luck system, rumors→leads, the
> roguelite run/meta shell). Items D-old about "cases/deduction/solvability" are **retired**; see
> the "Track D (v2)" note in that section. Tracks B/C/E/F (audio, VFX, UI, feel/ship) are
> largely direction-agnostic and stand. **Read `tingen_game_direction_v2.md` first.**

The engineering-continuity TODO (`TODO_NEXT_AGENTS.md`) is what's *in flight*. This is the rest —
everything Tingen needs to become a shippable indie title rather than a verified tech demo. It was
scoped from the design docs, the codebase, and the production-gap audit (`PRODUCTION_GAPS.md`).

> **Note on provenance:** the deep 5-discipline research fan-out for this roadmap was cut off by
> the Fable credit limit mid-run. This document was written directly by the main loop from the
> codebase + design docs + the completed audit. It is accurate but not exhaustive — a follow-up
> research pass (Opus, `WORKFLOWS.md` §2 template, one researcher per track) should deepen tracks
> B–F and is itself item **A0** below.

## How to read this

Every item: **what** (spec), **now** (current state with evidence), **wire** (the code seam),
**done** (acceptance), **effort**. `[USER]` = needs a user decision before an agent starts.
Execution follows the standard discipline: TDD + review-re-edit per `TESTING_WORKFLOW.md`; art via
the asset pipelines in `WORKFLOWS.md` §4; single-writer on `.tscn`; local commits, no push. Audio
is the one track with **no existing assets and no generation pipeline** — it needs a sourcing
decision first (item B0).

Cross-references to the audit use its numbers (e.g. GAP-2.10). Where the audit already specced a
blocker, this roadmap points at it rather than duplicating.

---

## Track A — Engineering continuity (already queued)

Keep `TODO_NEXT_AGENTS.md` P0–P3 as-is; the highlights, one line each:
- **A0** — deepen this roadmap with the 5-track research fan-out that got cut off (WORKFLOWS.md §2).
- **P0.1** city-fill rework (user-flagged; diagnosis in `fill_diagnosis_verdicts.json`).
- **P0.2/P0.3** interiors landed (`f0ae6ac`); play-test portals; close the overnight loop + tag.
- **P1.2** the audit's 13 critical blockers (`PRODUCTION_GAPS.md` §2/§6) — several are also game-
  completeness items and are cross-listed below so they aren't double-worked.
- Reload/ammo pickups, NPC cost enforcement, Yumina port, doomsday pacing.

---

## Track B — Audio & Music (greenfield: 0 `AudioStream` refs in the project)

**B0 [USER] — Audio sourcing & licensing decision.** *what:* pick the pipeline — CC0/CC-BY packs
(freesound, Kenney, GameSounds) + a music tool (e.g. licensed loops, or a generative service) vs
commissioned. There is no image-gen equivalent for audio; this gates all of B. *now:* zero audio
in the repo. *done:* a decision + a `assets/audio/` layout + an attribution file. *effort:* hours
(decision), then ongoing sourcing.

**B1 — Audio bus + AudioManager autoload.** *what:* a master/music/sfx/ambience bus layout, an
`AudioManager` autoload with `play_sfx(id, pos?)`, `play_music(track, crossfade)`,
`set_ambience(phase|room)`, volume from settings (Track E). *now:* none. *wire:* new autoload in
`project.godot`; EventBus subscriber for reactive SFX. *done:* a test scene triggers each bus;
volumes persist. *effort:* days.

**B2 — Combat SFX.** *what:* per-ability cast/telegraph/impact/dodge/transform stingers, driven by
the existing combat events (`ability_cast_started`, `agent_attacked`, `transformed`,
`ability_cast_interrupted`). *now:* events fire silently. *wire:* `AudioManager` subscribes to
`EventBus` combat events; ids on abilities.json (add optional `sfx` field, mirrors the Yumina
`sfxId` the spec already notes). *done:* a live fight is audibly readable with eyes closed for
telegraph→impact. *effort:* days.

**B3 — World ambience per phase & room.** *what:* a day/night/rain city bed that crossfades on
`Clock.phase_changed`; per-interior ambience (tavern murmur, warehouse drips, cathedral reverb).
*now:* `Clock` emits `phase_changed`; no listener plays sound. *wire:* `AudioManager.set_ambience`
on phase change + on room enter (RoomGraph/GameController transitions). *done:* phase/room changes
are audible; no clicks on crossfade. *effort:* days.

**B4 — UI & feedback SFX.** *what:* panel open/close, clue-pinned, button hover/confirm,
inventory pickup, save chime, footsteps (surface-aware later). *wire:* panel toggles + `add_item`
+ SaveManager. *done:* every interactive UI action has feedback. *effort:* days.

**B5 — Music direction & adaptive score.** *what:* themes for exploration (per-district feel),
tension (near a deed site / suspicious), combat (layered — intensify on transform), the ritual
climax, and 3 ending themes. Godot adaptive-music tech: stem layering via multiple synced
`AudioStreamPlayer`s or `AudioStreamInteractive` (4.6). *now:* none. *wire:* `AudioManager`
state machine keyed to WorldState pressures (attention/panic) + combat mode + `summoning_climax`.
*done:* music responds to threat/phase without hard cuts. *effort:* weeks. *[USER]* on the music
source (B0).

---

## Track C — VFX, Animation & Cinematics

**C1 — Wire combat VFX (GAP-2.10: combat is currently visually invisible).** *what:* give
projectiles, zones, hits, dashes, and transforms their sprites/particles. Assets EXIST and are
orphaned: `assets/fx/{bullet_tracer, charm_glyph, dash_afterimage_wisp, hit_spark_1/2,
ichor_splatter_1/2, icon_*}.png` + `assets/fx/flipbooks/`. *now:* `scenes/CombatProjectile.tscn`
and `CombatZone.tscn` have **no texture/sprite/modulate** (verified); the bullet just moves
invisibly. *wire:* add Sprite2D/GPUParticles2D to the projectile/zone scenes reading an
`fx`/`vfxId` field off abilities.json; spawn hit_spark on `agent_attacked`, ichor on damage,
afterimage on dash, a transform burst on `transformed`. *done:* a screenshot of a live fight shows
the bullet, the charm zone, hit sparks, and the transformation. *effort:* days. **This is the
single highest-impact polish item — combat is the showcase and it can't be seen.**

**C2 — Hit-stop, hit-flash, screen-shake, damage feedback.** *what:* brief freeze-frame on
meaningful hits, white-flash modulate on the struck sprite, camera shake (budgeted, toggleable —
Track E), optional floating feedback. *now:* damage applies with no feedback (GAP feel). *wire:*
`CombatExecutor` damage application → a `CombatFeedback` helper + the camera. *done:* hits feel
impactful in a playtest; shake respects the accessibility toggle. *effort:* days.

**C3 — NPC & monster animation wiring.** *what:* play the on-disk strips. `assets/anim/` has
`{bieber_monster, cultist_robed, wraith_shadow}_{attack_side, death_down, hurt_down}.png`. *now:*
`_play_anim` is wired in `Player.gd` and `CombatExecutor.gd` but **NPC.gd is not** in the anim
call sites (verified) — cultist_robed/wraith_shadow strips are likely unplayed; walk cycles for
the 19 NPCs are unconfirmed. *wire:* `AnimatedSprite2D`/`SpriteFrames` on NPC.tscn; map states
(idle/walk/attack/hurt/death) to strips; the monster (bieber) form-swap should swap SpriteFrames.
*done:* NPCs animate on the correct states; the butcher fight shows attack/hurt/death frames.
*effort:* days–weeks (depends how many walk cycles must be generated).

**C4 — Environmental & ambient VFX.** *what:* chimney smoke, lamp glow at night, rain, ritual
glow at the crypt altar, fog. *now:* day-night tint exists (`Clock`); no particles. *wire:*
GPUParticles2D on City.tscn landmarks + a phase-gated lamp shader. *done:* the city feels alive
across phases in screenshots. *effort:* days.

**C5 — Cinematics & transition wire-up.** *what:* the intro cinematic, the cathedral establishing
shot, and **three ending cinematics** (one per EndGame outcome). *now:* `cathedral_cinematic.png`
and `IntroRoom.tscn` + `IntroCard` exist; `test_scene_fade.gd` covers fades; EndGame raises a
text overlay only. *wire:* a `Cinematic` player (Ken-Burns pan over image-2 stills + text + music
cue, vs actual `VideoStreamPlayer` files — **[USER] decision**: stills are cheap/on-budget, video
needs external production). Hook EndGame's three branches (and the new cult-stopped ending, D-track)
to distinct cinematics. *done:* each ending plays a distinct cinematic; the intro plays on a real
new game. *effort:* days (stills) / weeks (video). *[USER]* on stills-vs-video.

**C6 — Boot-flow fix (GAP-2.8: game boots into dev City.tscn, orphaning the intro + 3 clues).**
*what:* boot into a proper new-game flow (title → intro → city) instead of `main_scene=City.tscn`.
*now:* `project.godot run/main_scene="res://scenes/City.tscn"`. *wire:* a `Main.tscn`/boot
controller (Main.tscn exists) + the intro scene + the 3 orphaned opening-lead grants. *done:* a new
run plays the intro, grants the opening leads, and is playable end-to-end from a cold boot.
*effort:* days. (Cross-listed: audit blocker + cinematics dependency; ties to D4 leads + D5 run shell.)

---

## Track D — Content & Systems (v2: RPG-roguelite, per `tingen_game_direction_v2.md`)

> **REALIGNED 2026-07-03.** The old Track D (cases / deduction / solvability / investigation) is
> **retired** with the investigation system. The game is now an action-RPG roguelite; this track
> is its content + the net-new systems the direction needs. All of it reuses built machinery
> (combat, ability/kit schema, item-backed weapons, LLM NPCs, the summoning engine, dynamic
> slotting). Read the direction doc first — it has the full rationale for each system below.

**D1 — Sequence/Pathway progression (the RPG spine).** *what:* the LotM-faithful advance loop —
hunt a same-pathway Beyonder → harvest its Characteristic → digest via an "acting" ritual (spikes
Madness) → gain/upgrade a tier of abilities. Three starting pathways = three builds mapping to
authored kits: Marauder (guns: revolver_shot/dash), Seer (paper_charm + "see the monster beneath"
sight), Beast (cleaver/charge/blood_frenzy + `assume_form` as a player tool). Demo scope: Seq 9→6.
*now:* ability/kit schema + item-backed weapons + `assume_form` all built; no progression layer.
*wire:* a `Progression`/`Sequence` autoload over `AbilityDB`/`ItemDB`; Characteristic drops on
kill; the acting ritual gates Madness (§D3). *done:* a run advances a pathway tier and the kit
grows. *effort:* days–weeks. **The core net-new RPG system.**

**D2 — The four-meter push-your-luck system (Doom / Madness / Notice / Heat).** *what:* replace
the GDD's 5 flat pressures with the direction-v2 set (see its §3): Doom (world clock → Ritual
Night), Madness (player control → lose-control fail = become a monster), Notice (Beyond hunters
spawn), Heat (Nighthawks hunt you). *now:* `WorldState.gd` has corruption/panic/fatigue/
cult_readiness/attention — keep corruption→Doom, attention→Notice, ADD Madness+Heat, drop
fatigue, fold panic into derived flavor + cult_readiness into Doom's fill. *wire:* WorldState
rework + EventBus hooks (power use → Notice/Heat/Madness; cult progress → Doom). *done:* the four
meters drive spawns/hunters/climax and are legible on the HUD. *effort:* days. **The tension core.**

**D3 — Madness & loss-of-control (the LotM signature risk).** *what:* Madness rises with Sequence
advancement, Characteristic ingestion, and heavy `assume_form`/high-tier use; falls via the
"acting" ritual / rest / calming items. Max = you lose control, `assume_form` fires on the PLAYER,
run ends (canon: Ray Biber → the butcher we already model). *wire:* a player-side reuse of the
exact transform path the butcher uses. *done:* pushing power too hard ends a run as a monster.
*effort:* days.

**D4 — Rumors → Leads (the open-world quest system; reuse the board UI).** *what:* LLM NPCs
surface leads via conversation + ambient chatter → each lead points at an emergent encounter
(hidden Beyonder / cult courier / fallback site). No map markers; the living city is the compass.
Repurpose `InvestigationBoard.gd` as the **Leads board** (don't delete). *now:* converse route +
NPC personas + the board UI all exist; clues.json is butcher-specific. *wire:* a lead-surfacing
hook on the converse/ambient path + the GM slotting leads per run (dynamic slotting §8.5). *done:*
you find the next fight by talking to the city. *effort:* days–weeks. **The open-world system.**

**D5 — The roguelite run & meta shell.** *what:* run = a few in-game days to Ritual Night; ends on
death or loss-of-control; Ritual Night climax = interrupt the descent at a canon interrupt point
(kill celebrant / destroy vessel / break altar / kill the avatar in its delayed-transformation
window — canon §⑦). Meta: unlock pathways, keep Beyonder-knowledge, account level, city reshuffles
per run; win → harder ascension cycle. *now:* summoning engine + EndGame + dynamic-slotting
groundwork exist; no run/meta framing. *wire:* a `Run`/`Meta` shell around the existing
world+EndGame; slotting per run. *done:* die/win → meta persists → next run differs. *effort:*
weeks. **The roguelite system.**

**D6 — Adversary & monster content (3–5 lost-control Beyonder archetypes).** *what:* new
combat_forms + reflex tables + Characteristic drops (tagged by pathway, feeding D1) + the
face-they-wear among the NPC population. LotM-flavored, fitting the canon (a Sailor-pathway drowned
thing on the docks, a Spectator mesmerist, a Corpse-Collector in the almshouse). All in the
existing data schemas (npcs.json/combat_forms.json/abilities.json/deeds.json). *now:* only the
butcher. *wire:* pure data + art; each reuses the whole combat stack + a combat_sim scenario.
*done:* each is a distinct fight + a distinct Characteristic for progression. *effort:* days each.

**D7 — Ritual Night boss & the descent climax.** *what:* the two-stage descent as a boss with the
canon counterplay — avatar lands (Seq-1 outpost) → delayed-transformation window → true entity
lands (= loss/doomsday) unless you kill the avatar in-window. Models directly on `assume_form` +
a timed window. *now:* summoning climax fires `summoning_climax`; no boss. *wire:* a boss encounter
on the climax hook using the combat stack. *done:* Ritual Night is a real, winnable boss fight.
*effort:* weeks.

**D0 [USER] — confirm the v2 direction & vertical-slice scope** (§9 of the direction doc: one
pathway/Hunter, one cycle to one Ritual Night, butcher + cult content, the four meters, leads,
one death→meta loop). *effort:* hours.

---

## Track E — UI/UX & Meta

**E1 — Visual design language for the panels.** *what:* a Victorian occult-dossier aesthetic
matching the painted city — a shared theme (fonts, frames, paper/ink palette, iconography). Icons
can be image-2 generated (icon budget exists; `assets/fx/icon_*` shows the style). *now:* all
panels are code-built `Control`s with default styling (`InvestigationBoard, InventoryPanel,
RitualPanel, PrayerPanel, CultProgressPanel, GMPanel, ModelPanel, DialoguePanel, CombatHUD`).
*wire:* a Godot `Theme` resource + per-panel restyle; `tingen_ui_panel_authoring_plan.md` is the
existing design intent. *done:* panels share a cohesive look in screenshots. *effort:* days–weeks.

**E2 — Title screen / main menu.** *what:* new game / continue / settings / quit, with the painted
city as backdrop + music (B5). *now:* none (boots straight into City.tscn — GAP-2.8). *wire:*
`Main.tscn` boot controller → menu → new-game flow (ties to C6). *done:* a real front end.
*effort:* days.

**E3 — Pause menu & settings.** *what:* pause (resume/settings/quit-to-menu) + settings: audio
sliders (B1), keybind remap, resolution/window mode, text size, screen-shake toggle, colorblind-
safe telegraph/clue colors. *now:* none; `EndGame` uses `process_mode=ALWAYS` as the pause
precedent. *wire:* an `InputMap`-remap UI + a settings resource persisted like saves. *done:*
settings persist and take effect. *effort:* days.

**E4 — Save/load UX.** *what:* a player-facing save/load flow — slots, autosave cadence, a load
menu. *now:* `SaveManager.gd` exists (engine-level) but the player-facing flow is unclear; GAP-2.12
found save/load loses the rite economy (fix that too). *wire:* SaveManager + a slots UI + autosave
hooks (phase change / room enter). *done:* a player can save, quit, reload, and continue with no
state loss (incl. mid-fight per COMBAT_SPEC §8.1 and the rite economy). *effort:* days.

**E5 — Onboarding / tutorialization.** *what:* teach movement, panels, the clue loop, combat, and
prayer — ideally diegetic (the intro room as a tutorial). *now:* IntroRoom exists but isn't the
boot scene; no guidance. *wire:* intro sequence (C6) + contextual first-time prompts. *done:* a
new player can reach the first clue and survive the first fight unaided. *effort:* days.

**E6 — Death/downed & ending screens.** *what:* a proper player-downed flow and polished ending
screens (tie to C5 cinematics + the new cult-stopped ending D2). *now:* EndGame raises a text
overlay; player-downed path exists (M5) but is unpolished; GAP-2.11 = stopping the cult has NO
ending (softlock). *wire:* EndGameResolver branches + cinematics. *done:* every win/lose path
resolves to a screen; no softlock. *effort:* days.

**E7 — Accessibility & localization readiness.** *what:* remappable keys (E3), colorblind-safe
combat/clue colors, screen-shake + hit-flash toggles, a dyslexia-friendly font option; extract UI
strings for future localization (are they hardcoded? — audit/verify). *now:* keys are fixed in
project.godot; colors hardcoded; strings inline. *done:* a baseline a11y pass + a string table.
*effort:* days.

**E8 — Controller support.** *what:* extend the InputMap with gamepad bindings + UI focus
navigation. *now:* keyboard/mouse only. *done:* the game is playable on a gamepad. *effort:* days.

---

## Track F — Game Feel, Performance & Ship-readiness

**F1 — Camera & game feel.** *what:* camera smoothing, combat framing/lookahead, interaction
affordances (outline/prompt on interactables), night-fight readability (tint vs telegraph
contrast — pairs with C1/E7). *now:* basic camera in Player/City scenes; no affordances. *done:*
movement and interaction feel responsive in a playtest. *effort:* days.

**F2 — Performance & soak.** *what:* hold 60fps with 19 NPCs + simultaneous fights; bound
EventBus/PlayLog growth over a multi-hour session; a headless soak test (run the sim N game-days,
assert no leak/no drift). *now:* `AgentRuntime` staggers beats (stagger_k=2); EventBus growth
unbounded over long sessions (audit). *wire:* an EventBus ring/prune + a `tests/soak_sim.gd`.
*done:* a 4-game-day headless soak stays flat on memory and deterministic. *effort:* days.

**F3 — LLM cost ceiling & degradation ladder.** *what:* a per-session/per-beat token budget with
graceful degradation to the ambient brain when exceeded or on API failure. *now:* GAP-2.13 found
API failure is masked as a valid "idle" so the ambient fallback never engages; no budget cap.
*wire:* HttpSidecar error classification + a budget guard + fallback trigger. *done:* an API
outage or budget exhaustion transparently drops to ambient; a test proves it. *effort:* days.

**F4 [USER] — Distribution model for the LLM.** *what:* players don't run sidecars. Decide:
(a) bundled ambient-only demo (no key needed), (b) bring-your-own-key, (c) hosted sidecar. This
shapes E2/F3 and the whole "can anyone else play this" story. *now:* the game requires a local
sidecar for LLM behavior; ambient works without one. *done:* a chosen model + its plumbing.
*effort:* hours (decision) → days–weeks (implementation).

**F5 — Export, branding & ship checklist.** *what:* macOS (at least) export preset, app icon,
window title/branding, version stamping, a license/credits screen (gpt-image-2 asset provenance +
LotM-inspiration attribution), and a **LICENSE file + repo-visibility decision** (GAP-2.7: the
repo is PUBLIC with no license). *now:* no export preset, no icon, no LICENSE, repo public.
*done:* a runnable exported build + a credits screen + a license decision. *effort:* days.
*[USER]* on license + public/private.

---

## Suggested phase ordering (dependency-aware milestones)

Quick-wins and `[USER]` decisions surface early so nothing blocks later.

- **M-A (now, engineering):** finish Track A — fill rework (P0.1), portal play-test, close the
  overnight loop + tag. Land the audit's non-content blockers (dialogue threading GAP-2.3, ambient
  fallback GAP-2.13, restart leak GAP-2.9).
- **M-B (make it visible & audible — highest polish ROI):** **C1** (wire combat VFX — the showcase
  is invisible), **C2** (hit feedback), **B0→B1→B2** (audio pipeline + combat SFX). One playtest
  after: the combat demo now looks and sounds like a game.
- **M-C (make it a game, not a scene):** **C6/E2** (boot flow + title screen), **E3/E4** (pause +
  save UX), **E6 + GAP-2.11** (endings incl. the missing cult-stopped one — kills the softlock),
  **B3** (world ambience). This is the "someone can start, play, win, and quit" milestone.
- **M-D (the RPG-roguelite game systems, then content):** the vertical-slice systems first —
  **D2** four meters + **D3** Madness/loss-of-control → **D1** Sequence/pathway progression →
  **D4** rumors→leads → **D5** run/meta shell; then breadth — **D6** new adversary archetypes →
  **D7** Ritual Night boss, with **C3** NPC animation + **C5** cinematics alongside. (This is the
  bulk of turning the slice into the full game; see `tingen_game_direction_v2.md` §9 for the
  slice-first cut.)
- **M-E (polish & feel):** **E1** panel visual language, **E5** onboarding, **C4** ambient VFX,
  **F1** camera/feel, **B4/B5** UI sfx + adaptive music, **E7/E8** a11y + controller.
- **M-F (ship):** **F2/F3** perf + soak + degradation, **F4** distribution model, **F5** export +
  branding + LICENSE. Yumina port (Track A) runs in parallel on its own track once the audit's
  Yumina blockers (§2.1 auth, §2.2 merge) are cleared — those are Yumina-team decisions.

**Decisions to put in front of the user first (they gate the most):** B0 (audio source), C5/F4
(cinematic + LLM distribution), D0 (narrative scope), F5 (license + repo visibility).
