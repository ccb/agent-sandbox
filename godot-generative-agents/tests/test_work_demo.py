"""The wage-drive DEMO scenario (regression demo for cf7ef4fb).

`generate_penn_replay.py --scenario work` bakes a short, single-persona replay
of a Houston Hall cashier walking in from the open campus before settling into
a work stop. `accrue_wage` (drives.py) used to pay wage_rate into
Property.MONEY for every tick a persona with a job was ticking at all, even
while still walking to the work stop -- cf7ef4fb gated it on the character
actually being settled (location matches the stop's place AND activity is
set). These tests pin the scenario world and, through the real bake pipeline
(not a hand-built fixture like test_wage_drive.py's unit tests), that money
never rises above the starting balance through the walk and only climbs once
settled. Mirrors test_boil_demo.py's structure and style.
"""

import os
import sys

from backend.penn.penn_world import (
    PENN_ACTION_VERBS,
    WORLD_DATA_WORK,
    build_penn_world,
)
from backend.run_simulation import simulate
from text_adventure_games.enums import Property

# Import the generator's scenario table without triggering a bake (main() is
# __main__-guarded). See test_boil_demo.py for why this sys.path dance is
# needed.
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "penn"))
)
from backend.penn import generate_penn_replay as gen  # noqa: E402


def test_scenarios_table_wires_the_work_scenario():
    """`--scenario work` selects the wage world YAML + its own output file, so
    the demo bakes ALONGSIDE (never over) the bundled replay."""
    work = gen.SCENARIOS["work"]
    assert work["world_data"] == WORLD_DATA_WORK
    assert work["out"] == "penn_replay_work.json"


def test_work_world_is_a_single_campus_persona_with_a_job():
    """The scenario is one persona whose home is the open campus (not the
    workplace itself), so the bake opens with a real walk in, and the shared
    factory still gives the wage drive something to read (wage_rate + an
    is_work stop)."""
    pw = build_penn_world(world_data=WORLD_DATA_WORK)
    assert len(pw.personas) == 1
    (persona,) = pw.personas
    assert persona["home"] == "Penn campus"
    assert persona.get("wage_rate")
    (stop,) = persona["schedule"]
    assert stop["place"] == "Houston Hall"
    assert stop["is_work"] is True
    # No meetings/relationships to inject for a solo demo.
    assert pw.meetings == []
    assert pw.relationships == []


# --- the baked arc on the timeline ------------------------------------------


def _sample_settled_and_money(name):
    """A `stop_when` predicate (`game -> bool`) that never actually stops the
    run -- it abuses the hook's per-step callback as a side-channel to sample
    (settled?, Property.MONEY) after every step, since `simulate()`'s frames
    carry only movement/pronunciatio/chat, not raw character properties.

    "Settled" mirrors accrue_wage's own read exactly: `char.location.name`
    flips to the destination the instant Travel is issued (the tile-by-tile
    walk that follows is a visual animation over subsequent frames, not a
    location change), so location alone can't tell "still walking" from
    "arrived" -- Property "activity" is the signal accrue_wage actually reads
    (cleared to False the moment travel starts, restamped only once the
    character has actually settled in). Returns (samples, predicate)."""
    samples = []

    def _predicate(game):
        char = game.characters[name]
        settled = bool(char.get_property("activity"))
        samples.append((settled, char.get_property(Property.MONEY) or 0))
        return False

    return samples, _predicate


def test_money_holds_flat_while_walking_then_accrues_once_settled():
    pw = build_penn_world(world_data=WORLD_DATA_WORK)
    (persona,) = pw.personas
    name = persona["name"]
    steps = gen.SCENARIOS["work"]["steps"]
    samples, stop_when = _sample_settled_and_money(name)

    simulate(
        pw.world_map,
        steps,
        personas=pw.personas,
        build_world_fn=pw.build_world_fn,
        extra_action_names=PENN_ACTION_VERBS,
        stop_when=stop_when,
    )

    assert samples, "stop_when never fired -- the bake produced no steps"
    # The walk in is real: at least the first tick is still unsettled (out on
    # the commute), not already on the clock.
    assert samples[0][0] is False
    starting_money = samples[0][1]  # _furnish_starting_money's baseline (#931)

    # Every tick spent still walking (not settled) paid nothing on top of the
    # starting balance -- the wage drive itself must stay at exactly 0 added.
    for settled, money in samples:
        if not settled:
            assert money == starting_money, "wage accrued while still walking to work"

    # Once settled, wage accrues: strictly above the starting balance by the
    # end.
    settled_money = [money for settled, money in samples if settled]
    assert settled_money, "never settled into the work stop in this bake's step budget"
    assert settled_money[-1] > starting_money, "wage never accrued after settling in"
    # Monotonically non-decreasing throughout -- wage is only ever paid, never
    # clawed back.
    monies = [money for _settled, money in samples]
    assert monies == sorted(monies)
