"""#624 experiment: does a live LLM ARTICULATE the missing boil action -- a
`proposed` wish (#620) -- when boiling is WITHHELD from the world?

Sibling of #595's ``boil_from_memory.py`` (which measures whether the LLM
CHOOSES an existing boil tool from an aversive memory): mirrors its structure
closely, but here the world never registers the boil Recipe
(``build_penn_world(..., withhold_boil=True)``, #624), restoring the #300
capability gap ("no agent can boil water yet") on demand and instrumenting it
via the wish channel (#620/#621, epic #619's demand side).

Runs N trials per arm on the single-persona boil world, boiling WITHHELD:
  * seeded   -- the persona carries the #595 t=0 "the unboiled water made me
                sick" memory (``_AVERSION``, reused verbatim);
  * control  -- identical, minus that memory.
Both arms additionally get the #692 scenario fixes (a first keyed re-run came
back 0%/0% in both arms; the plumbing wasn't the problem -- nothing created
goal pressure toward `propose`): an explicit persona goal to drink without
getting sick (populating the wish's ``goals`` snapshot too), and de-scripted
schedule wording, so the sickness/recovery stops aren't read by a live brain
as its own authored plan (see ``_configure``/``_NEUTRAL_ACTIVITY`` below).
Each trial reads the run's ActionWish log (via ``simulate(..., out_wishes=)``
-- never the event log) and classifies it with :func:`classify_wish`: a
`proposed` wish whose ``desired`` names a boil/heat/purify/sterilize/make-safe
fix for the water AND whose ``reason`` names the sickness is the articulation
signal. The per-arm articulation rate is printed, mirroring #595's summary;
the seeded arm clearly above control is the #624 result.

A secondary, free metric: non-`proposed` wishes -- `parse_gap` (#621) or
`craft_gap` (#628, now on `main`) -- that still show the agent TRYING to
boil/purify the water without articulating it as a wish, e.g. an unparsed
"make boiled water" attempt, or a "boil the water" CRAFT correctly rejects for
the missing recipe.

The propose tool must be reachable: Penn's live entry points only expose
``PENN_ACTION_VERBS`` (get/drink/activate/deactivate/make) to a real brain's
tool menu (via ``attach_agents(extra_action_names=...)``) -- "propose" isn't
among them, so this experiment passes its own
``extra_action_names=[*PENN_ACTION_VERBS, "propose"]`` to ``simulate()`` so a
live brain can reach ``propose`` at all: "propose" is never in a schedule's
authored commands (scripting the proposal would defeat the point of testing
whether the agent reaches for it on its own). ("make" *is* authored in the
reused boil fixture, so it already reaches the tool menu via authored_verbs --
widening the menu here is only needed for "propose".)

After a run, this module's own #623 wiring (:func:`demand_report`) runs the
``most_wanted_actions`` aggregator over the run's whole wish log: the withheld
boil capability should top it (the #624 acceptance criterion).

Offline: pass a scripted/mock make_client (no key). Live: default make_client
builds an Anthropic Haiku client -- needs ANTHROPIC_API_KEY (in-env only) and
small spend.

Live invocation (NOT run by this module or its tests -- a real key + spend is
the user's call)::

    ANTHROPIC_API_KEY=... uv run python \\
        godot-generative-agents/backend/penn/experiments/boil_wish_articulation.py \\
        --trials 10 --steps 80
"""

import argparse
import sys
from pathlib import Path

_SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SIM_DIR))
_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
sys.path.insert(0, str(_TOOLS_DIR))

from backend.penn.experiments.boil_from_memory import (
    _configure as _seed_aversion_memory,
)  # noqa: E402
from backend.run_simulation import simulate  # noqa: E402
from penn_world import (
    PENN_ACTION_VERBS,
    WORLD_DATA_BOIL,
    build_penn_world,
)  # noqa: E402
from text_adventure_games.llm_client import LlmConfig, create_llm_client  # noqa: E402
from text_adventure_games.things.characters import GoalType  # noqa: E402
from text_adventure_games.usage import UsageLedger  # noqa: E402
from text_adventure_games.wishes import TRIGGER_PROPOSED  # noqa: E402

import most_wanted_actions as mwa  # noqa: E402

# `_seed_aversion_memory` is #595's t=0 aversion memory ("Last time I drank the
# unboiled water at Houston Hall I got violently ill.") applied verbatim: seeded
# -> persona carries it, control -> doesn't. Reused, not re-derived, so the two
# experiments' "seeded" arms are directly comparable.

PROPOSE_VERB = "propose"
# Every verb a live brain may pick from in this experiment: Penn's usual
# device/drink verbs plus "propose" (see the module docstring -- Penn's live
# entry points never add it, so we do here).
EXTRA_ACTION_NAMES = [*PENN_ACTION_VERBS, PROPOSE_VERB]

