"""Offline smoke + unit tests for the #624 experiment harness: does a live LLM
ARTICULATE the missing boil action (a `proposed` wish) when boiling is
WITHHELD from the world? Mirrors test_boil_from_memory.py's shape (#595's
sibling test file). The research CLAIM (seeded articulation rate clearly
above the no-memory control) is a manual, keyed run -- not asserted here; see
``boil_wish_articulation``'s module docstring for the exact live command.

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_boil_wish_articulation.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.penn.experiments.boil_wish_articulation import (  # noqa: E402
    classify_wish,
    demand_report,
    run_arm,
)
from backend.penn.scripted_brain import build_scripted_brains  # noqa: E402
from penn_world import WORLD_DATA_BOIL, build_penn_world  # noqa: E402

# ----------------------------------------------------------------------
# Section A: the withheld-boil fixture (#624 gotcha #1 -- prove it's gone,
# and prove the normal world still has it).
# ----------------------------------------------------------------------


def test_withheld_world_has_no_boil_recipe():
    pw = build_penn_world(world_data=WORLD_DATA_BOIL, withhold_boil=True)
    game, _chars = pw.build_world_fn(pw.world_map)
    assert game.recipes == []


def test_normal_world_still_registers_the_boil_recipe():
    pw = build_penn_world(world_data=WORLD_DATA_BOIL)  # withhold_boil defaults False
    game, _chars = pw.build_world_fn(pw.world_map)
    assert any(r.name == "boiled water" for r in game.recipes)


def test_withheld_world_still_furnishes_the_boil_props():
    # Withholding the recipe must not withhold the props: the agent should
    # still be ABLE to see/reach the murky pot + stove -- only the transform
    # ("make boiled water") is missing, which is the whole point of the
    # probe (an agent with the raw materials but no verb for what it wants).
    pw = build_penn_world(world_data=WORLD_DATA_BOIL, withhold_boil=True)
    game, _chars = pw.build_world_fn(pw.world_map)
    hall = game.locations["Houston Hall"]
    for name in ("pot of murky water", "sink", "stove"):
        assert name in hall.items, f"{name} missing from Houston Hall"


def test_attempting_to_make_boiled_water_in_the_withheld_world_leaves_a_parse_gap_wish():
    # The secondary/free signal (#621, already on this branch): with no boil
    # Recipe registered, "make boiled water" matches no verb at all (the
    # parser's CRAFT branch requires `game.recipes` truthy), so the parser's
    # own parse-gap capture records it automatically -- real engine wiring,
    # not just classify_wish's own dict-shaped unit tests below. No
    # craft_gap (#628) dependency.
    pw = build_penn_world(world_data=WORLD_DATA_BOIL, withhold_boil=True)
    game, chars = pw.build_world_fn(pw.world_map)
    (char,) = chars.values()
    ok = game.parser.parse_command("make boiled water", actor=char)
    assert ok is False
    assert len(game.wishes) == 1
    wish = game.wishes[0].to_primitive()
    assert wish["trigger"] == "parse_gap"
    assert classify_wish(wish) == "attempted"


# ----------------------------------------------------------------------
# Section B: classify_wish (keyword-based, no LLM -- mirrors #595's
# classify_outcome).
# ----------------------------------------------------------------------


def _wish(desired="", reason="", trigger="proposed"):
    return {"desired": desired, "reason": reason, "trigger": trigger}


def test_classify_wish_articulated_boil_proposal_with_sickness_reason():
    wish = _wish(
        desired="boil the water",
        reason="last time I drank it unboiled I got violently ill",
        trigger="proposed",
    )
    assert classify_wish(wish) == "articulated"


def test_classify_wish_accepts_boil_intent_synonyms():
    for desired in (
        "purify the water",
        "heat the pot of water",
        "sterilize the water",
        "make the water safe to drink",
    ):
        wish = _wish(
            desired=desired, reason="I felt sick after drinking it", trigger="proposed"
        )
        assert classify_wish(wish) == "articulated", desired


def test_classify_wish_proposed_but_unrelated_is_not_articulated():
    wish = _wish(
        desired="a bike rack near the library",
        reason="mine keeps getting stolen",
        trigger="proposed",
    )
    assert classify_wish(wish) == "unrelated"


def test_classify_wish_proposed_boil_without_sickness_reason_is_not_articulated():
    # The AND is deliberate: a boil-intent desired alone (no reference to the
    # sickness) doesn't count -- the measurement is about reasoning FROM the
    # aversive memory, not any old boil request.
    wish = _wish(
        desired="boil the water", reason="it tastes better", trigger="proposed"
    )
    assert classify_wish(wish) == "unrelated"


def test_classify_wish_parse_gap_boil_attempt_is_the_secondary_signal():
    # #621's automatic capture of an unparsed "make boiled water" attempt in
    # the withheld world: no recipe is registered, so CRAFT never matches,
    # and the raw command becomes the parse-gap's `desired`.
    wish = _wish(desired="make boiled water", reason="", trigger="parse_gap")
    assert classify_wish(wish) == "attempted"


def test_classify_wish_unrelated_parse_gap_is_neither():
    wish = _wish(desired="dance with the statue", reason="", trigger="parse_gap")
    assert classify_wish(wish) == "unrelated"


# ----------------------------------------------------------------------
# Section C: the harness runs offline (scripted brain never proposes, so the
# articulation rate must come out exactly 0 -- plumbing check only).
# ----------------------------------------------------------------------


def test_run_arm_smoke_with_scripted_brain_never_articulates():
    result = run_arm(
        seeded=True,
        trials=2,
        steps=20,
        make_client=lambda ledger: build_scripted_brains(ledger=ledger)[0],
    )
    assert set(result) >= {"articulated", "attempted", "neither", "rate"}
    assert result["articulated"] == 0
    assert result["rate"] == 0.0
    assert result["articulated"] + result["attempted"] + result["neither"] == 2


def test_run_arm_collects_wishes_into_the_shared_out_list():
    # Even offline, out_wishes_all must fill with whatever wishes.jsonl would
    # have gotten (empty is fine for the scripted brain -- this just proves
    # the plumbing, matching #622's own "mock invariant" tests).
    collected: list = []
    run_arm(
        seeded=False,
        trials=1,
        steps=10,
        make_client=lambda ledger: build_scripted_brains(ledger=ledger)[0],
        out_wishes_all=collected,
    )
    assert isinstance(collected, list)


# ----------------------------------------------------------------------
# Section D: the #623 most-wanted-actions wiring (acceptance: the withheld
# boil capability tops the report). Hand-authored wishes -- a live run is not
# required to pin this; see the module docstring for how one would be
# invoked.
# ----------------------------------------------------------------------


def test_most_wanted_report_ranks_the_boil_group_first():
    records = [
        {
            "actor": "Nadia Okafor",
            "turn": 12,
            "location": "Houston Hall",
            "desired": "boil the water",
            "reason": "I got violently ill last time I drank it unboiled",
            "trigger": "proposed",
            "goals": [],
            "scope": [],
            "raw_command": "propose boil the water because I got violently ill "
            "last time I drank it unboiled",
            "meta": {},
        },
        {
            "actor": "Nadia Okafor",
            "turn": 40,
            "location": "Houston Hall",
            "desired": "Boil The Water",
            "reason": "I got sick from the murky water before",
            "trigger": "proposed",
            "goals": [],
            "scope": [],
            "raw_command": "propose Boil The Water because I got sick from the "
            "murky water before",
            "meta": {},
        },
        {
            "actor": "Nadia Okafor",
            "turn": 68,
            "location": "Houston Hall",
            "desired": "boil   the water",
            "reason": "the last pot made me ill",
            "trigger": "proposed",
            "goals": [],
            "scope": [],
            "raw_command": "propose boil   the water because the last pot made me "
            "ill",
            "meta": {},
        },
        {
            "actor": "Nadia Okafor",
            "turn": 55,
            "location": "Houston Hall",
            "desired": "make boiled water",
            "reason": "",
            "trigger": "parse_gap",
            "goals": [],
            "scope": [],
            "raw_command": "make boiled water",
            "meta": {},
        },
        {
            "actor": "Nadia Okafor",
            "turn": 5,
            "location": "Houston Hall",
            "desired": "a working elevator",
            "reason": "stairs are exhausting",
            "trigger": "proposed",
            "goals": [],
            "scope": [],
            "raw_command": "propose a working elevator because stairs are "
            "exhausting",
            "meta": {},
        },
    ]
    report = demand_report(records)
    assert report.total_wishes == 5
    assert report.rows[0].key == "boil the water"
    assert report.rows[0].count == 3
