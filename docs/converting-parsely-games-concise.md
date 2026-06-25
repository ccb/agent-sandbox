# Converting a Parsely game — field notes (concise)

The short version, for someone who **already knows the `text_adventure_games` engine**
(Frankie, this is you). It's mostly *how the work actually goes* — the prompts,
corrections, and decisions — with a one-screen engine cheat-sheet for lookup. The
full reference (object model, every feature, code samples) lives in
[`converting-parsely-games.md`](converting-parsely-games.md); the three finished ports
(`action_castle_{2,3,4}.py`) and their tests are the real spec.

> **The one idea:** implement most of the commands, and **generalize the reusable ones
> into the engine** — don't hand-code them per game. A port is an experiment that
> *hardens the engine*: each game surfaces a missing capability, you lift it into the
> engine (with tests), and the next port starts further ahead.

---

## It's a loop, not a prompt

Converting a game is **not** "paste the PDF into one prompt and get a finished game." An
LLM will confidently *misread* an ambiguous (often two-column-OCR'd) rulebook and
*drift* over a thousand lines, and several calls — how faithfully to model a fail-state,
whether a verb is a one-off or a reusable feature — are genuinely yours. The human in
the loop is what makes the port correct.

```
   plan → slice → (prompt → generate → run tests → read against rulebook → fix) → walkthrough wins
            ▲                                                                   │
            └───────────────────────── you steer the forks ────────────────────┘
```

You're not reviewing 1500 generated lines once; you're approving a ~100-line slice with
a passing test, then the next. **And the loop runs past the first green test** — some
corrections only surface in a playtest (see AC4's guard trap below).

## The workflow

1. **Read the rulebook into a plan.** Four lists: rooms+exits (with the page each leads
   to, to catch one-way passages / collisions), items (gettable vs. fixtures, what's in
   containers, start inventory), verbs (one-off *or* an instance of an existing engine
   mechanic?), scoring table + deaths/endings (points should sum to the max along the
   intended path).
2. **Do a `/pdf-to-markdown` faithfulness pass — and diff it against the port.** This is
   the highest-leverage correction step; it's where the LLM's invented rooms, misread
   exits, and wrong scores get caught. Do it early, not as an afterthought.
3. **Build in slices, one PR each**, running `pytest` between them. World skeleton +
   topology test first, then puzzles, then the endgame.
4. **Demand a `WALKTHROUGH` that wins at full score** — it's the proof the port is
   complete, and it doubles as the regression test.
5. **Generalize as you go.** When Claude writes a verb that's really generic (light,
   follow, a yes/no choice, riding, combining items), lift the mechanic into the engine
   with its own tests and use it from the game.

---

## Engine cheat-sheet (lookup)

**Parsely → engine.** Room → `Location` · Exit → `add_connection(dir, dest)` · item/scenery
→ `Item` · NPC → `Character` · special verb → an `actions.Action` subclass (or a built-in)
· "blocked until…" → a `blocks.Block` on an exit · "when X, Y" → `game.add_trigger(...)` ·
scoring line → `game.award(key, pts)` · the whole game → a `Game` subclass + `build_game()`.

**The parser rule that fixes most "missing action" bugs.** A verb that collides with a
built-in keyword (`GIVE X TO Y`, `SAY YES`, `OPEN DRESSER`) loses to the built-in unless
its `ACTION_NAME` is **multi-word** — multi-word names/aliases route *specific-first*,
before the keyword chain. So: **collides with a keyword → give it a multi-word name +
natural-phrasing aliases.** That single trick covers the majority of "the action isn't
wired up" cases.

**Reusable features.** These are features I built while
porting these games — each came out of a specific game's need (containers, follow,
posed prompts, crafting from AC2/AC3; vehicles, wear-slots, aliases, `contents_relation`
from AC4) — but I made them general because I expect they'll be reusable across many
other games:
- **Containers / surfaces** — `make_container()` / `make_surface()`; `accessible_contents()`;
  set `contents_relation` to voice the examine listing ("Under the mattress you see…").
- **Wearables / slots** — `WEARABLE` + `wear_slot` / `wear_over` / `wear_text`; one item per slot.
- **Object aliases** — `thing.add_alias("cot")` so "army cot" answers to "cot".
- **Item stacks** — `make_stackable(n)` for true duplicates (inventories are name-keyed).
- **Light / darkness** — `FLAMMABLE`/`IS_LIT` + `blocks.Darkness(room)`.
- **Follow / party** — `npc.following` + `refuses_follow`; **recruiting = clearing the refusal.**
- **Vehicles / mounts** — `make_vehicle(ready=)`; `MOUNT`/`DISMOUNT`; `blocks.RequiresVehicle`;
  a game verb flips `vehicle_ready` (key, taming).
- **Posed prompts** — `game.pose_prompt(Prompt(...))`: a choice (`{"yes": "say yes"}`) or
  free-text (`forward_as="answer riddle"`). Non-modal.
- **Crafting** — `Recipe(inputs=…consumed, tools=…required-not-consumed)` + one `Craft`
  verb (`make`/`cook`/`combine`/`braid`); gated on the game having recipes.
