# Tingen — Day-to-Day NPC Roster

Living townsfolk for Tingen City: ordinary people the player can interact with,
each with a **day identity**, a **schedule**, and a **goal/intention** that gives
them agency. A subset are secretly Beyonders or heretic cultists with a normal
public face and a **reveal trigger** — they are exposed in combat, or choose to
unmask when the world is corrupt enough.

Grounded in *Lord of the Mysteries* canon (see Sources): in the Fifth Epoch the
supernatural is hidden from the masses — most people live and die without meeting
a Beyonder. The **Nighthawks** (mostly Darkness-pathway) police Tingen and are
forbidden to reveal themselves to ordinary folk. Heretic organizations hide among
the citizenry; the two relevant in the Tingen era are the **Demoness Sect**
(worship the Primordial Demoness) and the **Aurora Order** (worship the True
Creator, treated publicly as a terrorist group).

Feeds the planned **NPC schedule system** (GDD §15 / gap-analysis M2) and the
**WorldState** pressure vars — a cultist reveal should bump `cult_readiness` /
`attention` / `panic`. Sprite column maps to the existing
[`asset-gen/out_image2/characters`](asset-gen/out_image2/characters) archetypes;
"combat form" maps to [`enemies`](asset-gen/out_image2/enemies).

Day phases referenced: `early-morning, morning, afternoon, dusk, night,
late-night` (TODO.md / GDD §14).

---

## How the hidden-cultist layer works

Each NPC has two layers:

- **Public layer** — `day_identity`, `schedule`, `public_goal`. This is all the
  player sees at first. Ordinary NPCs only ever have this layer.
- **Secret layer** (cultists/Beyonders only) — `faction`, `secret_goal`,
  `reveal_trigger`, `combat_form`. Hidden until triggered.

**Reveal triggers** (any one fires the unmask):
1. **Caught in the act** — the player gathers enough clues / interrupts a ritual,
   and confronts them with evidence (a dialogue check against collected clues).
2. **Combat exposure** — when forced into a fight, the day face drops and the
   `combat_form` sprite swaps in.
3. **World pressure** — once `cult_readiness` (or stage ≥ `ritual_night`) crosses
   a threshold, sleeper cultists self-reveal across the city in a coordinated beat.

A revealed cultist permanently flips to their secret layer (schedule changes:
they stop showing up at the bakery and start haunting the cemetery).

---

## Ordinary townsfolk (public layer only)

| Name | Day identity | District / schedule hub | Goal / intention | Sprite |
|---|---|---|---|---|
| **Old Neille** | Newspaper hawker & pamphleteer | Cathedral plaza (morning), taverns (night) | Land the scoop on the harbor "disappearances"; trades rumor for coin — a walking rumor-propagation node | `informant` |
| **Maribel Hatch** | Keeper of the *Laughing Eel* tavern | Iron Cross Street (afternoon→late-night) | Pay off a loan shark before he sends men round; knows everyone's business | `npc_civilian_woman` |
| **Constable Brom Aldery** | Beat constable | North Borough lanes (patrol all phases) | Make sergeant; resents the "private investigators" (Nighthawks) who outrank his reach | `npc_constable` |
| **Wm. Tasker** | Dockside stevedore foreman | Harbor warehouses (early-morning→dusk) | Skim a crate or two off the manifests; will talk for drink money | `npc_dockworker` |
| **Goodwife Perrin** | Laundress & char-woman | Residential lanes (morning), homes (afternoon) | Marry her daughter up a class; gossips while she works | `npc_civilian_woman` |
| **Ledger Finch** | University records clerk | University quad / archive (morning→dusk) | Avoid blame for a missing restricted volume (the one a cultist stole) | `npc_investigator` |
| **"Pip"** | Street urchin, runner & lookout | Iron Cross Street, alleys (all phases) | Eat today; will run messages or tail a mark for a copper | `npc_street_urchin` |
| **Hollis Vane** | Out-of-work poet, habitual drunk | Tavern, embankment (dusk→late-night) | Drown a grief; occasionally blurts a true thing he overheard | `npc_drunkard` |
| **Sister Auber** | Cathedral lay-sister | Saint Selena's (early-morning, dusk services) | Shelter the destitute; quietly doubts the recent "miracles" at the church | `witness_widow` |

These nine are the ambient pulse of the town — schedules, gossip, and small
favors. None are occult. Several are **information vectors** (Neille, Maribel,
Pip, Hollis) the rumor system and dialogue topics can hang off.

---

## Hidden Beyonders & cultists (secret layer)

> Each looks ordinary until a reveal trigger fires. `combat_form` is the sprite
> shown once unmasked.

