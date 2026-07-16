"""Serve the Penn campus sim LIVE over the backend API (issues #263/#297/#349).

Where ``generate_penn_replay.py`` runs the whole sim offline and writes a baked
``penn_replay.json`` the Godot viewer loads once, this script steps the *same*
configured Penn world (``penn_world.build_penn_world``, #297) one tick at a time
inside ``backend.api``'s self-stepping live loop (#349) -- so the viewer follows
it over real HTTP + WebSocket (#262/#263) instead of reading a file.

Two brains (#261). The default is the deterministic mock: real requests, zero
LLM keys, zero spend, authored ``meetings:`` dialogue painted on. With
``--brain llm`` the model named by the world YAML's ``llm:`` block -- Anthropic
Claude Haiku -- makes every decide/converse/reflect call instead: agents choose
their actions, speak for themselves when the routing brings them together
(perception-gated, scripted dialogue off), and reflect; every request is
metered by the terminal monitor and the ``max_cost_usd`` kill-switch ends the
day if spend reaches the ceiling.

Run from the repo root (terminal 1), then point the viewer at it (terminal 2)::

    uv sync --extra server
    uv run python godot-generative-agents/backend/penn/serve_penn.py --tick-seconds 0.1
    SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh

    # the real thing (uv sync --extra server --extra llm, key required):
    ANTHROPIC_API_KEY=sk-ant-... \
        uv run python godot-generative-agents/backend/penn/serve_penn.py --brain llm

The pieces:

* :class:`PennStepper` -- implements the ``backend.live.SimStepper`` protocol by
  reconstructing ``simulate()``'s pre-loop setup (the same reconstruction
  ``godot-generative-agents/tests/test_penn_live.py`` pins) and driving the extracted
  one-tick ``step()`` seam (#296) per ``tick()``. Frames come out in the exact
  replay schema the bake writes (``penn_world.replay_frame_entry``), so every
  viewer feature -- bubbles, links, trails, minimap, heatmap -- works unchanged.
* :class:`LiveMeetingInjector` -- the live port of the bake's post-hoc
  ``_inject_scripted_conversations``: the mock brain never speaks, so the
  authored ``meetings:`` dialogue is painted onto outgoing frames on the fly,
  the moment all participants are genuinely within perception range.
"""

import argparse
import concurrent.futures
import os
import threading
import time

from backend.api import run
from backend.contract import SCHEMA_VERSION
from backend.env import load_dotenv
from backend.llm_monitor import LlmCallMonitor, RoleTaggedLedger
from backend.run_simulation import step
from backend.run_store import DEFAULT_RUNS_DIR, RunStore
from backend.sim_config import CognitionConfig
from backend.cognition import attach_agents
from penn_world import (
    DIALOGUE_FADE_STEPS,
    DIALOGUE_LINE_STEPS,
    PENN_ACTION_VERBS,
    SEC_PER_STEP,
    SIM_START,
    PennWorld,
    build_penn_world,
    persona_meta_entry,
    replay_frame_entry,
)
from text_adventure_games.llm_client import LlmConfig, create_llm_client
from text_adventure_games.usage import UsageLedger

# The bake's full campus day (generate_penn_replay.DEFAULT_STEPS): long enough
# for every authored meeting to convene and the whole cast to finish its rounds.
DEFAULT_STEPS = 1200

# --stall-seconds (debug) holds every Nth step to fake a real brain's decision
# latency, so the viewer's "thinking…" indicator (#372) is testable under the
# free mock brain. Off unless --stall-seconds > 0.
STALL_EVERY_STEPS = 10

# The model --brain llm falls back to if the world's llm: block names none.
# Claude Haiku: a campus day is dozens-to-hundreds of low-stakes calls, so the
# cheapest current Anthropic model is the right default (issue #261).
DEFAULT_LLM_MODEL = "claude-haiku-4-5"


def resolve_llm(world_llm, brain, model=None, max_cost=None):
    """Resolve one run's LLM settings: ``None`` for the mock brain, else a dict.

    ``--brain mock`` (the default) returns ``None`` -- no client is ever built,
    no key is needed, nothing is spent, and whatever the world YAML declares is
    ignored. ``--brain llm`` starts from the world's ``llm:`` block and lets the
    CLI override the ``model`` and ``max_cost_usd`` for one run.

    Deliberately Anthropic-only and ``ANTHROPIC_API_KEY``-only: this never
    reads ``LLM_PROVIDER`` / ``LLM_API_KEY`` / ``LLM_MODEL`` (the engine's
    ``client_from_env`` knobs), so a stray key for some other provider sitting
    in the environment can never be picked up by a Penn run. Both failure modes
    (wrong provider, missing key) exit with a one-line fix rather than serving
    an all-day sim whose every model call silently returns ``None``.

    Note what is intentionally NOT configurable here: the daily planner. The
    authored YAML schedules (and the rendezvous routing built on them) stay in
    charge of the day's itinerary -- ``backend.planner.LLMPlanner`` validates
    stops against the world's location names, and a generated
    schedule would undo the hand-tuned meeting overlaps. A Penn-aware planner
    is follow-up work; decide/converse/reflect are the model's here.
    """
    if brain != "llm":
        return None
    llm = dict(world_llm or {})
    if model is not None:
        llm["model"] = model
    if max_cost is not None:
        llm["max_cost_usd"] = max_cost
    provider = str(llm.get("provider", "anthropic")).lower()
    if provider != "anthropic":
        raise SystemExit(
            f"--brain llm supports only provider 'anthropic' (the llm: block in "
            f"world_data_upenn.yaml says {provider!r})."
        )
    llm["provider"] = "anthropic"
    llm.setdefault("model", DEFAULT_LLM_MODEL)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "--brain llm needs ANTHROPIC_API_KEY: export it, or put it in a "
            "repo-root .env file (template: .env.example). "
            "(--brain mock runs offline, without keys)"
        )
    return llm


