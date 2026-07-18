"""#595 experiment: does a live LLM choose to boil from an aversive memory?

Runs N trials per arm on the single-persona boil world:
  * seeded   -- the persona carries a t=0 "the unboiled water made me sick" memory;
  * control  -- identical, minus that memory.
Each trial reads the AUTHORITATIVE drink outcome DrinkPenn stamped
(drank_unboiled / drank_boiled) -- never the event log -- and classifies it. The
per-arm boil-before-drink rate is printed; the seeded arm clearly above control is
the #595 result.

Offline: pass a scripted/mock make_client (no key). Live: default make_client builds
an Anthropic Haiku client -- needs ANTHROPIC_API_KEY (in-env only) and small spend.
"""

import argparse
import sys
from pathlib import Path

_SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SIM_DIR))

from backend.run_simulation import simulate  # noqa: E402
from penn_world import WORLD_DATA_BOIL, build_penn_world  # noqa: E402
from text_adventure_games.llm_client import LlmConfig, create_llm_client  # noqa: E402
from text_adventure_games.usage import UsageLedger  # noqa: E402

_AVERSION = "Last time I drank the unboiled water at Houston Hall I got violently ill."


def classify_outcome(char) -> str:
    """The trial outcome, read from DrinkPenn's authoritative counters."""
    if (char.get_property("drank_unboiled") or 0) > 0:
        return "drank_raw"
    if (char.get_property("drank_boiled") or 0) > 0:
        return "boiled_then_drank"
    return "neither"


def _configure(personas, *, seeded):
    """Return a fresh personas list configured for one arm: the boil persona is
    thirsty (so drinking is motivated) and -- in the seeded arm -- carries the
    aversion memory. Authored commands are left as-is: a live brain ignores them
    (attach_agents treats commands as mock-only), so nothing needs stripping."""
    out = [dict(p) for p in personas]
    p = out[0]
    p["thirst_rate"] = 1
    p["thirst_threshold"] = 2
    p["seed_memories"] = [_AVERSION] if seeded else []
    return out


def run_arm(*, seeded, trials, steps, make_client):
    """Run `trials` trials of one arm; return the outcome tally + boil-before-drink
    rate. `make_client(ledger)` builds the decide brain for a trial."""
    tally = {"boiled_then_drank": 0, "drank_raw": 0, "neither": 0}
    for _ in range(trials):
        pw = build_penn_world(world_data=WORLD_DATA_BOIL)  # fresh world per trial
        personas = _configure(pw.personas, seeded=seeded)
        ledger = UsageLedger()
        captured: dict = {}

        def build_capture(world_map):
            game, chars = pw.build_world_fn(world_map)
            captured.update(chars)
            return game, chars

        simulate(
            pw.world_map,
            steps,
            ledger=ledger,
            personas=personas,
            build_world_fn=build_capture,
            llm_client=make_client(ledger),
        )
        char = captured[personas[0]["name"]]
        tally[classify_outcome(char)] += 1
    rate = tally["boiled_then_drank"] / trials if trials else 0.0
    return {**tally, "rate": rate}


def _live_client(ledger, model):
    return create_llm_client(
        LlmConfig(provider="anthropic", model=model),
        ledger=ledger,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="#595 boil-from-memory experiment.")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--steps", type=int, default=80)
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

    # One shared ledger + one brain instance for the whole run (both arms, all
    # trials), so the printed spend at the end is the run's real total -- run_arm
    # hands each trial its own per-trial ledger (for attach_agents' embedding/
    # reflection bookkeeping), but the brain itself always records into this one.
    ledger = UsageLedger()
    if args.offline:
        from backend.penn.scripted_brain import build_scripted_brains

        brain, _reflector = build_scripted_brains(ledger=ledger)
    else:
        brain = _live_client(ledger, args.model)
    make_client = lambda _trial_ledger: brain  # noqa: E731

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
