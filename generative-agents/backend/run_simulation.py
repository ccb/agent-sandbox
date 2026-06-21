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

Run it (from the ``generative-agents`` directory; ``uv run`` finds the repo's
project env that has the engine installed)::

    uv run python -m backend.run_simulation            # 3 hours (1080 steps)
    uv run python -m backend.run_simulation --steps 120
    uv run python -m backend.run_simulation --start "2023-02-13 18:00:00"
    uv run python -m backend.run_simulation --sec-per-step 60   # 1 min/step
"""

import argparse
import datetime
import os
from contextlib import nullcontext

from text_adventure_games.config import GameConfig
from text_adventure_games.embedding_client import (
    EmbeddingConfig,
    create_embedding_client,
    embedding_client_from_env,
)
from text_adventure_games.reporting import Channel, Message, default_renderer
from text_adventure_games.usage import UsageLedger

from . import exporter
from .build_world import PERSONAS, build_world
from .smallville_agents import (
    attach_agents,
    memories_for_frame,
    observe_and_decide,
    remember_outcome,
)
from .world_map import WorldMap

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_GA_DIR = os.path.dirname(_BACKEND_DIR)
_FRONTEND = os.path.join(_GA_DIR, "frontend")

DEFAULT_VILLE_DIR = os.path.join(_FRONTEND, "static_dirs", "assets", "the_ville")
DEFAULT_STORAGE = os.path.join(_FRONTEND, "storage")
# The 25-resident base sim: the backend reuses its persona memory (copied into
# each generated sim so the frontend's click-a-persona state panel has something
# to show). setup.sh copies it into frontend/storage/.
DEFAULT_BASE_SIM = "base_the_ville_n25"
DEFAULT_SIM_CODE = "mock_the_ville_n25"

# 3 hours of in-game time at 10 seconds per step (8-11am): long enough for each
# agent to work through its daily schedule of stops, so memory keeps growing
# across the run instead of freezing after the first activity.
DEFAULT_STEPS = 1080
# Start at 8am: the town is waking, the cafe opens, students head out -- a lively
# hour. (The base sim starts at midnight, when everyone is asleep.)
DEFAULT_START_DT = datetime.datetime(2023, 2, 13, 8, 0, 0)

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
    relationships_csv: str | None = None,
    base_personas_dir: str | None = None,
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

    Pass ``relationships_csv`` / ``base_personas_dir`` (the upstream bootstrap
    assets) to seed each persona at t=0 -- relationships into memory, partial
    known-places into knowledge (issue #79, via :func:`attach_agents`). Both are
    optional: tests call ``simulate`` without them and stay byte-identical, while
    a real run (:func:`main`) points them at ``frontend/``.
    """
    game, chars = build_world()
    attach_agents(
        chars,
        PERSONAS,
        ledger=ledger,
        embedding_client=embedding_client,
        relationships_csv=relationships_csv,
        base_personas_dir=base_personas_dir,
    )
    emoji = {p["name"]: p["emoji"] for p in PERSONAS}
    order = [p["name"] for p in PERSONAS]

    state = {}
    for spec in PERSONAS:
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
        }

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

            # Has the current activity run its course? Un-latch and point the brain
            # at the next scheduled stop, so the agent becomes idle below and walks
            # on. When the schedule is exhausted, just stop the timer and let it
            # settle into this last activity for the rest of the run.
            if (
                st["performing"]
                and st["perform_until"] is not None
                and _step >= st["perform_until"]
            ):
                if char.agent.llm_client.advance():
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
                command = observe_and_decide(game, char, _step)
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
                        st["pron"] = char.agent.llm_client.emoji or emoji[name]
                        activity = char.get_property("activity") or "spending time"
                        st["desc"] = f"{activity} @ {char.location.tile_address}"
                        # Schedule the move on to the next stop. None steps means
                        # "stay" -- the agent settles here for the rest of the run.
                        duration = char.agent.llm_client.steps
                        st["perform_until"] = (
                            _step + duration if duration is not None else None
                        )

            # Advance one tile along any active walk.
            if st["path"]:
                st["tile"] = st["path"].pop(0)

            frame[name] = {
                "movement": [int(st["tile"][0]), int(st["tile"][1])],
                "pronunciatio": st["pron"],
                "description": st["desc"],
                "chat": None,
                # Reasoning + retrieved memories for this agent's card (the
                # exporter writes the frame verbatim, so these flow straight into
                # movement/<step>.json for the replay to render).
                "reasoning": st["reasoning"],
                "memories": st["memories"],
            }
        frames.append(frame)

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
    parser.add_argument(
        "--steps",
        type=int,
        default=DEFAULT_STEPS,
        help="number of steps to simulate (default: %(default)s = 3 hours at 10s/step)",
    )
    parser.add_argument(
        "--start",
        type=_parse_start,
        default=DEFAULT_START_DT,
        metavar="ISO_DATETIME",
        help="in-game start time, ISO format (default: 2023-02-13 08:00:00)",
    )
    parser.add_argument(
        "--sec-per-step",
        type=int,
        default=exporter.SEC_PER_STEP,
        help="seconds of in-game time per step (default: %(default)s)",
    )
    parser.add_argument("--sim-code", default=DEFAULT_SIM_CODE)
    parser.add_argument("--ville-dir", default=DEFAULT_VILLE_DIR)
    parser.add_argument("--storage", default=DEFAULT_STORAGE)
    parser.add_argument("--base-sim", default=DEFAULT_BASE_SIM)
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=None,
        help="GameConfig YAML/JSON file; its 'observability' section sets the "
        "usage log (falls back to GameConfig.from_env() when omitted)",
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

    # Semantic memory relevance (issue #102): the --embeddings flag (else
    # EMBEDDING_PROVIDER) selects a backend, degrading to keyword overlap when
    # none is set or installable. The mock brain ignores the retrieved block, so
    # this never changes the exported replay -- it's the seam a real LLM brain
    # would reason over (NEXT-STEPS Phase A); compare_retrieval.py shows the diff.
    embedding_client = resolve_embedding_client(args.embeddings)
    relevance_mode = (
        f"semantic ({type(embedding_client).__name__})"
        if embedding_client is not None
        else "keyword overlap (no embedding client)"
    )
    print(f"Memory retrieval relevance: {relevance_mode}.")

    # Observability follows the global GameConfig: load it from --config (or the
    # environment), then let the explicit CLI flags override its observability
    # section. The config builds the per-run JSONL artifact, so the sim honors a
    # log_path set anywhere a GameConfig can come from (file, env, or flag).
    config = GameConfig.from_file(args.config) if args.config else GameConfig.from_env()
    if args.llm_log:
        config.observability.log_path = args.llm_log
    if args.llm_log_prompts:
        config.observability.log_prompts = True

    # The t=0 seed assets (issue #79): the relationships CSV sits beside the maze
    # under --ville-dir, and each persona's partial known-places tree lives in its
    # bootstrap_memory under the base sim. Both feed attach_agents via simulate;
    # base_personas is reused below for the exporter's persona-memory copy.
    relationships_csv = os.path.join(args.ville_dir, "agent_history_init_n25.csv")
    base_personas = os.path.join(args.storage, args.base_sim, "personas")

    # Shared usage ledger across all personas; optionally streamed to the run's
    # JSONL artifact. The mock brain records $0, but the accounting is ready for
    # when a real client lands (NEXT-STEPS Phase A).
    ledger = UsageLedger()
    run_log = config.build_run_log(
        provider="mock", model="mock", turn_mode="simultaneous"
    )
    with run_log or nullcontext():
        if run_log is not None:
            run_log.attach(ledger)
        frames = simulate(
            world_map,
            args.steps,
            ledger=ledger,
            embedding_client=embedding_client,
            relationships_csv=relationships_csv,
            base_personas_dir=base_personas,
        )
    print(f"Simulated {len(frames)} steps for {len(PERSONAS)} agents.")
    _print_cost_summary(ledger)
    if run_log is not None:
        print(f"Wrote usage log to {run_log.path}")

    start_tiles = {p["name"]: tuple(p["start_tile"]) for p in PERSONAS}
    sim_dir = exporter.write_simulation(
        storage_root=args.storage,
        sim_code=args.sim_code,
        frames=frames,
        start_dt=args.start,
        start_tiles=start_tiles,
        base_personas_dir=base_personas,
        sec_per_step=args.sec_per_step,
    )
    print(f"Wrote simulation to {sim_dir}")
    print(
        "Start the frontend, then open:\n"
        f"  http://localhost:8000/replay/{args.sim_code}/0/"
    )


if __name__ == "__main__":
    main()
