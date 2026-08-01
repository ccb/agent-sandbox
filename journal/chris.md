# Chris's research journal

Daily log, newest entry on top. Format: [`journal/README.md`](README.md).

<!-- Copy the template from README.md to the top each working day. -->

## 2026-07-27 — Tomb: the hint system grows a cipher

(Work lives in the standalone repo now — ccb/tomb-of-nassak-an-rah, extracted
7/25 — so this journal is the one piece of tomb news still landing here.)

### InvisiClues, enciphered
Replaced type-HINT-repeatedly with a panel: every open question with its full
ladder visible in SHAPE — word lengths, case, punctuation — but unrevealed
rungs enciphered, and one [ DECRYPT ] on the next rung only. A tap submits the
same journaled free `hint <key>` as typing, so saves, replays, and the
hints-taken tally stay honest; the panel is a richer *rendering* of the same
mechanic, and the CLI still gets the classic Infocom list. First cut was CSS
blur; the better idea was glyph substitution — per-OCCURRENCE random (no
consistent mapping, so nothing for frequency analysis to attack), seeded by
the text so the ciphertext reads as a stable document, not static.

### The script safari
Auditioned Greek/Cyrillic (shipped first), Latin Ext-B, Glagolitic, Armenian,
Kannada, Mongolian. Picked **Mongolian**: cursive-joining, so the ciphertext
shapes into flowing script — intercepted Autarchy handwriting. The finding
worth keeping: fontTools cmap dumps showed the mono fonts (SF Mono, Roboto
Mono, Droid Sans Mono, Cascadia) carry essentially NONE of the exotic
candidates — even the "safe" Ext-B pool was 0/30 in SF Mono. Every mock I'd
admired was rendering through per-glyph font FALLBACK the whole time. So the
portability question isn't "what does the mono font cover" but "does every
platform ship any fallback face" — settled empirically, including booting the
iOS simulator against a test page with a tofu-control line. Mongolian passes
on iOS, macOS, Android (Noto Sans Mongolian), and Windows (Baiti).

### The invisible cascade
The [ DECRYPT ] sweep was imperceptible: the resolved prefix kept wearing the
dim cipher color until completion, the churn head was three characters, and
the whole run took 0.7s. Now three distinct regions — reading phosphor /
six-character yellow churn head / cipher-dim tail — sweep left-to-right over
~2.5s regardless of line length. Verified by screenshotting mid-flight, not
by vibes; a "Safari doesn't animate" report turned out to be a stale cache.

Also today: split the glowstone toggle card into one-way LIGHT/DOUSE halves
(the card now does what the command did), opted the terminal out of Chrome
scroll anchoring (the itch-iframe hop on the Hall of Youth card — Safari has
no scroll anchoring, which was the tell), and the game went up on itch.io
(jam submission still pending; deadline 9/30).

## 2026-07-07 — Student PR review day; Slack round

