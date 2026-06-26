"""Drive the Smallville sim and export it for the frontend to replay.

This is the outer loop of the port. The frontend's clock (one 10-second step,
sprites walking one tile at a time) is finer-grained than the engine's
action-level turns, so the *step* loop lives here and consults the engine's
decision seam (``Agent.decide`` -> mock client) only at decision points:

* When a character is idle (no walk in progress, not yet settled into an
  activity), ask its agent what to do. ``travel`` routes through the engine
  (moving its logical location) and we ask the pathfinder for a tile route;
  ``perform`` settles it into an activity in place.
* Every step, advance one tile along any active path, then record the
  character's tile + emoji + action label into that step's movement frame.

Run it from the repo root (``backend`` is an installed package; ``uv run``
finds the project env that has it)::

    uv run python -m backend.run_simulation            # 3 hours (1080 steps)
    uv run python -m backend.run_simulation --steps 120
    uv run python -m backend.run_simulation --start "2023-02-13 18:00:00"
    uv run python -m backend.run_simulation --sec-per-step 60   # 1 min/step
"""

import argparse
import datetime
import os
from contextlib import nullcontext

from text_adventure_games.embedding_client import (
    EmbeddingConfig,
    create_embedding_client,
    embedding_client_from_env,
)
from text_adventure_games.llm_client import LlmConfig, create_llm_client
from text_adventure_games.planning import (
    ACTION_FAILED,
    BEHIND_SCHEDULE,
    RevisionTrigger,
)
from text_adventure_games.npc import maybe_reflect
from text_adventure_games.reporting import Channel, Message, default_renderer
from text_adventure_games.usage import UsageLedger

from . import exporter
from .build_world import ALL_PERSONAS, PERSONAS, build_world
from .sim_clock import SimClock
from .sim_config import CognitionConfig, SimulationConfig
from .smallville_agents import (
    attach_agents,
    maybe_converse,
    maybe_revise_plan,
    memories_for_frame,
    memory_stream_for_persona,
    observe_and_decide,
    remember_outcome,
)
from .world_map import WorldMap

# backend/ is a top-level package at the repo root, but the Smallville replay
# assets it reads (the maze + storage) still live under the generative-agents/
# frontend that consumes them, so reach back into that sibling directory.
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_GA_DIR = os.path.join(os.path.dirname(_PACKAGE_DIR), "generative-agents")
_FRONTEND = os.path.join(_GA_DIR, "frontend")

DEFAULT_VILLE_DIR = os.path.join(_FRONTEND, "static_dirs", "assets", "the_ville")
DEFAULT_STORAGE = os.path.join(_FRONTEND, "storage")
# The 25-resident base sim: the backend reuses its persona memory (copied into
# each generated sim so the frontend's click-a-persona state panel has something
# to show). setup.sh copies it into frontend/storage/.
DEFAULT_BASE_SIM = "base_the_ville_n25"

# The run-time defaults (steps, start, sec-per-step, sim-code, base-sim) now live
# on SimulationRuntimeConfig (sim_config.py); the CLI flags default to None and
# fall back to that config. DEFAULT_STEPS is kept only for the --steps help text.
#
# 3 hours of in-game time at 10 seconds per step (8-11am): long enough for each
# agent to work through its daily schedule of stops, so memory keeps growing
# across the run instead of freezing after the first activity. The 8am start
# (the town waking up) lives on SimulationRuntimeConfig.start.
DEFAULT_STEPS = 1080

WALK_EMOJI = "\U0001f6b6"  # person walking


def _parse_start(value: str) -> datetime.datetime:
    """Parse a --start value like '2023-02-13 08:00:00' (ISO 8601)."""
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid start time {value!r}; use ISO format, "
            "e.g. '2023-02-13 08:00:00'"
        )


