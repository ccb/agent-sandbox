# Generative Action Castle — a reference prototype (study, don't copy)

An **earlier prototype** of Chris's: a Smallville-style generative-agents simulator with
a **Python asyncio backend** and a **Godot 2D front end**, running the classic Action
Castle quest with five LLM-driven characters. It predates this repo and **lives only on
Chris's machine** (`~/Developer/Games/smallville/generative_action_castle/`, single
snapshot dated 2026-02-22).

> **Status: reference only.** It's a thin prototype — ~33 source files, ~4.6k LOC, no
> tests, and several half-finished/buggy parts (called out below). It is **not a
> starting point** and you shouldn't copy it. But four pieces are genuinely worth
> studying as "same idea, different representation" contrasts with what we've built.
> This doc is the curated version; you don't need the whole repo.

The four parts the roadmap flags, each with *what it does*, *the key excerpt*, *what's
broken*, and *how it maps onto our current engine*:

---

## 1. Memory-retrieval scoring (recency × importance × relevance)

**What it does.** Textbook Stanford-Smallville scoring. Each memory is scored on three
axes — **recency** (exponential decay `decay^ticks_ago`, default `0.995`), **importance**
(an LLM-assigned 1–10 "poignancy" stored on the node), and **relevance** (cosine
similarity of the query embedding to the memory's cached embedding). Each axis is
**min-max normalized across the candidate set**, combined by a **weighted sum** (weights
default 1.0), and the top-`n` returned (updating `last_accessed_tick`). Embeddings:
OpenAI `text-embedding-3-small` @ 256 dims, MD5-cached.

`backend/agent/cognitive/retrieve.py`:
```python
for mem in memories:
    ticks_ago = current_tick - mem.created_tick
    recency = decay_factor ** ticks_ago               # default 0.995
    importance_scores.append(mem.importance / 10.0)   # 1-10 poignancy
    if query_embedding is not None:
        mem_embedding = agent.memory_stream.get_embedding(mem.embedding_key)
        sim = llm_client.cosine_similarity(query_embedding, np.array(mem_embedding))
        relevance_scores.append(max(0.0, sim))

recency_norm    = _min_max_normalize(recency_scores)
importance_norm = _min_max_normalize(importance_scores)
relevance_norm  = _min_max_normalize(relevance_scores)
final = [rw*recency_norm[i] + iw*importance_norm[i] + vw*relevance_norm[i]
         for i in range(len(memories))]   # then sorted desc[:n]
```

**Rough edges:** recency keys off `created_tick`, not `last_accessed_tick` (so re-access
never refreshes recency — a divergence from Smallville); and embeddings appear **never
stored** in the path shown, so the relevance axis likely collapses to all-zeros
(`_min_max_normalize` → 0.5 for everything = a no-op). **Verify embedding population
before trusting relevance.**

**Maps to our engine:** this is exactly our **#76 / Phase B** retrieval scoring — and our
implementation is the *clean* one (a pluggable `EmbeddingClient`, model2vec default,
relevance actually wired in via `--embeddings`). So study this for the *shape of the
formula*, but our `docs/design/memory-retrieval-embeddings.md` + the shipped code is the
better implementation to follow.

---

## 2. Data-driven (YAML) action engine + Action Castle *as data*

**What it does.** The most interesting contrast for you. Where our engine writes each
verb as a Python `Action` subclass, here **every action is declarative YAML** —
`name`, `keywords`, `parameters`, a list of typed **preconditions**, and a list of typed
**effects** — and `world/actions.py` is a generic interpreter. Preconditions and effects
are each a big dispatch on a `type` string (~8 precondition types: `in_inventory`,
`co_located`, `object_property`, `object_state`, …; ~14 effect types: `transfer_object`,
`set_property`, `change_state`, `add_memory`, `add_goal`, `complete_goal`,
`broadcast_event`, …). Variables like `$agent`/`$object`/`$target` resolve against a
bindings dict. The **entire Action Castle quest is encoded as data** — no quest logic in
Python: catch fish → give fish to troll (clears the drawbridge) → show decree to guard
(get iron key) → unlock tower → give rose to princess → place crown on throne (win).
Gating lives in `world.yaml` (`drawbridge: blocked_by_agent: troll, unless_property:
satisfied`; `tower_stairs: requires: iron_key`).

A representative action — note it flips NPC state, completes/injects goals at runtime,
and emits narration, all declaratively (`backend/config/actions.yaml`):
```yaml
give_rose_to_princess:
  keywords: ["give rose", "offer rose", "flower", "princess"]
  preconditions:
    - {type: in_inventory, object: rose, agent: $agent}
    - {type: co_located, agent: $agent, target: princess}
  effects:
    - {type: transfer_object, object: rose, from_agent: $agent, to_agent: princess}
    - {type: set_property, agent: princess, property: trusts_hero, value: true}
    - {type: add_memory, agent: $agent, importance: 9, description: "The Princess told $agent_name about the gold crown"}
    - {type: add_goal, agent: $agent, goal_id: get_crown, priority: 8, description: "Retrieve the gold crown from the ghost"}
    - {type: broadcast_event, message: "The Princess smiles warmly and whispers ..."}
```

The interpreter (`backend/world/actions.py`): check all preconditions, then apply effects
in order. The LLM never calls actions directly — it emits free text and a keyword matcher
(`keyword=2pts, name word=1pt`, threshold ≥3) maps it to a registered action.

**Rough edges:** effects are **not atomic** — each is wrapped in a try/except that *logs
and continues*, so a mid-list failure leaves partial state with no rollback. The keyword
matcher is crude and can mis-route similar verbs ("give …"). Two different property
mechanisms coexist (object attributes via `getattr` vs. an agent `scratch.properties`
dict), easy to confuse when authoring YAML.

**Maps to our engine:** this is the "same idea, different representation" the roadmap
mentions — a useful mirror to our Python-subclass approach (AC2/AC3/AC4). The YAML
approach is more data-driven and LLM-authorable; ours is more type-safe and testable. The
precondition/effect *vocabulary* here is a good checklist of what a declarative layer over
our `Action`s would need if we ever wanted one.

---

## 3. Agent personas (prompt-engineering examples)

**What it does.** Five personas in `config/agents.yaml` — `troll`, `guard`, `princess`,
`ghost`, `hero`. Schema per agent: `id`, `name`, `spawn_location`, `innate` (fixed
personality prose), `learned` (background knowledge prose), `emoji`, `personality_traits`
(tags), and `goals` — each `{id, description, priority, horizon}` with
`horizon ∈ {immediate, near_term, long_term}`. The goals double as designed-in quest
hints that line up with the action chain in §2.

`backend/config/agents.yaml` (trimmed):
```yaml
- id: hero
  name: "The Unlikely Hero"
  spawn_location: cottage
  innate: >
    A simple fisherman near the castle. Friendly, humble, always willing to help.
    Owns a fishing pole and an old oil lamp. Speaks plainly.
  learned: >
    Heard rumors of a princess trapped in the tower. Knows the pond is best for fish.
    Knows how to light his lamp using flint from his cottage fireplace.
  personality_traits: [friendly, humble, curious, brave]
  goals:
    - {id: rescue_princess,       priority: 9, horizon: long_term,  description: "Rescue the princess in the tower"}
    - {id: get_past_troll,        priority: 8, horizon: near_term,  description: "Get past the troll — he demands food"}
    - {id: catch_fish,            priority: 7, horizon: near_term,  description: "Catch a fish to trade with the troll"}
    - {id: prepare_for_adventure, priority: 8, horizon: immediate,  description: "Pick up the fishing pole and lamp, light the lamp"}
```

**Note vs. the roadmap's description:** there are **no `relationships` and no explicit
spatial-knowledge fields** in the YAML. Spatial knowledge is bootstrapped at runtime
(an agent learns its spawn + neighbors; `SpatialMemory` is just a growing `set` of known
location IDs as it moves), and relationships, if they exist at all, emerge only through
memory-stream entries — they aren't a structured field. Study the `innate`/`learned` +
prioritized-time-horizoned-goals shape; don't expect the relationship graph.

---

## 4. Godot ↔ Python websocket protocol (the Phase-3 bridge blueprint)

**What it does.** A raw `websockets` server (`ws://0.0.0.0:8765`) and a Godot
`WebSocketPeer` client. **Envelope both ways:** `{"type": <string>, "data": <object>}`,
JSON-encoded. No auth/version handshake — on connect the server immediately pushes one
full `world_state`, then loops over incoming messages; a separate **broadcast loop**
(every 0.5s) pushes incremental updates.

- **Client → server:** `set_speed`, `set_mode`, `player_intention {text}`,
  `god_whisper {agent_id, text}`, `object_state_change`, `inspect_agent {agent_id}`,
  `save_game`/`load_game {filename}`.
- **Server → client:** `world_state` (full snapshot), then push-based `agent_update`,
  `time_update`, `agent_action`, `conversation`, plus replies `agent_detail`,
  `save_result`, `load_result`, `speed_update`/`mode_update`.

Server dispatch (`backend/websocket_handler.py`) and client dispatch
(`frontend/scripts/main.gd`):
```python
msg_type = message.get("type", ""); data = message.get("data", {})
if   msg_type == "set_speed":        simulation.set_speed(data.get("speed", 1)); ...
elif msg_type == "player_intention": await simulation.handle_player_intention(data.get("text",""))
elif msg_type == "god_whisper":      await simulation.handle_god_whisper(data.get("agent_id",""), data.get("text",""))
```
```gdscript
match msg_type:
    "world_state":  _handle_world_state(msg_data)
    "agent_update": _handle_agent_updates(msg_data)
    "time_update":  _handle_time_update(msg_data)
    "agent_action": _handle_agent_action(msg_data)
    "conversation": _handle_conversation(msg_data)
```

**Tick model:** there is **no per-tick request** — the sim advances autonomously in its
own loop; the client only sets cadence (`set_speed` 0/1/2/5×) and receives a fire-and-
forget push stream. Worth deciding consciously whether our bridge wants this push model or
a request/response step.

**Rough edges:** the client `match` has no arm for `mode_update`/`save_result`/
`load_result` (silently dropped — no UI confirmation); no protocol versioning or message
IDs, so replies aren't correlated to requests (racy with >1 client).

**Maps to our engine:** this is the proven blueprint for our Phase-3 Godot bridge
(#82/#87/#88 territory). The envelope + message-type catalog is a solid starting contract;
just add a version field and request/response correlation.

---

## What to ignore / known rough edges (summary)

- **Embeddings may never be stored** → the retrieval relevance axis is likely a no-op (§1). The single most important thing to verify before relying on it.
- **Non-atomic effects with swallowed exceptions** → partial world-state on failure (§2).
- **Personas have no relationships/spatial fields** → spatial is runtime-only (§3).
- **Frontend drops several server message types** (§4).
- No tests anywhere; `perceive.py`/`plan.py`/`converse.py` exist but their prompt quality wasn't audited.

## Getting the actual code

It's on Chris's machine, not in any shared repo. If you need to run it (vs. just study the
above), ask Chris for a copy — **but note `backend/.env` holds real API keys** (gitignored,
not tracked), so it can't be zipped/sent wholesale; you'd get the source minus `.env` and
supply your own keys via `backend/.env.example`.
