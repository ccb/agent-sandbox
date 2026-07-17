"""The de-clumped boil-water DEMO scenario (#592).

`generate_penn_replay.py --scenario boil` bakes a short, single-persona replay of
the drink -> sicken -> boil -> recover arc (#300) so it plays *early* and spread
across the scrubber, instead of clustering at ~step 945 of Sofia's ~1100-step day
in the bundled bake. These tests pin the scenario world, the arc's on-timeline
placement, the "quiet" spacing (no wait-marker flood), the verb-free-activity
invariant the multi-stop spacing depends on, and that the full campus world is
untouched.
"""

import pytest

from backend.penn.penn_world import (
    PENN_ACTION_VERBS,
    WORLD_DATA_BOIL,
    build_penn_world,
)
from backend.run_simulation import simulate

# Import the generator's scenario table without triggering a bake (main() is
# __main__-guarded). The generator imports its sibling `penn_world` by bare name --
# it relies on its own directory being on sys.path, as it is when run as a script --
# so we add that directory before importing it as a package module.
import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "penn"))
)
from backend.penn import generate_penn_replay as gen  # noqa: E402


def _event_actions(events):
    return [e["action"] if isinstance(e, dict) else e.action for e in events]


def _event_step(e):
    return e.get("turn", e.get("step")) if isinstance(e, dict) else e.turn


# --- the scenario world -----------------------------------------------------


def test_scenarios_table_wires_the_boil_scenario():
    """`--scenario boil` selects the boil world YAML + its own output file, so the
    demo bakes ALONGSIDE (never over) the bundled replay."""
    boil = gen.SCENARIOS["boil"]
    assert boil["world_data"] == WORLD_DATA_BOIL
    assert boil["out"] == "penn_replay_boil.json"
    # The default full-cast scenario stays the bundled replay.
    assert gen.SCENARIOS["penn"]["out"] == "penn_replay.json"
    assert "penn" in gen.SCENARIOS and gen.SCENARIOS["penn"]["steps"] > 100


def test_boil_world_is_a_single_houston_persona_with_the_props():
    """The scenario is one Houston-homed persona (so the arc runs from step 0 with
    no cross-campus commute), and the shared factory still stocks Houston Hall with
    the boil props (the murky pot + sink + stove)."""
    pw = build_penn_world(world_data=WORLD_DATA_BOIL)
    assert len(pw.personas) == 1
    (persona,) = pw.personas
    assert persona["home"] == "Houston Hall"
    # No meetings/relationships to inject for a solo demo.
    assert pw.meetings == []
    assert pw.relationships == []
    game, _chars = pw.build_world_fn(pw.world_map)
    hall = game.locations.get("Houston Hall")
    for name in ("pot of murky water", "sink", "stove"):
        assert name in hall.items, f"{name} missing from Houston Hall"


def test_boil_activities_are_verb_free():
    """The multi-stop spacing performs `perform <activity>` between commands, and
    the parser re-reads that text -- so an activity containing an action verb (or
    the substring "ate") is mis-parsed as that command and spams failures (the #535
    "Diego's 'late' -> EAT" hazard). Guard every demo activity against it, since
    that misparse would NOT fail the arc events and so slips past the bake test."""
    pw = build_penn_world(world_data=WORLD_DATA_BOIL)
    (persona,) = pw.personas
    # Substrings that would trip the keyword parser (verbs + the classic "l-ate").
    hazards = [
        "drink",
        "boil",
        "activate",
        "deactivate",
        "ate",
        " get ",
        " go ",
        " take ",
        " use ",
        " look ",
        " wait ",
    ]
    for stop in persona["schedule"]:
        activity = f" {stop['activity'].lower()} "
        bad = [h for h in hazards if h in activity]
        assert not bad, f"activity {stop['activity']!r} contains parser hazard {bad}"


# --- the baked arc on the timeline ------------------------------------------