- **Give-to-NPC** — a multi-word custom action, *or* let built-in `Give` run and trigger
  on the resulting state (phrasing-agnostic).

**Helper kit (copy from the ports):** `_die(game, text)`, `_relocate(game, char, dest)`,
`_is_holding`/`_take_held` (held = inventory ∪ worn ∪ wielded ∪ open carried containers),
`_fixture`, `_one_way`.

**Gotchas that have bitten me:**
- `is_won()` ends the game *immediately* (it's what `is_game_over()` returns) — if the
  ending is "return home for the last points," **gate `is_won()` on `game_over`.**
- Canonical-direction **auto-reverse collisions** create phantom exits / clobber a hub's
  `in` — use the one-way helper for non-opposite or one-way links.
- Quest checks on **bare `inventory`** miss worn/wielded items — use `_is_holding`.
- Two items can't share a name (name-keyed) — use a **stack**.
- `persona` is the NPC's private mind, **not** its speech — use `talk_text`/`talk_topics`.
- Never `print()` — always `parser.ok` / `parser.fail` (captured, channel-typed).

---

## Worked examples: AC2, AC3, AC4 — real prompts, corrections, decisions

Three ports, in build order, shown as what they actually were: prompts I typed,
corrections I made against the rulebook and playtests, and decisions that were mine.

### Action Castle 2 — the first port (the one that taught the engine)

**Shape:** ~16 rooms, a town with shops, a following NPC (Rosemary), a dragon with a
riddle, two winning endings (king's champion / marriage).

AC2 wasn't really about shipping AC2 — it was the spike that proved the approach and
exposed what the engine was missing. I converted it *in scratch, uncommitted*, on
purpose, to see what would break.

**The prompts.** The kickoff was deliberately end-to-end, not incremental:

> *"Convert Parsely's Action Castle II onto `text_adventure_games`: all the rooms and
> exits, the custom verbs, Rosemary as a follower, scoring. Make both endings win via
> an automated walkthrough."*

That produced a playable-ish draft fast — and a pile of bugs, which was the point. The
follow-ups were each a specific breakage I'd hit:

> *"`give axe to smith` isn't doing anything — it just says I gave the axe."*
> *"I wielded the sword and now I'm getting arrested in the courtyard even though I'm holding it."*
> *"`tell dragon wits` does nothing — the dragon's waiting for an answer but won't take it."*

**The corrections — a faithfulness pass against the PDF.** Before trusting the port, I
ran `/pdf-to-markdown` on the rulebook and *diffed the markdown against the game*. That
single step caught a cluster of confident-but-wrong details the LLM had invented or
misread:

- **Max score is 100, not 97.** The model undercounted — it missed the +5 "finish
  without saving," and it had invented a "Middle of the Pond" room that inflated the
  location count. (The LLM will *add* content that reads plausibly. Check the score
  table sums to the rulebook total along the intended path.)
- **The workshop is NORTH of the square, not `in`.** A misread exit.
- **`WEAR SLIPPERS` → "The slippers don't fit."** They're wearable but *sized* — only
  the king and hermit carry the matching `shoe_size`. The LLM had made them freely wearable.
- **The blanket lives *in the boat*** (a container), takeable from shore — not loose in a room.

> *"Run `/pdf-to-markdown` on the AC2 rulebook and diff it against the port — I want to
> know everywhere the game disagrees with the book."*

is now a step I do for every port, not an afterthought.

**The decisions (these became engine features).** AC2's bugs each forced a design call:

- **Specific-first parsing.** `GIVE X TO Y` and `SAY YES` were hijacked by built-in
  `give`/`say` before the custom action was considered. The fix wasn't a one-off — I
  made the parser rank a registered action's **multi-word name/alias specific-first**.
  This is the single most important engine change the ports produced.
- **"Held" = inventory ∪ worn ∪ wielded.** The arrest soft-lock was a quest check
  reading bare `inventory` while `WIELD` had moved the sword into `wielded`. Generalized
  into the `_is_holding` helper every port now uses.
- **Cascade-on-move follow**, not a per-NPC turn behavior: following is a consequence of
  the *leader's* move, so the engine drags followers the instant a `Go` resolves. The
  boat carries Rosemary along.
- **Give-via-trigger, not a custom verb.** Instead of `GiveAxeToSmith`, let built-in
  `Give` run and attach a trigger reacting to "the smith now holds the unsharpened axe."
  `give smith the axe` (any word order) works — the parser never has to be guessed at.
- **The dragon's riddle → posed prompts.** `tell dragon wits` failing was the cue that
  the engine had no way for the *game* to ask a question. That became `pose_prompt`, so a
  bare `wits` / free-text answer resolves without the player guessing a magic verb.

### Action Castle 3 — the big interlock

**Shape:** a party-based dungeon crawl — recruit four companions, a bow-crafting chain, a
spider/web puzzle, a goblin queen, a demon/cultist endgame, score-branched epilogues.
Much denser than AC2.

**The prompts.** AC3 started with analysis, not code, and explicitly asked for planning:

> *"Read and analyze this game: `Action_Castle_3.pdf`. Use **ultrathink** to plan how
> you could convert it the same way you did for AC2."*

Then it was built in **phases, one PR each**, with me reading and steering between them —
the actual prompts were mostly *"sure"*, *"keep going"*, and the occasional redirect. The
one substantive design prompt was for crafting:

> *"Use ultrathink to design a crafting system where multiple items/ingredients combine
> into something new — e.g. a bow. The crafting step might require an instrument
> (a tool that's needed but not consumed)."*

**The decisions — most of AC3 was recognizing things were already-solved.** The
recurring move was *not* writing new code:

- **Recruiting a companion is just `follow` + a refusal flag.** A would-be party member
  sets `refuses_follow` with a reason; **clearing the refusal IS the rescue** (give the
  captive water + free him; drive off the spider + heal the poison — +10 each). `INVITE`
  just reports why someone won't come yet. No bespoke "party system."
- **GET reaches into a carried open container.** The party starts with a backpack and
  pulls gear out of it; that needed `Get`/`Examine` to look one level into a container
  the player is *holding*.
- **Crafting shipped engine-first, then AC3 used it.** The ultrathink design landed as a
  declarative `Recipe` + `Ingredient` (inputs consumed, **tools required but not**), one
  generic `Craft` action, gated on the game *having* recipes. Then AC3's stew (water +
  cave mushroom at the pot) and bow were just data.
- **One death predicate, reused.** "Carrying a crying baby into danger = THE END" is one
  predicate wired to several rooms — same pattern the demon's "dawdle and you're
  devoured" death reuses.
- **`is_won` gated on `game_over`.** AC3 ends by returning home for the last points;
  since `is_game_over()` returns `is_won()`, an ungated win-condition would end the game
  *before* the walkthrough could collect them. This bit me and is now a documented gotcha.

**The corrections.**

- **"A recipe needs 2 sticks" didn't work — and the real blocker wasn't crafting.**
  Inventories are name-keyed, so you can't hold two items both named "stick." That
  surfaced the need for opt-in **item stacks** (`make_stackable`) — a separate feature
  from crafting. (A bug whose fix lives somewhere other than where it shows up.)
- **The rescued captive stays named `cleric` the whole game**, even though the rulebook
  calls him "the man" until freed. One canonical dict key beats renaming a character
  mid-game; his *description* carries the tortured-man flavor, and the rescue verbs target
  him by location, so `free man` still works. A fidelity-vs-sanity call made consciously.

### Action Castle 4 — "Escape from Action Castle"

The princess escapes her tower and rides off into a road-trip. By AC4 the workflow was
routine; what's instructive is the **interventions** — the points where I overrode the
model. (Full slice-by-slice detail in the long guide's §15.) The greatest hits:

- **Generalize the second instance.** Riding shows up twice (horse, motorcycle) and AC2's
  boat is the same idea → built a reusable **vehicle/mount** feature instead of three
  bespoke mechanics.
- **A lint is a question, not a verdict.** A duplicate-destination topology test flagged
  "ride east OR west onto the highway," which first pushed me to "endings are actions, not
  rooms" — then *reversed* once the bike ending was concrete (riding out *is* travel, so a
  terminal Highway reached by two roads is faithful).
- **Catching OCR misreads (the big one).** The two-column layout glued lines together and
  the LLM inherited the mistakes: it made **`WEAR GLASS SLIPPERS` a death** (it's a gag)
  and **`KILL SELF` a death** (it's a *clue* — a falling hair slices the dagger). An LLM
  cannot reliably tell a death from a gag from a clue in jumbled OCR — but states its
  guess with total confidence. Verify against the source at every slice.
- **When *everyone's* memory is wrong, re-read the source.** Both the model and I believed
  the tower had two winning escapes; the port shipped that way. A playtest question —
  "isn't the guard supposed to catch me?" — sent me back to the rulebook pages: the front
  gate is a **trap** (the guard re-locks the door; no dagger = the "nineteen years"
  ending). The window is the only real escape. A confident shared assumption is still an
  assumption.
- **Model with a primitive, not machinery.** Boots "under the mattress" showed in the room
  listing. Tempting fix: a new `open_on_examine` flag. Real fix: the cot is just an **open
  container** (contents hidden from the listing, revealed on examine, self-updating) + a
  tiny `contents_relation` phrase override. Reroute to existing primitives before inventing.
- **Verb collisions are real.** `RIDE EAST` can't work — `ride` is a `MOUNT` alias, so it
  tries to *board*. Gate the roadhouse's plain `east`/`west` on being astride the started
  motorcycle instead. Playtest the actual words a player will type.

---

## Walkthroughs & tests

Every port ships a `WALKTHROUGH` (a command list that wins) and a test that runs it;
tests double as the **spec of supported commands**. Also worth testing (AC3/AC4 do):
topology (every exit resolves; no accidental duplicate-destination exits), each gate
(blocked → unlock → passable), each death, each scoring event. Run before pushing:

```bash
uv run pytest tests/ -q
uv run black text_adventure_games/ tests/
```

When in doubt about a mechanic, find the same situation in `action_castle_3.py` — almost
everything is exercised there.
