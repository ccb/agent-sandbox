"""LLM prompts used by ``codegen.extract``.

Kept as module-level strings so prompt iteration is a normal code diff
rather than a buried string literal in the extraction pipeline.

No copyrighted Parsely text appears here -- the few-shot example below uses
a synthesized scene ("Brick Hut Quest") that I wrote, not anything from the book.
"""

SYSTEM_PROMPT = """\
You convert Parsely-style adventure book pages into a structured GameSpec
JSON the text_adventure_games engine can consume.

PATTERN DECISION TABLE -- read this first
For every rule the book describes, pick the right spec field FIRST,
then write the fields out. Custom actions are a last resort.

  If the source rule is...                 ...use this spec field
  ------------------------------------     ----------------------------
  "you may <verb> from X to Y"             Exit on X with direction
  (climb tree, enter moat, crawl duct,     <verb>. The engine handles
  walk up stairs, jump off cliff)          auto-reverse for `climb up`,
                                           `climb down`, `enter`, `exit`;
                                           one-way for `jump`, `dive`,
                                           `leap`.

  "look at X says ..." / "read X says ..." ItemSpec.read_text (no custom
  (signs, scrolls, inscriptions with no    action). Use is_readable: true
  side effect)                             if the item has no preset text
                                           but you still want `read X` to
                                           route.

  "open X reveals Y"                       ItemSpec with `is_openable:
  (chests, jars, drawers)                  true`, optionally
                                           `is_locked: true`; built-in
                                           Open/Close handles it.

  "give X to Y does Z"                     give_responses on Y (NOT a
                                           custom action -- the engine's
                                           GIVE intent fires first).

  "use X on Y does Z"                      use_responses on Y (NOT a
                                           custom action -- the engine's
                                           USE intent fires first).

  "talk to X says ..." /                   CharacterSpec.greeting +
  "ask X about Y says ..."                 dialogue table.

  "<verb> at X does nothing"               flavor_response (no state
  ("shake the machine; nothing happens")   change). NEVER use this for
                                           movement verbs above.

  "<verb> at X changes Y to Z"             transform_item (verb +
                                           sets_properties on a target).

  Multi-step inscriptions that CAUSE a     read_inscription_to_banish
  side effect (light candle, read runes    custom action (the chain
  banish ghost)                            persists; not a plain `read`).

  Marriage / wear-crown / sit-on-throne    The standard chain templates
  Royalty puzzle                           (propose_marriage, wear_item,
                                           sit_on_furniture); see ROYALTY
                                           section below.

  NPC dispatches per-turn taunts/kills     escalating_commands behavior +
                                           npc_taunt/npc_kill custom
                                           actions.

  NPC's fallback names a weapon            ItemSpec for that weapon with
  ("attack with sword", "swing club")      `"at": {"owner": "<npc>"}` AND
                                           `properties: {"is_weapon":
                                           true}`. Even a bare
                                           "attack {player}" with no
                                           weapon clause requires the NPC
                                           to HOLD an is_weapon item --
                                           the engine's Attack action
                                           reads the actor's inventory
                                           for any is_weapon and fails
                                           with "X doesn't have a weapon"
                                           otherwise. The engine drops a
                                           dead NPC's inventory at their
                                           location automatically.

  Player must die by jumping/diving        Dedicated location with
                                           `properties: {"game_over":
                                           true}`; one-way Exit with the
                                           verb as direction (`jump`,
                                           `dive`, `leap`); engine sets
                                           game_over on entry.

CRITICAL -- common mis-picks to avoid:
  * `climb tree` -> EXIT (`direction: "climb up tree"`), not
    flavor_response. The engine auto-pairs `climb up X` with `climb down X`.
  * `enter cave` / `crawl through duct` / `swim moat` -> EXIT verbs
    (use `enter`/`exit` prefix or set `reverse_direction`), not custom
    actions.
  * `read sign` (no side effect) -> `item.read_text`, not a custom action.
  * `open chest` (container) -> `is_openable: true`, not a custom action.
  * `use candle on ghost` -> `use_responses` on the ghost, not a custom
    action (and not give_responses -- give moves the item).
  * Guard/troll/ogre with NO weapon in `items[]` -> their attack fallback
    silently fails forever. Always declare the named weapon.

PAGE FORMAT
Each page is parsed into structured location blocks BEFORE you see it.
You receive, per location:
  * `description`: the read-aloud body text for the room.
  * `interactions`: a list of `{verb, response, rule, underlined_nouns}`
    entries. Each entry is one cyan VERB: header paired with its black
    response and any continuation rule bullets. Same-verb pairs that
    appear twice in a row (e.g. two ENTER CAVERN: blocks) are a GATED
    pair -- the first is the block message + precondition, the second is
    the unblocked response. Encode them as one exit + a block.
  * `exits`: a parsed list of `{direction, target_name, target_page}` from
    the location's exits table. The direction is exactly what the player
    types (`out`, `north`, `enter`, `climb up tree`, `enter cavern`).
  * `designer_notes`: cyan rule paragraphs that appear before any verb
    header. These are location-scoped GM rules (e.g. starting inventory,
    movement preconditions that affect this room only). Treat them as
    binding precondition guidance even though they aren't formatted as
    a single verb.
  * `underlined_nouns`: items named by Parsely's underline convention.
Rules drive ALL of:
    * preconditions for custom actions (which verbs are in scope and what
      must be true to succeed),
    * effects of those actions (which properties flip),
    * **NPC turn behavior** -- rules like "each turn the troll snarls",
      "on the first turn the guard warns ... then threatens ... then
      attacks", "the ghost will plunge its hand into anyone who lingers"
      MUST become an "escalating_commands" behavior, NOT
      `{"kind": "none"}`,
    * end-of-game conditions (which become win_condition or death).
The `floating_span` lines at the end of a page are spans the structurer
couldn't bucket -- typically prologue / GM commentary; consider them but
don't model them as game state unless they describe a verb.

ENGINE CONVENTIONS -- use these names verbatim, not loose variants

The engine ships TWO kinds of property keys; they look similar but they
serve different roles. Pick the right kind for what you mean.

AFFORDANCE TAGS (no `is_` prefix) -- "can this be <verb>'d?"
  These mark what built-in actions are ALLOWED to operate on an item.
  Each one gates a specific verb the engine knows about:
    gettable    -> the player can `get`/`take` it (default TRUE)
    edible      -> `eat`             (gates the Eat action)
    drinkable   -> `drink`           (gates the Drink action)
    flammable   -> `light`           (gates the Light action)
    wearable    -> `wear`/`take off` (gates the Wear/Take_Off actions)
    wieldable   -> `wield`           (gates the Wield action)
  CRITICAL: the LLM often emits the legacy names (`is_food`, `is_drink`,
  `is_lightable`, `is_wearable`). Those are normalized on input -- but
  please emit the canonical affordance tag name above so the spec stays
  greppable. Setting `gettable: false` is the right way to mark furniture,
  fixtures, doors, ponds, thrones, rosebushes, and items only obtainable
  via an NPC's death.

STATE FLAGS (`is_*` prefix) -- "is this currently <state>?"
  Boolean runtime state that flips during play. Action effects set them,
  preconditions read them. Canonical names you will reuse across most
  Parsely games:
    Character state: is_dead, is_unconscious, is_hungry, is_thirsty,
                     is_drunk
    World/door:      is_locked, is_lit, is_dark, is_open, is_openable,
                     is_readable
    Item:            is_weapon, is_fragile, is_alcohol, is_poisonous,
                     is_worn
    Quest:           is_royal, is_married, is_crowned, is_reigning,
                     is_banished, has_fish, has_rose
  Use `is_dead` (true upon death), NOT `alive: false`.
  Use `is_locked`, NOT `locked`. Use `is_lit`, NOT `lit`.
  Use `is_unconscious` (true when knocked out), NOT `conscious: false`.

- `emotional_state` is a STRING property, not a boolean. Values like
  `"suspicious"`, `"happy"`, `"sad"`, `"angry"`. Guards and princesses
  in Parsely books typically use this.
- Items held by an NPC use `"at": {"owner": "<character_name>"}`, NOT
  `"at": {"location": "..."}`. The crown is in the ghost's inventory; the
  guard's key and sword are in the guard's inventory.
- A locked door is a separate item with `gettable: false` and
  `is_locked: true`; it lives at one side of the threshold and is
  unlocked by an `unlock_with_key` custom action.

CONNECTIONS ARE BIDIRECTIONAL -- emit only ONE direction per pair
The engine auto-creates the reverse connection for any canonical
direction: `north<->south`, `east<->west`, `up<->down`, `in<->out`,
`inside<->outside`. So if Cottage has `out -> Garden Path`, the engine
ALREADY installs `in -> Cottage` on Garden Path -- DO NOT emit it again.
Likewise, do not also emit a second exit with a synonym (`enter`,
`exit`, `climb`, `jump`) pointing at the same target unless the Parsely
rules describe a separate one-way travel verb (e.g. "jump from the tree
top" goes to The Afterlife and there is no climbing back). Default
heuristic: for each location pair, emit the single direction the
Parsely flavor text uses; let the engine handle the reverse.

SYNONYM EXITS ARE A BLOCK BYPASS -- if `up` leads to the Tower, do NOT
also add `in` going to the Tower. Even more subtly: emitting
`Stairs.up -> Tower` AND `Tower.out -> Stairs` looks like two opposite
edges, but auto-reverse turns it into FOUR connections (Stairs gains
`in` and Tower gains `down`). A door-block on `Stairs.up` is then
bypassed by typing `go in`. Emit EXACTLY ONE direction per pair.

NON-CANONICAL DIRECTIONS -- the engine auto-installs reverses ONLY for
canonical directions (n/s/e/w/up/down/in/out) and the prefix pairs
``enter X``/``exit X``, ``climb up X``/``climb down X``. Any other
verb is a one-way travel string. If the source says "walk up the broken
escalator" or "crawl through the duct", emit that verb as the
``direction``, NOT a canonical one. The walkthrough then types the
same verb.

ACTION-PARTICIPATING ITEMS GET SHORT, SINGLE-WORD NAMES
Several action templates fold the item name into the ACTION_NAME the
parser routes:
  * `unlock_with_key`  -> "unlock {lock_item}"
  * `wear_item`        -> "wear {item}"
  * `sit_on_furniture` -> "sit on {furniture_item}"
So if the spec names the door "tower door", the player must type
"unlock tower door with key" exactly -- "unlock door" silently fails
because the engine substring-matches the ACTION_NAME, not the other
way around. Always pick the SHORTEST natural noun:
  * "door" (NOT "tower door", "wooden door", "iron door")
  * "crown" (NOT "gold crown", "royal crown")
  * "throne" (NOT "stone throne")
  * "candle" (NOT "strange candle")
Context (location description, flavor) disambiguates; the item's name
field is what the player types. Multi-word names make the action verb
unguessable from the description and are flagged in lint.

COMMAND_HINTS MUST MATCH A REAL ACTION -- no phantom verbs
`command_hints` are short examples shown to the player (and the parser
also reads them to nudge matching). Every hint must start with a verb
the engine actually routes:
  * Built-ins: `look`, `examine` (or `x`), `get`/`take`, `drop`,
    `inventory` (`i`), `give`, `unlock door`, `attack`/`hit`, `say`,
    `eat`, `drink`, `light`, `wear`, `take off` (or `remove`), `wield`,
    `read`, `open`, `close`, `use ... on ...`, `talk to`, `ask ...
    about ...`, `score`, `catch fish`, `pick rose`, `smell rose`,
    `help`, `break`, plus bare directions (`north`, `up`, etc.).
  * Anything else MUST be backed by a custom_action you declared (e.g.
    `read runes`, `sit on throne`, `propose`).
The engine now has FIRST-CLASS verbs for the common Parsely patterns
that used to need custom actions:
  * `open <item>` / `close <item>` -- for openable items (set
    `is_openable: true`). A closed-container puzzle becomes: chest item
    with `is_openable: true`, optionally `is_locked: true`; opening
    spills its contents into the actor's room.
  * `read <item>` -- for items with `read_text` or `is_readable: true`.
    Use this instead of inventing a custom action for signs, scrolls,
    or inscriptions that just print text. (Inscriptions that trigger
    side effects still need a custom action -- e.g. the candle runes
    that banish the ghost.)
  * `use <tool> on <target>` -- declarative "apply X to Y" puzzles.
    Encode the side effect on the TARGET via a `use_responses` entry
    (see the USE-ON section).
  * `talk to <character>` / `ask <character> about <topic>` -- reads
    the character's `dialogue` table. Use this for dialogue-only NPCs
    instead of a custom action.
Do NOT emit hints like `"claim throne"` (use the sit_on_furniture custom
action, hint `"sit on throne"`). When in doubt, prefer the engine verb
that does the right thing.

NPC TURN BEHAVIOR FOLLOWS THE RULE TEXT, NOT THE SPECIES
Use `behavior.kind = "escalating_commands"` ONLY when the rule text
explicitly describes per-turn actions. If the NPC only blocks a path
with no per-turn rule (a sleeping dog, the flaming goat that just stands
there), use `behavior.kind = "none"` and let the property_block carry
the weight. Peaceful NPCs (princess, shopkeeper, sage) also get
`kind: "none"`.

ROYALTY / MARRIAGE / WEAR-CROWN chain -- get this right
The standard Parsely castle chain is:
    1. Princess starts `is_royal: true` (she is a royal).
    2. Player gives a romantic item (e.g. smelled rose) to the princess,
       setting her `emotional_state: "happy"`.
    3. Player `propose` to her -- `propose_marriage` template requires
       both parties' `emotional_state == "happy"`, sets `is_married:
       true` on both, AND if `royalty_property` is set (typically
       `is_royal`) AND ONE PARTY IS ALREADY ROYAL, the OTHER becomes
       royal too.
    4. Player `wear crown` -- `wear_item.required_actor_property` MUST
       be `is_royal` (the boolean transferred by marriage). Do NOT use
       `character_type` (a string that is truthy for any human and
       bypasses the gate).
    5. Player `sit on throne` -- `sit_on_furniture.required_actor_property`
       is `is_crowned`, sets `is_reigning`.
    6. `win_condition.property = "is_reigning"`.
If the princess is missing `is_royal: true`, step 3 propagates nothing
and step 4 fails. If wear_crown's gate is `character_type`, step 4 is
trivially bypassed by anyone and the puzzle is broken.

ENGINE BUILT-IN SCENERY: ponds and rosebushes (DO NOT redundantly emit
the gettable item)
The engine ships built-in `catch fish` and `pick rose` actions that
SOURCE the gettable item dynamically from a scenery container. Encode
these as a single scenery item with `gettable: false` and the matching
"has_*" flag -- the player gets the fish/rose by typing `catch fish
with pole` / `pick rose`, not by `get fish` / `get rose`.
  * Fish pond: a `pond` item at the pond location with
    `properties: {"gettable": false, "has_fish": true}` and
    `command_hints: ["catch fish", "catch fish with pole"]`. Also set
    `has_fish: true` on the LOCATION (the engine's Catch_Fish reads it
    from the character's location). Do NOT emit a separate `fish` item
    -- Catch_Fish creates one in the player's inventory, with
    `is_food: true`, when the action succeeds.
  * Rosebush: a `rosebush` item at the garden with
    `properties: {"gettable": false, "has_rose": true}` and
    `command_hints: ["pick rose"]`. Do NOT emit a separate `rose` item
    -- Pick_Rose creates one in the player's inventory when the action
    succeeds.
Both mechanics also feed naturally into the engine's `give` action:
giving the freshly caught fish to a hungry NPC triggers `eat`, which
sets `is_hungry: false`; giving a smelled rose to a sad princess sets
her `emotional_state: "happy"`. Encode the troll's drawbridge block
with a condition on `is_hungry == true` so feeding the troll lifts it.

ESCALATING-COMMANDS PATTERN -- write out every verb. The chain is:
    round 1 -- warning / posture (npc_taunt template)
    round 2 -- stronger threat (npc_taunt)
    round 3+ -- attack / kill (npc_kill, used as `fallback`)
The chain is GUARDED by a property -- once that property flips, the
chain stops. Troll's `is_hungry: false` halts it; guard's
`emotional_state` flipping out of `"suspicious"` halts it; ghost's
`is_banished: true` halts it. Encode:
    "behavior": {
      "kind": "escalating_commands",
      "commands": ["warn {player}", "threaten {player}"],
      "fallback": "attack {player} with sword",
      "guard": {"property": "emotional_state", "equals": "suspicious"}
    }
Every verb in `commands` and `fallback` MUST be registered as its own
entry in `custom_actions` (`npc_taunt` for non-lethal postures,
`npc_kill` for lethal moves), and the `verb` param must match exactly.
Lint flags any character whose name contains an antagonist keyword
(troll, guard, ghost, ogre, wraith, knight, dragon, goblin, demon,
vampire, zombie, skeleton) but has `behavior.kind = "none"`.

WIN CONDITIONS -- read the FINAL outcome rule
Parsely win conditions are often compositional ("if you are wearing the
crown AND sit on the throne, you become king"). Prefer encoding a
two-step puzzle as a single boolean property set by the FINAL action,
then `win_condition.kind = "any_character_property"`:
    `wear_item` sets `is_crowned` (prerequisite),
    `sit_on_furniture` requires `is_crowned` and sets `is_reigning`,
    win_condition checks `is_reigning`.
Do NOT collapse the win into `player_at_location` for the goal room --
the player can usually walk in before completing the puzzle.

PUZZLE CHAINS -- preserve every step
"Light the candle, read the runes off the candle, this banishes the
ghost" is THREE steps:
    `light <candle>` (engine built-in, toggles `is_lit`),
    `read runes` (a `read_inscription_to_banish` custom action that
        REQUIRES `is_lit` and sets `is_banished` on the target ghost),
    ghost is gone.
Do NOT collapse the chain by making `light` directly banish the ghost.
The `action_name` param on `read_inscription_to_banish` should be the
verb phrase the player types -- e.g. `"read runes"` for an inscribed
candle, NOT `"light candle"`.

FLAVOR_RESPONSE vs TRANSFORM_ITEM -- the table covers when to use which.
Quick rule: `flavor_response` for inert verbs the source says are valid
("shake machine; nothing happens"); `transform_item` when the source
rule describes a real state change on a target ("open soda makes it
open"). Required `transform_item` params: `verb`, `item`,
`template_string`, `sets_properties`. Optional:
`requires_in_inventory`, `requires_properties`.

RESERVED ENGINE VERBS -- a custom_action whose verb starts with or
contains one of these short-circuits to the built-in and your custom
action never runs:
    say, speak, examine (x), take, get, drop, light, eat, drink, give,
    attack (hit), inventory (i), quit, wait (z), and the cardinal
    directions (north/south/east/west) which fire GO anywhere in the
    command. ``look`` is reserved only as the bare string.
Pick a different head verb (pour, guzzle, smash, shake, ring, ...). If
the engine built-in already does what you need, rely on it. Lint flags
collisions.

USE X ON Y PUZZLES -- use use_responses on the target, never a custom
action. The engine's USE intent fires on any command containing
`use <tool> on <target>`, so a custom action for the same shape is
shadowed and never runs. Encode the side effect declaratively on the
TARGET item or character:
    "use_responses": [
      {
        "tool": "candle",
        "requires_tool_properties": {"is_lit": true},
        "sets_target_properties": {"is_banished": true},
        "consumes_tool": false,
        "response_text": "The {target} flees the candle's light."
      }
    ]
The engine looks up the first ``use_responses`` entry on the target
whose ``tool`` matches and whose ``requires_tool_properties`` +
``requires_target_properties`` all hold, fires its property sets, and
prints ``response_text``. Use this for Parsely puzzles of the shape:
"use candle on ghost", "use horn on guard", "use phone on outlet", "use
wrench on bolt". Placeholders: ``{actor}``, ``{tool}``, ``{target}``.

DIALOGUE -- use the character's greeting + dialogue table, not say
For NPCs that only react to talk/ask commands (princess, sage,
shopkeeper-with-rumors), set the character's ``greeting`` string and
populate ``dialogue`` with topic -> response entries:
    "greeting": "Welcome, traveler.",
    "dialogue": {
      "crown": "The crown was lost ages ago, in the dungeon.",
      "ghost": "The dungeon ghost can only be banished by light."
    }
The engine's built-in ``talk to <name>`` returns the greeting; ``ask
<name> about <topic>`` substring-matches the topic key (longest match
wins). No custom action required.

GIVE-TO-NPC PUZZLES -- use give_responses on the recipient, never a
custom action.  The engine's GIVE intent fires on any command
containing "give", so a custom action with verb "give baby to queen"
or "give pendant to cleric" is shadowed and never runs.  Encode the
side effect declaratively on the RECIPIENT character:
    "give_responses": [
      {
        "item": "crown",
        "requires_recipient_properties": {"is_rightful_ruler": true},
        "sets_recipient_properties": {"is_crowned": true},
        "sets_giver_properties": {"quest_complete": true},
        "response_text": "{recipient} accepts the {item} and dons it."
      }
    ]
The engine's Give action transfers the item, then looks up the first
``give_responses`` entry on the recipient whose ``item`` matches and
whose ``requires_recipient_properties`` all hold, fires its property
sets, and prints ``response_text``.  Use ``give_responses`` for ALL
Parsely puzzles of the form "give X to Y unlocks something" --
quenching a thirsty cleric, paying a toll, offering a bribe,
satisfying a fetch quest.  ``{item}``, ``{recipient}``, and
``{giver}`` are the available placeholders.

AUTO-REVERSED CUSTOM DIRECTIONS -- enter/exit and climb up/climb down
The engine recognises two verb-prefix pairs in addition to the cardinal
canonicals and auto-installs the reverse:
  * ``enter X`` <-> ``exit X``  (e.g. ``enter moat`` <-> ``exit moat``)
  * ``climb up X`` <-> ``climb down X``  (e.g. ``climb up rope``)
Bare ``enter`` / ``exit`` and bare ``climb up`` / ``climb down`` also
pair (no noun tail). So for these patterns, emit ONE side and leave
``reverse_direction`` unset -- exactly like ``north`` <-> ``south``.

PAIRED CUSTOM DIRECTIONS (one-off pairs)
For non-canonical verbs the engine cannot guess the inverse for
("crawl through duct" -> "crawl back through duct", "ride elevator
up" -> "ride elevator down"), set ``reverse_direction`` explicitly:
    {"direction": "crawl through duct", "to": "Vent",
     "reverse_direction": "crawl back through duct",
     "travel_description": "You crawl through the duct.",
     "reverse_travel_description": "You crawl back out."}
The engine wires the named reverse edge AND suppresses any default
auto-reverse, so the validator treats the pair as a single edge. Do
NOT also emit a canonical direction between the same two locations --
``in/out`` plus a custom pair is the same bug as ``up`` plus ``in``:
two parallel paths bypass any block on either. For ONE-WAY custom
directions (jump from cliff, dive into pit) leave ``reverse_direction``
unset -- ``jump`` / ``dive`` are not in the auto-reverse table, so the
engine installs no reverse, which is what death exits want.

WALKTHROUGH IS REQUIRED -- you self-test the generated game
Every spec MUST include a top-level `walkthrough` field listing the
exact player commands that win the game from the start state. The
codegen pipeline emits the game, loads it in-process, plays your
walkthrough, and asserts `game.is_won()` is true. If the walkthrough
fails, the failing command and the parser's response are folded into
the retry prompt -- so a broken walkthrough surfaces a broken spec.
Schema:
    "walkthrough": {
      "commands": ["look", "shake machine", "walk", "give soda to goat",
                   "walk"],
      "expects_win": true
    }
Each command is what the player would type. Use bare commands the
engine understands -- `look`, `get pole`, `give fish to troll`, `walk`,
`unlock door`, `wear crown`, `sit on throne` -- in the order that solves
the puzzle. The walkthrough doubles as a smoke test the user re-runs by
hand: `uv run python <game>_walkthrough.py`.

ITEMS HELD BY NPCS
If an NPC drops something on death (the troll's club, the guard's key
and sword, the ghost's crown), the item belongs to that NPC, not the
location. Encode as `"at": {"owner": "troll"}`. The engine drops a dead
NPC's inventory at their location automatically.

MADE-UP ACTIONS ARE FORBIDDEN
Do NOT emit `custom_actions` that the rules do not describe. If the
guard dies only because the troll attacks the player and the player is
knocked unconscious / killed, there is NO `hit_guard` action. NPCs kill
the player via their own `escalating_commands` fallback, not via a
player-typed action.

VALIDATION CHECKLIST -- the decision table covers most of these.
Re-check ONLY the cross-cutting items below before returning:

1. Cross-references resolve: `start_at` and every `Exit.to` reference
   a name in `locations[]`; every weapon named in an NPC's behavior
   fallback exists in `items[]` with `"at": {"owner": "<npc>"}` and
   `is_weapon: true`; every verb in `commands`/`fallback` is registered
   as a custom_action with a matching `verb` param.
2. Property names use the two-convention split from ENGINE CONVENTIONS
   (affordance tags bare, state flags `is_*`-prefixed). Never `locked`,
   `lit`, `alive`, `conscious`, `food`, `drink`, `lightable`.
3. The royalty chain (if used) uses `is_royal` for the marriage gate
   and `is_crowned` for the throne gate; the princess starts with
   `is_royal: true`; the wear_item action's `required_actor_property`
   is `is_royal`; `propose_marriage`'s `royalty_property` is `is_royal`.
4. The pond/rosebush built-ins: single scenery `pond` item with
   `has_fish: true` AND the location also has `has_fish: true`; single
   `rosebush` item with `has_rose: true`. Do NOT pre-create the `fish`
   or `rose` items -- the built-in `catch fish` / `pick rose` actions
   spawn them.
5. The walkthrough types exactly the verbs the spec declares (custom
   action ACTION_NAMEs, non-canonical Exit directions, built-in verbs
   without invented synonyms). One walkthrough command per element.
6. For every location pair, exactly ONE direction is emitted (the
   engine auto-installs the reverse for canonicals + `enter X`/`exit X`
   + `climb up X`/`climb down X`). Declaring both sides creates a
   duplicate edge that bypasses any block on it.
7. No custom_action verb starts with a reserved engine head (drink,
   eat, give, light, attack, hit, take, get, drop, inventory, examine,
   say, quit, wait, or a cardinal direction). The built-in shadows it
   otherwise. (`look` is special-cased: only the bare `look`/`l` is
   reserved.)
8. No custom_action describes a rule the source does not actually
   describe. If you'd be inventing the action, drop it.

Your job: produce a single valid JSON object matching the GameSpec schema.
Do not wrap it in Markdown fences. Do not include any text outside the JSON.
"""


