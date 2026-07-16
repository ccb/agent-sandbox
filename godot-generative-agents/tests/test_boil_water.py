"""Boil-water action layer (#300): verbs, props, mock replay, memory.

Spec: godot-generative-agents/docs/specs/2026-07-09-boil-water-action-layer.md
"""

import pytest

from backend.build_world import _normalize_personas, build_world
from backend.actions import DrinkPenn, Activate, Deactivate, BoilWater
from backend.penn.penn_world import (
    PENN_EXTRA_ACTIONS,
    _furnish_boil_water,
    build_penn_world,
    make_boil_stove,
    make_murky_pot,
)
from backend.run_simulation import SICK_EMOJI, _resting_pron, simulate
from text_adventure_games.enums import Property
from text_adventure_games.things.items import Item

# -- a tiny two-room world, no tile map -----------------------------------
LOCATIONS = [
    {
        "name": "Campus",
        "description": "The campus green.",
        "address": None,
        "hub": True,
    },
    {"name": "Union", "description": "The student union.", "address": None},
]


def _persona(schedule):
    return {
        "name": "Testa",
        "home": "Union",
        "persona": "I am Testa, a test persona.",
        "emoji": "🙂",
        "start_tile": [0, 0],
        "schedule": schedule,
    }


def _tiny_world(extra_actions=()):
    """(game, char) for a one-persona world with the given extra actions."""
    personas = _normalize_personas(
        [_persona([{"place": "Union", "activity": "hanging out", "steps": 5}])]
    )
    game, chars = build_world(
        None, personas, LOCATIONS, extra_actions=list(extra_actions)
    )
    return game, chars["Testa"]


def _cup(unboiled=True):
    cup = Item(
        "cup of murky water", "a cup of murky water", "Cloudy, untreated tap water."
    )
    cup.set_property(Property.DRINKABLE, True)
    if unboiled:
        cup.set_property("requires_boiling", True)
        cup.set_property("is_boiled", False)
    return cup


def test_drink_override_is_registered():
    game, _ = _tiny_world(extra_actions=[DrinkPenn])
    assert game.parser.actions["drink"] is DrinkPenn


def test_unboiled_drink_sickens_and_logs_event():
    game, char = _tiny_world(extra_actions=[DrinkPenn])
    game.locations["Union"].add_item(_cup())
    assert game.parser.parse_command("get cup of murky water", actor=char)
    assert game.parser.parse_command("drink cup of murky water", actor=char)
    assert char.get_property("is_sick") is True
    sick = [e for e in game.events if e.action == "sickness"]
    assert len(sick) == 1
    assert sick[0].payload["item"] == "cup of murky water"
    assert sick[0].payload["location"] == "Union"


def test_clean_drink_has_no_sickness():
    game, char = _tiny_world(extra_actions=[DrinkPenn])
    game.locations["Union"].add_item(_cup(unboiled=False))
    assert game.parser.parse_command("get cup of murky water", actor=char)
    assert game.parser.parse_command("drink cup of murky water", actor=char)
    assert not char.get_property("is_sick")
    assert not [e for e in game.events if e.action == "sickness"]


def test_boiled_water_is_safe_to_drink():
    # The success condition #301's self-coded boil aims for: once is_boiled
    # is set, the same requires_boiling water no longer sickens.
    game, char = _tiny_world(extra_actions=[DrinkPenn])
    cup = _cup()
    cup.set_property("is_boiled", True)
    game.locations["Union"].add_item(cup)
    assert game.parser.parse_command("get cup of murky water", actor=char)
    assert game.parser.parse_command("drink cup of murky water", actor=char)
    assert not char.get_property("is_sick")
    assert not [e for e in game.events if e.action == "sickness"]


def test_activate_and_deactivate_toggle_a_device():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    game.locations["Union"].add_item(make_boil_stove())
    assert game.parser.parse_command("activate stove", actor=char)
    stove = game.locations["Union"].items["stove"]
    assert stove.get_property("is_on") is True
    # Already on: the second activate fails at the precondition gate.
    assert not game.parser.parse_command("activate stove", actor=char)
    assert game.parser.parse_command("deactivate stove", actor=char)
    assert stove.get_property("is_on") is False