def resolve_embedding_client(provider: str | None):
    """Resolve a semantic-memory embedding client for the sim (issue #102).

    Precedence: an explicit ``--embeddings`` *provider* wins; otherwise fall back
    to the ``EMBEDDING_PROVIDER`` environment variable (via the engine's
    ``embedding_client_from_env``). Returns ``None`` -- keyword-overlap relevance,
    the offline default -- when neither is set, or when the chosen backend can't
    be created (e.g. the ``embeddings`` extra isn't installed). That graceful
    degrade is what keeps the plain ``run_simulation`` run free, offline, and
    CI-safe even with a default-on flag.

    Either way the deterministic mock brain decides from location alone, so the
    exported replay stays byte-identical; an embedding client only reorders the
    (mock-ignored) retrieved-memory block. Run ``backend.compare_retrieval`` to
    actually watch semantic vs keyword retrieval diverge.
    """
    if not provider:
        return embedding_client_from_env()
    try:
        config = EmbeddingConfig(
            provider=provider,
            model=os.environ.get("EMBEDDING_MODEL"),
            api_key=os.environ.get("EMBEDDING_API_KEY"),
            base_url=os.environ.get("EMBEDDING_BASE_URL"),
        )
        return create_embedding_client(config)
    except (ImportError, ValueError) as e:
        print(
            f"Warning: could not create embedding client ({e}); falling back "
            "to keyword-overlap relevance."
        )
        return None


