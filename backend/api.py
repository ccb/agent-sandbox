"""Headless HTTP API that drives a :class:`~text_adventure_games.games.Game`
from an out-of-process front-end (issue #179, unifying #177).

This is the project's **one canonical backend seam**: a 2D/Godot renderer, the
Smallville/Phaser viewer, or the web inspection companion all poll the *same*
endpoints here rather than each embedding Python or baking its own data dump. The
engine and any LLM stay server-side; the frontend just reads JSON.

    from backend.api import run
    run(build_game(), port=8080)     # then: GET /world_state, POST /command

Endpoints (composing the engine's world-state export #90 + change feed):

* ``GET  /health``       -> ``{"ok": true, "turn": N}``
* ``GET  /world_state``  -> the typed ``WorldState`` snapshot
* ``GET  /agents/{name}/memory`` -> the memory stream *name* has formed so far
  (issue #298) -- the live counterpart of the replay file's ``memory_streams``.
* ``POST /command``      body ``{"command": "go north"}`` -> the resulting
  change-feed ``events``, the new ``world_state`` snapshot, and ``game_over``.

``GET`` requests are read-only; ``POST /command`` advances the game by exactly
one command. The interactive OpenAPI contract is served at ``/docs`` -- that is
the single source of truth GDScript (Godot) and TS/JS (Phaser, companion)
clients generate against.

Security posture (issue #186). The API is **unauthenticated and bound to
loopback (127.0.0.1) by default** -- safe for local development only. Before it
binds any non-loopback host, :func:`run` requires an auth token
(``SIM_API_TOKEN``); requests must then send ``Authorization: Bearer <token>``.
A request body larger than ``max_body_bytes`` (64 KiB by default) is rejected
with ``413`` before it is read, so an oversized ``Content-Length`` can't be used
to exhaust memory. Do not expose this server to an untrusted network as-is.

FastAPI is an optional dependency: install it with ``uv sync --extra server``.
"""

from __future__ import annotations

import os
import threading

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from text_adventure_games.reporting import JSONRenderer

from .smallville_agents import memory_stream_for_persona

# Hosts that never need auth: a server bound here is only reachable from the
# same machine, so the loopback-only default is safe without a token (#186).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# A command request is a tiny JSON object; nothing legitimate approaches this.
# Capping it (#186) turns a hostile ``Content-Length`` into a clean 413 instead
# of an unbounded read.
DEFAULT_MAX_BODY_BYTES = 64 * 1024


class CommandRequest(BaseModel):
    """The body of ``POST /command``: the one command to run this turn."""

    command: str = Field(..., min_length=1, description="e.g. 'go north'")


class CommandResponse(BaseModel):
    """The result of one command: what happened, the new world, and whether the
    game ended. ``events`` are change-feed records (see ``reporting.JSONRenderer``)
    and ``world_state`` is the typed snapshot (see ``world_state.WorldState``);
    both are passed through as plain JSON, so they stay in lock-step with the
    engine's own shapes without a second schema to maintain here."""

    events: list[dict]
    world_state: dict
    game_over: bool


class MemoryEntry(BaseModel):
    """One formed memory, in the exact wire shape the replay bake emits.

    This is ``smallville_agents.memories_for_frame``'s dict -- the same four
    fields that ``penn_replay.json``'s ``memory_streams`` block and the
    frontend's ``replay.ts`` ``MemoryRecord`` carry. It is a lean projection of
    the engine's fuller ``MemoryRecord`` (``text_adventure_games/memory.py``);
    see ``backend/README.md`` ("The memory stream") for the full field mapping.
    Issue #305 will pin this as a versioned contract; #304 will back it with a
    persistent store."""

    kind: str = Field(..., description="observation | reflection | plan | chat")
    importance: float = Field(
        ..., description="the paper's 1-10 poignancy, rounded to 1 decimal"
    )
    text: str = Field(..., description="the memory itself, first person")
    created_turn: int = Field(..., description="the turn the memory was formed")