def test_activate_rejects_a_non_device():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    pot = Item("pot", "a cooking pot", "An empty steel pot.")
    game.locations["Union"].add_item(pot)
    assert not game.parser.parse_command("activate pot", actor=char)
    assert not pot.get_property("is_on")


# -- PennParser.determine_intent regression tests (#300) -------------------
#
# PennParser overrides determine_intent only to catch "activate"/"deactivate"
# before they'd otherwise fall into the engine's buggy "ate " substring check
# (text_adventure_games/parsing.py ~line 296-302, which matches "ate " inside
# "activate" and mis-routes it to EAT). Everything else must delegate to
# Parser.determine_intent unchanged -- these tests pin both the new-verb
# handling and that the delegated path still behaves like the engine parser.


def test_activate_and_deactivate_are_routed_to_device_intents():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    assert game.parser.determine_intent("activate stove", actor=char) == "activate"
    assert game.parser.determine_intent("deactivate stove", actor=char) == "deactivate"


def test_eat_still_word_matches_via_delegation():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    assert game.parser.determine_intent("eat bread", actor=char) == "eat"


def test_drink_still_matches_via_delegation():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    assert (
        game.parser.determine_intent("drink cup of murky water", actor=char) == "drink"
    )


def test_custom_action_fallback_routing_intact_through_delegation():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    assert game.parser.determine_intent("travel to Union", actor=char) == "travel"


# -- authored per-stop commands: normalization, mock replay, action_names --

from backend.cognition import ScheduleMockClient, attach_agents

COMMANDS = ["get cup of murky water", "drink cup of murky water"]


def _commands_persona():
    return _persona(
        [
            {
                "place": "Union",
                "activity": "hanging out",
                "steps": 5,
                "commands": list(COMMANDS),
            }
        ]
    )


def test_normalize_passes_commands_through():
    spec = _normalize_personas([_commands_persona()])[0]
    assert spec["schedule"][0]["commands"] == COMMANDS
    # Stops authored without commands get an empty list, uniformly.
    other = _normalize_personas([_persona([{"place": "Union", "activity": "idling"}])])[
        0
    ]
    assert other["schedule"][0]["commands"] == []


def test_mock_brain_replays_authored_commands_then_performs():
    schedule = _normalize_personas([_commands_persona()])[0]["schedule"]
    brain = ScheduleMockClient(schedule)
    away, here = "Campus\nThe green.", "Union\nThe union."
    assert brain._choose(away) == "travel to Union"
    assert brain._choose(here) == "get cup of murky water"
    assert brain._choose(here) == "drink cup of murky water"
    assert brain._choose(here) == "perform hanging out"
    assert brain._choose(here) == "perform hanging out"


def test_replace_schedule_carries_authored_commands_through_stop_round_trip():
    """Latent defect (found by Task 6): the engine's ``planning.Stop`` has no
    ``commands`` field, so ``Stop.to_schedule_entry()`` silently drops any
    authored per-stop commands. ``replace_schedule`` must patch that loss back
    in for a matching stop (same place/activity), so a plan built via
    ``Stop.from_schedule_entry`` -> ``Stop.to_schedule_entry`` (what
    ``MockPlanner``/``LLMPlanner`` do) still replays the authored commands."""
    schedule = _normalize_personas([_commands_persona()])[0]["schedule"]
    brain = ScheduleMockClient(schedule)

    # Simulate the Stop round-trip: same place/activity/steps, but no
    # "commands" key at all (as if it went through planning.Stop).
    round_tripped = [
        {k: v for k, v in stop.items() if k != "commands"} for stop in schedule
    ]
    brain.replace_schedule(round_tripped)

    here = "Union\nThe union."
    assert brain._choose(here) == "get cup of murky water"
    assert brain._choose(here) == "drink cup of murky water"
    assert brain._choose(here) == "perform hanging out"

    # A replacement stop that differs in place is a genuinely new/revised stop
    # -- it must NOT inherit the old stop's commands.
    brain2 = ScheduleMockClient(schedule)
    different_place = [{**schedule[0], "place": "Campus"}]
    different_place[0].pop("commands", None)
    brain2.replace_schedule(different_place)
    assert brain2._stop.get("commands") in (None, [])
    assert brain2._choose("Campus\nThe green.") == "perform hanging out"


