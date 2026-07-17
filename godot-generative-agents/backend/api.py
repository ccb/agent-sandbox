"""Headless HTTP API that drives a :class:`~text_adventure_games.games.Game`
from an out-of-process front-end (issue #179, unifying #177).

This is the project's **one canonical backend seam**: a 2D/Godot renderer or the
web inspection companion poll the *same*
endpoints here rather than each embedding Python or baking its own data dump. The
engine and any LLM stay server-side; the frontend just reads JSON.

    from backend.api import run
    run(build_game(), port=8080)     # then: GET /world_state, POST /command

Endpoints (composing the engine's world-state export #90 + change feed):

* ``GET  /health``       -> ``{"ok": true, "turn": N}``
* ``GET  /world_state``  -> the typed ``WorldState`` snapshot
* ``GET  /agents``       -> the roster of agent-bound characters, with a cheap
  memory summary each (issue #344) -- the discovery companion to the route below.
* ``GET  /agents/{name}/memory`` -> the memory stream *name* has formed so far
  (issue #298) -- the live counterpart of the replay file's ``memory_streams``;
  optional ``?since_turn=`` / ``?kind=`` / ``?limit=`` select a slice (issue #345).
* ``GET  /agents/{name}/knowledge`` -> what *name* *believes about the world*
  (issue #348) -- the seeded priors + anything learned since, the sibling read
  to memory (memory is the episodic log; knowledge is the current world-model).
* ``GET  /agents/{name}/retrieval?q=`` -> the memories *name*'s retriever would
  surface for a cue, scored most-useful-first but **not attended to** (issue
  #346) -- a read-only (``touch=False``) window onto decision-time retrieval.
* ``GET  /agents/{name}/plan`` -> what *name* *intends to do today* (issue #347)
  -- the live counterpart of the baked ``daily_plan.json``: the day outline,
  hourly schedule, and stops, plus a ``revision`` counter that bumps on replan.
* ``POST /command``      body ``{"command": "go north"}`` -> the resulting
  change-feed ``events``, the new ``world_state`` snapshot, and ``game_over``.

When a :class:`~backend.live.SimStepper` is injected (``create_app(stepper=...)``),
the app also runs the **self-stepping live loop** (#349) and serves the live
surface (#262) a following viewer needs:

* ``GET  /live``         -> the handshake: loop state + the stepper's ``meta()``.
* ``GET  /events?since=N`` -> the change-feed records after cursor ``N`` -- the
  HTTP catch-up door (reconnect/backfill, curl, tests).
* ``WS   /ws``           -> the push door: every record the loop appends, the
  moment it lands. Same records, same cursor, so a client that loses the socket
  backfills ``?since=<last seen>`` and re-attaches with no gap and no duplicate.
* ``POST /pause`` / ``/resume`` / ``/reset`` -> run control over the loop.
* ``GET  /usage``        -> the stepper's ``UsageLedger`` summary (tokens/cost)
  for the viewer's run-monitor HUD (#264) -- ~0 under the mock brain.

The **write-side interventions** (issue #369) let a human touch a running sim --
the mutating siblings of the read family, applied at the next tick boundary:

* ``POST /agents/{name}/say`` body ``{text, speaker?}`` -> speak to an agent; the
  utterance lands in its memory as a ``chat`` record it perceives next decision.
* ``POST /world/event`` body ``{text, location?}`` -> inject an observable event
  agents in range perceive, also appended to the change feed so viewers see it.

``GET`` requests are read-only; ``POST /command`` advances the game by exactly
one command (and is refused with ``409`` while the live loop is actively
stepping -- pause first). The interactive OpenAPI contract is served at
``/docs`` -- that is the single source of truth GDScript (Godot) and TS/JS
(Phaser, companion) clients generate against.

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

import asyncio
import contextlib
import json
import os
import secrets
import signal
import threading

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from text_adventure_games.events import GameEvent
from text_adventure_games.memory import MemoryKind
from text_adventure_games.reporting import JSONRenderer

from .env import load_dotenv
from .live import EventLog, LiveRunController, SimStepper, run_loop
from .cognition import (
    kind_counts_for_persona,
    memories_for_frame,
    memory_stream_for_persona,
)

# Hosts that never need auth: a server bound here is only reachable from the
# same machine, so the loopback-only default is safe without a token (#186).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _terminate_process() -> None:
    """The default ``POST /shutdown`` action: SIGINT our own process, so
    uvicorn unwinds exactly as a Ctrl-C would (the loop task cancels and
    publishes its final ``stopped`` status on the way down)."""
    os.kill(os.getpid(), signal.SIGINT)


def _agents_in_range_of(game, location_name: str) -> list[str]:
    """Agent-bound characters currently positioned to perceive *location_name*.

    Uses the engine's ``perceivable_locations`` visibility seam (falling back to
    the character's own room when the game predates it), so it matches exactly
    what ``AgentMemory.perceive`` will fold in: a character perceives an event at
    a location when that location is among the rooms it can see. Sorted by name,
    for a stable response."""
    names: list[str] = []
    for name, char in game.characters.items():
        if getattr(char, "agent", None) is None:
            continue
        if hasattr(game, "perceivable_locations"):
            locs = game.perceivable_locations(char)
        else:
            locs = [getattr(char, "location", None)]
        loc_names = {getattr(loc, "name", loc) for loc in locs}
        if location_name in loc_names:
            names.append(name)
    return sorted(names)


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


class SayRequest(BaseModel):
    """The body of ``POST /agents/{name}/say`` (#369): a human speaks to an agent."""

    text: str = Field(..., min_length=1, description="what is said to the agent")
    speaker: str = Field(
        "someone",
        min_length=1,
        description="who is speaking, for attribution in the agent's memory "
        "(defaults to 'someone' -- a voice with no named source)",
    )


class SayResponse(BaseModel):
    """The result of an utterance delivered to *name* (#369).

    ``reply`` is the agent's one-line answer -- ``null`` under the mock brain
    (the utterance is remembered, but a scripted stand-in doesn't talk back); a
    real brain (#261) fills it. ``cursor`` is the change-feed cursor of the
    ``intervention`` record this appended, so a viewer following ``/ws`` sees the
    same intervention the caller just made."""

    persona: str
    turn: int
    reply: str | None = Field(
        None, description="the agent's reply, or null when its brain doesn't answer"
    )
    cursor: int = Field(
        ..., description="cursor of the intervention record this appended"
    )


class WorldEventRequest(BaseModel):
    """The body of ``POST /world/event`` (#369): inject an observable happening."""

    text: str = Field(..., min_length=1, description="the happening, in plain language")
    location: str | None = Field(
        None,
        description="where it happens; agent-bound characters who can see that "
        "location perceive it at their next decision. Omitted = a feed-only "
        "announcement no agent perceives.",
    )


class WorldEventResponse(BaseModel):
    """The result of injecting a world event (#369).

    ``perceived_by`` is the agents currently positioned to see ``location`` --
    they fold the event into memory at their next decision point (a prediction,
    not a promise: an agent that moves first may miss it). Empty when no location
    was given (a feed-only announcement). ``cursor`` is the change-feed cursor of
    the ``intervention`` record, so viewers see the event land."""

    turn: int
    location: str | None
    perceived_by: list[str] = Field(
        default_factory=list,
        description="agent-bound characters currently in range to perceive it",
    )
    cursor: int = Field(
        ..., description="cursor of the intervention record this appended"
    )


class MemoryEntry(BaseModel):
    """One formed memory, in the exact wire shape the replay bake emits.

    This is ``cognition.memories_for_frame``'s dict -- the same four
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
    """``GET /agents/{name}/memory``: the slice of *name*'s stream the request
    asked for (the whole stream when unfiltered).

    ``memories`` is chronological (append order); unfiltered it is
    byte-identical to the baked ``memory_streams[name]`` for the same run.
    ``turn`` is the engine turn the stream was snapshotted at -- the same
    counter ``GET /health`` reports and the axis ``created_turn`` is measured on
    -- so a client can align the stream (and the ``since_turn`` cursor) with the
    change feed. The optional ``since_turn`` / ``kind`` / ``limit`` selectors
    (#345) never change an entry's shape, only *which* entries come back."""

    persona: str
    turn: int
    count: int = Field(
        ..., description="== len(memories), i.e. how many entries this response carries"
    )
    total: int | None = Field(
        default=None,
        description=(
            "the unfiltered stream size, for rendering 'showing count of total'; "
            "present only when a since_turn/kind/limit selector was applied "
            "(omitted entirely on an unfiltered read, which stays byte-identical "
            "to #298)"
        ),
    )
    memories: list[MemoryEntry]


class RetrievalResponse(BaseModel):
    """``GET /agents/{name}/retrieval?q=``: the memories *name*'s retriever would
    surface for a cue, scored but not attended to (#346).

    The read-only probe sibling of :class:`MemoryStreamResponse`: the entries are
    the same :class:`MemoryEntry` shape, but ``memories`` is ordered
    most-useful-first (the retriever's recency + importance + relevance ranking)
    rather than chronological, and the read runs with ``touch=False`` so it never
    bumps a memory's recency. ``query`` echoes the cue that produced this ranking;
    ``turn`` is the engine turn it was scored at (same counter ``GET /health``
    reports), so two probes with no turn between them return the same records."""

    persona: str
    turn: int
    query: str = Field(..., description="the retrieval cue this ranking answers")
    count: int = Field(..., description="== len(memories)")
    memories: list[MemoryEntry]


class AgentSummary(BaseModel):
    """One agent-bound character in the roster (``GET /agents``, #344).

    ``name`` is the exact, case-sensitive URL key for ``/agents/{name}/memory``
    (spaces and all). ``location`` is the location's name, or ``null`` for an
    unplaced character -- the same projection ``world_state`` uses.
    ``kind_counts``/``memory_count`` are a *cheap* activity summary so a list
    view needs no per-agent follow-up fetch; the full stream (with the memory
    *text*) stays behind the per-persona ``/agents/{name}/memory`` route, never
    the omniscient snapshot (#185)."""

    name: str
    persona: str
    location: str | None
    memory_count: int = Field(..., description="== sum(kind_counts.values())")
    kind_counts: dict[str, int] = Field(
        default_factory=dict,
        description="memories tallied by kind: observation | reflection | plan | chat",
    )


class AgentRosterResponse(BaseModel):
    """``GET /agents``: the characters that have a mind bound.

    ``turn`` is the engine turn the roster was snapshotted at -- the same
    counter ``GET /health`` reports and each memory stream's ``turn`` -- so a
    client can align the roster with the feed. ``agents`` is sorted by name."""

    turn: int
    agents: list[AgentSummary]


class BeliefEntry(BaseModel):
    """One belief, in the exact shape ``Knowledge.to_primitive()`` emits.

    These three fields *are* the save-file belief shape
    (``text_adventure_games/knowledge.py::Belief``) -- there is no second schema.
    A belief is what the character *thinks is true*; it may be incomplete or even
    wrong (the world graph stays the single source of truth). Deliberately no
    ``confidence`` / ``source``: the "uncertain or wrong" axis lives in ``text``."""

    text: str = Field(..., description="the belief in plain language, first person")
    topic: str | None = Field(
        None,
        description="optional lookup key; a belief whose topic matches a Thing's "
        "secret_topic unlocks perception of that hidden Thing",
    )
    learned_turn: int | None = Field(
        None,
        description="None for a prior known up front; else the turn it was learned",
    )


class KnowledgeResponse(BaseModel):
    """``GET /agents/{name}/knowledge``: everything *name* believes so far (#348).

    The belief-set sibling of :class:`MemoryStreamResponse`. ``beliefs`` is the
    verbatim ``Knowledge.to_primitive()['beliefs']`` list -- the seeded spatial
    priors (#79, ``learned_turn`` null) alongside anything learned during play
    (``learned_turn`` set). ``turn`` is the engine turn the belief set was
    snapshotted at (same counter ``GET /health`` reports), so two reads with no
    turn between them are identical."""

    persona: str
    turn: int
    count: int = Field(..., description="== len(beliefs)")
    beliefs: list[BeliefEntry]


class PlanResponse(BaseModel):
    """``GET /agents/{name}/plan``: what *name* intends to do today (#347).

    The intentions sibling of the memory / knowledge reads: memory is what the
    agent *remembers*, knowledge what it *believes*, and this is what it *plans*.
    ``plan`` is the verbatim ``DailyPlan.to_primitive()`` shape -- the same object
    the bake writes to ``personas/<name>/daily_plan.json`` -- so a live read and a
    baked artifact can never drift (the #298 rule: one formatter for both). It
    carries the day outline, the hourly schedule, and the ``stops`` the step loop
    walks. ``revision`` is lifted out of the plan to the top level so a client can
    poll it cheaply and refetch only when a mid-run replan bumps it. An agent
    whose brain never planned (a bare ``ScriptedAgent``) is ``plan: null`` /
    ``revision: null`` -- a 200, since a plan may still be generated later, the
    same way "no memories yet" is a 200 with ``memories: []``. ``turn`` is the
    engine turn it was snapshotted at (same counter ``GET /health`` reports)."""

    persona: str
    turn: int
    revision: int | None = Field(
        None,
        description="the plan's revision counter (0 when first generated, bumped "
        "on each mid-run replan); null when the agent has no plan yet",
    )
    plan: dict | None = Field(
        None,
        description="DailyPlan.to_primitive() (day / hours / stops / revision), "
        "the same shape the bake writes; null when the agent has no plan yet",
    )


class LiveStatusResponse(BaseModel):
    """``GET /live``: the handshake a live client reads once before following
    the feed (#262/#263).

    ``meta`` is the stepper's own ``meta()`` blob, passed through opaquely --
    for the Penn world it is the replay-meta shape (``tile_px``,
    ``width``/``height``, ``personas`` with emoji, ...), so a live viewer
    spawns its agents exactly the way the baked-replay loader does. ``cursor``
    is the newest change-feed cursor; a client that starts its backfill at
    ``GET /events?since=0`` (or attaches ``WS /ws?since=0``) replays history,
    while ``?since=<this cursor>`` starts at "now". With no stepper injected
    the route still answers (``enabled: false``, ``meta: null``) so a frontend
    can probe whether live mode exists at all."""

    enabled: bool
    running: bool
    paused: bool
    step: int | None = Field(
        None, description="completed sim steps (null when the loop is disabled)"
    )
    cursor: int = Field(..., description="the newest change-feed cursor (0 = none yet)")
    tick_seconds: float | None
    meta: dict | None
    boot_id: str | None = Field(
        None,
        description="per-process boot nonce; changes on a backend restart, "
        "null when no live loop is injected (#578)",
    )


class EventsResponse(BaseModel):
    """``GET /events?since=N``: the HTTP catch-up door of the change feed (#262).

    ``events`` are the retained records with ``cursor > N``, oldest first --
    the same objects ``WS /ws`` pushes, passed through as plain JSON (shapes:
    ``kind: "frame" | "status" | "engine"``; see ``backend/README.md``). The
    log is capped, so a very stale ``since`` may point at evicted history:
    the client detects that gap by ``events[0].cursor > since + 1`` (or by
    ``oldest_cursor``) and should re-sync from ``GET /live`` + ``/world_state``
    instead of trusting the tail."""

    latest_cursor: int
    oldest_cursor: int | None = Field(
        None, description="cursor of the oldest retained record (null = empty log)"
    )
    events: list[dict]


class RunControlResponse(BaseModel):
    """``POST /pause | /resume | /reset``: the loop state after the change.

    Each control also appends a ``status`` record to the change feed (its
    cursor is echoed here), so followers on ``/ws`` learn about the change the
    same way they learn about frames -- no side channel to poll."""

    running: bool
    paused: bool
    step: int
    cursor: int = Field(..., description="cursor of the status record this appended")


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
    stepper: SimStepper | None = None,
    tick_seconds: float = 1.0,
    start_paused: bool = False,
    allow_shutdown: bool = False,
    on_shutdown=None,
    max_log_records: int = 10_000,
) -> FastAPI:
    """Build the FastAPI app serving *game*.

    *game* is any engine :class:`~text_adventure_games.games.Game` -- Action
    Castle, a benchmark task, or the live Penn sim -- so this one app
    is the seam for every world. If *auth_token* is set, every request must carry
    ``Authorization: Bearer <token>``; left ``None`` (the loopback-only default)
    the API is open. Access to *game* is serialized with a lock, since FastAPI
    runs the sync handlers in a thread pool and ``do_command`` mutates state.

    Pass *stepper* (a :class:`~backend.live.SimStepper`) to turn on the
    **self-stepping live loop** (#349): a background task advances the sim every
    *tick_seconds* under the same lock the routes use, publishing each step to
    the change feed (capped at *max_log_records*; cursors stay monotonic across
    eviction). Left ``None`` -- the default -- the app is byte-identical to the
    command-driven API. The loop rides the app's lifespan, so it only runs
    inside a server (or a ``with TestClient(app):`` block -- a bare
    ``TestClient(app)`` never starts it). *start_paused* boots that loop armed
    but not ticking -- the first frame (and, with a real brain, the first paid
    model call) waits for ``POST /resume``, e.g. the viewer's Start button.
    *allow_shutdown* enables ``POST /shutdown`` (the viewer's close-the-window
    kill; 404 otherwise), and *on_shutdown* overrides what it does -- tests
    inject a spy; the default SIGINTs this very process."""
    lock = threading.Lock()
    log = EventLog(max_log_records)
    # A per-process boot nonce (#578): minted once here, so it is stable across
    # every GET /live in this process and unchanged by reset()/POST /runs
    # (those swap the run, not the process), but fresh on each restart. Clients
    # compare it to detect a restarted backend even when the new feed's cursor
    # has already climbed past the one they kept.
    boot_id = secrets.token_hex(8)
    controller = (
        LiveRunController(stepper, lock, start_paused=start_paused)
        if stepper is not None
        else None
    )
    ledger = getattr(stepper, "ledger", None)

    lifespan = None
    if controller is not None:

        @contextlib.asynccontextmanager
        async def _live_lifespan(_app):
            task = asyncio.create_task(run_loop(controller, log, tick_seconds))
            try:
                yield
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        lifespan = _live_lifespan

    app = FastAPI(
        title="agent-sandbox backend",
        summary="Headless HTTP seam over a text-adventure Game (issue #179).",
        lifespan=lifespan,
    )

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

    @app.get("/agents", response_model=AgentRosterResponse)
    def agents(_: None = Depends(require_auth)):
        """The roster of agent-bound characters, read mid-run (#344).

        The discovery companion to ``GET /agents/{name}/memory``: one small list
        of the characters that have a mind bound -- the same ``char.agent is not
        None`` seam the memory route filters on -- so a client learns which names
        are addressable without probing each and eating 404s. A character with no
        agent (the player, a scripted-behavior NPC) is absent here, exactly as it
        would 404 on the memory route. Read-only and pull-only; ``turn`` matches
        ``/health`` for feed alignment; the list is sorted by name for
        determinism. Read under the shared lock so ``turn`` and every entry are
        one atomic snapshot. Once a persistent store exists this becomes a
        store-backed query scoped under a run id (#304/#306)."""
        with lock:
            roster = [
                {
                    "name": name,
                    "persona": getattr(char, "persona", ""),
                    "location": char.location.name if char.location else None,
                    "kind_counts": kind_counts_for_persona(char.agent),
                    "memory_count": len(memory_stream_for_persona(char.agent)),
                }
                for name, char in sorted(game.characters.items())
                if char.agent is not None
            ]
            return {"turn": game.turn, "agents": roster}

    @app.get(
        "/agents/{name}/memory",
        response_model=MemoryStreamResponse,
        response_model_exclude_none=True,
    )
    def agent_memory(
        name: str,
        since_turn: int | None = Query(
            default=None,
            description="only memories with created_turn > this (the incremental "
            "poll: pass back the turn a prior read reported)",
        ),
        kind: MemoryKind | None = Query(
            default=None,
            description="only memories of this kind (observation | reflection | "
            "plan | chat); an unknown value is a 422, not an empty list",
        ),
        limit: int | None = Query(
            default=None,
            ge=1,
            description="return only the newest this-many memories (after the "
            "other filters), for a bounded first paint of a long stream",
        ),
        _: None = Depends(require_auth),
    ):
        """The memory stream *name* has formed *so far*, read mid-run (#298),
        optionally sliced by ``since_turn`` / ``kind`` / ``limit`` (#345).

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
        (#304/#306).

        The three selectors compose and each defaults to "everything", so a
        no-argument read is byte-identical to #298. They apply in the order
        ``since_turn`` (created_turn > cursor) -> ``kind`` -> ``limit`` (newest
        K of what survives), which is the natural "plans since turn T, newest
        20" reading and maps directly onto a future
        ``WHERE created_turn > ? AND kind = ? ... LIMIT ?`` store query (#304).
        Whenever any selector is set the response also carries ``total`` (the
        unfiltered stream size) so a client can render "showing count of total";
        an unfiltered read omits it and stays byte-identical."""
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
            total = len(memories)
            filtered = since_turn is not None or kind is not None or limit is not None
            if since_turn is not None:
                memories = [m for m in memories if m["created_turn"] > since_turn]
            if kind is not None:
                memories = [m for m in memories if m["kind"] == kind.value]
            if limit is not None:
                memories = memories[-limit:]  # newest K; stream is oldest-first
            response = {
                "persona": name,
                "turn": game.turn,
                "count": len(memories),
                "memories": memories,
            }
            if filtered:
                response["total"] = total
            return response

    @app.get("/agents/{name}/retrieval", response_model=RetrievalResponse)
    def agent_retrieval(
        name: str,
        q: str = Query(
            ...,
            min_length=1,
            description="the retrieval cue to score the stream against -- the "
            "same kind of query a decision-time retrieval passes",
        ),
        limit: int | None = Query(
            default=None,
            ge=1,
            description="cap the probe at this many records (maps to the "
            "retriever's max_records); omit for the decision-time default",
        ),
        _: None = Depends(require_auth),
    ):
        """What *name*'s memory would surface for query *q*, scored but **not
        attended to** (#346).

        A read-only window onto the retriever the agent uses at decision time: it
        scores every memory by the paper's recency + importance + relevance and
        returns the top few, ordered most-useful-first -- *not* chronological,
        unlike ``/memory``. Crucially it retrieves with ``touch=False``:
        inspecting what *would* surface never bumps a memory's
        ``last_accessed_turn``, so a probe can't perturb the very recency it is
        measuring, and two identical probes with no turn between them return the
        same records. That is what makes it safe to fire on every keystroke of a
        debugging UI (contrast the decision-time path, which bumps recency).

        The 404 story matches the memory sibling: an unknown character 404s, and
        so does one with no agent bound (the player, a scripted-behavior NPC) --
        there is no mind to probe. An agent with an as-yet-empty stream is a 200
        with ``memories: []``. Scored under the shared lock, so ``turn`` and
        ``memories`` are one atomic snapshot; the entries are the same
        :class:`MemoryEntry` shape ``/memory`` emits, so a client renders a probe
        result and a stream slice through one code path."""
        with lock:
            char = game.characters.get(name)
            if char is None:
                raise HTTPException(
                    status_code=404, detail=f"unknown character: {name!r}"
                )
            if char.agent is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"character {name!r} has no agent (and so no memory to probe)",
                )
            # An agent bound but with no memory stream is an empty probe, not a
            # 500 -- the same tolerance memory_stream_for_persona applies.
            memory = getattr(char.agent, "memory", None)
            if memory is None:
                records = []
            else:
                kwargs = {} if limit is None else {"max_records": limit}
                records = memory.retrieve(
                    query=q, turn=game.turn, touch=False, **kwargs
                )
            memories = memories_for_frame(records)
            return {
                "persona": name,
                "turn": game.turn,
                "query": q,
                "count": len(memories),
                "memories": memories,
            }

    @app.get("/agents/{name}/knowledge", response_model=KnowledgeResponse)
    def agent_knowledge(
        name: str,
        topic: str | None = Query(
            default=None,
            description="if set, return only beliefs carrying this exact topic",
        ),
        _: None = Depends(require_auth),
    ):
        """What *name* *believes about the world*, read mid-run (#348).

        The sibling of :func:`agent_memory`: memory is the episodic *log*;
        knowledge is the current *world-model* -- the seeded spatial priors
        (#79) plus anything learned during play. Like ``world_state``, the
        snapshot omits private cognition (#185), so this scoped per-persona
        route is the sanctioned way to read one agent's beliefs.

        **The 404 story is deliberate.** Unlike memory, ``knowledge`` lives on
        the *character*, not on ``agent.memory`` -- every character has a
        (possibly empty) belief set. We still 404 a character with no agent
        bound, keeping the ``/agents/{name}/...`` family consistent: it reads a
        *mind*, and the player / a scripted-behavior NPC is not one to inspect
        here. An agent that simply hasn't been seeded returns 200 with
        ``beliefs: []`` (absent, not an error -- the fresh-checkout case where
        #79 seeding no-ops). Optional ``?topic=`` filters to beliefs carrying
        that exact perception key when the set grows large.

        Read under the shared lock, so ``turn`` and ``beliefs`` are one atomic
        snapshot and two reads with no turn between them are identical. The
        belief shape is ``Knowledge.to_primitive()`` verbatim -- the save-file
        shape, so there is no second schema to drift."""
        with lock:
            char = game.characters.get(name)
            if char is None:
                raise HTTPException(
                    status_code=404, detail=f"unknown character: {name!r}"
                )
            if char.agent is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"character {name!r} has no agent (and so no mind to read)",
                )
            # to_primitive() is the save-file belief shape; response_model keeps
            # the wire frozen if the serializer ever grows a field.
            beliefs = char.knowledge.to_primitive()["beliefs"]
            if topic is not None:
                beliefs = [b for b in beliefs if b["topic"] == topic]
            return {
                "persona": name,
                "turn": game.turn,
                "count": len(beliefs),
                "beliefs": beliefs,
            }

    @app.get("/agents/{name}/plan", response_model=PlanResponse)
    def agent_plan(name: str, _: None = Depends(require_auth)):
        """What *name* intends to do today (#347).

        The live counterpart of the baked ``personas/<name>/daily_plan.json``:
        the agent's :class:`~text_adventure_games.planning.DailyPlan` -- day
        outline, hourly schedule, and the ``stops`` the step loop walks --
        serialized through the plan's own ``to_primitive()``, so a live read and
        the baked artifact are byte-identical (the #298 rule: one formatter for
        both, so they can never drift). Where ``/memory`` shows what the agent
        *remembers* and ``/knowledge`` what it *believes*, this is what it
        *plans*; together they are the agent card.

        ``revision`` is hoisted to the top level so a client can poll it cheaply
        and refetch the (larger) plan only when a mid-run replan
        (``maybe_revise_plan``) bumps it. The 404 story matches the memory
        sibling: an unknown character 404s, and so does one with no agent bound
        (the player, a scripted-behavior NPC) -- there is no mind whose plan to
        read. An agent that is bound but whose brain never planned (a bare
        ``ScriptedAgent``, ``agent.plan`` unset) is a 200 with ``plan: null`` /
        ``revision: null`` -- absent, not an error, since a plan may still be
        generated later (mirroring "no memories yet" being a 200 with an empty
        stream). Read under the shared lock, so ``turn``, ``revision``, and
        ``plan`` are one atomic snapshot."""
        with lock:
            char = game.characters.get(name)
            if char is None:
                raise HTTPException(
                    status_code=404, detail=f"unknown character: {name!r}"
                )
            if char.agent is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"character {name!r} has no agent (and so no plan)",
                )
            # A bare agent whose brain never planned has no .plan attribute at
            # all; treat that as "no plan yet" (200, null), not a 500.
            plan = getattr(char.agent, "plan", None)
            return {
                "persona": name,
                "turn": game.turn,
                "revision": plan.revision if plan is not None else None,
                "plan": plan.to_primitive() if plan is not None else None,
            }

    @app.get("/live", response_model=LiveStatusResponse)
    def live(_: None = Depends(require_auth)):
        """The live-loop handshake (#262/#263): loop state + the world's meta.

        A live client calls this once -- to learn the world's shape (``meta``:
        tile size, dimensions, personas) and where the feed currently stands
        (``cursor``, ``step``) -- then follows ``WS /ws`` with ``GET /events``
        as its backfill. Always answers: with no stepper injected it reports
        ``enabled: false`` so a frontend can cheaply probe for live mode."""
        if controller is None or stepper is None:
            return {
                "enabled": False,
                "running": False,
                "paused": False,
                "step": None,
                "cursor": log.latest_cursor(),
                "tick_seconds": None,
                "meta": None,
                "boot_id": None,
            }
        with lock:
            return {
                "enabled": True,
                "running": controller.running,
                "paused": controller.paused,
                "step": stepper.step,
                "cursor": log.latest_cursor(),
                "tick_seconds": tick_seconds,
                "meta": stepper.meta(),
                "boot_id": boot_id,
            }

    @app.get("/events", response_model=EventsResponse)
    def events(
        since: int = Query(
            default=0,
            ge=0,
            description="return only records with cursor > this; pass the last "
            "cursor you saw to catch up after a dropped socket (0 = everything "
            "retained)",
        ),
        _: None = Depends(require_auth),
    ):
        """The HTTP catch-up door of the change feed (#262).

        The same records ``WS /ws`` pushes, addressed by the same monotonic
        cursor -- so "reconnect, then ``GET /events?since=<last seen>``, then
        re-attach the socket at ``?since=<new last>``" yields no gap and no
        duplicate. An empty tail returns ``[]`` immediately (this door never
        blocks; the socket is the door that waits). Reads only the log, not the
        game, so it doesn't contend with a tick in progress."""
        records = log.since(since)
        return {
            "latest_cursor": records[-1]["cursor"] if records else log.latest_cursor(),
            "oldest_cursor": log.oldest_cursor(),
            "events": records,
        }

    async def _drain_inbound(websocket: WebSocket) -> None:
        """Consume (and ignore) client->server messages so disconnects surface.

        The feed is server-push; the only inbound policing is the body-size cap:
        ``_BodySizeLimitMiddleware`` never sees WebSocket scopes, so the 64 KiB
        rule (#186) is enforced here by hand -- an oversized message closes the
        socket with 1009 ("message too big")."""
        try:
            while True:
                message = await websocket.receive_text()
                if len(message.encode("utf-8")) > max_body_bytes:
                    await websocket.close(code=1009)
                    return
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.websocket("/ws")
    async def ws_feed(
        websocket: WebSocket,
        since: int | None = Query(default=None, ge=0),
        token: str | None = Query(default=None),
    ):
        """The push door of the change feed (#262): every record, as it lands.

        Auth mirrors the HTTP routes: send ``Authorization: Bearer <token>`` in
        the handshake (Godot's ``WebSocketPeer`` can), or -- because a browser
        ``WebSocket`` cannot set headers -- pass ``?token=<token>``. A bad
        token is refused with close code 1008 before the handshake completes.

        ``?since=N`` replays the retained records after cursor ``N`` before
        tailing (omit it to start at "now"). Each client just tails the shared
        log at its own cursor, so a slow reader backpressures only itself; one
        that falls behind the log's retention is closed with 1011 and must
        re-sync (``GET /live`` + ``/events``)."""
        if auth_token is not None:
            offered = websocket.headers.get("authorization")
            if offered != f"Bearer {auth_token}" and token != auth_token:
                await websocket.close(code=1008)  # policy violation: bad token
                return
        await websocket.accept()
        cursor = log.latest_cursor() if since is None else since
        # A gap in the *first* batch after an explicit ?since= is the client's
        # to judge (same contract as GET /events); after that, a gap means this
        # client was slower than the log's retention -- force a re-sync.
        caught_up = since is None
        waiter = log.subscribe()
        inbound = asyncio.create_task(_drain_inbound(websocket))
        try:
            while True:
                waiter.clear()  # clear BEFORE reading: a racing append re-sets it
                batch = log.since(cursor)
                if batch:
                    if caught_up and batch[0]["cursor"] > cursor + 1:
                        await websocket.close(
                            code=1011, reason="events evicted; re-sync and reconnect"
                        )
                        return
                    for record in batch:
                        await websocket.send_text(json.dumps(record))
                        cursor = record["cursor"]
                    caught_up = True
                    continue
                caught_up = True
                wake = asyncio.ensure_future(waiter.wait())
                done, _ = await asyncio.wait(
                    {inbound, wake}, return_when=asyncio.FIRST_COMPLETED
                )
                wake.cancel()
                if inbound in done:
                    return  # client went away (or sent an oversized message)
        except (WebSocketDisconnect, RuntimeError):
            pass  # client dropped mid-send; nothing to clean up beyond finally
        finally:
            inbound.cancel()
            log.unsubscribe(waiter)

    def _require_loop() -> LiveRunController:
        """Run control without a loop is a conflict (409), not a crash."""
        if controller is None:
            raise HTTPException(
                status_code=409,
                detail="live loop not enabled; serve with create_app(stepper=...)",
            )
        return controller

    @app.post("/pause", response_model=RunControlResponse)
    async def pause(_: None = Depends(require_auth)):
        """Stop ticking (idempotent). The loop task stays alive and every read
        keeps working; this is also the viewer's emergency stop (#264), which is
        why it is plain stateless HTTP rather than a socket message -- it must
        work even when the socket is wedged."""
        ctl = _require_loop()
        ctl.pause()
        record = log.append("status", reason="paused", **ctl.status())
        return {**ctl.status(), "cursor": record["cursor"]}

    @app.post("/resume", response_model=RunControlResponse)
    async def resume(_: None = Depends(require_auth)):
        """Start ticking again (idempotent; also un-does a ``finished`` pause,
        which simply re-checks the stepper -- a finished run pauses again)."""
        ctl = _require_loop()
        ctl.resume()
        record = log.append("status", reason="resumed", **ctl.status())
        return {**ctl.status(), "cursor": record["cursor"]}

    @app.post("/reset", response_model=RunControlResponse)
    async def reset(_: None = Depends(require_auth)):
        """Rebuild the sim to t0. ``step`` restarts at 0 but the change-feed
        cursor keeps climbing (a follower keys off the ``status`` record with
        ``reason: "reset"`` rather than a cursor rewind). Runs the stepper's
        rebuild in a worker thread -- it takes the app lock and may be slow."""
        ctl = _require_loop()
        await asyncio.get_running_loop().run_in_executor(None, ctl.reset)
        record = log.append("status", reason="reset", **ctl.status())
        return {**ctl.status(), "cursor": record["cursor"]}

    @app.post("/shutdown")
    async def shutdown(_: None = Depends(require_auth)) -> dict:
        """Stop the whole server process. The Penn viewer sends this when its
        window closes, so a paying live sim never keeps running -- or spending
        -- with nobody watching. Hidden (404) unless the embedding entrypoint
        opted in via ``create_app(allow_shutdown=True)``, so the generic API
        is unchanged. Pauses the loop first (spend stops even if the process
        lingers), answers, then exits a beat later -- the delayed SIGINT lets
        this response reach the client before uvicorn unwinds."""
        if not allow_shutdown:
            raise HTTPException(status_code=404, detail="Not Found")
        if controller is not None:
            controller.pause()
            log.append("status", reason="paused", **controller.status())
        threading.Timer(0.2, on_shutdown or _terminate_process).start()
        return {"ok": True}

    @app.get("/usage")
    def usage(_: None = Depends(require_auth)) -> dict:
        """The stepper's ``UsageLedger.summary()`` -- tokens and dollars -- for
        the run-monitor HUD (#264). ``available: false`` (with a zeroed summary
        in the same shape) when no ledger is wired, so the HUD renders $0.00
        instead of erroring; under the mock brain a real ledger also reads ~0.
        Real numbers arrive when #261 swaps a live LLM into the loop."""
        with lock:
            if ledger is None:
                return {
                    "kind": "summary",
                    "available": False,
                    "calls": 0,
                    "total_cost_usd": 0.0,
                    "by_actor": {},
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "over_budget": False,
                }
            summary = ledger.summary()
            summary["available"] = True
            summary["over_budget"] = ledger.over_budget()
            if ledger.max_cost_usd is not None:
                summary["max_cost_usd"] = ledger.max_cost_usd
                summary["remaining_budget_usd"] = ledger.remaining_budget_usd()
            # The per-run slice (#526): additive fields the dashboard's run
            # strip shows beside the (unchanged) lifetime totals + budget --
            # probed like `ledger`/`drain_events`, so steppers without it
            # serve exactly the pre-#526 shape.
            run_usage = getattr(stepper, "run_usage", None)
            if callable(run_usage):
                summary.update(run_usage())
            return summary

    # ---------------------------------------------------------- run registry
    # The #306 registry half: browse/fetch/export/delete the #304 RunStore's
    # run history, plus #543's resume (adopt a persisted run as the live one).
    # The store is probed off the stepper per request (the ledger/run_usage
    # idiom), so a storeless server -- no --persist, or no stepper at all --
    # answers available:false here and 404 on every id route instead of
    # erroring. POST /runs (create with a world-factory seam) stays deferred.

    def _run_store():
        return getattr(stepper, "run_store", None)

    def _current_run_id():
        return getattr(stepper, "run_id", None)

    @app.get("/runs")
    def runs_index(_: None = Depends(require_auth)) -> dict:
        """The run history, newest first: row summaries WITHOUT the manifest
        blob (a hundred-run history shouldn't ship a hundred manifests --
        fetch one run for its manifest), plus which id is live right now."""
        store = _run_store()
        if store is None:
            return {"available": False, "current": None, "runs": []}
        with lock:
            current = _current_run_id()
        return {
            "available": True,
            "current": current,
            "runs": [
                {k: v for k, v in row.items() if k != "manifest"}
                for row in store.list_runs()
            ],
        }

    @app.get("/runs/{run_id}")
    def runs_get(run_id: str, _: None = Depends(require_auth)) -> dict:
        """One run's full row, parsed manifest included, plus whether it is
        the live one."""
        store = _run_store()
        row = store.get_run(run_id) if store is not None else None
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown run id: {run_id}")
        with lock:
            row["current"] = run_id == _current_run_id()
        return row

    @app.get("/runs/{run_id}/replay")
    def runs_replay(run_id: str, _: None = Depends(require_auth)) -> dict:
        """The run as a viewer-loadable replay: #307's build_replay served
        over HTTP. Save the body as penn_replay.json and open it via the
        landing menu's "Open a local replay file"."""
        store = _run_store()
        if store is None:
            raise HTTPException(status_code=404, detail=f"unknown run id: {run_id}")
        # Lazy on purpose: api.py stays importable without the Penn package,
        # and Penn's is the only replay dialect today. A second world's
        # format is the cue to promote a replay_builder= seam on create_app.
        from backend.penn.export_replay import build_replay

        try:
            return build_replay(store, run_id)
        except ValueError:
            # The single source of truth for "does this run exist" is
            # build_replay's own lookup -- no check-then-use window (a
            # concurrent DELETE between two reads used to surface as a 500).
            raise HTTPException(status_code=404, detail=f"unknown run id: {run_id}")

    @app.delete("/runs/{run_id}")
    def runs_delete(run_id: str, _: None = Depends(require_auth)) -> dict:
        """Remove a persisted run (row + memories + directory). The CURRENT
        live run is refused with a 409: the stepper is still appending
        frames to it -- reset or stop the run first."""
        store = _run_store()
        if store is None:
            raise HTTPException(status_code=404, detail=f"unknown run id: {run_id}")
        with lock:
            if run_id == _current_run_id():
                raise HTTPException(
                    status_code=409,
                    detail="run is live; reset or stop it before deleting",
                )
            try:
                store.delete_run(run_id)
            except KeyError:
                raise HTTPException(status_code=404, detail=f"unknown run id: {run_id}")
        return {"ok": True, "deleted": run_id}

    @app.post("/runs/{run_id}/resume")
    async def runs_resume(run_id: str, _: None = Depends(require_auth)) -> dict:
        """Adopt a persisted run as the live one (#543, the second half of
        #306): the stepper rebuilds its world picking the run up where the
        store left off, and because everything reads through the stepper,
        ``/world_state``, ``/events`` and ``/agents/{name}/memory`` serve the
        resumed run from here on -- run-scoping by adoption.

        Not to be confused with ``POST /resume`` (the play button): that
        un-pauses ticking, this swaps WHICH run is ticking. The loop's paused
        state is deliberately untouched, consistent with ``POST /reset``.

        Followers see a ``status`` record with ``reason: "reset"`` -- the
        documented "the world was rebuilt, refetch meta and follow from here"
        signal, so both frontends handle a resume with zero client changes
        (the record's additive ``run_id`` field says which run took over).
        Plain dict like the rest of the registry: a ``RunControlResponse``
        model would strip the ``run_id`` key."""
        store = _run_store()
        if store is None:
            raise HTTPException(status_code=404, detail=f"unknown run id: {run_id}")
        resume_run = getattr(stepper, "resume_run", None)
        if not callable(resume_run):
            raise HTTPException(
                status_code=501, detail="this stepper cannot resume persisted runs"
            )

        # A store implies a stepper, and create_app wires a controller for
        # every stepper -- both are non-None past the guards above.
        def _swap():
            # The controller.reset() pattern: rebuild under the app lock in a
            # worker thread, bump the generation so an in-flight tick of the
            # OLD world is dropped instead of published. The already-current
            # check lives inside the lock, atomic with the swap.
            with lock:
                if run_id == _current_run_id():
                    raise HTTPException(
                        status_code=409, detail=f"run {run_id} is already live"
                    )
                resume_run(run_id)
                controller.generation += 1

        try:
            await asyncio.get_running_loop().run_in_executor(None, _swap)
        except KeyError as exc:
            # exc.args[0] keeps the message unquoted (str() of a KeyError
            # wraps it in repr quotes).
            raise HTTPException(status_code=404, detail=str(exc.args[0]))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        record = log.append(
            "status", reason="reset", run_id=run_id, **controller.status()
        )
        return {**controller.status(), "cursor": record["cursor"], "run_id": run_id}

    @app.post("/command", response_model=CommandResponse)
    def command(req: CommandRequest, _: None = Depends(require_auth)):
        """Run exactly one command and return events + the new snapshot.

        A command the *engine* rejects (a failed precondition) is still a
        successful request: 200, with the rejection surfaced as a ``blocked``
        event. A 4xx means a bad *request* (malformed/empty body), not a rejected
        *command*.

        While the live loop is actively stepping, a command would interleave
        with ticks mid-run, so it is refused with ``409`` -- ``POST /pause``
        first, command, then ``/resume`` (the #349 "decide and document" rule:
        pause-to-command rather than silent interleaving)."""
        if controller is not None and controller.running and not controller.paused:
            raise HTTPException(
                status_code=409,
                detail="sim loop is running; POST /pause before issuing commands",
            )
        try:
            return run_command(game, req.command.strip(), lock)
        except Exception as exc:  # an engine bug shouldn't drop the connection
            raise HTTPException(status_code=500, detail=f"engine error: {exc}")

    @app.post("/agents/{name}/say", response_model=SayResponse)
    async def agent_say(name: str, req: SayRequest, _: None = Depends(require_auth)):
        """Speak to an agent; the utterance lands in its memory (#369).

        The write-side sibling of ``GET /agents/{name}/memory``: a human (or, later,
        the Godot chat box) says something to *name*, and it enters the agent's
        stream as a ``chat``-kind record phrased from the listener's side
        (``'{speaker} said to me: "..."'``) -- the same dual-write shape
        ``conversation.py`` uses, minus the speaker half (the human has no agent
        memory). The line is also pushed onto the character's ``heard`` buffer, so
        it surfaces in the agent's next observation exactly like overheard speech.

        Applied **at the next tick boundary**: the delivery runs under the shared
        lock in a worker thread, so it lands cleanly between ticks even while the
        loop is stepping (no ``409`` -- unlike ``POST /command``, an utterance
        doesn't advance a turn, it just seeds a memory). 404 conventions match the
        read family: an unknown character 404s, and so does one with no agent
        bound (there is no mind to speak to). The agent's ``reply`` is ``null``
        under the mock brain and filled once #261 wires a real one."""
        text = req.text.strip()
        speaker = req.speaker.strip() or "someone"

        def _deliver() -> int:
            with lock:
                char = game.characters.get(name)
                if char is None:
                    raise HTTPException(
                        status_code=404, detail=f"unknown character: {name!r}"
                    )
                if char.agent is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"character {name!r} has no agent (and so cannot be spoken to)",
                    )
                char.agent.memory.add_chat(
                    f'{speaker} said to me: "{text}"', turn=game.turn, partner=speaker
                )
                hear = getattr(char, "hear", None)
                if callable(hear):
                    hear(f'{speaker} said to you: "{text}"')
                return game.turn

        turn = await asyncio.get_running_loop().run_in_executor(None, _deliver)
        record = log.append(
            "intervention",
            intervention="say",
            name=name,
            speaker=speaker,
            text=text,
            turn=turn,
        )
        return {
            "persona": name,
            "turn": turn,
            "reply": None,
            "cursor": record["cursor"],
        }

    @app.post("/world/event", response_model=WorldEventResponse)
    async def world_event(req: WorldEventRequest, _: None = Depends(require_auth)):
        """Inject an observable event agents in range perceive (#369).

        Appends a :class:`~text_adventure_games.events.GameEvent` to the world log
        so agent-bound characters who can see ``location`` fold it into memory at
        their next ``perceive`` (their next decision point) -- the same path a
        real action's aftermath travels. It is *also* appended to the #262 change
        feed as an ``intervention`` record, so a viewer sees the event happen even
        before any agent reacts. Omit ``location`` for a feed-only announcement
        that no agent perceives.

        Applied **at the next tick boundary** (delivered under the shared lock in
        a worker thread), so it lands cleanly between ticks while the loop runs. A
        given-but-unknown ``location`` is a ``404`` (a typo shouldn't silently
        vanish); otherwise ``perceived_by`` reports who is currently in range."""
        text = req.text.strip()
        location = req.location

        def _inject() -> tuple[int, list[str]]:
            with lock:
                if location is not None and location not in game.locations:
                    raise HTTPException(
                        status_code=404, detail=f"unknown location: {location!r}"
                    )
                turn = game.turn
                payload = {"location": location} if location is not None else {}
                game.events.append(
                    GameEvent(turn, None, "world_event", summary=text, payload=payload)
                )
                perceived_by = (
                    _agents_in_range_of(game, location) if location is not None else []
                )
                return turn, perceived_by

        turn, perceived_by = await asyncio.get_running_loop().run_in_executor(
            None, _inject
        )
        record = log.append(
            "intervention",
            intervention="world_event",
            text=text,
            location=location,
            turn=turn,
        )
        return {
            "turn": turn,
            "location": location,
            "perceived_by": perceived_by,
            "cursor": record["cursor"],
        }

    return app