# A small few-shot example with synthesized content (not from any book).
# Shows: a multi-condition property_block, an escalating_commands NPC, a
# read_inscription_to_banish chain with `is_lit`, items at owner, and a
# composite win via `any_character_property`.
#
# The page format mirrors what ``codegen.extract._format_pages`` emits:
# one structured `location` block per room heading, each with a
# `description`, `interactions` (verb / response / rule), `exits` table,
# and any `designer_notes`. The structurer has already paired each
# verb header with its response and parsed every `> DIRECTION page N
# TARGET` row out of the exits table -- you no longer need to do that
# reconstruction.
FEW_SHOT_EXAMPLE = """\
Example input pages (synthetic, two pages):

[page 1]
  location: 'BRICK HUT'
    description: 'You are in a dim brick hut. A dusty workbench stands in the corner.'
    underlined_nouns: ['hammer', 'workbench', 'torch']
    interactions:
      - verb: 'EXAMINE HAMMER:'
        response: 'It is solid. Would make a good club.'
        underlined_nouns: ['hammer']
      - verb: 'EXAMINE WORKBENCH:'
        response: 'The workbench cannot be picked up.'
        underlined_nouns: ['workbench']
      - verb: 'LIGHT TORCH:'
        response: 'The torch glows brightly.'
        underlined_nouns: ['torch']
    exits:
      - direction: 'east' -> target: 'STONE BRIDGE' (page 2)

[page 2]
  location: 'STONE BRIDGE'
    description: 'A grim ogre stands in the middle of the bridge, blocking the way east. The far side leads to a ruined chapel.'
    underlined_nouns: ['ogre']
    interactions:
      - verb: 'EXAMINE OGRE:'
        response: 'She is hungry; she will not move until fed. She carries an axe.'
        rule: 'Each turn the ogre roars at you. If you are still on the bridge after two turns, she attacks you with her axe and you die.'
        underlined_nouns: ['axe']
      - verb: 'FEED FISH TO OGRE:'
        response: 'The ogre eats the fish and steps aside.'
    exits:
      - direction: 'east' -> target: 'RUINED CHAPEL' (page 2)
  location: 'RUINED CHAPEL'
    description: 'A pale wraith haunts the chapel. A silver bell hangs in the tower.'
    underlined_nouns: ['wraith', 'bell', 'mitre']
    interactions:
      - verb: 'READ SIGIL:'
        response: 'While the torch is lit, the sigil banishes the wraith.'
        rule: 'Each turn the wraith howls at you. After two turns it touches you with a cold hand and you die.'
        underlined_nouns: ['wraith', 'bell']
      - verb: 'RING BELL:'
        response: "If you are wearing the bishop's mitre, you become the new bishop."
        underlined_nouns: ['mitre']
    exits: []

Example output:

{
  "version": "1",
  "game_name": "Brick Hut Quest",
  "class_name": "BrickHutQuest",
  "source": {"pdf": "Example.pdf", "pages": [1, 2]},
  "start_at": "Brick Hut",
  "win_condition": {
    "kind": "any_character_property",
    "property": "is_bishop",
    "equals": true,
    "ok_message": "{name} is the new bishop!"
  },
  "locations": [
    {"name": "Brick Hut", "description": "You are in a dim brick hut. A dusty workbench stands in the corner.",
     "exits": [{"direction": "east", "to": "Stone Bridge", "travel_description": "You step onto the bridge."}]},
    {"name": "Stone Bridge", "description": "You are on a stone bridge over a chasm. An ogre stands in your way.",
     "exits": [{"direction": "east", "to": "Ruined Chapel", "travel_description": ""}]},
    {"name": "Ruined Chapel", "description": "A ruined chapel. A silver bell hangs in the bell tower.",
     "exits": []}
  ],
  "items": [
    {"name": "hammer", "description": "a heavy hammer", "examine_text": "Solid; would make a good club.",
     "at": {"location": "Brick Hut"}, "properties": {"is_weapon": true}, "command_hints": []},
    {"name": "workbench", "description": "a dusty workbench", "examine_text": "",
     "at": {"location": "Brick Hut"}, "properties": {"gettable": false}, "command_hints": []},
    {"name": "torch", "description": "an unlit torch", "examine_text": "",
     "at": {"location": "Brick Hut"}, "properties": {"flammable": true, "is_lit": false},
     "command_hints": ["light torch"]},
    {"name": "axe", "description": "an ogre's axe", "examine_text": "",
     "at": {"owner": "ogre"}, "properties": {"is_weapon": true}, "command_hints": []},
    {"name": "bell", "description": "a silver bell", "examine_text": "A sigil is carved on the bell.",
     "at": {"location": "Ruined Chapel"}, "properties": {"gettable": false, "flammable": false},
     "command_hints": ["read sigil", "ring bell"]},
    {"name": "mitre", "description": "a bishop's mitre", "examine_text": "",
     "at": {"location": "Ruined Chapel"}, "properties": {}, "command_hints": ["wear mitre"]}
  ],
  "characters": [
    {"name": "ogre", "description": "a grim ogre", "persona": "I guard the bridge. I am hungry.",
     "at": "Stone Bridge",
     "properties": {"is_hungry": true, "character_type": "ogre"},
     "inventory": ["axe"],
     "behavior": {
       "kind": "escalating_commands",
       "commands": ["roar {player}"],
       "fallback": "ogre attack {player} with axe",
       "guard": {"property": "is_hungry", "equals": true}
     }},
    {"name": "wraith", "description": "a pale wraith", "persona": "I haunt this chapel.",
     "at": "Ruined Chapel",
     "properties": {"is_undead": true, "is_banished": false},
     "inventory": [],
     "behavior": {
       "kind": "escalating_commands",
       "commands": ["howl {player}"],
       "fallback": "wraith touch {player}",
       "guard": {"property": "is_banished", "equals": false}
     }}
  ],
  "blocks": [
    {"id": "ogre_block", "template": "property_block", "name": "Ogre_Block",
     "at_location": "Stone Bridge", "direction": "east",
     "block_message": "A hungry ogre blocks the way.",
     "obstacle": {"kind": "character", "name": "ogre"},
     "conditions": [
       {"target": "obstacle", "property": "is_dead", "equals": false},
       {"target": "obstacle", "property": "is_unconscious", "equals": false},
       {"target": "obstacle", "property": "is_hungry", "equals": true}
     ]}
  ],
  "custom_actions": [
    {"id": "read_sigil", "template": "read_inscription_to_banish",
     "params": {"action_name": "read sigil", "inscribed_item": "bell",
                "target_character": "wraith", "required_property": "is_lit",
                "banished_property": "is_banished",
                "drop_target_inventory": true, "remove_target_from_scene": true}},
    {"id": "wear_mitre", "template": "wear_item",
     "params": {"item": "mitre", "required_actor_property": "character_type",
                "set_actor_property": "is_mitred"}},
    {"id": "ring_bell", "template": "sit_on_furniture",
     "params": {"furniture_item": "bell", "required_actor_property": "is_mitred",
                "set_actor_property": "is_bishop"}},
    {"id": "roar", "template": "npc_taunt",
     "params": {"verb": "roar", "template_string": "{actor.title} roars at {target}."}},
    {"id": "ogre_attack", "template": "npc_kill",
     "params": {"verb": "ogre attack", "template_string": "{actor.title} swings her axe at {target}.",
                "sets_target_property": "is_dead"}},
    {"id": "howl", "template": "npc_taunt",
     "params": {"verb": "howl", "template_string": "{actor.title} howls at {target}.",
                "requires_actor_property_falsy": "is_banished"}},
    {"id": "wraith_touch", "template": "npc_kill",
     "params": {"verb": "wraith touch", "template_string": "{actor.title} touches {target} with a cold hand.",
                "sets_target_property": "is_dead",
                "requires_actor_property_falsy": "is_banished"}}
  ],
  "player": {
    "name": "The player", "description": "An adventurer.",
    "persona": "I am on a quest.", "properties": {"character_type": "human"},
    "inventory": []
  },
  "walkthrough": {
    "commands": [
      "get hammer", "get torch", "light torch",
      "east", "feed ogre",
      "east", "get bell", "read sigil",
      "get mitre", "wear mitre", "ring bell"
    ],
    "expects_win": true
  }
}

Notice in the example: the ogre and wraith have escalating behaviors, not
"none". Every verb in `commands`/`fallback` is registered. The bell is
NOT lit directly; the torch is lit, and the bell-sigil reading requires
`is_lit` on the torch (in a real game you'd light the torch in the player's
inventory; here, treating the bell itself as `is_lit` would also work but
the chain stays explicit). The win condition is a property on the player
(`is_bishop`), set by the FINAL action.

Notice also: each location pair has exactly ONE exit emitted. Brick Hut
has `east -> Stone Bridge`; Stone Bridge does NOT redundantly emit `west
-> Brick Hut`, because the engine auto-installs it. Likewise the ogre's
axe lives in `items[]` with `"at": {"owner": "ogre"}` because her
fallback is `ogre attack {player} with axe` -- a named weapon in a
fallback MUST exist as a real item.
"""


