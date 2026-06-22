# Parsely games — common feature outline

A map of the mechanics the 12 games in `Parsely_r31_final.pdf` actually use, so
you know what the engine has to support before porting any of them. Derived by
running `pdf_ingest` + `pdf_structure` over every game's page range and counting
the cyan verb headers (`EXAMINE LAMP:`, `USE WAND ON OOZE:`, …) — those headers
*are* the parser commands each game expects.

The 12 games (TOC ranges): Action Castle (15–28), Action Castle II (29–46),
Action Castle III (47–74), Blackboard Jungle (75–84), Dangertown Beatdown
(85–115), Flaming Goat (116–118), Jungle Adventure (119–138), Pumpkin Town
(139–166), Six-Gun Showdown (167–192), Space Station (193–212), Spooky Manor
(213–240), Z-Ward (241–269).

Counts below are interaction headers across all games; "N/12 games" is how many
games use that verb at all. Engine status maps each feature to
`text_adventure_games/actions/` (and the codegen `ACTION_TEMPLATES`).

---

## Tier 1 — Universal (every game, build first)

These appear in essentially every game. A port is dead in the water without them.

| Feature | Command shape | Count / spread | Engine status |
|---|---|---|---|
| **Movement** | `GO <dir>`, `ENTER <place>`, `GO OUT/UP/DOWN` | 21× `go` (11/12), 30× `enter` (8/12) | ✅ `locations.py` (`GO`), exits table → connections |
| **Examine** | `EXAMINE <noun>` | 349× (12/12) | ✅ `things.py` (`EXAMINE`) — by far the most common verb |
| **Take / drop** | `TAKE <item>`, `GET <item>`, `DROP <item>` | 26× `take` + 6× `get` (8/12), 2× `drop` | ✅ `things.py` (`GET`, `DROP`) |
| **Inventory** | `INVENTORY` / `I` | implicit, every game | ✅ `things.py` (`INVENTORY`) |
| **Give to NPC** | `GIVE <item> TO <npc>` | 26× (10/12) | ✅ `things.py` (`GIVE`) |
| **Talk / ask NPC** | `TALK TO <npc>`, `ASK <npc> FOR/ABOUT <topic>` | 27× `talk` + 27× `ask` | ✅ `talk.py` (`TALK`), dialog topics |
| **Use X on Y** | `USE <item> ON <target>` | 16× (8/12) | ✅ `use.py` (`use_item_on(...)` factory) |

**The "use X on Y" pattern is the workhorse two-object interaction.** The engine
has no single generic `USE` verb (the target and effect differ every time), so
`actions.use_item_on(...)` is a factory that builds a configured `Action` per
interaction: it checks the actor holds X and Y is present, runs an optional
`requires` gate, then applies an `effect` callback (+ optional `consume` /
`award` / narration). The same factory spells the siblings via `verb=` /
`preposition=`: `HIT … WITH`, `KILL … WITH`, `THROW … AT`, `POUR … ON`,
`SHOW … TO`. Replaces the hand-written one-class-per-interaction boilerplate in
the Action Castle ports.

---

## Tier 2 — Common (most games, share one implementation)

| Feature | Command shape | Count / spread | Engine status |
|---|---|---|---|
| **Wear / take off** | `WEAR <item>`, `TAKE OFF <item>` | 11× `wear` (6/12) | ✅ `equipment.py` (`WEAR`, `TAKE_OFF`), template `wear_item` |
| **Open / close** | `OPEN <thing>`, `CLOSE <thing>` | 9× `open` (7/12) | ✅ `things.py` (`OPEN`, `CLOSE`) |
| **Unlock with key** | `UNLOCK <door> WITH <key>`, `USE KEY ON DOOR` | — | ✅ `things.py` (`UNLOCK_DOOR`), template `unlock_with_key` |
| **Read** | `READ <sign/book>` | 8× `read` (7/12) | ✅ `investigate.py` (`Read` + `read_text` property) |
| **Search** | `SEARCH <container/place>` | 10× `search` (5/12) | ✅ `investigate.py` (`Search` + `is_hidden` reveal) |
| **Eat / drink** | `EAT <food>`, `DRINK <potion>` | 6× `eat` + 10× `drink` | ✅ `consume.py` (`EAT`, `DRINK`) |
| **Light source** | `LIGHT <lamp/torch>` + dark rooms | 5× `light` | ✅ `consume.py` (`LIGHT`) + `blocks.Darkness` |
| **Combat (simple)** | `ATTACK/HIT/KILL <npc> [WITH <weapon>]` | 4× attack, 5× hit, 2× kill, 6× shoot | ✅ `fight.py` (`ATTACK`); weapon via `WIELD` |
| **Say password** | `SAY <word>` | 15× `say` (4/12) | ✅ `talk.py` (`SAY`) — gates exits/effects on a spoken keyword |
| **Follow NPC** | `ASK <npc> TO FOLLOW`, `<npc> follows` | 3× `ask … to follow` | ✅ `talk.py` (`FOLLOW`/`UNFOLLOW`), `Character.following` |

