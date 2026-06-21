# Chris's research journal

Daily log, newest entry on top. Format: [`journal/README.md`](README.md).

<!-- Copy the template from README.md to the top each working day. -->

## 2026-06-21

**Focus:** Merging the summer interns' PR batch; prototyping a Parsely-game
conversion onto our engine, and the parser improvements it surfaced.

**Done today:**
- **Merged Alistair's ready batch** and closed the linked issues: #94 agent
  memory stream (closes #75), #96 actions targeting other agents (#81), #98 seed
  personas at t=0 (#79), #99 embeddings for memory retrieval (#76), #101 the 2025
  Godot-playground survey, #104 semantic retrieval in the sim (#102). Handed #106
  (vision-radius perception) back for a rebase — it collides with #98/#104 on the
  shared Smallville wiring (`attach_agents` / `simulate`).
- **Ran the Smallville replay** end-to-end (`generative-agents/run-replay.sh`):
  25 residents living a morning on our engine, mock-LLM, $0 — the cost ledger
  from #91 reports per-resident spend right in the output.
- **Tried the approach I pitched to Frankie** (#107): converted Parsely's
  *Action Castle II* onto `text_adventure_games` (scratch, not committed yet) —
  16 locations, custom actions, a following NPC (Rosemary), scoring; both endings
  (king's champion + marriage) win via automated walkthroughs.
- **That exercise exposed real engine limitations** (the point of the experiment):
  (1) the keyword parser pre-empts custom verbs — `GIVE X TO Y`, `SAY YES` were
  hijacked by the generic `give`/`say` before custom actions were considered;
  (2) locations reached only via an action/trigger weren't indexed in
  `game.locations`; (3) the canonical-direction auto-reverse silently creates
  phantom exits (an `in` exit that then matched *inside* "exam**in**e").
- **Hardened the parser** on branch `proto/specific-first-parser` (commit
  `154ae52`, full suite green — 483 passed):
  - `determine_intent` now ranks a registered action's multi-word name/alias
    *specific-first*, so custom verbs and multi-word aliases route correctly
    instead of being pre-empted. Generalizes the old ad-hoc precedence hacks.
  - `get_direction` now recognizes movement *structurally* (bare direction/exit,
    or movement-verb-led, matched on word boundaries) rather than by substring
    containment — fixes the whole false-positive class (the `in`-in-"examine"
    bug, "out" in "shout", a cardinal token inside a content command).
  - Added `LlmParser`: optional enum-constrained LLM intent determination (picks
    from the registered action names via structured outputs, so it can't
    hallucinate an action; `anthropic` lazily imported). Two parsers now: the
    verb-noun default and the LLM one.
- **Built a parser accuracy leaderboard + effect tests** (scratch) — detail in
  the leaderboard note below.
- **Mentoring / admin:** scoped the codegen work with Frankie (set the reusable
  PDF→game pipeline aside; generate each Parsely game as a notebook on the engine
  — #107) and Tingen with Mark (build it on our engine, commit to a `game/tingen`
  branch — #108); introduced Mark, Maxine, and Artemis to compare notes on AI map
  generation.

**Parser accuracy leaderboard (`parser_leaderboard.py`).** Two halves: an
*accuracy leaderboard* — which action each parser picks, scored over a tiered
command set (canonical `VERB NOUN` → aliases / light paraphrase → natural
language) — and *deterministic effect tests* — once the right action is chosen,
applying it must yield the right game state (8/8 pass). Today's numbers:

| parser | canonical | alias / paraphrase | natural language | overall |
|---|---|---|---|---|
| verb-noun (default) | 10/10 | 6/6 | 0/6 | 72% |
| llm (claude, enum) | _ready entrant — skipped offline (no API key)_ | | | |

The gradient is the point: deterministic substring matching is excellent on
canonical and aliased commands and collapses on natural language (0%) — exactly
where the LLM parser earns its place. A leaderboard (not a single pass/fail) is
the right way to compare parsers as we open the game to free-form input, and the
harness is ready to score the LLM entrant the moment an API key is set.

**Blockers / questions:**
- Parser branch needs a PR, plus a decision on where *Action Castle II* and the
  leaderboard land (a `games/` instances dir + the test suite).
- The same substring sloppiness still affects the verb-keyword chain
  (`"give"` is a substring of `"forgive"`); longer term the answer is to
  tokenize once, or lean on the LLM parser for free-form input.

**Next:**
- Push and open the PR for `proto/specific-first-parser` (leaderboard + suite
  results in the description).
- Land *Action Castle II* as a checked-in game instance and the leaderboard as a
  test.
- Review Alistair's #106 rebase once it's green; encourage spreading the
  Smallville-wiring changes so the parallel branches stop colliding.