class MemoryStreamResponse(BaseModel):
    """``GET /agents/{name}/memory``: everything *name* remembers so far.

    ``memories`` is chronological (append order), byte-identical to the baked
    ``memory_streams[name]`` for the same run. ``turn`` is the engine turn the
    stream was snapshotted at -- the same counter ``GET /health`` reports and
    the axis ``created_turn`` is measured on -- so a client can align the
    stream with the change feed."""

    persona: str
    turn: int
    count: int = Field(..., description="== len(memories)")
    memories: list[MemoryEntry]


def run_command(game, command: str, lock: threading.Lock | None = None) -> dict:
    """Advance *game* by one command and return the :class:`CommandResponse` dict.

    Mirrors the engine's renderer-swap pattern: capture this command's output as a
    change feed, then restore whatever renderer was installed so the API never
    disturbs the game's own configuration -- even if the engine raises (the caller
    turns that into a 500). Pure aside from the single ``do_command`` it runs.
    Pass *lock* to serialize access when several request threads share one game."""
    held = lock if lock is not None else _NULL_CONTEXT
    with held:
        feed = JSONRenderer()
        previous = game.parser.renderer
        game.parser.set_renderer(feed)
        try:
            game.do_command(command)
        finally:
            game.parser.set_renderer(previous)
        return {
            "events": feed.drain(),
            "world_state": game.to_world_state().to_jsonable(),
            "game_over": game.is_game_over(),
        }


class _NullContext:
    """A no-op context manager, so :func:`run_command` needs no ``if lock``."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_NULL_CONTEXT = _NullContext()


class _BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject any request whose declared body exceeds the cap with 413 (#186)."""

    def __init__(self, app, max_body_bytes: int):
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next):
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit():
            if int(declared) > self.max_body_bytes:
                return JSONResponse(
                    {"detail": "request body too large"}, status_code=413
                )
        return await call_next(request)


