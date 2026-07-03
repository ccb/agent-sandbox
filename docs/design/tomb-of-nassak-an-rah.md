# The Tomb of Nassak An-Rah — design spec

**Status:** design draft, not yet implemented. A parser adventure for the
`text_adventure_games` engine, built for a summer game jam as a Zork / Action
Castle homage set in **Vaults of Vaarn**. Adapts the one-page dungeon *The Tomb of
Nassak An-Rah* (Vaarn Adventure Pack 01) into a scored, deadly, noise-driven crawl.

*(Naming: the source spells it "Nassak An-Rah" in body text and "Nassk" in its
filename; we use **Nassak An-Rah**. The named tomb/NPC are from the Adventure
Pack, not Issue 1, but sit cleanly as an Autarch's tomb in canon.)*

---

## 1. Pitch

You are a lone scavenger in the **Blue Ruins** of Vaarn. Under the dying red sun, a
thirty-foot slab of azure stone juts from the phthalo sands — the tomb of the
fallen Autarch **Nassak An-Rah**, a God-king of the old Autarchy, now webbed in
orange corpse-fungus. Three carved faces stare out; their mouths are doors. Inside
wait the Autarch's **Exotica**, his cyborg hounds, his preserved memory — and the
**Mycomorph** rot that defiled him and animates the dead.

**The hook: the tomb listens.** Noise is the enemy. Fungus, bats, and roaming
horrors all *hear* you; every loud act risks waking something that will kill you.
But noise is also a *tool* — the tomb's singing fungal head lures the very
creatures carrying the keys you need. Move quietly, choose your noise, and carry
out what you can.

**Homage lineage:**
- *Zork*: a dark underground complex, light management, a flammable-gas hazard, a
  **roaming "thief"** carrying what you need (here: the two Spawn wearing the
  canopic jars), point-scored treasures, a nonlinear map, a regenerating guardian.
- *Action Castle*: a puzzle chain to a climax, a hint-NPC who helps if treated
  right (**Silas**), a key item gating progress (the **canopic jars**), prescribed
  deaths, a scored winning walkthrough, and a "coronation" denouement (cleansing
  the tomb).

**Decisions locked:** hybrid ending (escape-with-Exotica = win; cleanse + loot =
high score); **noise is the explicit core mechanic** (and we add a `DrawnToSound`
reaction); ancestry-select is a **stretch** goal; **Silas's fate is emergent**
(ally / rival / victim by the player's actions); the tomb is **deadly**.

---

## 2. The core mechanic: noise

Everything keys off the engine's physical-sound model (`docs/design/reactions.md`).

- **Loud verbs carry.** `say`/`talk`, `break`/`smash`, fighting, opening a burial
  cylinder, breaking the Hounds tank, and flailing in zero-g all set
  `AUDIBLE_RADIUS > 0` (or `emit_sound` for ambient noises). Quiet verbs (examine,
  look, careful movement, dousing a light) are silent.
- **Sounds wake threats.** Noise → the bats swarm (Hall of Youth), a Pthalo-Jackal
  pack converges (the halls), the **Fungal Horror** breaks out (Burial Sphere).
  These are `WakesAtNoise`/startle reactions; in a deadly game, most are lethal if
  you're unprepared.
- **Noise is a tool.** The Canopic room's fungal **Mantis-head** *sings* whenever
  it senses movement (an `emit_sound`), and the two roaming **Spawn** are
  `DrawnToSound` — they home in on it. So a player can deliberately make noise to
  gather both Spawn (and both jars) into one room for a single fight, trading
  safety for efficiency. This *teaches* the sound model through a real choice.

- **Even moving is loud.** The tomb is a resonance chamber: plain `go` carries a
  step's worth of sound into the next room (`AUDIBLE_RADIUS` 1), so just *traveling*
  can draw a listening threat. `sneak <dir>` moves in silence but slowly (it forfeits
  the free hands / spare turn other actions want, and you can't sneak while
  over-encumbered). The recurring question becomes *stride or creep?* — and the
  magnetic boots (§7) are what finally let you move freely **and** silently in the one
  room where a wrong step is fatal. (Exact lethality — which threats react to
  footsteps, and the radii — is a playtest dial.)

The whole game is a dialogue with the tomb's hearing: when to be silent, when to
be loud, and what each costs.

---

## 3. Map

Eight locations (the Exterior + seven tomb areas). Three entrances (the tomb's
three carved mouths). The lower halls
form a diamond; the prize is up top behind a sealed stair, or down a deadly
chimney from the summit.

```
                        [7 SUMMIT] ---- climb ---- (EXTERIOR)
                          |  (ossified corpse, Friend's Fungus, fungal chimney)
                   fungal chimney  (choke unless masked; Glass Centipede ambush)
                          |
                   [6 BURIAL SPHERE]   zero-g; Fungal Horror; An-Rah's skeleton
                          |  (crystal seal — opens when both jars are placed)
                   [5 CANOPIC JARS]    5 plinths; the singing Mantis-head
                        /     \  (stairs down)
              [2 HALL OF     [3 HALL OF
                 MEMORY]       HOUNDS]    Silas / memory crystals  |  hound tank (gel)
                   |   \      /   |
                   |    \    /    |
              [1 HALL OF  X  [4 HALL OF
                 YOUTH]        WARRIORS]   bats  |  guard-mummy cylinders (gear)
                   |               |
            child's mouth     warrior's mouth
                   \             /
                   (EXTERIOR — the phthalo sands)
```

Connections (engine `add_connection`):
- Exterior ↔ 1 (child's mouth), Exterior ↔ 4 (warrior's mouth), Exterior ↔ 7 (`climb`).
- 1 ↔ 2, 1 ↔ 3, 4 ↔ 2, 4 ↔ 3 (the lower diamond).
- 2 → 5 (stairs up), 3 → 5 (stairs up).
- 5 → 6 (central stair, **`Block`ed by the crystal seal** until both jars placed).
- 6 ↔ 7 (the **fungal chimney**; passable only with breathing protection — a
  `Block`/per-turn `Countdown` hazard otherwise).

Nonlinearity (Zork-style): the **front door** is the canopic-jar puzzle (5→6); the
**back door** is the summit chimney (7→6), which skips the puzzle but demands a
respirator and risks the Glass Centipede.

---

## 4. The spine puzzle: the canopic seal

Room 5 has five plinths, one per canopic jar; the central stair up to the Burial
Sphere is sealed by a **crystal seal**.

| Plinth (head) | Organ | State |
|---|---|---|
| Baboon | lungs | present |
| Human | liver | present |
| Mantis | eyes | present but **fungal** — the singing head |
| **Falcon** | **intestines** | **missing** — worn as a hat by the **Spawn of An-Rah's Guts** |
| **Jackal** | **brain** | **missing** — worn as a hat by the **Spawn of An-Rah's Brain** |

The two empty plinths glow crimson. **Placing both missing jars on their correct
plinths opens the crystal seal** (the `Block` clears) and grants the stair to room
6. The jars are carried by the two roaming Spawn — *defeat them, take the jars,
match head→organ.* The present jars + the **memory crystals** (room 2) supply the
matching clue (a Zork "read the lore to solve it" beat). Wrong placement doesn't
open the seal and flares a warning crimson; swap and retry (the puzzle is fair —
deaths live elsewhere).

**The Spawn are Zork's thief**, distributed: roaming, carrying the keys, lured by
the Mantis-song (§2). This is the heart of the game.

---

## 5. Items & Exotica (the item/puzzle graph)

**Light (Zork lamp layer).**
- **Glowstone** — starting gear. Dim, cold light; lets you see. *Holding any lit
  light in the Hall of Youth provokes the bats* (§6) — so light is both necessary
  and dangerous; you learn to `douse`/`drop` it passing through room 1.
- **Ulfire Lantern** (*Exotica*; "ulfire is the ninth colour — shines *through*
  solid objects, revealing what's hidden"). Held by **Silas**. Obtain it by allying
  with him, feeding him **Friend's Fungus**, or defeating him. It is the key that
  reveals the **Manifold Box** compartment and a hidden passage or two — `look
  through <thing> with lantern`.

**The seal puzzle.**
- **Falcon jar**, **Jackal jar** — the keys (worn by the two Spawn).
- **Baboon / Human / Mantis jars** — present; examine for the matching clue. The
  **Mantis jar** is fused to the singing fungal head (don't move it carelessly).

**The boss / fire puzzle.**
- **Flask of embalming gel** — from the **Hall of Hounds** tank (flammable).
  Breaking the tank floods the room and is *loud* (→ encounter); scooping a flask
  is the quieter route.
- **Plasma-igniter** — Autarchy fire-source, looted from a **guard mummy** (room
  4). Gel + igniter = the only way to *set the Fungal Horror ablaze* so it can't
  regenerate. Also burns the **Ossified Corpse** (the cleanse).
- **Respirator / filter-mask** — guard-mummy gear. Protects against burial-cylinder
  spores and lets you survive the **fungal chimney** (otherwise lethal choking).
- **Magnetic boots** (*Vaarn canon gear*) — guard-mummy equipment. The clean key to
  the **zero-gravity** Burial Sphere (§7): `wear boots` and you walk its metal inner
  wall under control and in silence. Without them you improvise with
  push-off / grab / recoil — riskier, and loud mistakes wake the Horror.

**The Exotica (treasure / win condition).**
- **An-Rah's Synth-Hunting Dagger** (*Exotica*; d6; flashes coded **LogLang**).
  Synthetic creatures attack its holder at disadvantage → the canonical anti-synth
  edge against **Silas** and the **guard mummies**. On An-Rah's skeleton (room 6).
- **An-Rah's Manifold Box** (*Exotica*; hypergeometric; a secret compartment 3× the
  box, "inaccessible unless viewed from a very specific angle"). On the skeleton.
  The compartment (revealed by the Ulfire Lantern, or `turn box` / `look through
  box`) holds **An-Rah's ego-core** — his preserved memory, the thing Silas covets
  and the payload of the cleanse ending.
- **Friend's Fungus** (*Exotica*; pink; the eater becomes agreeable & suggestible).
  On the **Ossified Corpse** (summit). Use it *on* Silas or a guard mummy (pacify /
  recruit); eating it yourself is a (deadly-flavored) mistake.
- **Singing Crystal** (*Exotica*) — a memory crystal from room 2; score loot, but
  taking one disturbs Silas's work (→ shifts him toward hostile).

**Collector loot (bonus score).**
- **Cyborg hounds** (×10, Hall of Hounds tank) — "valuable to collectors." Getting
  them means breaking the tank (loud → encounter). Pure high-score risk/reward.
- **Autarchy armour** (Armour 14, 4 slots) + **prismatic blade** (d8) — guard-mummy
  equipment; wearable/wieldable, helps you survive a deadly tomb.

**Stretch / optional master-keys** (the "command the synths" route, §8): a **TITAN
Protocol** or **Autarch's Sigil** to command Silas / the guard mummies or open the
seal — an alternate, non-combat solution true to Vaarn's pre-Collapse security
tropes. Seeded as its **own** find (the Manifold Box compartment is reserved for
An-Rah's ego-core, below).

---

## 6. Threats & NPCs → reaction/trigger wiring

### Combat is puzzle-forward
A Zork/Action-Castle homage, so fighting is thin and tool-gated, not an HP grind —
every threat has a *right answer*, and brute `attack` usually loses (loudly, which
in this tomb means death):
- **Fire is the answer to fungus, and it's scarce.** One flask of embalming gel +
  the plasma-igniter is the *only* thing that kills the regenerating **Fungal
  Horror**, and it can also torch the **Spawn** or the **Ossified Corpse** — but the
  flask holds only a couple of ignitions, so *where you spend fire* is the central
  resource puzzle (Zork's lamp-oil tension).
- **Silas** (synthetic) yields to the **LogLang dagger** (he attacks at
  disadvantage), to **Friend's Fungus** (pacified), or to being left alone — not to
  a brawl (he drains INT).
- **The Spawn** are the one genuine fight — the looted **prismatic blade + Autarchy
  armour**, ideally after luring both together; the Brain-spawn's domination is
  countered by the dagger or Friend's Fungus.
- **Guard mummies, Pthalo-Jackals, the Glass Centipede** are hazards to *avoid*
  (stay quiet, stay masked), not bosses to beat.

A thin HP layer (the engine's `Attack`) backs the few real fights; everything else
is solved by the right item, the right approach, or silence.

Each maps to a primitive from the engine (see `docs/game-development-guide.md`).
Stats from the source are abstracted to the engine's combat model.

| Creature / NPC | Where | Behaviour | Primitive |
|---|---|---|---|
| **Bats** | 1 Hall of Youth | swarm anyone holding a **lit light** *or* making noise; deadly if you linger | custom `Reaction` (Startle on sound **+** a "lit light held here" check) |
| **Silas** (synth archivist) | 2 Hall of Memory | ignores you while draining crystals; warns of the Spawn if talked to with respect; INT-drains if attacked; pacified by Friend's Fungus; at disadvantage vs the dagger | `Character` + `behavior`, `Prompt`-driven talk; fate **emergent** (§8) |
| **Guard mummies** (×4) | 4 Hall of Warriors | dormant in cylinders; opening one releases **choking spores** (deadly CON check) and animates a slow, non-aggressive but armed mummy | on-open `Trigger`/`Reaction`; loot = armour, blade, igniter, mask |
| **Spawn of Guts** (Falcon jar) | roams | Lash / Acid; **homes in on the Mantis-song** | **`DrawnToSound`** (new, §10) |
| **Spawn of Brain** (Jackal jar) | roams | **Psychic Domination** (EGO save or lose control — deadly); homes on song | `DrawnToSound` + a domination `Reaction`/attack; countered by the dagger / Friend's Fungus |
| **Mantis fungal head** | 5 Canopic | *sings* when it senses movement, luring the Spawn | `Reaction` that calls `emit_sound` |
| **Fungal Horror** (boss) | 6 Burial Sphere | "breaks out if it hears movement"; **regenerates 3/round unless set ablaze**; Acid Spray | **`WakesAtNoise`** + a per-round regen `Trigger`; dies only when `ablaze` |
| **Glass Centipede** | 7 chimney | ambush; bite → "Centipede Venom" fills an item slot | on-enter `Trigger` (if not already met) |
| **Pthalo-Jackals** (2d6) | the halls | a pack drawn by **noise** in the lower halls | noise `Reaction`/`Trigger` that spawns the encounter |
| **Ossified Corpse** | 7 Summit | the Mycomorph progenitor; the fungal *root*; scenery until burned | `search` → Friend's Fungus; burning it = the cleanse `Trigger` |

**Key emergent chain (the showcase):** movement in room 5 → Mantis-head sings
(`emit_sound`) → both Spawn `DrawnToSound` converge on room 5 → you fight them
there and claim both jars at once. Pure reactions, no scripting.

---

## 7. The two boss solutions (attack the symptom or the root)

The Fungal Horror is one organism with the summit's Ossified Corpse (canon: the
corpse's fungus "overcame the tomb"). So there are two ways to win the boss:

1. **Burn it in the sphere (direct, deadly).** Bring **gel + igniter**, enter the
   Burial Sphere *quietly* (zero-g movement is noisy — any slip wakes it), douse
   and ignite. Loud or unprepared = the Horror breaks out and kills you. Fast but
   high-risk.
2. **Burn the root (elegant, high-score = the cleanse).** Reach the **Summit**
   (climb the exterior), burn the **Ossified Corpse** with gel + igniter. The whole
   fungal network withers — the Horror collapses *remotely*, the tomb falls silent,
   and An-Rah is at peace. This is the "coronation" denouement and the high-score
   path, and it neutralizes the boss without the sphere gauntlet.

Either way, defeating the Horror lets you loot An-Rah's skeleton (Dagger + Box).

### Zero-gravity navigation (a puzzle in its own right)

The Burial Sphere has no gravity — the Autarch's failing **anti-entropy sphere**
(his coffin). You cannot simply `go`: the aperture (in, from 5) is at the bottom,
the fungal chimney (out, to 7) at the top, and **An-Rah's coffin floats in the dead
centre, off every wall** — and the prize (Dagger, Box, his skeleton) is *on the
coffin*. Crossing the sphere is the puzzle; doing it **silently** is the test
(uncontrolled motion = noise = the Horror, §2).

Two ways across:
- **The clean key — magnetic boots** (guard-mummy gear, §5): `wear boots` and you
  walk the carved inner wall under control and in silence, reaching any
  wall-anchored point (aperture, chimney rim, the prayer-handholds) at will. But the
  coffin is *off* the wall — even booted, reaching it is a committed
  `push off wall toward coffin` then `grab coffin`.
- **The improvised way — momentum** (no boots): move by
  `push off <anchor> toward <target>` then `grab <target>`, hopping between the
  fixed anchors (aperture rim → wall handholds → coffin → chimney rim). Push toward
  open space, the fungus, or a spot with no handhold and you drift — `grab`
  something at once or you **flail (noise → the Horror) or drift into the fungal
  mass**. And **recoil is real**: a forceful act shoves you the opposite way — `throw
  <heavy item>` (a jar, a hound, the gel flask) to propel yourself across a gap,
  though a thrown item is *gone* and may clatter.

Acting in zero-g:
- **Nothing stays put.** `drop` in the sphere and the item drifts off and is lost;
  keep things in hand or tethered. Hands are scarce — lantern *and* gel *and*
  grabbing handholds won't all fit, so freeing your hands (the boots) or sequencing
  carefully matters.
- **Looting the coffin imparts motion** — pry too hard and you recoil into the
  fungus.

How it fuses with the climax (the two boss solutions above):
- **Burn-in-the-sphere:** reach the coffin in *perfect silence*, then commit one
  loud act — `throw gel on horror; ignite` — accepting that it wakes, because it's
  already aflame; the throw's recoil flings you back toward the aperture as it
  catches. A choreographed attack-and-retreat; mistime the silence and it kills you.
- **Cleanse-first:** burn the Ossified Corpse at the summit and the Horror withers,
  so the sphere stops *listening*. The zero-g navigation puzzle remains (you still
  need boots / push-grab to reach the central coffin for the Exotica), but it turns
  *forgiving* — a flubbed move only spins you off, no longer fatal. The elegant path
  makes the hardest room safe.

**Optional lever (stretch):** the zero-g *is* the failing anti-entropy sphere.
`smash` the glass orb and gravity slams back — you walk normally — **but you've
freed the Fungal Horror and the impact is deafening.** A desperate trade: easy
movement for a wide-awake boss. The boots/push-grab puzzle stands without it.

New verbs this introduces: `push off <x> toward <y>`, `grab <x>`, `throw <x>
[at/on <y>]`, `wear boots`, and (stretch) `smash orb`.

---

## 8. Silas — the emergent NPC arc

Silas is the Action-Castle hint-NPC, but his fate follows the player (decision #4):

- **Ally / victim of kindness:** `talk` respectfully → he warns about the Spawn and
  the canopic seal (the central hint). `give friend's fungus to silas` → suggestible,
  he hands over the **Ulfire Lantern** and waves you on. Leave his crystals alone →
  he's peaceful. *Score: peaceful resolution.*
- **Rival:** disturb his work (`take crystal`, loud acts in room 2) → he turns
  hostile (INT-drain, deadly). Beat him with the **Synth-Hunting Dagger** (he's
  synthetic → disadvantage) → loot the lantern. *Score: claim the lantern by force.*
- **Replace him:** with a TITAN Protocol (stretch), `command silas` → he obeys
  (opens things, hands over the lantern, ignores you).

His relationship colors the ending text (a grateful Seeker, a slain rival, a
dominated servant) without changing the win condition.

---

## 9. Deaths (it's deadly)

A non-exhaustive list of prescribed deaths, in the Action Castle tradition:

- **Bats:** lingering in the Hall of Youth with a lit light, or making noise there.
- **Spores:** opening a burial cylinder without a respirator (CON); descending the
  chimney unmasked (d6 choking/round → death).
- **The Horror:** entering the Burial Sphere noisily or without fire — it breaks
  out and acid-sprays you; or fighting it without setting it ablaze (it regenerates
  faster than you can cut).
- **Psychic domination:** failing the EGO save vs the Spawn of An-Rah's Brain.
- **Silas:** attacking him without the dagger (cranial-bore INT-drain).
- **Glass Centipede:** the chimney ambush.
- **Pthalo-Jackals:** raising a racket in the halls while unarmed/unarmoured.
- **Zero-g:** a blind push or a missed `grab` → you flail (noise → the Horror) or
  drift into the fungal mass; recoiling off a forceful act into the Horror; or
  spinning out the aperture (non-fatal — you fall back to room 5 and retry).
- **Friend's Fungus, self-ingested:** you wander, suggestible, into the tomb's jaws.

Deaths are *teaching*: each punishes ignoring the noise/light/breath rules the
tomb keeps stating.

---

## 10. New engine piece: the `DrawnToSound` reaction

The Spawn-lure needs the **inverse of `FleesAtNoise`**: instead of bolting *away*
from a noise, the creature advances *toward* it. This is a clean, reusable addition
to the reaction library (`reactions.py`), a `Startle` sibling:

```python
class DrawnToSound(Startle):
    """The owner moves one hop TOWARD the loudest sound it hears each round, until
    it reaches the source. The moth-to-flame inverse of FleesAtNoise: pursuers,
    lured beasts, anything that homes on noise."""
    REPEATABLE = True   # keep closing the distance round after round

    def apply_effects(self):
        origin = (self.cause or {}).get("origin")
        # audible_rooms(origin, r)[my_room] == the exit in my room toward the source
        reach = self.game.audible_rooms(origin, BIG)
        step = reach.get(self.owner.location.name)
        if step:
            _relocate_and_log(self.game, self.owner, self.owner.location.connections[step])
            self.game.parser.ok(self.narration())
```

`Startle.check_preconditions` already stashes the loudest sound's `origin` on
`self.cause`; `DrawnToSound` walks the `audible_rooms` direction-map one hop toward
it. It's general (pursuit creatures, sirens, lures) and pairs naturally with
`FleesAtNoise` in the library. Build it as part of this game; it earns its place in
the engine.

---

## 11. Score table (max 100)

Zork-style milestone scoring via `game.award(key, points, msg)`:

| Milestone | Points |
|---|---|
| Place the Falcon jar correctly | 5 |
| Place the Jackal jar correctly | 5 |
| Open the crystal seal | 5 |
| Recover the Synth-Hunting Dagger | 10 |
| Recover the Manifold Box | 10 |
| Reveal & loot the Box's compartment (An-Rah's ego-core) | 10 |
| Neutralize the Fungal Horror | 10 |
| **Cleanse the Ossified Corpse (burn the root)** | 15 |
| Recover the cyborg hounds | 5 |
| Recover the Friend's Fungus | 5 |
| Recover a Singing Crystal | 5 |
| Resolve Silas (peace, or claim the lantern by wit/dagger) | 5 |
| **Escape the tomb alive with the Exotica** | 10 |
| **Total** | **100** |

**Win:** escape to the Exterior alive carrying at least the **Dagger + Manifold
Box**. **High score (100):** also cleanse the corpse, recover An-Rah's memory, and
sweep the optional loot.

---

## 12. A winning walkthrough (high-score path)

```
# Exterior — the player starts with a glowstone.
climb                         # -> Summit (the back way, for Friend's Fungus)
search corpse                 # -> Friend's Fungus            (+5)
climb                         # back down to the Exterior
enter child's mouth           # -> Hall of Youth
douse glowstone               # dark, but the bats stay calm; feel your way
go to hall of memory          # -> 2
talk to silas                 # respectful -> he warns of the Spawn (the hint)
give friend's fungus to silas # suggestible -> hands over the Ulfire Lantern (+5)
light lantern; examine crystals  # An-Rah's life: the head->organ matching clue
go to hall of warriors        # -> 4
open a cylinder               # spores (survive the CON hit); a guard mummy stirs
take respirator; take igniter; take prismatic blade; take boots; wear armour
go to hall of hounds          # -> 3
fill flask with gel           # quiet; flammable embalming gel
go to canopic jars            # -> 5 (stairs up)
say "come to me"              # NOISE -> the Mantis-head sings -> both Spawn drawn here
wield dagger; attack spawn of guts; attack spawn of brain   # claim both jars
put falcon jar on falcon plinth   # (+5, scored above)
put jackal jar on jackal plinth   # (+5) -> the crystal seal opens (+5)
wear boots                    # magnetic boots: walk the wall, controlled and silent
go up                         # -> 6 Burial Sphere (zero-g; the Horror is LISTENING)
# Sneak across the wall to the chimney WITHOUT waking the Horror, and kill its root.
climb chimney                 # masked -> 7 Summit (Glass Centipede may ambush)
throw gel on corpse; ignite corpse  # burn the ROOT -> the Horror withers (+10, +15)
climb chimney                 # back down to 6 -- the sphere no longer listens
push off wall toward coffin; grab coffin   # cross the dead centre (now forgiving)
take dagger; take manifold box      # loot An-Rah's skeleton (+10, +10)
look through box with lantern       # reveal the compartment -> An-Rah's ego-core (+10)
push off coffin toward aperture; grab rim
go down                       # -> 5, then out through the halls
# optional sweep on the way out (both are loud/risky):
#   in 2: take singing crystal (+5, but it angers Silas)
#   in 3: break hounds tank -> take cyborg hounds (+5, draws an encounter)
go to hall of youth           # -> 1
exit child's mouth            # -> Exterior, Exotica in hand -> ESCAPE (+10)  WIN
```

(The minimal win skips the summit cleanse and the optional loot: get the jars,
open the seal, burn the Horror *in the sphere* with gel+igniter, loot the Dagger +
Box, and leave — a lower score but a victory.)

---

## 13. Scope: MVP vs stretch

**MVP (the jam target — ≈ Action Castle's footprint):**
- 8 locations (Exterior + 7 areas), the diamond + seal + chimney map.
- The canopic-jar spine puzzle; the **Spawn as `DrawnToSound` thieves** lured by
  the Mantis-song.
- Noise as the core threat: bats, Pthalo-Jackals, the **`WakesAtNoise`** Fungal
  Horror.
- The fire puzzle (gel + igniter) with **both** boss solutions (sphere burn / root
  cleanse).
- **The zero-gravity Burial Sphere puzzle** (§7): magnetic-boots vs.
  push-off/grab/recoil navigation, fused with the noise constraint.
- Silas as the emergent hint/rival NPC; the Ulfire Lantern; the Exotica; the
  Manifold Box angle puzzle; light & breath management.
- Full score table; deadly deaths; scored winning walkthrough as a test.

**Stretch:**
- **Ancestry select** (mycomorph / true-kin / synth / newbeast / cacogen) changing
  puzzle routes (read An-Rah's memory directly; be recognized as "master"; fear the
  dagger).
- The TITAN Protocol / Autarch's Sigil "command the synths" route.
- The **`smash orb`** lever (restore gravity at the cost of freeing the Horror);
  the cyborg-hound collector economy; more memory-crystal lore; Vaarn
  random-encounter flavor tables.

---

## 14. Implementation status (v1 — shipped)

Built and merged across four phases (`adventures/tomb_of_nassak_an_rah.py`,
`tests/test_tomb_of_nassak_an_rah.py`); a full winning run scores **100/100** and
is verified by the suite (`python -m ...tomb_of_nassak_an_rah --win`).

**Done:**
- The 8-room map (the diamond + sealed stair + choked chimney) with Vaarn prose.
- The canopic spine puzzle: sealed-container jars (open to reveal the organ),
  five plinths, the `CrystalSeal` block, head→organ matching.
- Noise as the core mechanic: `sneak` vs striding, deadly rooms (bats, jackals,
  the Fungal Horror), and the **`DrawnToSound`** engine reaction driving the
  mantis-song Spawn lure.
- Silas the hint NPC; the prismatic blade; one-hit-KO Spawn that drop their jars.
- The fire/cleanse boss solution (burn the Ossified Corpse → the Horror dies →
  the Sphere is safe); the zero-g coffin pried only with the magnetic boots; the
  Exotica (Synth-hunting Dagger, Manifold Box); escape-to-win; the 100-pt score.

**Deferred to stretch (per §13), not yet built:**
- Ancestry select; the burn-in-the-sphere boss solution; the **Manifold Box
  angle puzzle → An-Rah's ego-core**; **Friend's Fungus**, the **Ulfire Lantern**,
  and **Silas's emergent fate**; the cyborg-hound / Singing-Crystal collector
  loot; the respirator + chimney back-door; richer push/grab/throw zero-g; and
  the inherently-noisy-*movement* dial (v1 keys threats on loud actions + noisy
  arrivals, with `sneak` as the safe move).

## 15. Resolved decisions

- **Player:** a nameless Vaarn scavenger for v1 (ancestry-select is stretch, §13).
- **Combat:** puzzle-forward with a thin HP layer; fire is a scarce, multi-target
  resource (see "Combat is puzzle-forward", §6).
- **Manifold Box compartment:** holds **An-Rah's ego-core** — the memory Silas covets
  and the cleanse/coronation payload — opened with the Ulfire Lantern. Any master-key
  (TITAN Protocol / Sigil) is a separate stretch find, not the box.
- **"Quiet":** movement is **inherently noisy** (plain `go` carries; `sneak` is the
  silent, slow alternative, §2). Exact lethality — which threats react to footsteps,
  and the radii — is a **playtest dial** we tune once it's playable.

With these locked, the build follows the reactions playbook: scaffold map + items,
then the canopic spine puzzle, then the reactions/threats (incl. `DrawnToSound` and
the zero-g navigation), then scoring + the winning walkthrough as a test — each its
own PR, green before the next.

---

## 16. v2 plan — voice, onboarding, and honest hints (2026-07-02)

Three playtest observations from CCB drive v2:

1. *The text gives away solutions directly rather than telegraphing.*
2. *The opening should onboard a first-time parser player (verb+object, simple
   puzzles first).*
3. *The language isn't evocative of Vaults of Vaarn.*

Style evidence: `docs/design/vaarn-style-guide.md` (zine re-read done; two Leo
Hunt interview transcriptions in progress).

### 16.1 The hint-leak audit (observation 1)

Every place the current text states the answer instead of the situation:

| Where | Current leak | Replace with |
|---|---|---|
| Youth dark blurb | "(EXAMINE or LISTEN overhead, or FEEL your way in the dark.)" | Pure telegraphing (see style guide §5 worked example); probe verbs get taught in the onboarding instead |
| Bats warn line | "…batting at your face — (2/3). Go dark and quiet, NOW." | Escalating *fiction*, no counters: rustle deepens → first bats drop → swarm. The escalation is the clock |
| Jackals warn | "(n/3). Quiet, or get out." | distant yipping answers your noise → yellow eyes ring the doorways → the pack |
| Spores warn | "(n/3). Get out, or mask up." | each breath burns worse; your vision swims — the body says "leave" without the menu |
| Horror warn | "(n/2). Don't disturb it — it's still alive." | the orange mass *tracks* you; the coffin-glass creaks. Alive is shown, not stated |
| PryCoffin fail | "You need purchase. (Magnetic boots?)" | "You flail in the void and drift; nothing holds you down." The boots' own examine text already says *magnetic clamp* — the link is discoverable |
| BurnCorpse fail | "You'd need something that burns and a flame to light it — gel, and an igniter." | "Bare flame won't take on stone; it would want dousing in something that burns." (The tank room's gel "reeks, and it burns" already) |
| Silas | Recites the whole seal solution (take jars → each on its plinth → seal yields) | Silas is oblique and self-interested: points at the *crystal lattice* ("the lattice remembers his embalming, for those who can read it") and warns of the walking Spawn; the head→organ mapping stays in the crystals + openable jars, where it already lives |
| Glowstone examine | "LIGHT it and it glows…; DOUSE it to go dark again." | In-fiction: "wakes at a word and sleeps at another; scavengers carry them dark — light is dear, and attention dearer." The verbs get taught in onboarding |
| Coffin examine | "You'd have to PRY it open." | Keep the verb discoverable but in fiction: "a seam fine as a hair, made to be pried, never opened" |

**Principle:** mechanics never leak ((n/3) counters, verb menus, parenthetical
stage directions). Danger telegraphs through *escalating fiction* — the second
warning is scarier than the first, and that's how you know time is short. Verb
discovery moves to the onboarding + item fiction ("pried", "wakes at a word").

### 16.2 The onboarding opening (observation 2)

New starting room **before** the Tomb Exterior: **The Caravan Wreck** — the
player's trade caravan, jackal-struck in the night; they are the survivor
(canonical: the zine's Trade Caravans table, complication "All Dead"). A safe
sandbox that teaches the verb curriculum diegetically:

| Beat | Verbs taught | Puzzle |
|---|---|---|
| The wreck, described with one glinting detail | `EXAMINE` | examine wreck/camel → reveals the half-buried pack |
| The pack | `OPEN`, `TAKE`, `INVENTORY` | open pack → take glowstone (+ waterskin flavor). The glowstone is *found*, not given |
| The wagon's hold — dim, not deadly (a `Fog`/DIM veil) | `LIGHT`, `DOUSE`, `READ` | too dim to read the merchant's ledger → light glowstone → read ledger → douse. Teaches the toggle in *safety* so the Hall of Youth can subvert it (light = danger) |
| A surviving newbeast draught-mule (talking animal, canon) | `TALK TO` | gives the goal + the *indirect* lore that replaces the leaks: "the mouths are doors… the boy's mouth is lightless, and the dead there sleep shallow… walk it the way the dead walk" |
| The road north | `GO` | go north → Tomb Exterior; the game proper begins |

The ledger + the mule carry the oblique versions of every hint we're deleting
from the interior (dark hall, listening dead, the fungus and fire). ~5 minutes,
zero deaths possible, full verb curriculum: examine/open/take/inventory/light/
douse/read/talk/go — plus modeling `feel`/`listen` in the hold's narration.

### 16.3 The voice pass (observation 3)

After the interview transcripts land and the style guide §6 is filled in:
rewrite **every** location description (lit + dark/dim variants), item
examine text, character text, hazard warn/kill lines, and travel flavor in the
zine register (style guide §§2–5). Rough order: Exterior → Youth → Memory →
Hounds → Warriors → Canopic → Sphere → Summit → Chimney → Wreck (new). Each
rewrite honors §16.1 (no leaks) as it goes.

### 16.4 Sequencing + status

Revised after the style corpus landed: B and C are the *same strings*, so they
merged into one room-by-room rewrite pass.

1. **PR A — onboarding (SHIPPED, #312)**: the Caravan Wreck + the Wagon's Hold,
   glowstone found not given, Worry the new-mule, the ledger as the diegetic
   hint-carrier, give_hints off by default. GO NORTH skips it.
2. **PR B — the rewrite pass (SHIPPED)**: every room/item/character/hazard
   re-voiced in the register (style guide §§2–7) with the §16.1 leaks fixed in
   the same stroke. `_hazard` takes escalating `warns` tuples — the fiction is
   the clock; the numeric counter appends only under `give_hints`. Silas points
   at the lattice instead of reciting the seal solution; PryCoffin/BurnCorpse
   failures describe the problem, not the shopping list.

WIN walkthrough held at 100/100 throughout; smoke tour covers all nine safe
rooms.
