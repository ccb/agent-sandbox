"""Show a persona's static schedule beside its generated daily plan (issue #83).

Daily planning, like memory retrieval before it (``compare_retrieval.py``), doesn't
change the *replay* until a real model is in the loop: the offline default uses
:class:`~gen_agents.planner.MockPlanner`, which replays the authored ``world_data.yaml``
schedule, so the exported frames stay byte-identical. The payoff -- a day that
*emerges* from identity + memory rather than being hand-typed -- only appears once a
real ``LlmClient`` drives :class:`~gen_agents.planner.LLMPlanner`.

This tool makes that difference visible. By default it reads the plan the **last
run already generated and saved** (``personas/<Name>/daily_plan.json``) -- fast,
free, and faithful to what the run actually used:

    uv run python -m gen_agents.run_simulation --steps 120   # with LLM_PROVIDER set
    uv run python -m gen_agents.compare_plans --resident "Klaus Mueller"

Pass ``--generate`` to instead make a *fresh* plan with the live model right now
(3 model calls: day -> hourly -> minute; nondeterministic, costs tokens) -- useful
when you haven't run the sim, or want to see generation in isolation:

    LLM_PROVIDER=anthropic uv run python -m gen_agents.compare_plans \
        --resident "Klaus Mueller" --generate

It is a manual research tool, not part of the replay pipeline or CI.
"""

import argparse
import datetime
import json
import os

from text_adventure_games.llm_client import client_from_env
from text_adventure_games.planning import DailyPlan

from .build_world import LOCATION_NAMES, PERSONAS, build_world
from .planner import LLMPlanner, MockPlanner
from .sim_clock import SimClock
from .smallville_agents import attach_agents

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_STORAGE = os.path.join(os.path.dirname(_BACKEND_DIR), "frontend", "storage")
_DEFAULT_SIM_CODE = "mock_the_ville_n25"
# Match run_simulation's defaults so a --generate plan reflects what a real run
# would produce (in particular, bounded to the run's clock window).
_DEFAULT_START = datetime.datetime(2023, 2, 13, 8, 0, 0)
_DEFAULT_STEPS = 1080
_DEFAULT_SEC_PER_STEP = 10


def _persona(name: str) -> dict:
    for spec in PERSONAS:
        if spec["name"] == name:
            return spec
    choices = ", ".join(p["name"] for p in PERSONAS)
    raise SystemExit(f"Unknown resident {name!r}. Choose from: {choices}")


def _print_plan(title: str, plan) -> None:
    print(f"\n=== {title} ===")
    if plan.day:
        print("Day outline:")
        for block in plan.day:
            print(f"  - {block.label}: {block.summary}")
    if plan.hours:
        print("Hourly:")
        for hour in plan.hours:
            print(f"  - {hour.start_hour:02d}:00  {hour.summary}")
    print("Stops:")
    for stop in plan.stops:
        steps = "stay" if stop.steps is None else f"{stop.steps} steps"
        print(f"  - {stop.place}: {stop.activity} ({steps})")


def _generate(spec: dict, args) -> None:
    """Make a fresh plan with the live model, bounded to the run window."""
    client = client_from_env()
    if client is None:
        print(
            "\nNo LLM provider configured -- set LLM_PROVIDER (anthropic|openai) "
            "to generate a plan. Showing the static plan only."
        )
        return
    # Same seeded t=0 memory the sim would give the agent (relationships skipped --
    # no bootstrap assets here).
    _, chars = build_world()
    attach_agents(chars, [spec])
    memory = chars[spec["name"]].agent.memory
    clock = SimClock(args.start, args.sec_per_step)
    window = f"{clock.time_at(0):%H:%M}-{clock.time_at(args.steps):%H:%M}"
    print(f"\nGenerating a fresh plan for the {window} window (3 live model calls)...")
    generated = LLMPlanner(
        client, LOCATION_NAMES, clock=clock, num_steps=args.steps
    ).generate(persona=spec, memory=memory)
    _print_plan(f"Generated (fresh, via {client.__class__.__name__})", generated)


def _from_saved(spec: dict, args) -> None:
    """Read the plan the last run saved -- no model calls."""
    path = os.path.join(
        args.storage, args.sim_code, "personas", spec["name"], "daily_plan.json"
    )
    if not os.path.isfile(path):
        print(
            f"\nNo saved plan at {path}.\n"
            "Run `python -m gen_agents.run_simulation` (with LLM_PROVIDER set) to "
            "generate and save one, or pass --generate to make a fresh plan now."
        )
        return
    with open(path, encoding="utf-8") as f:
        plan = DailyPlan.from_primitive(json.load(f))
    _print_plan(f"Generated (saved by the last run: {args.sim_code})", plan)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident", default=PERSONAS[0]["name"])
    parser.add_argument("--storage", default=_DEFAULT_STORAGE)
    parser.add_argument("--sim-code", default=_DEFAULT_SIM_CODE)
    parser.add_argument(
        "--generate",
        action="store_true",
        help="ignore any saved plan and generate a fresh one with the live model "
        "(3 model calls; nondeterministic, costs tokens)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=_DEFAULT_STEPS,
        help="(--generate) run length the plan is bounded to (default: %(default)s)",
    )
    parser.add_argument(
        "--start",
        type=datetime.datetime.fromisoformat,
        default=_DEFAULT_START,
        metavar="ISO_DATETIME",
        help="(--generate) in-game start time (default: 2023-02-13 08:00:00)",
    )
    parser.add_argument("--sec-per-step", type=int, default=_DEFAULT_SEC_PER_STEP)
    args = parser.parse_args()

    spec = _persona(args.resident)
    print(f"Resident: {spec['name']}")
    _print_plan("Static (MockPlanner)", MockPlanner(spec).generate())

    if args.generate:
        _generate(spec, args)
    else:
        _from_saved(spec, args)


if __name__ == "__main__":
    main()