### 1. Dr. Aldous Crane — respected physician → **Aurora Order** initiate
- **Day identity / schedule:** a kindly North-Borough doctor; surgery in the
  morning, house-calls in the afternoon.
- **Public goal:** be the city's most trusted physician.
- **Secret goal:** harvest Beyonder ingredients (organs, blood) from the dying
  for the Order's potions; he signs off "natural deaths" that aren't.
- **Reveal trigger:** the player links three bodies to his patient ledger
  (clue check), **or** he is cornered defending his cellar lab.
- **Combat form:** `cultist_robed` (sheds the frock coat for ritual robes).

### 2. Eulalia Vire — genteel widow & society hostess → **Demoness Sect** deaconess
- **Day identity / schedule:** a charming upper-class widow hosting salons;
  cathedral plaza and parlors by day.
- **Public goal:** marry into the Moretti-class gentry and climb.
- **Secret goal:** recruit grieving women into the Sect with promises of
  reunion-beyond-death; she runs the local cell.
- **Reveal trigger:** world pressure (`cult_readiness` high) — she unmasks at a
  séance the player attends, **or** combat at the ritual site.
- **Combat form:** `wraith_shadow` (channels a borrowed Demoness blessing).
- Maps to the existing `lady_genteel` day sprite.

### 3. Bram Kell — affable butcher → **Demoness Sect** enforcer
- **Day identity / schedule:** the cheerful Iron Cross Street butcher everyone
  likes; shop open early-morning→afternoon.
- **Public goal:** keep his shop and his sick wife fed.
- **Secret goal:** dispose of the Sect's "leavings"; he is the muscle and the
  body-man. Coerced as much as faithful.
- **Reveal trigger:** combat exposure — caught moving a corpse at night.
- **Combat form:** `bieber_monster` (a partial ritual-warp under stress).

### 4. Brother Cassian — cathedral curate → **sleeper / false priest**
- **Day identity / schedule:** the earnest young curate at Saint Selena's;
  services and confession by day.
- **Public goal:** restore faith in a doubting parish.
- **Secret goal:** he is the one staging the "miracles" — softening the city for
  the ritual night; reports to Eulalia's cell.
- **Reveal trigger:** the highest-tier reveal — only at stage `ritual_night`, or
  when the player presents the stolen university volume (Ledger Finch's missing
  book) as proof.
- **Combat form:** `descent_horror` (a botched partial-Descent — the setpiece).
- Maps to the existing `priest` day sprite.

### 5. Naya Brookes — fortune-teller on Iron Cross Street → **rogue Beyonder (not a cultist)**
- **Day identity / schedule:** a small-time card-reader and "spirit medium";
  stall by day, back-room readings at night.
- **Public goal:** make rent; her readings are *mostly* cold-reading — except she
  is a genuine low-Sequence Seer and some come true.
- **Secret goal:** none sinister — she is hiding from the Nighthawks, afraid of
  being mistaken for a heretic. A potential **ally/informant** if befriended,
  a tragic false-lead if hunted.
- **Reveal trigger:** befriend (clue/topic check) → she reveals her sight and
  becomes a divination resource; threaten her → she flees the district.
- **Combat form:** none (non-combatant); flees.

---

## Design hooks (so this stays implementable)

- **Schedules first, secrets later.** Ship all NPCs as public-layer
  schedule-walkers (M2). The secret layer is data on the same record — a later
  pass wires reveal triggers to clues / `cult_readiness` / stage.
- **Information economy.** Neille / Maribel / Pip / Hollis / Naya are the rumor
  and topic sources; the cult cell (Crane → Eulalia → Cassian, with Bram as
  muscle) is a **clue chain** the player reconstructs on the Investigation Board.
- **One cell, layered reveals.** The four cultists form a single Demoness/Aurora
  cell with escalating reveal tiers (butcher → physician → deaconess → curate),
  so unmasking one points at the next — a built-in mystery spine for the Tingen
  arc culminating at `ritual_night`.
- **Sprites already exist** for every day identity and every combat form, so no
  new art is blocked on this — but a hidden cultist ideally gets BOTH a day sheet
  and a combat sheet in the animation pass.

---

## Sources

- [Nighthawks — LotM Wiki](https://lordofthemysteries.fandom.com/wiki/Nighthawks)
- [Tingen City — LotM Wiki](https://lordofthemysteries.fandom.com/wiki/Tingen_City)
- [List of Secret Organizations — LotM Wiki](https://lordofthemysteries.fandom.com/wiki/List_of_Secret_Organizations)
- [Aurora Order — LotM Wiki](https://lordofthemysteries.fandom.com/wiki/Aurora_Order)
- [Demoness Sect — LotM Wiki](https://lordofthemysteries.fandom.com/wiki/Demoness_Sect)
