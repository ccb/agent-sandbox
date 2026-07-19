"""#595 experiment: does a live LLM choose to boil from an aversive memory?

Runs N trials per arm on the single-persona boil world:
  * seeded   -- the persona carries a t=0 "the unboiled water made me sick" memory;
  * control  -- identical, minus that memory.
Each trial reads the AUTHORITATIVE drink outcome DrinkPenn stamped
(drank_unboiled / drank_safe) -- never the event log -- and classifies it. The
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
from penn_world import (  # noqa: E402
    PENN_ACTION_VERBS,
    WORLD_DATA_BOIL,
    build_penn_world,
)
from backend.sim_config import RetrievalConfig  # noqa: E402
from text_adventure_games.llm_client import LlmConfig, create_llm_client  # noqa: E402
from text_adventure_games.usage import UsageLedger  # noqa: E402

_AVERSION = "Last time I drank the unboiled water at Houston Hall I got violently ill."

# Importance-forward retrieval (#633). The default profile weights recency at
# 1.0. In the sparse nominal run the seeded t=0 aversion still surfaces, but the
# default is fragile: recency = decay**(turn - last_accessed) collapses toward 0
# for an old memory, so once enough fresh same-place memories accrue (a live
# brain deciding every few ticks) the importance-5 aversion drops out of the
# top-k and the seeded arm silently reads like control for plumbing reasons, not
# cognition. Down-weighting recency to 0.25 (importance/relevance stay 1.0) makes
# a high-importance seed rank top-1 regardless of decide density -- verified
# against the real Houston decide observation at 80 accrued same-place memories,
# where the default buries it and this surfaces it. Applied to BOTH arms, so it
# removes a retrieval confound rather than biasing one: control has no aversion
# to surface. (The general engine-side fix -- an importance/relevance floor in
# memory.retrieve -- is the #633 follow-up to main.)
_RETRIEVAL = RetrievalConfig(alpha_recency=0.25)


def classify_outcome(char) -> str:
    """The trial outcome, read from DrinkPenn's authoritative counters.

    Raw is checked FIRST: an agent that drank raw and then boiled still failed
    the boil-BEFORE-drink metric. Mapping ``drank_safe`` to "boiled_then_drank"
    leans on a boil-world fact -- the only reachable safe drink there is the
    pot the agent boiled -- so this classifier is boil-world-specific, not a
    general drinking metric."""
    if (char.get_property("drank_unboiled") or 0) > 0:
        return "drank_raw"
    if (char.get_property("drank_safe") or 0) > 0:
        return "boiled_then_drank"
    return "neither"


def _configure(personas, *, seeded):
    """Return a fresh personas list configured for one arm: the boil persona is
    thirsty (so drinking is motivated) and -- in the seeded arm -- carries the
    aversion memory. Authored commands are left as-is: a live brain ignores them
    (attach_agents treats commands as mock-only), so nothing needs stripping."""
    out = [dict(p) for p in personas]
    # The whole design is single-subject; a second persona would silently run
    # unconfigured, so fail loudly if the boil world ever grows one.
    assert len(out) == 1, f"boil world must stay single-persona, got {len(out)}"
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
            # Hand the live brain Penn's full verb set (#635 parity with the
            # bake/serve entry points). get/drink/make arrive via authored
            # commands anyway, but this keeps activate/deactivate available and
            # the wiring identical to the canonical runners.
            extra_action_names=PENN_ACTION_VERBS,
            # Importance-forward retrieval so the seeded aversion isn't buried
            # (#633); a no-op for the control arm, which has no seed.
            retrieval=_RETRIEVAL,
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

    # One shared ledger for the whole run (both arms, all trials), so the
    # printed spend at the end is the run's real total -- but a FRESH brain per
    # trial, so no internal client state (scripted-brain accumulators, schedule
    # registrations) can leak across trials or arms. run_arm hands each trial
    # its own per-trial ledger too (attach_agents' embedding/reflection
    # bookkeeping); the brain itself always records into this shared one.
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