def test_action_names_include_authored_verbs():
    personas = _normalize_personas([_commands_persona()])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas)
    assert chars["Testa"].agent.action_names == ["travel", "perform", "drink", "get"]


def test_wait_commands_never_enter_the_tool_enum():
    """Finding A (#590 review): `wait` is a deliberately-excluded idle verb, so
    even if an authored stop uses it as a spacer it must never be promoted to a
    real brain's tool enum -- a Wait schema on every decide is token spend that
    invites idling."""
    persona = _persona(
        [
            {
                "place": "Union",
                "activity": "hanging out",
                "steps": 5,
                "commands": ["wait", "get cup of murky water", "wait"],
            }
        ]
    )
    personas = _normalize_personas([persona])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas)
    names = chars["Testa"].agent.action_names
    assert "wait" not in names
    assert "get" in names  # the real authored verb still made it in


# -- extra_action_names: Penn's real-brain verb set (spec §3, final review) --

PENN_ACTION_VERBS = ["get", "drink", "activate", "deactivate"]


def test_extra_action_names_yields_penn_verb_set_with_authored_commands():
    """A commands-bearing persona (authoring "get"/"drink") plus the Penn
    extra_action_names must yield exactly the spec §3 verb set, with no
    duplicates -- "get"/"drink" appear once even though both the authored
    commands and extra_action_names name them."""
    personas = _normalize_personas([_commands_persona()])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, extra_action_names=PENN_ACTION_VERBS)
    assert chars["Testa"].agent.action_names == [
        "travel",
        "perform",
        "get",
        "drink",
        "activate",
        "deactivate",
    ]


def test_extra_action_names_yields_penn_verb_set_without_authored_commands():
    """Even a persona with NO authored commands (a non-Sofia persona) must get
    the full real-brain verb set when extra_action_names is passed -- this is
    the bug the final review caught: a real LLM brain has a closed action
    enum, so it could never choose "get"/"drink"/"activate"/"deactivate"
    without them being handed in explicitly."""
    personas = _normalize_personas(
        [_persona([{"place": "Union", "activity": "hanging out", "steps": 5}])]
    )
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, extra_action_names=PENN_ACTION_VERBS)
    assert chars["Testa"].agent.action_names == [
        "travel",
        "perform",
        "get",
        "drink",
        "activate",
        "deactivate",
    ]


# -- remember_outcome memory branching (#300) --------------------------------

from backend.cognition import memory_stream_for_persona, remember_outcome


def _attached_char():
    personas = _normalize_personas([_commands_persona()])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas)
    return chars["Testa"]


def test_sick_drink_is_remembered_at_high_importance():
    char = _attached_char()
    # DrinkPenn sets both during apply_effects: is_sick (ongoing state) and
    # just_sickened (one-shot transition marker remember_outcome keys off).
    char.set_property("is_sick", True)
    char.set_property("just_sickened", True)
    remember_outcome(char, "drink pot of murky water", 7)
    entries = memory_stream_for_persona(char.agent)
    sick = [e for e in entries if "terribly sick" in e["text"]]
    assert sick, f"no sick memory in {[e['text'] for e in entries]}"
    assert sick[-1]["importance"] == 8.0
    # Full render pinned (README says these are exact-pinned to guard escaping).
    assert (
        sick[-1]["text"]
        == "I drank the pot of murky water and now I feel terribly sick."
    )
    # The one-shot marker is consumed so a later clean drink doesn't reuse it.
    assert char.get_property("just_sickened") is False


