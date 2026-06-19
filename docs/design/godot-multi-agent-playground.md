# The 2025 Godot Multi-Agent Playground — project & asset survey

A scouting write-up of last summer's (2025) **Multi-Agent Playground**: a
Python backend + **Godot** frontend in which LLM-driven agents move around a
house and interact with objects, visualized as a 2-D pixel-art game. This is the
direct ancestor of the **Godot 2-D bridge** on our roadmap, so the goal here is
*understanding and salvage*: what the project does, how each part is built, the
full feature set, and — most importantly for reuse — **where every art asset
comes from and how to get it**.

> Addresses issue #97. The repo URL in that issue (`okkirisss/multi_agent_playground`)
> has moved; the current, more complete repo is
> **[`MoodyMarshmallow/multi_agent_playground`](https://github.com/MoodyMarshmallow/multi_agent_playground)**.
> A local clone lives under `external/multi_agent_playground/` (git-ignored — see
> `.gitignore`). **All file paths below are relative to that clone** unless noted.

---

## 1. The big picture

The Multi-Agent Playground is **two programs that talk over HTTP**:

| Half | Path | Stack | Role |
|------|------|-------|------|
| **Backend (the brain)** | `backend/` | FastAPI · [Kani](https://github.com/zhudotexe/kani) · OpenAI | Runs the world simulation and the LLM agents; decides what each agent does. |
| **Frontend (the eyes)** | `frontend/Godot-Multi-Agent-Playground/` | Godot 4.4 (GDScript) | Draws the house, animates the agents walking and interacting; a thin visualization client. |

The backend owns all the *logic* — it's a text-adventure engine where the
"players" are LLM agents. The Godot frontend owns all the *pixels* — it polls
the backend for "what did each agent just do?" and plays that out as sprites
moving around a tile-mapped house. You can run the backend completely on its own
(it's a normal web API); the frontend is optional eye-candy on top.

```
 ┌─────────────────────────┐         HTTP (polling)          ┌──────────────────────────┐
 │   Python backend        │  ◀───────────────────────────  │   Godot frontend          │
 │   FastAPI + Kani + LLM  │   GET /agent_act/next  ──────▶  │   sprites + tilemap house │
 │   text-adventure world  │   GET /world_state, ...         │   HTTP/Action/Agent mgrs  │
 └─────────────────────────┘                                 └──────────────────────────┘
```

**Provenance.** MIT-licensed (`LICENSE`, "Copyright (c) 2025 Milo Shan"). Top
GitHub contributors are `MoodyMarshmallow`, `QuakerLives`, `mhedlund7`,
`okkirisss`, `lilyniu88` (**Lily Niu** — built the custom interactive objects
mentioned in issue #97), `okkiris`. Per-person work lives on branches
(`Marcus07/18`, `marcus-06/30`, `Iris-branch`, `lily_branch`, `Arush-Branch`,
`Refactor-for-scaling`, …), not just `main`. Last commit on `main`: **2025-08-16**.

---

## 2. Running it

From the project root (uses `uv`):

```bash
# Backend
echo "OPENAI_API_KEY=sk-..." > .env       # an OpenAI key is required — see §5
uv sync
uv run python -m uvicorn backend.main:app --reload   # serves on http://localhost:8000

# Frontend (optional)
#  1. Install Godot 4.x
#  2. Open frontend/Godot-Multi-Agent-Playground/project.godot
#  3. Run the project (the configured main scene is scenes/MAIN_SCENE/current_main_scene.tscn).
#     The README also points at scenes/test/test_scene_multi_agent.tscn as the demo scene.
```

> ⚠️ Heads-up: the README's "run scene" (`test_scene_multi_agent.tscn`) and the
> `project.godot` main scene (`scenes/MAIN_SCENE/current_main_scene.tscn`) disagree.
> Both exist; `current_main_scene.tscn` is the one Godot launches by default.

A pre-recorded demo is committed at `assets/multi_agent_playground_demo.gif`
(~10 MB) — the quickest way to see the end result without an API key.

---

## 3. Backend architecture (`backend/`)

### 3.1 HTTP API (`backend/main.py`)

A **FastAPI** app (CORS open to all origins). A single `GameLoop` is created at
startup and kept alive for the session. Endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/agent_act/next` | GET | Pop the next un-served agent action(s) for the frontend to play. **This is the main frontend polling endpoint.** |
| `/world_state` | GET | Full snapshot: agents, objects, locations, status. |
| `/agents/states` | GET | Current state (location, inventory, properties) of given agents. |
| `/objects` | GET | All interactive objects (name, description, location, state, gettable). |
| `/game/events` | GET | Events since a timestamp (actions rendered as `GameEvent`s). |
| `/game/status` | GET | Turn counter, active agents, counts. |
| `/game/reset` | POST | Reset the whole world. |
| `/game/pause`, `/game/resume` | POST | Control the loop. |

The frontend is **pull-based**: it repeatedly calls `/agent_act/next` and replays
whatever comes back. Nothing is pushed.

### 3.2 Game loop & turns (`backend/game_loop.py`)

`GameLoop` runs an async loop: pick the next agent → `execute_agent_turn(agent)`
→ push the resulting `AgentActionOutput` onto an event queue → advance the turn
counter only if the action "ends the turn" → sleep ~1s. At startup it builds the
house world, creates an `AgentManager`, and registers agents in `_setup_agents()`
(default cast: `alex_001`, `alan_002`, from `agents.yaml`). Each agent is seeded
once with an initial world description (an `EnhancedLookAction`).

### 3.3 Agent layer (`backend/agent/`) — how the LLM drives a character

Agents are built on the **Kani** LLM framework. `KaniAgent` (in
`agent_strategies.py`) *subclasses* `kani.Kani`, wires up an `OpenAIEngine`, and
exposes one tool via function-calling:

```python
@ai_function()
def submit_command(self, command: str):
    """Submit a SINGLE command and get immediate result."""
```

So the model "acts" by calling `submit_command("go north")` /
`submit_command("get apple")` etc. The flow each turn (`agent/manager.py`):

1. The agent is handed the **result of its previous action** as feedback
   (success text, or an error like "you can't go that direction"), plus any
   pending chat requests — *not* a fresh world dump.
2. To see the world again it must actively choose to `look`
   (`EnhancedLookAction._format_world_state()`), exactly like a human playing a
   MUD.
3. Kani runs one function-calling round (`max_function_rounds=1`); the submitted
   command is parsed and executed against the text-adventure engine; the
   resulting `ActionResult` is converted to the `AgentActionOutput` schema and
   queued for the frontend.

System prompts are **composed from templates** (persona + function-calling rules
+ chat rules + closing instructions) — see §5. A `ChatManager`
(`agent/chat_manager.py`) handles agent-to-agent chat *requests* (accept/reject,
then an active conversation), so agents can talk to each other, not just act.

### 3.4 The text-adventure engine (`backend/text_adventure_games/`)

This is a fork in the same lineage as our own `text_adventure_games` engine, but
**re-architected around "capability protocols"** rather than per-action
precondition methods. Key ideas:

- **Things** (`things/`): `Thing` → `Character`, `Item`, `Location`, `Object`,
  `Container`. Properties live in a `defaultdict(bool)`, same as ours. Items have
  rich subtypes (`EdibleItem`, `DrinkableItem`, `ClothingItem`, `BookItem`,
  `BeddingItem`, …); fixed furniture are `Object`s (`Sink`, `Television`, `Bed`,
  `Chair`, `Cabinet`, …).
- **Capabilities** (`capabilities.py`): runtime-checkable `Protocol`s —
  `Activatable`, `Openable`, `Lockable`, `Usable`, `Container`, `Recipient`,
  `Giver`, `Conversational`, `Consumable`, `Examinable`. An object *advertises*
  what can be done to it by implementing protocols; generic actions dispatch on
  them. Every capability method returns a standard `ActionResult(description,
  success, state_changed, events)`.
- **Actions** (`actions/`): generic verbs (`GoToAction`, `LookAction`,
  `TakeAction`, `DropAction`, `ExamineAction`, `PlaceAction`, `ConsumeAction`,
  `GenericSetToStateAction`, `Start/StopUsingAction`, `ChatAction` and the
  non-turn-ending `ChatRequest`/`ChatResponse`, plus `ActionSequence` for
  comma-chained commands). Actions carry `COMMAND_PATTERNS` (e.g. `"go {target}"`)
  and an `ends_turn` flag; the parser (`command/parser.py`, `command/matcher.py`)
  pattern-matches a command string to an action.
- **State/export** (`state/`, `events/`): `WorldStateManager` is the single
  source of truth for what an agent perceives; `SchemaExporter`
  (`events/schema_export.py`) turns the engine's `ActionResult` into the API's
  `AgentActionOutput`.

#### The house world (`backend/text_adventure_games/world/`)

The map is a single house of **8 rooms** (`world/layout.py`):

```
            Bedroom ── Laundry ── Game ── Bathroom
              │                     │
           Kitchen ──────────────  Living
              │                     │
            Entry  ──────────────  Dining
```

(Exact connections: Entry↔Kitchen, Entry↔Dining, Kitchen↔Dining, Kitchen↔Bedroom,
Bedroom↔Laundry, Laundry↔Game, Game↔Bathroom, Game↔Living, Dining↔Living,
Dining↔Bedroom.) Rooms are furnished with items and **multi-stage interactable
objects** — objects with more than one step/state, e.g.:

- **Closet / Cabinet / Bookshelf** — *open* → *see contents* → *take an item*.
- **TV** — *turn on* (activate) → *watch* (use).
- **Sink** — *turn the water on/off* (activate/deactivate).
- **Bed / Chair / Couch** — *start using* (sleep/sit) → *stop using*.

These map cleanly onto the `Openable`/`Container`, `Activatable`, and `Usable`
capabilities above.

### 3.5 Configuration (`backend/config/`)

Almost everything is data-driven via YAML, validated by Pydantic
(`config/models.py`, loaded by `config/yaml_config.py`):

- **`agents.yaml`** — the cast and their personas (`alex_001` = "friendly and
  social", `alan_002` = "quiet and thoughtful"), per-agent engine/model/temperature.
- **`llm.yaml`** — LLM engine settings (OpenAI default, e.g. `gpt-4.1-mini`; an
  Anthropic stanza exists too).
- **`prompts.yaml`** — prompt *templates* (`base_system_prompt`,
  `function_calling_instructions`, `chat_system_instructions`,
  `closing_instructions`) and *compositions* that stitch them into a final system
  prompt (`default_agent_prompt`, plus `debug`/`minimal` variants).
- **`defaults.yaml`** — fallback values when the above are missing.

- **`config/schema.py`** — the API contract: a discriminated-union `HouseAction`
  over all action types (`GoTo`, `SetToState`, `Take`, `Drop`, `Examine`,
  `Place`, `Consume`, `Chat`, …), wrapped in `AgentActionOutput {agent_id,
  action, timestamp, current_room, description}`. This is the JSON the frontend
  consumes.

### 3.6 Testing framework (`backend/testing/`)

A goal-based harness for LLM agents: `AgentGoalTest` defines a scenario (initial
world, persona, a `goal`, `success_criteria`/`failure_criteria`, `max_turns`);
`AgentTestRunner` runs it and scores behavior. Criteria include `LocationGoal`,
`InventoryGoal`, `InteractionGoal`, plus failure detectors (`TimeoutCriterion`,
`ImpossibleActionCriterion`, `LoopCriterion`). Useful prior art for evaluating
agents in our own engine.

### 3.7 Persistence / memory (`data/`)

`data/agents/<id>/agent.json` + `memory.json` hold persona/trait snapshots and a
salience-tagged event log; `data/world/messages.json` holds inter-agent chat
history. These look like **Generative-Agents-style** records (innate/learned/
currently traits, `curr_tile`, salience) but are *snapshots from prior runs* —
live state is held in memory during a session, not continuously written back.

---

## 4. Frontend architecture (`frontend/Godot-Multi-Agent-Playground/`)

**Godot 4.4**, GDScript. Internal viewport 640×320 scaled to 1920×960 with
integer pixel scaling. Autoload singletons: `DialogueManager`, `TimeManager`
(runs at 60× speed), `HouseLayout`. The one enabled addon is the third-party
**Dialogue Manager** (`addons/dialogue_manager/`).

### 4.1 Manager scenes (`scenes/managers/`) — the spine

The frontend is organized as cooperating "manager" nodes wired together by signals:

- **`http_manager`** — talks to the backend at **`http://localhost:8000`**.
  Polls `/agent_act/next` (timer ~5s, toggleable), converts incoming action
  names to snake_case, and feeds them into the action queue. Number keys `1`–`7`
  fire individual endpoints by hand; `E` toggles auto-polling, `F` auto-play,
  `R` plays the next queued action.
- **`action_manager`** — holds the action queue; emits `general_action` /
  `agent_action` / `object_action` signals as actions are played.
- **`agent_manager`** — owns the agent sprites; routes an action to navigation
  (walk there first) and then applies effects (inventory take/place, etc.).
- **`object_manager`** — maps room/object names to nodes; applies object state
  changes (open/close, on/off, take/consume) once an agent arrives.
- **`game_manager`** — the orchestrator that wires the others and the UI.
- **`text_input_manager`** — regex-parses typed debug commands (`take {item}`,
  `go_to {room}`, `set {object} to {state}`, `{sender} -> {recipient}: {msg}`, …)
  into the same action format, so you can drive the world by hand.

### 4.2 Agents, movement, scenes

Agents are `CharacterBody2D` (`scenes/characters/agents/base_agent/`) with an
`AnimatedSprite2D` (8 animations: `idle_/walk_` × up/down/left/right) and a
`NavigationAgent2D` for tile-based pathfinding (≈50 px/s). Houses
(`scenes/houses/base_house.tscn` and larger/second variants) are layered
`TileMapLayer`s (walls / floors / furniture). There are **many test scenes**
(`scenes/test/`) each isolating one subsystem — `test_scene_multi_agent`
(the demo), `test_scene_navigation`, `test_scene_second_house`,
`test_scene_dialogue`, `test_scene_camera`, etc. (matching the "lots of extra
test scenes" the issue warned about).

### 4.3 Interactable objects & dialogue

Interactable objects (`scenes/houses/interactable_objects/`: fridge, oven,
coffee, cabinet, sink, bathtub, modern_door, toybox, …) extend a `BaseObject`
and use an `InteractableComponent` that emits state-change signals to drive their
animations (the **animated** modern assets — see §6). The **Dialogue Manager**
addon powers the `guide` NPC and the chat box UI
(`dialogue/conversations/guide.dialogue`), and a `ChatBox` renders agent-to-agent
messages (`[HH:MM] sender → recipient: message`).

---

## 5. Feature summary

- LLM agents (OpenAI via Kani) that **perceive → decide → act** in a turn loop,
  selecting actions through function-calling.
- A **single-house world** of 8 connected rooms with furniture, items, and
  **multi-stage interactable objects** (open→take, on→use, sleep/sit).
- **Capability-protocol** action system (open/close, lock, activate, use, give,
  consume, examine, contain) instead of one method per verb.
- **Agent-to-agent chat** with request/accept/reject and conversation tracking.
- A full **FastAPI** so the world is a normal web service; frontend talks to it
  by polling.
- A **Godot 4.4** visualization: animated agents pathfinding through a tilemap
  house, inventory UI, chat box, NPC dialogue, manual text-command + hotkey
  debugging.
- YAML-driven **config** for personas, prompts, and LLM engines.
- A **goal-based agent test framework**.
- Generative-Agents-flavored **persistence** scaffolding (agent traits + salient
  memory logs).

---

## 6. Asset inventory & references (where to get everything)

This is the part most relevant to reuse. The 2025 project did **not** use the
"Cute RPG World" town pack or the Stanford `the_ville` assets named in issue #97
(no trace of either in this repo). Instead it's a **house** built from
pixel-art interior + farm + food packs. Below, *Confirmed* = an attribution/
license file is present **in the repo**; *Inferred* = identified from directory/
file names and visual style and **must be verified before reuse**.

### 6.1 Confirmed in-repo attributions

| Asset pack | In-repo location | Files | Source (from repo) | License (from repo) |
|------------|------------------|-------|--------------------|---------------------|
| **Craftpix clothing icons** | `frontend/.../assets/game/clothes/clothing_pixel_icons/` | ~42 PNG + coupon PDF | `Free Assets Craftpix!.url` → https://craftpix.net/freebies/ | `License.txt` → https://craftpix.net/file-licenses/ |
| **Alex Kovacs "100 pixel food icons"** | `frontend/.../assets/game/food/alexkovacsart_pixel_art_foods/` | ~100 food PNGs + icons | `Note from the artist.txt` (artist: **Alex Kovacs**) | **CC BY 4.0** (stated in the note) |
| **Noto Color Emoji** | `frontend/.../assets/ui/fonts/Noto_Color_Emoji/` | `.ttf` + `OFL.txt` | Google Inc. | **SIL Open Font License 1.1** (`OFL.txt`) |

The Alex Kovacs note, verbatim: *"Creative license is CC BY, you can read more
about it here: https://creativecommons.org/licenses/by/4.0/ … Alex"*. **CC BY
requires crediting the artist** if these foods are reused.

### 6.2 Inferred sources (named by folder/file; verify license before reuse)

| Asset pack | In-repo location | What it is | Likely upstream (itch.io / web) |
|------------|------------------|-----------|---------------------------------|
| **"LastTick" modern pixel clothes** | `.../assets/game/clothes/LastTick_modern_pixel_art_clothes/` | PNG + `.aseprite` sources; filename says "FREE" | LastTick (itch.io) |
| **Ghostpixxells pixel food** | `.../assets/game/food/Ghostpixxells_pixelfood/` | ~100 food PNGs | Ghostpixxells, "Pixel Food" (itch.io) |
| **PiiXL food & kitchenware** | `.../assets/game/food/PiiXL_food_and_little_bit_of_kitchenware/` | `FOOD.png` + **`FOOD.psd`** + `.eps` + cover | PiiXL (itch.io) |
| **"Mega Food Pack"** | `.../assets/game/food/` (mega food pack dir) | ~38 food PNGs | unidentified food pack |
| **HenrySoftware / SciGho food** | `.../assets/game/food/` (loose PNGs) | `HenrySoftware_pixel_food.png`, `SciGho_fruit+.png` | Henry Software; SciGho (itch.io) |
| **Farm/RPG base sprites** | `.../assets/game/characters/`, `.../assets/game/objects/`, `Tilesets/` | character/chicken/cow/crops/tools, basic furniture, grass/water/dirt tilesets | style strongly matches **"Sprout Lands" by Cup Nooble** (cupnooble.itch.io) — *inferred* |
| **"Modern Interiors" furniture + animated objects** | `frontend/.../modern_assets/` (incl. `animated_assets/animated_bathroom/`, `animated_kitchen/`, `animated_living/`) | kitchen/bathroom/bedroom/living/floors/walls sheets; animated fridge, oven, sink, bathtub, TV, toybox, doors | naming + style strongly match **LimeZu "Modern Interiors"** (limezu.itch.io/moderninteriors) — *inferred, no in-repo attribution* |

> ⚠️ **`modern_assets/` has no attribution file in the repo.** These are the
> highest-quality (and most license-sensitive) assets — the kitchen/bathroom/
> living-room furniture and the **animated** interactable objects. Their naming
> (`animated_kitchen_oven`, `animated_bathtub`, `animated_fridge_grey`, …) and
> style match LimeZu's *Modern Interiors* pack, which is a **paid** asset. Treat
> the source/license as **unverified** and confirm ownership before reusing.

### 6.3 The custom interactive objects from issue #97

Issue #97 noted that last summer's team (Lily Niu) built **custom interactive
objects (mostly bathroom + some kitchen)** and uploaded them, with a states doc,
to a shared Google Drive. Those objects now appear to live **in this repo** under
`frontend/.../modern_assets/animated_assets/` (`animated_bathroom/`,
`animated_kitchen/`, `animated_living/`) — i.e. the multi-state animated
fridge/oven/sink/bathtub/TV/toybox sprites that the Godot `InteractableComponent`
drives. `lilyniu88` is a contributor to the repo, consistent with this.

### 6.4 Editable source art (for re-export / editing)

- `.../assets/game/clothes/LastTick_modern_pixel_art_clothes/*.aseprite` (2 files)
- `.../assets/game/food/PiiXL_..._kitchenware/FOOD.psd` (~22 MB) and `.eps`
- `frontend/.../*.aseprite`, `*.psd` (a couple more scattered source files)

### 6.5 Where to obtain everything

1. **Code + the committed art** — clone
   `https://github.com/MoodyMarshmallow/multi_agent_playground` (most art is
   committed straight into the repo; no Git LFS). **Survey the branches**, not
   just `main` — work is spread across `Marcus*`, `Iris*`, `lily_branch`,
   `Arush*`, `Refactor-for-scaling`, etc.
2. **Shared Google Drive** (from issue #97 — original states doc + any objects
   not committed): https://drive.google.com/drive/folders/1K22Fc9042uwjfhdONjliYdtec9OAfGa8?usp=share_link
   (inside, see `asset packs/` → `animated_assets/` and
   `4_User_Interface_Elements/`). Access via **Lily Niu** (built/uploaded the
   objects) or **Iris Qian** (requested the states doc).
3. **Upstream asset packs** — to get clean, properly-licensed originals rather
   than the repo copies: Craftpix (confirmed URLs above), Alex Kovacs food
   (CC BY), Noto Color Emoji (Google, OFL), and the *inferred* itch.io packs in
   §6.2 (LimeZu Modern Interiors, Ghostpixxells, PiiXL, LastTick, Cup Nooble
   Sprout Lands — **verify each before shipping**).

---

## 7. Relevance to `agent-sandbox` & reuse notes

This project is the closest existing thing to our planned **Godot 2-D bridge**,
and it validates the overall shape: *keep the simulation in Python, make it a
web API, and let Godot be a thin polling visualizer.* Concretely worth a look:

- **The HTTP contract** (`/agent_act/next` polling + an `AgentActionOutput`
  discriminated union) is a clean, language-agnostic seam between our engine and
  any renderer — a strong candidate to adopt rather than reinvent.
- **The Godot manager/signal layout** (http → action queue → agent/object
  managers → sprites, with navigation-then-effect ordering) is a reusable
  blueprint for our bridge.
- **The animated interactable objects** (multi-state fridge/sink/bathtub/TV) are
  exactly the kind of art our `Openable`/`Activatable`/`Usable` actions imply —
  *if* licensing checks out (see §6.2 warning).
- **Caution / what to leave behind:** the backend re-architects the
  text-adventure engine around capability protocols (diverging from our
  precondition/effect actions), so it's reference, not a drop-in; there are many
  redundant test scenes to prune; and the most attractive art (`modern_assets/`)
  has **no in-repo license** — resolve provenance before depending on it.

---

## 8. Accuracy notes

- *Confirmed from files in the repo:* the backend architecture, endpoints, the
  8-room layout and connections, the Kani function-calling agent design, the
  config YAMLs, the Godot manager layout and `localhost:8000` URL, and the three
  **Confirmed** asset attributions in §6.1 (read verbatim from their
  `License.txt` / `.url` / artist note / `OFL.txt`).
- *Inferred (verify before relying on it):* every entry in §6.2 — these are
  identified by directory/file names and visual style, **not** by an in-repo
  license. The LimeZu/`modern_assets` and Cup Nooble/Sprout Lands attributions in
  particular are educated guesses from naming, and the §6.3 Drive↔repo linkage is
  inferred from matching folder names + contributor list, not a documented mapping.
