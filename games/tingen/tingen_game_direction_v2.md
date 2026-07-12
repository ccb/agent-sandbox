# Tingen — Game Direction v2 (2026-07-03)

*v2.3 (2026-07-03) — forks #5–#8 LOCKED by the user (60s playable rampage; NPC memory resets per
run; early assault allowed w/ one relocation; ~7 in-game days / ~60 min / nightly checkpoint) +
the "Ritual Night — Godot build map" (climax = assembly of built systems). See §13.*

*v2.2 (2026-07-03) — critical design pass: first-ten-minutes script, encounter anatomy, full run
trace with tuned meter economy (anti-turtle: Doom-tiered opposition makes advancing mandatory),
concrete fight+explore differentiation for the three builds, the Ritual Night encounter design,
"why the LLM city matters," and a re-tightened slice (Seq 9→7, two interrupt options).*

*v2.1 (2026-07-03) — pathways expanded to the canon Tingen Six; `assume_form` reframed as the
Seq-4 loss-of-control form (not a separate "Beast" pathway); §6 and §13 updated to canon names.*

**This supersedes the detective/investigation framing of `tingen_mystery_pixel_game_gdd.md`.**
The GDD's living-city, occult-canon, and world-manager ideas are kept; its investigation system,
forensic deduction, interrogation loop, and ally-deployment management are **dropped** (user
decision, 2026-07-03). This doc is the new north star. Decisions here were made by the design
agent at the user's request ("I am no design expert — make a lot of decisions that make this game
fun"); the handful of genuine forks are flagged **[USER]** at the end.

---

## 1. What Tingen is now

**An occult-noir action-RPG roguelite set in a living city of *Lord of the Mysteries*.**

You are a low-Sequence Beyonder in Tingen. A cult is completing a ritual that will pull something
through from the Beyond and end the world. To stop it — and survive the descent — you hunt the
monsters and rogue Beyonders hiding among the city's people, grow your own power by advancing your
pathway, and resist the madness that power brings, all while the city rots around you and forces
larger than you begin to *notice*.

Three genres, each carried by something already built:
- **RPG** — the Sequence/pathway progression spine (LotM's own system: hunt same-pathway
  Beyonders → harvest their Characteristic → digest it to advance → gain abilities). Build
  variety = replay variety. *Foundation built:* the ability/kit data model, the item-backed
  weapon system, `assume_form`.
- **Open-world** — a dense, alive Victorian occult city where every NPC has a public life and a
  secret one and *thinks* (the LLM sidecar). No quest rails: you find the action by talking to
  the city. *Foundation built:* the whole city, 19 LLM-driven scheduled NPCs, vision-gated
  perception, the GM/orchestrator.
- **Roguelite** — each run is a descent toward **Ritual Night**. Death or loss-of-control ends
  the run; the city reshuffles and meta-progress carries forward. *Foundation built:* the
  doomsday/summoning engine, dynamic slotting groundwork, the deterministic combat that makes
  every fight winnable-or-fatal on skill, not dice.

**The crown jewel is combat** (complete, live-verified). Everything else exists to feed the
player into fights that matter and make the wins mean something.

## 2. The core loop (moment to moment → run to run)

```
ROAM the living city ─▶ FOLLOW a rumor/lead (from LLM NPCs) to a monster / cult cell / site
        ▲                                   │
        │                                   ▼
   spend / rest                        FIGHT it  (the combat system)
        ▲                                   │
        │                                   ▼
  ADVANCE your Sequence  ◀── HARVEST characteristic + loot ──▶ the Doom clock ticks up if you DIDN'T
   (more power, more madness)                                   (cult progresses offscreen)
        │
        ▼
  push toward RITUAL NIGHT ─▶ WIN (interrupt the descent) or FALL (die / lose control)
        │
        ▼
  META: unlock pathways, keep Beyonder-knowledge, city reshuffles ─▶ next run / harder cycle
```

The engine of fun is a **push-your-luck** tension between two things the player feels every
minute: *the world is getting worse and I'm racing a clock* (roguelite escalation) and *the power
that lets me win is the same power that could destroy me* (the LotM madness fantasy).

### Why you roam (the loop's missing incentive, fixed)

"Roam → follow lead" only works if roaming is *pull*, not filler. Leads do **not** come to you:
they live in NPC heads, and information only exists where a witness was standing (§10). Four
concrete pulls keep the player moving through the city instead of camping the board:

1. **Leads are perishable.** A lead left to cool goes cold — the monster moves or kills again
   (Doom +5, and the *new* lead spawns somewhere else). The city is a pot that boils over
   wherever you aren't watching.
2. **Your build eats the city.** Advancing needs a *same-pathway* Characteristic (§6), and
   same-pathway Beyonders are hidden among the population. Locating your next meal *is* the
   exploration game, and each pathway locates differently (§6, explore verbs).
3. **Acting deeds live outdoors.** The Madness drain (§4) comes from performing your Sequence's
   role out in the world — a Seer telling fortunes, a Hunter stalking prey. Turtling indoors
   lets Madness sit high.
4. **Preparation is spatial.** Caches, ritual materials, ambush ground, the quiet route into the
   crypt (§9) — all are found, not menu-bought. The player who knows the city fights easier
   fights on Ritual Night.

## 3. The first ten minutes (the new-player contract)