class LiveMeetingInjector:
    """Paint authored dialogue onto live frames -- proximity-honestly, on the fly.

    The live port of the bake's ``_inject_scripted_conversations``: same window
    math (``len(dialogue) * DIALOGUE_LINE_STEPS + DIALOGUE_FADE_STEPS`` frames of
    the full transcript, which the viewer paces line-by-line itself), same clash
    rules (a participant already mid-conversation blocks arming), same "never
    faked across the map" rule (a meeting arms only when every participant is
    mutually within ``vision_r`` tiles).

    Two honest differences, because live code can't see the future:

    * The bake scans the finished run for the LONGEST co-location window --
      which the rendezvous routing makes the dwell at the authored venue. Live,
      "first mutual co-location" alone would misfire (Maya and Priya spawn a
      few tiles apart, so the Moelis study session would start in the dorms):
      a meeting with a resolvable ``at:`` venue therefore also waits until
      every participant is *settled at that venue* -- its ``act`` reads
      ``"<activity> @ <venue address>"``, not a ``walking to ...`` leg.
    * Once fired, the exchange plays for its full window even if participants
      drift apart mid-exchange (the conversation link just stretches).

    Each meeting fires at most once per run; ``reset()`` re-arms.
    """

    ARMED, FIRING, DONE = range(3)

    def __init__(
        self,
        meetings,
        vision_r,
        locations=None,
        line_steps=DIALOGUE_LINE_STEPS,
        fade_steps=DIALOGUE_FADE_STEPS,
    ):
        self.vision_r = vision_r
        # Resolve each meeting's `at:` name to its tile address (the same
        # name->address lookup the rendezvous routing uses); None = no venue
        # authored (or not resolvable), which degrades to proximity-only.
        addr_of = {loc["name"]: loc.get("address") for loc in (locations or [])}
        self._meetings = []
        for m in meetings:
            participants = list(m.get("participants", []))
            dialogue = [[str(s), str(t)] for s, t in m.get("dialogue", [])]
            if len(participants) < 2 or not dialogue:
                continue  # bad spec: skip, exactly like the bake
            self._meetings.append(
                {
                    "label": m.get("label", " + ".join(participants)),
                    "participants": participants,
                    "dialogue": dialogue,
                    "venue": addr_of.get(m.get("at")),
                    # Frames the whole exchange needs (incl. the final fade).
                    "need": len(dialogue) * line_steps + fade_steps,
                    "state": self.ARMED,
                    "start": -1,
                }
            )

    def _mutually_close(self, frame, participants):
        points = []
        for p in participants:
            entry = frame.get(p)
            if entry is None:
                return False  # participant not in this cast/frame
            points.append((entry["x"], entry["y"]))
        for a in range(len(points)):
            for b in range(a + 1, len(points)):
                dx = points[a][0] - points[b][0]
                dy = points[a][1] - points[b][1]
                if (dx * dx + dy * dy) ** 0.5 > self.vision_r:
                    return False
        return True

    def _settled_at_venue(self, frame, meeting):
        """Every participant is *at* the meeting's venue, doing something there.

        A frame's ``act`` is ``"<activity> @ <tile address>"`` (see
        ``run_simulation.step``); a travel leg reads ``"walking to <name> @
        <destination address>"``, which carries the venue's address the whole
        way there -- so the walking prefix must be excluded or the meeting
        would fire mid-commute. No authored venue -> trivially true."""
        venue = meeting["venue"]
        if not venue:
            return True
        for p in meeting["participants"]:
            act = frame.get(p, {}).get("act") or ""
            if not act.endswith(f"@ {venue}") or act.startswith("walking to "):
                return False
        return True

    def apply(self, frame, step_idx):
        """Mutate *frame* in place: write each firing meeting's transcript onto
        its participants' ``chat``. Called once per tick, after the sim step."""
        firing_cast = {
            p
            for m in self._meetings
            if m["state"] == self.FIRING
            for p in m["participants"]
        }
        for m in self._meetings:
            if (
                m["state"] == self.ARMED
                # Don't garble a participant already mid-conversation -- whether
                # in another authored meeting or (later, #261) a real-LLM chat.
                and not (set(m["participants"]) & firing_cast)
                and not any(
                    frame[p].get("chat") for p in m["participants"] if p in frame
                )
                and self._mutually_close(frame, m["participants"])
                and self._settled_at_venue(frame, m)
            ):
                m["state"], m["start"] = self.FIRING, step_idx
                firing_cast.update(m["participants"])
                print(f"  - FIRE  {m['label']} @ step {step_idx}")
            if m["state"] == self.FIRING:
                if step_idx - m["start"] < m["need"]:
                    for p in m["participants"]:
                        if p in frame:
                            frame[p]["chat"] = m["dialogue"]
                else:
                    m["state"] = self.DONE

    def reset(self):
        for m in self._meetings:
            m["state"], m["start"] = self.ARMED, -1


def _fast_forward_schedule(schedule, step_idx: int) -> None:
    """Point *schedule* (a ``ScheduleMockClient``) at the stop a resumed day
    should be working on at *step_idx* (#543).

    Only authored dwell times are budgeted -- the steps an agent spent walking
    between stops aren't stored anywhere -- so this is a deliberate
    approximation that can land a stop early relative to the original day. A
    ``steps: None`` stop ("stay here for the rest of the day") always holds,
    and a schedule that runs out settles on its last stop, exactly like the
    live loop's own ``advance()`` handling.
    """
    elapsed = 0
    while schedule.steps is not None and elapsed + schedule.steps <= step_idx:
        elapsed += schedule.steps
        if not schedule.advance():
            break


class _DecideThreads:
    """A ``submit()``-compatible executor that runs each decision on its own
    daemon thread instead of a shared pool (#366 review fixes).

    Two failure modes of ``ThreadPoolExecutor`` motivated this: its non-daemon
    workers are JOINED at interpreter exit, so one decide hung on a provider
    socket blocked ``POST /shutdown``/Ctrl-C for the client's whole retry
    budget; and its fixed worker set let stragglers abandoned by ``POST
    /reset`` starve the new world's decisions. Daemon threads cost ~nothing
    next to an LLM round-trip and die silently with the process.

    ``max_workers`` is honored via a semaphore: at most that many decisions
    run at once (the rate-limit knob ``--decide-workers`` promises), the rest
    queue behind it. A queued decide that misses its tick's timeout window
    parks like any straggler and its perceive runs late -- against a world the
    serial phase may be mutating -- which at worst raises and degrades to the
    pinned outage-idle path, exactly like a failed provider call.
    """

    def __init__(self, max_workers):
        self._slots = threading.Semaphore(max_workers)

    def submit(self, fn, /, *args, **kwargs):
        future = concurrent.futures.Future()

        def _run():
            with self._slots:
                if not future.set_running_or_notify_cancel():
                    return
                try:
                    future.set_result(fn(*args, **kwargs))
                except BaseException as exc:
                    future.set_exception(exc)

        threading.Thread(target=_run, daemon=True, name="decide").start()
        return future


