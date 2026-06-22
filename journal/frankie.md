## 2026-06-22
**Focus:** tightened the slice-by-slice Parsely porting workflow after merging the conversion guide.

**Done today:**
- Decided ingest stays a random-access view, not a lazy stream — authoring slices are room-shaped, not page-shaped.
- Built `codegen.render_source` + CLI: renders a scoped slice (game / pages / room + one-hop exits) as compact markdown; 6 PDF-free tests.
- Pulled the shared `format_location` renderer into `pdf_structure.py`; documented in the guide §2; committed `8297fff`.

**Blockers / questions:**
- N/A

**Next:**
- Drive the next real port slice-by-slice with `render_source` to confirm room-plus-neighbours is the right chunk.
- `feat/issue-29-pdf-generation` is 3 commits ahead of origin and unpushed — push / open a PR when ready.

## 2026-06-19
**Focus:** chased a stream of user-reported AC2 gameplay bugs through the generated `.py` — endings, gating, and a wrong-answer death — and grew `verify_ac2.py` to 107 checks.

**Done today:**
- Propose now requires a ring and ends the game on success; Choose actions gated on dragon state, granting the sword directly.
- Split the one-choose-per-game lock into two flags + added a king yes/no champion/cobbler ending branch.
- Added `Answer_Wrong` catch-all so any non-riddle `answer` while the riddle is posed triggers the dragon's fire.

**Blockers / questions:**
- `ActionCastleII.is_won()` returns True on any `game_over`, so fatal endings count as wins — worth a follow-up.
- AC2 spec.json hasn't been resynced with today's `.py` edits; a fresh regen would lose all this.

**Next:**
- Decide whether to sync the AC2 spec back or accept the `.py`-first divergence and move on.
- Pick up #67 (epilogue sub-section detection in the structured PDF intermediate).

## 2026-06-18
**Focus:** finished the rebase, shipped the Tier-1 engine sweep, made the codegen retry iterative, then chased eight live Action Castle III interaction bugs back to their layers

