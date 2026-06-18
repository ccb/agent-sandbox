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

    uv run python -m backend.run_simulation            # 1 hour (360 steps)
    uv run python -m backend.run_simulation --steps 120
    uv run python -m backend.run_simulation --start "2023-02-13 18:00:00"
    uv run python -m backend.run_simulation --sec-per-step 60   # 1 min/step
"""

import argparse
import datetime
import os
from contextlib import nullcontext

from text_adventure_games.reporting import Channel, Message, default_renderer
from text_adventure_games.usage import RunLog, UsageLedger

from . import exporter
from .build_world import PERSONAS, build_world
from .smallville_agents import attach_agents
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

# 1 hour of in-game time at 10 seconds per step.
DEFAULT_STEPS = 360
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


def simulate(
    world_map: WorldMap, num_steps: int, ledger: UsageLedger | None = None
) -> list[dict]:
    """Run the simulation and return one movement frame per step.

    Each frame is ``{persona_name: {movement, pronunciatio, description, chat}}``.
    Builds its own game + agents, so it is self-contained and easy to test.

    Pass a shared ``ledger`` to accumulate per-agent LLM token/cost accounting
    across the run (usage.py); the mock brain records zero cost, so the numbers
    are $0 until a real client is wired in (NEXT-STEPS Phase A).
    """
    game, chars = build_world()
    attach_agents(chars, PERSONAS, ledger=ledger)
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
        }

    frames: list[dict] = []
    for _step in range(num_steps):
        frame = {}
        for name in order:
            char = chars[name]
            st = state[name]

            # Decision point: idle and not yet settled into an activity.
            if not st["path"] and not st["performing"]:
                # Attribute this LLM call to the persona and step (usage.py).
                ctx = getattr(char.agent.llm_client, "context", None)
                if ctx is not None:
                    ctx.update({"actor": name, "turn": _step, "attempt": 0})
                command = char.agent.decide(game.describe_for(char))
                if command and game.parser.parse_command(command, actor=char):
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
                        st["pron"] = emoji[name]
                        activity = char.get_property("activity") or "spending time"
                        st["desc"] = f"{activity} @ {char.location.tile_address}"

            # Advance one tile along any active walk.
            if st["path"]:
                st["tile"] = st["path"].pop(0)

            frame[name] = {
                "movement": [int(st["tile"][0]), int(st["tile"][1])],
                "pronunciatio": st["pron"],
                "description": st["desc"],
                "chat": None,
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
        help="number of steps to simulate (default: %(default)s = 1 hour at 10s/step)",
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
        "--llm-log",
        metavar="DIR",
        default=None,
        help="write a per-run JSONL usage log to this directory (off if unset)",
    )
    parser.add_argument(
        "--llm-log-prompts",
        action="store_true",
        help="include full prompts/responses in the usage log (default: numbers only)",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.ville_dir):
        raise SystemExit(
            f"Maze assets not found at {args.ville_dir}.\n"
            "Run ./setup.sh first to populate generative-agents/frontend/."
        )

    world_map = WorldMap(args.ville_dir)
    print(f"Loaded the_ville ({world_map.width}x{world_map.height}).")

    # Shared usage ledger across all personas; optionally streamed to a per-run
    # JSONL artifact. The mock brain records $0, but the accounting is ready for
    # when a real client lands (NEXT-STEPS Phase A).
    ledger = UsageLedger()
    if args.llm_log:
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = os.path.join(args.llm_log, f"{ts}-mock.jsonl")
        run_log_cm = RunLog(
            log_path,
            provider="mock",
            model="mock",
            turn_mode="simultaneous",
            log_prompts=args.llm_log_prompts,
        )
    else:
        log_path = None
        run_log_cm = nullcontext()

    with run_log_cm as run_log:
        if run_log is not None:
            run_log.attach(ledger)
        frames = simulate(world_map, args.steps, ledger=ledger)
    print(f"Simulated {len(frames)} steps for {len(PERSONAS)} agents.")
    _print_cost_summary(ledger)
    if log_path:
        print(f"Wrote usage log to {log_path}")

    start_tiles = {p["name"]: tuple(p["start_tile"]) for p in PERSONAS}
    base_personas = os.path.join(args.storage, args.base_sim, "personas")
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