The doc's promise — "the fun is the hunt" — must be cashed before minute five, in play, with zero
tutorial text screens. The GM guarantees the opening of every run; run one is tuned like this:

| clock | beat | what it teaches |
|---|---|---|
| 0:00 | Cold open in your lodging. One premise line. Loadout: revolver + 12 rounds (`player_loadout`, built). HUD shows **Doom only** — the other meters reveal on first trigger (progressive disclosure). | Who you are; the clock exists. |
| 1:30 | The first lead is **hot and close**, guaranteed by the GM: `constable_brom` hammering on doors — *"the butcher's on Iron Cross. Blood under the door."* No map marker; he names the street. | Leads come from people; the city is navigated by talk and signage. |
| 3:00 | **The butcher fight** (`bram_kell` — the built, live-verified fight). Phase 1: human form, cleaver telegraphs teach dodge timing. At half HP he casts `assume_form` — the **mask-drop** — and phase 2 is the `bieber_monster`. | Telegraphs, dash i-frames, poise; and the game's signature beat: *people are wearing faces.* |
| 5:30 | **Harvest.** A grey wet mass precipitates (Bieber canon). It's *off-pathway* — Brom: sell it quietly, or keep it as ritual fuel. *"He wasn't the only one."* | The Characteristic economy and its first fork (digest / fuel / sell). |
| 6:30 | If the fight had witnesses, **Heat** reveals itself with a toast — and within minutes an NPC is heard retelling the fight. | Meters are narrated by the city, not just bars (§10). |
| 7:00–10:00 | Back on the street: **two leads** in walking range — one smells like your own pathway's prey (your first real hunt), one is a cult courier sighting. A public cult event ticks Doom +10 in view. | The core choice: feed the build or fight the clock. The loop is open. |

Rules of the contract: **first fight before minute 4; first real choice before minute 10; every
system met in play, none by text.** Dying to the butcher on run one is acceptable roguelite
handshake (runs are short; the genre teaches by death) — but phase 1 of that fight is tuned
generous.

## 4. Pressure, redesigned (drop the GDD's 5 flat meters)

The GDD tracked five citywide meters (Corruption, Panic, Investigator Fatigue, Cult Readiness,
Attention of the Beyond). Critique: five overlapping meters are illegible, and Fatigue/ally-morale
belonged to the dropped ally-management layer. **Canon (§⑦ of `tingen_summoning_canon.md`) already
proposes a better, tighter set: three risk bars — noticed / corruption / heat.** Adopt that, plus
the one personal meter that makes power a *decision*:

| meter | what it is | rises when | at max |
|---|---|---|---|
| **Doom** (world clock) | how close the cult is to the descent | time passes; cult couriers/rites you DON'T stop; monsters you leave alive | **Ritual Night** triggers — the run's climax (§9) |
| **Madness** (your control) | how close YOU are to losing yourself | advancing Sequence; ingesting a Characteristic; over-using high-tier / `assume_form` powers | **you lose control** → your Seq-4 creature-form takes over → run ends (canon: Old Neil, Ray Biber; see §6's `assume_form` reframe) |
| **Notice** ("Attention of the Beyond") | how much the *unknown* is watching you | using flashy/high-Sequence powers; digesting characteristics; divination (canon: the low-Seq exposure channel) | Beyond-touched **hunters spawn to kill you** |
| **Heat** (officialdom) | how exposed you are to the law/Nighthawks | using powers in public view; leaving bodies where they're seen | the **Nighthawks** (official Beyonders) hunt you |

The player *mainly feels two*: the world worsening (**Doom**) and their own two-edged power
(**Madness**). **Notice** and **Heat** are the "how you play" knobs — they punish flashy/reckless
play and reward the deliberate. Panic, crowd-thinning, shop closures etc. become **derived
flavor** of high Doom (the city visibly reacts), not tracked variables. Fatigue is cut.

### Meters have ladders, not just ceilings

A meter that only matters at 100 is a meter the player ignores until it kills them. Each has two
visible thresholds before the max, so pressure is *felt* on the way up (numbers are tuning
targets, all deterministic):

| meter | soft (≈50 / 40) | hard (≈75 / 70) | max (100) |
|---|---|---|---|
| **Doom** | streets thin, prices rise, night comes "earlier" (derived flavor); cult ops get Beyonder guards | monsters hunt bolder; opposition tier rises (§6 anti-turtle table) | Ritual Night begins — with a fuse, not a cutscene (§9) |
| **Madness** | **whispers**: the sidecar tints ambient lines; occasional *false* leads surface (§10 — the city starts lying to you) | **the form stirs**: high-tier casts cost bonus Madness; audiovisual distortion; the GM may fire brief corruption directives | the GM directive casts `assume_form` — the creature takes over; run ends |
| **Notice** | omens (flavor warnings — mirrors crack, dogs refuse you) | **a hunter is dispatched**: one Beyond-touched stalker enters the city, tracking you | it looks back: elite hunter + a permanent run affliction |
| **Heat** | constables ask questions — NPCs *tell you* they were questioned about you | **Nighthawks investigate**: patrols near your lodging; digestion nights (§6) can be raided | a Nighthawk kill team, on you, wherever you are |

### Madness is a cycle, not a ratchet

If Madness only ever rises, the dominant strategy is "never advance" — which kills the game (§6
closes the other half of that hole). So Madness has real sinks and flows both ways:

- **Sources:** digesting a Characteristic **+35**; invoking `assume_form` **+25** per use;
  witnessing descent rites **+5**; Hermit-pathway digestion pays a whisper surcharge (canon:
  the Hidden Sage).
- **Sinks:** a night's **Cogitation** (sleep at a lodging) **−10**; each **acting deed** −5 (cap
  3/day) — performing your Sequence's role in the world, data-driven per rank (a Seer divines
  for someone, a Provoker picks and wins a provoked duel; rides the built `DeedRunner`);
  Hermit-only **cleansing rites** at consecrated ground.
