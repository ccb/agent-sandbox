# Thing reactions (a stimulus-triggered, Action-shaped reflex)

**Status:** draft spec, not yet implemented.

## 1. Motivation

Several creatures and objects respond *reflexively* to what happens around them:
the AC2 dragon wakes when you linger, the AC4 doe bolts at a noise, the poacher
looses his arrow if you don't stop him in time, a trap springs when stepped near.
Today these
are **game-level triggers keyed to a location** (`Game.add_disturbance_trigger`),
with the reacting thing hidden inside a closure — pinned to a room name, with the
"who reacts" implicit, and unable to use the cross-room hearing the perception
layer already has (a scream next door is *heard* by the doe but doesn't *spook*
her).

A **reaction owned by the thing** fixes all three: it travels with the thing,
names its owner explicitly, is reusable across creatures, and keys off the
thing's own perception (its room + earshot).

## 2. Sound is a property of the source, not the reactor

The earlier draft made the doe carry a list of "loud" verbs, a closure about the
shack door, and an earshot flag. That's backwards. Commit to a physical model:

* **Actions carry volume.** `Action.AUDIBLE_RADIUS` (default `0` = silent beyond
  its room) says how far the *sound* of an action travels. SAY, BREAK, the bar
  brawl set it > 0; examine / dismount / take stay silent.
* **Ambient noises emit themselves.** A noise that isn't an action — the shack
  door slamming, the goblin baby wailing — is emitted by *that* thing:
  `game.emit_sound(location, radius, description)` logs a sound event with no
  actor. The door owns "I am loud," not the doe.

A "sound" is then just **an event with `heard_radius > 0`**, and `game`'s hearing
helpers (`audible_rooms`, `sounds_audible_at`) already say who can hear it and
from which direction.

## 3. A reaction is an Action, stimulus-triggered

An `Action` is a **command-triggered gated effect**: `check_preconditions()`
gates, `apply_effects()` acts, `__call__` runs gate→effect. A `Reaction` has the
*same shape*, only **stimulus-triggered** — the precondition *is* the trigger,
the effect *is* the response. Two kinds of gated effect, differing only in what
pulls the trigger (a command vs. the world). This collapses trigger / Action /
reaction into one idiom — *gate → effect*; a reaction is its thing-owned,
stimulus-driven member.

```python
class Reaction(GatedEffect):       # sibling of Action, NOT a subclass (see §4)
    def __init__(self, game=None, owner=None):
        self.game = game
        self.owner = owner          # the Thing whose reflex this is (set on attach)
        self.cause = None           # what the precondition detected

    def check_preconditions(self) -> bool:
        """Is there a stimulus this reflex should answer this round? Stash what
        was detected on self.cause (mirrors how an Action stashes
        self.matched_item)."""
        ...

    def apply_effects(self):
        """React, using self.cause."""
        ...
```

`GatedEffect.__call__` — factored out of `Action` — is the one place gate→effect
lives, and the cause is **instance state** (stashed in the precondition, read in
the effect), so nothing is threaded through callables.

### Reactions are subclasses, like Actions
The codebase already authors behaviour as `Action` subclasses (`CutHair`,
`ShootPoacher`) — not callables handed to a factory. Reactions follow suit: a
reaction is a class; you attach an **instance**. There is **no**
`react_to_disturbance`/callable-pair convenience — the reusable library classes
below *are* the convenience.

## 4. Sibling of Action, not a subclass

A `Reaction` is **not** an `Action`: no `ACTION_NAME`/aliases, no command, no
parser matching, and it's **persistent** (instantiated once, re-evaluated each
round) rather than transient. Both extend a tiny shared `GatedEffect` base (the
`__call__` above + `_preconditions_passed`); `Action` adds the parser-facing
bits, `Reaction` adds `owner`/`cause`. No Action machinery leaks in.

## 5. Thing.reactions + attach

`Thing` gains `self.reactions: list[Reaction]` (default empty), inherited by
`Item`, `Character`, and `Location` — so reflexes live on an **Item** (the doe;
a tripwire), a **Character** (the dragon, the poacher), or a **Location** (a
room-wide ward). Reactions are about "execute an effect on a stimulus," which is
broader than agency — hence `Thing`, not `Character`.