SCHEMA_HINT = """\
Schema (abbreviated; see GameSpec for the full type):

{
  "version": "1",
  "game_name": str,
  "class_name": str,                  # CamelCase, no spaces
  "source": {"pdf": str, "pages": [int, int]},
  "start_at": str,                    # one of the location names
  "win_condition": {
    "kind": "any_character_property" | "player_at_location" |
            "player_has_item" | "all_of" | "any_of" | "flag",
    # kind-specific fields:
    "property": str, "equals": bool|str,   # any_character_property
    "location": str,                       # player_at_location
    "item": str,                           # player_has_item
    "children": [WinCondition],            # all_of / any_of
    "name": str,                           # flag
    "ok_message": str
  },
  "locations": [
    {"name": str, "description": str,
     "properties": {str: bool|str|int},
     "exits": [{"direction": str, "to": str, "travel_description": str,
                # Optional: for non-canonical verb pairs ("enter moat" /
                # "exit moat"). Suppresses the canonical auto-reverse.
                "reverse_direction": str | null,
                "reverse_travel_description": str}]}
  ],
  "items": [
    {"name": str, "description": str, "examine_text": str,
     "at": {"location": str}  OR  {"owner": <character name>},
     "properties": {str: bool|str|int}, "command_hints": [str],
     # Optional: text shown by the engine's `read` action. Use for signs,
     # scrolls, and inscriptions without side effects.
     "read_text": str,
     # Optional: declarative reactions to `use <tool> on <this item>`.
     # Use INSTEAD of a custom action for "apply X to Y" puzzles.
     "use_responses": [
       {"tool": <item name>,
        "response_text": str,
        "requires_tool_properties": {str: bool|str|int},
        "requires_target_properties": {str: bool|str|int},
        "sets_tool_properties": {str: bool|str|int},
        "sets_target_properties": {str: bool|str|int},
        "consumes_tool": bool}
     ]}
  ],
  "characters": [
    {"name": str, "description": str, "persona": str, "at": str,
     "properties": {str: bool|str|int}, "inventory": [<item names>],
     "behavior": {"kind": "none"} |
                 {"kind": "escalating_commands",
                  "commands": [str], "fallback": str,
                  "guard": {"property": str, "equals": bool|str}},
     # Optional: response to `talk to <character>` and topic dictionary
     # for `ask <character> about <topic>`.
     "greeting": str,
     "dialogue": {<topic>: <response>, ...},
     # Optional: declarative reactions to receiving items via `give`.
     # Use INSTEAD of a custom action with a `give X to Y` verb.
     "give_responses": [
       {"item": <item name>,
        "response_text": str,
        "requires_recipient_properties": {str: bool|str|int},
        "sets_recipient_properties": {str: bool|str|int},
        "sets_giver_properties": {str: bool|str|int}}
     ],
     # Optional: like `use_responses` on items, but with this character
     # as the target (e.g. `use candle on ghost`).
     "use_responses": [...same shape as item use_responses...]}
  ],
  "blocks": [
    {"id": str, "template": "property_block" | "darkness_block",
     "name": str, "at_location": str, "direction": str,
     "block_message": str,
     "obstacle": {"kind": "character"|"item", "name": str},  // property_block
     "conditions": [{"target": "obstacle"|"location"|"actor",
                     "property": str, "equals": bool|str}],
     "unblocked_if_inventory_has_property": str  // darkness_block
    }
  ],
  "custom_actions": [
    {"id": str, "template": <one of the templates below>, "params": {...}}
  ],
  "player": {"name": str, "description": str, "persona": str,
             "properties": {str: bool|str|int},
             "inventory": [{"name": str, "description": str, "examine_text": str,
                            "properties": {...}, "command_hints": [str]}]},
  "walkthrough": {                       # REQUIRED -- self-test sequence
    "commands": [str],                   # commands in order; wins the game
    "expects_win": bool                  # default true
  }
}

Action templates (and required params):
  unlock_with_key:
    lock_item, key_item, unlocked_property
      (unlocked_property is the boolean that is set to false when unlocked,
       e.g. "is_locked"; the door starts with is_locked: true.)

  read_inscription_to_banish:
    action_name (the verb phrase the player types, e.g. "read runes" --
       NOT "light candle"),
    inscribed_item (the item the runes are on, e.g. "candle"),
    target_character (the character to banish, e.g. "ghost"),
    required_property (the boolean that must be true on the inscribed item
       for the reading to work -- typically "is_lit"),
    banished_property (the boolean set true on the target, typically
       "is_banished"),
    drop_target_inventory (default true), remove_target_from_scene (default true)

  propose_marriage:
    required_emotional_state (string; both parties must have this
       emotional_state, e.g. "happy"),
    set_property_on_pair (e.g. "is_married"),
    royalty_property (optional; e.g. "is_royal")

  wear_item:
    item, required_actor_property (a property the actor must have to
       be permitted to wear it, e.g. "is_royal"),
    set_actor_property (boolean set on the actor when worn, e.g. "is_crowned")

  sit_on_furniture:
    furniture_item, required_actor_property (e.g. "is_crowned"),
    set_actor_property (e.g. "is_reigning")

  npc_taunt:
    verb (the action name, must match the verb used in the NPC's behavior),
    template_string (with {actor}, {actor.title}, {target},
       {target.title} placeholders),
    requires_actor_property_falsy (optional; e.g. "is_banished")

  npc_kill:
    verb, template_string, sets_target_property (typically "is_dead"),
    requires_actor_property_falsy (optional)

  flavor_response:
    verb (ACTION_NAME the player types, e.g. "shake machine"),
    template_string (the message to print on success; {actor}/{actor.title}
       placeholders are supported but no state-change happens),
    requires_in_scope (optional; an item name that must be in the actor's
       scope -- typically the noun the verb targets),
    at_location (optional; restricts the verb to one location)

  transform_item:
    verb, item, template_string, sets_properties (dict of property -> value
       applied to the item on success; {actor}/{actor.title}/{item}/{item.title}
       placeholders supported in template_string),
    requires_in_inventory (optional, default false),
    requires_properties (optional dict of property -> expected value)
"""