# #692: the withheld-boil scenario ran 0%/0% in both arms across two keyed
# runs. The plumbing wasn't the problem -- nothing created goal pressure
# toward `propose`. Two scenario fixes, applied to BOTH arms (they're
# properties of the persona's situation, not the seeded aversion memory):
_EXPLICIT_GOAL = "find a way to drink water without getting sick"
# The world YAML's schedule (`world_data_boil.yaml`) is authored so the mock
# brain's bake/replay narrates a sickness arc -- but `decide_context_block`
# (cognition.py) surfaces every stop's `activity` text to a LIVE brain too, as
# "your plan's current stop". Read verbatim, "feeling ill at the table" /
# "hoping the queasiness passes" / "recovered and back at the union" tell the
# live agent that getting sick (and getting better) is ITS OWN AUTHORED PLAN,
# not a problem to solve -- undermining the aversive tension the experiment
# measures. Neutralized here, not in the shared YAML: that file is also #595's
# fixture and is wording-pinned by test_boil_demo.py, and the mock brain never
# reads `activity` text (issue #300), so this only changes what a live brain
# sees in THIS experiment.
_NEUTRAL_ACTIVITY = {
    "feeling ill at the table": "at the table",
    "hoping the queasiness passes": "still at the table",
    "recovered and back at the union": "back at the union",
}


def _configure(personas, *, seeded):
    """#595's ``_configure`` (thirst + the seeded aversion memory) plus the
    #692 scenario fixes: an explicit goal and de-scripted schedule wording,
    both applied to every arm."""
    out = _seed_aversion_memory(personas, seeded=seeded)
    for p in out:
        for stop in p.get("schedule", []):
            if stop.get("activity") in _NEUTRAL_ACTIVITY:
                stop["activity"] = _NEUTRAL_ACTIVITY[stop["activity"]]
    return out


# --- classify_wish (keyword-based, no LLM; mirrors #595's classify_outcome) -

# Boil-intent verbs/adjectives, matched as a lowercase substring. "safe" is
# deliberately broad ("make the water safe to drink") -- the tradeoff of a v1
# keyword classifier: a wish about "a safe path across the water" would also
# false-positive on boil-intent, but that combination has not appeared in
# practice and simplicity beats a bigger regex here (documented, not hidden).
_BOIL_WORDS = (
    "boil",
    "heat",
    "purify",
    "purifie",
    "sterilize",
    "sterilise",
    "disinfect",
    "cleanse",
    "safe",
)
# The desired phrase must also name the water/vessel, so "heat my room" or
# "a safer bike lane" don't false-positive on "heat"/"safe" alone.
_WATER_WORDS = ("water", "pot")
# The wish's `reason` must reference the sickness for a "proposed" wish to
# count as ARTICULATED (the #624 measurement is about reasoning FROM the
# aversive memory, not any old boil request -- see
# test_classify_wish_proposed_boil_without_sickness_reason_is_not_articulated).
_SICKNESS_WORDS = (
    "sick",
    "ill",
    "nause",
    "vomit",
    "stomach",
    "queasy",
    "unwell",
    "threw up",
)


def _mentions_boiling_the_water(text: str) -> bool:
    lowered = text.lower()
    return any(b in lowered for b in _BOIL_WORDS) and any(
        w in lowered for w in _WATER_WORDS
    )


def classify_wish(wish: dict) -> str:
    """Classify one ``ActionWish.to_primitive()`` dict for the #624 measurement.

    Returns one of:

    * ``"articulated"`` -- a ``trigger="proposed"`` wish whose ``desired``
      names a boil/heat/purify/sterilize/make-safe fix FOR THE WATER (a
      boil-intent keyword plus a water/pot mention) AND whose ``reason``
      names the sickness (a sick/ill/nausea/... keyword). This is the #624
      primary signal: the agent explicitly asked the world's designers for
      the missing action, reasoning from the aversive memory.
    * ``"attempted"`` -- any OTHER (non-``proposed``) wish that still names a
      boil-intent fix for the water -- e.g. an unparsed "make boiled water"
      attempt (``trigger="parse_gap"``, #621), or a "boil the water" CRAFT
      correctly rejects for the missing recipe (``trigger="craft_gap"``,
      #628) -- both leave a wish record in the withheld world.
    * ``"unrelated"`` -- neither of the above (a wish about something else,
      a boil-intent proposal with no sickness reason, or no boil-relevant
      wish at all).

    Keyword-based and deliberately simple (no LLM, mirrors #595's
    ``classify_outcome``): substring matches against small fixed
    vocabularies, not semantic clustering.
    """
    desired = str(wish.get("desired") or "")
    reason = str(wish.get("reason") or "")
    boil_intent = _mentions_boiling_the_water(desired)
    if wish.get("trigger") == TRIGGER_PROPOSED:
        if boil_intent and any(s in reason.lower() for s in _SICKNESS_WORDS):
            return "articulated"
        return "unrelated"
    if boil_intent:
        return "attempted"
    return "unrelated"


