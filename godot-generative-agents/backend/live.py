"""The self-stepping live loop behind ``backend.api`` (issues #349 + #262).

``backend.api`` on its own is *command-driven*: the world only advances when a
client POSTs ``/command``. A live viewer (the Godot campus, the web companion)
instead needs the sim to advance **on its own** and to publish what happened as
a change feed it can follow. This module is that machinery, kept deliberately
free of HTTP so it can be unit-tested with plain ``pytest`` and reused by any
transport:

* :class:`SimStepper` -- the *seam*: one object that knows how to advance the
  simulation by exactly one tick and describe itself. The loop is brain-agnostic;
  a stepper may be scripted (:class:`ScriptedStepper`, free and offline), the
  Penn generative-agents ``step()`` seam (#296), or a real-LLM brain later
  (#261) -- the loop and every API route are unchanged either way.
* :class:`EventLog` -- an append-only, capped log with a monotonic cursor. The
  change feed's single source of truth: ``GET /events?since=`` and ``WS /ws``
  are two doors into this one log (#262), which is what makes reconnect-without-
  gaps-or-duplicates possible.
* :class:`LiveRunController` -- the run-control seam (#349): pause/resume/reset
  as plain method calls, driven by the HTTP routes but testable without them.
* :func:`run_loop` -- the asyncio task that ties them together: sleep a tick,
  step the sim in a worker thread (the engine is synchronous), publish the
  resulting frame at the tick boundary.

Only the stdlib is imported here -- no FastAPI -- so ``tests/test_live_loop.py``
runs even without the ``server`` extra installed.
"""

from __future__ import annotations

import asyncio
import collections
import threading
from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class SimStepper(Protocol):
    """The one-tick seam the live loop drives.

    ``tick()`` and ``reset()`` are ALWAYS called while the API's request lock is
    held (the loop takes it before calling), so they may freely mutate the
    served ``Game`` -- but ``reset()`` must restore that *same* object in place,
    because every route closes over it.

    Some attributes are OPTIONAL, probed with ``getattr`` per request (they
    are not part of the protocol, so a minimal stepper can skip any of them).
    This list is the registry -- a new probed attribute belongs here:

    * ``ledger`` -- a :class:`~text_adventure_games.usage.UsageLedger`; when
      present, ``GET /usage`` reports it (tokens/cost -- ~0 under the mock
      brain, real numbers once #261 swaps a live one in).
    * ``drain_events() -> list[dict]`` -- engine change-feed records (the
      ``reporting.JSONRenderer`` shape) formed during the last ``tick()``; the
      loop appends each as a ``kind: "engine"`` record, honoring #262's "reuse
      the JSONRenderer as the log's source" without coupling the loop to the
      game's parser.
    * ``run_usage() -> dict`` -- additive per-run usage fields
      (``run_calls``/``run_cost_usd``) merged into ``GET /usage`` beside the
      lifetime summary (#526); the ledger itself stays lifetime.
    * ``run_store`` / ``run_id`` -- the #304 persistence seam: the
      :class:`backend.run_store.RunStore` this stepper records into, and the
      id of the run it is currently appending to. When present, the ``/runs``
      registry family (#306) serves that history; without them ``GET /runs``
      answers ``available: false`` and the per-id routes 404.
    * ``resume_run(run_id)`` -- adopt a persisted run as the live one
      (#543); without it ``POST /runs/{run_id}/resume`` answers 501 even
      when a ``run_store`` is present.
    """

    @property
    def step(self) -> int:
        """Completed ticks since construction (or the last ``reset()``)."""
        ...

    def meta(self) -> dict:
        """The handshake blob ``GET /live`` serves. Opaque to the backend.

        For the Penn viewer this is the replay-meta shape --
        ``{tile_px, width, height, sec_per_step, start, vision_r,
        personas: [{name, emoji}]}`` -- so a live client spawns agents exactly
        the way the baked ``penn_replay.json`` loader does."""
        ...

    def tick(self) -> dict | None:
        """Advance the sim one step and return the per-agent frame.

        The frame uses the replay schema -- ``{name: {"x": int, "y": int,
        "act": str, "e": str, ...}}`` -- the same per-step dict the bake writes,
        so live and baked clients share one contract. Returning ``None`` means
        "the run is finished": the loop auto-pauses and publishes a
        ``status(reason="finished")`` record instead of a frame."""
        ...

    def reset(self) -> None:
        """Rebuild the sim to t0 in place; ``step`` goes back to 0."""
        ...