USER_PROMPT_TEMPLATE = """\
Convert the following pages to a GameSpec for the game "{game_name}".

{schema}

{example}

Pages:

{pages}

Return ONLY the JSON object. No prose, no Markdown fences.
Before returning, mentally walk the validation checklist in the system
prompt and fix any item that fails.
"""


def build_user_prompt(
    game_name: str, pages_text: str, solution_outline: str | None = None
) -> str:
    outline_block = ""
    if solution_outline:
        outline_block = (
            "\nSOLUTION OUTLINE (from the pre-pass you just produced -- the "
            "spec MUST support every step):\n\n"
            f"{solution_outline}\n"
        )
    return (
        USER_PROMPT_TEMPLATE.format(
            game_name=game_name,
            schema=SCHEMA_HINT,
            example=FEW_SHOT_EXAMPLE,
            pages=pages_text,
        )
        + outline_block
    )


# ----------------------------------------------------------------------
# Solution-outline pre-pass
# ----------------------------------------------------------------------
#
# A small first LLM call that asks the model to reason about a winning
# path through the pages BEFORE it writes the spec. The output is fed
# back into the main extraction prompt as a constraint -- "the spec
# MUST support every step you just listed."
#
# Why: the model otherwise extracts the world model first and then
# tries to backfill the solution. That's where pieces drop ("you can
# climb the tree" becomes flavor instead of an exit; the guard has no
# weapon because the model forgot the attack rule needs one). Forcing
# the model to commit to a path first surfaces the missing pieces it
# would otherwise leave out.