- **The rhythm:** advance → spike to ~35–50 → spend a day *being* your Sequence to come down →
  advance again. That's the canon acting method as a play loop, and it forces the player back
  into the city between power-ups (§2's pull #3).

`WorldState.gd` already holds `corruption / panic / fatigue / cult_readiness / attention` — the
rename/rework is: keep **corruption→Doom** and **attention→Notice**, add **Madness** (player) and
**Heat**, drop **fatigue**, fold **panic** into derived flavor and **cult_readiness** into Doom's
fill rate. Small, additive change to an existing autoload.

## 5. Rumors → Leads (repurpose, don't delete — and reuse the board UI)

Investigation-as-forensics is cut, but the city being *alive with information* is the whole point
of the LLM tech. So: **rumors become the open-world lead/quest system.** NPCs surface leads through
conversation and ambient chatter — "the butcher on Iron Cross hasn't been himself," "something
walks the canal after dark." A lead points you at an emergent encounter; you find the action by
*talking to the living city*, not reading map markers. The **existing `InvestigationBoard.gd`
panel is repurposed as the Leads board** (a tracker of what the city is whispering), not deleted —
honoring "take what's sensible." The GM/orchestrator **slots leads per run** (the GDD's dynamic
slotting §8.5, which is exactly a roguelite reshuffle: each run the ritual site, the first
lost-control Beyonder, the key courier are placed differently).

Three rules give leads texture beyond "quest list with flavor":

- **Leads are witness-born.** A lead exists only because some NPC *saw or heard something* (the
  vision-gated perception layer, built). No witness, no lead — a careful monster produces a
  quiet city and a climbing Doom bar. **Silence is itself information.**
- **Leads have a lifecycle:** *whisper* (vague, district-level — overheard ambient) → *lead*
  (named person/place — earned by conversation) → *cold* (ignored too long; Doom +5; the trail
  re-emerges elsewhere, worse).
- **At Madness 50+, some whispers are false** (§4) — delivered through the same channel as true
  ones. The player's trust in the city degrades exactly as the canon says it should.

## 6. The RPG spine — Sequences & Pathways (LotM-faithful, kit-driven)

Progression *is* the LotM Sequence system, and it's canonically a combat-and-risk loop, not a
skill tree you buy: **advance by hunting a same-pathway Beyonder, harvesting the Characteristic
that precipitates from the kill, and digesting it via an "acting" ritual — which spikes Madness.**

**Pathways vs. sequences — get the naming right.** A **pathway** is named by its **Sequence 0**
(the top of the ladder): *Fool, Hermit, Hunter, Darkness, Death, Spectator*. A "sequence name"
like **Seer, Sleepless, Corpse Collector** is *not* a separate build — it's a **rank** on a
pathway's 9→0 ladder. In-game a player picks **a pathway** and starts at its **Seq 9** rank,
then climbs **9 → 8 → … → lower** (each step = a promotion up the same ladder).

### The Tingen Six (canon-accurate pathway set)

Three of these are literally the **Evernight Goddess's** pathways — the **Nighthawks' church is the
Tingen anchor** — and the other three are the arc's key figures. Tingen is the anchor for all six.
Verified rank names below come from `docs/canon_tingen_characters.md` (now written).

| Pathway (Seq 0) | Seq 9 (low rank) | notable ranks (verified) | Tingen anchor | game roster | playstyle |
|---|---|---|---|---|---|
| **Fool (愚者)** | Seer (占卜家) | Clown 小丑 (Seq 8), Magician 魔术师 (Seq 7) | Klein; the Antigonus notebook | (Klein-flavored) | misdirection/control, divination-dodge, marionettes at depth |
| **Hermit (隐者)** | Mystery Pryer (窥秘人) | Sage 贤者 (Seq 2) | Old Neil (lost control to Hidden Sage pollution); astrology/ritual/knowledge | `old_neil` | prepared ground: wards, zones, occult utility |
| **Hunter (猎人)** | Hunter | Provoker 挑衅者 (Seq 8), Pyromaniac 纵火家 (Seq 7) *(verify per follow-up (a))* | Nighthawk-adjacent field muscle; guns → fire → blood-fury | `constable_brom` | mobile gun DPS scaling into fire and berserk melee |
| **Darkness (黑暗)** [Evernight] | Sleepless (不眠者) | Midnight Poet 午夜诗人 (Seq 8), Nightmare 梦魇 (Seq 7) | Evernight Church night-combat/dream (Dunn Smith, Leonard) | (Nighthawk) | dream/fear debuffs, spirit strikes, night mobility |
| **Death (死神)** [Evernight] | Corpse Collector (收尸人) | Gravedigger 掘墓人 (Seq 8), Spirit Medium 通灵者 (Seq 7), Necromancer 死灵导师 (Seq 6 — Daly) | Evernight Church; graves/spirits | `sister_auber` / `brother_cassian` | spirit summons, decay, life-drain |
| **Spectator (观众)** [Evernight] | | | Evernight Church; mesmerists/psychiatrists | `dr_aldous_crane` | mind control, charm, read-intent |

**Fool / Hermit / Hunter = the three vertical-slice player builds.**
**The Evernight trio (Darkness / Death / Spectator) = the world factions / future player builds.**
The **Nighthawks** and the **monsters wearing human faces** are drawn from these three — they're
what the city *is* before they're what the player can *become*. Each maps to an existing NPC on the
roster (table above), grounding the world in canon flavor now and seeding post-slice builds later.

### The three builds, actually differentiated (fight AND explore)

A pathway that only changes your damage type is a costume. Each build differs in **how it
fights**, **how it finds prey**, and **which meter is its personal enemy** — all mapped to the
built ability schema (`projectile / strike / spell+zone / movement / effect / transform`) and the
built occult-tool code (`DivinationTool`, `ResidueSightTool`, `GrayFogTool`; items
`spirit_pendulum`, `divination_kit`, `gray_fog_focus` already exist):

| | **Hunter** | **Fool (Seer)** | **Hermit (Mystery Pryer)** |
|---|---|---|---|
| **fights by** | tempo: open at range (`revolver_shot`, built), close with `dash` (built), finish in melee; `blood_frenzy`-style spikes at depth. Fast kills, thin margins; resources = ammo/stamina. | denial: slow/silence zones (`paper_charm`, built), a decoy double, a paper-substitute swap (i-frame blink — `movement` class). Wins by making the enemy miss; resource = spirituality. | preparation: pre-placed ward/burn zones, damage-over-time brands, long cooldowns. Strongest on chosen ground, weakest ambushed in the open. |
| **finds prey by** | tracking and ambush: physical trails between rooms; initiating unseen grants a first-strike poise bonus (deterministic opener, no RNG). | **divination**: pendulum-dowse a lead to district level; *read the face* — is this NPC wearing one? Canon cost: divination is THE low-Seq exposure channel, so every reading is **Notice +10**. Knowledge is bought with being seen. | **ritual literacy**: read residue at scenes (tool built); ward the lodging (safer digestion nights); **counter-rites** at discovered cult sites — the only verb in the game that pushes **Doom down** directly, at material + Notice cost. |
| **personal enemy meter** | **Heat** — the gun is loud; kills get witnessed. | **Notice** — seeing means being seen back. | **Madness** — knowledge corrupts (Hidden Sage whispers: digestion surcharge, but exclusive cleansing rites). |

One sentence each: **the Hunter strikes first, the Fool knows first, the Hermit prepared the
ground last week.**

**Kit honesty — built today vs. to-author:** built ability rows: `revolver_shot`, `dash`,
`paper_charm`, `cleaver_swipe`, `charge`, `hook_throw`, `blood_frenzy`, `assume_form`. The slice
(Hunter 9→7) needs **two new data rows**, both expressible in the existing schema: `mark_prey`
(Seq 8 Provoker — an `effect`-class mark/taunt) and `incendiary_round` (Seq 7 Pyromaniac — a
`projectile` that leaves a burn `zone`). Fool/Hermit ladders are authored post-slice (decoy,
substitute-swap, ward circle, brand — all existing classes). No engine work, only JSON.

Each pathway is a **Sequence ladder** (demo scope: Seq 9→7 for the slice; 9→6 post-slice); each
tier is a promotion that grants or upgrades abilities in that kit. **Advancing a tier costs:** one
**Characteristic** from a *same-pathway* Beyonder (canon — and it makes "which monster do I hunt"
a build decision) + your acting deeds done + **a digestion night** at a lodging. Canon precedent
Rear Bieber: *interrupted digestion = instant loss of control* — so a digestion night while
**Heat ≥ 70** risks a Nighthawk raid mid-digestion (Madness +25, Characteristic wasted). Where
you sleep, and how loudly you lived that day, matters on the night you advance. Off-pathway
characteristics aren't dead loot: they're **ritual fuel** (Hermit counter-rites, wards) or **quiet
income** (sold to a church fence — money for gear). Gear rides the **item-backed weapon system
already built** (`items.json`, `ItemDB`) — different revolvers/charms/blades as loot.

**Pity slotting (no dead-end runs):** the GM's per-run slotting **guarantees at least two
same-pathway Beyonders** for the player's pathway — one findable in day 1, one mid-run. A run can
go badly; it cannot become unwinnable-by-lottery.

### Power is mandatory (closing the turtle hole)

Trap to design out: *never advance → never gain Madness → win by turtling at Seq 9.* Combat is
deterministic and skill-winnable, so if numbers never gate anything, the optimal player ignores
the entire RPG spine. The fix is **Doom-tiered opposition** — legible, deterministic, no RNG:

| Doom band | what's standing between you and the win |
|---|---|
| < 40 | human cultists, one Seq-9-tier lost-control Beyonder |
| 40–70 | Seq-8-tier monsters; cult ops get a Beyonder guard |
| > 70 | Seq-7-tier avatar-touched creatures; the crypt celebrant is Seq-7-tier |
| Ritual Night | the descended **avatar is Seq-6-tier**: its poise regeneration simply exceeds a Seq-9 kit's poise damage — provably, on paper, no dice — inside the transformation window (§9) |

A Seq-9 turtle can still *win* — by the early interrupts (steal the vessel, burn the grimoire,
§9) — but those get harder as Doom rises (the cult guards what matters), and they only earn the
**Quiet Win** (§9), the smaller meta payout. The full prize sits behind the avatar window, and
the avatar window sits behind Sequence 7. **Power is the door; Madness is the toll.**

### `assume_form` = the Sequence-4 monster form (Madness is the leash)

There is **no separate "Beast" pathway.** Canon: at **Sequence 4** a Beyonder gains a
**神话生物形态 (mythical-creature form)** — the monster shape of *whatever pathway they're on*. Losing
control (our **Madness** meter, §4, maxed) means that form **takes over the Beyonder** — exactly
what happened to **Old Neil** (Hermit pathway) and to our butcher `bram_kell`. So `assume_form`
is not a build; it's the **high-Sequence form on every ladder**, and **Madness is the leash** that
decides whether you wield it or it wields you.

Mechanically this makes `assume_form` a **two-edged, pathway-agnostic tool**: at high Sequence you
can *briefly* invoke your creature-form for overwhelming power at steep Madness cost (+25/use) —
but max the Madness meter and control flips, the form takes over, and the run ends (the §4 Madness
fail / canon Ray Biber loss-of-control). Cross-ref: **§4 Madness** (the meter) and the
loss-of-control transformation is the same event the Ritual-Night avatars model (§9). The
push-your-luck fantasy — "the power that lets me win is the power that could destroy me" — is now
literal and pathway-wide, not walled off in one build.

### Canon verification follow-ups (before data)

Before any of this hardens into game data, confirm against the wiki:
- **(a)** Each pathway's full **Seq 9 → 0 ladder** — `docs/canon_tingen_characters.md` verified
  the Fool (Seer→Clown), Darkness (Sleepless→Midnight Poet→Nightmare), Death (Corpse
  Collector→Gravedigger→Spirit Medium→Necromancer) and Hermit (Mystery Pryer, Sage) cells above;
  the **Hunter ladder ranks (Provoker/Pyromaniac) and all Spectator cells still need wiki
  verification** before they're written into data. Also verify the Hunter pathway's true Seq-0
  name (the "Red Priest" rank placement in v2.1 was unsourced — keep "Hunter" as the build's
  display name regardless; it's the arc-appropriate rank).
- **(b)** **Which church owns the Hunter pathway** — likely **NOT** Evernight (probably a God of
  Combat / Steam-adjacent church). Confirm before we place Hunter Beyonders in a faction.
- **(c)** `docs/canon_tingen_characters.md` is written — use it for flavor grounding when
  authoring roster NPCs (it also pins the loss-of-control precedents Madness is modeled on).

## 7. Monsters & encounters (reuse everything, all canon)

Three enemy classes, all already expressible in the built data schemas:
- **Lost-control Beyonders / corrupted humans** — hide among the NPC population wearing a normal
  face; `assume_form` drops the mask under pressure (the butcher/`bieber_monster` template, done).
  The **Fool's** Diviner sight and the tension of "is *this* one a monster?" live here.
- **Cult operatives** — the summoning cell (built): couriers, ritualists, the site guard.
- **Descended avatars / ritual spawns** (endgame) — the two-stage descent gives a *canon boss
  counterplay* (§①/§⑦): kill the avatar during its "delayed transformation" window to wound the
  true entity before it fully lands. `assume_form` + a timed window models this directly — the
  Ritual Night boss is a race against that clock (§9).

### Anatomy of one encounter (the minute-to-minute, traced)

A single hunt is a five-beat arc, and every beat touches a meter — that's how "you feel the
pressure every minute" gets cashed:

1. **The lead** (§5): *"the dockhand at the Salt Stair drinks alone now, and the gulls won't
   land near him."* A name, or just a district and a wrongness.
2. **The stalk.** NPCs run real schedules (built), so following a suspect's day is real play:
   watch who he meets, where he eats, when he slips away. Pathway verbs shortcut it — the Fool
   *reads the face* (Notice +10), the Hunter cuts the trail, the Hermit reads residue where he
   sleeps. **You choose the ground and the hour:** take him in the noon market and every witness
   is Heat; follow him to the canal at midnight and there are no witnesses — but night is *his*
   ground (monster tier +1 after dark). A clean, deterministic tradeoff, chosen before a single
   blow.
3. **The mask-drop.** Combat opens against the human form; under pressure the NPC's own layers
   cast `assume_form` (built — never an engine reveal) and the fight restarts as phase 2 against
   the creature. The signature beat, every hunt.
4. **The kill.** The deterministic combat game: telegraphs, poise, i-frames, positioning. No
   dice — every death is legible.
5. **The harvest, under pressure.** The Characteristic precipitates over ~60 seconds. Harvesting
   in public view = Notice + Heat; leaving before it precipitates = the prize lost; the downed
   body is never deleted (invariant) — whoever finds it later is a witness, and Heat arrives on
   a delay, with a story attached (§10). *Take the prize, hide the body, or run?*

Aftermath ripples through the city: gossip about the fight, the lead resolves, Doom eases (a
monster that will never kill again) or doesn't (you fled).

## 8. The roguelite run & meta (specific, not vibes)

**Run shape:** a run is **3 in-game days + Ritual Night**, one in-game day ≈ 15 minutes real
time → **a run is ~45–60 minutes** (see [USER] fork 8). Doom starts at 10 and its passive tick
alone reaches 100 by the end of night 3; cult operations completed offscreen add +10 each, your
interference subtracts. An untouched cult reaches Ritual Night mid-day-3; an opposed one is
pushed into night 3 or later. The player can also **force the climax early** by assaulting a
discovered ritual site ([USER] fork 7).

**Run start:** you wake in your lodging (the safehouse interior, built), pick a pathway (slice:
Hunter only), the GM has already slotted the run, and the first hot lead lands inside two
minutes (§3). No hub, no shop screen — the city is the hub.

**A run ends** on death (HP), loss-of-control (Madness 100), or the true descent completing
(§9). **Win grades** (§9): the **Quiet Win** (ritual scattered before the avatar lands) and the
**Deep Win** (avatar slain in its window — the entity is wounded).

**Carries over vs. resets:**

| carries over (meta) | resets (run) |
|---|---|
| pathway unlocks (Fool, Hermit, then the Evernight trio) | Sequence (every run starts at Seq 9) |
| the **codex** — Beyonder-knowledge earned by encounter: archetype tells, ritual materials, interrupt options discovered | items, money, meters |
| starting-loadout options (earned, not stat-boosting) | NPC states, city state, who-is-corrupted |
| account level → cosmetic/loadout track, **never stats** (no numeric snowball; the fun is skill + build) | leads, cult progress |

**The reshuffle** is the built slot system, extended. `scenario.json` already slots
`primary_ritual_site`, `decoy_courier`, `first_corrupted_civilian`; the run director grows this
to ~6 slots: ritual site (from 3 candidate sites), 2 corrupted civilians (from the 19-persona
roster), courier, vessel location, grimoire holder, first-lead vector. **The 19 personas persist
across runs — who among them is corrupted is what reshuffles.** Last run's friendly barmaid can
be this run's monster, and the player's knowledge of *people* stays valuable while their
knowledge of *answers* expires (see [USER] fork 6 on cross-run NPC memory).

**Death cadence:** early runs die at the butcher or at Ritual Night — both inside the first
hour. Every death pays out codex entries earned in-run plus account progress; a Ritual Night
loss pays more than a day-1 death (depth-scaled, so late losses sting but never feel like zero).

### A run, traced end-to-end (the economy closes)

**Day 1 (Doom 10→35).** Butcher fight (§3); off-pathway Characteristic banked as fuel. Afternoon:
stalk the Hunter-pathway lead; midnight canal kill — same-pathway Characteristic. Digestion night:
Madness 0→35. Wake **Seq 8** (`mark_prey`).
**Day 2 (Doom →55).** Morning acting deeds ×2 + last night's Cogitation: Madness 35→15. Intercept
the cult courier (Doom −10, and the crypt's quiet route learned — §9 payoff). The pity-slotted
second prey is Seq-8-tier now — a real fight. Kill, harvest. Digestion night 2: Madness 15→50 —
**whispers begin; one false lead enters the board.**
**Day 3 (Doom →85).** Wake **Seq 7** (`incendiary_round`). Streets thin (derived flavor). The
choice that defines the run: hunt the **vessel** (make Ritual Night easier), shed Madness with a
deed day (safer), or push Notice chasing the grimoire (greedier meta payout). No option is
dominant; all three cost the same scarce thing — daylight.
**Ritual Night (Doom 100).** Bells; blood-lit sky. In via the courier's route (day 2's earn).
The player goes greedy: lets the avatar land, burns `blood_frenzy` + incendiaries in the
transformation window, kills it at the second-to-last candle. **Deep Win.** Final Madness 65 —
`assume_form` never invoked, this time.
**The counter-trace (the turtle):** a player who never advanced meets Day 3 at Seq 9: the
celebrant's poise doesn't break, the avatar is untouchable on paper, and the only live option is
a vessel steal under maximum guard. Possible, rarely — and it pays only the Quiet Win. The
economy's message: *power is necessary and power costs sanity; manage the exchange rate.*

**The meta-arc:** runs 1–2 die learning (butcher, Ritual Night); run ~3 lands a Quiet Win and
unlocks the **Fool**; runs 4–6 chase the first **Deep Win**, which unlocks the **ascension
cycle** — Doom fills faster, Notice starts above zero, avatar tier rises, the Hermit and (later)
the Evernight trio come online. Target: **first Deep Win inside 6–10 hours.**

## 9. Ritual Night (the climax is an encounter, not a meter)

The failure mode to design out: Doom hits 100, a boss spawns, the run ends in a corridor. Ritual
Night is instead a **staged raid on a live ceremony** — the summoning engine already *walks the
cult through the real canon steps* (gather offerings → descend to the crypt → lay each offering →
drive the rite; built, in `scenario.json` + `CitySummoning`), so the climax is the player
*physically interrupting a process that is actually running*, at the point of their choosing.

**The fuse:** at Doom 100 the bells ring city-wide and the sky goes wrong — and the ceremony
takes **one more in-game hour (~12 real minutes)** to complete. Wherever you are, there is time
to cross the city and break it. A climax with a fuse, never a cutscene loss.

**The beats:**

1. **Approach.** Heat decides the street outside: clean hands slip past constable cordons;
   Heat ≥ 70 means Nighthawks are hunting *you* through the same streets the cult controls — a
   three-faction night (§10).
2. **The spirit wall** (canon §⑥ step 6). Breach it loudly and every celebrant turns as one
   wave; or enter by the **courier's route** — learnable in-run (§8's day-2 earn). Exploration
   pays off exactly here.
3. **The interrupt — a menu, not a corridor** (canon §⑦, each a different fight *shape*):
   - **kill the celebrant** — a duel while acolytes keep the chant alive (a DPS check with adds);
   - **break the altar / tear the wall** — an objective fight: channel the interaction while
     defending (Hermit ground-prep shines);
   - **steal or destroy the vessel** — mobility and stealth under the chant (Hunter-shaped);
   - **wait for the avatar and kill it in the window** — the greedy option, below.
4. **Backlash** (canon §⑤ — a rite interrupted rebounds on its casters): break the ceremony
   mid-chant and unshielded celebrants **lose control** — `assume_form` fires down the cult's
   own ranks and the crypt collapses into three-way chaos that attacks everyone. The cult can
   eat itself; the player who times the interrupt uses the backlash as a weapon.
5. **The two-stage descent** (canon §① — the greedy path). If the rite completes its call, the
   **avatar lands** (Seq-6-tier, an `assume_form` creature on a form row) and the **delayed
   transformation window** opens — made visible by the **altar candles guttering out one by
   one** (canon's candle rite as a boss timer; five candles ≈ 90 seconds). Kill the avatar
   in-window = **the Deep Win**: the true entity is wounded through its avatar (canon), the
   biggest meta payout, the ascension unlock. The last candle dies with the avatar alive =
   **true descent** — the run is lost to a fast, terrible cut of the city ending. You don't
   fight a god; you fail to prevent one.

**Win grades:** interrupt before the avatar lands = the **Quiet Win** (the god was never
wounded; modest payout). Kill the avatar in its window = the **Deep Win**. Earlier is easier and
pays less; latest is hardest and pays most — the run's push-your-luck thesis, restated at full
volume in its final two minutes.

## 10. Why the LLM city matters (the differentiator, cashed)

If the LLM NPCs only decorate dialogue, a scripted game does this cheaper. They earn their cost
by making **information itself** the living system — five things a scripted city can't do:

1. **Gossip is real state.** The stimulus/witness layer (built) means your public deeds travel
   NPC-to-NPC and come back to you *as talk*. Heat isn't only a bar — it's the fishwife going
   quiet when you enter, a dockhand retelling your canal fight wrong. The meters are narrated
   by the city.
2. **The mask talks back.** The corrupted NPC's LLM plays its cover identity under your
   questions — there is no scripted "tell" list to look up on a wiki. Press too hard and it can
   *spook*: the GM relocates it, and the city genuinely doesn't know where it went. Every
   suspect conversation is a real read of a mind that knows it's hiding. (Interrogation returns
   — not as a minigame, but as actual talking.)
3. **Leads are witness-born** (§5). Quests exist only where perception happened. A monster that
   kills the only witness has *actually* covered its tracks — and the resulting silence, against
   a climbing Doom bar, is the scariest signal in the game.
4. **Madness speaks through the same channel as truth.** At Madness 50+ the sidecar tints
   ambient lines and seeds false whispers (§4) — the city gaslights you through the very system
   you've learned to trust. Only a generative city can lie fluently.
5. **Three factions think at once.** The cult runs real goal chains (built); the Nighthawks
   investigate you by *asking NPCs what they saw* — so an emergent manhunt assembles itself out
   of actual witnesses. On a high-Heat Ritual Night, cult, Nighthawks, and player converge on
   the crypt with three live agendas.

The moment only this game produces: *you fought the mask-dropped monster in the noon market on
day 1. On day 3 a lamplighter describes the fight to you — wrong — blaming "a stranger in a gray
coat," and the constables spend the evening hunting a fiction while you walk to the crypt.*

**Guardrails (all existing invariants):** the LLM is never on the frame path; conversation is a
deliberate, sat-down activity, not a combat verb; every NPC belief is grounded in
engine-published perception facts (the engine stays authoritative — even the Madness whispers
are engine-tagged as unreliable, so the *game* always knows what's true).

## 11. What's dropped from the GDD, and why

- **Investigation / forensic deduction / 3 evidence layers / hypothesis mechanics** — user cut;
  the fun is the *hunt and the build*, not paperwork. Clues become **leads** (§5).
- **Interrogation-as-mechanic** — talking to NPCs stays (it's the lead system + the LLM
  showpiece, §10), but there's no correctness-scored interview minigame.
- **Investigator Fatigue / ally-deployment management** — cut with the ally-command layer.
- **Rumor-as-witness-reliability sim** — simplified into leads (§5).
- **Occult tools as forensics** (residue sight, gray-fog reconstruction as evidence viewers) —
  repurposed into **pathway explore verbs** (§6) instead of investigation gadgets.
Kept and repurposed: pressures→**§4**, rumors→**§5**, dynamic slotting→**roguelite reshuffle**,
narrative stages→**difficulty/Doom tiers**, the world-manager/GM→**the run director**.

## 12. Scope — vertical slice first

Ship one coherent slice before breadth (the GDD's own scope discipline, §5.3, still holds). The
slice is deliberately **smaller than v2.1's**:

**In the slice:** one pathway (**Hunter**), **Seq 9→7** (two advancements, two new ability JSON
rows — §6), the butcher + the 3-cultist summoning cell + the crypt (all built content), the four
meters (§4), leads v1 (converse-route hook + the repurposed board), the 3-day run, **Ritual
Night with two interrupt options** (kill the celebrant, break the altar) **+ the avatar window**,
one death→meta loop with **one unlock** (the Fool, as the teaser) and codex v1.

**Explicitly deferred:** Fool/Hermit as playable, the Notice-70 dedicated hunter archetype (v1:
reuse an existing cult-assassin form), Hermit counter-rites, the ascension cycle, the
loss-of-control rampage ([USER] fork 5), cross-run NPC memory ([USER] fork 6), the Evernight trio.

**Net-new engineering** (everything else reuses built systems): the 4-meter rework of
`WorldState` (small, §4), the Sequence/advancement + harvest loop, acting deeds on the existing
`DeedRunner`, the lead-surfacing hook on the converse route, the run/meta shell over
`SaveManager`, the Ritual Night director as interrupt-checks + a window timer on the existing
summoning engine, and three data rows (`mark_prey`, `incendiary_round`, the avatar form).

## 13. [USER] decisions — override any of these

Decisions made (say the word and any is a one-line change):

1. **Tone:** pulpy occult-noir action-horror — tense and eerie, but the *fun* is empowerment and
   the hunt, not misery. (Alternative: bleaker survival-horror. I chose pulpy because it suits an
   action-roguelite and the combat's power fantasy.)
2. **Death model:** roguelite — a run ends but meta-progress carries (forgiving, replay-friendly).
   (Alternative: harsher permadeath with less carryover.)
3. **First build:** **Hunter (猎人)** as the vertical-slice pathway — its gun kit is the cleanest to
   teach and the most complete today, and it scales into a satisfying fire/berserk power curve.
   Fool and Hermit are the other two slice builds. (Alternatives: lead with Fool or Hermit.)
4. **Madness = a hard fail** (lose control → run ends). Softened on the way up by the §4
   threshold ladder (whispers at 50, the form stirring at 75), so the cliff is telegraphed.
   (Alternative: a debuff spiral with no cliff.)

**Forks — DECIDED & LOCKED (2026-07-03, by the user). These are authoritative for the sprint:**

5. **Loss-of-control = a 60s playable rampage, then run-end.** At Madness 100 you *play* your
   Seq-4 creature-form for ~60 unwinnable seconds (reuses `assume_form` + existing forms) before
   the run ends — the central threat is experienced, not a game-over screen. **In the slice.**
6. **NPC memory resets each run** for the slice (personas persist). Cross-run "haven't we met?"
   memory is the flagged signature feature to prototype *right after* the slice — not now.
7. **Early assault ALLOWED.** The player may force Ritual Night by hitting the ritual site once
   discovered; if the cult was tipped it **relocates once** as counterplay. (See "Ritual Night —
   Godot build map" below for how this stays cheap.)
8. **Run = ~7 in-game days, ~60 min wall-clock, nightly safe-house checkpoint.** In-game days are
   a fictional calendar (the clock is compressible) — 7 days × 3 phases = 21 event slots for
   leads/escalation/routines without spending more of the player's hour. Death or the rampage
   costs **the current day's progress, not the whole run** (the nightly checkpoint), which keeps a
   longer immersive descent fair and softens #5's sting.

### Ritual Night — Godot build map (feasibility, agreed with the user)

The climax is **assembly of built systems, not new engines** — scope the slice to the minimal
spine and add richness later:

| piece | built? | how |
|---|---|---|
| cult defenders | ✅ | combat NPCs (the summoning cell already fights) |
| the avatar boss (two-stage descent) | ✅~ | a `combat_form` + kit; avatar→true-form is `assume_form`, the exact two-phase trick `bram_kell` does. Author + tune, don't build. |
| interrupt targets (break altar / destroy vessel) | ✅~ | `Interactable.gd` + a flag the **summoning engine already reads** (it tracks altar/materials/rite-steps). Kill-the-celebrant = combat. |
| entry choice | ⚠️ scope down | NOT a stealth system — **two RoomGraph portals** (guarded front vs quiet side). Portals are built. |
| the fuse timer | ✅ | Clock + the existing `summoning_climax` countdown |
| **survive the aftermath** | ✅ + canon | interrupting the rite causes **backlash — celebrants lose control** (canon §⑦), so the finale wave is cultists turning into monsters via `assume_form`. More combat + the transform we have. |

**Slice spine:** fight in via one of two doors → interrupt (one interactable) or kill the celebrant
→ if too slow, the avatar half-lands as a boss → **survive the backlash wave** → win/lose screen.
The four-option interrupt menu and any stealth entry are post-slice.

This is the locked direction; the roadmap Track D is written against it.
