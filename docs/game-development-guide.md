# Game development guide

A newcomer's tour of the `text_adventure_games` engine: the classes you build a
world from, the primitives that make it tick, and — most importantly — *which
primitive to reach for when*. Read this once and the existing games
(`text_adventure_games/adventures/`) will read like prose.

For deeper dives, see `docs/design/custom-world-authoring.md`, the reactions spec
(`docs/design/reactions.md`), and the runnable demo
`text_adventure_games/adventures/reactions_demo.py`.

---

## 1. The one-paragraph mental model

A **`Game`** holds a graph of **`Location`**s connected by directions. In each
location sit **`Item`**s and **`Character`**s (the player is a Character). The
player types commands; the **`Parser`** turns each into an **`Action`** — a
*gated effect* that checks its preconditions and, if they pass, changes the
world. After every turn the engine runs a **react phase**: it fires **`Trigger`**s
(world/plot rules) and **`Reaction`**s (thing-owned reflexes) whose conditions are
now true. **`Block`**s gate movement between rooms; **`Prompt`**s let the game ask
the player a question; the **event log** records what happened so perception and
reactions can read it.

Everything else is a convenience layered on those pieces.

---

## 2. The world: `Thing` and its three subclasses

`Thing` is the shared base (`things/base.py`). Every Thing has a `name`,
`description`, a `properties` dict (defaults to `False` for unset keys),
`aliases` the parser also matches, and a `reactions` list (see §6). Properties
use either a `Property` enum member or a plain string — they're interchangeable:

```python
from text_adventure_games.enums import Property
item.set_property(Property.GETTABLE, False)   # well-known key
item.set_property("rope_tied", True)          # ad-hoc key, no coordination needed
item.get_property("rope_tied")                # -> True (unset keys read False)
```

### `Location`
A room. You wire the map with `add_connection`, which auto-wires the reverse for
cardinal directions (and `in/out`, `up/down`):

```python
from text_adventure_games import things
hall = things.Location("Hall", "A dusty hall.")
cellar = things.Location("Cellar", "A damp cellar.")
hall.add_connection("down", cellar)            # cellar --up--> hall, automatically
hall.add_item(torch)                           # also sets torch.location = hall
hall.add_character(ghost)                       # also sets ghost.location = hall
hall.add_block("down", LockedHatch(hall))      # gate the exit (see §8)
hall.move_verbs["down"] = "climbs"             # "X climbs to Cellar" instead of "moved"
hall.travel_descriptions["down"] = "The stairs creak."
```

### `Item`
`things.Item(name, description, examine_text="")`. Gettable by default; turn that
off for scenery. Items can be containers or stackable:

```python
gem = things.Item("gem", "a glittering gem", "A fat gemstone.")        # gettable
altar = things.Item("altar", "a stone altar", "Carved with runes.")
altar.set_property(Property.GETTABLE, False)                            # scenery
chest = things.Item("chest", "a chest").make_container(capacity=5)      # holds items
coins = things.Item("coins", "silver coins").make_stackable(3)          # a stack of 3
gem.add_alias("gemstone")                                               # parser also matches "gemstone"
```

### `Character`
`things.Character(name, description, persona, goals=None)`. The player is just a
Character. Characters carry an `inventory`, can wear/wield items, and have a few
runtime-only fields (not serialized): `behavior` (how an NPC acts on its turn),
`following`, `riding`, and `last_action`.

```python
player = things.Character("you", "an adventurer", "I explore.")
ghost  = things.Character("ghost", "a pale ghost", "I haunt this hall.")
ghost.set_behavior(lambda c, g: g.parser.parse_command("say boo", actor=c))  # acts each turn
```

---

## 3. Building and running a game

The convention is a `build_game()` that assembles the world and returns a `Game`,
plus a `__main__` that either plays interactively or runs a scripted walkthrough:

```python
from text_adventure_games import games, things

def build_game():
    start = things.Location("Ledge", "A windy ledge.")
    # ... build the map, items, characters ...
    player = things.Character("you", "an adventurer", "I explore.")
    game = games.Game(start, player,
                      characters=[ghost],          # NPCs (the player is added for you)
                      custom_actions=[RingGong])    # your custom verbs (§4)
    # ... add_trigger / add_reaction wiring (§5, §6) ...
    return game

if __name__ == "__main__":
    import sys
    if "--walk" in sys.argv:
        # drive a fixed command list for a smoke test
        g = build_game()
        for cmd in ["look", "go down", "take gem"]:
            g.do_command(cmd)
    else:
        build_game().game_loop()
```

The player is placed at `start_at` automatically. Built-in verbs (look, go, take,
drop, examine, say, attack, …) are registered for you; your own verbs go in
`custom_actions`. `Game` also takes optional `time_config`, `turn_mode`
(`"sequential"` default or `"simultaneous"`), and `config` — see
`docs/configuration.md` and `docs/design/simulation-config.md`.

---

## 4. Verbs: `Action` (the gate→effect contract)

An `Action` is a **command-triggered gated effect**. It extends `GatedEffect`
(`reactions.py`), whose `__call__` runs the contract: `check_preconditions()`
gates, and only if it passes does `apply_effects()` change the world. You author
a verb by subclassing and filling in those two methods:

```python
from text_adventure_games import actions

class RingGong(actions.Action):
    ACTION_NAME = "ring gong"                       # the command keyword
    ACTION_DESCRIPTION = "Strike the bronze gong"   # shown in HELP
    ACTION_ALIASES = ["strike gong", "bang gong"]
    AUDIBLE_RADIUS = 2                              # how far its SOUND carries (§6)

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        if "gong" not in self.game.player.location.items:
            self.parser.fail("There's no gong here.")   # narrate why it failed
            return False
        return True

    def apply_effects(self):
        self.parser.ok("A deep CLANG rolls out.")        # narrate success
        self.game.emit_sound(self.game.player.location, 2, "the clang of a gong")
```

Useful bits on `Action`:
- **Narration:** `self.parser.ok(text)` for success, `self.parser.fail(text)` for a
  rejected command. A command "succeeds" (and the turn advances) only if
  `check_preconditions` returns `True`.
- **Precondition helpers** (each narrates a default failure): `self.at(thing, loc)`,
  `self.is_in_inventory(char, item)`, `self.loc_has_item(loc, item)`,
  `self.has_property(thing, key)`, `self.property_equals(...)`, `self.was_matched(thing, msg)`,
  `self.has_connection(...)`, `self.is_blocked(...)`.