class PennStepper:
    """The Penn campus sim behind the ``backend.live.SimStepper`` seam.

    Reconstructs ``simulate()``'s pre-loop setup (build the patched world,
    attach the mock brains, seed each persona's per-step ``state``) and then
    drives the extracted one-tick ``step()`` per ``tick()`` call -- so N ticks
    produce exactly the frames ``simulate(world_map, N)`` would
    (``godot-generative-agents/tests/test_penn_live.py`` pins that equivalence).

    ``reset()`` rebuilds *everything* from a fresh ``build_penn_world()``: the
    routing patches carry per-venue round-robin counters in closures, so
    reusing the old world would hand later runs different rendezvous slots.
    That means the served ``Game`` is a new object after a reset -- which is why
    :func:`main` hands the API a :class:`_GameProxy` rather than the game
    itself. The ``ledger`` deliberately survives resets (money spent stays
    spent; ~$0 under the mock, real Haiku numbers under ``--brain llm``).
    """

    def __init__(
        self,
        num_steps=DEFAULT_STEPS,
        endless=False,
        world=None,
        monitor=None,
        llm=None,
        run_store=None,
        cognition_tools=False,
        decide_workers=0,
        decide_timeout=30.0,
        mock_latency=0.0,
        stall_seconds=0.0,
        resume_run_id=None,
    ):
        self.num_steps = num_steps
        self.endless = endless
        # Concurrent decisions (#366): with decide_workers > 0, every agent at
        # a decision point decides in parallel inside step(), each bounded by
        # decide_timeout seconds of wall clock. 0 = today's serial path,
        # byte-identical (and what the simulate-equivalence test pins).
        # Concurrency is min(decide_workers, cast): _DecideThreads caps live
        # decides at decide_workers (the provider rate-limit knob), and
        # step() keeps at most one in-flight decision per agent.
        # mock_latency > 0 makes each ScheduleMockClient decide sleep that
        # long -- an offline stand-in for real provider latency.
        self.decide_timeout = decide_timeout
        self.mock_latency = mock_latency
        self._decide_executor = (
            _DecideThreads(decide_workers) if decide_workers > 0 else None
        )
        # How many agents were at a decision point in the last tick() -- the
        # live loop stamps it onto each frame record (live.py) so a viewer can
        # tell "thinking" from "frozen" (#372).
        self.last_deciders = None
        # DEBUG (#372): hold every STALL_EVERY_STEPS-th step this long to fake a
        # real brain's decision latency so the viewer's "thinking…" cue can be
        # exercised under the free mock brain. 0.0 = off (byte-identical timing).
        self.stall_seconds = stall_seconds
        # The #304 persistence seam: a backend.run_store.RunStore, or None (the
        # default -- nothing is written, byte-identical to before). Set before
        # the _build() below so every build, first boot and each POST /reset,
        # opens its own run in the store.
        if resume_run_id is not None and run_store is None:
            raise ValueError("resuming a run needs a run store (--persist)")
        self.run_store = run_store
        self._run_id = None
        self._run_finished = False
        self._mem_synced = {}
        # Dollars the resumed run had already spent before this process (#543):
        # the ledger restarts at $0 with the process, so the stored cost column
        # is topped up from this base, never overwritten backwards.
        self._cost_base = 0.0
        # The #514 switch for the #512 wiring: agentic recall/query_knowledge/
        # read_plan before each decide. Held on the stepper -- not read from
        # argv -- so _build() re-applies it on every reset (POST /reset).
        self.cognition_tools = cognition_tools
        # Resolved LLM settings (resolve_llm), or None for the mock brain. The
        # ledger's cost ceiling comes from the same block, so GET /usage
        # reports the budget and tick() can end the day at it.
        self.llm = llm
        self.ledger = UsageLedger(  # backs GET /usage across resets
            max_cost_usd=(llm or {}).get("max_cost_usd")
        )
        # The terminal request monitor (backend.llm_monitor), or None for quiet.
        # Like the ledger it lives here, not in _build(), so its call counter
        # survives resets.
        self.monitor = monitor
        # The real-brain clients (issue #261): one shared by decide + converse,
        # one for reflection -- separate instances so the request monitor can
        # tag each role exactly, all recording into self.ledger. Built once
        # here (they are stateless apart from ledger/context) and re-wired onto
        # fresh agents by every _build().
        self.llm_client = None
        self.reflector_client = None
        if llm is not None:
            self._llm_config = LlmConfig(provider="anthropic", model=llm.get("model"))
            self.llm_client = self._decide_client()
            self.reflector_client = create_llm_client(
                self._llm_config, ledger=self._recording_ledger("reflect")
            )
        # Per-agent decide clients (#366): created once per persona on first
        # _build and RE-WIRED (not rebuilt) by later resets -- each SDK client
        # owns a real connection pool, so rebuilding N of them per POST /reset
        # would orphan the old pools.
        self._agent_clients = {}
        self._build(world, resume_run_id=resume_run_id)

    def _decide_client(self):
        """One decide/converse client recording into the shared ledger.

        With the monitor on, the ledger is a RoleTaggedLedger view bound to
        this client's own mutable ``context`` -- the call sites stamp
        ``role``/``actor`` per call and the view reads them live, so every
        instance (the shared mode-flag client and each per-agent brain) labels
        its monitor rows correctly.
        """
        view = self._recording_ledger("decide")
        client = create_llm_client(self._llm_config, ledger=view)
        ctx = getattr(client, "context", None)
        if isinstance(view, RoleTaggedLedger) and ctx is not None:
            view.bind_context(ctx)
        return client

    def _recording_ledger(self, role):
        """What a client should record into: the base ledger, or -- when the
        monitor is on -- a write-through view of it that also prints one
        terminal line per call, tagged *role*."""
        if self.monitor is None:
            return self.ledger
        return RoleTaggedLedger(self.ledger, self.monitor, role=role)

    def _build(
        self,
        world: PennWorld | None = None,
        resume_run_id=None,
        resume_row=None,
        resume_frames=None,
    ):
        # Mirror simulate()'s pre-loop setup exactly (run_simulation.py; the
        # same reconstruction tests/test_penn_live.py::
        # test_stepper_matches_simulate_prefix pins). If simulate's setup ever
        # drifts from this, the equivalence test fails -- on purpose.
        self.world = world if world is not None else build_penn_world()
        self.cog = CognitionConfig(cognition_tools=self.cognition_tools)
        self.game, self.chars = self.world.build_world_fn(self.world.world_map)
        # How much of game.events drain_events() has already published
        # (#467). Lives in _build so reset() restarts it with the new game.
        self._events_seen = 0
        # ...and how much the #307 persistence hook has flushed to the store.
        # Its own cursor: --persist must never steal rows from the feed above.
        self._persist_events_seen = 0
        # Every client records into self.ledger; with a monitor, through a
        # write-through view that also prints one terminal line per call (the
        # base ledger stays the single source GET /usage sums). Under the mock
        # brain the schedule clients this ledger feeds ARE the brains; under a
        # real brain they only pace the day and never call a model.
        attach_agents(
            self.chars,
            self.world.personas,
            ledger=self._recording_ledger("decide"),
            vision_r=self.cog.vision_r,
            cognition_tools=self.cog.cognition_tools,
            num_steps=self.num_steps,
            # The #261 swap: with a real client every agent's decide (and its
            # conversation lines) go through the model, and reflection passes
            # run when enough importance accrues. With None (mock mode) both
            # fall back exactly as before. No planner_client on purpose: the
            # authored schedules own the itinerary (see resolve_llm).
            llm_client=self.llm_client,
            reflector_client=self.reflector_client,
            extra_action_names=PENN_ACTION_VERBS,
        )
        # In-flight decisions from earlier ticks ({name: Future}, #366). Fresh
        # per build: a straggler still running across a reset references the
        # OLD world -- harmless, because parked results are always discarded.
        self._decide_pending = {}
        if self.mock_latency > 0:
            for char in self.chars.values():
                char.agent.schedule.latency_s = self.mock_latency
        if self.llm is not None and self._decide_executor is not None:
            # Parallel decides need one client instance PER AGENT: the engine
            # clients carry a single mutable `context` dict that the decide
            # path stamps per call (and _resilient_create writes mid-call), so
            # N threads through one shared client would clobber each other's
            # attribution. Each instance records into the same base ledger;
            # self.llm_client stays as the mode flag (injector gate,
            # conversation_enabled) and the serial fallback.
            for name, char in self.chars.items():
                if name not in self._agent_clients:
                    self._agent_clients[name] = self._decide_client()
                char.agent.llm_client = self._agent_clients[name]
        # Real conversations pace themselves through a per-pair cooldown that
        # must OUTLIVE each tick (simulate() keeps one for its whole run;
        # step()'s default is a throwaway dict, which would let a settled pair
        # re-converse every single step). Fresh per day, like the rest of the
        # world state.
        self._convo_cooldowns = {}
        self.emoji = {p["name"]: p["emoji"] for p in self.world.personas}
        self.order = [p["name"] for p in self.world.personas]
        self.state = {}
        for spec in self.world.personas:
            char = self.chars[spec["name"]]
            self.state[char.name] = {
                "tile": tuple(spec["start_tile"]),
                "path": [],
                "pron": self.emoji[char.name],
                "desc": f"waking up @ {char.location.tile_address}",
                "performing": False,
                "perform_until": None,
                "reasoning": "(waking up)",
                "memories": [],
                "chat": None,
            }
        self.injector = LiveMeetingInjector(
            # Under a real brain the authored dialogue stands down entirely:
            # the rendezvous routing still walks the cast together, but what
            # they say when they meet comes from the model -- on-screen chat is
            # never ambiguous about its author. (The injector object stays so
            # apply()/reset() call sites are mode-blind.)
            [] if self.llm_client is not None else self.world.meetings,
            vision_r=self.cog.vision_r,
            locations=self.world.locations,
        )
        self._step_idx = 0
        # Per-run ledger baseline (#526): the ledger itself survives resets
        # on purpose (the cost ceiling is lifetime -- money spent stays
        # spent), so the per-run view SUBTRACTS this snapshot instead of
        # rebasing anything. Same boundary as the store's run id above.
        self._run_ledger_calls_base = len(self.ledger.records)
        self._run_ledger_cost_base = self.ledger.total_cost_usd()
        # Open this day's run in the store (#304). The manifest is the same
        # meta() blob the live handshake serves; each _build() gets its own id
        # -- unless we are resuming a persisted run (#543), which adopts the
        # existing id and picks the day up where the store left off.
        if self.run_store is not None:
            self._run_finished = False
            self._mem_synced = {name: -1 for name in self.order}
            self._cost_base = 0.0
            if resume_run_id is not None:
                self._adopt_run(resume_run_id, row=resume_row, frames=resume_frames)
            else:
                self._run_id = self.run_store.create_run(self.meta())

    def _resumable_row(self, run_id: str) -> dict:
        # The one guard home for both resume entry paths (boot --resume and
        # POST /runs/{id}/resume): the run must exist, and its recorded cast
        # must be the cast this world builds -- resuming a run whose personas
        # the current YAML no longer produces would seed tiles and memories
        # for the wrong people.
        row = self.run_store.get_run(run_id)
        if row is None:
            raise KeyError(f"unknown run id: {run_id}")
        stored = [p.get("name") for p in row["manifest"].get("personas", [])]
        if stored != self.order:
            raise ValueError(
                f"run {run_id} was recorded with cast {stored}, but this world "
                f"builds {self.order} -- resume needs the same world YAML"
            )
        # ...and on this campus map: regenerating the tmj is routine
        # (tools/geo), and tiles seeded from the last frame of a
        # differently-sized map would land agents out of bounds or in walls.
        current = self.meta()
        for key in ("schema_version", "width", "height"):
            if row["manifest"].get(key) != current[key]:
                raise ValueError(
                    f"run {run_id} was recorded on a different map "
                    f"({key} {row['manifest'].get(key)}, now {current[key]}) -- "
                    "resume needs the map it was recorded on"
                )
        return row

    def _adopt_run(self, run_id: str, row=None, frames=None) -> None:
        """Pick a persisted run back up where the store left off (#543).

        ``resume_run`` passes through the *row*/*frames* its pre-teardown
        guards already fetched, so a long run's frames file isn't parsed
        twice under the app lock; the boot path (``--resume``) leaves them
        ``None`` and they are fetched here, once.

        Memory-first resume: the freshly built world stays fresh, and only
        what the store holds durably is restored --

        * the step counter (``len(frames)``: the frames file is the authority,
          the row's ``steps`` column can lag one behind after a crash; it also
          keeps ``append_frame``'s step == line-count invariant by
          construction),
        * each agent's rendered position (the last frame's x/y),
        * each schedule's cursor (fast-forwarded by authored dwell times),
        * each agent's memory stream (lossless, the ``query_memories``
          pattern), and
        * the run's spend so far (``_cost_base``).

        Everything else is deliberately this-morning fresh: item properties,
        conversation cooldowns, meeting-injector arming, perform timers, and
        the ``_events_seen``/``_persist_events_seen`` cursors (correct -- the
        new ``game.events`` starts empty; the stored ``events.jsonl`` is
        append-only history).
        """
        if row is None:
            row = self._resumable_row(run_id)
        if frames is None:
            frames = self.run_store.read_frames(run_id)
        self._run_id = run_id
        self._step_idx = len(frames)
        if frames:
            last = frames[-1]
            for name in self.order:
                self.state[name]["tile"] = (
                    int(last[name]["x"]),
                    int(last[name]["y"]),
                )
                # desc/pron/reasoning stay at their waking-up defaults: the
                # first resumed tick is a decision point (no path, not
                # performing) and overwrites them all.
        for name in self.order:
            agent = self.chars[name].agent
            _fast_forward_schedule(agent.schedule, self._step_idx)
            records = self.run_store.hydrated_records(run_id, name)
            if records:
                # Replace the fresh seeds wholesale: the stored stream already
                # holds the original t=0 plan (and relationship) memories, so
                # keeping both would duplicate them. _next_id is private, but
                # the engine is deliberately untouched this cycle -- rows come
                # back ordered by record id, so max is last.
                agent.memory.records = records
                agent.memory._next_id = records[-1].id + 1
            self._mem_synced[name] = self.run_store.last_memory_id(run_id, name)
        # Top up, never rewind: the stored dollars predate this process's
        # ledger, and _persist_tick adds them to the run's ledger slice
        # (#526's baseline, snapshotted by _build just before this, makes
        # that slice start at $0 as of the adoption).
        self._cost_base = float(row["cost"])
        self.run_store.update_run(run_id, status="running")

    @property
    def step(self) -> int:
        return self._step_idx

    @property
    def run_id(self):
        """The store id of the current day's run, or None when not persisting."""
        return self._run_id

    def _run_cost_usd(self) -> float:
        # THE run-cost sum, defined once: this run's slice of the lifetime
        # ledger (#526's baseline) plus whatever the run spent before this
        # process (#543's _cost_base, 0 otherwise). _persist_tick writes it
        # to the run's row and run_usage() serves it to GET /usage, so the
        # two agree to the cent structurally, not by convention.
        return round(
            self._cost_base + self.ledger.total_cost_usd() - self._run_ledger_cost_base,
            6,
        )

    def run_usage(self) -> dict:
        """This run's slice of the lifetime ledger (#526).

        ``GET /usage`` probes for this optional method and merges the dict
        beside the (unchanged) lifetime totals, so the dashboard's run strip
        can agree with its per-run call log. The budget gate stays lifetime.
        ``run_cost_usd`` is ``_run_cost_usd()`` -- the sum the run's row gets
        too. ``run_calls`` stays this-process (the store keeps no cheap call
        count to re-anchor on).
        """
        return {
            "run_calls": len(self.ledger.records) - self._run_ledger_calls_base,
            "run_cost_usd": self._run_cost_usd(),
        }

    def meta(self) -> dict:
        """The handshake blob ``GET /live`` serves -- the baked replay's ``meta``
        shape (minus ``steps``, which a live run doesn't know up front), so the
        viewer spawns agents exactly the way the file loader does."""
        wm = self.world.world_map
        return {
            # The pinned replay contract this blob conforms to (#305), kept in
            # lock-step with the bake's meta so baked and live can't drift (#297).
            "schema_version": SCHEMA_VERSION,
            "tile_px": wm.tile_size,
            "width": wm.width,
            "height": wm.height,
            "sec_per_step": SEC_PER_STEP,
            "start": SIM_START,
            "vision_r": self.cog.vision_r,
            # Same projection the bake uses (penn_world.persona_meta_entry): name/
            # emoji for the sprite + sidebar, persona/home/schedule for the State
            # Details inspector (issue #408), so live and baked meta stay identical.
            "personas": [persona_meta_entry(p) for p in self.world.personas],
            # The t=0 seed social graph, already validated/normalized by
            # penn_world.relationships_meta at build time -- the same list the
            # bake writes, so the social-graph pop-up (#252) sees identical
            # seed edges live and baked.
            "relationships": self.world.relationships,
            # What is driving the cast: None under the mock brain, else the
            # provider/model, so the viewer can say which model it is watching.
            "llm": (
                {"provider": self.llm["provider"], "model": self.llm["model"]}
                if self.llm is not None
                else None
            ),
        }

    def tick(self) -> dict | None:
        """One sim step -> one replay-schema frame (called under the app lock).

        Returns ``None`` once the campus day is over (non-``endless``) -- or,
        before anything else, once cumulative spend has reached the ledger's
        cost ceiling (the ``llm:`` block's ``max_cost_usd``): ``simulate()``
        polls ``over_budget()`` every step and the live path must too, or a
        runaway day would keep paying until the schedule ran out. Either way
        the live loop auto-pauses and publishes ``status(reason="finished")``
        instead of an endless stream of identical frames. ``POST /reset``
        starts a new day (spent money stays spent, so a tripped ceiling stays
        tripped).
        """
        if self.ledger.over_budget():
            self._finish_run()
            return None
        if not self.endless and self._step_idx >= self.num_steps:
            self._finish_run()
            return None
        # DEBUG (#372): fake a decision stall so the head stops growing long
        # enough for the viewer's "thinking…" indicator to fire. Holding the app
        # lock here is the point -- pollers wait, exactly like a real brain mid-
        # decision. Off (0.0) leaves timing byte-identical.
        if (
            self.stall_seconds > 0.0
            and self._step_idx > 0
            and self._step_idx % STALL_EVERY_STEPS == 0
        ):
            time.sleep(self.stall_seconds)
        decide_info = {}
        raw, _chats = step(
            self.game,
            self.chars,
            self.state,
            self._step_idx,
            order=self.order,
            world_map=self.world.world_map,
            emoji=self.emoji,
            cog=self.cog,
            # Real conversations only when a real brain drives -- the same gate
            # simulate() applies (conversation_enabled = llm_client is not None).
            conversation_enabled=self.llm_client is not None,
            conversation_cooldowns=self._convo_cooldowns,
            # Concurrent decides (#366): None executor = the serial path the
            # simulate-equivalence test pins; workers > 0 fans decisions out.
            decide_executor=self._decide_executor,
            decide_timeout=self.decide_timeout,
            decide_pending=self._decide_pending,
            decide_info=decide_info,
        )
        self.last_deciders = decide_info.get("deciders", 0)
        for name in decide_info.get("timeouts", ()):
            # Mirror the injector's FIRE print: the skipped decision must be
            # visible in the run log (#366 acceptance).
            print(
                f"  - DECIDE TIMEOUT {name} @ step {self._step_idx} -- "
                "idling this tick; its answer will apply when the call resolves"
            )
        frame = {name: replay_frame_entry(raw[name]) for name in self.order}
        # Paint authored dialogue post-step, exactly where the bake's injector
        # runs (on the converted frames, never the engine state) -- so a future
        # real-LLM chat in `raw` composes: the clash rule above skips over it.
        self.injector.apply(frame, self._step_idx)
        if self.run_store is not None:
            self._persist_tick(frame)
        self._step_idx += 1
        return frame

    def _persist_tick(self, frame: dict) -> None:
        # Called with the pre-increment step index: frames.jsonl line N IS
        # step N. Memory sync is incremental by engine record id (monotonic
        # per agent), so each row is written exactly once across the run.
        self.run_store.append_frame(self._run_id, self._step_idx, frame)
        for name in self.order:
            memory = getattr(self.chars[name].agent, "memory", None)
            if memory is None:
                continue
            last = self._mem_synced.get(name, -1)
            fresh = [r.to_primitive() for r in memory.records if r.id > last]
            if fresh:
                self.run_store.record_memories(self._run_id, name, fresh)
                self._mem_synced[name] = fresh[-1]["id"]
        self._persist_pending_events()
        self.run_store.update_run(
            self._run_id,
            # The RUN's spend, not the server's lifetime total: the one
            # _run_cost_usd() sum GET /usage serves too (#526/#543).
            cost=self._run_cost_usd(),
            steps=self._step_idx + 1,
        )

    def _persist_pending_events(self) -> None:
        # GameEvents logged since the last flush -> events.jsonl (#307).
        # Also called by _finish_run() and reset(): POST /world/event can
        # land an event between the last tick and the day's close, where
        # the per-tick flush would never see it.
        if self.run_store is None or self._run_id is None:
            return
        pending = self.game.events[self._persist_events_seen :]
        if pending:
            self.run_store.append_events(
                self._run_id, [event.to_primitive() for event in pending]
            )
        self._persist_events_seen = len(self.game.events)

    def _finish_run(self) -> None:
        # Idempotent: the live loop keeps ticking a finished day (every tick
        # returns None) and only the first one flips the status. The tail
        # flush catches events logged after the final tick (#307).
        self._persist_pending_events()
        if (
            self.run_store is not None
            and self._run_id is not None
            and not self._run_finished
        ):
            self.run_store.update_run(self._run_id, status="finished")
            self._run_finished = True

    def drain_events(self) -> list:
        """New change-feed rows formed during the last ``tick()`` (#398, #467).

        ``backend.live`` probes this optional method after every tick and
        publishes each returned dict as a ``kind: "engine"`` change-feed
        record. Two row types ride it, told apart by their inner ``kind``:

        * ``"llm_call"`` -- the request monitor's kept records (a flattened
          :class:`~text_adventure_games.usage.CallRecord` plus ``role``/
          ``call_no``/``cum_cost_usd``/``time``), so the viewer's run monitor
          shows the same one-line-per-request log the terminal prints (#398).
        * ``"game_event"`` -- the engine ``GameEvent``s logged since the last
          drain (#467), ``to_primitive()`` dicts (the #305 EventState shape,
          identical to what the replay bake persists), e.g. the boil-water
          ``sickness`` events (#465).

        Assumes a finishing tick (``tick()`` -> ``None``) logs no new
        GameEvents -- backend.live drops drained rows for ``None`` ticks,
        same as llm_call rows since #398.
        """
        rows = []
        if self.monitor is not None:
            rows.extend(dict(rec, kind="llm_call") for rec in self.monitor.drain())
        new_events = self.game.events[self._events_seen :]
        self._events_seen = len(self.game.events)
        rows.extend(
            dict(event.to_primitive(), kind="game_event") for event in new_events
        )
        return rows

    def reset(self) -> None:
        # A reset is a new day AND a new run: close the old run's row first
        # (status "reset" -- its frames stay readable), then _build() opens
        # the next one. A day that already finished keeps "finished".
        self._persist_pending_events()
        if (
            self.run_store is not None
            and self._run_id is not None
            and not self._run_finished
        ):
            self.run_store.update_run(self._run_id, status="reset")
        self._build()

    def resume_run(self, run_id: str) -> None:
        """Swap the live day for a persisted run (#543); caller holds the app
        lock, like ``reset()``.

        Every guard runs BEFORE any teardown: a failure after the rebuild
        would leave ``_step_idx = 0`` against a non-empty frames file, and the
        next ``append_frame`` would raise and kill the run loop.
        """
        if self.run_store is None:
            raise ValueError("this server has no run store (--persist)")
        if run_id == self._run_id:
            raise ValueError(f"run {run_id} is already the live run")
        row = self._resumable_row(run_id)
        frames = self.run_store.read_frames(run_id)  # present + parseable, too
        # Close the current day exactly the way reset() does (a finished day
        # keeps "finished"), then rebuild adopting the persisted run. The
        # guards' row/frames ride along so the frames file -- thousands of
        # lines on a long day, all of this under the app lock -- is parsed
        # once, not twice.
        self._persist_pending_events()
        if self._run_id is not None and not self._run_finished:
            self.run_store.update_run(self._run_id, status="reset")
        self._build(resume_run_id=run_id, resume_row=row, resume_frames=frames)


