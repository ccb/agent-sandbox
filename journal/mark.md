# Mark's research journal

Daily log, newest entry on top. Format: [`journal/README.md`](README.md).

<!-- Copy the template from README.md to the top each working day. -->

## 2026-06-23

**Focus:** #108 — get Tingen into the lab repo + capture the map workflow.

**Done today:**
- Vendored the Tingen game into `ccb/agent-sandbox` on a `game/tingen` branch via `git subtree` (satisfies #108's "version-control the materials, not just my laptop"); kept the heavy asset-gen scratch out of tracking, source of truth stays my `Tingen-Game` repo.
- Wrote an end-to-end city-map generation tutorial notebook (`games/tingen/asset-gen/map_generation_tutorial.ipynb`) for Artemis & Maxine — prompt → relabel to canon → strip-to-background → buildings-only → compose-with-colliders — self-contained with embedded screenshots.
- Filed #92 (off-scene room simulation / catch-up) and #93 (master "director" LLM for pacing/tension) out of the design discussion.

**Blockers / questions:**
- none

**Next:**
- Share the notebook with Artemis & Maxine; log the workflow tie-in for Frankie.
- Start the #92 off-scene-sim probe; double-check how much of Tingen actually runs on `text_adventure_games` vs. the Godot/sidecar layer.

## 2026-06-22

**Focus:** Tingen Godot scenes + city-map asset generation.

**Done today:**
- Godot: `SceneFade` autoload (scene-transition fade overlay), Old Neil's home scene, persistent-HUD fades, and run-from-anywhere scene transitions.
- Generated the Tingen city map end-to-end in the ChatGPT in-app image tool (GPT-Image): generate a top-down district → relabel to canon → strip to bare walkable ground → isolate building compounds (e.g. St. Selena's = chapel + churchyard + fence) on transparency; composed background + building colliders in the `City` / `CityBlocks` scenes.

**Blockers / questions:**
- AI image tools garble small lettering — relabeling needs careful prompting and some manual fixes.

**Next:**
- Vendor the materials into the lab repo (#108) and write up the asset workflow.

## 2026-06-19

**Focus:** Tingen asset generation / Godot interiors. _(reconstructed — no commits this day; correct me)_

**Done today:**
- [confirm] Continued asset generation and interior scene work (cathedral / Nighthawks HQ / archive).

**Blockers / questions:**
- [confirm]

**Next:**
- City map generation.

## 2026-06-18

**Focus:** Asset generation in the ChatGPT in-app image tool. _(reconstructed — no commits this day; correct me)_

**Done today:**
- Generated Tingen character/scene art via the ChatGPT in-app image tool (GPT-Image), iterating toward the *Lord of the Mysteries* canon look; exported into `asset-gen/my_assets/` (e.g. the Jun-18 export).

**Blockers / questions:**
- [confirm]

**Next:**
- City-map generation + relabel.

## 2026-06-17

**Focus:** Tingen Godot front-end ergonomics.

**Done today:**
- Added persistent on-screen panel-key hints to the HUD.
- Added a dev `StandaloneBoot` so any world scene can run solo with the HUD + controls — much faster iteration when building scenes.

**Blockers / questions:**
- none

**Next:**
- More scene content and asset generation.

## 2026-06-16

**Focus:** Follow-up cleanup on the just-landed agent layer — #66 (disambiguate `MockReActClient.tool_calls`).

**Done today:**
- **#66 — fixed, PR #67 up (green, MERGEABLE).** Chris filed this after the merge: my #57 (structured tool calling) and #58 (persuasion) both wrote to `MockReActClient.tool_calls` for *different* reasons. #57 logs every `call_tool` invocation (unconditionally, even on a silent turn); #58 logged the brain's actual non-`None` command in `_decide`. Because `LLMAgent.decide()` prefers the `call_tool` path, the `_decide` logging was effectively dead in the live game, and a persuasion test was passing for the wrong reason (it asserted on `tool_calls`, which is non-empty even when the NPC does nothing). Fix (TDD): added a dedicated `decisions` list written on **both** paths on a real command, kept `tool_calls` meaning #57's thing, and pointed the persuasion test at `decisions`. 301 tests pass, `black` clean.

**Blockers / questions:**
- none

**Next:**
- Wait for Chris to merge #67.
- Back to Tingen — wire NPC daily schedules onto the new city navmesh.

## 2026-06-15

**Focus:** Merge-train day — rebasing my batch (#52 → #57 → #58) onto `main`; on Tingen, rebuilding the world to scale with a real navmesh.

**Done today:**
- **Merge train (my batch) — all three landed.** Chris ran a fixed-order train across the overlapping PRs; my job was to keep each of mine rebased and conflict-free.
  - **#52 (containers / carry-capacity, #43)** — rebased onto `main`; resolved conflicts in `characters.py` (kept both the equipment slots *and* `carry_capacity`), `actions/things.py` (Drop/Give guards), and `consume.py` (Eat/Drink now use `discard_item` + clear hunger/thirst). Fixed one post-rebase test failure where a test seeded the stale `is_food` flag but `main` had migrated food to `Property.EDIBLE`.
  - **#57 (structured tool calling, #44)** — rebased; resolved `npc.py` / `llm_parser.py` conflicts (kept the duration constants alongside the new `call_tool` path).
  - **#58 (goal-influencing dialogue / persuasion, #46 — my own feature)** — rebased 9 commits; conflicts in `parsing.py` (`determine_intent`: kept the `SAY` enum, re-added the adopt/drop-goal routing) and `npc.py`. Verified `black` clean + 301 tests, pushed `--force-with-lease`, CI green, merged (`992cb36`). That finished my batch.
- Diagnosed a "failing all CI checks" scare on #52 as a **GitHub Actions billing problem** (Chris's lapsed card), not a code bug — impossibly-fast failures + missing log blobs + clean local runs. Re-triggered once it was sorted; green.
- **Tingen — rebuilt the district to a to-scale walkable city.** Added a `CityLayout` loader + `city_layout.json`, replaced the old Iron-Cross remap with a single global `CITY_SCALE` transform, baked a navmesh region from the layout, and got NPCs pathing around the city on it. Added a map underlay, a bounded camera, and city-edge walls; retired `LiveDistrict` and the old hubs. Logged the design decisions and addressed final-review findings.

**Blockers / questions:**
- none

**Next:**
- Clear any post-merge follow-ups Chris flags (became #66).
- Tingen: re-anchor NPC schedules/waypoints to the new world scale.

## 2026-06-11

**Focus:** Tingen — the Nighthawks HQ scene; agent-sandbox dialogue feature wrap-up.

**Done today:**
- **Tingen — built the Nighthawks HQ.** Top-down HQ room with a City door + a wiring test, a captain dialogue tree that hands out the briefing clue, and the HQ background + captain portrait art.
- **agent-sandbox (#46 dialogue/persuasion)** — finished the feature build: the `AdoptGoal`/`DropGoal` actions through the precondition gate, parser routing for the goal verbs (ahead of inventory "drop"), the "recently heard" section in NPC observations, the persuadable-servant / refusing-knight mock-brain rules, and an end-to-end integration test. Opened it as PR #58.

**Blockers / questions:**
- none

**Next:**
- Keep #58 rebased as the merge train moves.
- Tingen: connect HQ → city.

## 2026-06-10

**Focus:** Tingen — the map panel; agent-sandbox dialogue feature core.

**Done today:**
- **Tingen — real map panel, built bottom-up with TDD.** A pure `MapProjection.world_to_map` seam, then an aspect-preserving `image_to_canvas` + inverse, a `map_polygon` per district in map-image space, and finally rendering the real `tingen_map.png` with risk regions, markers, and a live player tracker. Also a Y-sorted depth upgrade for `IntroRoom`. Logged the map-panel design decisions + rejected alternatives.
- **agent-sandbox (#46)** — built the dialogue core: the bounded per-character `heard` buffer, the overridable `Game.audience_for` audibility seam, and `Say` delivering spoken utterances into the audience's buffer. All TDD.

**Blockers / questions:**
- none

**Next:**
- Finish the dialogue actions + mock brains and PR it.
- Tingen: HQ scene next.

## 2026-06-09

**Focus:** Closing out #26 (scenario tests); designing the dialogue feature (#46); Tingen endgame + asset pipeline.

**Done today:**
- **#26 — committed and merged (#33).** The game-agnostic `scenario.py` helpers + world-state integration tests.
- **#46 (dialogue/persuasion) — designed.** Brainstormed the feature, wrote the design spec, and turned it into a task-by-task implementation plan (heard buffer → audience seam → say delivery → goal actions → parser routing → observation surfacing → mock brains → integration test).
- **Tingen — endgame + animation pipeline.** The cult rite at the warehouse now drives the summoning countdown; wired the player's three interference levers into the summoning and added real endgame endings plus NPC combat/gather/talk verbs. Switched the animation generator to `gpt-image-2` with slim-gutter strips and rebuilt the intro blood-room art.

**Blockers / questions:**
- none

**Next:**
- Start implementing the #46 dialogue feature.
- Tingen: map panel.

## 2026-06-08

**Focus:** Shipping #24 (variable action durations), kicking off #26 (scenario integration tests), plus more work on my own game (Tingen).

**Done today:**
- **#24 — done, PR up (#32).** Implemented as a per-turn *time budget* for NPCs rather than a variable clock: the `GameClock` stays a pure function of turn count, but each NPC now acts within a budget equal to `clock.minutes_per_turn`. A behavior reports the minutes it spent (returns the number) and keeps acting while budget remains; the first action always runs even if it overruns. Behaviors that return `None` run exactly once, so the legacy troll/guard/ghost escalation is untouched. Added `Action.DURATION` + `get_duration()`, `Parser.last_action`, the budget loop in `Character.take_turn`, and an optional LLM `Duration:` line on the existing ReAct decision prompt (resolution precedence: LLM estimate > declared DURATION > full budget). Sample durations on Smell_Rose/Examine/Inventory. Built with TDD (179 passing), had a subagent review it (APPROVE, no blocking issues), opened PR #32.
- **#26 — started on `feature/scenario-integration-tests`.** Added a game-agnostic `text_adventure_games/scenario.py` (`play`, `blocked`, `prop`, `at`, `has_item`) and `tests/test_scenarios.py` with three scenarios asserting *world state* (not strings): feed-the-troll (drawbridge blocked→unblocked, troll hungry→fed — the motivating example), pick-the-rose (property/inventory transition), and light-lamp-dispels-darkness (a tiny purpose-built world). Goal predicates are kept as standalone `game -> bool` functions so a future agent-planning eval can reuse them unchanged. Verified the tests aren't vacuous with a mutation check; subagent review came back APPROVE. Not yet PR'd.
- Continued building out my own game (Tingen).

**Blockers / questions:**
- none

**Next:**
- Commit #26 and open its PR.
- Keep iterating on Tingen.

## 2026-06-05

**Focus:** Two newly-assigned issues (#24, #26), plus the first implementation pass on my own game (Tingen) and its asset pipeline.

**Done today:**
- Picked up the two issues just assigned to me: #24 (variable action durations instead of a constant time tick) and #26 (scenario-based integration tests asserting game state across action sequences). Read and started scoping both — #24 builds on the time model from #7, #26 builds on the event log from #6. No code up yet.
- Started implementing the Tingen game in Godot — stood up the core data-driven simulation as autoload singletons: `WorldState` (canonical pressures + derived stability), `Clock` (6-phase day + day/night tint), `WorldManager` (6-stage story machine on a strategic refresh with seeded dynamic slots), a weighted `EventManager`, `ClueDB` + a live Investigation Board, a topic/clue-gated `DialogueManager`, scheduled NPCs, `SaveManager`, a dev console, toast notifications, and a district map.
- Wired it all into the project and validated headless: clean import, zero script errors on boot, and 25/25 on a dependency-free test runner (clock phases, pressure clamping, stage machine, seeded-slot determinism, clue collection, event scoring, save/load round-trip).
- Kept a `DESIGN_DECISIONS.md` log of the choices I made plus open questions (stability formula weighting, refresh cadence, etc.) for review later.
- Asset generation: started the Tingen asset pipeline (`asset-gen/generate_tingen_assets.py`) — Replicate-backed generation of placeholder art.

**Blockers / questions:**
- For #24, still deciding whether durations should live on the `Action` subclass or come from a central lookup — will raise once I've scoped it properly.

**Next:**
- Put up a first PR on #24 or #26.
- Keep building out the Tingen implementation (event tuning, real NPC pathfinding later) and the asset generation.

## 2026-06-04

**Focus:** Planning my own game (Tingen) on top of the engine — design reconciliation + build order.

**Done today:**
- Read through the full Tingen design docs and resolved the engine question: the docs target a web "Yumina" engine, but the actual build is Godot. Decided to treat the engine docs as a portable system-design spec and port their contracts into Godot rather than rewrite them.
- Pinned down the design canon the scaffold has to match: the five pressure variables (corruption, panic, fatigue, cult_readiness, attention), the six day phases, and the six world stages (disturbance → awakening → investigation → confrontation → ritual_night → resolution).
- Rewrote the game's `TODO.md` into a sequenced build plan — tagged each task with its milestone, added a build-order DAG and a "what to avoid" list — so Friday's implementation could just follow the order.

**Blockers / questions:**
- none

**Next:**
- Start implementing the core simulation systems and pick up the two new engine issues.

## 2026-06-03

**Focus:** #8 — agent-to-agent interaction (actor seam + `say` action), then addressing #14/#16 review feedback and integrating onto current `main`.

**Done today:**
- Put #8 up as PR #19. Threaded an optional `actor` through the parse funnel (`parse_command` -> `parse_action` -> `determine_intent` -> `Action.__init__`) so NPCs act through the same precondition/effect gate as the player. Actions resolve the acting character via a new `acting_character()` seam that falls back to the old player-default scan when no actor is set.
- Added self-exclude disambiguation: `get_character(..., exclude=<actor>)` so an attacker or giver cannot target itself, backed by tests that fail if the `exclude=` guard is removed.
- Added a `say` / `speak` action (broadcast plus directed `say to <name>`), routed by its own intent branch and recorded in `command_history` so NPCs can hear speech. Wired NPC routing to the actor seam.
- Merged current `main` into the branch (event log #6, time model #7). The overlap was in the shared parse-funnel files, but it resolved cleanly with no conflicts.
- Fixed the actor-conflation bug Chris flagged in the #16 review (commit `bf2e348`): the event log derived its actor with `get_character(command)`, which returns the first character named anywhere in the command, so a player `attack troll` was mis-logged under the troll. `parse_command` now logs the explicitly threaded actor (`do_command` passes the player; NPC behavior already threads itself) and only falls back to the command scan when no actor is supplied. Added a regression test.
- Addressed the two #14 review comments (commit `1f0a0c4`): documented why the LLM system message omits the character name (identity rides on the first-person persona string) and noted that each behavior factory builds one agent for one character.
- Pushed to PR #19 with a note summarizing the follow-ups. The #8 implementation passed a full code review earlier; after the merge and fixes everything is still green — 137 pytest tests plus `test_npc_behaviors.py` pass and the touched files are `black`-clean.

**Blockers / questions:**
- The 12 `action_castle.py` subclasses accept `actor=` but still use the legacy player scan (mechanical widening only). Worth filing a follow-up to honor `actor`, or leave it until a concrete NPC needs it?

**Next:**
- Wait for PR #19 approval, then merge into `main`.
- Decide whether to file the `action_castle` actor follow-up.

## 2026-06-02

**Focus:** #3 (first-class NPC Agent seam) and #6 (event log + trigger system)

**Done today:**
- #3 -> PR #14 (merged): promoted NPCs to first-class Agent objects with a decision seam, giving a behavior or LLM a clean place to plug in instead of relying only on scripted behaviors.
- #6 -> PR #16 (merged): added a structured event log that captures game events, plus a trigger system (condition -> action factories) that fires in a react phase after each turn, with a bounded cascade so triggers cannot loop forever. Full regression plus formatting.

**Blockers / questions:**
- none

**Next:**
- Start #8 (agent-to-agent interaction).

## 2026-06-01

**Focus:** Onboarding / homework — Action Castle, lecture videos, Godot docs

**Done today:**
- Worked through the Action Castle text-adventure homework to get familiar with the engine: locations / items / characters, the precondition -> effect action model, and the keyword parser.
- Watched the course videos and read the Godot documentation to prep for the Godot front-end work I will own later.

**Blockers / questions:**
- none

**Next:**
- Pick up the first engine issues: the Agent seam (#3) and the trigger system (#6).
