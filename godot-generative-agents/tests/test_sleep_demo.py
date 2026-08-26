"""The sleep-interrupt DEMO scenario (regression demo for 45df120b, c12b3723,
44729cf5).

`generate_penn_replay.py --scenario sleep` bakes a short, two-persona replay of
a resident sleeping through the night in Houston Hall's Reading Room (the
campus's only `sleepable` spot, #931) while a passerby's evening errand brings
them into the very same room during the sleep window -- exactly the situation
the three fixes on this branch guard:

  - maybe_converse could still pair a sleeping resident into a conversation
    (45df120b);
  - maybe_react could still hand a walking passerby a "greet" for a sleeping
    resident (44729cf5);
  - needs_interrupt_seen stayed frozen through sleep, suppressing a real
    interrupt on waking (c12b3723).

Those three fixes are already thoroughly unit-tested against synthetic
fixtures -- test_conversation_sleep_gate.py, test_react_interruption_370.py,
and test_pacing_authority_581.py -- and this suite does not re-derive their
correctness (the guard functions don't care whether the location came from a
two-tile synthetic Plaza or this real Reading Room). What's tested here,
mirroring test_boil_demo.py's own scope, is that THIS authored world actually
produces the situation it claims to: the sleeper's sleepy -> asleep -> awake
transitions land in order with sane spacing, and the passerby is genuinely
co-located with her for a real stretch of that sleep window (proving the
scenario is a real overlap, not an accident of scheduling) -- and, gated by
--brain scripted or --reactive-sleep, that (converse/react are mock-inert, see
cognition.maybe_converse's own docstring) the plain mock bake stays quiet
(no accidental chat) through it.
"""

import os
import sys