```python
game.add_reaction(thing, reaction)   # sets reaction.owner = thing, appends to
                                     # thing.reactions, registers it for the react phase
```

## 6. The built-in reaction library

Two ready shapes cover the existing threats; games subclass `Reaction` for
anything bespoke (just like a custom `Action`).

### Startle — `FleesAtNoise`, `WakesAtNoise`
Reacts to **any sound it perceives**. The precondition is dead simple — "is there
a sound audible at my room this round?" — using `game.sounds_audible_at(
self.owner.location)`. No loud/safe set (the action's `AUDIBLE_RADIUS` already
decides what's a sound), no `extra` closure (the door emits its own sound), no
`earshot` flag (perception already respects each sound's radius — hearing *is*
earshot). Gated only by the creature's own state, usually just *fire once*.

```python
deer.reacts? -> game.add_reaction(deer, FleesAtNoise(to=deep_woods))
# bolts to the Deep Woods at the first noise it hears, once. apply_effects
# relocates the doe and narrates from self.cause: "<the sound>, and the doe bolts
# off into the Deep Woods."
```

`self.cause` carries the sound's description and (for a far sound) its direction,
so the narration reads "The shack door bangs shut behind you, and the doe bolts…"
or "A scream from the south, and the doe bolts…" with no per-doe wiring.

### Countdown — `Countdown`
The poacher/demon aren't sound reactors, and they aren't "react to a wrong move"
either — they're on a **clock**. A stimulus starts the countdown; you have a few
turns to avert it; if the timer elapses, the bad thing happens. `Countdown` fires
**once** on its stimulus, schedules a **cancelable** consequence `DELAY` turns
out, and narrates a warning. Subclass it for the stimulus, the cancel test, and
the consequence.

```python
class PoacherShoots(Countdown):
    DELAY = 2
    def __init__(self, quarry):
        super().__init__(); self.quarry = quarry          # the doe
    def stimulus(self):                                    # the doe is driven into his sights
        return self.game.entered_this_round(self.quarry, self.owner.location)
    def cancelled(self):                                   # SHOOT POACHER set this
        return self.owner.location.get_property("poacher_dealt")
    def warning(self):
        return "The poacher draws his bow on the cornered doe -- you have only moments!"
    def consequence(self, game):
        _die(game, "Too slow -- the poacher looses his arrow and the doe drops. THE END.")