def simulate(
    world_map: WorldMap,
    num_steps: int,
    ledger: UsageLedger | None = None,
    embedding_client=None,
    *,
    retrieval=None,
    cognition=None,
    relationships_csv: str | None = None,
    base_personas_dir: str | None = None,
    out_memories: dict | None = None,
    personas: list[dict] | None = None,
    build_world_fn=None,
    clock: SimClock | None = None,
    planner_client=None,
    reflector_client=None,
    llm_client=None,
    out_planner_sources: dict | None = None,
    out_plans: dict | None = None,
) -> list[dict]:
    """Run the simulation and return one movement frame per step.

    Each frame is ``{persona_name: {movement, pronunciatio, description, chat}}``.
    Builds its own game + agents, so it is self-contained and easy to test.

    Pass a shared ``ledger`` to accumulate per-agent LLM token/cost accounting
    across the run (usage.py); the mock brain records zero cost, so the numbers
    are $0 until a real client is wired in (NEXT-STEPS Phase A).

    Pass an optional ``embedding_client`` (issue #76) for semantic memory
    relevance. The mock brain decides from location alone, so the frames are
    byte-identical with or without it; only the retrieved-memory block changes.

    Pass an optional ``retrieval`` (:class:`sim_config.RetrievalConfig`) to tune
    the memory-retrieval scoring; ``None`` uses the engine defaults. As above, the
    mock brain ignores the retrieved block, so the frames stay byte-identical --
    only *which* memories surface changes.

    Pass an optional ``cognition`` (:class:`sim_config.CognitionConfig`) to set the
    perception radius (``vision_r``) and conversation pacing; ``None`` uses today's
    defaults. ``vision_r`` only changes co-presence under a TiledGame, and
    conversation is a no-op under the mock brain, so the mock replay is unchanged.

    Pass ``relationships_csv`` / ``base_personas_dir`` (the upstream bootstrap
    assets) to seed each persona at t=0 -- relationships into memory, partial
    known-places into knowledge (issue #79, via :func:`attach_agents`). Both are
    optional: tests call ``simulate`` without them and stay byte-identical, while
    a real run (:func:`main`) points them at ``frontend/``.

    Pass an ``out_memories`` dict to also collect each agent's *full* memory
    stream (``{persona_name: [memory dicts]}``) at the end of the run -- the
    exporter writes it per persona so the State Details panel can show every
    memory an agent formed, not just the few retrieved per step. It's an
    out-parameter (not part of the return) so the many ``frames = simulate(...)``
    callers and the determinism tests stay unchanged.

    Pass a :class:`~backend.sim_clock.SimClock` to enable clock-based plan
    revision (issue #83): at an hour boundary an agent still en route is "behind
    schedule," a trigger its planner may react to. With no clock (the test
    default) those triggers never fire. Either way the mock planner's ``revise``
    is a no-op, so the exported frames are byte-identical -- the clock only gates
    *whether the seam is offered*, not the deterministic decisions themselves.

    Pass a ``planner_client`` (an engine ``LlmClient``) to plan each day with a
    real model (:class:`~backend.planner.LLMPlanner`); with none -- the offline
    default -- each agent replays its authored schedule via ``MockPlanner`` and the
    replay is byte-identical. ``main`` supplies one only for a non-mock provider.

    Pass an ``llm_client`` (NEXT-STEPS Phase A) to make the per-step travel/perform
    *decisions* through a real model: it becomes each agent's brain, while a
    deterministic ``SmallvilleMockClient`` still paces the schedule
    (``advance``/``steps``/``emoji``). With none -- the offline default -- that mock
    client is also the brain, so decisions stay deterministic and byte-identical.
    A real ``llm_client`` also enables **conversation** (NEXT-STEPS Phase E, issue
    #86): co-located, settled residents run a turn-taking dialogue each step (via
    :func:`~backend.smallville_agents.maybe_converse`), writing each line into both
    agents' memory streams and onto their replay cards' ``chat`` field. With the
    mock brain no utterance is produced, so no conversation happens and the replay
    stays byte-identical.

    Pass a ``reflector_client`` (an engine ``LlmClient``) to give each agent an
    ``LLMReflector`` for periodic memory synthesis (issue #84): the loop runs a
    reflection pass once an agent's accumulated importance crosses its threshold.
    With none -- the offline default -- no reflector is wired on, so reflection
    never fires and the replay is byte-identical. ``main`` supplies one only for a
    non-mock provider.

    Pass an ``out_planner_sources`` dict to collect, per persona, where its plan came
    from (``"llm"`` / ``"static"`` fallback / ``"mock"``) -- an out-parameter so the
    determinism tests' ``simulate(...)`` calls stay unchanged. ``main`` uses it to
    report how many agents the model actually planned vs. fell back.

    Pass an ``out_plans`` dict to collect each persona's generated plan
    (``{name: DailyPlan.to_primitive()}``) so the run can persist it; the exporter
    writes ``personas/<Name>/daily_plan.json`` and ``backend.compare_plans`` reads it
    back without re-calling the model. Also an out-parameter, for the same reason.
    """
    # Default to the module's the_ville cast/builder so existing callers and the
    # determinism tests are unchanged; a different world (e.g. UPenn) passes its
    # own personas + builder. The builder receives the world_map so perception
    # (issue #82) stays tile-distance based.
    personas = personas if personas is not None else PERSONAS
    build_world_fn = build_world_fn if build_world_fn is not None else build_world
    # Cognition defaults (perception radius, conversation pacing) come from the
    # config; None means "today's behavior", i.e. CognitionConfig()'s defaults.
    cog = cognition if cognition is not None else CognitionConfig()

    game, chars = build_world_fn(world_map)
    attach_agents(
        chars,
        personas,
        ledger=ledger,
        embedding_client=embedding_client,
        relationships_csv=relationships_csv,
        base_personas_dir=base_personas_dir,
        vision_r=cog.vision_r,
        planner_client=planner_client,
        reflector_client=reflector_client,
        llm_client=llm_client,
        clock=clock,
        num_steps=num_steps,
        out_planner_sources=out_planner_sources,
        out_plans=out_plans,
    )
    emoji = {p["name"]: p["emoji"] for p in personas}
    order = [p["name"] for p in personas]

    state = {}
    for spec in personas:
        char = chars[spec["name"]]
        state[char.name] = {
            "tile": tuple(spec["start_tile"]),
            "path": [],
            "pron": emoji[char.name],
            "desc": f"waking up @ {char.location.tile_address}",
            "performing": False,
            # The step at which the current activity is done and the agent should
            # move on to its next scheduled stop (None = stay put indefinitely).
            "perform_until": None,
            # Latest reasoning + retrieved-memory block, surfaced on the replay's
            # agent card. They update at each decision point and carry forward on
            # the steps in between (like desc/pron), so the card is never blank.
            "reasoning": "(waking up)",
            "memories": [],
            # Latest dialogue line, surfaced on the replay's agent card (issue
            # #86). None until this agent has a conversation; then it persists
            # (like reasoning/desc) until the next one.
            "chat": None,
        }

    # Conversation is gated on a real brain (issue #86): the deterministic mock
    # brain never produces an utterance, so the default offline run holds no
    # conversations and the replay stays byte-identical. `cooldowns` throttles how
    # often the same pair re-converses across the run.
    conversation_enabled = llm_client is not None
    conversation_cooldowns: dict = {}

    # Heartbeat plumbing (real-brain runs only). A live run makes many blocking
    # API calls per turn with no other output during quiet stretches, which reads
    # as a hang; we emit a one-line pulse per step so progress stays visible.
    heartbeat = default_renderer()
    prev_calls = 0

    frames: list[dict] = []
    for _step in range(num_steps):
        # Give per-agent memory a coherent time axis: the step index is the
        # "turn" memories are stamped and scored against (issue #75). The custom
        # loop never calls end_turn, so without this game.turn would stay 0 and
        # recency could never tell memories apart.
        game.turn = _step
        frame = {}
        for name in order:
            char = chars[name]
            st = state[name]

            # Behind-schedule trigger (design doc §8): a new in-game hour began
            # and this agent is still walking, not yet at its planned stop. Offer
            # its planner a chance to re-plan the tail. Clock-gated, so tests that
            # pass no clock skip it; the mock's revise is a no-op regardless.
            if (
                clock is not None
                and _step > 0
                and st["path"]
                and clock.hour_at(_step) != clock.hour_at(_step - 1)
            ):
                maybe_revise_plan(char, RevisionTrigger(BEHIND_SCHEDULE, _step), clock)

            # Has the current activity run its course? Un-latch and point the brain
            # at the next scheduled stop, so the agent becomes idle below and walks
            # on. When the schedule is exhausted, just stop the timer and let it
            # settle into this last activity for the rest of the run.
            if (
                st["performing"]
                and st["perform_until"] is not None
                and _step >= st["perform_until"]
            ):
                if char.agent.schedule.advance():
                    st["performing"] = False
                st["perform_until"] = None

            # Decision point: idle and not yet settled into an activity.
            if not st["path"] and not st["performing"]:
                # Attribute this LLM call to the persona and step (usage.py).
                ctx = getattr(char.agent.llm_client, "context", None)
                if ctx is not None:
                    ctx.update({"actor": name, "turn": _step, "attempt": 0})
                # Observe (perceive + retrieve memories) -> decide -> remember
                # the outcome, the same shape react_behavior gives engine NPCs.
                # The usage context above is set first so the decide() call
                # inside observe_and_decide is attributed to this persona/step.
                command = observe_and_decide(game, char, _step, retrieval=retrieval)
                # Capture the thinking behind this decision for the replay card:
                # the reasoning the agent produced and the memories it retrieved
                # (stashed on the agent by observe_and_decide). They persist on
                # st until the agent's next decision.
                st["reasoning"] = (
                    getattr(char.agent, "last_reasoning", None) or "(no reasoning)"
                )
                st["memories"] = memories_for_frame(
                    getattr(char.agent, "last_retrieved", None)
                )
                if command and game.parser.parse_command(command, actor=char):
                    remember_outcome(char, command, _step)
                    # Periodic memory synthesis (issue #84): now that this step's
                    # outcome is in memory, reflect if enough importance has
                    # accrued. A no-op unless a reflector was wired on (real
                    # provider only), so the mock replay stays byte-identical.
                    maybe_reflect(char.agent, game)
                    if command.startswith("travel"):
                        dest = char.location
                        address = getattr(dest, "tile_address", None)
                        st["path"] = (
                            world_map.walk_path(st["tile"], address) if address else []
                        )
                        st["pron"] = WALK_EMOJI
                        st["desc"] = f"walking to {dest.name} @ {address}"
                    elif command.startswith("perform"):
                        st["performing"] = True
                        # Per-stop emoji (the schedule may vary it from the
                        # persona's default), falling back to the persona's.
                        st["pron"] = char.agent.schedule.emoji or emoji[name]
                        activity = char.get_property("activity") or "spending time"
                        st["desc"] = f"{activity} @ {char.location.tile_address}"
                        # Schedule the move on to the next stop. None steps means
                        # "stay" -- the agent settles here for the rest of the run.
                        duration = char.agent.schedule.steps
                        st["perform_until"] = (
                            _step + duration if duration is not None else None
                        )
                elif command:
                    # The agent chose a command but it failed the precondition
                    # gate. Offer its planner a chance to re-plan around the
                    # blocked action (design doc §8). The mock never lands here --
                    # its travel/perform are always legal -- so this stays
                    # byte-identical; it's the seam a real planner needs.
                    reason = getattr(game.parser, "last_fail_message", "") or command
                    maybe_revise_plan(
                        char, RevisionTrigger(ACTION_FAILED, _step, reason), clock
                    )

            # Advance one tile along any active walk.
            if st["path"]:
                st["tile"] = st["path"].pop(0)

            frame[name] = {
                "movement": [int(st["tile"][0]), int(st["tile"][1])],
                "pronunciatio": st["pron"],
                "description": st["desc"],
                # The agent's latest dialogue line (issue #86), or None. Updated
                # below by maybe_converse for any pair that talks this step.
                "chat": st["chat"],
                # Reasoning + retrieved memories for this agent's card (the
                # exporter writes the frame verbatim, so these flow straight into
                # movement/<step>.json for the replay to render).
                "reasoning": st["reasoning"],
                "memories": st["memories"],
            }

        # Conversation (issue #86): after everyone has moved, let co-located,
        # settled residents talk. Each meeting writes dialogue into both agents'
        # memory streams and updates their cards' chat line. Gated + a no-op for
        # the mock brain, so the default replay is unchanged.
        chats_this_step = 0
        if conversation_enabled:
            chats_this_step = maybe_converse(
                game,
                chars,
                state,
                frame,
                _step,
                conversation_cooldowns,
                order,
                cooldown_steps=cog.conversation_cooldown_steps,
                max_exchanges=cog.conversation_max_exchanges,
            )
        frames.append(frame)

        # Per-turn heartbeat: stdout only, so it never touches the exported
        # frames -- the mock replay stays byte-identical. Gated on a real client
        # because that is the only run slow enough to look stalled.
        if llm_client is not None:
            total_calls = ledger.summary()["calls"] if ledger else 0
            delta = total_calls - prev_calls
            prev_calls = total_calls
            when = (
                clock.time_at(_step).strftime("%H:%M:%S")
                if clock is not None
                else f"step {_step}"
            )
            chat_note = f" · {chats_this_step} chat(s)" if chats_this_step else ""
            heartbeat.emit(
                Message(
                    Channel.SYSTEM,
                    f"Turn {_step + 1}/{num_steps} · {when} · "
                    f"+{delta} LLM calls ({total_calls} total){chat_note}",
                )
            )

    # Hand back each agent's complete memory stream, if the caller asked for it.
    if out_memories is not None:
        for name in order:
            out_memories[name] = memory_stream_for_persona(chars[name].agent)

    return frames


