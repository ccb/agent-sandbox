# Perception: darkness, senses, and narration

**Status:** design spec, not yet implemented.

A reusable, **opt-in** way for what a character perceives of a location — its
description, exits, items, and characters — to depend on perception conditions
(darkness, fog, blindness) and on which **senses** they can bring to bear (sight,
touch, hearing, smell). Designed so that (a) games that don't use it are entirely
unaffected, (b) a future LLM narrator can rewrite descriptions *anchored* in the
perceived facts, and (c) mechanisms beyond light — feeling your way, listening —
can reveal what the dark hid.

Perception is to **describing** what `Block` is to **movement**: a small,
composable, subclassable thing you attach to a location. It plugs into the seam
that already exists — `Game.describe_for(character)`.

---

## 1. Goals

- **Optional & zero-cost.** No veils on a location + a sighted observer ⇒
  `describe_for` produces exactly today's output. No new required API, no added
  concepts for base game creation.
- **Composable & reusable.** Ships with `Darkness` / `Fog` and a `blind` observer
  flag; games subclass for custom senses (an ulfire lantern that sees through
  dark, a glamour only synths pierce). Reusable across every adventure.
- **Multi-sense.** Sight is the default, but touch / hearing / smell can reveal
  elements the dark hides — with sense-appropriate fidelity.
- **Narrator-ready.** Perception yields a *structured* `Scene`; the default
  renderer turns it into standard prose, and a pluggable narrator (an LLM) can
  rewrite from the same `Scene`, anchored in the defaults.

---

## 2. Shape of the design (four layers)

Each layer is independently opt-in; a game uses only as much as it needs.

| Layer | What it adds | A game opts in by… |
|---|---|---|
| **0 — default** | today's behavior, unchanged | doing nothing |
| **1 — veils / sight** | dark & foggy rooms, blindness | `location.obscure(Darkness())`; `char.set_property("blind", True)` |
| **2 — senses / probes** | feel / listen / smell reveal what sight can't | tagging elements `perceptible_by` + registering the probe verbs |
| **3 — narrator** | LLM rewrites the description | installing a narrator plugin |

---

## 3. Layer 1 — Sight and Veils (the common case)

A small ordered level:

```python
class Sight(IntEnum):
    NONE  = 0   # can't see -- render only the "can't see" line
    DIM   = 1   # partial -- the room's gist + exits; not items/characters
    CLEAR = 2   # full
```