@pytest.fixture(scope="module")
def boil_bake():
    """Bake the boil scenario once (the generator's default step budget) and hand
    the tests the events + frames. Mock brain: offline, deterministic, free."""
    pw = build_penn_world(world_data=WORLD_DATA_BOIL)
    steps = gen.SCENARIOS["boil"]["steps"]
    memories, events = {}, []
    frames = simulate(
        pw.world_map,
        steps,
        personas=pw.personas,
        build_world_fn=pw.build_world_fn,
        out_memories=memories,
        out_events=events,
        extra_action_names=PENN_ACTION_VERBS,
    )
    name = pw.personas[0]["name"]
    return {"steps": steps, "events": events, "frames": frames, "name": name}


def test_arc_fires_in_order(boil_bake):
    actions = _event_actions(boil_bake["events"])
    for kind in ("sickness", "boiled", "recovery"):
        assert kind in actions, f"{kind} missing from {actions}"
    assert (
        actions.index("sickness") < actions.index("boiled") < actions.index("recovery")
    )


def test_arc_is_early_and_clearly_separated(boil_bake):
    """The point of #592: the three events start early and spread across most of the
    timeline, clearly apart -- not clustered at the far-right end."""
    n = boil_bake["steps"]
    step = {
        e["action"]: _event_step(e)
        for e in boil_bake["events"]
        if e["action"] in ("sickness", "boiled", "recovery")
    }
    # Strictly increasing, and each event well clear of the next (>= 15 steps).
    assert step["sickness"] < step["boiled"] < step["recovery"]
    assert step["boiled"] - step["sickness"] >= 15
    assert step["recovery"] - step["boiled"] >= 15
    # Starts early (first event within the first third) ...
    assert step["sickness"] <= n / 3
    # ... and the arc fills most of the timeline (recovery past the midpoint, but
    # not jammed against the very end -- room for a recovered tail).
    assert n * 0.5 <= step["recovery"] <= n * 0.9


def test_timeline_is_not_flooded_with_wait_markers(boil_bake):
    """`steps:` gaps space the events with quiet `perform` blocks (one marker each),
    NOT explicit `wait` commands (one marker PER step) -- so the scrubber isn't
    drowned in markers. The whole run should log only a handful of events."""
    actions = _event_actions(boil_bake["events"])
    assert "wait" not in actions
    assert len(boil_bake["events"]) <= 20, actions


def test_sick_emoji_shows_then_reverts(boil_bake):
    """The sprite reads as sick (🤢) through the sick window and reverts once the
    boiled water is drunk -- the visible half of the arc (#590)."""
    frames, name = boil_bake["frames"], boil_bake["name"]
    emojis = [f[name]["pronunciatio"] for f in frames]
    sick = [i for i, e in enumerate(emojis) if e == "\U0001f922"]  # 🤢
    assert sick, "agent never showed the sick emoji"
    # Recovered by the end (the tail shows a healthy sprite again).
    assert emojis[-1] != "\U0001f922"


# --- the full campus world is untouched -------------------------------------


def test_full_world_still_carries_sofias_arc():
    """Acceptance: the bundled replay / Sofia's curated day are unaffected -- the
    demo is additive. The default world still has the full cast and Sofia's Houston
    boil stop."""
    pw = build_penn_world()  # the default full-cast world
    assert len(pw.personas) > 1
    sofia = next((p for p in pw.personas if p["name"] == "Sofia Ramirez"), None)
    assert sofia is not None
    houston = [s for s in sofia["schedule"] if s["place"] == "Houston Hall"]
    assert houston, "Sofia's Houston Hall stop went missing"
    # #590 splits Sofia's arc across several same-place Houston stops (boil sits
    # in the middle one), so gather the commands across all of them.
    commands = [c for s in houston for c in (s.get("commands") or [])]
    assert "make boiled water" in commands  # boiling is the crafting recipe (#300)
