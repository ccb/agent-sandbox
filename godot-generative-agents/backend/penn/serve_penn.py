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
import datetime
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace

from backend.api import run
from backend.build_world import library_personas
from backend.contract import SCHEMA_VERSION
from backend.env import load_dotenv
from backend.llm_monitor import LlmCallMonitor, RoleTaggedLedger
from backend.run_simulation import step
from backend.run_store import DEFAULT_RUNS_DIR, RunStore
from backend.sim_clock import SimClock
from backend.sim_config import CognitionConfig, SimulationConfig
from backend.cognition import attach_agents
from scripted_brain import build_scripted_brains
from penn_world import (
    DIALOGUE_FADE_STEPS,
    DIALOGUE_LINE_STEPS,
    PENN_ACTION_VERBS,
    SEC_PER_STEP,
    SIM_START,
    WORLD_DATA_BOIL,
    WORLD_DATA_BOIL_HARD,
    PennWorld,
    build_penn_world,
    persona_meta_entry,
    relocate_stove_to_kitchen,
    replay_frame_entry,
)
from text_adventure_games.llm_client import LlmConfig, create_llm_client
from text_adventure_games.recording import (
    CassetteMiss,
    CassetteWriter,
    RecordingClient,
    ReplayClient,
    seed_world,
)
from text_adventure_games.transcript import RunRecord, file_sha256, git_sha
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

# Call-site roles the tiering map may key (issue #368) -- exactly the roles
# the call sites stamp into client.context (backend/cognition.py,
# run_simulation.py) plus the two fixed-role clients built in _build.
TIER_ROLES = frozenset(
    {"decide", "plan", "reflect", "converse", "outcome", "score", "react"}
)

# Mid-run brain-outage threshold (#745): after this many CONSECUTIVE failed
# real-brain calls (error rows in the ledger with no genuine answer between
# them), the next tick() raises BrainOutage instead of burning more paid,
# failing round-trips. backend.live's #637 tick-error handler turns the raise
# into a visible pause + status(reason="error") record; POST /resume retries
# with a fresh window. Low enough that a dead key (every agent fails its first
# decide) trips within a tick or two; high enough that a single transient
# failure -- already retried by the client's own #260 budget -- rides through.
BRAIN_OUTAGE_PAUSE_STREAK = 3


class BrainOutage(RuntimeError):
    """The live brain is erroring on every call (#745): raised by
    ``PennStepper.tick()`` once ``BRAIN_OUTAGE_PAUSE_STREAK`` consecutive
    real-brain calls have failed, so the #637 error path pauses the run
    visibly instead of the cast freezing silently at $0."""


def _parse_model_for(pairs):
    """``["plan=claude-sonnet-4-6", ...]`` -> ``{"plan": "claude-sonnet-4-6"}``.
    Role validity is checked in resolve_llm (one place for YAML + CLI)."""
    out = {}
    for pair in pairs or []:
        role, sep, model = pair.partition("=")
        if not sep or not role.strip() or not model.strip():
            raise SystemExit(f"--model-for expects ROLE=MODEL, got {pair!r}")
        out[role.strip()] = model.strip()
    return out


# The scripted full-feature mock brain (#563): a deterministic, key-free brain
# that -- unlike the schedule mock -- is a DISTINCT client object, so it opens
# the llm_client-gated paths (tool loop, cognition tools, conversation,
# reflection) offline. resolve_llm returns this sentinel; it is not a paid run.
SCRIPTED = "scripted"

# The world-factory registry (#568): a world name -> a zero-arg builder that
# returns a FRESH PennWorld. build_penn_world already hands back a fresh world
# (fresh WorldMap + patch state) on every call, which is what a per-run build
# needs. Penn is the first (and today only) entry; a second world is one line.
WORLD_BUILDERS = {"penn": build_penn_world}


def _build_boil_hard_world(cast: list[str] | None = None) -> PennWorld:
    """A fresh #728 boil_hard world: the boil world plus its `Kitchen` location,
    with the stove relocated there at build time (`penn_world.
    relocate_stove_to_kitchen`) -- the murky pot stays visible from step 0, the
    boil Recipe's tool is a real 297-tick Travel away. Wraps build_world_fn
    rather than patching one game post-hoc so every rebuild -- including a POST
    /reset's -- carries the relocation."""
    pw = build_penn_world(world_data=WORLD_DATA_BOIL_HARD, cast=cast)
    inner = pw.build_world_fn

    def _relocated(world_map):
        game, chars = inner(world_map)
        relocate_stove_to_kitchen(game)
        return game, chars

    return replace(pw, build_world_fn=_relocated)


# Named scenarios (#592/#728): which world this server steps, using the same
# names as the bake's `generate_penn_replay.py --scenario`. Each entry is a
# zero-arg builder returning a FRESH PennWorld (the stepper rebuilds through it,
# so the scenario survives POST /reset) plus the perception radius the scenario
# pins (None = the config/default radius). boil_hard pins vision_r=0: its stove
# lives in a separate Kitchen and must not leak into observations via
# cross-location perception (#82) -- the only lead the agent gets is "Kitchen"
# in Travel's destination enum (#635).
SCENARIOS = {
    "penn": {"world": build_penn_world, "vision_r": None},
    "boil": {
        "world": lambda cast=None: build_penn_world(
            world_data=WORLD_DATA_BOIL, cast=cast
        ),
        "vision_r": None,
    },
    "boil_hard": {"world": _build_boil_hard_world, "vision_r": 0},
}


def _is_paid(llm) -> bool:
    """True only for a real, paying LLM config (a dict). None (mock) and the
    SCRIPTED sentinel are free."""
    return isinstance(llm, dict)


def _resolve_cognition_tools(flag: bool, sim_config, llm) -> bool:
    """OR-resolution for cognition tools (#358/#512/#564): a CLI flag, either
    config surface -- the sim-level ``cognition.cognition_tools`` or the
    engine's own ``game.agent.cognition_tools`` (#564 review finding 4: the
    same knob a plain ``GameConfig`` honors, silently dead here until this
    was added) -- or the scripted brain (#563) can each switch it on; none
    can veto another. Shared by ``__init__`` and the resume path (finding 1),
    so a resumed run's adopted config re-derives the identical value."""
    return bool(
        flag
        or (sim_config is not None and sim_config.cognition.cognition_tools)
        or (sim_config is not None and sim_config.game.agent.cognition_tools)
        or (llm == SCRIPTED)
    )


def _resolve_react(flag: bool, sim_config) -> bool:
    """OR-resolution for the react gate (#370/#564): a CLI flag or the
    config's ``cognition.react_enabled`` can each switch it on. Shared by
    ``__init__`` and the resume path (finding 1)."""
    return bool(flag or (sim_config is not None and sim_config.cognition.react_enabled))


def _resolve_plan_mode(flag: str, llm) -> str:
    """Resolve ``--plan``'s ``"auto"`` default (#787): the model plans its own
    day whenever the model is the one living it.

    ``auto`` -> ``"llm"`` under a paying brain, ``"schedule"`` otherwise. The
    point of a live run is model cognition, and the day -- what an agent does
    with its hours -- is the most consequential thing there is to decide; with
    ``schedule`` the day stays hand-authored and *unrevisable* (``MockPlanner``
    has a no-op ``revise``, so the whole ``deviation -> revise`` path, #778, is
    dead on the default live path). ``schedule`` stays an explicit opt-out: the
    YAML days have hand-tuned overlaps so agents converge for the scripted
    rendezvous, which a free-play generated day does not guarantee.

    Free brains resolve to ``schedule`` and are untouched -- the mock (None) and
    the scripted sentinel have no client to plan with, so the bake and every
    offline replay stay byte-identical. Explicit values pass straight through,
    which is what keeps the ``--plan llm`` + free-brain combination an error
    (the caller's own guard) rather than a silent downgrade.
    """
    if flag != "auto":
        return flag
    return "llm" if _is_paid(llm) else "schedule"