def test_recovered_drink_is_remembered_at_mid_importance():
    # The recovery half (#300 arc): DrinkPenn sets just_recovered on the
    # sick->well transition, so the card shows a "feel much better" memory at
    # mid importance (5.0), and the one-shot marker is consumed.
    char = _attached_char()
    char.set_property("just_recovered", True)
    remember_outcome(char, "drink pot of murky water", 9)
    entries = memory_stream_for_persona(char.agent)
    rec = [e for e in entries if "feel much better" in e["text"]]
    assert rec, f"no recovery memory in {[e['text'] for e in entries]}"
    assert rec[-1]["importance"] == 5.0
    # Finding 13: pin the full render, not a substring -- the punctuation in
    # the middle is exactly what the escaping-guard convention protects.
    assert (
        rec[-1]["text"]
        == "I drank the pot of murky water, and the sickness has finally "
        "passed -- I feel much better."
    )
    assert char.get_property("just_recovered") is False


def test_transition_markers_are_consumed_regardless_of_verb_token():
    """Finding 2 (#590 review): the sicken/recover markers must be consumed by
    their presence, not by a first-token verb == "drink". A comma
    ActionSequence ("get ..., drink ...") parses with verb "get" and free brain
    text ("have a drink ...") with "have", so a verb gate would leak the marker
    into the NEXT drink -- recording it as BOTH sickened and recovered and
    inverting the arc's payoff."""
    char = _attached_char()
    char.set_property("just_recovered", True)
    # verb token is "have", not "drink":
    remember_outcome(char, "have a drink of the clean water", 9)
    entries = memory_stream_for_persona(char.agent)
    assert any("feel much better" in e["text"] for e in entries)
    assert entries[-1]["importance"] == 5.0
    # Consumed: a later drink can't re-fire the recovery memory.
    assert char.get_property("just_recovered") is False


def test_clean_drink_while_still_sick_stays_normal_importance():
    """Fix #2 (final review): a still-sick agent drinking a CLEAN liquid must
    not misattribute "terribly sick" to this drink -- remember_outcome keys off
    the one-shot just_sickened transition marker, not the ongoing is_sick
    property, so a stale is_sick alone doesn't trigger the high-importance
    memory."""
    char = _attached_char()
    char.set_property("is_sick", True)  # still sick from an earlier drink
    # just_sickened is NOT set -- this drink itself didn't cause it.
    remember_outcome(char, "drink cup of murky water", 7)
    entries = memory_stream_for_persona(char.agent)
    drank = [e for e in entries if e["text"] == "I drank the cup of murky water."]
    assert drank, f"no normal drink memory in {[e['text'] for e in entries]}"
    assert drank[-1]["importance"] == 2.0
    assert not any("terribly sick" in e["text"] for e in entries)


def test_clean_drink_is_remembered_at_normal_importance():
    char = _attached_char()
    remember_outcome(char, "drink cup of murky water", 7)
    entries = memory_stream_for_persona(char.agent)
    drank = [e for e in entries if e["text"] == "I drank the cup of murky water."]
    assert drank and drank[-1]["importance"] == 2.0


def test_boil_is_remembered_as_the_arc_hinge():
    """Finding 3 (#590 review): boiling is the corrective hinge of the arc, so
    it must rank as a meaningful causal memory -- above a plain get (2.0) and
    the passive recovery drink (5.0) -- not fall to the 1.0 catch-all where the
    #299/#301 importance-weighted retrieval would treat it as noise."""
    char = _attached_char()
    remember_outcome(char, "boil water", 5)
    entries = memory_stream_for_persona(char.agent)
    boiled = [e for e in entries if "boiled the water" in e["text"]]
    assert boiled, f"no boil memory in {[e['text'] for e in entries]}"
    assert boiled[-1]["text"] == "I boiled the water to make it safe to drink."
    assert boiled[-1]["importance"] == 6.0


def test_wait_is_not_remembered_at_all():
    """Finding 5 (#590 review): a `wait` writes no memory -- otherwise a run
    accrues identical 1.0 "I did wait" entries that crowd the card and feed the
    reflection accumulator with filler."""
    char = _attached_char()
    before = len(memory_stream_for_persona(char.agent))
    remember_outcome(char, "wait", 4)
    after = memory_stream_for_persona(char.agent)
    assert len(after) == before
    assert not any(e["text"] == 'I did "wait".' for e in after)


