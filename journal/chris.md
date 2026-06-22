# Chris's research journal

Daily log, newest entry on top. Format: [`journal/README.md`](README.md).

<!-- Copy the template from README.md to the top each working day. -->

## 2026-06-21 (cont. 2)

**Focus:** Engine features the AC2 port pulled for -- containers, surfaces, and
a general follow -- plus landing the games as a package.

**Done:**
- **`text_adventure_games/adventures/` package** (PR #111): `action_castle.py`
  (moved from `notebooks/hw1_solution/`, history preserved + a re-export shim so
  the course notebooks are untouched) and `action_castle_2.py`. Nesting *inside*
  the installed package makes them importable in notebooks/tests/web app with no
  `sys.path` setup -- and it couldn't be `games/` (collides with the `games.py`
  Game-class module).
- **Room containers, then surfaces (PR #114).** `Get`/`Examine`/`get_items_in_scope`
  reach into an open holder via a single `Item.accessible_contents()`. Added a
  **surface** (supporter) as a *sibling flag sharing the container storage*
  (`is_surface`; chosen over a class hierarchy or a unified holder+preposition
  flag), unified behind `is_holder`/`is_open`/`accessible_contents`/`preposition`.
  New verbs **Put** (`put X in/on Y`) and **Open/Close**. "The candle is on the
  table" works; AC2's Dungeon Stairs lamp now rests on a ledge (PR #116).
- **General-purpose follow (PR #115, closes #112).** Chose **cascade-on-move**
  over a turn behavior: following is a consequence of the *leader's* move (the
  engine drags followers the instant a `Go` resolves, recursively + cycle-safe),
  so it's correct in sequential *and* simultaneous mode, player- or NPC-led, and
  for chains -- a follower travels *during the leader's move*, not on its own
  later turn. `Character.following` + a `follow_filter` for no-go zones; `Follow`/
  `Unfollow` verbs. Rosemary migrated off her bespoke behavior, so `ask rosemary
  to follow` works (declines "too chilly" until the blanket); the boat ride
  carries her along.
- **AC2 smith via trigger (PR #116, #113).** Replaced the `GiveAxeToSmith`
  custom action with a trigger reacting to "the smith holds the unsharpened
  axe", so `give smith the axe` (word order) sharpens it too -- the built-in
  `Give` is phrasing-agnostic; the parser no longer has to be guessed at.
- Captured TODOs as issues from playtesting: **#112** (follow, now done),
  **#113** (give word-order, now done for the smith), **#110** (dialog-aware
  parsing, still design-only).

**Next:**
- The give-reaction hook (cleaner systematic #113) and the holder-tree refactor
  remain optional north stars -- only if games get deep with containment.
- A live-key `LlmParser` run to fill the leaderboard's LLM row.

## 2026-06-21 (cont.)

**Focus:** Playtesting the *Action Castle II* port, fixing what it surfaced, and
landing it (and Action Castle I) as checked-in games.

**Done:**
- **Playtested AC2 interactively** and fixed real issues: a one-way-door
  soft-lock plus junk/duplicate exits, all from canonical-direction auto-reverse
  *collisions* (multiple buildings' `out` fighting over `town_square["in"]`) —
  fixed by wiring those links one-way; and a wield-the-sword →
  arrested-in-the-courtyard soft-lock, because quest checks read only
  `inventory` while `WEAR`/`WIELD` move items into `worn`/`wielded` (fixed with a
  "held = inventory ∪ worn ∪ wielded" helper).
- **Engine affordances → `main` (`75f020a`, from `proto/specific-first-parser`):**
  `Examine` now works on NPCs; a generic `Talk` verb (`talk to <npc>` speaks a
  character's `talk_text`, never the private `persona` that drives the LLM
  agent); a `Wear` **fit gate** (an item declares `fit_property` + value, so it
  can be wearable yet only fit certain wearers); and **room containers** — `Get`
  takes an item out of an open container in the room, `Examine` lists an open
  container's contents, `get_items_in_scope` reaches one level in. + tests.
- **PDF faithfulness pass** (ran `/pdf-to-markdown` on the rulebook, diffed vs.
  the port): real **max score is 100** (I'd undercounted to 97 — missing the +5
  "finish without saving", and a self-added Middle-of-Pond room inflated the
  location count); the workshop is **NORTH** of the Town Square (not `in`);
  `WEAR SLIPPERS` → **"The slippers don't fit."** (wearable but *sized* — only
  the king/hermit carry the matching `shoe_size="imperial_foot"`); the blanket
  lives **in the boat** (a container), takeable from shore; restored the
  prophecy/slippers-gated riddle hint.
- **Landed the games (PR #111 → `main` `6863913`):** new
  **`text_adventure_games/adventures/`** package with `action_castle.py` (moved
  from `notebooks/hw1_solution/`, history preserved + a re-export shim so the
  course notebooks are untouched) and `action_castle_2.py`. Nesting *inside* the
  installed package makes them importable in notebooks/tests/webapp with **no
  `sys.path` setup** — and it couldn't be `games/` (collides with the `games.py`
  Game-class module). Added `tests/test_action_castle_2.py`. Full suite **457
  passed**.

**Next:**
- Research stronger **container/supporter** representations (Inform 7 / TADS
  conventions) and add **surfaces** — "the candle is on the table": PUT X ON Y,
  and LOOK/EXAMINE listing what rests on a supporter.
- Live-key run of `LlmParser` to fill the leaderboard's LLM row.

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

---

## 2026-06-21 (cont.) — Posed prompts: the game can ask a question (#110)

Closed out two playtest snags and then built the dialog feature they pointed at.

**The parser glitch (#124).** At the dragon, `tell dragon wits` printed
"Treasure trove does not have an exit 'None'". Root cause was the oldest bug in
the book: `determine_intent`'s else-fallback matched a registered action name
*anywhere* in the command as a raw substring — and `"go"` lives inside
`"dra-go-n"`, so anything mentioning the dragon routed to GO with no direction.
Fixed by matching action names on word boundaries (same fix class as `"give"`
inside `"forgive"`, which the journal flagged earlier), plus a guard so a `None`
direction can never render that message ("Go where?").

**Posed prompts (#110, #125 + #126).** The deeper itch: every dialogue fork in
AC2 was a bespoke verb (`choose wits`, `say yes`) and we *leaked the syntax* to
the player in parentheses so they'd know the magic words. So I built a general
"the game poses a question" mechanism:

- A `Prompt` (engine `prompts.py`); `Game.pose_prompt`/`pending_prompt`/
  `clear_prompt`. The parser consults a posed prompt **as a fallback** — only
  after a command fails to resolve to a real action — so it's never modal
  (`look`/`inventory` still work mid-conversation). Choice prompts map a keyword
  to a command; free-text prompts forward the whole reply to a verb. Word-
  boundary matching so `no` doesn't fire inside `snowing`. Expires when
  answered, replaced, or when the player leaves the room.
- AC2 wired on: the dragon's "wits or steel?", its riddle (free-text), the
  reward, and the king's yes/no all take bare answers now (`wits`, `a wise man`,
  `sword`, `yes`). All four parenthetical hints deleted. The conversation finally
  reads like one.

The LLM parser gets a `match_prompt` override (choices by meaning); free-text
just forwards. 559 tests green.

**Next:**
- The free-text riddle prompt is faithful but a footgun — a typo at the riddle
  counts as a (fatal) wrong answer. Fine for old-school parser play; revisit if
  it annoys playtesters.
- If a branching multi-turn dialog *tree* is ever wanted (vs. the single posed
  question), that's a follow-up beyond #110.

### Playtest follow-up — the linger-wake prompt gap (#127)

Chris caught it in live play: after the dragon woke *by lingering* (the
`dragon_stirs` trigger), a bare `wits` printed "I'm not sure what you want to
do." The prompt was only posed by the `WAKE DRAGON` *verb* — the trigger woke
the dragon and printed the same roar but never called `pose_prompt`. The two
paths had also duplicated and drifted the roar text ("wakes up" vs "wakes").

Fix: factored `_wake_and_challenge(game, dragon, roar)` (set awake → roar →
pose the wits/steel choice) and called it from both paths, so the prompt is
posed however the dragon wakes. Regression test covers linger-wake → bare
`wits`. 560 green.

Lesson worth keeping: when a feature hooks one path to a state transition,
audit *every* path that makes that transition. The dragon has two (verb +
trigger); a third would have been the same trap. The general engine answer is
to pose prompts on the state change, not in the action — but a shared helper is
enough here.

**Noted, not fixed:** the Treasure Trove's static description still says "A huge
dragon slumbers here" even once it's awake. Cosmetic; would need a
state-aware room description. Offered to Chris; parked unless it grates in play.

---

## 2026-06-21 (cont.) — Action Castle III: analysis + Phases 1-2

Chris pointed me at Action Castle III ("Beneath Action Castle") and asked for an
AC2-style port plan. Ran the PDF through /pdf-to-markdown and read all 28 pages.

**What AC3 is.** A party-based dungeon crawl — a real step up from AC2. You
recruit four companions (elf, dwarf, cleric, wizard), each unlocking an
ability-verb (SHOOT SPIDER, USE HATCHET, TURN UNDEAD, CAST SLEEP, USE WAND), and
nearly every obstacle is gated on having the right companion present with the
right item. ~21 rooms in three regions off a Crossroads hub. Not a single win:
GO NORTH home ends it and an epilogue is chosen by score (max 100); the best
ending banishes the demon AND kills the cultist. The puzzle graph interlocks
hard (bow needs sleep needs spellbook needs crypt needs cleric+pendant...),
forcing you to bounce between the cave and castle regions.

**The big realization:** the party maps cleanly onto AC2's follow system
(multi-follower cascade), and the one genuinely new *reusable* engine feature is
darkness/light. Everything else reuses AC2 machinery (containers, triggers,
gift/exchange actions, posed prompts, scoring).

**Phase 1 (#128):** promoted Darkness from a hand-rolled class inside AC1 to a
real engine block (blocks/darkness.py). Clears when anyone present holds a lit
item — including one inside an *open* carried container (a lit lantern in an
open pack). AC1 now uses it; its local copy is gone.

**Phase 2 (#129):** the AC3 skeleton — all 21 rooms, exits, populated fixtures,
the four companions placed, both darkness gates, a backpack container, and the
GO-NORTH-home ending via a yes/no confirm prompt + arrival epilogue stub. 14
topology/gate/ending tests.

**Finding worth its own PR:** GET only reaches holders sitting in the *room*,
not the player's own carried containers — so you can't pull gear out of the
pack. AC3 leans on exactly that (lockpicks, dagger, waterskin all start in the
pack), so the next engine feature is "GET into carried open containers." Parked
the lantern in-hand for now and left a TODO; build it when Phase 3 needs the
other gear out.

**Next (Phases 3-5):** the carried-container GET feature; recruit the four
companions (follow) + ability-verbs; the puzzle chain (bow/sleep, spider, webs,
baby + mushroom stew + crying-death triggers, goblin queen exchanges,
pendant/crypt, ooze/lockbox/crown, statue slide-trap); the endgame (javelin
summons + banishes the demon, push the cultist) and the scored epilogues; full
walkthrough + faithfulness audit. A couple of rulebook ambiguities to pin down:
how the wand is used (player vs wizard-in-party), and whether the stew pot needs
the bandits asleep first.