def run(
    game,
    host: str = "127.0.0.1",
    port: int = 8080,
    auth_token: str | None = None,
    *,
    stepper: SimStepper | None = None,
    tick_seconds: float = 1.0,
    start_paused: bool = False,
    allow_shutdown: bool = False,
) -> None:
    """Serve *game* over HTTP until interrupted (Ctrl-C).

    Defaults to loopback with no auth (local dev). Binding a non-loopback host
    requires a token -- passed here or via the ``SIM_API_TOKEN`` env var -- or
    this refuses to start, so the API is never silently exposed unauthenticated
    (issue #186c). Pass *stepper* to run the self-stepping live loop (#349);
    note that serving ``WS /ws`` needs the ``websockets`` package, which the
    ``server`` extra installs alongside uvicorn."""
    import uvicorn

    auth_token = auth_token or os.environ.get("SIM_API_TOKEN")
    if host not in LOOPBACK_HOSTS and not auth_token:
        raise RuntimeError(
            f"refusing to bind non-loopback host {host!r} without an auth token; "
            "set SIM_API_TOKEN (or pass auth_token=...) first -- see issue #186"
        )
    uvicorn.run(
        create_app(
            game,
            auth_token=auth_token,
            stepper=stepper,
            tick_seconds=tick_seconds,
            start_paused=start_paused,
            allow_shutdown=allow_shutdown,
        ),
        host=host,
        port=port,
    )


