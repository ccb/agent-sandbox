"""End-to-end smoke test of the live-LLM brain + planner (issue #78 / Phase A).

Unlike ``run_simulation``, this needs **no maze assets** and writes **no replay**:
it builds the world, generates each agent's day with a real ``LLMPlanner``, and
runs a handful of real travel/perform decisions through the precondition gate --
just enough to shake out prompt / parsing / latency issues with a live model
before committing to a full run. It is a manual tool, not part of CI.

    LLM_PROVIDER=anthropic uv run python -m gen_agents.smoke_llm
    LLM_PROVIDER=openai LLM_MODEL=gpt-4o-mini \
        uv run python -m gen_agents.smoke_llm --agents 2 --steps 6

With no provider configured it exits with a clear message rather than doing
anything, so it is safe to run by accident.
"""

import argparse
import os

from text_adventure_games.llm_client import client_from_env

from .build_world import PERSONAS, build_world
from .smallville_agents import attach_agents, observe_and_decide, remember_outcome


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live-LLM smoke test (no maze assets, no replay export)."
    )
    parser.add_argument(
        "--agents",
        type=int,
        default=2,
        help="how many personas to exercise (default: %(default)s; keeps cost low)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=6,
        help="decision rounds per agent (default: %(default)s)",
    )
    args = parser.parse_args()

    # The whole point is to hit a real model, so reject the unset/mock cases
    # loudly rather than silently exercising the deterministic stand-in (whose
    # call_tool is the Action-Castle brain, not Smallville's).
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if provider in ("", "mock"):
        raise SystemExit(
            "This smoke test needs a real model. Set LLM_PROVIDER=anthropic|openai "
            "and the matching API key (ANTHROPIC_API_KEY / OPENAI_API_KEY or "
            "LLM_API_KEY), then re-run. (For the offline mock, use run_simulation.) "
            "See the README's 'Trying it with a live LLM' section."
        )
    # client_from_env reads LLM_PROVIDER (+ key); None means it couldn't be built.
    client = client_from_env()
    if client is None:
        raise SystemExit(
            f"Could not build an LLM client for provider {provider!r}; check the "
            "API key and `uv sync --extra llm`."
        )
    print(f"Using {client.__class__.__name__}.\n")

    game, chars = build_world()
    personas = PERSONAS[: max(1, args.agents)]

    # Planning: attach_agents generates each agent's day with the live model
    # (LLMPlanner) when planner_client is set. Print the result so a hallucinated
    # or empty plan is obvious (an empty plan falls back to the static schedule).
    print(f"Generating plans for {len(personas)} agent(s) with the live model...")
    attach_agents(chars, personas, llm_client=client, planner_client=client)
    for spec in personas:
        agent = chars[spec["name"]].agent
        print(f"\n[{spec['name']}] plan via {type(agent.planner).__name__}:")
        for stop in agent.plan.stops:
            dur = "stay" if stop.steps is None else f"{stop.steps} steps"
            print(f"    -> {stop.place}: {stop.activity} ({dur})")

    # Decisions: run the real brain through the precondition gate a few times.
    # Reports per decision whether the model's command parsed -- the usual failure
    # is a travel target that isn't a known location (printed with the gate's
    # reason), which is exactly what this smoke test exists to surface.
    print("\nRunning decisions through the precondition gate:")
    passed = failed = 0
    for step in range(args.steps):
        for spec in personas:
            char = chars[spec["name"]]
            command = observe_and_decide(game, char, step)
            ok = bool(command) and game.parser.parse_command(command, actor=char)
            if ok:
                passed += 1
                remember_outcome(char, command, step)
                print(f"  step {step} {spec['name']}: {command!r} -> ok")
            else:
                failed += 1
                why = getattr(game.parser, "last_fail_message", "") or "no command"
                print(f"  step {step} {spec['name']}: {command!r} -> FAILED ({why})")

    print(f"\nDone: {passed} decision(s) passed the gate, {failed} failed.")
    ledger = getattr(client, "ledger", None)
    if ledger is not None:
        s = ledger.summary()
        print(
            f"LLM cost: ${s['total_cost_usd']:.4f} over {s['calls']} calls "
            f"({s['input_tokens']} in / {s['output_tokens']} out tokens)."
        )


if __name__ == "__main__":
    main()
