# Backend HTTP API

The `backend` package is **agent-sandbox's one canonical backend seam**: a small
[FastAPI](https://fastapi.tiangolo.com/) app (`backend/api.py`) that serves *any*
engine `Game` over HTTP. Every out-of-process frontend — a Godot/2D renderer, the
Smallville/Phaser viewer, the web inspection companion — polls the **same** three
endpoints here instead of embedding Python or baking its own data dump. The engine
and any LLM stay server-side; the frontend just reads JSON.

> This document is the human-readable endpoint reference. The interactive,
> machine-readable contract is auto-served at **`/docs`** (Swagger UI) and
> **`/openapi.json`** whenever the server is running — that is the source of truth
> GDScript (Godot) and TS/JS (Phaser, companion) clients generate against. This
> page exists so you can read the whole API end-to-end without first starting it.

It documents the API as shipped in PR #196 (issues #179, #186, #185): the
**snapshot + change-feed contract**. See [Not yet implemented](#not-yet-implemented)
for what is deliberately deferred.

> [!WARNING]
> The API is **unauthenticated and bound to loopback by default** — safe for local
> development only. Do not expose this server to an untrusted network as-is. See
> [Authentication & security](#authentication--security).

## Contents

- [Install & run](#install--run)
- [Endpoint reference](#endpoint-reference)
  - [`GET /health`](#get-health)
  - [`GET /world_state`](#get-world_state)
  - [`POST /command`](#post-command)
- [Status codes](#status-codes)
- [The `world_state` snapshot](#the-world_state-snapshot)
- [The `events` change feed](#the-events-change-feed)
- [Authentication & security](#authentication--security)
- [CORS](#cors)
- [Quick start (a full curl walkthrough)](#quick-start-a-full-curl-walkthrough)
- [Not yet implemented](#not-yet-implemented)

## Install & run

FastAPI is an **optional** dependency. Install it (and `uvicorn`) with the
`server` extra:

```bash
uv sync --extra server          # adds fastapi + uvicorn (pydantic rides along)
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
benchmark task, or the live Penn/Smallville sim. Access to the game is serialized
with a lock, since FastAPI runs the sync handlers in a thread pool and
`POST /command` mutates state.

## Endpoint reference

Three endpoints. `GET`s are read-only; `POST /command` advances the game by
exactly one command (one turn).

| Method | Path           | Purpose                                            |
| ------ | -------------- | -------------------------------------------------- |
| `GET`  | `/health`      | Liveness + the current turn (cheap poll)           |
| `GET`  | `/world_state` | The full, typed world snapshot                     |
| `POST` | `/command`     | Run one command → events + new snapshot            |

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
      "characters": ["player"],
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

## Status codes

| Status | When                                                                                  |
| ------ | ------------------------------------------------------------------------------------- |
| `200`  | Success — **including a command the engine rejected** (surfaced as a `blocked` event) |
| `401`  | A token is configured and the `Authorization: Bearer <token>` header is missing/wrong |
| `404`  | Unknown path                                                                          |
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
`blocked` boolean, never *why*).

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
  gate applies to **all three** endpoints.

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

So the local Godot/Phaser/companion frontends can call the API from a browser
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

# 6. with auth (only needed when SIM_API_TOKEN is set / non-loopback bind)
curl -s http://127.0.0.1:8080/health -H "Authorization: Bearer $SIM_API_TOKEN"
```

Prefer to click around? Open **http://127.0.0.1:8080/docs** for the interactive
Swagger UI generated from the same code.

## Not yet implemented

This PR ships the **snapshot + change-feed contract** only. Deferred to the
live-game tranche (don't expect these yet):

- a self-stepping autonomous loop and a pull poll (`/agent_act` / `next`,
  `/events?since=`);
- run control (`/pause`, `/resume`, `/reset`);
- migrating the Flask webapp, the web companion, and Godot from file-based replay
  to thin clients of this API.

---

*Tests that double as executable examples live in
[`tests/test_api.py`](../tests/test_api.py) — they exercise every status code and
the security posture above. The architecture rationale is in the repo's
`CLAUDE.md` ("Backend HTTP API").*