def create_app(
    game,
    *,
    auth_token: str | None = None,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> FastAPI:
    """Build the FastAPI app serving *game*.

    *game* is any engine :class:`~text_adventure_games.games.Game` -- Action
    Castle, a benchmark task, or the live Penn/Smallville sim -- so this one app
    is the seam for every world. If *auth_token* is set, every request must carry
    ``Authorization: Bearer <token>``; left ``None`` (the loopback-only default)
    the API is open. Access to *game* is serialized with a lock, since FastAPI
    runs the sync handlers in a thread pool and ``do_command`` mutates state."""
    app = FastAPI(
        title="agent-sandbox backend",
        summary="Headless HTTP seam over a text-adventure Game (issue #179).",
    )
    lock = threading.Lock()

    # Body-size cap first (#186b), then CORS. CORS is scoped to localhost origins
    # so the local Godot/Phaser/companion frontends can call us from a browser
    # without opening the API to arbitrary sites.
    app.add_middleware(_BodySizeLimitMiddleware, max_body_bytes=max_body_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def require_auth(authorization: str | None = Header(default=None)) -> None:
        """Gate every request when a token is configured (no-op otherwise, #186c)."""
        if auth_token is None:
            return
        expected = f"Bearer {auth_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="invalid or missing token")

    @app.get("/health")
    def health(_: None = Depends(require_auth)) -> dict:
        """Liveness + the current turn -- a cheap poll that never mutates."""
        with lock:
            return {"ok": True, "turn": game.turn}

    @app.get("/world_state")
    def world_state(_: None = Depends(require_auth)) -> dict:
        """The typed, deterministic snapshot of the whole world (#90)."""
        with lock:
            return game.to_world_state().to_jsonable()

    @app.get("/agents/{name}/memory", response_model=MemoryStreamResponse)
    def agent_memory(name: str, _: None = Depends(require_auth)):
        """The memory stream *name* has formed *so far*, read mid-run (#298).

        Pull-only: the sim never pushes streams anywhere; a client fetches one
        when a user opens the agent's panel. The ``world_state`` snapshot
        deliberately omits private cognition (#185) -- this per-persona route is
        the one sanctioned way to read a single agent's mind. Unknown character
        names 404; so does a character with no agent bound (the player, a
        scripted-behavior NPC) -- such a character will never have a stream,
        which is different from an agent that simply hasn't formed memories yet
        (a 200 with ``memories: []``). Everything is read under the shared lock
        so ``turn`` and ``memories`` are one atomic snapshot. Once a persistent
        store exists this becomes a store-backed query scoped under a run id
        (#304/#306)."""
        with lock:
            char = game.characters.get(name)
            if char is None:
                raise HTTPException(
                    status_code=404, detail=f"unknown character: {name!r}"
                )
            if char.agent is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"character {name!r} has no agent (and so no memory stream)",
                )
            # response_model drops any field not in MemoryEntry, so if the
            # formatter ever grows a field the wire contract stays frozen (#305).
            memories = memory_stream_for_persona(char.agent)
            return {
                "persona": name,
                "turn": game.turn,
                "count": len(memories),
                "memories": memories,
            }

    @app.post("/command", response_model=CommandResponse)
    def command(req: CommandRequest, _: None = Depends(require_auth)):
        """Run exactly one command and return events + the new snapshot.

        A command the *engine* rejects (a failed precondition) is still a
        successful request: 200, with the rejection surfaced as a ``blocked``
        event. A 4xx means a bad *request* (malformed/empty body), not a rejected
        *command*."""
        try:
            return run_command(game, req.command.strip(), lock)
        except Exception as exc:  # an engine bug shouldn't drop the connection
            raise HTTPException(status_code=500, detail=f"engine error: {exc}")

    return app


def run(
    game,
    host: str = "127.0.0.1",
    port: int = 8080,
    auth_token: str | None = None,
) -> None:
    """Serve *game* over HTTP until interrupted (Ctrl-C).

    Defaults to loopback with no auth (local dev). Binding a non-loopback host
    requires a token -- passed here or via the ``SIM_API_TOKEN`` env var -- or
    this refuses to start, so the API is never silently exposed unauthenticated
    (issue #186c)."""
    import uvicorn

    auth_token = auth_token or os.environ.get("SIM_API_TOKEN")
    if host not in LOOPBACK_HOSTS and not auth_token:
        raise RuntimeError(
            f"refusing to bind non-loopback host {host!r} without an auth token; "
            "set SIM_API_TOKEN (or pass auth_token=...) first -- see issue #186"
        )
    uvicorn.run(create_app(game, auth_token=auth_token), host=host, port=port)


def _demo_game():
    """A tiny two-room world so ``python -m backend.api`` is runnable with no
    assets -- enough to exercise the contract and ``/docs``. Real worlds (the
    Penn/Smallville sim) are served by passing your own ``Game`` to :func:`run`.

    The gardener NPC carries three hand-seeded memories (the same
    ``AgentMemory`` a live LLM agent accrues into) so
    ``GET /agents/gardener/memory`` (#298) has something to show without any
    provider key. In a real sim the loop writes the stream instead -- seeded
    plans, perceived events, action outcomes, reflections."""
    from text_adventure_games import games, things
    from text_adventure_games.npc import ScriptedAgent

    field = things.Location("Field", "An open field full of tall grass.")
    forest = things.Location("Forest", "A dense, dark wood.")
    field.add_connection("north", forest)
    field.add_item(things.Item("flower", "a red flower", "It smells sweet."))
    player = things.Character("player", "you", "I explore the world.")

    gardener = things.Character("gardener", "a wizened gardener", "I tend this field.")
    field.add_character(gardener)
    # A do-nothing agent whose *memory* is real: the rule always returns None,
    # so the gardener never acts, but the stream reads back over HTTP.
    agent = ScriptedAgent(lambda observation: None, persona=gardener.persona)
    agent.memory.owner = gardener.name
    agent.memory.add_observation(
        "The flowers by the north path bloomed overnight.", turn=0, importance=3.0
    )
    agent.memory.add_observation(
        "A stranger wandered into the field.", turn=0, importance=2.0
    )
    agent.memory.add_plan("Water the tall grass before midday.", turn=0)
    gardener.set_agent(agent)

    return games.Game(field, player, characters=[gardener])


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    print(f"serving demo world on http://{host}:{port}  (OpenAPI at /docs)")
    run(_demo_game(), host=host, port=port)