class _GameProxy:
    """A stable façade over ``stepper.game`` for the API routes to close over.

    ``create_app(game)`` captures the game object once, but ``PennStepper.reset()``
    must rebuild a *fresh* world (see its docstring) -- so the routes are handed
    this proxy instead, and every attribute access resolves against whichever
    game the stepper currently owns. ``/world_state`` therefore serves the new
    day immediately after a reset."""

    def __init__(self, stepper):
        object.__setattr__(self, "_stepper", stepper)

    def __getattr__(self, name):
        return getattr(self._stepper.game, name)


def resolve_resume(run_store, resume):
    """Turn the ``--resume`` argument into a concrete run id (#543).

    ``--resume`` bare means "the newest run in the store"; with an id it
    passes through (existence is checked by the stepper's own guards, which
    produce the same error either way). Friendly ``SystemExit``s here -- these
    are CLI mistakes, not server faults.
    """
    if run_store is None:
        raise SystemExit("--resume requires --persist (there is no run store)")
    if resume == "last":
        runs = run_store.list_runs()  # newest first
        if not runs:
            raise SystemExit("nothing to resume: the store has no runs yet")
        return runs[0]["id"]
    return resume


def _decide_workers_arg(value):
    """argparse type for --decide-workers: 'auto' or a non-negative integer.

    Validated here so a typo gets a clean usage error instead of an uncaught
    ValueError traceback deep inside main().
    """
    if value == "auto":
        return value
    try:
        workers = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a non-negative integer or 'auto', got {value!r}"
        )
    if workers < 0:
        raise argparse.ArgumentTypeError("must be >= 0 (0 = serial)")
    return workers


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Serve the live Penn sim for the Godot viewer (#263)."
    )
    ap.add_argument(
        "--steps",
        type=int,
        default=DEFAULT_STEPS,
        help="length of the campus day; the loop pauses itself when it ends",
    )
    ap.add_argument(
        "--endless",
        action="store_true",
        help="never finish: keep ticking past --steps (agents idle at their "
        "last stop once their schedules run out)",
    )
    ap.add_argument(
        "--tick-seconds",
        type=float,
        default=0.1,
        help="wall-clock seconds per sim step; 0.1 matches the viewer's "
        "step_seconds default so live playback paces like a 1x replay",
    )
    ap.add_argument(
        "--stall-seconds",
        type=float,
        default=0.0,
        help="DEBUG: the mock brain never stalls, so every %d steps hold the "
        "step this many seconds to fake the decision-latency pauses a real LLM "
        "brain produces -- lets the viewer's 'thinking…' indicator (#372) be "
        "exercised for free (set >~2s to clear the viewer's stall threshold; 0 "
        "= off)" % STALL_EVERY_STEPS,
    )
    ap.add_argument(
        "--brain",
        choices=("mock", "llm"),
        default="mock",
        help="mock (default): the deterministic schedule brain -- offline, free, "
        "authored meeting dialogue on. llm: the model named by the world's "
        "llm: block (Anthropic Claude Haiku) makes every decide/converse/"
        "reflect call; needs ANTHROPIC_API_KEY and `uv sync --extra llm`",
    )
    ap.add_argument(
        "--model",
        default=None,
        help="override the llm: block's model for this run (--brain llm only)",
    )
    ap.add_argument(
        "--max-cost",
        type=float,
        default=None,
        help="override the llm: block's max_cost_usd kill-switch, in USD "
        "(--brain llm only); the day ends when cumulative spend reaches it",
    )
    ap.add_argument(
        "--persist",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="record this run durably (#304): frames to runs/<run_id>/frames.jsonl,"
        " agent memory + run metadata to runs/sim.db, under"
        " godot-generative-agents/runs/. POST /reset starts a new run id",
    )
    ap.add_argument(
        "--resume",
        nargs="?",
        const="last",
        default=None,
        metavar="RUN_ID",
        help="boot by picking a persisted run back up instead of opening a new "
        "one (#543): positions, schedules and agent memories come back from "
        "the store; transient world state starts fresh. Bare --resume means "
        "the newest run. Requires --persist",
    )
    ap.add_argument(
        "--cognition-tools",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="let each decide -- and each conversation line -- consult the "
        "agent's memory / world knowledge / day plan first (recall, "
        "query_knowledge, read_plan; issues #358/#512): up to 3 model "
        "requests per decide tick instead of 1, metered by --max-cost as "
        "usual. --brain llm only; the mock brain never reaches the tool loop",
    )
    ap.add_argument(
        "--decide-workers",
        type=_decide_workers_arg,
        default="auto",
        help="max concurrent agent decisions (#366): 0 = strictly serial "
        "(deterministic); N caps how many decides run at once (tune it "
        "under your provider's rate limit -- also at most one in-flight "
        "decision per persona). 'auto' (default) = one per persona under "
        "--brain llm, 0 under mock",
    )
    ap.add_argument(
        "--decide-timeout",
        type=float,
        default=30.0,
        help="wall-clock budget in seconds for one decision when decides run "
        "concurrently; past it the agent idles this tick and is re-asked "
        "once the in-flight call resolves (the skip is printed)",
    )
    ap.add_argument(
        "--mock-latency",
        type=float,
        default=0.0,
        help="sleep this many seconds inside every mock-brain decision -- an "
        "offline stand-in for real provider latency (pair with "
        "--decide-workers N to demo #366 pacing / #372 thinking stalls)",
    )
    ap.add_argument(
        "--start-paused",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="boot the loop paused so the day (and, under --brain llm, the "
        "first paid model call) waits for the viewer's Start button / POST "
        "/resume. Default: paused under --brain llm, auto-start under mock",
    )
    ap.add_argument(
        "--monitor",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="print one terminal line per LLM request (timestamp, actor, role, "
        "tokens, latency, cost); --no-monitor silences it",
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument(
        "--token",
        default=None,
        help="require 'Authorization: Bearer <token>' (defaults to the "
        "SIM_API_TOKEN env var; required for a non-loopback --host)",
    )
    args = ap.parse_args()

    # A repo-root .env (git-ignored; template at .env.example) can supply
    # ANTHROPIC_API_KEY / SIM_API_TOKEN without per-terminal exports;
    # already-exported environment variables always win (backend/env.py).
    if load_dotenv():
        print("Loaded .env from the repo root (already-exported variables win).")

    # Build the world once: resolve_llm reads its llm: block, the stepper
    # steps it (a second build would waste the map load and fork patch state).
    world = build_penn_world()
    llm = resolve_llm(world.llm, args.brain, model=args.model, max_cost=args.max_cost)
    # A paying brain shouldn't spend before anyone is watching: under --brain
    # llm the loop boots paused and the viewer's Start button (POST /resume)
    # opens the day. The free mock keeps auto-starting. --[no-]start-paused
    # overrides either way.
    start_paused = (
        args.start_paused if args.start_paused is not None else llm is not None
    )
    store = RunStore(DEFAULT_RUNS_DIR) if args.persist else None
    resume_id = resolve_resume(store, args.resume) if args.resume else None
    # 'auto' concurrency (#366): a real brain decides in parallel (LLM latency
    # is the whole point), the mock stays serial so the default offline run
    # remains deterministic. An explicit integer wins.
    if args.decide_workers == "auto":
        decide_workers = len(world.personas) if llm is not None else 0
    else:
        decide_workers = args.decide_workers
    if args.mock_latency > 0 and llm is not None:
        # latency_s is read only by the mock brain's _choose; under a real
        # brain the flag would be a silent no-op, so refuse it instead.
        raise SystemExit(
            "--mock-latency only affects the mock brain -- drop it, or use "
            "--brain mock (it exists to demo stalls without spending)."
        )
    try:
        stepper = PennStepper(
            num_steps=args.steps,
            endless=args.endless,
            world=world,
            monitor=LlmCallMonitor() if args.monitor else None,
            llm=llm,
            run_store=store,
            cognition_tools=args.cognition_tools,
            decide_workers=decide_workers,
            decide_timeout=args.decide_timeout,
            mock_latency=args.mock_latency,
            stall_seconds=args.stall_seconds,
            resume_run_id=resume_id,
        )
    except ImportError as e:
        raise SystemExit(f"{e}\n(--brain llm needs the LLM extra: uv sync --extra llm)")
    except (KeyError, ValueError) as e:
        # A bad --resume: unknown id, a different cast's or map's run, or a
        # corrupt frames file (JSONDecodeError is a ValueError). Only claim
        # "cannot resume" when a resume was actually asked for -- any other
        # KeyError/ValueError is a real fault and should traceback.
        if resume_id is None:
            raise
        raise SystemExit(f"cannot resume: {e}")
    wm = stepper.world.world_map
    print(
        f"Loaded the_upenn ({wm.width}x{wm.height}); "
        f"{len(stepper.order)} personas, {len(stepper.world.meetings)} authored "
        f"meetings. Stepping every {args.tick_seconds}s "
        f"({'endless' if args.endless else f'{args.steps}-step day'})."
    )
    if llm is not None:
        ceiling = llm.get("max_cost_usd")
        print(
            f"Brain: LIVE LLM -- anthropic/{llm['model']} makes every "
            "decide/converse/reflect call. "
            + (
                f"Cost ceiling ${ceiling:.2f} (the day ends at it)."
                if ceiling is not None
                else "NO cost ceiling -- set max_cost_usd in the llm: block "
                "or pass --max-cost."
            )
        )
        print("Authored meeting dialogue: OFF -- the cast speaks through the model.")
    else:
        print(
            "Brain: mock (deterministic, free; authored meeting dialogue ON). "
            "For the real thing: --brain llm."
        )
    if args.persist:
        if resume_id is not None:
            print(
                f"Persistence: ON -- RESUMED run {stepper.run_id} at step "
                f"{stepper.step}, recording to {stepper.run_store.root}."
            )
            if not args.endless and stepper.step >= args.steps:
                print(
                    f"  (already past --steps {args.steps} -- the day will "
                    "finish immediately; pass --endless or a larger --steps)"
                )
        else:
            print(
                f"Persistence: ON -- run {stepper.run_id} recording to "
                f"{stepper.run_store.root} (frames.jsonl + sim.db)."
            )
    if args.cognition_tools:
        print(
            "Cognition tools: ON -- a decide tick may spend up to 3 model "
            "requests (recall/query_knowledge/read_plan before acting)."
            if llm is not None
            else "Cognition tools: ON, but the mock brain never reaches the "
            "tool loop -- pair it with --brain llm for any effect."
        )
    if decide_workers > 0:
        print(
            f"Concurrent decides: ON (up to {decide_workers} at once, one "
            f"in-flight decision per agent), {args.decide_timeout:g}s budget "
            "each -- a decision tick costs the slowest decision, not the "
            "sum (#366)."
        )
    print(
        f"LLM request monitor: {'on' if args.monitor else 'off (--monitor to enable)'}"
    )
    if start_paused:
        print(
            "Start gate: the loop boots PAUSED — press ▶ Start in the viewer "
            "(or POST /resume) to begin the day."
        )
    print(
        f"Live surface: GET /live, GET /events?since=0, ws://{args.host}:{args.port}/ws, "
        "POST /pause|/resume|/reset|/shutdown, GET /usage  (OpenAPI at /docs)"
    )
    run(
        _GameProxy(stepper),
        host=args.host,
        port=args.port,
        auth_token=args.token,
        stepper=stepper,
        tick_seconds=args.tick_seconds,
        start_paused=start_paused,
        # This server's lifecycle follows the viewer: closing the Godot window
        # POSTs /shutdown, so a paying sim never keeps running unwatched.
        allow_shutdown=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