class EventLog:
    """Append-only event log with a monotonic 1-based cursor (#262).

    The cursor NEVER resets -- not on ``reset()``, not on eviction -- so a
    client that remembers the last cursor it saw can always ask "everything
    after N" and get no duplicates. The log is capped (a ``deque`` with
    ``maxlen``); when old records fall off, the numbering keeps climbing, so a
    gap is *detectable*: if the first record returned has
    ``cursor > since + 1``, the client missed evicted records and should
    re-sync from ``/world_state`` + ``/live`` instead of trusting the tail.

    Thread-safety contract:

    * ``since()`` / ``latest_cursor()`` / ``oldest_cursor()`` -- any thread
      (the sync HTTP handlers run in a thread pool); guarded by an internal lock.
    * ``append()`` and ``subscribe()``/``unsubscribe()`` -- **event loop only**
      (the ``run_loop`` task and the async run-control handlers). That invariant
      makes waking subscribers a plain ``asyncio.Event.set()`` with no
      cross-thread handoff.
    """

    def __init__(self, max_records: int = 10_000):
        self._lock = threading.Lock()
        self._records: collections.deque[dict] = collections.deque(maxlen=max_records)
        self._next_cursor = 1
        self._subscribers: set[asyncio.Event] = set()

    def append(self, kind: str, **fields) -> dict:
        """Stamp the next cursor onto a ``{cursor, kind, **fields}`` record,
        retain it, and wake every waiting subscriber. Event loop only."""
        with self._lock:
            record = {"cursor": self._next_cursor, "kind": kind, **fields}
            self._next_cursor += 1
            self._records.append(record)
        for waiter in list(self._subscribers):
            waiter.set()
        return record

    def since(self, cursor: int) -> list[dict]:
        """Every retained record with ``cursor >`` the given one, oldest first.
        Callers must treat the returned records as read-only."""
        with self._lock:
            return [r for r in self._records if r["cursor"] > cursor]

    def latest_cursor(self) -> int:
        """The cursor of the newest record ever appended (0 when none yet)."""
        with self._lock:
            return self._next_cursor - 1

    def oldest_cursor(self) -> int | None:
        """The cursor of the oldest *retained* record (``None`` on an empty
        log). ``oldest_cursor() > 1`` means eviction has happened."""
        with self._lock:
            return self._records[0]["cursor"] if self._records else None

    def subscribe(self) -> asyncio.Event:
        """Register and return a waiter that ``append()`` will ``set()``.
        The subscriber loop is: ``clear()``, drain ``since(cursor)``, and only
        then ``await wait()`` -- clearing before reading makes the race benign
        (a record appended in between just makes ``wait()`` return at once)."""
        waiter = asyncio.Event()
        self._subscribers.add(waiter)
        return waiter

    def unsubscribe(self, waiter: asyncio.Event) -> None:
        self._subscribers.discard(waiter)


class LiveRunController:
    """Run-control over an injected :class:`SimStepper` (#349's control seam).

    Pure state machine: no HTTP, no log -- the async layer (:func:`run_loop`
    plus the route handlers) decides what to publish. ``paused``/``running``
    are plain attribute flips read without the lock (stale-by-a-tick reads are
    fine; the flags gate the *next* tick, never a running one).

    ``generation`` closes the reset-vs-in-flight-tick race: a tick that started
    before a ``reset()`` finishes with the old generation stamped on its
    result, and :func:`run_loop` drops it instead of publishing a stale frame.

    ``start_paused`` boots the loop armed but not ticking: reads work, the
    feed carries the ``started`` status, and the first frame waits for a
    ``resume()`` (``POST /resume``) -- how a paying real-LLM sim holds its
    first model call until someone actually presses Start in the viewer.
    """

    def __init__(
        self,
        stepper: SimStepper,
        lock: threading.Lock,
        *,
        start_paused: bool = False,
    ):
        self._stepper = stepper
        self._lock = lock
        self.paused = start_paused
        self.running = False  # set/cleared by run_loop, read by the routes
        self.generation = 0

    def tick_once(self) -> dict:
        """One tick under the app lock. Runs in a worker thread (or directly in
        unit tests). Returns what the loop should publish -- ``agents`` is the
        frame for index ``step`` (``None`` when the stepper says finished)."""
        with self._lock:
            generation = self.generation
            step = self._stepper.step  # the index of the frame this tick makes
            agents = self._stepper.tick()
            drain = getattr(self._stepper, "drain_events", None)
            events = list(drain()) if drain is not None else []
        return {
            "generation": generation,
            "step": step,
            "agents": agents,
            "events": events,
        }

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def reset(self) -> None:
        """Rebuild t0 under the app lock (worker thread -- may be slow)."""
        with self._lock:
            self._stepper.reset()
            self.generation += 1

    def status(self) -> dict:
        """The shared payload of every ``status`` record and run-control
        response. Lock-free: ``step`` may lag an in-flight tick by one, which
        is harmless for an informational read."""
        return {
            "running": self.running,
            "paused": self.paused,
            "step": self._stepper.step,
        }