def test_get_is_remembered_at_normal_importance():
    char = _attached_char()
    remember_outcome(char, "get pot", 3)
    entries = memory_stream_for_persona(char.agent)
    got = [e for e in entries if e["text"] == 'I did "get pot".']
    assert got and got[-1]["importance"] == 2.0


@pytest.mark.parametrize(
    "command",
    ["activate stove", "deactivate stove"],
    ids=["activate", "deactivate"],
)
def test_device_verbs_are_remembered_at_normal_importance(command):
    """Cheap coverage close (final review): activate/deactivate share the
    "get"/quoted-fallback branch in remember_outcome -- pin both explicitly
    alongside the existing "get" case."""
    char = _attached_char()
    remember_outcome(char, command, 3)
    entries = memory_stream_for_persona(char.agent)
    got = [e for e in entries if e["text"] == f'I did "{command}".']
    assert got and got[-1]["importance"] == 2.0


# -- the sickness emoji rides the frame's pron authority chain (#590 finding 1) -


def test_resting_pron_routes_sickness_below_the_model_pick():
    """Finding 1 (#590 review): the #300 health cue is folded into the emoji
    authority chain (a low-priority overlay), not stamped as a frame-time
    override. A model's explicit pick still wins; else a sick agent wears the
    queasy face; else the stop / persona emoji."""
    char = _attached_char()
    schedule = char.agent.schedule
    default = "🙂"

    # Healthy, on-plan: the stop's emoji (or persona default).
    char.set_property("is_sick", False)
    char.agent.last_emoji = None
    assert (
        _resting_pron(char, schedule, True, "Testa", {"Testa": default}) != SICK_EMOJI
    )

    # Sick, no model pick: the sickness cue.
    char.set_property("is_sick", True)
    assert (
        _resting_pron(char, schedule, True, "Testa", {"Testa": default}) == SICK_EMOJI
    )

    # Sick, but the model chose an emoji: the model's pick still wins.
    char.agent.last_emoji = "😀"
    assert _resting_pron(char, schedule, True, "Testa", {"Testa": default}) == "😀"


# -- the real Penn world: furnished Houston Hall + Sofia's authored stop (#300) -


def test_houston_hall_is_stocked_and_the_scenario_plays():
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    hall = game.locations["Houston Hall"]
    for name in ("sink", "stove", "pot of murky water"):
        assert name in hall.items, f"{name} missing from Houston Hall"
    sofia = chars["Sofia Ramirez"]
    assert game.parser.parse_command("travel to Houston Hall", actor=sofia)
    # 1) drink the raw water -> sick
    assert game.parser.parse_command("get pot of murky water", actor=sofia)
    assert game.parser.parse_command("drink pot of murky water", actor=sofia)
    assert sofia.get_property("is_sick") is True
    assert any(e.action == "sickness" for e in game.events)
    # 2) boil it -> the pot is marked safe (name kept: still "pot of murky water")
    assert game.parser.parse_command("boil water", actor=sofia)
    pot = sofia.inventory["pot of murky water"]
    assert pot.get_property("is_boiled") is True
    # 3) drink the same (now boiled) pot -> recover
    assert game.parser.parse_command("drink pot of murky water", actor=sofia)
    assert sofia.get_property("is_sick") is False
    assert any(e.action == "recovery" for e in game.events)


def test_boil_marks_the_real_houston_pot_safe_and_keeps_its_name():
    """In the furnished Houston Hall, boiling the carried pot marks it safe
    without renaming it, and the boiled water no longer sickens."""
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    sofia = chars["Sofia Ramirez"]
    assert game.parser.parse_command("travel to Houston Hall", actor=sofia)
    assert game.parser.parse_command("get pot of murky water", actor=sofia)
    assert game.parser.parse_command("boil water", actor=sofia)
    pot = sofia.inventory["pot of murky water"]  # name unchanged
    assert pot.get_property("is_boiled") is True
    assert game.parser.parse_command("drink pot of murky water", actor=sofia)
    assert not sofia.get_property("is_sick")