**Done today:**
- Tier-1 sweep landed as built-ins (Wear/Take_Off, Use_On, Talk_To, Read, Open/Close, Score + multi-epilogue); 433 passing.
- Codegen retry is now iterative (`max_retries` loop, MODIFY-don't-regenerate); trimmed `SYSTEM_PROMPT` ~750→503 lines.
- Fixed all 8 live AC III bugs across parser (word-boundary directions), engine (location-scoped Examine), and spec.

**Blockers / questions:**
- Structured PDF intermediate is the right next investment to stop the LLM dropping rules; dataclasses + heuristics ready.
- `property_block` doesn't support `target: actor` — blocks the confirmation / party-required patterns.
- Two-step game-over confirmation in `Go.apply_effects` is the proper fix for AC III's "return home".

**Next:**
- Land the structured PDF intermediate (#60).
- Engine support for actor-property `property_block` and two-step game-over confirmation.
- Re-run the live extractor on AC III, diff against today's hand-fixed spec.

## 2026-06-17
**Focus:** surveying which Parsely-book mechanics the engine is missing — first scoped to Action Castle III, then expanded to all 12 games — and turning the findings into a Tier-1/Tier-2 engine roadmap

**Done today:**
- Walked AC III rule text page-by-page and surfaced 16 unsupported mechanics, bucketed Tier 1/2/3.
- Expanded the survey to all 12 games (21 mechanics); top finding: party/companion is broad (6/12), so it's Tier 2 not 3.
- Set the roadmap — Tier 1: wear, use-on, read, open, talk, score; Tier 2: companion + 7 more — and seeded party tasks #29–#33.

**Blockers / questions:**
- Party model paused: ship the Tier-1 PR first or proceed with the half-designed party model?
- Verification script's `SHOW`/`KNOCK` rows have narrator-prose false positives; tighten the regex if we publish the table.

**Next:**
- Decide Tier-1 PR vs party model and act.
- Re-run live LLM extraction on AC II / AC III after the engine sweep lands.

## 2026-06-16
**Focus:** issue #29 — fixing the Parsely ingest to preserve VERB↔response adjacency, then chasing a Flaming Goat regression where the LLM modeled the vending machine as inert flavor

**Done today:**
- Rewrote `_format_pages` to emit spans inline with `[FLAVOR]`/`[RULE]` tags, preserving the verb-to-response pairing.
- Rewrote `_underlined_words_for` to credit only words actually under an underline (x-range interpolation); 242 passing.
- Hand-patched Flaming Goat's vending machine into `transform_item` dispense actions; replay wins with the dispense step.

**Blockers / questions:**
- The walkthrough self-check validates win, not faithfulness — the LLM gamed it by skipping the machine; lean toward requiring every custom_action to appear in the walkthrough.
- Soda still shows in `describe_items` from the start (no `is_visible`); leaning toward a `spawn_item` template.

**Next:**
- Add the "walkthrough must exercise every custom_action" lint check + a `spawn_item` template.
- Re-run live extraction on Flaming Goat and confirm the LLM converges unaided.

## 2026-06-15
**Focus:** issue #29 — playing the live-extracted Action Castle, surfacing each gap, and tightening codegen + the engine + prompts at the point of error

**Done today:**
- Diagnosed and fixed five live bugs: phantom command hints, `go`-inside-`gold` substring match, royal-gating messages, NPC-only verbs leaking to the player, and the double `"I don't see it."` on `get`.
- Latched `game_over` to stop the triple win message; surfaced silent LLM-client errors (root cause: deprecated model → default `claude-sonnet-4-6`).
- Added the death-trigger location pattern to the prompt; regression test pins NPC-only verb hiding.

**Blockers / questions:**
- Latest module still walks through a locked door despite the `property_block` — suspect a duplicate-direction interaction with auto-reverse; trace it live next session.

**Next:**
- Diagnose the locked-door walk-through (dedupe block directions or emit one canonical direction).
- Re-run extraction with the strengthened prompts; try an unseen game (Spooky Manor / Z-Ward).

## 2026-06-12
**Focus:** worked on issue #29: strengthening the codegen extractor; merged #53

**Done today:**
- Merged #53 (feat/affordance tags) into `main`.
- Reviewed the live AC spec vs the gold and found flattened NPC behaviors, a collapsed win condition, drifted property names, and a fabricated `hit_guard`.
- Strengthened `prompts.py` (engine conventions, NPC-behavior + compositional-win guidance, validation checklist) and fixed `python_class_name` to sanitize spaced block names.

**Blockers / questions:**
- N/A

**Next:**
- Re-run extraction with the new prompts and diff against the gold; consider a second-pass critique call.
- Try an unseen game and convert `codegen_demo.py` into a `.ipynb`.

## 2026-06-11
**Focus:** issue #29 — Parsely PDF → playable game codegen pipeline

**Done today:**
- Shipped the codegen pipeline end-to-end: PyMuPDF ingest, LLM `GameSpec` extraction, template emit, validating CLI, `codegen_demo.py`.
- Added `Help`/`Break` built-ins; round-trip test plays the gold spec to `is_won()`, isolating emitter bugs from LLM hallucination.
- Docs in `codegen.md` + `codegen_gaps.md`; 219 tests passing on Python 3.9.6.

**Blockers / questions:**
- N/A

**Next:**
- Run live extraction on Spooky Manor / Z-Ward and populate `codegen_gaps.md`.
- Convert `codegen_demo.py` into a proper `.ipynb`.
- CI + manual live-extraction testing on an unseen game.

## 2026-06-10
**Focus:** focusing on implementing enums and structuring the data for the engine in issue #40

**Done today:**
- migrating the codebase to use tag-based affordances based on the LIGHT dataset, i.e., `edible` instead of `is_food`
- adding a `worn` dictionary and a `wield` dictionary, conforming to the standards of LIGHT by removing items in either to be removed from the inventory
- continued structuring the rest of the codebase using enums
- looked into `PyMuPDF` for #29 in order to both parse the text and keep the text color

**Blockers / questions:**
- N/A

**Next:**
- developing issue #29 further
## 2026-06-08
**Focus:** working on issue #23 and looking into logging for triggers

**Done today:**
- finished rebasing onto main and changed testing environment to match (`Python 3.9`)
- started issue #29
- auditing the codebase (i.e., checking logging behavior for triggers)

**Blockers / questions:**
- N/A

**Next:**
- working on issue #29
## 2026-06-05
**Focus:** working on issue #23 and looking into algebraic data types

**Done today:**
- researched implementation of the Goal class via a GoalType enum rather than just string matching to make the implementation less fragile
- finished #23 by integrating into `npc.py` (removing the original goals parameter, since that was now handled by character)
- changed tests to use GoalType rather than strings

**Blockers / questions:**
- N/A

**Next:**
- rebasing onto other PRs and focusing on less string-matching implementations
## 2026-06-04
**Focus:** researching and watching lectures on AI

**Done today:**
- watched lecture on CLIN
- read through Reflexion paper
- skimmed through text adventure papers

**Blockers / questions:**
- N/A

**Next:**
- reading more papers while working on issues
## 2026-06-03
**Focus:** rebasing issue #4 onto main and looking into implementation of #9

**Done today:**
- Finished rebase of issue #4, adding reflections to the ReAct loop implementation on top of the Agent framework
- Discussed possible implementation details of emergent behavior with Alistair

**Blockers / questions:**
- Uncertain of which repository I should use for studying smallville's websocket implementation (both the original [Generative Agents](https://github.com/joonspk-research/generative_agents) repo and a separate [smallville](https://github.com/nmatter1/smallville) repo didn't use websocket)

**Next:**
- Finish issue #9
## 2026-06-02
**Focus:** read the ReAct paper and work on PR #4

**Done today:**
- Implemented the Reflect step in `npc.py`: on a failed action, the agent now receives the parser's actual precondition-failure message instead of the generic "Choose a different action" placeholder, so it knows *why* the action was blocked
- Added `Parser.last_fail_message` (and wired `WebParser.fail()` to set it too) so the reflect loop can read the failure reason without side-effects
- Capped retries at 2 (1 initial attempt + up to 2 reflect iterations)
- Added 3 tests in `tests/test_agent_layer.py` covering: failure reason surfaced in retry prompt, retry cap enforced, and reflect path through the hybrid behavior

**Blockers / questions:**
- N/A

**Next:**
- Open PR for #4, get review
- Look at hooking the agent loop into the live game (currently `npc.py` is not wired into `action_castle.py`)
## 2026-06-01
**Focus:** figuring out the interface between Python and Godot

**Done today:**
- Wrote a simple Python script to connect to Godot via UDP
	- ![[Screen Recording 2026-06-02 at 12.19.14 1.gif|240]]
- Finished lectures for "Search in AI" and "Classical Planning"

**Blockers / questions:**
- N/A

**Next:**
- Working on PR #4