def _demo_game():
    """A tiny two-room world so ``python -m backend.api`` is runnable with no
    assets -- enough to exercise the contract and ``/docs``. Real worlds (the
    Penn sim) are served by passing your own ``Game`` to :func:`run`.

    The gardener NPC carries three hand-seeded memories (the same
    ``AgentMemory`` a live LLM agent accrues into) so
    ``GET /agents/gardener/memory`` (#298) has something to show without any
    provider key. In a real sim the loop writes the stream instead -- seeded
    plans, perceived events, action outcomes, reflections.

    Its ``knowledge`` is seeded too, so ``GET /agents/gardener/knowledge``
    (#348) shows both a prior (``learned_turn`` null, the way #79 seeds spatial
    knowledge) and a belief learned during play (``learned_turn`` set)."""
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

    # Beliefs (the current world-model, #348) -- distinct from the log above. A
    # prior known up front (learned_turn stays None, the way #79 seeds spatial
    # knowledge) and one learned mid-run (stamped with the turn), so the route
    # shows both. The ``forest`` topic doubles as a perception key.
    gardener.add_belief("The field lies just south of a dense forest.", topic="forest")
    gardener.knowledge.learn("The north path is overgrown with tall grass.", turn=1)

    return games.Game(field, player, characters=[gardener])