A **`Veil`** is a location-attached, observer-aware perception condition
(`Block`'s sibling). It answers "how well can this observer *see* here?":

```python
class Veil:
    def sight(self, observer, location) -> Sight: return Sight.CLEAR
    def blurb(self, location) -> str: return ""          # "It's pitch dark."

class Darkness(Veil):                                    # reads IS_DARK + a lit light
    def sight(self, observer, location):
        return Sight.CLEAR if _carries_light(observer) else Sight.NONE
    def blurb(self, location): return "It's pitch dark -- you can see nothing."

class Fog(Veil):
    def sight(self, observer, location): return Sight.DIM
    def blurb(self, location): return "Fog swallows everything a few feet off."
```

Blindness is an **observer** condition, folded into the resolver (most-restrictive
wins, so darkness + fog + a blind observer all compose):

```python
def sight_for(observer, location) -> tuple[Sight, str]:
    if observer.get_property("blind"):
        return Sight.NONE, "You see nothing -- you're blind."
    level, blurb = Sight.CLEAR, ""
    for veil in getattr(location, "veils", ()):          # empty by default -> CLEAR
        s = veil.sight(observer, location)
        if s < level:
            level, blurb = s, veil.blurb(location)
    return level, blurb
```

**The level → facet policy** (the whole sight rule, in one table):

| Sight | description | exits | items ("You see") | characters |
|---|---|---|---|---|
| CLEAR | full | ✓ | ✓ | ✓ |
| DIM | `dim_description` or full | ✓ | — | — |
| NONE | just the blurb | — | — | — |

**Zero-cost guarantee:** with no veils and a non-blind observer, `sight_for`
returns `CLEAR` immediately and every facet renders as today.

### Movement vs. sight are separate
The existing **`Darkness` block** gates *movement* (per exit); a **`Darkness`
veil** gates *sight* (the whole room). They read the same `IS_DARK` + lit-light,
but stay separable so a game can pick:
- *dark = can't see AND can't move* (attach both — the Tomb's Hall of Youth), or
- *dark = can't see but can stumble* (veil only), or
- *dark = can't move but you're told so* (block only, today's behavior).

A convenience `location.darken()` can wire the veil + block on all exits for the
common "pitch-black room" case.

---

## 4. Layer 2 — Senses and probing (revealing what the dark hid)

Sight is one sense. Perception generalizes to:

```python
class Sense(StrEnum):
    SIGHT = "sight"; TOUCH = "touch"; HEARING = "hearing"; SMELL = "smell"
```

**Every element declares which senses reach it**, defaulting to sight so nothing
changes until a game opts in:

- **Exits:** `{SIGHT, TOUCH}` by default — you can feel your way to a doorway.
- **Items / characters:** `{SIGHT}` by default; a game tags extras via a
  `perceptible_by` property (`{SIGHT, TOUCH}` for a big statue, `{SIGHT, SMELL}`
  for a corpse). A character *making a sound this round* is auto-`HEARING`-perceptible
  (reusing `sounds_audible_at` / the reactions sound layer).
- **Descriptions have per-sense variants + fidelity.** Sight → the full
  `description` / `examine_text`; touch → a `touch_text` ("a cold stone figure,
  taller than you"); hearing → the `sound_description`; smell → a `smell_text`.
  Unset variants fall back to a terse generic ("you feel bare, cold stone").

**Passive vs. active senses:**
- **Passive** (sight, hearing, smell) fold into a plain `look`/`describe_for`
  automatically: in a dark room you still *hear* the dragon breathing and *smell*
  the rot, so the Scene at `Sight.NONE` still carries `heard`/`smelled` facts.
- **Active** (touch) is a probe: **`feel` / `grope` / `feel around`** exercises
  `TOUCH`, revealing the room's tactile shape, its exits, and any `TOUCH`-tagged
  fixtures — the canonical "feel your way in the dark." Sibling probes **`listen`**
  and **`smell`** exercise those senses on demand.

```python
# a dark room; the player has no light:
> look        It's pitch dark. Close by, something breathes, slow and heavy.   # sight NONE + passive hearing
> feel        You grope along cold walls: an opening north, another west, and a
              squat stone plinth under your hands.                             # touch reveals exits + a tactile fixture
> listen      The breathing is north of you, and vast.
```

**The reveal hook, generalized:** an element hidden from sight is revealed by any
sense that reaches it, exercised by the matching probe. Games add senses to
elements; players (and agents) probe. Custom senses are just `Veil`/sense
subclasses (ulfire-sight grants `SIGHT` through `Darkness`; a synth's sensor-suite
grants `SIGHT` in fog).

Perception composes with the existing **`is_hidden`** item flag: `is_hidden`
means "concealed until revealed" (a secret compartment); perception means "your
senses can't reach it right now." An element shows only if it is *both* not
`is_hidden` *and* reachable by a working sense.

---

## 5. Layer 3 — The `Scene` and a pluggable narrator

`describe_for` is split into **perceive** (facts) and **render** (prose):

```python
def describe_for(self, character):
    scene = self.perceive(character)          # structured perception snapshot
    return self.narrator.render(scene)        # default renderer, or an LLM narrator
```

The **`Scene`** is the stable contract — the anchor a narrator may not contradict:

```python
@dataclass
class Scene:
    location: str
    sight: Sight
    description: str                 # the perceived room text (full / dim / dark blurb)
    exits: list[Exit]                # (direction, dest-or-hint), those perceived
    items: list[Perceived]           # name + the sense-appropriate text + which sense
    characters: list[Perceived]
    heard: list[str]                 # passive non-sight facts (breathing, voices)
    smelled: list[str]
    obscured: list[str]              # KNOWN-unknowns ("something rustles overhead")
```

- **Default narrator:** assembles the standard prose (description, `Exits:`,
  `You see:`, `Characters:`) — byte-identical to today at `CLEAR`.
- **LLM narrator (future plugin):** receives the `Scene` (and the default prose as
  a floor) and rewrites atmospheric prose *anchored* in it — it may reword and
  enrich, but every exit/item/character it mentions must come from the `Scene`,
  and anything in `obscured` is a hint, not a fact. `obscured` gives the narrator
  (and the player) evocative "you sense something you can't quite make out" without
  leaking the hidden specifics.

This is the payoff of computing facts before prose: the same `Scene` drives the
deterministic renderer *and* the LLM narrator, so the two never disagree about
what's actually in the room.

---

## 6. Integration with what exists

- **`describe_for(character)`** already renders per-observer; perception slots in
  there, and `describe()` routes through `describe_for(self.player)`. Agents and
  NPCs perceive correctly for free.
- **Agent perception** (`perceivable_locations`, `audience_for`, memory) is the
  *cross-room* seam (what you perceive of *other* rooms); this is the *current-room*
  seam. Same philosophy; the `HEARING` sense here reuses `sounds_audible_at`.
- **`Darkness` block** (movement) and **`is_hidden`** (concealment) compose as in
  §3–§4 rather than being replaced.

---

## 7. Dev-facing API — minimal to rich

```python
# base game: nothing changes.

# a dark room (sight only):
crypt.obscure(Darkness())

# a dark room you also can't move through without light (block + veil):
crypt.darken()                       # convenience: veil + Darkness block on all exits

# fog:
marsh.obscure(Fog()); marsh.dim_description = "Grey shapes loom in the murk."

# a blinded hero:
hero.set_property("blind", True)

# let players feel/listen their way (opt-in verbs + a tactile fixture):
game.enable_senses()                 # registers feel / listen / smell
plinth.set_property("perceptible_by", {Sense.SIGHT, Sense.TOUCH})
plinth.touch_text = "a squat stone plinth, its top worn smooth"

# a custom sense (ulfire lantern sees through the dark):
class UlfireSight(Veil):
    def sight(self, observer, loc):
        return Sight.CLEAR if _holds_lit(observer, "ulfire lantern") else Sight.NONE
```

---

## 8. Migration / first users

- **Tomb of Nassak An-Rah — Hall of Youth.** Replace the game-level darkness hack
  with `youth.obscure(Darkness())` (dark description + suppressed "You see" for
  free) + the `Darkness` block on `north`/`west` (already there) for the
  travel-gating; lighting the glowstone lifts both and trips the bats. Optionally
  tag the statues/ceiling `TOUCH`/`HEARING` so `feel`/`listen` reveal the rustling
  bats as a clue in the dark.
- **AC1 / AC3 dark rooms** currently only block movement; adding `obscure(Darkness())`
  gives them correct "can't see" rendering. (Verify their walkthroughs — this is a
  behavior improvement, so a test update may be warranted, but confirm no
  regression.)

---

## 9. Decisions to confirm

1. **Naming:** `Veil` for the sight-obscurer (vs `Obscurer` / `Occlusion`)?
   `Scene` for the snapshot? `perceptible_by` for the sense tag?
2. **DIM facet policy:** ship "description + exits only" (table §3), with a `Veil`
   able to override the facet rules for finer control?
3. **Probe verbs opt-in vs always-on:** register `feel`/`listen`/`smell` only when
   `enable_senses()` is called (keeps base HELP clean) — or always available and
   degrade gracefully ("you feel only bare stone")? *Lean: opt-in.*
4. **In the dark, are exits passive or feel-only?** Spec has them **feel-only**
   (a plain `look` in the dark shows nothing but passive sound/smell; `feel`
   reveals exits). Confirm that's the intended texture.

---

## 10. Non-goals

- Not a lighting-simulation (light levels, line-of-sight geometry) — a small
  discrete `Sight` level, not lumens.
- Not multi-sense for *movement* (that stays `Block`) — perception is about
  *describing*.
- The LLM narrator itself is out of scope here; this spec only guarantees the
  `Scene` is a clean, sufficient anchor for one.

---

## 11. Build order (when approved)

1. **Layer 1** — `Sight`, `Veil`, `Darkness`/`Fog`, `blind`, the `sight_for`
   resolver, and the `perceive` → `Scene` → default-render split in `describe_for`
   (proving zero-cost against the full existing suite). Migrate the Hall of Youth.
2. **Layer 2** — `Sense`, `perceptible_by`, per-sense texts, passive hearing/smell
   in the `Scene`, and the `feel`/`listen`/`smell` probe verbs (opt-in).
3. **Layer 3 hook** — finalize the `Scene` dataclass + a `Narrator` interface with
   the default renderer, leaving the LLM narrator as a documented plugin point.

Each its own PR, green before the next — the reactions playbook.