_RANK = {"unrelated": 0, "attempted": 1, "articulated": 2}


def classify_trial(wishes: list[dict]) -> str:
    """One trial's outcome: the BEST :func:`classify_wish` label found among
    its wishes (articulated > attempted > neither) -- mirrors #595's
    ``classify_outcome`` shape (a single best label per trial). "neither"
    also covers a trial with zero wishes at all (nothing was proposed or left
    an unparsed trace)."""
    best = "unrelated"
    for wish in wishes:
        label = classify_wish(wish)
        if _RANK[label] > _RANK[best]:
            best = label
    return "neither" if best == "unrelated" else best


def demand_report(records: list[dict]) -> "mwa.Report":
    """Run #623's most-wanted-actions aggregator over a set of collected
    ActionWish dicts (a run's whole wish log). Thin wiring, not a
    reimplementation -- the normalize/group/rank logic stays entirely in
    ``tools/most_wanted_actions.py`` (out of scope here, #623); this just
    imports it (mirroring ``tests/test_most_wanted_actions.py``'s own
    ``sys.path`` setup above) and hands the records through. The #624
    acceptance criterion is that the withheld boil capability tops this
    report's ranked rows."""
    return mwa.build_report(records)


def run_arm(*, seeded, trials, steps, make_client, out_wishes_all=None):
    """Run `trials` trials of one arm on the WITHHELD-boil world; return the
    outcome tally + articulation rate. `make_client(ledger)` builds the
    decide brain for a trial.

    Pass `out_wishes_all` to also collect every trial's wishes (as
    ``ActionWish.to_primitive()`` dicts) into one flat list -- e.g. to feed
    :func:`demand_report` over the whole run afterward.
    """
    tally = {"articulated": 0, "attempted": 0, "neither": 0}
    for _ in range(trials):
        pw = build_penn_world(world_data=WORLD_DATA_BOIL, withhold_boil=True)
        personas = _configure(pw.personas, seeded=seeded)
        ledger = UsageLedger()
        out_wishes: list = []

        # #692 fix (a): the persona otherwise starts with `goals == []` -- no
        # blocked-goal tension for the wish channel to record. Set on the
        # built Character (there's no persona-dict -> Character.goals wiring
        # to lean on), same tally as _configure's single-persona assertion.
        def build_world_with_goal(world_map):
            game, chars = pw.build_world_fn(world_map)
            assert (
                len(chars) == 1
            ), f"boil world must stay single-persona, got {len(chars)}"
            next(iter(chars.values())).add_goal(_EXPLICIT_GOAL, GoalType.SHORT)
            return game, chars

        simulate(
            pw.world_map,
            steps,
            ledger=ledger,
            personas=personas,
            build_world_fn=build_world_with_goal,
            llm_client=make_client(ledger),
            extra_action_names=EXTRA_ACTION_NAMES,
            out_wishes=out_wishes,
        )
        tally[classify_trial(out_wishes)] += 1
        if out_wishes_all is not None:
            out_wishes_all.extend(out_wishes)
    rate = tally["articulated"] / trials if trials else 0.0
    return {**tally, "rate": rate}


def _live_client(ledger, model):
    return create_llm_client(
        LlmConfig(provider="anthropic", model=model),
        ledger=ledger,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="#624 boil-wish-articulation experiment.")
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
        "not a real measurement (it never proposes, so the rate is always 0)",
    )
    args = ap.parse_args()

    # One shared ledger for the whole run (both arms, all trials) so the
    # printed spend is the run's real total -- but a FRESH brain per trial (see
    # #595's own note), so no internal client state leaks across trials/arms.
    ledger = UsageLedger()
    if args.offline:
        from backend.penn.scripted_brain import build_scripted_brains

        make_client = lambda _t: build_scripted_brains(ledger=ledger)[0]  # noqa: E731
    else:
        make_client = lambda _t: _live_client(ledger, args.model)  # noqa: E731

    all_wishes: list = []
    for arm in ("seeded", "control"):
        result = run_arm(
            seeded=(arm == "seeded"),
            trials=args.trials,
            steps=args.steps,
            make_client=make_client,
            out_wishes_all=all_wishes,
        )
        print(
            f"[{arm:8}] articulation rate: {result['rate']:.0%}  "
            f"({result['articulated']} articulated / {result['attempted']} attempted "
            f"(parse-gap + craft-gap secondary) / {result['neither']} "
            f"neither of {args.trials})"
        )
    print(f"ledger spend: ${ledger.total_cost_usd():.4f}")

    print()
    print(mwa.render_markdown(demand_report(all_wishes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
