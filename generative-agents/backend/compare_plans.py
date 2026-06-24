"""Compare a persona's static schedule with an LLM-generated daily plan (issue #83).

Daily planning, like memory retrieval before it (``compare_retrieval.py``), doesn't
change the *replay* until a real model is in the loop: the offline default uses
:class:`~backend.planner.MockPlanner`, which replays the authored ``world_data.yaml``
schedule, so the exported frames stay byte-identical. The payoff -- a day that
*emerges* from identity + memory rather than being hand-typed -- only appears once a
real ``LlmClient`` drives :class:`~backend.planner.LLMPlanner` (NEXT-STEPS Phase A).

This tool makes that difference visible *before* the sim wires the LLM brain in: it
prints the static schedule beside the model's generated day for one resident, so you
can eyeball whether generation produces something sensible (and differently shaped)
for that persona. It is a **manual research tool**, not part of the replay pipeline
or CI -- it needs no maze assets (``build_world`` alone) and, without a provider, it
just shows the static plan and says what to set.

    # Static plan only (no provider configured):
    uv run python -m backend.compare_plans --resident "Isabella Rodriguez"

    # Generated plan too (a real model; see README for keys):
    LLM_PROVIDER=anthropic uv run python -m backend.compare_plans \
        --resident "Klaus Mueller"
"""

import argparse

from text_adventure_games.llm_client import client_from_env

from .build_world import LOCATION_NAMES, PERSONAS, build_world
from .planner import LLMPlanner, MockPlanner
from .smallville_agents import attach_agents


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident", default=PERSONAS[0]["name"])
    args = parser.parse_args()

    spec = _persona(args.resident)
    # Build the agent so a generative planner has the same seeded t=0 memory the
    # sim would give it (relationships are skipped here -- no bootstrap assets).
    _, chars = build_world()
    attach_agents(chars, [spec])
    memory = chars[spec["name"]].agent.memory

    print(f"Resident: {spec['name']}")
    _print_plan("Static (MockPlanner)", MockPlanner(spec).generate())

    client = client_from_env()
    if client is None:
        print(
            "\nNo LLM provider configured -- set LLM_PROVIDER (anthropic|openai) to "
            "generate a plan to compare. Showing the static plan only."
        )
        return
    generated = LLMPlanner(client, LOCATION_NAMES).generate(persona=spec, memory=memory)
    _print_plan(f"Generated (LLMPlanner via {client.__class__.__name__})", generated)


if __name__ == "__main__":
    main()
