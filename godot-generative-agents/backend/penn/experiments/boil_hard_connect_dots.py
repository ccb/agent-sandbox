"""A harder connect-the-dots variant of #595's boil_from_memory experiment:
does a live LLM figure out it needs to LEAVE the room to find a stove?

Sibling of ``boil_from_memory.py``, reusing its persona config (``_configure``,
the seeded ``_AVERSION`` memory) and outcome classifier (``classify_outcome``)
verbatim. The difference is the world: ``world_data_boil_hard.yaml`` adds a
``Kitchen`` location, and this module moves the stove (furnished into Houston
Hall by ``_furnish_boil_water``, same as the base world) out of Houston Hall
and into Kitchen at build time -- so the murky pot is visible from step 0, but
the tool needed to treat it never is. Runs with ``CognitionConfig(vision_r=0)``
so the stove cannot leak into the agent's Houston Hall observation via
cross-location perception (#82): reaching it requires actually choosing to
``travel to kitchen`` first. The only lead is that "Kitchen" is always listed
as a named Travel destination (the decide tool's per-verb enum lists every
``game.locations`` entry, #635) -- there is no other in-room hint.

Runs N trials per arm on this harder single-persona boil world:
  * seeded   -- the persona carries the #595 t=0 "the unboiled water made me
                sick" memory (``_AVERSION``, reused verbatim from
                boil_from_memory.py);
  * control  -- identical, minus that memory (bare "thirsty" only).
Each trial reads the AUTHORITATIVE drink outcome DrinkPenn stamped
(drank_unboiled / drank_safe) -- never the event log -- and classifies it via
``classify_outcome`` (reused, unmodified: it's world-shape-specific but this
world keeps the same murky/boiled pot pair). The per-arm boil-before-drink
rate is printed, mirroring #595's summary.

Offline: pass --offline for the scripted brain (no key, no spend) -- plumbing
check only, not a real measurement (the scripted brain doesn't reason about
exploring for a stove, so expect ~0% both arms offline; that's expected, not a
bug).

Live invocation (NOT run by this module or its tests -- a real key + spend is
the user's call)::

    ANTHROPIC_API_KEY=... uv run python \\
        godot-generative-agents/backend/penn/experiments/boil_hard_connect_dots.py \\
        --trials 8 --steps 400

A step budget much larger than the base experiment's default (40) is needed
here, for two independent reasons: (1) a live brain often spends its first
several steps following the schedule's authored "settling in" context before
thirst becomes salient enough to act (pacing, not the puzzle), and (2)
``Travel`` is NOT an instant teleport between named locations -- it's a real
tile-by-tile walk (``WorldMap.walk_path``, BFS pathfinding), one tile per
step. Houston Hall -> Kitchen (Sweeten Alumni Building's real dorm
kitchenette) measures 297 ticks door to door -- so a trial that correctly
decides to travel there needs a step ceiling comfortably above that just to
finish the walk, before it can act at all once it arrives. Walking ticks
consult no brain (no decide happens while ``st["path"]`` is non-empty), so
raising the ceiling doesn't meaningfully raise real spend -- only wall-clock
turn count -- but too low a ceiling silently truncates a trial mid-walk and
miscounts it as a cognitive failure ("neither") when it was actually a step-
budget artifact. ``stop_when`` still ends the trial the instant the outcome
resolves, so the higher ceiling only costs turns on trials that actually
travel, not on every trial.
"""

import argparse
import sys
from pathlib import Path

_SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SIM_DIR))

from backend.run_simulation import simulate  # noqa: E402
from penn_world import (  # noqa: E402
    PENN_ACTION_VERBS,
    WORLD_DATA_BOIL_HARD,
    build_penn_world,
    relocate_stove_to_kitchen,
)
from backend.sim_config import CognitionConfig  # noqa: E402
from text_adventure_games.llm_client import LlmConfig, create_llm_client  # noqa: E402
from text_adventure_games.usage import UsageLedger  # noqa: E402

from backend.penn.experiments.boil_from_memory import (  # noqa: E402
    _configure,
    classify_outcome,
)


def run_arm(*, seeded, trials, steps, make_client):
    """Run `trials` trials of one arm; return the outcome tally + boil-before-drink
    rate. `make_client(ledger)` builds the decide brain for a trial."""
    tally = {"boiled_then_drank": 0, "drank_raw": 0, "neither": 0}
    for _ in range(trials):
        pw = build_penn_world(world_data=WORLD_DATA_BOIL_HARD)
        personas = _configure(pw.personas, seeded=seeded)
        name = personas[0]["name"]
        ledger = UsageLedger()
        captured: dict = {}

        def build_and_relocate(world_map):
            game, chars = pw.build_world_fn(world_map)
            relocate_stove_to_kitchen(game)
            captured.update(chars)
            return game, chars

        def _outcome_decided(_game):
            ch = captured.get(name)
            return ch is not None and classify_outcome(ch) != "neither"

        simulate(
            pw.world_map,
            steps,
            ledger=ledger,
            personas=personas,
            build_world_fn=build_and_relocate,
            llm_client=make_client(ledger),
            extra_action_names=PENN_ACTION_VERBS,
            cognition=CognitionConfig(vision_r=0),
            stop_when=_outcome_decided,
        )
        char = captured[name]
        tally[classify_outcome(char)] += 1
    rate = tally["boiled_then_drank"] / trials if trials else 0.0
    return {**tally, "rate": rate}


def _live_client(ledger, model):
    return create_llm_client(
        LlmConfig(provider="anthropic", model=model),
        ledger=ledger,
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Harder #595 connect-the-dots experiment: stove hidden in a "
        "separate Kitchen location."
    )
    ap.add_argument("--trials", type=int, default=8)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="model id for the live (non --offline) brain",
    )
    ap.add_argument(
        "--offline",
        action="store_true",
        help="use the scripted brain (no key, no spend) -- plumbing check only, "
        "not a real measurement",
    )
    args = ap.parse_args()

    ledger = UsageLedger()
    if args.offline:
        from backend.penn.scripted_brain import build_scripted_brains

        make_client = lambda _t: build_scripted_brains(ledger=ledger)[0]  # noqa: E731
    else:
        make_client = lambda _t: _live_client(ledger, args.model)  # noqa: E731

    for arm in ("seeded", "control"):
        result = run_arm(
            seeded=(arm == "seeded"),
            trials=args.trials,
            steps=args.steps,
            make_client=make_client,
        )
        print(
            f"[{arm:8}] boil-before-drink rate: {result['rate']:.0%}  "
            f"({result['boiled_then_drank']} boiled / {result['drank_raw']} raw / "
            f"{result['neither']} neither of {args.trials})"
        )
    print(f"ledger spend: ${ledger.total_cost_usd():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