```

The chain is the payoff: a noise fires the doe's `FleesAtNoise`, which relocates
her into the Deep Woods — *that arrival* is the poacher's stimulus, so the
countdown starts the moment she's cornered, whether or not you've followed yet.
Follow fast and `SHOOT POACHER` (which sets `poacher_dealt`, canceling the
scheduled shot); dawdle and the timer fires. Unlike the old "any non-safe action
kills instantly," you may act freely inside the window — you just can't outlast
the clock, and examining no longer stalls forever. `DELAY` tunes the window;
anchoring on the doe's arrival (not yours) means your follow turn eats into it,
so a careful approach has to be a *fast* one.

## 7. Evaluation semantics

* Reactions fire in the **post-round react phase**, after every actor has moved —
  so they see the whole round and are order-independent (multi-agent-safe).
* Each thing's reactions are evaluated by **calling them** (`reaction()` → the
  `GatedEffect` gate→effect), reusing the existing trigger driver: bounded
  cascade, fire-once-per-round, `once` for one-shots, game-over short-circuit.
* **Self-exclusion:** a thing never reacts to its *own* logged sound (the
  precondition skips events whose actor is `self.owner`).

## 8. Self-relative location (the payoff)

Startle preconditions read **`self.owner.location`**, not a frozen room — so the
reaction travels with the thing and supports duplicates, and "what I react to" =
"what I can hear there," near or far, by the same perception machinery. The
"heard but didn't react" seam disappears, and "loud is contextual" stops being a
problem: SAY is physically a sound everywhere; it only matters where something is
*listening for* sound, so talking in a bar (no startle reaction there) is
harmless without any per-scene classification.

## 9. Effects are ordinary code: run Actions, or defer them

`apply_effects` is plain Python, which buys two things for free:

* **Run an Action.** The dragon's reaction executes a `WakeAndChallenge`, which
  logs its own event, is perceived, and can trip further reactions (a bounded
  cascade the trigger driver handles).
* **Defer a consequence.** An effect can call
  `game.schedule_event(turn + n, callback, name=...)` (the engine's existing
  one-shot timer) instead of acting now — the poacher's `Countdown` above. The
  callback fires in the react phase `n` turns later and guards on a flag so a
  player action (`SHOOT POACHER` → `poacher_dealt`) cancels it. "Timed reaction"
  is just this composition — no new machinery — and generalizes to armed traps,
  delayed spells, or an alarm raised a turn after a guard spots you.

Neither is required: the doe is an Item that can't take an action, so its effect
just relocates itself and narrates.

## 10. Relationship to neighbours

| | `behavior` | `Reaction` | game trigger |
|---|---|---|---|
| when | the thing's own turn | post-round, on a stimulus | post-round, on a condition |
| nature | proactive: decide + act | reactive reflex (gate→effect) | place/plot rule |
| owner | a Character | any Thing | the game |
| good for | NPCs with goals/LLM | dragon, doe, poacher, traps | scoring, "on enter", room alarms |

A full NPC can have both a `behavior` and `reactions`. Place/plot triggers stay
game-level (AC4's escape-scored, mark-escaped, drawbridge-sync are room/plot, not
creature reflexes).

## 11. Migration of existing threats

```python
# Doe (Item): one line. The shack door emits its own sound where the player exits.
game.add_reaction(deer, FleesAtNoise(to=deep_woods))
# ... on stepping out of the shack:
game.emit_sound(old_woods, radius=1, description="the shack door bangs shut behind you")

# Bandits / stirges: WakesAtNoise, gated on being asleep / at the ambush spot.
# The baby's wail becomes game.emit_sound(camp, radius=1, "the baby's wailing").

# AC2 dragon (Character): WakesAtNoise, gated on still asleep -- migrated off its
# turn/linger trigger, and now woken by a crash a room away too.
game.add_reaction(dragon, WakesAtNoise())   # apply_effects runs WakeAndChallenge

# Poacher / demon (Character): Countdown, started by the doe's arrival.
game.add_reaction(poacher, PoacherShoots(quarry=deer))   # SHOOT POACHER cancels the timed shot
```

Loud player actions (`SAY`, `BREAK`, the brawl) get an `AUDIBLE_RADIUS > 0`; quiet
ones stay 0, so a careful player can still slip in for the crossbow unheard.

## 12. Decisions to confirm

1. **Reactions on `Thing`** (so the doe-Item and traps qualify). *Recommend yes.*
2. **`Reaction` is Action-shaped** (`check_preconditions`/`apply_effects`/
   `__call__`), a sibling of `Action` via a shared `GatedEffect` base; authored as
   **subclasses** like Actions — **no** callable-pair / `react_to_disturbance`
   convenience. *Recommend yes.*
3. **Sound is a source property:** `Action.AUDIBLE_RADIUS` + `game.emit_sound(...)`
   for ambient noise; startle reactions react to *any* sound perceived (no
   per-scene loud/safe/extra/earshot). The poacher/demon become **`Countdown`**
   reactions — the doe's arrival starts a cancelable timed shot — retiring the
   old non-safe-action `Standoff`. *Recommend yes.*
4. **Reuse the trigger driver** to evaluate reactions in the react phase.
   *Recommend yes.*
5. **Migrate** the four threats (doe, bandits/stirges, dragon, poacher) onto
   reactions; the dragon comes off its turn/linger trigger and gains earshot.

## 13. Non-goals

* Not instantaneous/interrupt reactions mid-action — they fire in the react
  phase, like triggers (simple timing, multi-agent-safe).
* Not a general rules engine — preconditions are plain predicates; the shipped
  library is `FleesAtNoise` / `WakesAtNoise` / `Countdown`, others added as needed.
* No new serialization: reactions hold callables/state, so — like `behavior` —
  they're runtime-only and re-attached by `build_game`, not persisted.