def _print_cost_summary(ledger: UsageLedger, renderer=None) -> None:
    """Print a per-agent LLM cost summary through the engine's renderer seam
    (reporting.py), so it formats consistently with the rest of the engine's
    output. With the mock brain every line is $0.0000 -- the plumbing is what's
    delivered; real numbers appear once a live client is wired in."""
    renderer = renderer or default_renderer()
    summary = ledger.summary()
    renderer.emit(
        Message(
            Channel.SYSTEM,
            f"LLM cost: ${summary['total_cost_usd']:.4f} over "
            f"{summary['calls']} calls "
            f"({summary['input_tokens']} in / {summary['output_tokens']} out tokens)",
        )
    )
    for actor, cost in sorted(
        ledger.totals_by_actor().items(), key=lambda kv: kv[1], reverse=True
    ):
        renderer.emit(Message(Channel.SYSTEM, f"  {actor}: ${cost:.4f}"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Smallville replay.")
    # The run-time flags default to None so a value set in --config (or its
    # SimulationConfig defaults) is only overridden when the flag is given
    # explicitly. The documented default below is SimulationRuntimeConfig's.
    parser.add_argument(
        "--steps",
        type=int,
        default=None,
        help=f"number of steps to simulate (default: {DEFAULT_STEPS} = 3 hours at "
        "10s/step, unless set in --config)",
    )
    parser.add_argument(
        "--start",
        type=_parse_start,
        default=None,
        metavar="ISO_DATETIME",
        help="in-game start time, ISO format (default: 2023-02-13 08:00:00, "
        "unless set in --config)",
    )
    parser.add_argument(
        "--sec-per-step",
        type=int,
        default=None,
        help=f"seconds of in-game time per step (default: {exporter.SEC_PER_STEP}, "
        "unless set in --config)",
    )
    parser.add_argument("--sim-code", default=None)
    parser.add_argument("--ville-dir", default=DEFAULT_VILLE_DIR)
    parser.add_argument("--storage", default=DEFAULT_STORAGE)
    parser.add_argument("--base-sim", default=None)
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=None,
        help="SimulationConfig YAML/JSON file: run-time (simulation), memory "
        "(retrieval), embedding, and engine (game: ...) sections. Falls back to "
        "SimulationConfig.from_env() when omitted; explicit CLI flags still win.",
    )
    parser.add_argument(
        "--llm-log",
        metavar="DIR",
        default=None,
        help="write a per-run JSONL usage log here, overriding the config's "
        "observability.log_path (off if neither is set)",
    )
    parser.add_argument(
        "--llm-log-prompts",
        action="store_true",
        help="include full prompts/responses in the usage log (default: numbers only)",
    )
    parser.add_argument(
        "--embeddings",
        nargs="?",
        const="local",
        default=None,
        metavar="PROVIDER",
        help="score memory relevance semantically via an embedding backend "
        "(local | mock | sentence-transformers | openai). Bare --embeddings uses "
        "'local' (model2vec; needs `uv sync --extra embeddings`). Omit it for "
        "keyword-overlap relevance, the offline default (EMBEDDING_PROVIDER is "
        "honored when this flag is absent). The mock brain ignores retrieved "
        "memories, so the replay is byte-identical either way -- run "
        "`python -m backend.compare_retrieval` to compare retrieval directly.",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.ville_dir):
        raise SystemExit(
            f"Maze assets not found at {args.ville_dir}.\n"
            "Run ./setup.sh first to populate generative-agents/frontend/."
        )

    world_map = WorldMap(args.ville_dir)
    print(f"Loaded the_ville ({world_map.width}x{world_map.height}).")

    # Load the global SimulationConfig: from --config (a YAML/JSON file) or, when
    # omitted, from the environment. It composes the engine's GameConfig (the
    # `game:` section -> LLM, observability, ...) and adds the sim's run-time and
    # memory-retrieval knobs. Explicit CLI flags below still take precedence.
    sim = (
        SimulationConfig.from_file(args.config)
        if args.config
        else SimulationConfig.from_env()
    )
    # Explicit usage-log flags override the config's observability section.
    if args.llm_log:
        sim.game.observability.log_path = args.llm_log
    if args.llm_log_prompts:
        sim.game.observability.log_prompts = True

    # Semantic memory relevance (issue #102): the --embeddings flag (else
    # EMBEDDING_PROVIDER) selects a backend, degrading to keyword overlap when
    # none is set or installable. When neither flag nor env is given, a config-file
    # `embedding:` section is the last-resort source. The mock brain ignores the
    # retrieved block, so this never changes the exported replay -- it's the seam a
    # real LLM brain would reason over (NEXT-STEPS Phase A); compare_retrieval.py
    # shows the diff.
    embedding_client = resolve_embedding_client(args.embeddings)
    if (
        embedding_client is None
        and args.embeddings is None
        and not os.environ.get("EMBEDDING_PROVIDER")
        and sim.embedding is not None
    ):
        try:
            embedding_client = create_embedding_client(sim.embedding)
        except (ImportError, ValueError) as e:
            print(
                f"Warning: could not create embedding client from config ({e}); "
                "falling back to keyword-overlap relevance."
            )
    relevance_mode = (
        f"semantic ({type(embedding_client).__name__})"
        if embedding_client is not None
        else "keyword overlap (no embedding client)"
    )
    print(f"Memory retrieval relevance: {relevance_mode}.")

    # Resolve the run-time knobs: an explicit CLI flag wins, else the config's
    # value (from --config, or SimulationConfig's defaults).
    steps = args.steps if args.steps is not None else sim.simulation.steps
    sec_per_step = (
        args.sec_per_step
        if args.sec_per_step is not None
        else sim.simulation.sec_per_step
    )
    sim_code = args.sim_code if args.sim_code is not None else sim.simulation.sim_code
    base_sim = args.base_sim if args.base_sim is not None else sim.simulation.base_sim
    start_dt = (
        args.start if args.start is not None else _parse_start(sim.simulation.start)
    )
    # How many residents actually run (config only -- no CLI flag). Slice the full
    # roster so the cast and the world are built from the *same* personas.
    active_personas = ALL_PERSONAS[: sim.simulation.num_agents]

    # The t=0 seed assets (issue #79): the relationships CSV sits beside the maze
    # under --ville-dir, and each persona's partial known-places tree lives in its
    # bootstrap_memory under the base sim. Both feed attach_agents via simulate;
    # base_personas is reused below for the exporter's persona-memory copy.
    relationships_csv = os.path.join(args.ville_dir, "agent_history_init_n25.csv")
    base_personas = os.path.join(args.storage, base_sim, "personas")

    # The LLM brain (NEXT-STEPS Phase A), gated by LLM_PROVIDER exactly like the
    # engine's client_from_env: "anthropic"/"openai" build a real client; unset or
    # "mock" -> None, so the deterministic SmallvilleMockClient stays the brain and
    # the offline replay is byte-identical. The one client drives both the
    # per-step travel/perform decisions and daily planning (LLMPlanner).
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    model = os.environ.get("LLM_MODEL")

    # Shared usage ledger across all personas, streamed to the run's JSONL
    # artifact. With the mock brain every line is $0; a real brain records into
    # this same ledger (created with it below), so the cost summary stays accurate.
    ledger = UsageLedger()
    run_log = sim.game.build_run_log(
        provider=provider or "mock",
        model=model or "mock",
        turn_mode="simultaneous",
    )

    llm_client = None
    if provider and provider != "mock":
        try:
            llm_client = create_llm_client(
                LlmConfig(
                    provider=provider,
                    api_key=os.environ.get("LLM_API_KEY"),
                    model=model,
                    base_url=os.environ.get("LLM_BASE_URL"),
                    verbose=os.environ.get("LLM_VERBOSE", "").lower() in ("1", "true"),
                ),
                ledger=ledger,
            )
        except (ImportError, ValueError) as e:
            print(
                f"Warning: could not create LLM client ({e}); "
                "using the deterministic mock brain + static schedule."
            )
    print(
        f"LLM brain: {provider} -- travel/perform decisions + daily planning "
        "+ periodic reflection + conversation."
        if llm_client is not None
        else "LLM brain: none -- deterministic mock decisions + static schedule."
    )

    # Collect every agent's full memory stream alongside the frames, so the
    # exporter can give the State Details panel the complete history (not just
    # the per-step retrieved set the cards show).
    memory_streams: dict = {}
    # Where each agent's daily plan came from (llm / static fallback / mock), so we
    # can report whether the model actually planned every agent or some fell back.
    planner_sources: dict = {}
    # Each agent's generated plan, persisted by the exporter as daily_plan.json.
    plans: dict = {}
    # One clock for the run, shared by the loop's revision triggers (issue #83):
    # built from the same --start / --sec-per-step the exporter stamps frames
    # with, so plan time and replay time agree.
    clock = SimClock(args.start, args.sec_per_step)
    with run_log or nullcontext():
        if run_log is not None:
            run_log.attach(ledger)
        frames = simulate(
            world_map,
            steps,
            ledger=ledger,
            embedding_client=embedding_client,
            retrieval=sim.retrieval,
            cognition=sim.cognition,
            relationships_csv=relationships_csv,
            base_personas_dir=base_personas,
            out_memories=memory_streams,
            personas=active_personas,
            build_world_fn=lambda wm: build_world(wm, active_personas),
            clock=clock,
            llm_client=llm_client,
            planner_client=llm_client,
            reflector_client=llm_client,
            out_planner_sources=planner_sources,
            out_plans=plans,
        )
    print(f"Simulated {len(frames)} steps for {len(active_personas)} agents.")
    if llm_client is not None:
        via_llm = sorted(n for n, s in planner_sources.items() if s == "llm")
        fell_back = sorted(n for n, s in planner_sources.items() if s == "static")
        msg = f"Daily plans: {len(via_llm)} generated by the model"
        if fell_back:
            msg += (
                f", {len(fell_back)} fell back to the static schedule "
                f"({', '.join(fell_back)})"
            )
        print(msg + ".")
    _print_cost_summary(ledger)
    if run_log is not None:
        print(f"Wrote usage log to {run_log.path}")

    start_tiles = {p["name"]: tuple(p["start_tile"]) for p in active_personas}
    sim_dir = exporter.write_simulation(
        storage_root=args.storage,
        sim_code=sim_code,
        frames=frames,
        start_dt=start_dt,
        start_tiles=start_tiles,
        base_personas_dir=base_personas,
        sec_per_step=sec_per_step,
        memory_streams=memory_streams,
        plans=plans,
    )
    print(f"Wrote simulation to {sim_dir}")
    print(
        "Start the frontend, then open:\n"
        f"  http://localhost:8000/replay/{sim_code}/0/"
    )


if __name__ == "__main__":
    main()