def _demo_stepper(game):
    """A :class:`~backend.live.ScriptedStepper` over the demo world, so
    ``SIM_LIVE=1 python -m backend.api`` exercises the whole live surface --
    loop, feed, ``/ws``, run control -- with no assets and no key.

    Each tick runs one real command through *game* (cycling north/south, so
    ``/world_state`` and ``game.turn`` genuinely advance) and appends one
    observation to the gardener's memory (so ``GET /agents/gardener/memory``
    visibly grows over time -- the #349 acceptance check). The frame maps the
    two rooms onto a toy 4x4 grid; real worlds (the Penn sim) implement their
    own :class:`~backend.live.SimStepper` instead."""
    from .live import ScriptedStepper

    positions = {"Field": (1, 2), "Forest": (1, 1)}
    commands = ["go north", "go south"]
    gardener = game.characters["gardener"]

    def do_tick(step: int) -> list[dict]:
        # The loop already holds the app lock around tick(), so run the command
        # WITHOUT passing the lock here -- taking it again would deadlock.
        result = run_command(game, commands[step % len(commands)])
        gardener.agent.memory.add_observation(
            f"Step {step}: I watched over the field.", turn=game.turn, importance=1.0
        )
        return result["events"]

    def snapshot(step: int) -> dict:
        x, y = positions.get(game.player.location.name, (0, 0))
        here = game.player.location.name
        return {
            "player": {"x": x, "y": y, "act": f"wandering @ demo:{here}", "e": "🧍"},
            "gardener": {
                "x": 2,
                "y": 2,
                "act": "tending the grass @ demo:Field",
                "e": "🌱",
            },
        }

    def go_home() -> None:
        # Demo-grade reset: walk the player back rather than rebuilding the
        # world (the routes close over *game*, so it must be the same object).
        if game.player.location.name != "Field":
            run_command(game, "go south")

    meta = {
        "tile_px": 32,
        "width": 4,
        "height": 4,
        "sec_per_step": 1,
        "start": "2026-01-01 08:00:00",
        "vision_r": 2,
        "personas": [
            {"name": "player", "emoji": "🧍"},
            {"name": "gardener", "emoji": "🌱"},
        ],
    }
    return ScriptedStepper(snapshot, meta=meta, on_tick=do_tick, on_reset=go_home)


if __name__ == "__main__":
    # A repo-root .env (git-ignored; template at .env.example) can supply
    # HOST/PORT/SIM_LIVE/SIM_API_TOKEN; exported variables win (backend/env.py).
    if load_dotenv():
        print("Loaded .env from the repo root (already-exported variables win).")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    game = _demo_game()
    stepper = None
    tick_seconds = float(os.environ.get("SIM_TICK_SECONDS", "1.0"))
    if os.environ.get("SIM_LIVE"):  # default OFF: command-driven, as always
        stepper = _demo_stepper(game)
        print(
            f"live loop ON (tick every {tick_seconds}s): "
            f"GET /live, GET /events?since=0, ws://{host}:{port}/ws"
        )
    print(f"serving demo world on http://{host}:{port}  (OpenAPI at /docs)")
    run(game, host=host, port=port, stepper=stepper, tick_seconds=tick_seconds)
