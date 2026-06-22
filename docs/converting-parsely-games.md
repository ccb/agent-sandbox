# Converting a Parsely game to the `text_adventure_games` engine

A practical guide to porting a Parsely-style gamebook (Action Castle, Spooky
Manor, etc.) into a runnable Python game on this engine. It's written for someone
authoring by hand *or* with an LLM (Claude) — the same principles apply.

The single most important idea up front:

> **Implement most of the commands, and generalize the reusable ones into the
> engine — don't hand-code them per game.** Most verbs you need (talk, follow,
> take/put, light, containers, crafting, yes/no choices) already exist as engine
> features. When you reach for a new verb that feels generic, add it to the
> engine so the next game gets it for free. That's what keeps the "missing
> actions" problem from recurring.

Two finished ports are your canonical references — read them alongside this guide:

- `text_adventure_games/adventures/action_castle_2.py` — town, gifts, a follower,
  topic dialogue, a shoe-size fit gate, posed-prompt dialogue.
- `text_adventure_games/adventures/action_castle_3.py` — a full party-based dungeon
  crawl: companions, ability-verbs, crafting, the whole interlock, scored epilogues.
- Their test suites (`tests/test_action_castle_2.py`, `tests/test_action_castle_3.py`)
  are the **spec of every supported command**, and AC3 ships a `--walk` walkthrough
  that wins 100/100.

---

## Contents

