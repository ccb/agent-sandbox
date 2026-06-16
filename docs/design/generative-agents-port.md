# Generative Agents ("Smallville") — characters & settings reference

A survey of the world and cast defined in Stanford's **Generative Agents** repo
([joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents),
the code behind [*Generative Agents: Interactive Simulacra of Human Behavior*](https://arxiv.org/abs/2304.03442)),
written as **step one of porting that simulation onto our `agent-sandbox` engine**.

The goal here is *understanding*, not implementation: catalog exactly what the
upstream repo hands us — the map, the places, the props, the people — so we can
later map each piece onto our `Location` / `Item` / `Character` model. A
porting-notes section at the end records the rough correspondence.

> The upstream clone lives under `external/generative_agents/` (git-ignored — see
> `.gitignore`). All file paths below are relative to that clone.

---

## 1. The big picture

Generative Agents is **not** a text adventure. It's a 2-D tile world ("Smallville",
internally `the_ville`) rendered by a Phaser/Django frontend, driven by a Python
backend (`reverie`) where each agent is an LLM-backed *persona*. Agents perceive
nearby tiles, retrieve memories, plan a day, act it out minute-by-minute, converse
when they collide, and reflect. There is no win condition and no player-issued
commands in the adventure-game sense — it's an open-ended social simulation.

Two halves:

| Half | Path | Role |
|------|------|------|
| **Environment server** | `environment/frontend_server/` (Django) | Owns the map, tiles, sprites; renders + replays. |
| **Simulation server** | `reverie/backend_server/` (`reverie.py`) | Runs the agents' cognition and writes movements back. |

Time: `sec_per_step = 10` (one game step = 10 simulated seconds). The shipped
simulations start **February 13, 2023, 00:00:00**, with the narrative climax being
**Isabella's Valentine's Day party at Hobbs Cafe on Feb 14, 5–7pm** — the event the
3-agent demo is built around.

---

## 2. The world: `the_ville`

Defined under
`environment/frontend_server/static_dirs/assets/the_ville/matrix/`. The map is a
**140 × 100 grid of 32px tiles** (`maze_meta_info.json`).

The world is a strict **4-level containment hierarchy**, which is the part most
relevant to a port:

```
World  →  Sector  →  Arena  →  Game Object
"the Ville"   "Hobbs Cafe"  "cafe"   "behind the cafe counter"
```

- **World** — one: `the Ville` (`world_blocks.csv`).
- **Sector** — a building or named outdoor area (a "place you travel to").
- **Arena** — a room/zone inside a sector (where activity happens).
- **Game object** — an interactable prop inside an arena (the leaves of the tree).

The map itself is encoded as parallel CSV "layers" in `matrix/maze/`
(`sector_maze.csv`, `arena_maze.csv`, `game_object_maze.csv`, `collision_maze.csv`,
`spawning_location_maze.csv`) — each a 140×100 grid of block IDs. The human-readable
ID→label mapping is in `matrix/special_blocks/`. Tile `32125` is the collision
(wall) block.

### 2.1 Sectors (19)

From `special_blocks/sector_blocks.csv`:

**Public / commercial**
- **Hobbs Cafe** — Isabella's cafe; the social hub & party venue.
- **The Rose and Crown Pub** — Arthur Burton's bar.
- **Harvey Oak Supply Store** — Carmen Ortiz's shop.
- **The Willows Market and Pharmacy** — run by Tom Moreno (grocery) & John Lin (pharmacy).
- **Oak Hill College** — classroom, library, hallway.
- **Johnson Park** — the town's green space.

**Residences**
- **The artist's co-living space** — shared by Latoya, Rajiv, Abigail, Francisco, Hailey.
- **Dorm for Oak Hill College** — Klaus, Maria, Ayesha, Wolfgang.
- **Lin family's house** — John, Mei, Eddy Lin.
- **Moreno family's house** — Tom & Jane Moreno.
- **Moore family's house** — Sam & Jennifer Moore.
- **Tamara Taylor and Carmen Ortiz's house** — housemates.
- Solo apartments/houses: **Arthur Burton's**, **Ryan Park's**, **Isabella Rodriguez's**,
  **Giorgio Rossi's**, **Carlos Gomez's** (apartments); **Adam Smith's**,
  **Yuriko Yamamoto's** (houses).

### 2.2 Arenas (rooms)

From `special_blocks/arena_blocks.csv` (~62 arenas). Pattern: residences have
bedrooms + bathroom + (often) common room / kitchen / garden; commercial sectors
have their working floor. Highlights:

- **Hobbs Cafe** → `cafe`
- **The Rose and Crown Pub** → `pub`
- **Oak Hill College** → `classroom`, `library`, `hallway`
- **Johnson Park** → `park`
- **Harvey Oak Supply Store** → `supply store`
- **The Willows Market and Pharmacy** → `store`
- **Dorm** → one room per student (Klaus / Maria / Ayesha / Wolfgang) + man's/woman's
  bathroom, common room, kitchen, garden
- **Artist's co-living space** → one room + private bathroom per artist, plus common
  room and kitchen

### 2.3 Game objects (interactables)

From `special_blocks/game_object_blocks.csv` — declared with sector `<all>`, i.e.
these object *types* may appear in any arena. The full set (~46):

`bed, desk, closet, shelf, easel, bathroom sink, shower, toilet, kitchen sink,
refrigerator, toaster, cooking area, common room table, common room sofa, guitar,
microphone, bar customer seating, behind the bar counter, behind the cafe counter,
cafe customer seating, piano, blackboard, game console, computer desk, computer,
library sofa, bookshelf, library table, classroom student seating, classroom podium,
behind the pharmacy counter, behind the grocery counter, pharmacy store shelf,
grocery store shelf, pharmacy store counter, grocery store counter, supply store
product shelf, behind the supply store counter, supply store counter, dorm garden,
house garden, garden chair, park garden, harp, lifting weight, pool table`

Objects are where actions land: an agent's activity resolves to a target object
(e.g. *"cooking breakfast @ the Ville:Lin family's house:kitchen:stove"*) and the
object carries its own event/state ("stove is being used to cook breakfast").

### 2.4 Spawning locations

`special_blocks/spawning_location_blocks.csv` defines `sp-A` / `sp-B` start tiles per
residence — where each agent is first placed.

---

## 3. The cast

Two shipped base simulations (in `environment/frontend_server/storage/`):

| Base sim | Agents |
|----------|--------|
| `base_the_ville_isabella_maria_klaus` | 3: Isabella, Maria, Klaus |
| `base_the_ville_n25` | 25 (the full town) |

### 3.1 What defines a character

Each persona is a folder under `<sim>/personas/<Full Name>/bootstrap_memory/` with
three memory structures (see `reverie/backend_server/persona/`):

- **`scratch.json`** — identity + short-term state. The character "sheet". Key fields:
  - `name`, `first_name`, `last_name`, `age`
  - `innate` — fixed personality traits (e.g. *"friendly, outgoing, hospitable"*)
  - `learned` — background / self-concept (a paragraph)
  - `currently` — what they're up to right now (drives planning)
  - `lifestyle` — sleep/wake/meal rhythm
  - `living_area` — home address as `world:sector:arena`
  - `daily_plan_req` — a hard daily constraint (e.g. shopkeeper hours), often blank
  - cognition knobs: `vision_r` (perception radius, 8), `att_bandwidth` (8),
    `retention` (8), plus retrieval weights (`recency_w`/`relevance_w`/`importance_w`,
    `recency_decay = 0.995`) and reflection thresholds.
- **`spatial_memory.json`** — a *partial* world tree: only the places/objects **this
  agent knows about**. (e.g. John Lin's tree covers his house, the shops, the park,
  the pub, the cafe, the college hallway — not other people's bedrooms.)
- **`associative_memory/`** — the **memory stream**: `nodes.json` (events / thoughts /
  chats), `kw_strength.json`, `embeddings.json`. **Ships empty** (0 nodes) — memories
  accrue during simulation, or are pre-seeded from a history file (§3.3).

### 3.2 The 25 residents

Personality (`innate`) and `learned`/`currently` are abbreviated below; full text in
each `scratch.json`.

| Name | Age | Innate traits | Role / hook | Home (sector) |
|------|----:|---------------|-------------|---------------|
| **Isabella Rodriguez** | 34 | friendly, outgoing, hospitable | Owns **Hobbs Cafe**; hosting the Valentine's party | Isabella's apartment |
| **Maria Lopez** | 21 | energetic, enthusiastic, inquisitive | Physics student + Twitch streamer; secret crush on Klaus | Oak Hill Dorm |
| **Klaus Mueller** | 20 | kind, inquisitive, passionate | Sociology student writing on gentrification; crush on Maria | Oak Hill Dorm |
| **John Lin** | 45 | patient, kind, organized | Pharmacist at Willows Market & Pharmacy; election-curious | Lin family's house |
| **Mei Lin** | 44 | nurturing, kind, patient | College professor; John's wife, Eddy's mother | Lin family's house |
| **Eddy Lin** | 19 | curious, analytical, musical | Music-theory/composition student | Lin family's house |
| **Tom Moreno** | 52 | rude, aggressive, energetic | Grocery keeper at Willows Market; **dislikes Sam Moore** | Moreno family's house |
| **Jane Moreno** | 46 | friendly, helpful, organized | Homemaker; Tom's wife | Moreno family's house |
| **Sam Moore** | 65 | wise, resourceful, humorous | Retired navy officer; **running for mayor** | Moore family's house |
| **Jennifer Moore** | 68 | wise, experienced, warm | Watercolor painter; Sam's wife of 40 yrs | Moore family's house |
| **Arthur Burton** | 42 | friendly, outgoing, generous | Owns **The Rose and Crown Pub** | Arthur's apartment |
| **Carmen Ortiz** | 33 | friendly, outgoing, helpful | Keeper of **Harvey Oak Supply Store** | shared w/ Tamara |
| **Tamara Taylor** | 30 | imaginative, patient, kind | Children's-book author; Carmen's housemate | shared w/ Carmen |
| **Giorgio Rossi** | 41 | analytical, logical, eccentric | Mathematician; election gossip | Giorgio's apartment |
| **Carlos Gomez** | 32 | loud, rude, toxic | Poet | Carlos's apartment |
| **Ryan Park** | 29 | analytical, pragmatic, driven | Software engineer | Ryan's apartment |
| **Adam Smith** | 36 | thoughtful, reflective, intellectual | Philosopher writing a book; election-curious | Adam's house |
| **Yuriko Yamamoto** | 28 | organized, reliable, detail-oriented | Tax lawyer; election-curious | Yuriko's house |
| **Latoya Williams** | 25 | organized, logical, attentive | Digital photographer; election gossip | artist's co-living |
| **Rajiv Patel** | 27 | patient, reliable, cheerful | Painter prepping a solo show | artist's co-living |
| **Abigail Chen** | 25 | open-minded, curious, determined | Digital artist / animator | artist's co-living |
| **Francisco Lopez** | 23 | outgoing, friendly, honest | Actor / comedian | artist's co-living |
| **Hailey Johnson** | 30 | imaginative, energetic, resourceful | Writer | artist's co-living |
| **Ayesha Khan** | 20 | curious, determined, independent | Lit student; Shakespeare thesis | Oak Hill Dorm |
| **Wolfgang Schulz** | 21 | hardworking, passionate, dedicated | Chemistry student-athlete | Oak Hill Dorm |

**Recurring narrative threads** baked into `currently`:
- The **Valentine's party** (Isabella → everyone).
- The **mayoral election**: Sam Moore is running; John, Giorgio, Adam, Yuriko, Latoya
  gossip about it; Tom dislikes Sam.
- A **Maria↔Klaus** mutual crush (in the n3 history file).

### 3.3 Pre-seeded relationships (history files)

`static_dirs/assets/the_ville/agent_history_init_n3.csv` and `..._n25.csv` are
`Name,Whisper` CSVs of semicolon-separated memory records loaded into the memory
stream at startup (`call -- load history ...`). They establish relationships and
intentions the bare `scratch.json` doesn't — e.g. Maria's secret crush on Klaus,
their 2-year friendship, Isabella's party excitement and her friendship with Maria.
**These are where social structure actually lives** at t=0.

---

## 4. How an agent thinks (for context)

Each `Persona` (`reverie/backend_server/persona/persona.py`) runs a cognitive loop of
modules in `cognitive_modules/`:

**perceive → retrieve → plan → execute → reflect** (+ **converse** on agent-agent
contact).

- **perceive** — see objects/events within `vision_r` tiles, store as memory nodes.
- **retrieve** — pull relevant memories by recency × relevance × importance.
- **plan** — generate a daily plan, decompose to hourly then minute-level actions.
- **execute** — turn the chosen action into a movement/target tile + object event.
- **reflect** — periodically synthesize higher-level thoughts from recent memories.

This is a richer cognitive stack than our current ReAct loop (`npc.py`), but the seams
line up (see below).

---

## 5. Porting notes → `agent-sandbox`

Rough correspondence to our engine (`text_adventure_games/`). This is a sketch to
revisit, not a committed design.

| Generative Agents | agent-sandbox equivalent | Notes |
|-------------------|--------------------------|-------|
| Sector | `Location` | Top-level travelable place. |
| Arena (room) | `Location` (nested/connected) | Our model is a flat connection graph, not a containment tree — sectors+arenas likely both become `Location`s wired by connections. |
| Game object | `Item` (often fixed/`gettable=False`) | Counters, beds, pianos = non-portable interactables. |
| Persona `scratch` (innate/learned/currently/lifestyle) | `Character` + agent persona prompt | Maps cleanly onto our `Agent` decision seam. |
| `spatial_memory` (known-places tree) | per-character knowledge layer (issue #45) | We already have a belief/knowledge layer — a natural home for partial world knowledge. |
| `associative_memory` (memory stream) | **Phase 2 memory** (not yet built) | The biggest gap; ours is deferred. |
| perceive→retrieve→plan→execute→reflect | `Agent.decide()` / ReAct loop (`npc.py`) | Our loop is shallower (Observe→Decide→Act→Reflect, no long-term memory yet). |
| Tile grid + collision maze | (no equivalent) | We're text/graph-based; the 140×100 pixel map doesn't port — only the place/object hierarchy and the cast do. |
| 10s/step continuous time | turn-based or `turn_mode="simultaneous"` | Their minute-level scheduling ≠ our discrete turns; needs a time mapping (cf. `clock.py`, issue #7). |

**Key takeaways for the port:**
1. The **valuable, portable content** is the *world hierarchy* (19 sectors, ~62
   arenas, ~46 object types) and the *25 personas* (traits + relationships) — all
   plain JSON/CSV, engine-agnostic.
2. The **pixel map, sprites, pathfinding, and Django frontend are not portable** and
   not needed — our world is a graph of `Location`s.
3. The **memory stream is the deepest dependency** and aligns with our deferred
   Phase 2 work; an initial port can run on `scratch`-style identity + the existing
   knowledge layer without the full associative memory.
4. There is **no win condition** — porting this means embracing open-ended
   simulation, not a goal-driven `is_won()` game. The Valentine's party / mayoral
   election are emergent narrative seeds, not scripted objectives.

---

## 6. Source map (where to look in the clone)

| What | Path (under `external/generative_agents/`) |
|------|---------------------------------------------|
| World metadata (size, tile) | `environment/.../the_ville/matrix/maze_meta_info.json` |
| Sector / arena / object labels | `environment/.../the_ville/matrix/special_blocks/*.csv` |
| Map tile layers | `environment/.../the_ville/matrix/maze/*.csv` |
| Base simulations | `environment/frontend_server/storage/base_the_ville_*` |
| Per-agent identity & memory | `.../storage/<sim>/personas/<Name>/bootstrap_memory/` |
| Pre-seeded relationships | `environment/.../the_ville/agent_history_init_n{3,25}.csv` |
| Agent cognition | `reverie/backend_server/persona/` |
| Sim driver / loop | `reverie/backend_server/reverie.py` |