### Reviewed and merged all four open student PRs
Frankie's **#414** (asset-path regression after the #399 restructure — seeding
had been *silently* no-op'ing), **#402** (furniture solidity + Fisher's
bookshelves/chairs as addressable game objects), **#415** (Anthropic prompt
caching on the stable persona prefix), and Alistair's **#342** (resilient LLM
client: retries + backoff + timeout, with every attempt recorded in the usage
ledger). Review method worth keeping: don't take the PR body's word for it —
**re-verify the claims locally**. #402's "pipeline is idempotent" checked out
byte-for-byte (re-running both scripts reproduced the committed CSVs exactly);
#342/#415 interleave in the same two client functions, so I merged their
combination locally and ran the full suite (1452 green) before merging either.
One rake: running the Godot smoke test in my review worktree let Godot rewrite
53 `.png.import` files — editor metadata masquerading as a diff. Know what your
tools touch. Flagged a leftover single-`dirname` path in `compare_plans.py`
(same class as #407) for a student follow-up.

### Journals + Slack
Frankie's journal is exemplary — daily through 7/7, with honest post-mortems
(his rebase-vs-merge analysis of the godot-ga-main sync is better than most of
what I've seen from grad students). Alistair's is stale since 6/25 despite his
biggest stretch of work (the live-LLM MVP!); Mark's since 6/23; Mekides hasn't
started. Sent encouraging DMs to Alistair and Mark (journal habit + I'm on
campus Thursday), a DM to Frankie offering help with his logged blockers (the
`workflow`-scope push failure on #390; the CLAUDE.md branch-reality mismatch),
and a note in #summer-research-26 asking Alistair and Frankie to sketch what
**actions** agents should take in the Penn simulator (check out a book, study,
take an exam, eat at Houston Hall...) — and Mark the same for Tingen. The
framing question for Thursday: what does an action need to be *real* in the sim
(a place, a duration, a visible state change, something memory can reason
about)?

## 2026-07-05 — The fire burns whether or not you watch

Boss-fight playtest forensics. I lit the Horror, spent the burn window
shuttling gear (acid wounds kept displacing my blade — the slot system working
as intended), came back, and landed blow after blow against a boss that
wouldn't die. The bug: **the Horror's turn only ran while I was in the room**,
so the fire froze whenever I left, expired unseen, and the only tell was
narration quietly switching from "the fire walks the coil" back to "the rents
knit closed." Two principles came out of it (#378):
- **The world runs whether or not you watch.** Burn ticks (and regeneration)
  now continue with the player elsewhere; only the acid needs a target. Douse,
  light, and *run* is now a legitimate tactic.
- **State changes are never silent.** The window closes audibly — a gutter-out
  line in the room, a dying roar heard remotely, a heard-not-seen shriek if it
  dies alone.

The rest of the day was narration legibility, all from playtest reactions:
- **#381**: burning the chimney growth from *inside* the shaft now costs a
  Scorched wound; from the Summit's mouth it's free — light a chimney the way
  chimneys are lit. Same shape as the coffin's boots-or-silk: two routes, one
  insight.
- **#383**: burn narration names the liquid, the target, and the tool actually
  in hand; the "burning, it cannot knit itself" tag became **earned knowledge**
  — only said once you've *watched* it mend (a `knit_seen` flag); and bare "the
  coil" got anchored ("What is 'the coil'?" is a question no player should have
  to ask).
- **#384**: the Burial Sphere becomes **the fight's record** — shattered
  coffin, the Autarch's bones adrift, the Horror's remains as a drift-of-ash
  *object* (not a lingering Characters entry), and room descriptions that track
  all three states (erupted / aftermath / root-killed-first). A room that
  forgets what happened in it is a bug.
- **#385/#386**: the climb gate moved to the sphere's crown (refuse the
  encumbered *before* they float up a room), and the mantis jar got its
  one-time defensive snap — an alarm with teeth, not a fourth combatant.

## 2026-07-04 — The boss fight earns its physics

Playtest-driven day on the Horror fight and the creatures around it:
- **Wound variety (#361)**: every wound description now draws from a variant
  pool — being killed by the Horror is "actually great fun," being told
  "a rope of acid caught you across the shoulder" four times is not.
- **Free meta-actions (#362)**: reasoned through whether checking inventory
  should cost a turn (it drew boss attacks — "punishingly fun" but wrong as a
  default). Now an engine policy: `Inventory`/`Help` are `FREE_ACTION`, with a
  `meta_actions_cost_turns` config knob for anyone who wants the old cruelty.
- **The jackals had never attacked me (#363/#364)**: the suspicion ledger
  decayed faster than real play raised it — playtest data beats design intent.
  Crashes now weigh +2, and the pack *pursues* by sight and scent through its
  territory at a lope-and-rest rhythm (escapable by a player who keeps moving,
  which is the point). The glass centipede existed only in the design doc;
  now it ambushes in the chimney for real.
- **The throw-douse-spark sequence (#375–#377)**: my own instinctive attack
  ("throw gel at horror", then "light gel") failed three ways — the alias
  didn't match, the Horror *caught* the flask, and lighting the dose wasn't a
  thing. All three fixed (engine: alias matching in combat targeting, a
  `no_catch` property; tomb: thrown gel douses, a spark alone ignites). The
  lesson: **when the player's instinct is physical and reasonable, the parser
  saying no is the bug.**

## 2026-07-03 — Slots, wounds, and the Horror as a boss

The big Vaarn-mechanics day (~25 PRs, #311–#351):
- **Slots + wounds (#323–#326)**: Vaarn's "inventory is your HP bar" —
  10 hard slots, wounds occupy slots and displace gear (your blade literally
  spills from your pack as you take hits), full = encumbered = no climbing.
  The death spiral is legible: you are too hurt to carry everything.
- **The [damage] channel + the coffin, properly (#340)**: every wound lands in
  one consistent voice on its own reporting channel; the coffin pry wants an
  anchor (boots worn *or* silk tether) and a lever (the blade — which snaps as
  the coffin gives: the sword you fought with buys the treasure and is spent
  doing it).
- **Fire, the gel economy, and the boss (#341, design doc §17)**: the flask
  holds 3 doses, refillable at gel pools, drinkable-but-regrettable; BURN
  generalized (corpse / chimney growth / the Horror); and the Fungal Horror is
  a real boss — vigor 5, a weapon hit costs 1, its turn **visibly knits 1
  back** ("mending faster than you are") plus an acid wound. Steel alone is a
  treadmill; ablaze, nothing knits. The fight teaches its own solution.
- **Embodied jackals (#333), spawn sound-hunting in darkness (#336), footfall
  verbs (#338), the throw gambit (#339)** — and a batch of line edits from
  playing (the tombwright seal, no unearned hints, "floating and unmoored from
  gravity").
Also merged Frankie's #311, un-sticking the black-format CI gate on main.

## 2026-07-02 — Dren onboarded

New student: **Dren Zabeli** (@ZaDrMeister) joins the project. Invited him to the
repo with write access, wrote a reusable [student onboarding
guide](../docs/student-onboarding.md) (day-one checklist, reading list, the
branch→PR→review workflow, and this journal habit), seeded `journal/dren.md`
(#303), and DM'd him the onboarding + setup instructions on Slack.

## 2026-07-01 — Student-PR backlog cleared; perception Layers 1–2 shipped

### Cleared the student PR backlog (and learned two git lessons)
Reviewed and merged Alistair's open PRs: #214 (branch-convention docs), #195
(SmallvilleConfig refactor), #196 (unify the backend behind one FastAPI HTTP
API). Two rakes stepped on, worth recording:
- **GitHub's merge engine ≠ local git.** #196 renamed `gen_agents/` → `backend/`
  while #195/#204 edited files inside it; local `git merge` auto-resolves via
  rename detection, but GitHub reports a modify/delete conflict. Fix: merge
  `main` into the PR branch (and make sure your local `origin/main` is fresh),
  verify, push, then merge.
- **Deleting a base branch auto-closes its stacked PRs — irreversibly.** Merging
  #196 with `--delete-branch` closed #204/#213, which can't be reopened or
  retargeted once the base is gone. Re-landed them from the same branches as
  #288/#289. Lesson: land the base of a stack first, retarget the children,
  *then* delete.

### Perception: spec → Layer 1 → first consumer → Layer 2
The design spec (#287) became working code in three PRs:
- **Layer 1 (#290):** `Sight` (NONE/DIM/CLEAR), `Veil` + `Darkness`/`Fog`
  (`location.obscure(...)`), observer `blind`, and `Game.perceive() → Scene`.
  The key design question: should the player's `describe()` and the agents'
  `describe_for()` stay two functions? Answer — **one perception, two
  renderers**: they serve different audiences (human prose vs. structured agent
  observation) but now share a single `perceive()`, so darkness hides the same
  things from both. Zero-cost proven: no veils → the full pre-existing suite
  renders byte-identical.
- **Hall of Youth (#291):** the glowstone is now a lantern — new engine **Douse**
  action (inverse of Light; a light source is a toggle), room pitch dark until
  lit, and *lighting up* is what rouses the bats (a warn-then-kill timer). No
  movement gate: a player who knows the layout can creep through blind.
- **Layer 2 (#292):** `Sense` (touch/hearing/smell) + `Thing.perceptible_by`;
  `Examine` is perception-gated (in the dark it falls back to what you can
  *hear/smell*, else "too dark"); opt-in `feel`/`listen`/`smell` probes via
  `game.enable_senses()`. The Youth's ceiling is now heard in the dark (the
  clue) and seen once lit — and sensing quietly never wakes the bats.

Suite at 1362 green. Next: Layer 3 (the `Scene`-anchored LLM narrator).

## 2026-06-30 — Tomb of Nassak An-Rah: a full adventure in a day

### Game-development guide + reactions demo (#275)
Wrote the newcomer-facing guide to the engine's classes and primitives, plus a
runnable reactions demo.

### The Tomb (#276–#281)
Converted the Vaults of Vaarn adventure *Tomb of Nassak An-Rah* into a
Zork/Action-Castle-homage parser game for the summer game jam — spec-first
([design doc](../docs/design/tomb-of-nassak-an-rah.md)), then five implementation
phases: map + atmosphere scaffold; the canopic-seal puzzle + Silas the archivist;
noise and the Spawn lure (the mantis jar's `FungalSong` amplifies any racket and
the Spawn are `DrawnToSound` — the reactions library earning its keep); the
endgame (burn the corpse at the Summit to kill the Fungal Horror, zero-g coffin
pried with magnetic boots) — winnable at 100/100.

Playtest verdict on my own first cut: instant-death rooms were **annoying**. #281
replaced every death-on-entry with a patient `_hazard` timer — warn, escalate,
kill only if you persist, reset the moment the danger lifts. Movement is never
lethal; light, noise, spores, and disturbing the dead are. Much fairer game.

## 2026-06-29 — The reactions system

Built the thing the noise work was pointing at: **reactions** — thing-owned,
stimulus-triggered reflexes (#228–#235, on the groundwork of #225/#227:
event-based disturbances + cross-room sound perception).

- **Design:** `GatedEffect` (check preconditions → apply effects) is the shared
  shape; `Action` and `Reaction` both subclass it. A `Reaction` lives on a
  `Thing` and is adapted into a `Trigger` by *composition*, not inheritance —
  we talked through both alternatives (literal Trigger subclass? Trigger as
  Action?) before settling here.
- **Sound layer:** `Game.emit_sound(location, radius, description)`,
  `sounds_audible_at`, `audible_rooms` — sounds are events with a radius.
- **Library:** `Startle` → `FleesAtNoise` / `WakesAtNoise` / `DrawnToSound`
  (homes toward the loudest sound), plus `Countdown`.
- **Migrations as proof:** AC4's doe+poacher (the poacher shoots on the doe's
  *arrival*, a timed reaction), AC3's demon (`Countdown`), AC2's dragon (first
  `WakesAtNoise`, then corrected to a linger `Countdown` — #234), and AC3's
  goblin baby now emits its wail as a real sound (#235).

## 2026-06-28 — Big AC4 day + engine quality-of-life

Engine: worn/wielded items are in EXAMINE scope (#207); INVENTORY lists
carried → worn → wielded (#208); command sequences skip empty segments and run
one turn per command (#209); narration is capitalized (#210).

AC4, mostly playtest-driven: per-exit move verbs + a fall that reacts to what
she's wearing (#202); a **working drawbridge** — guardroom winch, front-gate
trap, sealed castle (#211); the deer as a fixture that flees the shack and gets
chased (#212); room descriptions that track state — crossbow, poacher, horse,
brawl, drawbridge (#215); the Breakpoint crowded with bikers and ranchers
(#216); the ranchers' truck as a second getaway + a longest-match item fix
(#218); table-4 alias, brawl drops only the biker's keys, "toss a drink"
(#219–#221); the doe startled by *noise*, not just the shack door (#222). And
the first cross-game noise spread: AC3's bandits and stirges alert on any noise,
not only the crying baby (#223).

## 2026-06-27 — Mirrors

AC4 polish (wearable cloak, readable sign, Dalton + jukebox dialogue, #200) and
a fun engine feature: **reflective mirrors** (#201) — examining a mirror
composes the examiner's live appearance (including what they're wearing) instead
of canned text that goes stale after a haircut.

## 2026-06-26 — AC4 playtest fixes

Pick rose works with flavor instead of "the rosebush is bare" (#188); watermelon
vines gag in the Gardens (#190); tying the rope consumes it + talk to the prince
about art (#191); mounted travel narrates "rides the <vehicle>" via `ride_verb`
(#192); Deep Woods only enterable by FOLLOW DEER (#193); renamed a GA test file
that broke root-level pytest collection (#194).

## 2026-06-25 — The window escape, done right

Finished what the 06-23 guard-trap discovery started: the tower escape is now the
book's **two-step window escape** through a proper "Outside the Tower" room, with
the hair left on the floor (#181). Plus single-word parser aliases.

## 2026-06-23 — AC4 playtest fixes: object aliases, the guard trap, guide finished

A morning of playtest-driven fixes to AC4, plus finishing Frankie's conversion guide.

### Finished the conversion guide
Closed the remaining gaps now that AC4 is complete: added a §7 entry for the
vehicle/mount feature (it was the headline of Slice 1 but never documented as a
reusable feature), fixed a garbled posed-prompts "Used by" line, de-staled the
"two ports"/"in progress" markers (three ports now; AC4 wins 100/100), and added a
§7 "Object aliases" entry.

### Small engine + AC4 fixes from the playtest
- **Object aliases (engine):** a multi-word thing only matched text containing its
  full name, so `examine cot` failed for "army cot". Added `Thing.add_alias()` +
  parser matching + serialization; aliased the cot ("cot") and the coin purse
  ("purse"). General, cheap, reusable.
- **brush hair:** added the missing BRUSH HAIR action (it errored before); matched
  the rulebook's deliberately-anticlimactic flavor.
- **Boots double-message:** the boots' wear_text and the score line both said "you
  can actually walk"; reworded the score line.

### The big one: the tower escape was wrong (read the source!)
Both I *and* CCB believed the tower had two winning escapes (sneak out the front
through the guardroom, or rope out the window). A playtest question -- "isn't the
guard supposed to catch me?" -- sent me to the actual AC4 rulebook PDF (pages 4-7).
The front gate is a **trap**: GUARDROOM → WEST runs you into the guard, who marches
you back upstairs and **locks the door**; with no dagger to cut your hair, that's
the "nineteen years" ending. The **only** real escape is the window.

Fixes:
- Removed the fabricated Tower-Stairs west exit + its GuardBlock (Tower Stairs has
  only DOWN + ENTER, per the book -- CCB caught this first).
- Per CCB's call, modeled the guard as a **trigger on arriving at the Drawbridge**
  (the guard waiting at the bridge), not a block: it relocates you to the Tower and
  locks the door, unless you've genuinely escaped via the window (an `escaped` flag
  set on reaching the Gardens, the one window-only room).
- Made GUARDROOM → WEST one-way ("returning to the castle is out of the question").
- Added the locked-door block on the Tower's OUT exit and the trapped-forever death.
- Rewrote WALKTHROUGH_WIN to the window route (still 100/100); fixed all the Slice-4
  tests that had piggybacked on the bogus west shortcut (a shared ESCAPE_TO_GARDENS
  helper now); added guard/lock/trapped tests.

Updated the guide's Intervention 6 to tell this story straight -- a confident shared
assumption is still an assumption; the rulebook page is the only authority. 723
tests green.

---

## 2026-06-22 — Action Castle III (Phases 3–5), crafting, item stacks

(Continues the 6-21 AC3 analysis + Phases 1-2 logged in the day below.)

### AC3 Phase 3 — carried-container GET + party recruitment (#130, #131)

**Engine (#130):** GET now reaches into the player's own carried open containers,
not just holders sitting in the room. AC3 needs it — the party starts with a
backpack and pulls gear out (lantern, dagger, lockpicks, waterskin). "take
lantern" moves it pack -> hand; a closed pack hides its contents. Lantern went
back into the pack in AC3 (rulebook-faithful).

**AC3 (#131):** recruiting the four companions. The nice realization held up:
recruitment is just the engine's follow mechanism plus refuses_follow as the
gate. Elf/wizard join on sight; the cleric and dwarf must be rescued first
(give water + free; drive off spider + free + heal poison), and clearing the
refusal IS the rescue (+10 each). INVITE reports why a recruit won't come yet.
The whole party cascades when you move (drag_followers).

One faithfulness nick: the captive cleric is named "cleric" throughout (the
rulebook calls him "the man" until rescued). One canonical character name is far
cleaner than renaming a dict key mid-game; his description keeps the tortured-man
flavor, and the rescue verbs (give water / free man) target him by location, not
name, so "free man" still works.

**Next (Phase 4):** the ability-verbs and their puzzle items — SHOOT SPIDER
(elf+bow, drives off the spider so FREE DWARF is safe), USE HATCHET (dwarf,
clears the web), CAST SLEEP (wizard+spellbook, sleeps the bandits for the bow),
USE WAND (wizard, freezes the ooze), TURN UNDEAD (cleric+pendant, Crypt) — then
the baby + mushroom-stew + crying-death chain, the goblin-queen exchanges, and
ooze/lockbox/crown. The interlock is the whole game; I'll land it in slices.

### AC3 Phase 4a/4b — the bow chain + spider/web (#132, #133)

The hardest interlock in AC3, landed in two slices.

**4a — bow chain (#132):** the long quest that arms the elf, threading the
cleric and wizard abilities through it: SEARCH dungeon -> pendant -> GIVE PENDANT
TO CLERIC -> Crypt (TAKE BOOK wakes skeletons; cleric+pendant TURN UNDEAD them,
else death) -> spell book -> GIVE SPELL BOOK TO WIZARD (+5) -> CAST SLEEP drops
the bandits -> take bow -> GIVE BOW TO ELF (+5). Ability-verbs gate on the
companion being in the party AND co-located (_in_party). The multi-word
give/take verbs route specific-first ahead of built-in give/take (the AC2 trick).

**4b — spider/web (#133):** SHOOT SPIDER (armed elf, +10) drives the spider off;
USE HATCHET (dwarf) clears the web blocking west -- but only after the spider's
gone (hacking the web while it watches = death). WebBlock gates Spider Lair west.
Deep Ravine now reachable.

602 tests. The pattern is settling nicely: each ability is a small custom action
gated on (companion in party + present) + (required item flag), and deaths are
the faithful gates that force the right order.

**Remaining (Phase 4 tail + 5):** baby (DROP BACKPACK -> fissure -> take baby) +
mushroom stew (spring water + cave mushroom cooked at the bandit pot) + the
crying-baby death triggers (Bandit Camp, Deep Ravine) + feeding to quiet it;
goblin-caves net trap + queen exchanges (baby, crown->javelin); ooze/lockbox/
crown (USE WAND freezes the ooze) + statue slide-trap; then the endgame (javelin
summons + THROW JAVELIN banishes the demon, push cultist into pit) and the
score-branched epilogues. Plus a full win walkthrough + faithfulness audit.

### Reusable crafting system (#136) + AC3 stew (#137)

Chris asked (ultrathink) for a general crafting system -- stew = water + mushroom,
but also Minecraft-style string + stick -> bow, possibly requiring an instrument.

**Design that shipped (#136):** declarative `Recipe` + `Ingredient` (crafting.py),
one generic `Craft` action. Inputs are consumed from held items; *tools* are
required present (held or in room) but NOT consumed -- so a pot, a forge, and a
hammer are all just "tools" (station vs instrument is only a scope difference).
Ingredients match by name or by a property *tag* (tag="plank", count=2 -> any
two planks). Output is a factory (g -> Item|list) so recipes repeat. The parser
routes make/craft/cook/brew/forge/mix/combine/assemble/build to CRAFT, gated on
the game having recipes (non-crafting games unaffected; "make a wish" still wins
specific-first). Resolve by output name / by ingredients / bare-verb-at-station.

Two decisions Chris made: liquids = waterskin-as-container (a `water` item in
the skin) over a provider protocol; and build engine-first then AC3.

Two limits filed as issues rather than solved now: **#134** count>1 for
same-named items (engine keys inventory by name; tags cover the real cases), and
**#135** "known"/recipe-book gating (every recipe is always craftable for now).

**AC3 (#137):** stew is a Recipe (water + cave mushroom at the pot). Waterskin
became a container -- FILL puts a `water` item in it; GIVE WATER and the stew
both consume it. Key gotcha: nested containers only resolve one level deep in
the held-scope helpers, so the waterskin rides directly in inventory (not in the
backpack) to keep its water reachable. TAKE MUSHROOM yields a cave mushroom.

620 tests. Next: the baby/stew feeding + crying-death chain (the stew now has a
consumer), goblin-queen exchanges, ooze/lockbox/crown, then the endgame.

### AC3 Phase 4 (baby) — rescue + crying-deaths + feeding (#138)

The chain that ties the fissure, the stew, and the death triggers together.
DROP BACKPACK (a PackBlock) to squeeze into the fissure; TAKE BABY (+5), and it
cries. Crying baby = fatal at the Bandit Camp and Deep Ravine (triggers); FEED
BABY consumes the stew and quiets it. The intended order is emergent: cook stew
at the camp before fetching the baby, then feed it right after rescue. 627 tests.

Notable: the stew (crafting PR) now has its consumer, and the death triggers
reuse the same carry-a-crying-baby predicate -- clean. Remaining AC3: goblin
queen (net trap SHOW BABY, GIVE BABY, crown->javelin), ooze/lockbox/crown, then
the endgame (demon/cultist) + scored epilogues + full win walkthrough.

### AC3 Phase 4 (goblin queen) — net trap + throne exchanges (#139)

Goblin Caves net trap (no baby -> enslaved death; SHOW BABY frees you, NetBlock
herds you east), Throne Room GIVE BABY (+5, lets you leave) and GIVE CROWN (+5,
trades the crown for the bronze javelin -- the endgame key). A throne_escort
trigger whisks you to the surface once the audience is satisfied (baby given,
crown too if carried) and pacifies the caves. 632 tests. Crown source (lockbox)
comes next; GIVE CROWN tested with a placed crown. Remaining: ooze/lockbox/crown
+ statue slide-trap, then endgame (demon/cultist) + epilogues + win walkthrough.

### AC3 Phase 4 (ooze/crown) — #140

Dark Corridor gray ooze: LOOK UP reveals it; PICK LOCK / TAKE LOCKBOX while it
lives = death; USE WAND ON OOZE (wizard's wand) freezes it (+10). Then PICK LOCK
(starting lockpicks) yields the gold crown -> the queen's tribute -> the bronze
javelin. Vault statue slide-trap (PUSH STATUE) drops you to the Mushroom Garden.
639 tests; the full crown->queen->javelin loop is tested end to end. All puzzle
pieces now in. Remaining: the endgame (javelin summons + THROW JAVELIN banishes
the demon, push cultist into pit) + score-branched epilogues + win walkthrough +
faithfulness audit. Possible polish: OPEN DOOR (spiked door) / OPEN IRON MAIDEN
gates were left ungated to avoid churning routes -- revisit in the endgame slice.

### AC3 COMPLETE — endgame + scored epilogues (#141, #142, #143)

Action Castle III is winnable end to end: the WALKTHROUGH scores 100/100 and
hits the "TO BE CONTINUED!" hero ending.

- #141 endgame: the bronze javelin summons the cultist + demon in the Chaos
  Chapel; THROW JAVELIN banishes the demon (dawdling in front of it = death),
  PUSH CULTIST finishes him. Plus the two way-down flavor gates (OPEN DOOR,
  OPEN IRON MAIDEN); updated the cleric/crypt routes through them.
- #142 epilogues: rulebook page-72 branch-by-progress endings (hero / banished-
  only / return-artifact / sell-crown / raise-baby / die-alone), home +10 and
  finish +5 always. Plus a real WALKTHROUGH (--walk) and the 100/100 win test.
- Gotcha fixed: is_game_over() consults is_won(), so an is_won() that returned
  True on killing the cultist ended the game before going home (score 85).
  Re-gated is_won() on game_over -- the adventure only finishes on GO NORTH.
- #143: marked the port complete in the docstring.

Across AC3 the "each finding -> reusable engine feature" pattern held: it drove
the Darkness block (#128), GET-from-carried-container (#130), and the whole
crafting system (#136). 651 tests. Optional flavor left unported (noted in the
docstring): topic dialogue, the telescope/journal hints, FIGHT BANDITS death.

### #134 — opt-in item stacks/quantities (#148)

The real blocker behind "a recipe needs 2 sticks" wasn't crafting -- it's that
every holder keys items by name, so you can't hold two identical items at all.
Rejected the big refactor (list/id-keyed holders); went with a quantity on Item.

Item.quantity (default 1) + make_stackable(n). Stackable items merge on add
across all three holders (inventory/container/location); a stack is one slot.
The safety property: stacking is OPT-IN, so non-stackable items never merge or
show counts and the name->item shape is unchanged -- zero regression risk, full
suite stayed green by construction. Crafting sums quantity for availability and
decrements stacks on consume, so Ingredient(count=2) works against a single
named stack or across tag matches. (x N) in listings; quantity serializes.

Shipped Tier 1+2; deferred Tier 3 (partial-count commands like "drop 2 sticks",
which need parser number-handling). #135 (known/recipe-book recipes) still open.

Also today: reviewed Alistair's PR #109 (5-agent replay + memory/reasoning UI) --
green CI, all within generative-agents/, engine untouched; left for CCB to merge.
Sent Frankie a Slack DM pointing him at the AC2/AC3 ports, their tests (the
command spec), the journal, and the reusable engine features to build on.

### Parsely conversion guide + AC4 worked example (#151-154)

Wrote a comprehensive how-to for converting Parsely games to the engine
(docs/converting-parsely-games.md, #154), aimed at Frankie. Headline framing he
needed: it's an iterative LOOP, not one prompt -- plan, slice, prompt/generate/
test/fix per slice, walkthrough -- because the LLM confidently misreads ambiguous
rulebooks. Covers the parser routing rule (multi-word ACTION_NAMEs beat built-in
keywords = the #1 "missing action" fix), the reusable engine features, and the
is_won/is_game_over gotcha.

To make it concrete, started porting AC4 ("Escape from Action Castle") WITH Chris,
slice by slice, capturing the real points of intervention (now §15 of the guide):
- #151 vehicle/mount engine feature (Chris's call to generalize, not hand-code;
  horse + motorcycle ride on it; AC2 boat refactor deferred).
- #152 AC4 world skeleton (14 rooms). The "ride east OR west onto the highway"
  tempted a Highway room with two exits; the dup-destination topology test caught
  it -> endings are action-effects, not rooms.
- #153 tower escape: cut hair -> MAKE ROPE (a crafting recipe!) -> climb out, OR
  sneak down through the guardroom. Chris corrected two of my OCR misreads: WEAR
  GLASS/RUBY SLIPPERS are gags (not deaths) and KILL SELF is a clue (a falling
  hair slices the dagger), not a death. Exactly the "human catches the confident
  misread" lesson the guide preaches.

AC4 slices 4-5 (horse+poacher/deer; ranch/roadhouse/bar + endings + full
walkthrough) still to do. 683 tests green.

### AC4 Slice 4 (horse + poacher) + wearable slots generalization (#155, #156)

- #155 horse (Slice 4a): PICK APPLE / BRUSH (hairbrush) tames the skittish mare
  (first real use of the vehicle feature); ride west into the Old Woods, DISMOUNT
  to enter the shack for the crossbow.
- #156 poacher/deer (Slice 4b): FOLLOW DEER rides into the Deep Woods; SHOOT
  POACHER (crossbow) saves the deer (+5), drops the coin purse (+5); hesitating
  (any committal action but shooting) lets him kill the deer = THE END (the AC3
  demon pattern reused).
- Playtest-driven (Chris): boots gettable/wearable as "boots" or "army boots";
  and -- Chris's call to generalize rather than special-case -- a reusable engine
  WEAR-SLOT feature (#156): items declare wear_slot ("feet"/"head"/"body") +
  wear_over (layering) + wear_text; the Wear action enforces one-per-slot. AC4's
  footwear now rides on it (only one pair worn at a time); deleted the bespoke
  WearBoots/footwear hack. Good "spot the playtest bug -> generalize it" example.

### contents_relation + AC4 cot (#157)

A playtest nit: the army boots, meant to be "under the mattress," showed in the
Guardroom listing. Walked through the primitives with Chris (open_on_examine?
surface? secret_topic?) and landed on the simplest: the cot is just an **open
container** -- its contents don't show in the room listing, but EXAMINE COT
reveals them and self-updates as they're taken. The only gap was voice, so added
a tiny reusable `contents_relation` phrase override on a holder ("Under the
stained mattress you see...") instead of the default "It contains...". ~3 lines
in Examine. Good "reach for a primitive, not new machinery" example.

### AC4 Slice 5 -- the finale, AC4 done (#158)

Finished AC4 as a winnable 100/100. The ranch: GIVE HORSE TO RANCHER earns a
yes/no job offer (posed Prompt, #110) -- SAY YES = Rancher ending (+40, score
80); SAY NO sends you to Dalton at the roadhouse. Dalton bars the bar until SAY
WADE SENT ME. Inside: TALK TO BARTENDER (tray) -> TAKE TRAY TO TABLE FOUR
(provoke) -> PUNCH BIKER (+5, keys fly) -> CATCH KEYS -> USE KEY ON MOTORCYCLE.

Two real decisions this slice:
- **Reversed the Slice-2 "endings are actions" call for the highway.** With the
  bike ending concrete, riding out IS travel, so a terminal Highway room reached
  by two roads (east + west) is the faithful model; relaxed the dup-destination
  lint for that one case. The Rancher ending (pure dialogue) stayed an action.
- **Verb collision:** RIDE EAST can't work (ride is a MOUNT alias -> tries to
  board), so the highway exits are plain east/west gated on being astride the
  *started* motorcycle (not the horse, not on foot). Playtest the actual words.

WALKTHROUGH_WIN now plays the full 100-point run. Updated the conversion guide's
§15 worked example (interventions 9-11: generalize-the-playtest-bug, primitive-
not-machinery, verb-collisions) and §7 (advertised wear-slots + contents_relation).
716 tests green. AC4 complete; deferred AC2-boat-onto-vehicles refactor remains.

---

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