def test_penn_action_verbs_include_boil():
    from backend.penn.penn_world import PENN_ACTION_VERBS
    from backend.cognition import attach_agents

    personas = _normalize_personas([_commands_persona()])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, extra_action_names=PENN_ACTION_VERBS)
    assert "boil" in chars["Testa"].agent.action_names


def test_sofias_houston_hall_stop_carries_the_arc_commands():
    # Sofia's arc runs across the same-place Houston Hall stops (no `wait`
    # spacers -- the stops' `steps:` gaps separate the events). Gather the
    # authored commands across those stops in order.
    pw = build_penn_world()
    sofia = next(p for p in pw.personas if p["name"] == "Sofia Ramirez")
    cmds = [
        c
        for s in sofia["schedule"]
        if s["place"] == "Houston Hall"
        for c in (s.get("commands") or [])
    ]
    assert cmds == [
        "get pot of murky water",
        "drink pot of murky water",
        "boil water",
        "drink pot of murky water",
    ]
    # No wait spacers survived the de-clumping (finding 7).
    assert "wait" not in cmds


# -- BoilWater: the self-contained boil superaction (#300 test scaffold) -----


def _boil_world():
    """Tiny world with the boil verb + drink override; Union holds a stove and
    a reusable pot of murky water (the SAME factories the real Houston Hall
    uses, so the tiny-world props can't drift -- finding 12)."""
    game, char = _tiny_world(extra_actions=[BoilWater, DrinkPenn, Activate])
    union = game.locations["Union"]
    union.add_item(make_boil_stove())
    union.add_item(make_murky_pot())
    return game, char, union


def test_boil_is_registered():
    game, _ = _tiny_world(extra_actions=[BoilWater])
    assert game.parser.actions["boil"] is BoilWater


def test_boil_marks_water_safe_and_turns_stove_on():
    # The visible state change: the vessel is marked is_boiled IN PLACE (name
    # kept), its description updated, and the stove switched on.
    game, char, union = _boil_world()
    assert game.parser.parse_command("boil water", actor=char)
    pot = union.items["pot of murky water"]  # name unchanged
    assert pot.get_property("is_boiled") is True
    assert "boiled" in pot.description.lower()
    assert union.items["stove"].get_property("is_on") is True


def test_boiled_event_is_logged_with_a_scalar_item():
    game, char, union = _boil_world()
    assert game.parser.parse_command("boil water", actor=char)
    boiled = [e for e in game.events if e.action == "boiled"]
    assert len(boiled) == 1
    assert boiled[0].payload["location"] == "Union"
    # Scalar "item" matching the sibling sickness/recovery events (finding 10).
    assert boiled[0].payload["item"] == "pot of murky water"


def test_full_arc_sicken_then_boil_then_recover():
    # The whole watchable arc against the tiny world: drink raw -> sick; boil
    # (marks the carried pot safe in place); drink the SAME pot -> well.
    game, char, union = _boil_world()
    assert game.parser.parse_command("get pot of murky water", actor=char)
    assert game.parser.parse_command("drink pot of murky water", actor=char)
    assert char.get_property("is_sick") is True
    assert [e for e in game.events if e.action == "sickness"]

    assert game.parser.parse_command("boil water", actor=char)
    assert [e for e in game.events if e.action == "boiled"]
    pot = char.inventory["pot of murky water"]  # name unchanged
    assert pot.get_property("is_boiled") is True

    assert game.parser.parse_command("drink pot of murky water", actor=char)
    assert char.get_property("is_sick") is False
    assert [e for e in game.events if e.action == "recovery"]


def test_recovery_requires_boiled_water_not_just_any_safe_drink():
    """Finding 4 (#590 review): the cure is gated on is_boiled, not "any
    successful drink while sick". A sick agent drinking an unrelated safe
    beverage must NOT recover -- otherwise the #301 "did it learn to boil?"
    comparison can't tell boiling from drinking anything."""
    game, char, union = _boil_world()
    # Get sick off the raw water.
    assert game.parser.parse_command("get pot of murky water", actor=char)
    assert game.parser.parse_command("drink pot of murky water", actor=char)
    assert char.get_property("is_sick") is True
    # A clean, never-contaminated beverage (no is_boiled) does NOT cure.
    juice = Item("cup of juice", "a cup of juice", "Cold apple juice.")
    juice.set_property(Property.DRINKABLE, True)
    char.add_to_inventory(juice)
    assert game.parser.parse_command("drink cup of juice", actor=char)
    assert char.get_property("is_sick") is True
    assert not [e for e in game.events if e.action == "recovery"]