---

## Tier 3 — Genre / game-specific (build only for the game that needs it)

Concentrated in one or two games — don't generalize these prematurely.

- **RPG leveling / stats** — `LEVEL UP`, XP-driven combat. 11× `level`, all in
  **Dangertown Beatdown** (a beat-'em-up). Needs a stat/XP system the engine
  lacks today.
- **Gambling** — `WAGER <amount>`, `PLAY <game>`. `wager` (Six-Gun Showdown),
  5× `play`. Needs money + random/deterministic outcome resolution.
- **Gunfights** — `SHOOT <target>`, `DRAW`. 6× `shoot` (Six-Gun Showdown).
  Timing/initiative-flavored combat.
- **Vehicles / driving** — `PARK`, `GET ON MOTORCYCLE`, `SET DIAL TO LOW`.
  `park` (5×, 1 game), `set … to`.
- **Law enforcement** — `ARREST <npc>`, `ORDER <npc> TO <verb>`. 2× arrest,
  2× `order … to` (Space Station: ordering robots/NPCs).
- **Ringing / knocking / pushing / pulling** — `RING BELL`, `KNOCK ON DOOR`,
  `PUSH`, `PULL`, `MOVE`, `TURN`, `SHAKE`, `DIG`, `MINE … WITH PICKAXE`,
  `FILL`, `POUR`, `STICK GUM ON HOOK`. Each is a one-off custom action.
- **Marriage / win triggers** — `MARRY <npc>`. ✅ template `propose_marriage`
  (Action Castle ending).

---

## Cross-cutting systems (not verbs — structural features every port needs)

These don't show up as verb headers but the PDFs depend on them, and the codegen
README flags them as exactly what the pipeline *dropped* and hand-porting must
honor:

1. ✅ **Scoring** — point tables (Action Castle II/III award points per
   milestone). `Game.award(key, points, msg)` is now a base-engine primitive
   (idempotent per key); `Game.score` / `Game.max_score` ship with every game.
2. ✅ **Multiple endings / epilogues** — numbered outcome sections
   (`1. VICTORY!`, `2. THE HITCHHIKER`). Win *condition* stays in `is_won()`;
   `Game.announce_ending(text, show_score=)` factors the print-once + score line.
3. ✅ **Prescribed death paths** — specific actions that kill the player.
   `Game.end_in_death(message)` narrates and ends the game; `is_game_over()`
   also covers `is_dead` / lethal `Block`.
4. ✅ **Posed yes/no prompts** — "Are you sure you want to go home?" Engine:
   `Prompt` / `pose_prompt` (issue #110).
5. ✅ **Gated / blocked exits** — exits open only after a condition
   (`blocks/`, `property_block`).
6. ✅ **Darkness** — rooms unreadable without a lit light source (`blocks.Darkness`).
7. ✅ **Crafting / recipes** — combine items into a result. Engine: `Recipe`,
   `CRAFT` (`things.py`).
8. ✅ **Item transformation** — an item becomes another after a `USE`. Express
   it in a `use_item_on(..., effect=)` closure (set a property, swap the item).
9. ✅ **NPC dialog topics & taunts** — `ASK … ABOUT …`, NPC barks (`talk.py`).

---

## Build order recommendation

1. **Tier 1** is mandatory and now entirely in the engine — the **`USE X ON Y`**
   two-object pattern (and its siblings `HIT/THROW/SHOW/POUR … prep …`) is built
   as `actions.use_item_on(...)` (see `actions/use.py`, `tests/test_use_item_on.py`).
2. **Tier 2** is now entirely in the engine — the former soft spots **`READ`**
   (prints an item's `read_text`) and **`SEARCH`** (reveals `is_hidden` items)
   are built as `actions.Read` / `actions.Search` (see `actions/investigate.py`,
   `tests/test_read_search.py`).
3. **Cross-cutting systems** now all have engine primitives — scoring
   (`Game.award`), death (`Game.end_in_death`), endings (`Game.announce_ending`),
   prompts (`Prompt`), blocks/darkness, recipes. Wiring the *specific* point
   table and win conditions is still per-game; mirror
   `adventures/action_castle_2.py` / `action_castle_3.py`.
4. **Tier 3** only when you port that specific game.
