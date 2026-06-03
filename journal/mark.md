# Mark's research journal

Daily log, newest entry on top. Format: [`journal/README.md`](README.md).

<!-- Copy the template from README.md to the top each working day. -->

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