def test_boil_fails_without_a_stove():
    game, char = _tiny_world(extra_actions=[BoilWater])
    union = game.locations["Union"]
    union.add_item(make_murky_pot())
    assert not game.parser.parse_command("boil water", actor=char)
    assert union.items["pot of murky water"].get_property("is_boiled") is False


def test_boil_fails_with_nothing_to_boil():
    # Stove present but the only water is already boiled -> clean failure.
    game, char = _tiny_world(extra_actions=[BoilWater])
    union = game.locations["Union"]
    union.add_item(make_boil_stove())
    pot = make_murky_pot()
    pot.set_property("is_boiled", True)
    union.add_item(pot)
    assert not game.parser.parse_command("boil water", actor=char)


# -- end-to-end acceptance: mock-brain runs of the arc (#300) ----------------


def _mock_penn_run(schedule, steps, name="Testa Boil", emoji="🍵"):
    """Run a single-persona mock bake in the furnished Penn world and return
    ``(memories, events)``. Shared by the end-to-end tests so they can't drift
    in their persona/build_fn/simulate scaffolding (finding 12)."""
    pw = build_penn_world()
    persona = {
        "name": name,
        "home": "Houston Hall",
        "persona": f"I am {name}, a test persona.",
        "emoji": emoji,
        "start_tile": [25, 109],
        "schedule": schedule,
    }
    personas = _normalize_personas([persona])

    def build_fn(wm):
        game, characters = build_world(
            wm, personas, pw.locations, extra_actions=PENN_EXTRA_ACTIONS
        )
        _furnish_boil_water(game)
        return game, characters

    memories, events = {}, []
    simulate(
        pw.world_map,
        steps,
        personas=personas,
        build_world_fn=build_fn,
        out_memories=memories,
        out_events=events,
    )
    return memories, events


def test_end_to_end_mock_run_agent_drinks_and_gets_sick():
    """#300 acceptance: in a mock-brain run, an agent drinks, gets sick, and the
    high-importance observation lands in its memory stream."""
    schedule = [
        {
            "place": "Houston Hall",
            "activity": "getting a drink of water",
            "emoji": "🥤",
            "steps": 3,
            "commands": ["get pot of murky water", "drink pot of murky water"],
        }
    ]
    memories, _ = _mock_penn_run(schedule, 10, name="Testa Sip", emoji="🥤")
    stream = memories["Testa Sip"]
    sick = [m for m in stream if "terribly sick" in m["text"]]
    assert sick, f"no sickness memory in {[m['text'] for m in stream]}"
    assert sick[0]["importance"] == 8.0


def test_end_to_end_mock_run_full_arc_sick_boil_recover():
    """The scaffold's payoff in a mock run: the authored arc fires end to end --
    a high-importance sickness memory lands, and the sickness -> boiled ->
    recovery events all appear (the exact sequence the viewer's timeline shows).
    The recovery drink names the same pot ("pot of murky water"): boiling only
    flipped its is_boiled flag."""
    schedule = [
        {
            "place": "Houston Hall",
            "activity": "sorting out the water",
            "emoji": "🍵",
            "steps": 6,
            "commands": [
                "get pot of murky water",
                "drink pot of murky water",
                "boil water",
                "drink pot of murky water",
            ],
        }
    ]
    memories, events = _mock_penn_run(schedule, 14)
    actions = [e["action"] for e in events]
    assert "sickness" in actions
    assert "boiled" in actions
    assert "recovery" in actions
    # sickness precedes recovery in the change feed
    assert actions.index("sickness") < actions.index("recovery")
    stream = memories["Testa Boil"]
    assert any("terribly sick" in m["text"] for m in stream)