from backend.penn.penn_world import (
    PENN_ACTION_VERBS,
    WORLD_DATA_SLEEP,
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

_SLEEPER = "Priya Nair"
_PASSERBY = "Ben Ochoa"


def test_scenarios_table_wires_the_sleep_scenario():
    """`--scenario sleep` selects the sleep world YAML + its own output file,
    so the demo bakes ALONGSIDE (never over) the bundled replay."""
    sleep = gen.SCENARIOS["sleep"]
    assert sleep["world_data"] == WORLD_DATA_SLEEP
    assert sleep["out"] == "penn_replay_sleep.json"


def test_sleep_world_is_two_houston_personas_with_a_sleepable_room():
    """The scenario is two Houston-adjacent personas: the sleeper homed
    directly in the sleepable Reading Room (no travel needed to reach the one
    place she can sleep), and a passerby homed in the lobby whose schedule
    later targets that same room."""
    pw = build_penn_world(world_data=WORLD_DATA_SLEEP)
    assert {p["name"] for p in pw.personas} == {_SLEEPER, _PASSERBY}
    by_name = {p["name"]: p for p in pw.personas}
    assert by_name[_SLEEPER]["home"] == "Houston Hall — Reading Room"
    assert by_name[_PASSERBY]["home"] == "Houston Hall"
    assert any(
        stop["place"] == "Houston Hall — Reading Room"
        for stop in by_name[_PASSERBY]["schedule"]
    )
    game, _chars = pw.build_world_fn(pw.world_map)
    room = game.locations.get("Houston Hall — Reading Room")
    assert room is not None and room.get_property("sleepable")
    # No meetings/relationships to inject for this two-persona demo.
    assert pw.meetings == []
    assert pw.relationships == []


# --- the baked arc on the timeline ------------------------------------------


def _sample_sleep_and_location():
    """A `stop_when` predicate (`game -> bool`) that never actually stops the
    run -- it abuses the hook's per-step callback as a side-channel to sample
    per-tick (location, IS_SLEEPY, IS_SLEEPING) for both personas, since
    `simulate()`'s frames carry movement/pronunciatio/chat, not raw character
    properties. Returns (samples, predicate); samples is a list of
    {name: (location, is_sleepy, is_sleeping)} dicts, one per tick."""
    samples = []

    def _predicate(game):
        row = {}
        for name in (_SLEEPER, _PASSERBY):
            char = game.characters[name]
            row[name] = (
                char.location.name if char.location is not None else None,
                bool(char.get_property(Property.IS_SLEEPY)),
                bool(char.get_property(Property.IS_SLEEPING)),
            )
        samples.append(row)
        return False

    return samples, _predicate


def _first(samples, name, predicate):
    return next((i for i, row in enumerate(samples) if predicate(row[name])), None)


def test_sleeper_falls_asleep_and_wakes_in_order_with_sane_spacing():
    pw = build_penn_world(world_data=WORLD_DATA_SLEEP)
    steps = gen.SCENARIOS["sleep"]["steps"]
    samples, stop_when = _sample_sleep_and_location()

    simulate(
        pw.world_map,
        steps,
        personas=pw.personas,
        build_world_fn=pw.build_world_fn,
        extra_action_names=PENN_ACTION_VERBS,
        stop_when=stop_when,
    )

    sleepy_at = _first(samples, _SLEEPER, lambda s: s[1])
    sleeping_at = _first(samples, _SLEEPER, lambda s: s[2])
    awake_at = _first(samples, _SLEEPER, lambda s: sleeping_at is not None and not s[2])
    assert sleepy_at is not None, "sleeper never got sleepy in this step budget"
    assert sleeping_at is not None, "sleeper never fell asleep in this step budget"
    # awake_at must be found strictly after sleeping_at, not the (also True)
    # not-yet-asleep prefix.
    awake_at = next(
        (i for i in range(sleeping_at, len(samples)) if not samples[i][_SLEEPER][2]),
        None,
    )
    assert awake_at is not None, "sleeper never woke back up in this step budget"

    # Order: gets sleepy well before the authored sleep command is even
    # issued (she was never scripted around the natural threshold), then
    # actually sleeps, then wakes.
    assert sleepy_at < sleeping_at < awake_at
    # A real sleep, not an instant nap: recovery takes a couple dozen ticks at
    # least, not one.
    assert awake_at - sleeping_at >= 10


def test_passerby_is_genuinely_co_located_through_part_of_the_sleep_window():
    """The demo's whole point: the passerby must actually be standing in the
    Reading Room for a real stretch of the sleeper's asleep window -- proving
    this is a genuine overlap the guards would have to contend with, not an
    accident of scheduling that happens to never bring them together."""
    pw = build_penn_world(world_data=WORLD_DATA_SLEEP)
    steps = gen.SCENARIOS["sleep"]["steps"]
    samples, stop_when = _sample_sleep_and_location()

    simulate(
        pw.world_map,
        steps,
        personas=pw.personas,
        build_world_fn=pw.build_world_fn,
        extra_action_names=PENN_ACTION_VERBS,
        stop_when=stop_when,
    )

    room = "Houston Hall — Reading Room"
    overlap = [
        i
        for i, row in enumerate(samples)
        if row[_SLEEPER][2]  # sleeper asleep
        and row[_PASSERBY][0] == room  # passerby physically in the same room
    ]
    assert len(overlap) >= 10, (
        f"passerby overlapped the sleeper's asleep window for only "
        f"{len(overlap)} ticks -- not a real co-location, retune the schedule"
    )


def test_no_scripted_meeting_and_no_accidental_chat():
    """No `meetings` block is authored for this world (both personas are
    mock-brain-driven, and maybe_converse/maybe_react are mock-inert -- see
    their own docstrings), so nothing should ever paint a `chat` line here;
    if one appeared it would mean an authored meeting leaked in by accident."""
    pw = build_penn_world(world_data=WORLD_DATA_SLEEP)
    steps = gen.SCENARIOS["sleep"]["steps"]
    frames = simulate(
        pw.world_map,
        steps,
        personas=pw.personas,
        build_world_fn=pw.build_world_fn,
        extra_action_names=PENN_ACTION_VERBS,
    )
    for frame in frames:
        for name in (_SLEEPER, _PASSERBY):
            assert not frame[name].get("chat")