async def run_loop(
    controller: LiveRunController, log: EventLog, tick_seconds: float
) -> None:
    """The #349 stepping task: sleep, tick in a worker thread, publish.

    The tick boundary is the publish point (#262): each completed step appends
    one ``frame`` record (plus any drained ``engine`` records), which wakes
    every ``WS /ws`` subscriber. Pausing keeps the task alive (reads keep
    working; ticking stops); cancellation is the clean shutdown path and still
    publishes a final ``status(reason="stopped")`` record.
    """
    loop = asyncio.get_running_loop()
    controller.running = True
    log.append("status", reason="started", **controller.status())
    try:
        while True:
            await asyncio.sleep(tick_seconds)
            if controller.paused:
                continue
            result = await loop.run_in_executor(None, controller.tick_once)
            if result["generation"] != controller.generation:
                continue  # a reset raced this tick; drop the stale frame
            if result["agents"] is None:
                controller.pause()  # run finished: stop ticking, keep serving
                log.append("status", reason="finished", **controller.status())
                continue
            log.append("frame", step=result["step"], agents=result["agents"])
            for event in result["events"]:
                log.append("engine", step=result["step"], event=event)
    finally:
        controller.running = False
        log.append("status", reason="stopped", **controller.status())


class ScriptedStepper:
    """A :class:`SimStepper` with no simulation behind it -- frames come from a
    list (cycled forever) or a callable (``frames(step) -> dict | None``, where
    ``None`` means the run is finished). The free, offline stand-in that lets
    the whole live surface (loop, feed, routes, viewer) be exercised with zero
    keys -- the same role ``MockReActClient`` plays for the LLM layer.

    ``on_tick(step)`` (optional) runs *before* the frame lookup each tick --
    "advance the world, then snapshot it" -- and may return engine records
    (the ``JSONRenderer`` shape) to publish; ``on_reset()`` (optional) undoes
    whatever ``on_tick`` did to external state. Set ``.ledger`` (and optionally
    ``.run_usage``) after construction to back ``GET /usage``.
    """

    def __init__(
        self,
        frames: list[dict] | Callable[[int], dict | None],
        meta: dict | None = None,
        on_tick: Callable[[int], list[dict] | None] | None = None,
        on_reset: Callable[[], None] | None = None,
    ):
        self._frames = frames
        self._meta = dict(meta or {})
        self._on_tick = on_tick
        self._on_reset = on_reset
        self._step = 0
        self._pending_events: list[dict] = []
        self.ledger = None

    @property
    def step(self) -> int:
        return self._step

    def meta(self) -> dict:
        return dict(self._meta)

    def tick(self) -> dict | None:
        if self._on_tick is not None:
            events = self._on_tick(self._step)
            if events:
                self._pending_events.extend(events)
        if callable(self._frames):
            frame = self._frames(self._step)
        elif self._frames:
            frame = self._frames[self._step % len(self._frames)]
        else:
            frame = {}
        if frame is None:
            return None  # finished; step deliberately not counted
        self._step += 1
        return frame

    def drain_events(self) -> list[dict]:
        drained, self._pending_events = self._pending_events, []
        return drained

    def reset(self) -> None:
        self._step = 0
        self._pending_events = []
        if self._on_reset is not None:
            self._on_reset()