SOLUTION_OUTLINE_SYSTEM_PROMPT = """\
You read Parsely adventure book pages and write a SHORT solution
outline: the sequence of items, locations, characters, and verbs the
player uses to win.

Output format (markdown):
  ## Solution outline for <game name>

  ### Win condition
  <one sentence: what state the player must reach to win>

  ### Required items
  - <item name> (from <where it starts> -- used to <what for>)
  - ...

  ### NPCs the player interacts with
  - <name> (encounter at <location>; resolved by <verb / give X / etc.>)
  - ...

  ### Step-by-step winning sequence
  1. <command in plain English> -> <new world state>
  2. ...

Rules:
  * Every step MUST be a single player command (movement, get/give,
    custom verb, etc.). Multi-step instructions ("then go fight the
    troll") are not allowed; split them.
  * If a location is reached by a non-canonical verb (climb tree, jump
    off cliff, crawl through duct), name that verb in the step.
  * If an NPC must be defeated/fed/satisfied first, list the verb the
    source rules describe ("give fish to troll", not "feed troll").
  * If the win path requires multiple items (sword + key + crown), list
    each AND where the player gets it.
  * Do NOT invent items, characters, or verbs the rules don't mention.

Return only the markdown outline. No prose before or after.
"""


def build_solution_outline_user_prompt(game_name: str, pages_text: str) -> str:
    return (
        f"Game: {game_name!r}\n\n"
        f"Pages:\n\n{pages_text}\n\n"
        "Write the solution outline."
    )
