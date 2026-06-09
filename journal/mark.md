# Mark's research journal

Daily log, newest entry on top. Format: [`journal/README.md`](README.md).

<!-- Copy the template from README.md to the top each working day. -->

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