def resolve_llm(world_llm, brain, model=None, max_cost=None, model_for=None):
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

    The daily planner is a *separate* switch (``--plan``, #397) that this
    resolution only *feeds*: its ``auto`` default reads the brain resolved here
    and picks the model planner for a paying run (#787, see
    ``_resolve_plan_mode``). ``--plan schedule`` keeps the authored YAML day and
    its hand-tuned meeting overlaps; ``--plan llm`` lets the model author the
    day, which is free-play (the scripted rendezvous may not converge).
    ``--brain llm`` here still only decides whether decide/converse/reflect are
    the model's.
    """
    if brain == "scripted":
        return SCRIPTED
    if brain != "llm":
        return None
    llm = dict(world_llm or {})
    if model is not None:
        llm["model"] = model
    if max_cost is not None:
        llm["max_cost_usd"] = max_cost
    # Per-role model tiering (#368): the YAML llm.models map, with --model-for
    # entries layered on top. Validated here so a typo'd role dies at startup
    # (for both config surfaces), not silently pays the default model.
    models = dict(llm.get("models") or {})
    if model_for:
        models.update(model_for)
    unknown = sorted(set(models) - TIER_ROLES)
    if unknown:
        raise SystemExit(
            f"unknown tiering role(s) {', '.join(unknown)}: valid roles are "
            f"{', '.join(sorted(TIER_ROLES))}"
        )
    if models:
        llm["models"] = models
    else:
        llm.pop("models", None)
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


def check_anthropic_key(urlopen=urllib.request.urlopen, timeout=10.0):
    """Fail fast on a key the API rejects, before serving an all-day sim.

    ``resolve_llm`` proves ``ANTHROPIC_API_KEY`` is *present*; this proves it
    *works*, with one models-list request (free -- no tokens are billed). The
    check matters because past boot a bad key is invisible by design: every
    decide's API error degrades to an idle tick (the brain-outage contract),
    so the whole cast just sits frozen on "waking up" at $0 spend with nothing
    in the terminal. A 401/403 therefore exits with the fix; any *other*
    failure (no network, a 5xx) warns and continues -- transient trouble is
    the run's own retry path's job, not a boot blocker.
    """
    request = urllib.request.Request("https://api.anthropic.com/v1/models?limit=1")
    request.add_header("x-api-key", os.environ["ANTHROPIC_API_KEY"])
    request.add_header("anthropic-version", "2023-06-01")
    try:
        urlopen(request, timeout=timeout).close()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SystemExit(
                f"ANTHROPIC_API_KEY was rejected by the API (HTTP {e.code}): "
                "the key is present but not valid. Fix the export in this "
                "terminal (or the repo-root .env; template: .env.example), "
                "then restart. Without this check, every model call would "
                "fail silently and the cast would sit on 'waking up' forever."
            )
        print(
            f"WARNING: could not verify ANTHROPIC_API_KEY (HTTP {e.code}); continuing."
        )
    except OSError as e:
        # URLError (DNS, refused, timeout) is an OSError subclass.
        print(f"WARNING: could not verify ANTHROPIC_API_KEY ({e}); continuing.")
    else:
        print("ANTHROPIC_API_KEY verified with the API (one free models-list request).")


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
        react=False,
        decide_workers=0,
        decide_timeout=30.0,
        mock_latency=0.0,
        stall_seconds=0.0,
        plan_mode="auto",
        resume_run_id=None,
        seed=0,
        replay_cassette=None,
        sim_config=None,
        world_builder=None,
        vision_r=None,
        scenario="penn",
    ):
        # What a rebuild without an explicit world (reset()) constructs from:
        # the launch scenario's builder (#728), defaulting to the full campus --
        # without this a boil_hard server's POST /reset would silently swap the
        # scenario back to the default world.
        self._world_builder = (
            world_builder if world_builder is not None else build_penn_world
        )
        # The scenario NAME behind that builder (#747), recorded into the run
        # manifest so --re-run rebuilds the same world instead of the default
        # campus. (If #730/#732's config-in-manifest work settles a fuller
        # config block, this field's long-term home is there.)
        self.scenario = scenario
        # The configured cast (#732): persona ids applied by apply_config, or
        # None for the world YAML's own cast. Held here so reset()'s default
        # rebuild keeps the configured cast instead of silently reverting.
        self._cast: list[str] | None = None
        # The scenario's pinned perception radius (#728), or None for the
        # config/default value; applied in _build after the config-derived cog.
        self.vision_r = vision_r
        self.num_steps = num_steps
        # The launch-configured budget, kept so a per-request create_run(steps=)
        # override stays one-shot: reset()/resume_run() restore this instead of
        # inheriting a prior create_run's reduced num_steps (which used to leak).
        self._launch_num_steps = num_steps
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
        # The scripted brain (#563) is a SINGLE shared object whose decision reads
        # context["actor"] (stamped per decide); a concurrent fan-out would race
        # that field across threads and consult the wrong persona's schedule. So
        # scripted decides serially only -- reject an explicit --decide-workers > 0
        # rather than silently desync (--brain llm gives every agent its own
        # client and is the way to parallelize; --decide-workers auto already
        # maps scripted -> 0).
        if llm == SCRIPTED and decide_workers > 0:
            raise SystemExit(
                "--brain scripted decides serially (one shared deterministic "
                "brain) and has no --decide-workers > 0 mode. Drop --decide-workers "
                "(auto already uses 0 for scripted), or use --brain llm to "
                "parallelize."
            )
        self._decide_executor = (
            _DecideThreads(decide_workers) if decide_workers > 0 else None
        )
        # How many agents were at a decision point in the last tick() -- the
        # live loop stamps it onto each frame record (live.py) so a viewer can
        # tell "thinking" from "frozen" (#372).
        self.last_deciders = None
        # Per-agent decision lifecycle records for the live feed (#551), buffered
        # here and drained each tick by backend.live. Only populated under a
        # real/scripted brain (see the tick() gate); the pure mock never fills it,
        # so its feed stays byte-identical. _deciding_started holds per-agent
        # begin timestamps to compute elapsed_ms on end. Both are guarded by
        # _deciding_lock: _deciding_sink may run on a #366 decide worker thread
        # while drain_deciding swaps the buffer on the tick thread (#598 review).
        # The lock lives here (not _build) so it survives resets, like the ledger.
        self._deciding_buf: list = []
        self._deciding_started: dict = {}
        self._deciding_lock = threading.Lock()
        # Out-of-band `begin` publish (#605): api.create_app injects a callable
        # that appends straight onto the live EventLog, so a viewer's thinking
        # bubble lights the moment a decide starts -- mid-tick -- rather than
        # at the boundary drain (which, for a within-tick decide, delivered
        # begin+end together and never lit it). Lives here (not _build) so the
        # wiring survives resets, like the lock.
        self._deciding_publish = None
        # DEBUG (#372): hold every STALL_EVERY_STEPS-th step this long to fake a
        # real brain's decision latency so the viewer's "thinking…" cue can be
        # exercised under the free mock brain. 0.0 = off (byte-identical timing).
        self.stall_seconds = stall_seconds
        # Wish feed lock (#622): guards the two buffers `_on_wish` fills (see
        # _build()). One lock, created once here (not per _build/reset), like
        # the #551 deciding buffer's discipline -- a wish is logged from the
        # same thread that resolves that tick's commands, so a plain list
        # append would likely be safe on its own, but the lock keeps the seam
        # correct even if a future path logs one from another thread.
        self._wish_lock = threading.Lock()
        # The #304 persistence seam: a backend.run_store.RunStore, or None (the
        # default -- nothing is written, byte-identical to before). Set before
        # the _build() below so every build, first boot and each POST /reset,
        # opens its own run in the store.
        if resume_run_id is not None and run_store is None:
            raise ValueError("resuming a run needs a run store (--persist)")
        self.run_store = run_store
        self.seed = seed
        self._engine_sha = git_sha()  # provenance snapshot, captured once
        self._replay_cassette = replay_cassette
        self._cassette_writer = None
        self._cassette_path = None
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
        # The #564 config seam: a SimulationConfig loaded from --config, or
        # None (all defaults -- byte-identical to before by construction).
        # Held on the stepper, like cognition_tools below, so _build()
        # re-applies it on every reset (POST /reset).
        self.sim_config = sim_config
        # Memory-retrieval scoring for every live decide (#564): step() has
        # threaded a retrieval= into observe_and_decide since #296; tick()
        # passes this one. None -> the engine's default scoring, unchanged.
        self.retrieval = sim_config.retrieval if sim_config is not None else None
        # Raw CLI flags, kept (not just folded into the resolved booleans
        # below) so a resumed run's adopted manifest config (#564 review
        # finding 1, see _build's resume-adopt block) can re-run the same
        # OR-resolution without losing the "the flag always wins" coupling.
        self._cognition_tools_flag = cognition_tools
        self._react_flag = react
        self.cognition_tools = _resolve_cognition_tools(
            cognition_tools, sim_config, llm
        )
        # React-or-continue (#370): perception-driven interruption while
        # walking. Held on the stepper so _build() re-applies it on every
        # reset. Mock-inert: under the mock brain the react pass never runs
        # at all (step() gates it on conversation_enabled), so it is safe to
        # leave on for mechanics demos.
        self.react = _resolve_react(react, sim_config)
        # Daily planning source (#397): "schedule" keeps the authored YAML day
        # -- byte-identical, meeting overlaps intact. "llm" lets the model
        # author each day (LLMPlanner); free-play, so the hand-tuned rendezvous
        # windows are no longer guaranteed. "auto" (the default since #787)
        # picks llm under a paying brain and schedule otherwise -- see
        # _resolve_plan_mode. Kept raw alongside the resolved value, like the
        # cognition/react flags above, so apply_config can re-resolve it
        # against a brain the config session swaps in.
        self._plan_mode_flag = plan_mode
        self.plan_mode = _resolve_plan_mode(plan_mode, llm)
        # Filled by every _build() from attach_agents; empty until the first
        # one, which is when the boot run's manifest is first written.
        self._planner_sources: dict = {}
        # The planner shares the run's paid Anthropic client, so llm planning
        # needs --brain llm -- the free mock (None) and scripted (SCRIPTED)
        # brains have no such client, so _is_paid gates both out (the scripted
        # sentinel is truthy, so a plain `llm is None` check would let --brain
        # scripted through and then crash on the unset _llm_config below).
        # Only an EXPLICIT --plan llm can trip this: auto never resolves to llm
        # on a free brain. A re-run is the third exception -- its brain is the
        # cassette (llm is None, so never "paid"), and the recorded plan calls
        # replay from it like every other call (#787).
        if (
            self.plan_mode == "llm"
            and not _is_paid(llm)
            and self._replay_cassette is None
        ):
            raise SystemExit(
                "--plan llm needs --brain llm (the planner shares its client)."
            )
        # Resolved LLM settings (resolve_llm), or None for the mock brain. The
        # ledger's cost ceiling comes from the same block, so GET /usage
        # reports the budget and tick() can end the day at it. The ledger and
        # monitor live HERE, not in _init_brain: they survive resets AND brain
        # swaps (create_app captures `ledger` once at boot, and money spent
        # stays spent).
        self.ledger = UsageLedger(  # backs GET /usage across resets
            max_cost_usd=(llm if _is_paid(llm) else {}).get("max_cost_usd")
        )
        # The terminal request monitor (backend.llm_monitor), or None for quiet.
        # Like the ledger it lives here, not in _build(), so its call counter
        # survives resets.
        self.monitor = monitor
        # Mid-run brain health (#745). _llm_failures_seen is a cursor into
        # ledger.records (the _events_seen idiom) -- it lives here because the
        # ledger it indexes survives resets. The streak counts consecutive
        # failed real-brain calls (a genuine answer resets it; _build resets
        # it too -- a new day gets a fresh window); tick() raises BrainOutage
        # at BRAIN_OUTAGE_PAUSE_STREAK. _llm_error_buf holds the per-failure
        # feed rows drain_events publishes (kind "llm_error").
        self._llm_failures_seen = 0
        self._brain_error_streak = 0
        self._last_brain_error = None
        self._llm_error_buf: list = []
        # What POST /config applied, or None for an unconfigured server; when
        # set, _store_manifest records it as the manifest's `config` block (#732).
        self._applied_config = None
        self._init_brain(llm)
        self._build(world, resume_run_id=resume_run_id)

    def _init_brain(self, llm) -> None:
        """Construct the brain clients for *llm* -- None (mock), SCRIPTED, or a
        paid dict. Extracted from __init__ (#732) so apply_config can swap the
        brain at apply time by re-running it; the ledger/monitor deliberately
        stay in __init__ (they must survive brain swaps -- create_app captures
        the ledger object once at boot). Clears the per-agent client pool: a
        new brain's clients must not reuse the old model's.
        """
        self.llm = llm
        # The real-brain clients (issue #261): one shared by decide + converse,
        # one for reflection -- separate instances so the request monitor can
        # tag each role exactly, all recording into self.ledger. Built once
        # here (they are stateless apart from ledger/context) and re-wired onto
        # fresh agents by every _build().
        self.llm_client = None
        self.reflector_client = None
        # The planner client (#397): a separate instance so the request monitor
        # tags `plan` calls exactly; built only in --plan llm mode (which the
        # guard above restricts to the paid --brain llm branch, else None ->
        # attach_agents uses MockPlanner, byte-identical).
        self.planner_client = None
        if self._replay_cassette is not None:
            # Re-run mode (#715): serve every model call from the recorded
            # cassette -- no key, no network. ONE shared instance across
            # decide/converse/reflect: request keys differ by role/messages, so
            # their FIFO queues never interleave. `llm` here is always None
            # (reproduce_run never passes SCRIPTED or a paid dict -- the
            # recorded cognition_tools/react/plan_mode are reconstructed
            # explicitly from the manifest instead), so _is_paid stays False
            # (no per-agent clients, sequential decide).
            replay = ReplayClient(self._replay_cassette, strict=True)
            self.llm_client = replay
            self.reflector_client = replay
            if self.plan_mode == "llm":
                # ...and the planner too (#787). The recording seam already
                # wraps the planner client in the run's OWN RecordingClient
                # (see _build), so a model-authored day is in the cassette
                # like every other call; without replaying it here the re-run
                # would fall back to MockPlanner and diverge on step 1. The
                # planner's prompts are built from persona + t=0 memory + the
                # clock window, all reproduced by the seed, so the request
                # keys line up. This is the whole reason --plan llm can be
                # the live default (#787) without undoing #715.
                self.planner_client = replay
        elif llm == SCRIPTED:
            # Free, key-free full-feature brain (#563): distinct client objects,
            # so the llm_client-gated paths open. Record each role through the
            # same _recording_ledger view the paid path uses, so --monitor tags
            # decide/converse vs reflect request lines (GET /usage still sums the
            # base ledger). Bind the decide view to the brain's context so the
            # monitor's per-call actor/role stamps read live -- mirrors
            # _decide_client().
            decide_view = self._recording_ledger("decide")
            self.llm_client, self.reflector_client = build_scripted_brains(
                decide_ledger=decide_view,
                reflect_ledger=self._recording_ledger("reflect"),
            )
            ctx = getattr(self.llm_client, "context", None)
            if isinstance(decide_view, RoleTaggedLedger) and ctx is not None:
                decide_view.bind_context(ctx)
        elif llm is not None:
            self._llm_config = LlmConfig(
                provider="anthropic",
                model=llm.get("model"),
                models_by_role=llm.get("models"),
            )
            self.llm_client = self._decide_client()
            self.reflector_client = self._role_client("reflect")
            if self.plan_mode == "llm":
                self.planner_client = self._role_client("plan")
        # Per-agent decide clients (#366): created once per persona on first
        # _build and RE-WIRED (not rebuilt) by later resets -- each SDK client
        # owns a real connection pool, so rebuilding N of them per POST /reset
        # would orphan the old pools.
        self._agent_clients = {}
        # Raw (unwrapped) real clients, stashed once (#715): the recording hook
        # in _build() re-wraps FROM these on every build instead of wrapping
        # self.llm_client/reflector_client/planner_client in place -- those
        # attributes hold last build's RecordingClient after the first build,
        # and re-wrapping THAT would nest a new RecordingClient around a
        # client whose writer a reset just closed, crashing the next call.
        self._raw_llm_client = self.llm_client
        self._raw_reflector_client = self.reflector_client
        self._raw_planner_client = self.planner_client

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

    def _role_client(self, role):
        """A dedicated client for one fixed call site (reflect/plan). Unlike
        the decide-family sites, these call sites never stamp context
        themselves, so stamp the role once here: the one key both labels the
        ledger records (by_role, #368) and routes the call to the tiering
        map's model for that role."""
        client = create_llm_client(
            self._llm_config, ledger=self._recording_ledger(role)
        )
        ctx = getattr(client, "context", None)
        if ctx is not None:
            ctx["role"] = role
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
        # Pin the engine RNG so this build + its ticks are reproducible (#715).
        # Runs every _build so a reset re-seeds from the same base; a straight
        # start-to-finish run seeds once, which is what a re-run reproduces.
        seed_world(self.seed)
        # Mirror simulate()'s pre-loop setup exactly (run_simulation.py; the
        # same reconstruction tests/test_penn_live.py::
        # test_stepper_matches_simulate_prefix pins). If simulate's setup ever
        # drifts from this, the equivalence test fails -- on purpose.
        if world is not None:
            self.world = world
        elif self._cast is not None:
            self.world = self._world_builder(cast=self._cast)
        else:
            # Zero-arg call kept for test doubles that don't accept cast=.
            self.world = self._world_builder()
        # Resume semantics (#564 review finding 1): a resumed run's OWN
        # recorded sim_config wins over whatever this server booted with
        # (its own --config, or None) -- otherwise the world silently
        # continues under different knobs and a later --re-run of the SAME
        # run reports DIVERGED (--re-run reconstructs the manifest's config;
        # a mismatched resume would not have). Peeked here, before base_cog/
        # attach_agents below derive from self.sim_config, from whichever row
        # the caller already fetched (resume_run's guard-before-teardown
        # read) or a fresh lookup on the boot --resume path -- either way the
        # authoritative cast/map validation still happens once, unchanged,
        # in _adopt_run's _resumable_row call at the end of this method; a
        # bad run id/cast/map simply raises there and this speculative
        # adoption is moot (the whole _build() call -- and the stepper
        # construction -- aborts with it). Pre-#564 manifests (no sim_config
        # key) leave this server's own config untouched, exactly like today.
        if resume_run_id is not None:
            peek_row = (
                resume_row
                if resume_row is not None
                else self.run_store.get_run(resume_run_id)
            )
            recorded = (
                _sim_config_from_manifest(peek_row["manifest"])
                if peek_row is not None
                else None
            )
            if recorded is not None:
                if self.sim_config is not None:
                    print(
                        f"  - NOTE: resuming {resume_run_id} adopts its recorded "
                        "sim_config -- this server's own --config is ignored "
                        "for this run."
                    )
                self.sim_config = recorded
                self.retrieval = recorded.retrieval
                self.cognition_tools = _resolve_cognition_tools(
                    self._cognition_tools_flag, recorded, self.llm
                )
                self.react = _resolve_react(self._react_flag, recorded)
        # Cognition knobs (#564): start from the --config file's section (or
        # today's defaults with no config) and stamp on the RESOLVED booleans
        # from __init__ -- so the flag couplings hold and a reset re-derives
        # the same values.
        base_cog = (
            self.sim_config.cognition
            if self.sim_config is not None
            else CognitionConfig()
        )
        self.cog = replace(
            base_cog,
            cognition_tools=self.cognition_tools,
            react_enabled=self.react,
        )
        # The scenario's pinned perception radius (#728): boil_hard serves with
        # vision_r=0 so its relocated stove can't leak into observations via
        # cross-location perception (#82). Applied over the config-derived base
        # so neither a --config file nor a resumed run's adopted sim_config can
        # quietly re-widen it.
        if self.vision_r is not None:
            self.cog = replace(self.cog, vision_r=self.vision_r)
        # The live analogue of the bake's meta start/sec_per_step (#580): one
        # SimClock so the decide-context block and the hourly BEHIND_SCHEDULE
        # revision seam see the same in-game time the viewer's navbar shows.
        # Mock-safe: the mock brain reads only the observation's first line,
        # and MockPlanner.revise is a no-op.
        self.clock = SimClock(
            datetime.datetime.fromisoformat(SIM_START), sec_per_step=SEC_PER_STEP
        )
        self.game, self.chars = self.world.build_world_fn(self.world.world_map)
        # Per-run ledger baseline (#526): the ledger itself survives resets
        # on purpose (the cost ceiling is lifetime -- money spent stays
        # spent), so the per-run view SUBTRACTS this snapshot instead of
        # rebasing anything. Same boundary as the store's run id below.
        #
        # Taken HERE, ahead of both create_run and attach_agents, and not at
        # the end of _build (#782): under --plan llm the LLMPlanner authors
        # every agent's day inside attach_agents, so ~3 calls/agent are spent
        # before the first tick. Snapshotting after that attach folded the
        # planning spend into the BASELINE, and _run_cost_usd() -- the sum
        # both the run's row and GET /usage serve -- subtracted it straight
        # back out: a model-planned run under-reported by 29% in the #760
        # live batch, while its schedule-planned siblings matched to the
        # cent. Those calls are the run's in every other sense (the planner
        # client is wrapped in THIS run's RecordingClient just below, so they
        # land in its cassette), so the call-count base moves with the cost
        # base and the run's log counts them too. Nothing between here and
        # the old position spends: the seam below only opens files, and the
        # per-agent client loop only constructs clients.
        self._run_ledger_calls_base = len(self.ledger.records)
        self._run_ledger_cost_base = self.ledger.total_cost_usd()
        # Recording seam (#715): open this run and wrap every real client in a
        # RecordingClient BEFORE attach_agents wires them onto agents, so the
        # agents' decide/converse (agent.llm_client) and reflection
        # (agent.reflector = LLMReflector(reflector_client)) both flow through
        # the cassette without any post-hoc re-pointing. Skipped for: replay
        # (re-run mode records nothing), resume (a resumed run keeps its own
        # cassette), and the mock brain (self.llm_client is None -> no funnel
        # traffic to capture; the run is deterministic by construction anyway).
        # Wraps the RAW clients stashed in __init__, not self.llm_client/
        # reflector_client/planner_client themselves -- those hold the PRIOR
        # build's RecordingClient after the first build, and re-wrapping that
        # would nest a new RecordingClient around a client whose cassette a
        # reset just closed (every real _build() -- reset()/create_run() --
        # would re-enter this block, since only resume_run_id skips it).
        # A skipped build (resume, replay, or no run store) must not leave the
        # primary clients as a prior build's RecordingClient wrapping a cassette
        # that _close_current_run() already closed. Reset to the raw clients
        # first; the hook below re-wraps from raw only when recording. (The
        # per-agent clients already re-derive from raw each build.)
        self.llm_client = self._raw_llm_client
        self.reflector_client = self._raw_reflector_client
        self.planner_client = self._raw_planner_client
        if (
            self.run_store is not None
            and resume_run_id is None
            and self._replay_cassette is None
            and self._raw_llm_client is not None
        ):
            self._run_id = self.run_store.create_run(self._store_manifest())
            self._cassette_path = str(
                self.run_store.root / self._run_id / "cassette.jsonl"
            )
            self._cassette_writer = CassetteWriter(self._cassette_path)
            self.llm_client = RecordingClient(
                self._raw_llm_client, writer=self._cassette_writer
            )
            self.reflector_client = RecordingClient(
                self._raw_reflector_client, writer=self._cassette_writer
            )
            if self._raw_planner_client is not None:
                self.planner_client = RecordingClient(
                    self._raw_planner_client, writer=self._cassette_writer
                )
        # How much of game.events drain_events() has already published
        # (#467). Lives in _build so reset() restarts it with the new game.
        self._events_seen = 0
        # ...and how much the #307 persistence hook has flushed to the store.
        # Its own cursor: --persist must never steal rows from the feed above.
        self._persist_events_seen = 0
        # Malformed events this run dropped rather than persisted (#637): 0 on
        # a healthy day, surfaced so a lossy artifact is at least visible.
        self._dropped_events = 0
        # Wish feed (#622): install the engine's streaming tap on the FRESH
        # game object every _build() makes (a reset gets a new Game, so the
        # hook must be re-installed each time, like _events_seen above). Two
        # independent buffers -- one for the live feed, one for persistence --
        # both filled by the same _on_wish call, so draining one can never
        # starve the other (mirrors game.events' dual-cursor design, but
        # push- rather than pull-based per the engine's on_wish tap). Both are
        # empty for the whole run under the mock brain BY CONSTRUCTION: it
        # never proposes and its authored commands always parse, so
        # game.log_wish is simply never called (contrast #551's `deciding`
        # sink, which needs an explicit llm_client-is-not-None gate because
        # every decide, mock included, passes through it).
        self.game.on_wish = self._on_wish
        self._wish_feed_buf: list = []
        self._wish_persist_buf: list = []
        # Malformed wishes this run dropped rather than persisted (#637-style
        # tolerance, mirrors _dropped_events).
        self._dropped_wishes = 0
        # Every client records into self.ledger; with a monitor, through a
        # write-through view that also prints one terminal line per call (the
        # base ledger stays the single source GET /usage sums). Under the mock
        # brain the schedule clients this ledger feeds ARE the brains; under a
        # real brain they only pace the day and never call a model.
        # Where each agent's day came from, for a one-line boot summary below.
        planner_sources: dict = {}
        attach_agents(
            self.chars,
            self.world.personas,
            ledger=self._recording_ledger("decide"),
            vision_r=self.cog.vision_r,
            cognition_tools=self.cog.cognition_tools,
            # Sampling temperature + reflection trigger from the --config file
            # (#564); None -> LLMAgent's own defaults, unchanged.
            temperature=(
                self.sim_config.game.agent.temperature
                if self.sim_config is not None
                else None
            ),
            reflection_threshold=(
                self.sim_config.game.agent.reflection_threshold
                if self.sim_config is not None
                else None
            ),
            num_steps=self.num_steps,
            # The #261 swap: with a real client every agent's decide (and its
            # conversation lines) go through the model, and reflection passes
            # run when enough importance accrues. With None (mock mode) both
            # fall back exactly as before.
            llm_client=self.llm_client,
            reflector_client=self.reflector_client,
            # Daily planning (#397): a real client only under --plan llm (else
            # None -> MockPlanner, byte-identical). The planner validates its
            # stops against the world's full location set and bounds the day to
            # the run's clock window; both are inert for the mock planner.
            # Note: these ~3 planning calls/agent fire here at attach time,
            # before the first tick()'s over_budget() gate -- a one-time 3N
            # spend that can precede (not skip) the budget ceiling; the next
            # tick catches it.
            planner_client=self.planner_client,
            location_names=frozenset(loc["name"] for loc in self.world.locations),
            clock=self.clock,
            out_planner_sources=planner_sources,
            extra_action_names=PENN_ACTION_VERBS,
        )
        # Where each agent's day actually came from (#787): "llm" only if the
        # model produced usable stops -- a hallucinated place fails
        # validate_stops and the agent silently falls back to "static", the
        # authored YAML. Persisted on the manifest so a saved run records
        # whether it really got model-authored days, rather than only the
        # plan_mode that was ASKED for.
        self._planner_sources = planner_sources
        if self.run_store is not None and self._run_id is not None:
            # The row was opened above (create_run) so the cassette writer
            # existed before attach; re-stamp its manifest now that the answer
            # is known. Cheap and unconditional: schedule-planned runs record
            # an all-"static" map, which is exactly as informative.
            self.run_store.update_run(self._run_id, manifest=self._store_manifest())
        if self.planner_client is not None:
            authored = sum(1 for s in planner_sources.values() if s == "llm")
            print(
                f"  - PLAN: {authored}/{len(planner_sources)} agents on a "
                "model-authored day (#397); the rest fell back to the schedule"
            )
        # In-flight decisions from earlier ticks ({name: Future}, #366). Fresh
        # per build: a straggler still running across a reset references the
        # OLD world -- harmless, because parked results are always discarded.
        self._decide_pending = {}
        self._deciding_buf = []
        self._deciding_started = {}
        # A rebuild gets a fresh brain-outage window (#745): a reset/config
        # apply must never inherit a tripped streak (a brain swapped to the
        # free mock would otherwise raise on its first tick). The ledger
        # cursor is deliberately NOT reset -- it indexes the surviving ledger,
        # and any error rows stragglers land across the boundary are scanned
        # (and counted against the new window) on the next tick.
        self._brain_error_streak = 0
        self._last_brain_error = None
        self._llm_error_buf = []
        if self.mock_latency > 0:
            for char in self.chars.values():
                char.agent.schedule.latency_s = self.mock_latency
        if _is_paid(self.llm) and self._decide_executor is not None:
            # Parallel decides need one client instance PER AGENT: the engine
            # clients carry a single mutable `context` dict that the decide
            # path stamps per call (and _resilient_create writes mid-call), so
            # N threads through one shared client would clobber each other's
            # attribution. Each instance records into the same base ledger;
            # self.llm_client stays as the mode flag (injector gate,
            # conversation_enabled) and the serial fallback.
            #
            # self._agent_clients holds the RAW client per agent (built once,
            # ever -- its connection pool must survive a reset, see above).
            # The RecordingClient wrapper is rebuilt fresh every _build() from
            # that raw client, so a reset's new cassette writer is what this
            # run's calls land in -- wrapping the STORED (dict) value instead
            # would nest onto whatever a prior run already wrapped it with,
            # and write into that run's closed cassette file.
            for name, char in self.chars.items():
                if name not in self._agent_clients:
                    self._agent_clients[name] = self._decide_client()
                client = self._agent_clients[name]
                if self._cassette_writer is not None:
                    client = RecordingClient(client, writer=self._cassette_writer)
                char.agent.llm_client = client
        # Real conversations pace themselves through a per-pair cooldown that
        # must OUTLIVE each tick (simulate() keeps one for its whole run;
        # step()'s default is a throwaway dict, which would let a settled pair
        # re-converse every single step). Fresh per day, like the rest of the
        # world state.
        self._convo_cooldowns = {}
        # In-progress conversations carried across live ticks (issue #371), so a
        # meeting spans ticks instead of resolving inside one. Fresh per day/reset
        # (lives in _build, which reset() re-runs), like _convo_cooldowns.
        self._active_conversations = {}
        # Who was already within mutual sight last tick (issue #370): the
        # react pass's edge detector. Fresh per day/reset, like the two
        # conversation dicts above.
        self._react_state = {}
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
                "stop_since": 0,
                # Pinned during a multi-tick conversation (issue #371); step()
                # skips schedule-advance/decision/movement while set. Stays set
                # through the post-conversation playback hold (#673).
                "conversing": False,
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
            elif self._run_id is None:
                self._run_id = self.run_store.create_run(self._store_manifest())

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
        the ``_events_seen``/``_persist_events_seen`` cursors and the wish
        buffers (correct -- the new ``game.events``/``game.wishes`` start
        empty; the stored ``events.jsonl``/``wishes.jsonl`` are append-only
        history).
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
                # The character mirrors the state tile (issue #662): perception
                # must resume from where the agent stood, not its spawn stamp.
                # tuple(...) like the other two tile writers, so char.tile has
                # one shape everywhere.
                self.chars[name].tile = tuple(self.state[name]["tile"])
                # desc/pron/reasoning stay at their waking-up defaults: the
                # first resumed tick is a decision point (no path, not
                # performing) and overwrites them all.
        for name in self.order:
            agent = self.chars[name].agent
            # Elapsed-on-stop (#580) restarts at the resume point: the
            # fast-forwarded schedule below IS the stop the agent is on now.
            self.state[name]["stop_since"] = self._step_idx
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

    @property
    def dropped_events(self) -> int:
        """Count of malformed GameEvents this run dropped rather than persisting
        (#637). 0 on a healthy run; a non-zero value means the durable
        events.jsonl is missing records the feed may have shown."""
        return self._dropped_events

    @property
    def dropped_wishes(self) -> int:
        """Count of malformed ActionWishes this run dropped rather than
        persisting (#622, mirrors ``dropped_events``). 0 on a healthy run
        (and always 0 under the mock brain, which never wishes at all)."""
        return self._dropped_wishes

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
        too. ``run_calls``/``run_by_actor`` stay this-process (the store keeps
        no cheap call count to re-anchor on).

        ``run_calls`` and ``run_by_actor`` count only REAL model requests --
        records whose ``usage.provider`` is not ``"mock"``. The free mock
        schedule brain appends a ``provider="mock"``, $0 ``CallRecord`` every
        tick to pace the day; those are not LLM calls and never appear as
        run-monitor log rows, so counting them would show ``run_calls`` climbing
        over an empty log (#569.1) -- the run-scoped echo of the "27 calls over a
        3-row log" mismatch #526 set out to kill. ``run_cost_usd`` needs no such
        filter (mock records cost $0). ``run_by_actor`` is the run-scoped
        counterpart of the lifetime ``by_actor`` (#569.2): a dashboard can
        headline ``run_cost_usd`` beside per-agent spend that reconciles with it
        (``sum(run_by_actor.values()) == run_cost_usd`` for a fresh, non-resumed
        run), instead of mixing a run-scoped total with lifetime per-agent rows.

        ``run_failed_calls`` (#745) counts this run's FAILED real calls (error
        rows) -- 0 on a healthy day; climbing while ``run_cost_usd`` stands
        still is the mid-run-outage fingerprint, now visible in ``GET /usage``.
        """
        run_records = self.ledger.records[self._run_ledger_calls_base :]
        run_calls = 0
        run_failed_calls = 0
        run_by_actor: dict[str, float] = {}
        for rec in run_records:
            if rec.usage.provider == "mock":
                continue
            run_calls += 1
            if rec.error:
                # Failed real calls (#745): counted beside run_calls so the
                # dashboard can tell "brain erroring" from "not being asked".
                run_failed_calls += 1
            key = rec.actor or "(unattributed)"
            run_by_actor[key] = run_by_actor.get(key, 0.0) + rec.cost_usd
        return {
            "run_calls": run_calls,
            "run_failed_calls": run_failed_calls,
            "run_cost_usd": self._run_cost_usd(),
            "run_by_actor": {a: round(c, 6) for a, c in run_by_actor.items()},
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
                if _is_paid(self.llm)
                else None
            ),
        }

    def _sim_config_for_manifest(self) -> dict | None:
        """The #564 config as stored in the manifest: to_dict() minus the
        sections the live path ignores (game.llm, embedding) -- they can
        carry api_key material, which must never land in runs/ or be served
        by GET /runs/{id}. from_dict treats the absent keys as None, so the
        re-run reconstruction is unchanged."""
        if self.sim_config is None:
            return None
        data = self.sim_config.to_dict()
        data.get("game", {}).pop("llm", None)
        data.pop("embedding", None)
        return data

    def _store_manifest(self) -> dict:
        """The manifest persisted to the store: the handshake meta() plus the
        provenance a re-run needs (#715). Kept OFF meta() itself so the live
        GET /live blob and the pinned replay contract are unchanged.

        cognition_tools/react/plan_mode are the RESOLVED values (post the
        ``cognition_tools or (llm == SCRIPTED)`` coupling above), so
        ``reproduce_run`` can reconstruct the exact cognition config a real
        re-run needs instead of guessing it back from the ``llm`` sentinel.

        Also carries the applied pre-run ``config`` block (#732), when set --
        see below."""
        manifest = {
            **self.meta(),
            "seed": self.seed,
            "engine_sha": self._engine_sha,
            # Which SCENARIOS entry built this run's world (#747), so a re-run
            # rebuilds the same world instead of the default campus. Pre-#747
            # manifests lack the key and read back as the default scenario.
            "scenario": self.scenario,
            "cognition_tools": self.cognition_tools,
            "react": self.react,
            "plan_mode": self.plan_mode,
            # Per-persona plan provenance (#787): {name: "llm"|"static"}. The
            # plan_mode above is the request; this is what each agent got.
            "planner_sources": self._planner_sources,
            # The step BUDGET this run was launched with -- not how many steps
            # it actually took (that is the row's `steps`). meta() deliberately
            # omits it, but a re-run needs it (#787): LLMPlanner bounds the day
            # to the clock window the budget covers and puts that window in its
            # prompt, so a run stopped early -- at the cost ceiling, or by a
            # human -- would otherwise re-plan against a shorter window, change
            # the request key, and miss the cassette.
            "num_steps": self.num_steps,
            # The #564 --config, so a re-run rebuilds the same retrieval/
            # temperature/cognition and the cassette's request keys line up.
            # A default run stores None; pre-#564 manifests simply lack the key.
            # game.llm/embedding are stripped -- they can carry api_key
            # material and must never land in runs/ or GET /runs/{id}.
            "sim_config": self._sim_config_for_manifest(),
        }
        # The applied pre-run config (#732): persona ids + SimulationConfig
        # dump + run knobs, present only on a run someone configured -- so
        # every saved run records its setup (the E5 round-trip's source).
        if self._applied_config is not None:
            manifest["config"] = self._applied_config
        return manifest

    def _brain_name(self) -> str:
        return (
            "llm"
            if _is_paid(self.llm)
            else ("scripted" if self.llm == SCRIPTED else "mock")
        )

    def _stop_time(self) -> str:
        """The in-game wall-clock the run ends at -- SIM_START plus the step
        budget -- as a display string for the setup UI (#732). Read-only:
        the wire knob is `steps` (the sim's native unit)."""
        start = datetime.datetime.fromisoformat(SIM_START)
        return str(start + datetime.timedelta(seconds=self.num_steps * SEC_PER_STEP))

    def describe_config(self) -> dict:
        """The pre-run config surface GET /config serves (#732); read-only.

        `status` and `tick_seconds` are the loop's to report -- the route
        composes them in (the stepper doesn't know paused). `knobs` is the
        #564 SimulationConfig surface with the key-carrying sections
        (game.llm, embedding) stripped, exactly like the manifest dump.
        `llm` is advertised only when the server env holds a key -- keys
        never travel over HTTP.
        """
        defaults = SimulationConfig().to_dict()
        defaults.get("game", {}).pop("llm", None)
        defaults.pop("embedding", None)
        current = self._sim_config_for_manifest() or defaults
        personas = (
            library_personas(self.world.world_data) if self.world.world_data else []
        )
        active = {p["name"] for p in self.world.personas}
        brains = ["mock", "scripted"]
        if os.environ.get("ANTHROPIC_API_KEY"):
            brains.append("llm")
        return {
            "personas": personas,
            "cast": [e["id"] for e in personas if e["name"] in active],
            "knobs": {"defaults": defaults, "current": current},
            "brains": brains,
            # The planner knob (#787). `plans` is the accepted vocabulary and
            # `run.plan` the RESOLVED value the current brain would run, so the
            # setup screen can show "llm" for an auto+llm-brain session without
            # having to re-derive the auto rule client-side.
            "plans": ["auto", "schedule", "llm"],
            "run": {
                "brain": self._brain_name(),
                "plan": self.plan_mode,
                "steps": self.num_steps,
                "stop_time": self._stop_time(),
                "max_cost": self.ledger.max_cost_usd,
            },
        }

    def apply_config(
        self,
        *,
        cast: list[str] | None = None,
        brain: str | None = None,
        plan: str | None = None,
        sim_config: dict | None = None,
        steps: int | None = None,
        max_cost: float | None = None,
        tick_seconds: float | None = None,
    ) -> dict:
        """Apply a pre-run configuration by rebuilding through the reset path
        (#732). Caller holds the app lock and has already checked the
        paused-at-tick-0 gate; every field is optional (None = keep current).
        ValueError on any bad input -> the route's 400; guard-before-teardown
        (the create_run/resume_run discipline): everything that can fail is
        validated/built BEFORE the current run is closed. tick_seconds is the
        loop's knob, not this stepper's -- it rides through only so the echo
        (and so the manifest's config block) records the full setup.
        """
        # ---- validate + build; no teardown yet ----
        if cast is not None and not cast:
            raise ValueError("cast: must name at least one persona")
        new_sim_config = self.sim_config
        if sim_config is not None:
            # The wire never carries the key-bearing sections: describe_config /
            # _sim_config_for_manifest strip game.llm + embedding (they can hold
            # api_key material). So a POST of the stripped knobs.current has them
            # absent; rebuilding straight from it would reset a non-default
            # embedding (or game.llm) to None -- silently reverting memory
            # retrieval to keyword overlap on the first edit (#753). Re-attach
            # them from the live config (its only source of truth) before the
            # rebuild. The frontend sends the whole merged knobs.current, so the
            # ONLY missing pieces are these two top-level sections -- re-attach
            # them, don't deep-merge.
            merged = dict(sim_config)
            if self.sim_config is not None:
                live = self.sim_config.to_dict()
                if "embedding" in live:
                    merged["embedding"] = live["embedding"]
                live_llm = live.get("game", {}).get("llm")
                if live_llm is not None:
                    merged["game"] = {**merged.get("game", {}), "llm": live_llm}
            new_sim_config = SimulationConfig.from_dict(merged)
        new_llm = self.llm
        if brain is not None:
            if brain not in ("mock", "scripted", "llm"):
                raise ValueError(
                    f"unknown brain: {brain!r} (valid: mock, scripted, llm)"
                )
            if max_cost is not None and brain != "llm":
                raise ValueError("max_cost needs the llm brain")
            try:
                new_llm = resolve_llm(self.world.llm, brain, max_cost=max_cost)
                if _is_paid(new_llm):
                    # create_llm_client imports anthropic lazily -- _init_brain
                    # is the first place that actually happens, which is AFTER
                    # teardown. Probe here, before any teardown, so a server
                    # missing the extra fails clean instead of half-torn-down;
                    # before the network check_anthropic_key too, so a missing
                    # extra never even attempts the probe.
                    try:
                        import anthropic  # noqa: F401
                    except ImportError as exc:
                        raise ValueError(
                            f"{exc} (this server needs `uv sync --extra llm`)"
                        ) from exc
                    # The boot path's fail-fast (#261): a present-but-rejected
                    # key would otherwise serve a frozen, silent, $0 sim.
                    check_anthropic_key()
            except SystemExit as exc:
                # resolve_llm/check_anthropic_key speak CLI (SystemExit);
                # over HTTP the same message is a 400.
                raise ValueError(str(exc)) from exc
        elif max_cost is not None:
            if not _is_paid(new_llm):
                raise ValueError("max_cost needs the llm brain")
            new_llm = dict(new_llm, max_cost_usd=max_cost)
        # The planner (#787). Resolved against the brain THIS apply lands on,
        # not the one the server launched with: the config session is the run's
        # setup authority, so switching to mock must drop an auto-resolved llm
        # planner back to the schedule rather than fail. Only an explicit
        # `plan: "llm"` on a free brain is an error -- the same rule (and the
        # same message, re-voiced as a 400) __init__ applies to --plan llm.
        new_plan_flag = plan if plan is not None else self._plan_mode_flag
        if new_plan_flag not in ("auto", "schedule", "llm"):
            raise ValueError(
                f"unknown plan: {new_plan_flag!r} (valid: auto, schedule, llm)"
            )
        new_plan_mode = _resolve_plan_mode(new_plan_flag, new_llm)
        if new_plan_mode == "llm" and not _is_paid(new_llm):
            raise ValueError(
                "plan 'llm' needs the llm brain (the planner shares its client)"
            )
        effective_cast = cast if cast is not None else self._cast
        world = (
            self._world_builder(cast=effective_cast)
            if effective_cast is not None
            else self._world_builder()
        )  # ValueError on an unknown persona id -- before any teardown
        # ---- apply: the reset path, with the new knobs stamped on ----
        self._close_current_run()
        self._cast = effective_cast
        self.sim_config = new_sim_config
        self.retrieval = (
            new_sim_config.retrieval if new_sim_config is not None else None
        )
        # Set BEFORE _init_brain -- that is what reads plan_mode to decide
        # whether to build the dedicated planner client (#787).
        plan_changed = new_plan_mode != self.plan_mode
        self._plan_mode_flag = new_plan_flag
        self.plan_mode = new_plan_mode
        if brain is not None or plan_changed:
            # A plan change alone still needs the brain rebuilt: the planner
            # client is constructed there, so turning the planner on (or off)
            # without this would leave plan_mode saying "llm" and every agent
            # still on the MockPlanner.
            self._init_brain(new_llm)
        else:
            self.llm = new_llm  # a max_cost-only change still lands in meta()
        if brain is not None or (cast is not None and _is_paid(self.llm)):
            # The boot 'auto' rule (#366) re-derived on a brain or paid-cast
            # change: one slot per persona under a paid brain, serial
            # otherwise. A launch --decide-workers value is deliberately
            # superseded -- the config session is the run's setup authority.
            self._decide_executor = (
                _DecideThreads(len(world.personas)) if _is_paid(self.llm) else None
            )
        # The ceiling always mirrors the active brain (#732 final review):
        # a paid ceiling left armed after a switch to a free brain would
        # keep over_budget() true and finish every new day on its first
        # tick. The ledger OBJECT is never replaced -- create_app captured
        # it at boot -- only its ceiling is reconciled.
        self.ledger.max_cost_usd = (
            self.llm.get("max_cost_usd") if _is_paid(self.llm) else None
        )
        self.cognition_tools = _resolve_cognition_tools(
            self._cognition_tools_flag, self.sim_config, self.llm
        )
        self.react = _resolve_react(self._react_flag, self.sim_config)
        if steps is not None:
            # The configured budget is the run's new baseline: reset() must
            # not quietly revert it (unlike create_run's one-shot override).
            self.num_steps = self._launch_num_steps = steps
        applied = {
            # None = the world YAML's own default cast (never overridden).
            "cast": effective_cast,
            "brain": self._brain_name(),
            # The RESOLVED planner (#787), matching `brain` above -- what the
            # run will actually do, not the "auto" that was asked for.
            "plan": self.plan_mode,
            "sim_config": self._sim_config_for_manifest(),
            "run": {
                "steps": self.num_steps,
                "tick_seconds": tick_seconds,
                "max_cost": self.ledger.max_cost_usd,
            },
        }
        # Set BEFORE _build: the rebuild opens the new run row, and its
        # manifest must carry this block.
        self._applied_config = applied
        self._build(world=world)
        return applied

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
        # Mid-run brain outage (#745): the brain is failing every call (auth
        # revoked, quota, network down). Raising here -- BEFORE spending more
        # failing round-trips -- hands the run to backend.live's #637 tick-error
        # handler, which pauses visibly and publishes status(reason="error")
        # with this message, instead of the silent frozen-cast freeze. The
        # streak resets so a POST /resume retries with a fresh window.
        if (
            self.llm_client is not None
            and self._brain_error_streak >= BRAIN_OUTAGE_PAUSE_STREAK
        ):
            streak, last = self._brain_error_streak, self._last_brain_error
            self._brain_error_streak = 0
            raise BrainOutage(
                f"{streak} consecutive LLM call failures (last: {last}) -- "
                "pausing the run; fix the key/network, then resume to retry"
            )
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
            # Memory-retrieval scoring from --config (#564); None = engine
            # defaults. step() has threaded this into every decide since #296.
            retrieval=self.retrieval,
            clock=self.clock,
            # Real conversations only when a real brain drives -- the same gate
            # simulate() applies (conversation_enabled = llm_client is not None).
            conversation_enabled=self.llm_client is not None,
            conversation_cooldowns=self._convo_cooldowns,
            active_conversations=self._active_conversations,
            react_state=self._react_state,
            # Concurrent decides (#366): None executor = the serial path the
            # simulate-equivalence test pins; workers > 0 fans decisions out.
            decide_executor=self._decide_executor,
            decide_timeout=self.decide_timeout,
            decide_pending=self._decide_pending,
            decide_info=decide_info,
            # #551: emit the deciding lifecycle only under a real/scripted brain
            # (self.llm_client set) -- the pure mock feed stays byte-identical.
            deciding_sink=(
                self._deciding_sink if self.llm_client is not None else None
            ),
        )
        self.last_deciders = decide_info.get("deciders", 0)
        for name in decide_info.get("timeouts", ()):
            # Mirror the injector's FIRE print: the skipped decision must be
            # visible in the run log (#366 acceptance).
            print(
                f"  - DECIDE TIMEOUT {name} @ step {self._step_idx} -- "
                "idling this tick; its answer will apply when the call resolves"
            )
        # Brain health (#745): pick up any error rows the tick's calls (or a
        # parked #366 straggler) landed in the ledger -- each becomes a feed
        # row and counts against the consecutive-failure streak checked above.
        # Real/scripted brains only: the mock never errors and must never pay
        # the scan.
        if self.llm_client is not None:
            self._scan_llm_failures()
        frame = {name: replay_frame_entry(raw[name]) for name in self.order}
        # Paint authored dialogue post-step, exactly where the bake's injector
        # runs (on the converted frames, never the engine state) -- so a future
        # real-LLM chat in `raw` composes: the clash rule above skips over it.
        self.injector.apply(frame, self._step_idx)
        if self.run_store is not None:
            self._persist_tick(frame)
        else:
            # No store: _persist_tick (and its _persist_pending_wishes call)
            # never runs, but the wish persist-buffer still needs draining
            # every tick -- otherwise an endless, no-persist live run driven
            # by a proposing brain grows _wish_persist_buf without bound
            # (#622 review finding). _persist_pending_wishes() itself already
            # no-ops the actual write when there's no store; only the buffer
            # swap matters here.
            self._persist_pending_wishes()
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
        self._persist_pending_wishes()
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
            # Tolerant persistence (#637): a malformed event -- an evolving
            # schema field the allowlist rejects, a value that won't serialize
            # -- is dropped and counted, never allowed to raise through the tick
            # and permanently halt the run. The cursor advances past it either
            # way: a record the store can't accept must not be re-flushed
            # forever.
            bad = self.run_store.append_events(
                self._run_id,
                [event.to_primitive() for event in pending],
                skip_bad=True,
            )
            for event, reason in bad:
                self._dropped_events += 1
                # Mirror the DECIDE TIMEOUT print: a dropped record must be
                # visible in the run log, not silently swallowed.
                print(
                    f"  - DROPPED EVENT @ step {self._step_idx}: {reason} "
                    f"-- {event.get('summary', event)!r}"
                )
        self._persist_events_seen = len(self.game.events)

    def _finish_run(self) -> None:
        # Idempotent: the live loop keeps ticking a finished day (every tick
        # returns None) and only the first one flips the status. The tail
        # flush catches events (and wishes, #622) logged after the final tick
        # (#307).
        self._persist_pending_events()
        self._persist_pending_wishes()
        if (
            self.run_store is not None
            and self._run_id is not None
            and not self._run_finished
        ):
            self.run_store.update_run(self._run_id, status="finished")
            self._write_run_record()
            self._run_finished = True

    def _write_run_record(self) -> None:
        """Save the run's reproducibility recipe next to its frames (#715).

        The cassette sha is only knowable once the cassette is fully written, so
        this runs at finish. engine_version is the git sha captured at __init__
        -- never the literal "unknown" (#197 follow-up)."""
        if self._cassette_writer is None:
            return  # a mock run has no cassette; nothing to reproduce
        self._cassette_writer.close()
        record = RunRecord(
            game="penn",
            seed=self.seed,
            cassette={
                "path": "cassette.jsonl",
                "sha256": file_sha256(self._cassette_path),
            },
            engine_version=self._engine_sha,
            result={"steps": self._step_idx, "cost_usd": self._run_cost_usd()},
        )
        record.save(str(self.run_store.root / self._run_id / "run.yaml"))

    def set_deciding_publisher(self, publish) -> None:
        """Adopt the live feed's out-of-band `deciding` channel (#605).

        api.create_app calls this once at boot when serving live. From then on
        `_deciding_sink` sends each `begin` through *publish* the moment the
        decide starts -- from the decide's own thread; the live EventLog's
        append is thread-safe -- instead of buffering it for the tick-boundary
        drain. `end`s keep the boundary path, which lands them after the
        tick's frame record, so a within-tick decide reads begin (mid-tick),
        frame, end. A record published here is never also returned by
        drain_deciding(), so nothing double-publishes."""
        self._deciding_publish = publish

    def _deciding_sink(self, name: str, state: str, step: int) -> None:
        """Called by run_simulation._decide_for at a decision's start/finish
        (issue #551). With a live publisher wired (#605) a `begin` is published
        out-of-band immediately; everything else is buffered for backend.live's
        per-tick drain, which appends each row as a `kind: "deciding"`
        change-feed record.

        Held under `_deciding_lock` because this may run on a #366 decide worker
        thread while `drain_deciding` swaps the buffer on the tick thread: a
        lockless append could land on the detached old list and be lost, stranding
        the matching bubble (#598 review). An `end` with no matching `begin` THIS
        run -- a straggler finishing after a reset cleared `_deciding_started` --
        is dropped, so a stray elapsed-less `end` can't leak into the fresh run's
        feed and clear a real bubble there."""
        publish_now = None
        with self._deciding_lock:
            if state == "begin":
                self._deciding_started[name] = time.monotonic()
                record = {"agent": name, "state": "begin", "step": step}
                if self._deciding_publish is not None:
                    publish_now = record  # out-of-band below, NEVER also buffered
                else:
                    self._deciding_buf.append(record)
            else:  # "end"
                started = self._deciding_started.pop(name, None)
                if started is None:
                    return  # orphan end (pre-reset straggler): drop it
                self._deciding_buf.append(
                    {
                        "agent": name,
                        "state": "end",
                        "step": step,
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                    }
                )
        if publish_now is not None:
            # Outside _deciding_lock: the publisher takes the EventLog's own
            # lock, and keeping the two un-nested keeps the sink/drain critical
            # section tiny. Program order still puts this append before the
            # matching end is even buffered, so begin < end in cursor order.
            self._deciding_publish(publish_now)

    def drain_deciding(self) -> list:
        """New `deciding` records formed since the last drain (#551). backend.live
        probes this optional method after each tick and appends each as a
        `kind: "deciding"` feed record (beside the `engine` rows). Empty under the
        pure mock brain; with a live publisher wired (#605) `begin`s bypass this
        buffer entirely (published out-of-band as the decide starts), so the
        drain then carries only `end`s. Swaps under `_deciding_lock` so a
        concurrent `_deciding_sink` append can't be lost to the buffer swap
        (#598 review)."""
        with self._deciding_lock:
            rows = self._deciding_buf
            self._deciding_buf = []
        return rows

    def _scan_llm_failures(self) -> None:
        """Scan ledger rows appended since the last scan for failed calls (#745).

        Each failure -- an API error the adapter degraded to ``None``, recorded
        as a zero-cost error row -- is buffered as an ``llm_error`` feed row
        (published by :meth:`drain_events`) and counts against the
        consecutive-failure streak ``tick()`` checks. A genuinely answered call
        (non-mock, with real token usage) clears the streak; the zero-usage
        retry-attempt rows (#260) and the mock pacing records are neutral, so
        interleaved retries can never mask a dead key. Runs on the tick thread;
        a parked #366 straggler may append concurrently, which is safe (list
        append/slice are GIL-atomic) -- a row this scan misses is simply picked
        up next tick.
        """
        fresh = self.ledger.records[self._llm_failures_seen :]
        self._llm_failures_seen += len(fresh)
        for rec in fresh:
            usage = rec.usage
            if usage.provider == "mock":
                continue
            if rec.error:
                self._brain_error_streak += 1
                self._last_brain_error = rec.error
                self._llm_error_buf.append(
                    {
                        "kind": "llm_error",
                        "agent": rec.actor,
                        "role": rec.role,
                        "error": rec.error,
                        "streak": self._brain_error_streak,
                    }
                )
                # Mirror the DECIDE TIMEOUT print: a failed model call must be
                # visible in the run log even with --no-monitor.
                print(
                    f"  - LLM ERROR {rec.actor or '(unattributed)'} @ step "
                    f"{self._step_idx}: {rec.error} "
                    f"({self._brain_error_streak} consecutive)"
                )
            elif usage.total_input_tokens or usage.output_tokens:
                self._brain_error_streak = 0

    def drain_events(self) -> list:
        """New change-feed rows formed during the last ``tick()`` (#398, #467).

        ``backend.live`` probes this optional method after every tick and
        publishes each returned dict as a ``kind: "engine"`` change-feed
        record. Three row types ride it, told apart by their inner ``kind``:

        * ``"llm_call"`` -- the request monitor's kept records (a flattened
          :class:`~text_adventure_games.usage.CallRecord` plus ``role``/
          ``call_no``/``cum_cost_usd``/``time``), so the viewer's run monitor
          shows the same one-line-per-request log the terminal prints (#398).
        * ``"game_event"`` -- the engine ``GameEvent``s logged since the last
          drain (#467), ``to_primitive()`` dicts (the #305 EventState shape,
          identical to what the replay bake persists), e.g. the boil-water
          ``sickness`` events (#465).
        * ``"llm_error"`` -- one row per FAILED model call (#745):
          ``{agent, role, error, streak}``, buffered by
          :meth:`_scan_llm_failures` regardless of whether a monitor is wired,
          so a mid-run API outage names the erroring agent in the feed instead
          of freezing the cast silently.

        A finishing tick (``tick()`` -> ``None``) can still drain rows -- a
        ``POST /world/event`` landing between the last real tick and the
        day's close is the live case -- and since #644 backend.live publishes
        those before the ``finished`` status instead of dropping them, so the
        feed shows everything ``_persist_pending_events`` stores.
        """
        rows = []
        if self.monitor is not None:
            rows.extend(dict(rec, kind="llm_call") for rec in self.monitor.drain())
        # Failed-call rows (#745), right after the llm_call log lines they
        # annotate; buffered by _scan_llm_failures, monitor or not.
        rows.extend(self._llm_error_buf)
        self._llm_error_buf = []
        new_events = self.game.events[self._events_seen :]
        self._events_seen = len(self.game.events)
        rows.extend(
            dict(event.to_primitive(), kind="game_event") for event in new_events
        )
        return rows

    def _on_wish(self, wish) -> None:
        """Installed as ``game.on_wish`` by ``_build()`` (#622): the engine
        fires this synchronously the moment ``Game.log_wish`` records an
        :class:`~text_adventure_games.wishes.ActionWish` (a ``propose``, or an
        unparsed command, #621). Buffers the same primitive record into BOTH
        the feed queue (:meth:`drain_wishes`) and the persistence queue
        (:meth:`_persist_pending_wishes`) so draining one can never steal a
        record from the other."""
        rec = wish.to_primitive()
        with self._wish_lock:
            self._wish_feed_buf.append(rec)
            self._wish_persist_buf.append(rec)

    def drain_wishes(self) -> list:
        """New wish records formed since the last drain (#622).

        ``backend.live`` probes this optional method after every tick and
        publishes each returned dict as its OWN top-level ``kind: "wish"``
        change-feed record -- unlike llm_call/game_event, a wish does not ride
        inside the ``engine`` envelope (it mirrors the #551 ``deciding``
        record's own top-level kind instead). Empty for the whole run under
        the mock brain: it never proposes and its authored commands always
        parse, so ``game.on_wish`` is simply never called (byte-identical by
        vacuity, pinned by test_wish_feed.py's
        ``test_mock_stepper_emits_no_wish_records``).
        """
        with self._wish_lock:
            rows, self._wish_feed_buf = self._wish_feed_buf, []
        return rows

    def _persist_pending_wishes(self) -> None:
        # ActionWishes buffered since the last flush -> wishes.jsonl (#622),
        # mirroring _persist_pending_events. Also called by _finish_run() and
        # _close_current_run(): a wish logged between the last tick and the
        # day's close must not be lost. Drains the buffer unconditionally
        # (even with no run_store) so an unpersisted run's persist-queue can
        # never grow unbounded across a long, wish-heavy live-LLM day.
        with self._wish_lock:
            pending, self._wish_persist_buf = self._wish_persist_buf, []
        if self.run_store is None or self._run_id is None:
            return
        if pending:
            # Tolerant persistence (#637's precedent): a malformed wish -- an
            # evolving `meta` field the allowlist rejects, a value that won't
            # serialize -- is dropped and counted, never allowed to raise
            # through the tick and permanently halt the run.
            bad = self.run_store.append_wishes(self._run_id, pending, skip_bad=True)
            for wish, reason in bad:
                self._dropped_wishes += 1
                print(
                    f"  - DROPPED WISH @ step {self._step_idx}: {reason} "
                    f"-- {wish.get('desired', wish)!r}"
                )

    def _close_current_run(self) -> None:
        """Persist pending events and mark the live run 'reset' before a rebuild
        (a finished day keeps 'finished'). Shared by reset/create_run/resume_run.

        Clears self._run_id (#715 follow-up): the upcoming _build() rebuilds
        for a NEW day, so the non-resume `elif self._run_id is None` guard
        there must see None again to open a fresh run row -- without this, a
        rebuild after the first would keep reusing the just-closed run's id
        forever (caught by test_stepper_reset_closes_the_run_and_opens_a_new_one
        et al.). A resumed rebuild is unaffected: it adopts an explicit
        resume_run_id regardless of this attribute.
        """
        self._persist_pending_events()
        self._persist_pending_wishes()
        if self._cassette_writer is not None:
            self._cassette_writer.close()
            self._cassette_writer = None
        if (
            self.run_store is not None
            and self._run_id is not None
            and not self._run_finished
        ):
            # ...and bank what it spent (#782). _persist_tick writes cost per
            # tick, so a day that ran keeps the sum it already had; a run
            # closed BEFORE its first tick has never persisted one and would
            # otherwise keep cost=0.0 no matter what it spent. That is not
            # hypothetical under --plan llm: the boot run of a config session
            # (#732) pays for a model-authored day at attach time and is then
            # discarded by apply_config, so without this its planning spend
            # is charged to no run at all -- the same hole as the baseline
            # above, one build later. steps stays _persist_tick's to write.
            self.run_store.update_run(
                self._run_id, status="reset", cost=self._run_cost_usd()
            )
        self._run_id = None

    def reset(self) -> None:
        # A reset is a new day AND a new run: close the old run's row first
        # (status "reset" -- its frames stay readable), then _build() opens
        # the next one. A day that already finished keeps "finished".
        self._close_current_run()
        self.num_steps = self._launch_num_steps
        self._build()

    def create_run(self, world: str, *, steps: int | None = None) -> str:
        """Build a NAMED world from the factory registry, open a fresh run in
        the store, and adopt it as the live one (#568); caller holds the app
        lock, like reset()/resume_run().

        The world is built BEFORE any teardown (guard-before-teardown, like
        resume_run): an unknown world name or a failed build leaves the live
        run intact. v1 chooses only the world and an optional step budget --
        the launch-configured brain is reused, so the LLM clients (built once
        in __init__, surviving _build on purpose) are untouched and meta()
        stamps the new run's manifest correctly.

        The unknown-world ``KeyError`` is the ONLY KeyError this raises (the
        route maps it to 404). A KeyError raised while BUILDING is re-raised as
        a RuntimeError so a build fault can't masquerade as "unknown world".
        """
        if self.run_store is None:
            raise ValueError("this server has no run store (--persist)")
        builder = WORLD_BUILDERS.get(world)
        if builder is None:
            raise KeyError(f"unknown world: {world}")
        try:
            world_obj = builder()  # build first -- no teardown yet
            # Close the current day the way reset() does (a finished day keeps
            # "finished"), then rebuild on the new world -- _build's non-resume
            # path opens the next run row via create_run(self.meta()).
            self._close_current_run()
            # A named-world create is a fresh setup: the pre-run config
            # (#732) described the run it configured, not this one -- a
            # stale block here would stamp this manifest with a cast that
            # isn't running.
            self._cast = None
            self._applied_config = None
            # attach_agents reads num_steps inside _build. A per-request steps is
            # a one-shot override; without one, fall back to the launch budget so
            # a prior reduced create_run does not leak forward.
            self.num_steps = steps if steps is not None else self._launch_num_steps
            self._build(world=world_obj)
        except KeyError as exc:
            # A build-path KeyError is NOT the unknown-world signal; don't let
            # it reach the route's KeyError -> 404 handler.
            raise RuntimeError(f"world {world!r} failed to build") from exc
        return self._run_id

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
        self._close_current_run()
        # the resumed run's own recorded config is authoritative (#564
        # adopt); this server's pre-run config belongs to the run it
        # configured.
        self._cast = None
        self._applied_config = None
        # A resumed run must not inherit a prior create_run's reduced budget;
        # the launch default is the safe non-leaking value.
        self.num_steps = self._launch_num_steps
        self._build(resume_run_id=run_id, resume_row=row, resume_frames=frames)

    def rerun_run(self, run_id: str) -> dict:
        """Re-run a persisted run and report whether it reproduced byte-identically
        (#715). Ephemeral -- never touches the live run. Probed off the stepper by
        POST /runs/{id}/rerun, the resume/create_run idiom."""
        if self.run_store is None:
            raise ValueError("this server has no run store (--persist)")
        return reproduce_run(self.run_store, run_id).to_dict()


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


@dataclass
class ReproResult:
    """Outcome of re-running a persisted run from its cassette (#715)."""

    run_id: str
    steps: int
    match: bool
    first_divergence: int | None
    engine_sha_recorded: str | None
    engine_sha_current: str

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "steps": self.steps,
            "match": self.match,
            "first_divergence": self.first_divergence,
            "engine_sha_recorded": self.engine_sha_recorded,
            "engine_sha_current": self.engine_sha_current,
        }


def _canonical_frame(frame) -> str:
    """Key-order-independent string for one replay frame."""
    return json.dumps(frame, sort_keys=True, ensure_ascii=False)


def _sim_config_from_manifest(manifest: dict) -> SimulationConfig | None:
    """The run's recorded #564 SimulationConfig, or None for a default run
    (including runs recorded before the key existed)."""
    data = manifest.get("sim_config")
    return SimulationConfig.from_dict(data) if data else None


def reproduce_run(store: RunStore, run_id: str) -> ReproResult:
    """Re-run a persisted run offline from its cassette + seed and check the
    frames come out byte-identical to what the store holds (#715).

    Zero network: the world is driven by a ReplayClient over
    runs/<id>/cassette.jsonl -- no provider, no key, no spend. The re-run
    reconstructs the recorded scenario world (#747) and cognition config
    (seed, cognition_tools, react, plan_mode, sim_config) from the manifest
    and always forces decide_workers=0, so byte-identity holds for runs that
    were recorded under sequential decide (the default for --brain scripted;
    opt-in via --decide-workers 0 for --brain llm). A run recorded under
    parallel decide (--decide-workers > 0, the paid default) may have
    resolved its agents' decisions in a different order than a serial re-run
    would, so it is outside this guarantee.

    Model-planned runs re-run too (#787). ``--plan llm`` used to be refused
    here -- the planner's day was model-authored but the re-run's planner was
    the mock, so it could only diverge. It now replays out of the same cassette
    as every other call (see the replay branch in ``_init_brain``), which is
    what lets ``--plan llm`` be the live default without giving up #715.
    """
    row = store.get_run(run_id)
    if row is None:
        raise KeyError(f"unknown run id: {run_id}")
    manifest = row["manifest"]
    seed = int(manifest.get("seed", 0))
    # The recorded scenario (#747): rebuild through the SAME SCENARIOS dispatch
    # serve_penn uses at boot, or a --scenario boil run would be replayed on a
    # default-campus world and report DIVERGED despite reproducing perfectly.
    # Pre-#747 manifests lack the key and mean the default scenario (the only
    # world they could have been recorded on). An unknown name fails loudly --
    # ValueError, the vocabulary the CLI and the HTTP route (409) both map --
    # rather than silently building the wrong world.
    scenario_name = manifest.get("scenario", "penn")
    scenario = SCENARIOS.get(scenario_name)
    if scenario is None:
        raise ValueError(
            f"run {run_id} was recorded with unknown scenario "
            f"{scenario_name!r} (this build knows: {', '.join(sorted(SCENARIOS))}); "
            "refusing to rebuild the default campus and report a bogus verdict"
        )
    cassette_path = str(store.root / run_id / "cassette.jsonl")
    if not os.path.exists(cassette_path):
        raise ValueError(
            f"run {run_id} has no cassette -- only runs recorded with a real "
            "client (--brain scripted|llm) can be re-run"
        )
    stored = store.read_frames(run_id)
    n = len(stored)

    # reproduce_run reseeds process-global RNG (seed_world in _build). This can
    # run in an executor thread (POST /runs/{id}/rerun) concurrently with a live
    # tick, so snapshot and restore global random state to isolate the re-run's
    # determinism from the rest of the process.
    _rng_state = random.getstate()
    rerun = []
    miss_at = None
    try:
        stepper = PennStepper(
            # The recorded BUDGET, not the frame count: it shapes the planner's
            # prompt (#787), and a run stopped early has fewer frames than
            # steps. We tick exactly n times below regardless, so a larger
            # budget only means the re-run doesn't call itself finished.
            # Pre-#787 manifests lack the key; those runs are schedule-planned,
            # where num_steps reaches no prompt, so n is as good as anything.
            num_steps=int(manifest.get("num_steps", n)),
            world=scenario["world"](),
            monitor=None,
            llm=None,  # the replay branch below supplies the brain; llm is unused
            run_store=None,  # ephemeral: never persist over the original
            seed=seed,
            replay_cassette=cassette_path,
            decide_workers=0,  # sequential -> deterministic, no timeout races
            cognition_tools=manifest.get("cognition_tools", False),
            react=manifest.get("react", False),
            plan_mode=manifest.get("plan_mode", "schedule"),
            sim_config=_sim_config_from_manifest(manifest),
            # The scenario's pinned perception radius (#728) shaped the
            # recorded observations (and so the cassette's request keys);
            # None for penn/boil leaves the config/default value, unchanged.
            vision_r=scenario["vision_r"],
        )
        for _ in range(n):
            try:
                frame = stepper.tick()
            except CassetteMiss:
                # A missing recorded response IS a divergence, not a crash: the
                # re-run asked something the recording never captured (e.g. the
                # engine changed the decide prompt, so the request key no longer
                # matches). That is exactly what this check exists to report --
                # so record the frame it happened at and fall through to the
                # DIVERGED verdict instead of letting CassetteMiss escape (it is
                # neither KeyError nor ValueError, so the CLI and the HTTP route
                # would otherwise traceback / 500 instead of reporting match=False).
                miss_at = len(rerun)
                break
            if frame is None:
                break
            rerun.append(frame)
    except CassetteMiss:
        # The same divergence, one build earlier (#787): under --plan llm the
        # planner runs inside _build(), so a re-run whose PLANNING diverges
        # misses the cassette before there is a stepper to tick. Frame 0.
        miss_at = 0
    finally:
        random.setstate(_rng_state)

    first = None
    for i in range(min(len(stored), len(rerun))):
        if _canonical_frame(stored[i]) != _canonical_frame(rerun[i]):
            first = i
            break
    if first is None and len(stored) != len(rerun):
        first = min(len(stored), len(rerun))
    if miss_at is not None and (first is None or miss_at < first):
        first = miss_at
    match = first is None and len(stored) == len(rerun) and miss_at is None
    return ReproResult(
        run_id=run_id,
        steps=n,
        match=match,
        first_divergence=first,
        engine_sha_recorded=manifest.get("engine_sha"),
        engine_sha_current=git_sha(),
    )


def _fmt_or_default(value) -> str:
    """``:g``-format *value*, or ``"default"`` when it's ``None`` (#564 review
    finding 3): a config file can leave any numeric field unset (a blank
    ``key:`` parses as YAML null), and ``f"{None:g}"`` raises ``TypeError``."""
    return f"{value:g}" if value is not None else "default"


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


def _build_parser() -> argparse.ArgumentParser:
    """Build the serve_penn CLI parser (a seam so the arg defaults are testable
    without booting a server)."""
    ap = argparse.ArgumentParser(
        description="Serve the live Penn sim for the Godot viewer (#263)."
    )
    ap.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="penn",
        help="which world to serve, mirroring the bake's --scenario names: "
        "'penn' (default: the full campus cast), 'boil' (the one-persona "
        "boil-water demo, #592), or 'boil_hard' (#728: the demo with the stove "
        "relocated to a separate Kitchen and vision_r pinned to 0 -- the "
        "connect-the-dots experiment world)",
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
        choices=("mock", "scripted", "llm"),
        default="mock",
        help="mock (default): the deterministic schedule brain -- offline, free, "
        "authored meeting dialogue on. scripted: a deterministic, key-free brain "
        "that drives the full backend offline (tool loop, cognition tools, "
        "conversation, reflection; #563). llm: the model named by the world's "
        "llm: block (Anthropic Claude Haiku) makes every decide/converse/"
        "reflect call; needs ANTHROPIC_API_KEY and `uv sync --extra llm`",
    )
    ap.add_argument(
        "--plan",
        choices=("auto", "schedule", "llm"),
        default="auto",
        help="auto (default): llm under --brain llm, schedule otherwise (#787) "
        "-- a run paying for model cognition gets a model-authored day. "
        "schedule: agents follow the authored YAML day, so the hand-tuned "
        "meeting overlaps hold. llm: the model authors each agent's day "
        "(LLMPlanner, #397) -- free-play, so scripted rendezvous meetings may "
        "not converge; requires --brain llm",
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
        "--model-for",
        action="append",
        default=None,
        metavar="ROLE=MODEL",
        help=(
            "Route one call-site role to a different model (repeatable), e.g. "
            "--model-for plan=claude-sonnet-4-6. Valid roles: decide, plan, "
            "reflect, converse, outcome, score, react. Layers on top of the "
            "world YAML's llm.models map; only meaningful with --brain llm."
        ),
    )
    ap.add_argument(
        "--persist",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="record this run durably (#304), ON BY DEFAULT: frames to "
        "runs/<run_id>/frames.jsonl, agent memory + run metadata to runs/sim.db, "
        "under godot-generative-agents/runs/. POST /reset starts a new run id. "
        "--no-persist makes the run ephemeral (no runs/ rows, no store writes) "
        "for dev/smoke/throwaway sessions",
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
        "the newest run. Needs a run store, present by default (do not combine "
        "with --no-persist)",
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
        "--react",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="perception-driven interruption (#370): a walking agent that "
        "newly notices another resident may spend one 'react' model call "
        "(continue/greet/replan), rule-gated and capped per sim hour; a "
        "greet pauses the walk for a conversation, then the walk resumes. "
        "Needs a real brain: under --brain mock the pass never runs "
        "(conversation is disabled). Note: 'replan' only changes the day "
        "under --plan llm",
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
        "--seed",
        type=int,
        default=0,
        help="RNG seed pinned for this run (#715); recorded into the run's "
        "manifest so --re-run reproduces it byte-identically",
    )
    ap.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="load a SimulationConfig (.yaml/.json, #564) and tune the live "
        "sim with it: the retrieval: section (memory-scoring weights), the "
        "cognition: section (vision_r, conversation pacing, ...), and "
        "game.agent's temperature / reflection_threshold are honored. The "
        "batch-runner sections (simulation:, embedding:) and game.llm are "
        "ignored here (the world YAML's llm: block drives the model) -- "
        "live runs keep --steps/--tick-seconds. Boolean flags "
        "(--cognition-tools, --react) still force their feature ON over "
        "the file. Recorded into the run manifest so --re-run reproduces it",
    )
    ap.add_argument(
        "--re-run",
        dest="re_run",
        default=None,
        metavar="RUN_ID",
        help="reproduce a persisted run offline from its cassette + seed and "
        "check it is byte-identical (#715), then exit; does not start a server. "
        "Needs a run store (present by default)",
    )
    ap.add_argument(
        "--token",
        default=None,
        help="require 'Authorization: Bearer <token>' (defaults to the "
        "SIM_API_TOKEN env var; required for a non-loopback --host)",
    )
    return ap


def main() -> int:
    ap = _build_parser()
    args = ap.parse_args()

    # A repo-root .env (git-ignored; template at .env.example) can supply
    # ANTHROPIC_API_KEY / SIM_API_TOKEN without per-terminal exports;
    # already-exported environment variables always win (backend/env.py).
    if load_dotenv():
        print("Loaded .env from the repo root (already-exported variables win).")

    # The #564 config source: one file for the sim's tuning surface instead of
    # N per-knob flags. A bad path/parse aborts before any world state exists.
    sim_config = None
    if args.config:
        try:
            sim_config = SimulationConfig.from_file(args.config)
        except (OSError, ValueError, ImportError) as e:
            raise SystemExit(f"cannot load --config {args.config}: {e}")

    # Build the scenario's world once: resolve_llm reads its llm: block, the
    # stepper steps it (a second build would waste the map load and fork patch
    # state). The builder itself rides along so reset() rebuilds the SAME
    # scenario (#728).
    scenario = SCENARIOS[args.scenario]
    world = scenario["world"]()
    llm = resolve_llm(
        world.llm,
        args.brain,
        model=args.model,
        max_cost=args.max_cost,
        model_for=_parse_model_for(args.model_for),
    )
    if _is_paid(llm):
        # The key exists (resolve_llm gates that); now prove the API accepts
        # it, or an invalid key would serve a frozen, silent, $0 all-day sim.
        check_anthropic_key()
    # A paying brain shouldn't spend before anyone is watching: under --brain
    # llm the loop boots paused and the viewer's Start button (POST /resume)
    # opens the day. The free mock keeps auto-starting. --[no-]start-paused
    # overrides either way.
    start_paused = args.start_paused if args.start_paused is not None else _is_paid(llm)
    store = RunStore(DEFAULT_RUNS_DIR) if args.persist else None
    if args.re_run is not None:
        if store is None:
            raise SystemExit("--re-run needs a run store; drop --no-persist")
        if args.config:
            # #564 review finding 5: reproduce_run reconstructs the SAME
            # sim_config the run was recorded with (from its manifest) --
            # a --config passed alongside --re-run would silently do nothing,
            # so say so rather than let it look honored.
            print(
                f"NOTE: --config {args.config} is ignored for --re-run -- the "
                "run's own recorded sim_config (if any) is reconstructed from "
                "its manifest instead."
            )
        try:
            result = reproduce_run(store, args.re_run)
        except (KeyError, ValueError) as exc:
            raise SystemExit(f"cannot re-run: {exc}")
        verdict = "byte-identical" if result.match else "DIVERGED"
        print(
            f"re-run {result.run_id}: {verdict} over {result.steps} steps "
            f"(recorded on {result.engine_sha_recorded}, now {result.engine_sha_current})"
        )
        if not result.match:
            print(f"  first divergence at frame {result.first_divergence}")
        return 0 if result.match else 1
    resume_id = resolve_resume(store, args.resume) if args.resume else None
    # 'auto' concurrency (#366): a real brain decides in parallel (LLM latency
    # is the whole point); the mock AND the scripted brain (#563) stay serial so
    # the offline run stays deterministic -- the scripted brain reads
    # context["actor"] per decide, which a parallel decide would race. An
    # explicit integer wins.
    if args.decide_workers == "auto":
        decide_workers = len(world.personas) if _is_paid(llm) else 0
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
            react=args.react,
            decide_workers=decide_workers,
            decide_timeout=args.decide_timeout,
            mock_latency=args.mock_latency,
            stall_seconds=args.stall_seconds,
            plan_mode=args.plan,
            resume_run_id=resume_id,
            seed=args.seed,
            sim_config=sim_config,
            world_builder=scenario["world"],
            vision_r=scenario["vision_r"],
            scenario=args.scenario,
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
        f"Loaded the_upenn ({wm.width}x{wm.height}), scenario '{args.scenario}'; "
        f"{len(stepper.order)} personas, {len(stepper.world.meetings)} authored "
        f"meetings. Stepping every {args.tick_seconds}s "
        f"({'endless' if args.endless else f'{args.steps}-step day'})."
    )
    if _is_paid(llm):
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
    elif llm == SCRIPTED:
        print(
            "Brain: scripted (deterministic, free) -- drives the full backend "
            "offline: tool loop, cognition tools, conversation, reflection (#563). "
            "For the real thing: --brain llm."
        )
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
    else:
        print(
            "Persistence: OFF (--no-persist) -- this run is ephemeral and cannot "
            "be saved or resumed later."
        )
    # These three read stepper.sim_config/cognition_tools/react -- the
    # RESOLVED values -- rather than the CLI's own sim_config/args.* (#564
    # review findings 1 + 4): a resumed run may have adopted a different
    # sim_config than what --config loaded, and cognition_tools already
    # folds in game.agent.cognition_tools + the scripted-brain coupling, so
    # re-deriving either from args here would drift from what is actually
    # driving the sim.
    if stepper.sim_config is not None:
        r = stepper.sim_config.retrieval
        print(
            f"Sim config: {args.config or '(resumed run)'} -- retrieval "
            f"recency={_fmt_or_default(r.alpha_recency)}/"
            f"importance={_fmt_or_default(r.alpha_importance)}/"
            f"relevance={_fmt_or_default(r.alpha_relevance)} (max {r.max_records}), "
            f"temperature={_fmt_or_default(stepper.sim_config.game.agent.temperature)}, "
            f"vision_r={stepper.cog.vision_r}."
        )
    if stepper.cognition_tools:
        print(
            "Cognition tools: ON -- a decide tick may spend up to 3 model "
            "requests (recall/query_knowledge/read_plan before acting)."
            if llm is not None
            else "Cognition tools: ON, but the mock brain never reaches the "
            "tool loop -- pair it with --brain llm for any effect."
        )
    if stepper.react:
        print(
            "React gate: ON -- a mid-walk encounter may consult the brain "
            "(continue/greet/replan, #370), capped per agent per sim hour."
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
            "(or POST /resume) to begin the day. While paused at tick 0 the "
            "run is configurable: GET/POST /config (#732)."
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
