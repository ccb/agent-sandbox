# Backend HTTP API

The `backend` package is **agent-sandbox's backend seam**: a small
[FastAPI](https://fastapi.tiangolo.com/) app (`backend/api.py`) that serves *any*
engine `Game` over HTTP. Every out-of-process frontend — a Godot/2D renderer, the
web inspection companion — polls the **same** endpoints here instead of embedding
Python or baking its own data dump. The engine and any LLM stay server-side; the
frontend just reads JSON. (The package lives at `godot-generative-agents/backend/`;
it's imported as the top-level `backend` package via the editable install, so
`from backend…` and `python -m backend.api` work from anywhere in the repo.)

> This document is the human-readable endpoint reference. The interactive,
> machine-readable contract is auto-served at **`/docs`** (Swagger UI) and
> **`/openapi.json`** whenever the server is running — that is the source of truth
> GDScript (Godot) and TS/JS (companion) clients generate against. This
> page exists so you can read the whole API end-to-end without first starting it.

It documents the API as shipped in PR #196 (issues #179, #186, #185) — the
**snapshot + change-feed contract** — plus the on-demand reads of an agent's
private cognition: its memory stream (issue #298), its belief set (issue #348),
and its daily plan (issue #347); the **write-side interventions** (issue #369)
that let a human speak to an agent or perturb the world; plus **live mode**
(issues #349, #262): an opt-in self-stepping loop that
advances the sim on its own and publishes each step to a cursor-addressed change
feed a viewer follows over `WS /ws` (with `GET /events?since=` as the catch-up
door), controlled by `POST /pause|/resume|/reset`. See
[Not yet implemented](#not-yet-implemented) for what is deliberately deferred.

> [!WARNING]
> The API is **unauthenticated and bound to loopback by default** — safe for local
> development only. Do not expose this server to an untrusted network as-is. See
> [Authentication & security](#authentication--security).

## Contents

- [Install & run](#install--run)
- [Endpoint reference](#endpoint-reference)
  - [`GET /health`](#get-health)
  - [`GET /world_state`](#get-world_state)
  - [`GET /agents`](#get-agents)
  - [`GET /agents/{name}/memory`](#get-agentsnamememory)
  - [`GET /agents/{name}/knowledge`](#get-agentsnameknowledge)
  - [`GET /agents/{name}/retrieval`](#get-agentsnameretrieval)
  - [`GET /agents/{name}/plan`](#get-agentsnameplan)
  - [`POST /command`](#post-command)
  - [`POST /agents/{name}/say`](#post-agentsnamesay)
  - [`POST /world/event`](#post-worldevent)
- [Live mode: the loop, the feed, run control (#349/#262)](#live-mode-the-loop-the-feed-run-control-349262)
  - [`GET /live`](#get-live)
  - [`GET /events`](#get-events)
  - [`WS /ws`](#ws-ws)
  - [`POST /pause`, `/resume`, `/reset`](#post-pause-resume-reset)
  - [`GET /usage`](#get-usage)
- [Status codes](#status-codes)
- [The `world_state` snapshot](#the-world_state-snapshot)
- [The `events` change feed](#the-events-change-feed)
- [The memory stream](#the-memory-stream)
- [The belief set](#the-belief-set)
- [The daily plan](#the-daily-plan)
- [Authentication & security](#authentication--security)
- [CORS](#cors)
- [Quick start (a full curl walkthrough)](#quick-start-a-full-curl-walkthrough)
- [Not yet implemented](#not-yet-implemented)

## Install & run

FastAPI is an **optional** dependency. Install it (and `uvicorn`) with the
`server` extra:

```bash
uv sync --extra server   # fastapi + uvicorn + websockets (pydantic rides along;
                         # websockets lets uvicorn serve the live feed's WS /ws)
```

**Run a demo world** — a tiny two-room map, enough to exercise the contract and
`/docs` with no assets:

```bash
uv run python -m backend.api                    # serves on http://127.0.0.1:8080
HOST=127.0.0.1 PORT=9000 uv run python -m backend.api   # override host/port
```

**Serve your own game** — `run()` takes any
`text_adventure_games.games.Game` and blocks until Ctrl-C:

```python
from backend.api import run
from notebooks.hw1_solution.action_castle import build_game   # or any Game

run(build_game(), host="127.0.0.1", port=8080)
```

**Embed the app** (e.g. in tests, or behind your own ASGI server) — `create_app()`
returns the `FastAPI` instance without starting a server:

```python
from backend.api import create_app

app = create_app(game, auth_token="s3cret", max_body_bytes=64 * 1024)
# hand `app` to TestClient, uvicorn, gunicorn, ...
```

`create_app(game)` is **game-agnostic** — the same app serves Action Castle, a
benchmark task, or the live Penn sim. Access to the game is serialized
with a lock, since FastAPI runs the sync handlers in a thread pool and
`POST /command` mutates state.

## Endpoint reference

Seventeen endpoints. `GET`s are read-only; `POST /command` advances the game by
exactly one command (one turn); the live routes observe and steer the
self-stepping loop when one is enabled ([live mode](#live-mode-the-loop-the-feed-run-control-349262)).

| Method | Path                       | Purpose                                            |
| ------ | -------------------------- | -------------------------------------------------- |
| `GET`  | `/health`                  | Liveness + the current turn (cheap poll)           |
| `GET`  | `/world_state`             | The full, typed world snapshot                     |
| `GET`  | `/agents`                  | Roster of agent-bound characters + a summary (#344)|
| `GET`  | `/agents/{name}/memory`    | One agent's memory stream, formed so far (#298)    |
| `GET`  | `/agents/{name}/knowledge` | One agent's belief set (world-model) (#348)        |
| `GET`  | `/agents/{name}/retrieval` | What an agent would recall for a cue, read-only (#346) |
| `GET`  | `/agents/{name}/plan`      | One agent's daily plan / intentions (#347)         |
| `POST` | `/command`                 | Run one command → events + new snapshot            |
| `POST` | `/agents/{name}/say`       | Speak to an agent → a `chat` memory it perceives (#369) |
| `POST` | `/world/event`             | Inject an observable event agents in range perceive (#369) |
| `GET`  | `/live`                    | Live-mode handshake: loop state + world `meta` (#262) |
| `GET`  | `/events`                  | Change-feed catch-up: records after `?since=` (#262) |
| `WS`   | `/ws`                      | Change-feed push: every record as it lands (#262)  |
| `POST` | `/pause` `/resume` `/reset`| Run control over the loop (#349/#262)              |
| `GET`  | `/usage`                   | `UsageLedger` summary (tokens/cost) for the HUD (#264) |

### `GET /health`

A cheap liveness poll that never mutates the game.

**Response** `200 OK`

```json
{ "ok": true, "turn": 0 }
```

```bash
curl -s http://127.0.0.1:8080/health
```

### `GET /world_state`

Returns the typed, deterministic snapshot of the whole world (issue #90). Two
calls with no command in between return byte-identical JSON, and a `GET` never
advances the game. See [The `world_state` snapshot](#the-world_state-snapshot)
for the full shape.

**Response** `200 OK` — the `WorldState` snapshot (abridged, from the demo world):

```json
{
  "schema_version": "1.0",
  "turn": 0,
  "player": "player",
  "clock": null,
  "locations": [
    {
      "name": "Field",
      "description": "An open field full of tall grass.",
      "visited": true,
      "exits": [
        { "direction": "north", "to": "Forest", "blocked": false, "description": "" }
      ],
      "items": [
        {
          "name": "flower",
          "description": "a red flower",
          "location": "Field",
          "owner": null,
          "container": null,
          "quantity": 1,
          "affordances": ["gettable"],
          "properties": {},
          "contents": []
        }
      ],
      "characters": ["gardener", "player"],
      "properties": {}
    }
  ],
  "characters": [
    {
      "name": "player",
      "description": "you",
      "persona": "I explore the world.",
      "location": "Field",
      "is_player": true,
      "inventory": [],
      "worn": [],
      "wielded": [],
      "goals": [],
      "properties": { "character_type": "notset" }
    }
  ],
  "events": []
}
```

```bash
curl -s http://127.0.0.1:8080/world_state
```

### `GET /agents`

The **roster** of characters that have an agent (a mind) bound (issue #344) —
the discovery companion to [`GET /agents/{name}/memory`](#get-agentsnamememory).
Without it a client would have to hard-code the cast or scrape `/world_state`'s
omniscient `characters` list, which doesn't say *which* characters have a mind;
this returns just those, each with enough summary to drive a sidebar or panel
list without an extra fetch per agent. Read-only and pull-only, sorted by name;
`turn` matches [`GET /health`](#get-health) so a client can align it with the
feed.

The `/world_state` snapshot deliberately omits private cognition (#185), and
this roster keeps that line: it exposes only per-kind memory **counts** (plus
`persona`/`location`, which are already public in `world_state`), never the
memory **text** — that stays behind the per-persona
[`GET /agents/{name}/memory`](#get-agentsnamememory) route.

**Response** `200 OK` — `AgentRosterResponse` (from the demo world):

```json
{
  "turn": 0,
  "agents": [
    {
      "name": "gardener",
      "persona": "I tend this field.",
      "location": "Field",
      "memory_count": 3,
      "kind_counts": { "observation": 2, "plan": 1 }
    }
  ]
}
```

Each entry's `name` is the exact, case-sensitive URL key for that agent's
memory route — spaces and all, URL-encoded (`Maya Chen` →
`/agents/Maya%20Chen/memory`). `location` is the location's name, or `null` for
an unplaced character. `memory_count == sum(kind_counts.values())`, and the
counts are tallied over the very stream `/agents/{name}/memory` returns, so a
list badge and the opened panel never disagree. A world with no agent-bound
characters returns `{"turn": N, "agents": []}` — an empty list, not an error.

```bash
curl -s http://127.0.0.1:8080/agents
```

### `GET /agents/{name}/memory`

Returns the memory stream the named agent has formed **so far** (issue #298) —
readable mid-run, without waiting for any end-of-run export. This is the live
counterpart of the `memory_streams` block a baked replay file carries: the
`memories` list is produced by the same formatter
(`backend/cognition.py::memory_stream_for_persona`), so a live fetch and
a bake of the same run can never drift apart. See
[The memory stream](#the-memory-stream) for the data model.

Pull-only: the sim never pushes streams to anyone. A client fetches one when a
user opens an agent's panel — user-initiated, occasional, potentially large —
while the tiny per-decision `reasoning`/`memories` shorthand already rides
inside every frame.

`{name}` is the character's exact name — **case-sensitive**, no fuzzy matching —
URL-encoded as usual (`/agents/Maya%20Chen/memory` for `"Maya Chen"`).

**Response** `200 OK` — `MemoryStreamResponse` (from the demo world's gardener):

```json
{
  "persona": "gardener",
  "turn": 0,
  "count": 3,
  "memories": [
    { "kind": "observation", "importance": 3.0, "text": "The flowers by the north path bloomed overnight.", "created_turn": 0 },
    { "kind": "observation", "importance": 2.0, "text": "A stranger wandered into the field.", "created_turn": 0 },
    { "kind": "plan", "importance": 5.0, "text": "Water the tall grass before midday.", "created_turn": 0 }
  ]
}
```

`turn` is the engine turn the stream was snapshotted at — the same counter
`GET /health` reports and the axis each record's `created_turn` is measured on —
so a client can align the stream with the feed. `count == len(memories)` — how
many entries *this response* carries. The list is chronological (append order);
an agent that simply hasn't formed memories yet returns `200` with
`"memories": []`.

**Query parameters (issue #345)** — three optional selectors let a client fetch
a *slice* instead of the whole stream. They compose, and each defaults to
"everything", so a **no-argument request is byte-identical to the above**.

| Param        | Effect                                                                 |
| ------------ | ---------------------------------------------------------------------- |
| `since_turn` | only memories with `created_turn > N` — the incremental poll (below)   |
| `kind`       | only one `MemoryKind`: `observation` \| `reflection` \| `plan` \| `chat` |
| `limit`      | only the newest `K` (≥ 1), after the other filters — a bounded first paint |

They apply in the order `since_turn` → `kind` → `limit` (the newest `K` of what
survives) — the natural "plans since turn T, newest 20" reading, which also maps
straight onto a future `WHERE created_turn > ? AND kind = ? … LIMIT ?` store
query (#304). Whenever **any** selector is set, the response gains a `total`
field — the *unfiltered* stream size — so a UI can render "showing `count` of
`total`":

```json
{ "persona": "gardener", "turn": 0, "count": 2, "total": 3, "memories": [ … ] }
```

The incremental-poll loop: read `turn` (from `/health` or a prior stream fetch),
then re-fetch with `since_turn=<that turn>` to get exactly what formed since —
an already-caught-up poller gets a prompt `200` with `"memories": []`. An
unrecognised `kind` is a `422` (validation error), never a silently-empty list;
`limit` below `1` is likewise a `422`.

```bash
curl -s 'http://127.0.0.1:8080/agents/gardener/memory?kind=plan&limit=20'
curl -s 'http://127.0.0.1:8080/agents/gardener/memory?since_turn=42'   # only newer
```

**Errors** — two distinct `404`s:

| Case                                             | `detail`                                              |
| ------------------------------------------------ | ----------------------------------------------------- |
| No character by that name                        | `unknown character: 'nobody'`                         |
| Character exists but has **no agent** bound (the player, a scripted-behavior NPC) | `character 'player' has no agent (and so no memory stream)` |

```bash
curl -s http://127.0.0.1:8080/agents/gardener/memory
```

### `GET /agents/{name}/knowledge`

Returns the named agent's **belief set** — what it *thinks is true about the
world* (issue #348). This is the sibling of the memory read: **memory is the
episodic log** of what an agent saw or did; **knowledge is its current
world-model.** The set holds the seeded spatial priors (#79 — the places and
areas this persona knows exist) plus anything learned during play. Like the
memory stream it is private cognition the `world_state` snapshot deliberately
omits (#185), so this scoped per-persona route is the sanctioned way to read it.
See [The belief set](#the-belief-set) for the data model.

Beliefs are **context, not authority**: the world graph stays the single source
of truth. A belief may be incomplete (an agent that doesn't know the Biopond
exists simply has no belief about it) or even wrong; it shapes what the agent
reasons about (and, via a matching `topic`, what it can perceive), but never
mutates the world.

`{name}` is the character's exact name — **case-sensitive**, no fuzzy matching —
URL-encoded as usual (`/agents/Maya%20Chen/knowledge`). An optional **`?topic=`**
query narrows the response to beliefs carrying that exact perception key, for
when a belief set grows large.

**Response** `200 OK` — `KnowledgeResponse` (from the demo world's gardener):

```json
{
  "persona": "gardener",
  "turn": 0,
  "count": 2,
  "beliefs": [
    { "text": "The field lies just south of a dense forest.", "topic": "forest", "learned_turn": null },
    { "text": "The north path is overgrown with tall grass.", "topic": null, "learned_turn": 1 }
  ]
}
```

`turn` is the engine turn the belief set was snapshotted at (the same counter
`GET /health` reports), so two reads with no turn between them are identical.
`count == len(beliefs)`. Each belief's `learned_turn` is `null` for a prior known
up front (the way #79 seeds spatial knowledge) and the turn number for one
learned during play. An agent whose knowledge was never seeded (the fresh
checkout where #79 seeding no-ops) returns `200` with `"beliefs": []` — absent,
not an error.

**Errors** — two distinct `404`s, matching the memory route so the
`/agents/{name}/...` family stays consistent:

| Case                                             | `detail`                                              |
| ------------------------------------------------ | ----------------------------------------------------- |
| No character by that name                        | `unknown character: 'nobody'`                         |
| Character exists but has **no agent** bound (the player, a scripted-behavior NPC) | `character 'player' has no agent (and so no mind to read)` |

> **Why 404 a character with no agent, when every character *has* a
> `knowledge`?** Because this route family reads a *mind*. The player and
> scripted-behavior NPCs aren't agents to inspect here; gating on the agent
> keeps the memory and knowledge routes behaving identically. (Player/NPC belief
> inspection, if ever wanted, would be a separate, deliberately-named surface.)

```bash
curl -s http://127.0.0.1:8080/agents/gardener/knowledge
curl -s 'http://127.0.0.1:8080/agents/gardener/knowledge?topic=forest'
```

### `GET /agents/{name}/retrieval`

Returns the memories the named agent's retriever **would surface for a cue**,
scored but *not attended to* (issue #346). Where `/memory` hands back the whole
stream in chronological order, this scores every memory the way the agent does at
decision time — the paper's **recency + importance + relevance** — and returns
the top few, **ordered most-useful-first**. It is the read-only window onto
retrieval: a debugging UI can ask "what does Maya recall about the library right
now?" and see exactly the block a real decision would draw on.

The cue is the required **`?q=`** query. `{name}` is the character's exact name —
**case-sensitive**, URL-encoded as usual. An optional **`?limit=`** caps the
probe at that many records (it maps to the retriever's `max_records`); omit it for
the decision-time default.

The read runs with **`touch=False`**: inspecting what *would* surface never bumps
a memory's `last_accessed_turn`, so a probe can't perturb the very recency it is
measuring, and two identical probes with no turn between them return the same
records. That is what makes it safe to fire on every keystroke of an inspector —
unlike the decision-time path, which *does* bump recency (attending to a memory
keeps it fresh).

**Response** `200 OK` — `RetrievalResponse` (the demo gardener, `?q=flowers&limit=2`):

```json
{
  "persona": "gardener",
  "turn": 0,
  "query": "flowers",
  "count": 2,
  "memories": [
    { "kind": "observation", "importance": 3.0, "text": "The flowers by the north path bloomed overnight.", "created_turn": 0 },
    { "kind": "plan", "importance": 5.0, "text": "Water the tall grass before midday.", "created_turn": 0 }
  ]
}
```

Note the ordering: the flowers observation leads the *higher-importance* plan
because it matches the cue — relevance, recency, and importance combine, so the
most on-topic memory wins even when it isn't the most important. `query` echoes
the cue this ranking answers; `turn` is the engine turn it was scored at (the same
counter `GET /health` reports). `count == len(memories)`, and each entry is the
same shape [`GET /agents/{name}/memory`](#get-agentsnamememory) emits — so a
client renders a probe result and a stream slice through one code path. Ordering
is by score (most useful first), **not** chronological. An agent with an
as-yet-empty stream returns `200` with `"memories": []`.

**Errors** — the required cue plus the two family `404`s:

| Case                                             | Status | `detail`                                              |
| ------------------------------------------------ | ------ | ----------------------------------------------------- |
| Missing or empty `?q=`                           | `422`  | (validation error — the cue is required)              |
| No character by that name                        | `404`  | `unknown character: 'nobody'`                         |
| Character exists but has **no agent** bound      | `404`  | `character 'player' has no agent (and so no memory to probe)` |

```bash
curl -s 'http://127.0.0.1:8080/agents/gardener/retrieval?q=forest'
curl -s 'http://127.0.0.1:8080/agents/gardener/retrieval?q=forest&limit=3'
```

### `GET /agents/{name}/plan`

Returns the named agent's **daily plan** — what it *intends to do today* (issue
#347). This completes the agent card: **memory** is what it remembers, **knowledge**
what it believes, and this is what it **plans**. The plan is the agent's
`DailyPlan` (`text_adventure_games/planning.py`) at three altitudes — a `day`
outline, an `hours` schedule, and the concrete `stops` (`{place, activity, emoji,
steps}`) the step loop actually walks. It is the **live counterpart of the baked
`personas/<name>/daily_plan.json`**: both go through the plan's own
`to_primitive()`, so a live read and the baked artifact can never drift (the #298
rule — one formatter for both). See [The daily plan](#the-daily-plan) for the shape.

`{name}` is the character's exact name — **case-sensitive** — URL-encoded as usual
(`/agents/Maya%20Chen/plan`).

**Response** `200 OK` — `PlanResponse` (illustrative — the shape a planned agent returns):

```json
{
  "persona": "Maya Chen",
  "turn": 42,
  "revision": 1,
  "plan": {
    "day": [{ "label": "morning", "summary": "open and run the cafe" }],
    "hours": [{ "start_hour": 8, "summary": "tend the counter, then buy milk" }],
    "stops": [
      { "place": "Hays Cafe", "activity": "brew the morning batch", "emoji": "☕", "steps": 6 },
      { "place": "The Willows Market", "activity": "buy milk", "emoji": "🥛", "steps": 3 }
    ],
    "revision": 1
  }
}
```

`revision` is **hoisted to the top level** so a client can poll it cheaply and
refetch the (larger) plan only when a mid-run replan bumps it — it starts at `0`
when the plan is first generated and increments each time `maybe_revise_plan`
rewrites the not-yet-executed tail. `turn` is the engine turn the plan was
snapshotted at (the same counter `GET /health` reports). The nested `plan` is
`DailyPlan.to_primitive()` verbatim (note it carries its own `revision`, mirrored
by the top-level field).

An agent that is bound but whose brain **never planned** (a bare `ScriptedAgent`)
returns `200` with `"plan": null` and `"revision": null` — absent, not an error,
since a plan may still be generated later (the same way "no memories yet" is a
`200` with `"memories": []`). The stock demo gardener is exactly this case.

**Errors** — the two family `404`s:

| Case                                             | `detail`                                              |
| ------------------------------------------------ | ----------------------------------------------------- |
| No character by that name                        | `unknown character: 'nobody'`                         |
| Character exists but has **no agent** bound (the player, a scripted-behavior NPC) | `character 'player' has no agent (and so no plan)` |

```bash
curl -s http://127.0.0.1:8080/agents/gardener/plan   # stock demo → "plan": null
```

### `POST /command`

Runs exactly one command and returns what happened, the new world, and whether
the game ended.

**Request body** — `CommandRequest`:

```json
{ "command": "go north" }
```

`command` is a non-empty string (`min_length=1`); it is stripped of surrounding
whitespace before it reaches the engine.

**Response** `200 OK` — `CommandResponse`:

| Field         | Type         | Meaning                                                       |
| ------------- | ------------ | ------------------------------------------------------------- |
| `events`      | `list[dict]` | The [change-feed](#the-events-change-feed) records this command emitted |
| `world_state` | `dict`       | The new [snapshot](#the-world_state-snapshot) after the command |
| `game_over`   | `bool`       | Whether the game has now ended                                |

```bash
curl -s -X POST http://127.0.0.1:8080/command \
  -H 'Content-Type: application/json' \
  -d '{"command": "go north"}'
```

```json
{
  "events": [
    { "channel": "narration", "text": "Player moved to Forest", "actor": null, "turn": 0, "phase": null, "meta": {} },
    { "channel": "narration", "text": "FOREST\nA dense, dark wood.\nExits:\n * South to Field\n", "actor": null, "turn": 0, "phase": null, "meta": {} }
  ],
  "world_state": { "schema_version": "1.0", "turn": 1, "player": "player", "...": "..." },
  "game_over": false
}
```

> [!IMPORTANT]
> **A rejected *command* is not a failed *request*.** A command the **engine**
> rejects — a failed precondition, e.g. `go east` when there is no east exit —
> still returns **`200 OK`**, with the rejection surfaced as a `blocked` event in
> `events`. A `4xx` means the **request** was bad (malformed or empty body), not
> that the command was disallowed. Clients should inspect the `events` channels to
> learn whether a command actually succeeded — never the HTTP status alone.

### `POST /agents/{name}/say`

Lets a human **speak to an agent** (issue #369) — the write-side sibling of
[`GET /agents/{name}/memory`](#get-agentsnamememory). The utterance enters the
agent's stream as a **`chat`-kind memory** phrased from the listener's side
(`'{speaker} said to me: "…"'`) — the same dual-write shape `conversation.py`
uses, minus the speaker half (the human has no agent memory). The line is also
pushed onto the character's `heard` buffer, so it surfaces in the agent's next
observation exactly like overheard speech.

`{name}` is the character's exact name — **case-sensitive**, URL-encoded as usual.

**Request body** — `SayRequest`:

```json
{ "text": "The market closes at noon.", "speaker": "Alistair" }
```

`text` is a non-empty string; `speaker` is optional attribution (defaults to
`"someone"` — a voice with no named source).

**Response** `200 OK` — `SayResponse`:

| Field     | Type          | Meaning                                                        |
| --------- | ------------- | -------------------------------------------------------------- |
| `persona` | `str`         | The agent spoken to                                            |
| `turn`    | `int`         | The engine turn the utterance was delivered on                 |
| `reply`   | `str` \| `null` | The agent's one-line answer — `null` under the mock brain (the utterance is remembered, but a scripted stand-in doesn't talk back); a real brain (#261) fills it |
| `cursor`  | `int`         | The change-feed cursor of the `intervention` record this appended, so a viewer following `/ws` sees the same intervention |

Applied **at the next tick boundary**: the delivery runs under the shared lock in
a worker thread, so it lands cleanly between ticks even while the live loop is
stepping. Unlike `POST /command`, an utterance does **not** advance a turn (it
seeds a memory), so it is **not** refused with `409` while the loop runs.

**Errors** — the two family `404`s (same as the read routes): `unknown character:
'…'`, and `character '…' has no agent (and so cannot be spoken to)`. An empty
`text` is `422`.

```bash
curl -s -X POST http://127.0.0.1:8080/agents/gardener/say \
  -H 'Content-Type: application/json' \
  -d '{"text": "The market closes at noon.", "speaker": "Alistair"}'
```

### `POST /world/event`

Injects an **observable world event** (issue #369) that agent-bound characters in
range perceive. It appends a `GameEvent` to the world log, so agents who can see
`location` fold it into memory at their next `perceive()` (their next decision
point) — the same path a real action's aftermath travels. It is **also** appended
to the [change feed](#the-events-change-feed) as an `intervention` record, so a
viewer sees the event happen even before any agent reacts.

**Request body** — `WorldEventRequest`:

```json
{ "text": "A storm rolls in.", "location": "Field" }
```

`text` is a non-empty string. `location` is optional: with it, agents positioned
to see that location perceive the event; **omitted, it's a feed-only announcement**
no agent perceives (there is no origin room to see).

**Response** `200 OK` — `WorldEventResponse`:

| Field          | Type        | Meaning                                                       |
| -------------- | ----------- | ------------------------------------------------------------- |
| `turn`         | `int`       | The engine turn the event was injected on                     |
| `location`     | `str` \| `null` | Where it happens (echoed back)                            |
| `perceived_by` | `list[str]` | Agent-bound characters currently in range to perceive it — they fold it into memory at their next decision point (a prediction, not a promise: an agent that moves first may miss it). Empty for a feed-only announcement |
| `cursor`       | `int`       | The change-feed cursor of the `intervention` record           |

Applied **at the next tick boundary**, under the shared lock. A **given-but-unknown
`location` is a `404`** (`unknown location: '…'`) — a typo shouldn't silently
vanish. An empty `text` is `422`.

```bash
curl -s -X POST http://127.0.0.1:8080/world/event \
  -H 'Content-Type: application/json' \
  -d '{"text": "A storm rolls in.", "location": "Field"}'
```

## Live mode: the loop, the feed, run control (#349/#262)

Everything above is **command-driven**: the world only advances when a client
POSTs `/command`. Live mode adds the other shape a viewer needs — the sim
advancing **on its own** while frontends follow along:

- **The loop (#349).** Pass a *stepper* to enable it:
  `create_app(game, stepper=..., tick_seconds=0.1)` (or the same kwargs on
  `run()`). A stepper is any object implementing the small
  `backend.live.SimStepper` protocol — `step`, `meta()`, `tick()`, `reset()` —
  and the loop is deliberately **brain-agnostic**: a scripted stepper
  (`backend.live.ScriptedStepper`, free and offline), the Penn generative-agents
  tick, or a real-LLM brain later (#261) all drive the same loop and routes.
  Each `tick_seconds` the loop advances the stepper once **under the same lock
  every route uses**, then publishes at the tick boundary. With no stepper the
  app is byte-identical to the command-driven API above — the loop is opt-in.
  Try it with zero assets and zero keys:

  ```bash
  SIM_LIVE=1 SIM_TICK_SECONDS=0.5 uv run python -m backend.api
  ```

- **The feed: one log, two doors (#262).** Every published record lands in one
  append-only log with a **monotonic 1-based cursor** that never resets — not on
  `/reset`, not on eviction. `GET /events?since=N` is the stateless catch-up
  door; `WS /ws` is the push door. Same records, same cursor, which is what
  makes the reconnect recipe gap-free and duplicate-free:

  1. socket drops → remember the last `cursor` you applied;
  2. `GET /events?since=<last>` (or just reconnect `WS /ws?since=<last>`);
  3. re-attach — nothing missed, nothing doubled.

  The log is capped (`max_log_records`, default 10 000). Eviction never renumbers,
  so a too-stale client *detects* the gap — the first record returned has
  `cursor > since + 1` — and should re-sync from `GET /live` + `/world_state`.

  Record shapes (passed through as plain JSON; `kind` is the discriminator):

  ```json
  { "cursor": 12, "kind": "frame",  "step": 11, "agents": { "Maya Chen": { "x": 41, "y": 27, "act": "walking ...", "e": "🚶", "chat": null } } }
  { "cursor": 13, "kind": "status", "reason": "paused", "running": true, "paused": true, "step": 12 }
  { "cursor": 14, "kind": "engine", "step": 12, "event": { "channel": "narration", "text": "...", "actor": null, "turn": 12, "phase": null, "meta": {} } }
  { "cursor": 16, "kind": "intervention", "intervention": "say", "name": "Maya Chen", "speaker": "Alistair", "text": "The market closes at noon.", "turn": 12 }
  { "cursor": 17, "kind": "intervention", "intervention": "world_event", "text": "A storm rolls in.", "location": "The Willows Market", "turn": 12 }
  ```

  `frame` is one sim step in the **replay frame schema** — the same per-agent
  dict a baked `penn_replay.json` carries, so live and baked viewers share one
  contract. `status` marks run-state changes
  (`started|paused|resumed|reset|finished|stopped`). `engine` wraps a
  [change-feed record](#the-events-change-feed) the stepper drained from the
  engine during that tick (steppers opt in by implementing `drain_events()`).
  `intervention` records a human write ([`POST /agents/{name}/say`](#post-agentsnamesay)
  or [`POST /world/event`](#post-worldevent), #369), discriminated by its
  `intervention` field, so a viewer sees the same perturbation the operator made.
  (These record shapes are pinned by the forthcoming data contract, #305.)

  One `engine` payload has its own sub-contract: **`event.kind: "llm_call"`** —
  one record per LLM request (#398), the buffered copy of the row the terminal
  monitor prints (`backend/llm_monitor.py`: a flattened
  `usage.CallRecord.to_primitive()` plus the monitor's `role` / `call_no` /
  `cum_cost_usd` / `time` extras). A stepper publishes these by returning its
  monitor's `drain()` from `drain_events()`, the way the Penn runner does:

  ```json
  { "cursor": 15, "kind": "engine", "step": 12, "event": {
      "kind": "llm_call", "call_no": 7, "time": "12:05:02", "role": "decide",
      "actor": "Diego Torres", "turn": 118, "attempt": null, "prompt_sha256": null,
      "provider": "anthropic", "model": "claude-haiku-4-5",
      "input_tokens": 1088, "output_tokens": 102,
      "cache_creation_input_tokens": 912, "cache_read_input_tokens": 0,
      "cost_usd": 0.001238, "cum_cost_usd": 0.02141, "latency_ms": 731.2 } }
  ```

  `turn` / `actor` / `latency_ms` may be `null` (viewers show `-`); `actor` is
  the per-agent filter key. This stream is the per-request *detail* — the
  aggregate [`GET /usage`](#get-usage) summary the HUD polls is unchanged.

### `GET /live`

The handshake a live client reads once before following the feed:

```json
{ "enabled": true, "running": true, "paused": false, "step": 42, "cursor": 87,
  "tick_seconds": 0.1, "meta": { "tile_px": 32, "width": 245, "height": 279,
  "sec_per_step": 10, "start": "2023-02-13 08:00:00", "vision_r": 8,
  "personas": [ { "name": "Maya Chen", "emoji": "📚" } ] } }
```

`meta` is the stepper's own `meta()` blob, passed through opaquely — for the
Penn world it is the replay-meta shape, so a live viewer spawns its
agents exactly the way the baked-replay loader does. Always answers: with no
stepper it reports `enabled: false` (and `meta: null`), so a frontend can
cheaply probe whether live mode exists.

### `GET /events`

`GET /events?since=N` returns the retained records with `cursor > N`, oldest
first (`since` defaults to 0 = everything retained). An empty tail returns `[]`
immediately — this door never blocks; the socket is the door that waits.

```json
{ "latest_cursor": 87, "oldest_cursor": 1, "events": [ { "cursor": 86, "kind": "frame", "...": "..." } ] }
```

### `WS /ws`

The push door: after an optional `?since=N` replay of retained history, every
new record is pushed as one JSON text message the moment the loop appends it.

- **Auth** mirrors the HTTP routes: send `Authorization: Bearer <token>` in the
  handshake (Godot's `WebSocketPeer` can set handshake headers) **or** — because
  a browser `WebSocket` cannot set headers — pass `?token=<token>`. A bad token
  is refused with close code `1008` before the handshake completes.
- **Close codes**: `1008` bad token · `1009` inbound message over the body cap
  (the 64 KiB rule is enforced in-handler here, since the HTTP middleware never
  sees WebSocket traffic) · `1011` you fell behind the log's retention — re-sync
  via `GET /live` + `/events` and reconnect.
- Each client just tails the shared log at its own cursor, so a slow reader
  backpressures only itself.

### `POST /pause`, `/resume`, `/reset`

Run control over the loop. All three are deliberately **plain stateless HTTP**,
not socket messages — an emergency stop (#264) must work even when the socket is
wedged. Each is idempotent, appends a `status` record to the feed (so followers
learn about it like any other event), and returns the state after the change:

```json
{ "running": true, "paused": true, "step": 42, "cursor": 88 }
```

- `/pause` stops ticking; the loop task stays alive and every read keeps working.
- `/resume` starts ticking again.
- `/reset` rebuilds the sim to t0: `step` restarts at 0 but **the cursor keeps
  climbing** — a follower keys off the `status` record with `reason: "reset"`,
  never a cursor rewind.
- Without a stepper all three are `409` — there is no loop to control.
- A stepper may also declare its run **finished** (its `tick()` returns `None`,
  e.g. a fixed-length sim reached its last step): the loop auto-pauses and
  publishes `status(reason: "finished")`.

While the loop is enabled, running, and not paused, `POST /command` is refused
with `409` — a manual command would interleave with ticks mid-run. Pause first,
command, then resume (the #349 "decide and document" rule: pause-to-command
rather than silent interleaving).

### `GET /usage`

The stepper's `UsageLedger.summary()` — tokens and dollars — for the viewer's
run-monitor HUD (#264). Under the mock brain this reads ~0; real numbers arrive
when #261 swaps a live LLM into the loop.

```json
{ "kind": "summary", "available": true, "calls": 12, "total_cost_usd": 0.0031,
  "by_actor": { "Maya Chen": 0.0011 }, "input_tokens": 5210, "output_tokens": 340,
  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
  "over_budget": false, "max_cost_usd": 5.0, "remaining_budget_usd": 4.9969 }
```

`available: false` (with the same shape zeroed) when the stepper carries no
ledger, so a HUD renders $0.00 instead of erroring. `max_cost_usd` /
`remaining_budget_usd` appear only when the ledger was armed with a cost
ceiling (#183); `over_budget` flips when the kill-switch trips.

**Reading the two cache fields (#367).** `cache_creation_input_tokens` counts
tokens *written* to the prompt cache (billed ~1.25× input); `cache_read_input_tokens`
counts tokens *read back* from it (billed ~0.1×). Anthropic caches the stable
request prefix — an agent's system message (persona + rules) plus its tool
schema — so on a steady cast you'd expect the first call per agent to write and
every later one to read. Both stay **0** on the current Penn cast, and that's
correct, not a bug: prompt caching silently declines any prefix below the model's
minimum cacheable length (Haiku 4.5: 4096 tokens), and these personas render to
~200 tokens — ~20× under the floor. The `cache_control` marker is wired in
(`llm_client._cacheable_system`) and dormant; it starts writing/reading the day
the stable prefix grows past the floor (a richer persona, or a shared world/rules
preamble in the system block). To check *before* a run whether caching will fire,
and to prove the wiring end-to-end once a prefix does clear the floor, use
`backend/penn/cache_prefix_check.py` (offline go/no-go table; `--live` makes two
real calls and asserts write→read).

## Status codes

| Status | When                                                                                  |
| ------ | ------------------------------------------------------------------------------------- |
| `200`  | Success — **including a command the engine rejected** (surfaced as a `blocked` event) |
| `401`  | A token is configured and the `Authorization: Bearer <token>` header is missing/wrong |
| `404`  | Unknown path; on `/agents/{name}/{memory,knowledge,retrieval,plan,say}`, an unknown character or one with no agent; on `POST /world/event`, a given-but-unknown `location` |
| `409`  | Run control without a loop enabled; or `POST /command` while the loop is actively stepping (pause first) |
| `413`  | Request body exceeds the cap (64 KiB by default) — rejected before it is read         |
| `422`  | Invalid request body: missing / empty / non-string `command`, or malformed JSON       |
| `500`  | The engine raised while running the command (`{"detail": "engine error: ..."}`); the game's renderer is restored regardless |

## The `world_state` snapshot

`GET /world_state` and the `world_state` field of `POST /command` both return the
engine's typed snapshot (`text_adventure_games/world_state.py`). It is a pure,
deterministic tree — building it never mutates the game — and is **versioned** via
`schema_version` (currently `"1.0"`). The engine owns *topology* (the room graph,
who is where, what is blocked); a renderer derives *pixels* client-side (there are
no x/y coordinates — space is named-exit adjacency).

Top-level fields:

| Field            | Type                | Notes                                                        |
| ---------------- | ------------------- | ------------------------------------------------------------ |
| `schema_version` | `str`               | `"1.0"` — bump signals a shape change                        |
| `turn`           | `int`               | Current turn number                                          |
| `player`         | `str`               | The player character's name                                  |
| `clock`          | `object` or `null`  | `{time, period, day, hour, minute}` if the game has a clock  |
| `locations`      | `list`              | Every location (see below) — v1 is **omniscient**            |
| `characters`     | `list`              | Every character (see below)                                  |
| `events`         | `list`              | The newest 20 world events (see note below)                  |

- **location**: `name`, `description`, `visited`, `exits[]`
  (`{direction, to, blocked, description}`), `items[]`, `characters[]` (names),
  `properties`.
- **item**: `name`, `description`, `location`, `owner`, `container`, `quantity`,
  `affordances[]` (any of `drinkable`, `edible`, `flammable`, `gettable`,
  `wearable`, `wieldable`), `properties`, and `contents[]` (nested items,
  recursive).
- **character**: `name`, `description`, `persona`, `location`, `is_player`,
  `inventory[]`, `worn[]`, `wielded[]`, `goals[]`
  (`{description, type, done}`), `properties`.
- `properties` everywhere lists only the **truthy** flags, sorted (no `false`
  noise).

**Deliberately omitted in v1** (privacy / non-serializable / out of scope):
private agent cognition (a character's `knowledge` / `heard` / memory / beliefs —
exporting them into a shared, all-seeing snapshot would leak one agent's mind;
the exclude set is pinned per #185); runtime-only callables (behavior / agent /
triggers / recipes); and an exit's *unlock condition* (an exit reports only a
`blocked` boolean, never *why*). Memory is instead read through the **scoped,
per-persona** [`GET /agents/{name}/memory`](#get-agentsnamememory) (#298) — one
agent's mind at a time, on request — and stays out of the omniscient snapshot.

> **Two different `events`.** The snapshot's `events` is the world's *recent
> history* — each is `{turn, actor, action, summary, payload}`. The
> `POST /command` response's top-level `events` is the *change feed* for that one
> command, a different shape — see the next section.

## The `events` change feed

The `events` returned by `POST /command` are the structured **change feed** for
that command (from `reporting.JSONRenderer`). Where the snapshot says *"the world
is X"*, the feed says *"X just happened"*. Each record is:

```json
{ "channel": "narration", "text": "...", "actor": null, "turn": 0, "phase": null, "meta": {} }
```

| Field     | Meaning                                                                 |
| --------- | ----------------------------------------------------------------------- |
| `channel` | What kind of message — switch on this. e.g. `narration`, `blocked`      |
| `text`    | The human-readable message                                              |
| `actor`   | Who caused it (a character name), or `null`                             |
| `turn`    | The turn the message was emitted on                                     |
| `phase`   | Optional phase label                                                    |
| `meta`    | A JSON-safe dict of extra, channel-specific detail                      |

A turn boundary appears as a leaner record:
`{"channel": "turn_header", "turn": N, "time": "..."}`. Consumers switch on
`channel`: a `blocked` channel record is how an engine-rejected command shows up
(the request itself is still `200` — see [`POST /command`](#post-command)).

## The memory stream

The data model behind [`GET /agents/{name}/memory`](#get-agentsnamememory).
Each entry in `memories` is one formed memory (`MemoryEntry`):

| Field          | Type    | Meaning                                                             |
| -------------- | ------- | ------------------------------------------------------------------- |
| `kind`         | `str`   | `observation` \| `reflection` \| `plan` \| `chat` — panels colour-code it |
| `importance`   | `float` | The paper's 1–10 "poignancy" (1 = mundane, 10 = momentous), 1 decimal |
| `text`         | `str`   | The memory itself, first person                                     |
| `created_turn` | `int`   | The turn it was formed — the same axis as the response's `turn`     |

This one shape appears, byte-identical, in three places — the wire stays in
lock-step because all three come from the same formatter
(`backend/cognition.py::memories_for_frame`):

1. **this endpoint's** `memories` list (live, mid-run);
2. a baked replay's **`memory_streams[name]`** block
   (`godot-generative-agents/backend/penn/generate_penn_replay.py`) and per-frame
   `memories` shorthand;
3. the frontend type **`MemoryRecord`**
   (`godot-generative-agents/web/src/types/replay.ts`).

**It is a lean projection, not the whole record.** The engine's canonical
`MemoryRecord` (`text_adventure_games/memory.py`, spec:
`docs/design/agent-memory.md` §4) also carries `id`, `last_accessed_turn`
(recency decay), `actor`, `source_event_ids` (provenance), `tags`, `embedding`
(semantic retrieval, #76), and `metadata`. Those stay server-side: they power
retrieval scoring (recency × importance × relevance), not rendering. The
persistence layer (`backend/run_store.py`, #304) stores rows as
`memories(run_id, agent, record_id, kind, importance, created_turn, text,
embedding, extra)` — the four wire fields map 1:1 onto queryable columns, the
richer fields ride the `extra` JSON (embeddings a float32 BLOB), and a stored
record rehydrates losslessly via `MemoryRecord.from_primitive`.

**How a stream fills up.** Memories are written by the sim loop (not by the LLM
provider directly), so the shape is identical whether the brain is the mock or a
real model: seeded relationship observations at turn 0 (`backend/seed.py`,
importance 3.0), the day's plan (5.0), perceived events and presence sightings
("I see X nearby.", 1.0), the agent's own action outcomes (2.0), and — with a
real LLM — reflections (5.0) and conversation lines (`chat`, 4.0). A brand-new
agent legitimately returns `"memories": []` until the loop writes something.

**Forward pointers.** #305 pins this shape as the versioned wire contract; #304
backs the read with a store instead of live objects; #306 scopes it under a run
id (`/runs/{run_id}/agents/{name}/memory`). Today it reads the in-process
`AgentMemory` under the same lock `POST /command` mutates under, so `turn` and
`memories` are one atomic snapshot.

## The belief set

The data model behind [`GET /agents/{name}/knowledge`](#get-agentsnameknowledge).
Each entry in `beliefs` is one `Belief` — **the exact shape
`Knowledge.to_primitive()` emits** (`text_adventure_games/knowledge.py`; design
doc `docs/design/implemented/agent-knowledge.md`), so the wire *is* the save-file
shape and there is no second schema to drift:

| Field          | Type            | Meaning                                                                    |
| -------------- | --------------- | -------------------------------------------------------------------------- |
| `text`         | `str`           | The belief in plain language, first person                                 |
| `topic`        | `str` \| `null` | Optional lookup key; a belief whose `topic` matches a Thing's `secret_topic` unlocks perception of that hidden Thing |
| `learned_turn` | `int` \| `null` | `null` for a prior known up front; the turn number for one learned during play |

There is deliberately **no `confidence` or `source`** field: the "uncertain or
wrong" axis lives in the `text` itself. Beliefs are a flat list, in the order the
agent acquired them.

**Memory vs. knowledge.** These are the two halves of an agent's private
cognition, and the two `/agents/{name}/...` reads mirror them exactly:

| | Memory (#298) | Knowledge (#348) |
| --- | --- | --- |
| What it is | the episodic *log* — what was seen or done | the current *world-model* — what's believed true now |
| Lives on | `agent.memory` (`memory.py`) | `character.knowledge` (`knowledge.py`) |
| Grows via | the sim loop appending records | seeded priors (#79) + `Knowledge.learn()` during play |
| Authority | — | context only; the world graph stays the source of truth |

**How a belief set fills up.** Seeded once at t0 from the persona's *partial*
spatial tree (`backend/seed.py::seed_spatial_knowledge`, #79 — one belief per
known place, `learned_turn=null`), then extended during play whenever the agent
learns something (`Knowledge.learn(text, turn)` stamps `learned_turn`). Knowledge
is **partial by design**: an agent only believes in the places its own tree
lists, which is exactly the partial-knowledge story the Penn sim trades on — a
viewer can now answer "does this agent even know that place exists?". On a fresh
checkout the ~38 MB upstream assets are absent and seeding no-ops, so the set is
legitimately empty (`"beliefs": []`), not an error.

**Forward pointers.** Same trajectory as the memory read: a persistent store
(#304) and run-scoping (`/runs/{run_id}/agents/{name}/knowledge`, #306) come
later. Today it reads the in-process `Knowledge` under the same lock
`POST /command` mutates under, so `turn` and `beliefs` are one atomic snapshot.

## The daily plan

The data model behind [`GET /agents/{name}/plan`](#get-agentsnameplan). The nested
`plan` object is **the exact shape `DailyPlan.to_primitive()` emits**
(`text_adventure_games/planning.py`; design doc `docs/design/daily-planning.md`) —
the same object the bake writes to `personas/<name>/daily_plan.json`, so the wire
*is* the baked artifact and there is no second schema to drift. It holds the plan
at three altitudes plus a revision counter:

| Field      | Type          | Meaning                                                                 |
| ---------- | ------------- | ----------------------------------------------------------------------- |
| `day`      | `DayBlock[]`  | The broad day outline — `{label, summary}` phrases ("morning": "open the cafe") |
| `hours`    | `HourBlock[]` | The hourly schedule — `{start_hour, summary}`, one per in-sim hour       |
| `stops`    | `Stop[]`      | The concrete minute plan the step loop walks — `{place, activity, emoji, steps}` |
| `revision` | `int`         | `0` when first generated; bumped on each mid-run replan                  |

A `Stop`'s `place` must resolve to a known `Location` name when executed;
`activity` is free text; `emoji` is an optional glyph a viewer renders; `steps` is
how many sim steps to perform the activity for (`null` = stay indefinitely). The
step loop only consumes `stops`; `day`/`hours` are the higher-altitude reasoning,
kept so retrieval, reflection, and revision see the agent's intentions at every
level (they are also written into the memory stream as `plan`-kind records).

**Why `revision` is also at the top level.** The response lifts `plan.revision`
out to a sibling field so a client can **poll `revision` cheaply and refetch the
whole plan only when it changes** — a mid-run replan (`maybe_revise_plan` →
`planning.replace_tail`) preserves the already-executed head of `stops` and
rewrites the tail, bumping `revision`. The top-level value always equals the
nested `plan.revision`.

**Memory vs. knowledge vs. plan.** The three halves — er, thirds — of an agent's
private cognition, one `/agents/{name}/...` read each: memory is what it
*remembers* (#298), knowledge what it *believes* (#348), plan what it *intends*
(#347). An agent whose brain never planned has no plan yet, so the read is a `200`
with `"plan": null` (like an empty memory stream is `200 []`), never a `404`.

**Forward pointers.** Same trajectory as the sibling reads: a persistent store
(#304) and run-scoping (`/runs/{run_id}/agents/{name}/plan`, #306) come later.
Today it reads the in-process `DailyPlan` under the same lock `POST /command`
mutates under, so `turn`, `revision`, and `plan` are one atomic snapshot.

## Authentication & security

Issue #186. The defaults are tuned for **local development**:

- **Loopback + unauthenticated by default.** Bound to `127.0.0.1`, the server is
  only reachable from the same machine, so it ships with no token. The loopback
  hosts that never require auth are `127.0.0.1`, `localhost`, and `::1`.
- **Binding a non-loopback host requires a token.** `run()` refuses to start on a
  non-loopback host unless a token is provided — via the `SIM_API_TOKEN` env var
  or the `auth_token=` argument — so the API is never *silently* exposed
  unauthenticated:

  ```text
  RuntimeError: refusing to bind non-loopback host '0.0.0.0' without an auth
  token; set SIM_API_TOKEN (or pass auth_token=...) first -- see issue #186
  ```

- **When a token is set, every request must carry it** as a bearer header:

  ```bash
  export SIM_API_TOKEN=s3cret
  curl -s http://127.0.0.1:8080/health -H "Authorization: Bearer $SIM_API_TOKEN"
  ```

  A missing or wrong header gets `401 {"detail": "invalid or missing token"}`. The
  gate applies to **all six** endpoints.

- **Request-body cap.** A request whose declared `Content-Length` exceeds
  `max_body_bytes` (**64 KiB** by default) is rejected with `413` *before the body
  is read*, so a hostile `Content-Length` can't be used to exhaust memory. A
  legitimate command is a tiny JSON object, so nothing real approaches the cap.

> [!WARNING]
> Loopback + no auth is safe only because nothing off-machine can reach it. Behind
> a reverse proxy, on `0.0.0.0`, or anywhere reachable by others, set
> `SIM_API_TOKEN` and serve over TLS. This server has no rate limiting, no
> per-user accounts, and a single shared token — it is an internal seam, not a
> public API.

## CORS

So the local Godot/companion frontends can call the API from a browser
without it being open to arbitrary sites, CORS is scoped to **localhost origins
only**: any `http(s)://localhost` or `http(s)://127.0.0.1` origin (any port), for
the `GET` and `POST` methods.

## Quick start (a full curl walkthrough)

```bash
# 1. install the server extra and start the demo world
uv sync --extra server
uv run python -m backend.api            # http://127.0.0.1:8080  (OpenAPI at /docs)

# --- in another shell ---

# 2. liveness + current turn
curl -s http://127.0.0.1:8080/health
# {"ok":true,"turn":0}

# 3. the whole world as JSON
curl -s http://127.0.0.1:8080/world_state

# 4. run a command -> events + the new snapshot + game_over
curl -s -X POST http://127.0.0.1:8080/command \
  -H 'Content-Type: application/json' \
  -d '{"command": "go north"}'

# 5. a command the engine rejects is still 200 -- look for a "blocked" event
#    (the demo map has no east exit, so this is always rejected)
curl -s -X POST http://127.0.0.1:8080/command \
  -H 'Content-Type: application/json' \
  -d '{"command": "go east"}'
# -> {"events":[{"channel":"blocked","text":"Field does not have an exit 'east'",...}],...}

# 6. one agent's memory stream so far (#298) -- the demo gardener ships with
#    three seeded memories; "turn" tells you when the stream was snapshotted
curl -s http://127.0.0.1:8080/agents/gardener/memory
# {"persona":"gardener","turn":2,"count":3,"memories":[{"kind":"observation",...}]}
curl -s 'http://127.0.0.1:8080/agents/gardener/memory?kind=plan&limit=20'  # a slice (#345)
curl -s 'http://127.0.0.1:8080/agents/gardener/memory?since_turn=1'        # only what's new
# -> adds "total":3 alongside "count" so a UI can show "showing count of total"
curl -s http://127.0.0.1:8080/agents/nobody/memory      # 404: unknown character
curl -s http://127.0.0.1:8080/agents/player/memory      # 404: no agent bound

# 7. the same agent's belief set -- its world-model (#348); the demo gardener
#    ships with a prior (learned_turn null) and one learned mid-run
curl -s http://127.0.0.1:8080/agents/gardener/knowledge
# {"persona":"gardener","turn":0,"count":2,"beliefs":[{"text":"The field lies ...","topic":"forest","learned_turn":null},...]}
curl -s 'http://127.0.0.1:8080/agents/gardener/knowledge?topic=forest'  # narrow by topic

# 8. with auth (only needed when SIM_API_TOKEN is set / non-loopback bind)
curl -s http://127.0.0.1:8080/health -H "Authorization: Bearer $SIM_API_TOKEN"

# --- live mode (#349/#262): restart the demo with the loop on ---
SIM_LIVE=1 SIM_TICK_SECONDS=0.5 uv run python -m backend.api

# 9. the handshake, then the feed so far
curl -s http://127.0.0.1:8080/live
curl -s 'http://127.0.0.1:8080/events?since=0'

# 10. follow the push door (any WS client; python -m websockets ships with the
#     server extra), then pause/resume/reset from another shell
uv run python -m websockets ws://127.0.0.1:8080/ws
curl -s -X POST http://127.0.0.1:8080/pause
curl -s -X POST http://127.0.0.1:8080/resume
curl -s http://127.0.0.1:8080/usage

# 11. watch the world advance with no one POSTing commands: /health's turn
#     climbs, and the gardener's memory stream grows on its own (#349)
curl -s http://127.0.0.1:8080/agents/gardener/memory | head -c 200
```

Prefer to click around? Open **http://127.0.0.1:8080/docs** for the interactive
Swagger UI generated from the same code.

## Not yet implemented

Deferred (don't expect these yet):

- a **real-LLM brain** inside the live loop — #261; today's steppers are
  scripted/mock (that's the point: the whole live surface works offline);
- a persistent store behind the private-cognition reads, and run-scoping
  (`/runs/{run_id}/agents/{name}/{memory,knowledge,plan}`) — #304/#306; today
  `/agents/{name}/memory`, `/agents/{name}/knowledge`, and `/agents/{name}/plan`
  read the live in-process `AgentMemory` / `Knowledge` / `DailyPlan`;
- migrating the Flask webapp and the web companion from file-based replay to
  thin clients of this API (the Godot viewer's live client is #263, built on
  this feed).

---

*Tests that double as executable examples live in
[`tests/test_api.py`](../tests/test_api.py) — they exercise every status code and
the security posture above. The architecture rationale is in the repo's
`CLAUDE.md` ("Backend HTTP API").*

## The replay data-contract (#305)

The replay schema — `meta` / `AgentFrame` / `MemoryRecord` / the whole
`penn_replay.json` — is pinned in two backend modules:

- **`backend/contract.py`** — the schema prose, `SCHEMA_VERSION`, and the
  pinned field orders (`AGENT_FRAME_FIELDS`, `MEMORY_RECORD_FIELDS`). Field
  order is part of the contract: the bake's `json.dump` serializes insertion
  order and #297's acceptance is a byte-identical replay. Deliberately
  **stdlib-only** so the base-env bake can import it (pydantic only arrives
  with the `server`/`llm` extras).
- **`backend/contract_models.py`** — the enforcing Pydantic models
  (`extra="forbid"`). One `Meta` covers both surfaces: the bake knows `steps`
  and has no `llm`; a live run is the reverse.

Both emitters — `penn/generate_penn_replay.py` and the live
`serve_penn.PennStepper.meta()` — stamp `schema_version` as `meta`'s first
key. **Bump `SCHEMA_VERSION` on any breaking change** (field removed, renamed,
retyped); additive optional fields don't bump it.

`web/src/types/replay.ts` is a **mirror**, not the definition —
`tests/test_replay_contract.py` holds the two field-for-field in lock-step,
alongside conformance tests that validate the real bake output and live meta.
The RunStore (`backend/run_store.py`, #304) writes `frames.jsonl` lines in the
`dict[str, AgentFrame]` shape — checked structurally at write time, since the
base env has no pydantic — and the #307 live-run exporter (emits a `Replay`)
constructs against these models.

## RunStore: durable runs (#304)

`backend/run_store.py` — SQLite + JSONL, zero extra dependencies:

    godot-generative-agents/runs/        # git-ignored
      sim.db                             # runs + memories tables
      <run_id>/manifest.json             # the run's meta() blob
      <run_id>/frames.jsonl              # line N = the step-N frame (#305 shape)

Two opt-in producers: `serve_penn.py --persist` records a live run as it ticks
(each `POST /reset` closes the current run and opens a new id), and
`generate_penn_replay.py --persist [--runs-dir DIR]` mirrors a bake after the
fact — round-trip tests pin that a persisted bake equals its replay file.
Reads: `read_frames`, `memories_for` (the lean wire projection), and
`query_memories`, which rehydrates rows into engine `MemoryRecord`s and
delegates to `AgentMemory.retrieve` — store queries score exactly like the
sim. Consumers on deck: the #307 live→replay exporter and the #306
run-lifecycle endpoints.