- **Resolving who/what:** `self.acting_character(command)` (who's acting),
  `self.target_character(command)` (who it's aimed at), `self.character_in_room(...)`.
- **Metadata:** `ACTION_ALIASES`, `PLAYER_VISIBLE=False` (hide an NPC-only verb from
  HELP), `DURATION` (in-game minutes, for the NPC budget), `AUDIBLE_RADIUS` /
  `sound_description()` (its physical volume — see §6).

For a simple "use X on Y" interaction you usually don't need a full class — the
`use_item_on` factory builds one:

```python
ThrowJavelin = actions.use_item_on(
    "throw javelin", item="bronze javelin", target="demon",
    verb="throw", preposition="at", consume=True,
    success="The javelin pierces the demon — it's gone!",
    effect=lambda action: action.character.set_property("banished_demon", True),
    award=("banish_demon", 5),
)
```

---

## 5. The react phase: `Trigger` (world & plot rules)

After every successful turn (player, then NPCs), the engine runs `_run_triggers`:
each `Trigger` whose `condition(game)` is true runs its `action(game)`. Triggers
re-evaluate in a bounded cascade (a trigger can enable another), fire at most once
per round, and `repeatable=False` ones fire at most once ever.

A `Trigger` is a lightweight `(condition, action)` pair — perfect for one-off
plot/place rules: scoring, "on entering room X", keeping a room description in
sync, endgame checks.

```python
# Score the first time the player reaches the throne; bar a door until a flag flips.
game.add_trigger(
    "reach_throne",
    lambda g: g.player.location.name == "Throne Room",
    lambda g: g.award("throne", 10, "The court gasps as you enter."),
    repeatable=False,
)
```

Composable condition factories live in `text_adventure_games.triggers`:
`at_turn(n)`, `every(n)`, `in_location(char, loc)`, `has_property(thing, key)`,
`all_of(...)`, `any_of(...)`, and `from_command("...")` as a ready-made action.

**Timed events** are just a one-shot trigger — use the sugar:

```python
game.schedule_event(game.turn + 3, lambda g: g.end_in_death("The bomb goes off."))
```

---

## 6. Reflexes: `Reaction` (thing-owned, stimulus-triggered)

A `Reaction` is the **world-pulled sibling of `Action`**: the same `GatedEffect`
contract (`check_preconditions` → `apply_effects`), but owned by a Thing and fired
by something happening in the world rather than by a command. Attach one with
`game.add_reaction(thing, reaction)`, which sets the reaction's `owner`/`game` and
registers it to run in the react phase. Reactions are runtime-only (like
`behavior`) — re-attach them in `build_game`, they aren't serialized.

Because a Reaction reads `self.owner`, it travels with the thing and is reusable.
Three ready-made shapes cover most threats (`reactions.py`):

```python
from text_adventure_games import reactions

# Startle: bolt to another room at ANY noise it hears.
game.add_reaction(deer, reactions.FleesAtNoise(to=deep_woods))

# Startle: a sleeper roused by noise (override wake() for a custom awakening).
class OgreWakes(reactions.WakesAtNoise):          # gates on the owner's "asleep" flag
    def wake(self):
        self.game.parser.ok("The ogre lurches upright with a ROAR.")
game.add_reaction(ogre, OgreWakes())

# Countdown: a stimulus starts a clock; a consequence lands DELAY turns later
# unless cancelled. The poacher/demon/dragon clocks all use this.
class FuseBurns(reactions.Countdown):
    DELAY = 3
    def stimulus(self):    return self.game.entered_this_round(self.game.player, self.owner.location)
    def warning(self):     return "A fuse hisses to life — CUT FUSE, fast!"
    def cancelled(self):   return self.owner.location.get_property("fuse_cut")
    def consequence(self, g): g.end_in_death("The ceiling comes down. THE END.")
game.add_reaction(fuse, FuseBurns())
```

### Sound is the source's property
Startle reactions just *hear*; what counts as a sound is the **source's** business:
- An `Action` declares `AUDIBLE_RADIUS` (>0) and a `sound_description()` — `say`
  carries one room, `break` two.
- A noise no command produced (a slamming door, a wailing baby) is emitted by the
  source: `game.emit_sound(location, radius, description)`.

Reactions read these via `game.sounds_audible_at(location, exclude=...)` (the
startle stimulus) and `game.entered_this_round(thing, location)` (the countdown
stimulus). A loud event is heard in its origin room and `radius` hops out — the
same hearing the perception layer uses.

The runnable `reactions_demo.py` shows all three reactions plus `emit_sound` firing
across rooms; read it alongside this section.

---

## 7. Which primitive do I reach for?

Everything that "fires when a condition holds" runs through the trigger driver, but
you author it in the shape that fits. The deciding question is **whose behaviour is
this?**

| You want… | Use | Why |
|---|---|---|
| A verb the player/NPC types | **`Action`** | command-pulled gate→effect; the parser dispatches it |
| A reflex owned by a creature/object | **`Reaction`** | self-relative, reusable, Action-shaped; travels with the thing |
| A plot/place/score rule (ownerless) | **`Trigger`** | lightweight `(condition, action)`; the world's state machine |
| Something to happen N turns later | **`schedule_event`** | a one-shot timed trigger |
| To stop movement in a direction | **`Block`** | spatial gate, evaluated by `go` (§8) |
| An NPC that pursues goals each turn | **`behavior`** (§9) | proactive, on the NPC's own turn |

Rules of thumb:
- If the answer to "whose behaviour?" is a *specific thing* → `Reaction`. If it's
  "the plot / the place / the score" → `Trigger`.
- `Action` and `Reaction` are both `GatedEffect`s, so a reaction reads exactly like
  a verb the world types. `Trigger` is the lightweight primitive they (and the
  sugar) all bottom out into — see `docs/design/reactions.md` for the full
  rationale.

---

## 8. Blocks (movement gates)

A `Block` prevents travel in a direction until some condition clears. Subclass it,
implement `is_blocked()`, and attach it to a location's exit:

```python
from text_adventure_games import blocks

class LockedHatch(blocks.Block):
    def __init__(self, hall):
        super().__init__("A locked hatch", "The hatch is bolted from below.")
        self.hall = hall
    def is_blocked(self) -> bool:
        return not self.hall.get_property("hatch_open")

hall.add_block("down", LockedHatch(hall))
```

A blocked move *fails* (the player is told why) and does **not** advance the turn —
handy to know when reasoning about timed reactions. Ready-made blocks live in
`blocks/` (doors, darkness, vehicle gates).

---

## 9. Talking to the player, NPCs, scoring, endings

- **Narration:** `self.parser.ok(text)` / `self.parser.fail(text)`. The event log
  (`game.events`, `GameEvent` records) is the structured history; perception and
  reactions read it rather than scanning narration.
- **Asking a question:** pose a `Prompt` and the parser reads the player's next bare
  reply as the answer:
  ```python
  from text_adventure_games import Prompt
  game.pose_prompt(Prompt(text="Wits or steel?",
                          options={"wits": "choose wits", "steel": "choose steel"}))
  ```
  (Or `forward_as="..."` for a free-text reply.) `pending_prompt()` / `clear_prompt()`
  manage it.
- **NPCs:** `character.set_behavior(fn)` where `fn(character, game)` acts on the
  NPC's turn; `following` / `follow_filter` for companions; `riding` for mounts.
  LLM-driven agents are a larger topic — see `docs/design/generative-agents-port.md`.
- **Scoring & endings:** `game.award(key, points, msg=None)` scores once per key
  (idempotent); set `game.max_score`. End the game with `game.end_in_death(msg)` or
  by setting `game.game_over`/`game_over_description`; define winning by overriding
  `is_won()` on a `Game` subclass; `announce_ending(msg, show_score=True)` prints an
  epilogue once.

---

## 10. Conventions and gotchas

- **Runtime-only state isn't serialized.** `behavior`, `following`, `riding`,
  `reactions`, posed prompts, triggers, and recipes hold live callables/state and
  are re-attached by `build_game` — never persisted. Persist world facts as
  **properties** instead.
- **The react phase runs after *every* actor has moved.** So triggers/reactions see
  the whole round and are order-independent (multi-agent-safe). Read "what happened
  this round" from the event log (`disturbances_this_round`, `sounds_audible_at`,
  `entered_this_round`), never from a single global "last action".
- **Failed commands don't advance the turn.** A blocked move or a rejected
  precondition won't tick a countdown — useful when tuning timed reactions.
- **Properties default to `False`.** `get_property` on an unset key returns `False`,
  so you can gate on a flag before anything sets it.
- **Reach for the lightest tool.** A one-off rule is a `Trigger` lambda; a reusable
  creature reflex is a `Reaction` subclass; a typed verb is an `Action`. Don't
  reach for a class where a closure will do, or a closure where the Action-shaped
  library (`FleesAtNoise`/`Countdown`) already fits.

---

## 11. Where to look next

- **Worked examples:** `text_adventure_games/adventures/action_castle*.py` (full
  games) and `reactions_demo.py` (a tiny, heavily-commented sandbox for the react
  phase).
- **Design docs:** `docs/design/reactions.md` (reactions in depth),
  `docs/design/custom-world-authoring.md`, `docs/configuration.md`,
  `docs/converting-parsely-games.md`, `docs/TESTING.md`.
- **Run a game:** `python -m text_adventure_games.adventures.reactions_demo`
  (add `--walk` for a scripted tour).