1. [Mental model: Parsely → engine](#1-mental-model)
2. [Read the rulebook into a port plan](#2-read-the-rulebook-into-a-port-plan)
3. [A minimal runnable game](#3-a-minimal-runnable-game)
4. [The world: locations, exits, items, characters](#4-the-world)
5. [How the parser routes a command (the key to "missing actions")](#5-how-the-parser-routes-a-command)
6. [Writing a custom action](#6-writing-a-custom-action)
7. [Reuse these engine features instead of reinventing them](#7-reuse-these-engine-features)
8. [Dialogue](#8-dialogue)
9. [Gates, set-pieces, and deaths: blocks and triggers](#9-gates-set-pieces-and-deaths)
10. [Scoring and endings](#10-scoring-and-endings)
11. [Walkthroughs and tests](#11-walkthroughs-and-tests)
12. [Authoring with Claude — it's a loop, not a prompt](#12-authoring-with-claude)
13. [Common pitfalls](#13-common-pitfalls)
14. [File map](#14-file-map)
15. [Worked example: porting Action Castle 4](#15-worked-example-porting-action-castle-4)

---

## 1. Mental model

A Parsely gamebook is a set of **rooms**, each listing a description, **items**,
**exits**, and a handful of **special commands** (verbs) with their effects, plus
a **scoring table** and several **endings/deaths**. The engine is the same world
expressed as Python objects:

| Parsely concept | Engine |
|---|---|
| Room | `things.Location` (a node in a graph) |
| Exit ("NORTH page 51") | `location.add_connection("north", other)` |
| Item / scenery | `things.Item` |
| NPC / creature | `things.Character` |
| Special command (verb) | an `actions.Action` subclass (or a built-in) |
| "It's blocked until..." | a `blocks.Block` on an exit |
| "When X happens, Y" | a trigger (`game.add_trigger`) |
| Scoring line | `game.award(key, points)` |
| The whole game | a `games.Game` subclass with `build_game()` |

A port is one module with:

- a `build_game()` that assembles locations, items, characters, custom actions,
  blocks, triggers, and recipes, and returns the game;
- a small `Game` subclass holding `max_score` and the win/ending logic;
- the custom `Action` subclasses for the genuinely novel verbs;
- a `WALKTHROUGH` list that wins, doubling as the regression test.

The player drives it through a **parser** that turns text into actions. Most of
your authoring effort is (a) laying out the world and (b) writing the few custom
verbs the parser doesn't already know — and **generalizing** the reusable ones.

---

## 2. Read the rulebook into a port plan

Before writing code, extract the book into a plan. (Use the `pdf-to-markdown`
skill to OCR the PDF first.) Make four lists:

1. **Locations & exits** — every room and its exits *and the page each leads to*,
   so you can wire the graph and catch one-way passages / collisions.
2. **Items** — gettable items vs. fixtures (scenery you can examine but not take);
   which start in the player's pack; which live in containers.
3. **Verbs** — every special command. For each, decide: *is this a one-off custom
   action, or an instance of a generic mechanic the engine already has* (talk,
   give-to-NPC, light, open, craft, a yes/no choice)?
4. **Scoring table + deaths/endings** — the points (they should sum to the max
   along the intended path) and every "THE END."

Then write a **canonical walkthrough** in your head (the shortest winning path).
That becomes your `WALKTHROUGH` and your first test. Build the world incrementally
and keep the walkthrough running green as you go.

---

## 3. A minimal runnable game

```python
from text_adventure_games import games, things, actions


def build_game() -> games.Game:
    cottage = things.Location("Cottage", "A cozy one-room cottage. A door leads out.")
    yard = things.Location("Yard", "A grassy yard. The cottage door is north.")
    cottage.add_connection("out", yard)        # auto-wires yard --in--> cottage

    lamp = things.Item("lamp", "a small brass lamp", "A small brass lamp.")
    cottage.add_item(lamp)

    player = things.Character(
        "you", "a curious villager", "I am exploring."
    )
    game = games.Game(cottage, player, characters=[], custom_actions=[])
    return game


if __name__ == "__main__":
    build_game().game_loop()      # interactive REPL
```

That already supports `look`, `go out`/`out`, `take lamp`, `examine lamp`,
`drop lamp`, `inventory`, and more — those are **built-in actions** (see §5).
You only write code for the verbs the book adds.

The real ports wrap this in a `Game` subclass for scoring/ending and add a
`WALKTHROUGH`; copy the top-of-file scaffolding from `action_castle_2.py`.

---

## 4. The world

### Locations and exits

```python
L = things.Location
square = L("Town Square", "A cobbled square. Exits lead north, south and east.")
hall = L("Town Hall", "A drafty hall.")
square.add_connection("east", hall)   # also wires hall --west--> square
```

`add_connection(direction, dest, travel_description="")` **auto-wires the reverse**
for canonical directions (north↔south, east↔west, up↔down, in↔out). Two gotchas:

- **Exit-collision footgun.** If several rooms all leave via `"out"` to the same
  hub, each auto-reverse tries to claim the hub's `"in"` — they collide and only
  the last wins (rooms become unreachable). When you need a one-way link, write it
  directly instead of via `add_connection`. AC2/AC3 use a `_one_way(frm, dir, to)`
  helper for exactly this (copy it). Use it for non-opposite pairs too (e.g. an
  `enter cavern` going in but `up` coming back).
- **Custom exit names work.** A direction can be any string, e.g.
  `square.add_connection("enter tunnel", underground)`. The player types `enter
  tunnel` and the parser matches it as a movement target.

### Items vs. fixtures

```python
sword = things.Item("sword", "a gleaming sword", "It's glowing faintly.")     # gettable
statue = things.Item("statue", "a stone statue", "A stern figure in armor.")
statue.set_property("gettable", False)                                        # scenery
```

Helper pattern from the ports: a tiny `_fixture(name, desc, examine)` that sets
`gettable=False`. Fixtures still respond to `examine`.

### Characters

```python
smith = things.Character("smith", "a burly blacksmith", "I shoe horses all day.")
smith.talk_text = '"Whaddya want? I\'m busy!"'     # what `talk to smith` says
smithy.add_character(smith)
```

`persona` is the character's *private* first-person mind (used by the LLM agent
in the simulation side) — **not** their spoken dialogue. Don't print persona as
speech; use `talk_text`/`talk_topics` for what they say (see §8).

### Player start inventory

Add items to `player.inventory` (a name→Item dict). To start the player with a
pack of gear, make a container and put items in it (see §7 — Containers). Note the
**one-level rule**: the engine's "held" helpers look one container deep, so don't
nest a container inside another you need to reach into (AC3 carries the waterskin
directly, not inside the backpack, for this reason).

### The `Game` subclass

```python
class MyGame(games.Game):
    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        self.score = 0
        self.max_score = 100
        self._scored_keys = set()

    def award(self, key, points, msg=None):
        if key in self._scored_keys:        # idempotent: score each event once
            return
        self._scored_keys.add(key)
        self.score += points
        if msg:
            self.parser.ok(msg)

    def is_won(self) -> bool:
        return bool(self.player.get_property("has_won"))
```

---

## 5. How the parser routes a command

This is the section that explains most "the action is missing" bugs. When the
player types a command, `Parser.determine_intent` decides which action to run, in
this order:

1. A comma-separated command → a SEQUENCE (run each part).
2. **Specific-first: a multi-word registered ACTION_NAME or alias that appears in
   the command wins.** This is the crucial rule.
3. A short keyword chain for built-ins: `say`/`speak`, `ask … about …`,
   directions, `look`, `examine`/`x`, `take off`/`remove`, `take`/`get`, `light`,
   `drop`, `eat`, `drink`, `give`, `attack`, `inventory`, `wait`, `quit`.
4. Crafting verbs (`make`/`craft`/`cook`/`combine`/…) — **only if the game has
   recipes** (see §7).
5. A direction / exit name → GO.
6. Else-fallback: the longest registered single-word action name that appears in
   the command **on a word boundary**.

The built-in actions you get for free (no code): **Go, Get/Take, Drop, Put,
Open, Close, Examine, Inventory, Give, Light, Eat, Drink, Wear/Take_Off,
Wield/Unwield, Attack, Talk, Follow/Unfollow, Say, Wait, Quit, Craft.**

### The rule that fixes "missing actions"

A signature Parsely verb like **`GIVE PENNY IN WELL`** or **`GIVE AXE TO SMITH`**
contains a built-in keyword (`give`), so a naïve custom action loses to the
built-in `Give`. **Make your custom action's `ACTION_NAME` multi-word** and it
wins via specific-first (step 2), *before* the keyword chain:

```python
class GiveAxeToSmith(actions.Action):
    ACTION_NAME = "give axe to smith"               # multi-word → routed first
    ACTION_ALIASES = ["give smith the axe", "hand the smith my axe"]
    ...
```

So: **if a verb collides with a built-in keyword, give it a multi-word name (and
add natural-phrasing aliases).** That single trick covers the majority of the
"Claude-generated game is missing this command" cases.

### The two parsers

- The default `Parser` does verb-noun matching as above — great for canonical and
  aliased commands, weak on free-form English.
- `LlmParser` (in `parsing.py`) interprets intent *and* arguments with an LLM
  constrained to the game's actual options, so "rouse the dragon" → `wake dragon`.
  `build_game()` should stay **parser-agnostic** — return the game on the default
  parser and let the caller swap in `LlmParser` via `game.set_parser(...)`.

---

## 6. Writing a custom action

Every action is a class with three parts. Construction matches the command's
targets; `check_preconditions` validates and reports failures; `apply_effects`
mutates the world and narrates.

```python
class MoveStone(actions.Action):
    ACTION_NAME = "move stone"                 # multi-word: routed specific-first
    ACTION_DESCRIPTION = "Shift the loose stone in the moat wall"
    ACTION_ALIASES = ["push stone", "shift the loose stone"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)   # who's acting
        self.moat = self.game.locations["Moat"]

    def check_preconditions(self) -> bool:
        if self.character.location is not self.moat:
            self.parser.fail("There's no loose stone here.")
            return False
        return True

    def apply_effects(self):
        self.moat.set_property("stone_moved", True)
        self.parser.ok("You heave the stone aside, revealing a tunnel.")
```

Key pieces:

- **Reporting:** `self.parser.ok(text)` for success/world narration;
  `self.parser.fail(text)` for a blocked/refused command. (NPC narration is
  `parser.npc_ok`.) These route to the renderer on typed channels — never `print`.
- **Helpers on the base `Action`:** `self.acting_character(command)`,
  `self.was_matched(thing, "error")`, `self.at(thing, location)`,
  `self.has_property(thing, prop, error_message=...)`.
- **State** lives as item/location/character **properties** (`set_property` /
  `get_property`, default falsy), or as flags on the `Game`.
- **Register** custom actions by passing the classes to the `Game` (the ports do
  `custom_actions=[MoveStone, ...]`); they're then routable by name.

Copy a small helper kit from the ports: `_die(game, text)` (narrate + set
`game_over`), `_relocate(game, char, dest_name)` (move + drag followers),
`_is_holding(char, name)` / `_take_held(char, name)` (held = inventory ∪ worn ∪
wielded ∪ open carried containers — quest checks must use this, not bare
`inventory`, or wielding/wearing an item makes the game think you dropped it).

---

## 7. Reuse these engine features

Before writing a custom action, check whether it's one of these. Each is a
shipped, tested, reusable feature — use it rather than reinventing it per game.

### Containers & surfaces
`item.make_container(capacity=None)` (things go *in*, can be open/closed) and
`item.make_surface()` (things rest *on*, always in view). `Get`/`Put`/`Examine`
reach into open holders — including a container the player is **carrying** (pull
the lamp out of your pack). A surface lists its contents in the room description.
*Used by:* AC2 boat/stump/treasure; AC3 backpack/waterskin.

### Item stacks / quantities (`#134`)
`item.make_stackable(n)` makes an item N identical, fungible units in one entry;
same-named stackable items merge on pickup. Recipes can then require `count > 1`
of a named item. Default items never stack. *(Inventories are name-keyed, so two
*non*-stackable items can't share a name — use stacks for true duplicates.)*

### Light & darkness
Flag a flammable light source (`FLAMMABLE`, `IS_LIT`); `light lamp` lights it. Gate
a dark passage with `blocks.Darkness(room)` — the exit is blocked until someone
present carries a lit item (in hand, worn, or an open carried bag).
*Used by:* AC3 cavern + dungeon descents.

### Follow / party
Set `npc.following = player` and the engine drags followers along on every move
(`Game.drag_followers`, recursive/cycle-safe). A would-be companion that isn't
ready sets `npc.set_property("refuses_follow", True)` with an optional
`"follow_refusal_message"`; **recruiting is just clearing that refusal.** A
`follow_filter` lets a companion refuse certain rooms. *Used by:* AC2 Rosemary;
AC3's whole 4-member party + `INVITE`.

### Posed prompts — dialogue forks (`#110`)
When the game asks a question, `game.pose_prompt(Prompt(...))`. The parser reads
the next otherwise-unrecognized reply as the answer — **non-modal** (`look`/
`inventory` still work). Two shapes:

```python
from text_adventure_games import Prompt
# choice: a bare "wits" / "steel" runs the mapped command
game.pose_prompt(Prompt(text="Wits or steel?",
                        options={"wits": "choose wits", "steel": "choose steel"}))
# free-text: forward the whole reply to a verb ("a wise man" -> "answer riddle a wise man")
game.pose_prompt(Prompt(text="Answer the riddle.", forward_as="answer riddle"))
```

Prompts expire when answered, replaced, or when the player leaves the room.
*Used by:* AC3 dragon-less... the dragon lives in AC2; AC3 uses it for the
GO-NORTH-home "are you sure?" and could for any yes/no.

### Crafting (`#136`)
Declare recipes; one generic `Craft` action drives `make`/`cook`/`combine`/…:

```python
from text_adventure_games import Recipe, Ingredient
game.add_recipe(Recipe(
    name="stew", aliases=["mushroom stew"],
    inputs=["water", "cave mushroom"],     # consumed from held items
    tools=["pot"],                          # required present, NOT consumed (station/instrument)
    output=lambda g: things.Item("stew", "a bowl of stew"),
    result_text="You simmer the mushrooms in spring water into a stew.",
))
```

Ingredients match by **name** or by a property **tag** (`Ingredient(tag="plank",
count=2)`), summing stack quantities. *Used by:* AC3 mushroom stew.

### Give-to-NPC exchanges
Model "GIVE X TO Y → effect" as a multi-word custom action (see §5), or — for the
"hand it back / react" pattern — let the built-in `Give` run and attach a trigger
that reacts to the resulting state (§9). AC2's smith sharpening the axe uses the
trigger approach so it fires regardless of phrasing.

---

## 8. Dialogue

- **`talk to X`** → the built-in `Talk` verb prints `X.talk_text` verbatim.
- **`talk to X about Y` / `ask X about Y`** → looks up `X.talk_topics[Y]`:

```python
hermit.talk_text = "The hermit mumbles something about a prophecy."
hermit.talk_topics = {"prophecy": '"A champion will arise from humble beginnings."'}
```

You don't write a custom action for these — just set the attributes. The
deterministic parser matches the topic by keyword; `LlmParser` matches by meaning.

- **Choices / yes-no / riddles** → posed prompts (§7), so the player can answer in
  plain words (`yes`, `wits`, `a wise man`) instead of guessing a magic verb.
- Write spoken lines as full narration (include the quotes). Keep `persona` for the
  character's private reasoning, not their speech.

---

## 9. Gates, set-pieces, and deaths

### Blocks gate an exit

A `blocks.Block` subclass decides whether a direction is passable. `is_blocked()`
returns a bool; the block's `description` is shown when blocked.

```python
from text_adventure_games import blocks

class FlagBlock(blocks.Block):
    def __init__(self, loc, flag, description):
        super().__init__("The way is shut", description)
        self.loc, self.flag = loc, flag
    def is_blocked(self) -> bool:
        return not self.loc.get_property(self.flag)

dark_corridor.add_block("east", FlagBlock(dark_corridor, "door_open", "The door is shut."))
# ...then an `open door` action sets door_open=True.
```

`blocks.Darkness` and `blocks.Locked_Door` are ready-made. AC3's web, net-trap,
backpack-gate, and door/maiden gates are all small `Block` subclasses.

### Triggers react after a turn

`game.add_trigger(name, condition, action, repeatable=False)` runs `action(game)`
in the post-turn react phase whenever `condition(game)` is true. Use them for
set-pieces and conditional deaths that aren't tied to one verb:

```python
game.add_trigger(
    "baby_alerts_bandits",
    lambda g: _carrying_crying_baby(g) and g.player.location.name == "Bandit Camp",
    lambda g: _die(g, "The baby's wailing alerts the bandits. THE END."),
    repeatable=False,
)
```

A trigger that should fire once is `repeatable=False`; an ongoing check (e.g.
"score each newly-visited room", "the demon devours you if you dawdle") is
`repeatable=True`, guarded by its own condition.

### Deaths and one-way relocations

`_die(game, text)` ends the game with a death message. `_relocate` moves the
player (e.g., a chute that drops you elsewhere). The engine ends the game when the
player dies, when `game.game_over` is set, or when `is_won()` returns true.

---

## 10. Scoring and endings

- `game.max_score` is the rulebook total; `game.award(key, points, msg=None)`
  scores an event **once** (idempotent by key). Make the keys mirror the scoring
  table ("bow", "spider", "banish_demon", …).
- **Watch the `is_won()` / `is_game_over()` interaction.** `is_game_over()` returns
  `is_won()`, so if your *win achievement* (e.g. "killed the boss") returns true
  from `is_won()`, the game ends *immediately* — before the player walks home for
  the last points. If the rulebook ends by "returning home," **gate `is_won()` on
  `game_over`** so it reports the final state rather than triggering it:

  ```python
  def is_won(self):
      return bool(self.game_over and not self.player.get_property("is_dead")
                  and self.player.get_property("banished_demon")
                  and self.player.get_property("killed_cultist"))
  ```

- **Multiple endings:** branch by progress in an epilogue routine fired by an
  arrival trigger at the "home" room (AC3's `GO NORTH` → score-branched epilogues).

---

## 11. Walkthroughs and tests

Every port ships a `WALKTHROUGH` (a list of commands that wins) and a test that
runs it. Tests double as the **spec of supported commands** and catch regressions
as the engine evolves. Use `CaptureRenderer` to assert on output:

```python
from text_adventure_games.adventures import my_game as mg
from text_adventure_games.reporting import CaptureRenderer, Channel

def _play(cmds):
    game = mg.build_game()
    cap = CaptureRenderer(); game.parser.set_renderer(cap)
    for c in cmds:
        game.do_command(c)
        if game.is_game_over():
            break
    return game, cap

def _said(cap, sub):                       # player-facing text (narration + blocked)
    return any(sub in t for ch in (Channel.NARRATION, Channel.BLOCKED)
               for t in cap.texts(ch))

def test_walkthrough_wins():
    game, _ = _play(mg.WALKTHROUGH)
    assert game.is_won() and game.score == game.max_score
```

Also worth testing (AC3 does all of these): topology (every exit resolves; no
room has two exits to the same place), each gate (blocked → unlock → passable),
each death, and each scoring event. Run `pytest` and `black` before you push:

```bash
uv run pytest tests/ -q
uv run black text_adventure_games/ tests/
```

See `docs/TESTING.md` for the house testing conventions.

---

## 12. Authoring with Claude

If you're generating the port with Claude (this is the recommended flow):

- **Point it at the references and this guide:** "Port this Parsely game the way
  `action_castle_3.py` does it; follow `docs/converting-parsely-games.md`; reuse
  the engine's containers/follow/prompts/crafting/darkness features rather than
  reimplementing them."
- **Give it the parser rule explicitly:** custom verbs that collide with built-in
  keywords (give/take/drop/say/attack/open) must use **multi-word `ACTION_NAME`s**
  so they route specific-first. This prevents the #1 generation failure ("the
  action isn't wired up").
- **Build in slices, verify each:** generate the world skeleton + topology test
  first, then companions/verbs, then the endgame — running `pytest` between slices
  rather than generating 1500 lines blind.
- **Demand the walkthrough.** A `WALKTHROUGH` that wins at full score is the proof
  the port is complete and correct; make Claude produce and pass it.
- **Generalize as you go.** When Claude writes a verb that's really generic
  (light, talk, a yes/no choice, combining items), have it lift the mechanic into
  the engine (with its own tests) and use it from the game — that's how the shared
  engine grows and the *next* game starts ahead.

---

## 13. Common pitfalls

- **Verb collides with a built-in keyword** → use a multi-word `ACTION_NAME`
  (+ aliases). (§5) This is the most common "missing action."
- **`is_won()` ends the game too early** → gate it on `game_over` if the ending is
  "return home." (§10)
- **Exit auto-reverse collisions** → multiple `out`→hub links clobber the hub's
  `in`; use a one-way helper. (§4)
- **Quest checks on bare `inventory`** → an item the player *wields* or *wears*
  isn't in `inventory`; check "held" (inventory ∪ worn ∪ wielded ∪ open carried
  containers) via an `_is_holding` helper. (§6)
- **Nested containers** → held-scope helpers look one level deep; don't bury a
  container you need to reach into inside another. (§4)
- **Two identical items** → inventories are name-keyed; you can't hold two items
  named "stick" — use a stack (`make_stackable`). (§7)
- **Persona printed as speech** → persona is the NPC's private mind; use
  `talk_text`/`talk_topics` for dialogue. (§8)
- **`print()` instead of the renderer** → always `parser.ok`/`parser.fail` so
  output is captured and channel-typed. (§6)
- **A trigger that should fire once is `repeatable=True`** (or vice-versa) → pick
  deliberately and guard the condition. (§9)

---

## 14. File map

| Where | What |
|---|---|
| `text_adventure_games/adventures/action_castle{,_2,_3}.py` | the three reference ports |
| `tests/test_action_castle_{2,3}.py` | their tests = the command spec |
| `text_adventure_games/things/` | `Item`, `Character`, `Location` |
| `text_adventure_games/actions/` | built-in actions; subclass `actions.Action` |
| `text_adventure_games/parsing.py` | `Parser` (routing) + `LlmParser` |
| `text_adventure_games/blocks/` | `Block`, `Darkness`, `Locked_Door` |
| `text_adventure_games/crafting.py` | `Recipe`, `Ingredient` |
| `text_adventure_games/prompts.py` | `Prompt` (posed dialogue) |
| `text_adventure_games/games.py` | `Game` (loop, triggers, recipes, relocate) |
| `journal/chris.md` | the narrative of how AC2/AC3 were built + why |

When in doubt, find the same situation in `action_castle_3.py` — almost every
mechanic in this guide is exercised there.
