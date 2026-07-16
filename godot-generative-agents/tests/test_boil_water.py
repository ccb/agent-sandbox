"""Boil-water action layer (#300): verbs, props, mock replay, memory.

Spec: godot-generative-agents/docs/specs/2026-07-09-boil-water-action-layer.md
"""

import pytest

from backend.build_world import _normalize_personas, build_world
from backend.actions import DrinkPenn, Activate, Deactivate
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


def _stove():
    stove = Item("stove", "a small electric stove", "A single coil burner.")
    stove.set_property(Property.GETTABLE, False)
    stove.set_property("is_device", True)
    return stove


def test_activate_and_deactivate_toggle_a_device():
    game, char = _tiny_world(extra_actions=[Activate, Deactivate])
    game.locations["Union"].add_item(_stove())
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
    remember_outcome(char, "drink cup of murky water", 7)
    entries = memory_stream_for_persona(char.agent)
    sick = [e for e in entries if "terribly sick" in e["text"]]
    assert sick, f"no sick memory in {[e['text'] for e in entries]}"
    assert sick[-1]["importance"] == 8.0
    assert "I drank the cup of murky water" in sick[-1]["text"]
    # The one-shot marker is consumed so a later clean drink doesn't reuse it.
    assert char.get_property("just_sickened") is False


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


# -- the real Penn world: furnished Houston Hall + Sofia's authored stop (#300) -

from backend.penn.penn_world import build_penn_world


def test_houston_hall_is_stocked_and_the_scenario_plays():
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    hall = game.locations["Houston Hall"]
    for name in (
        "sink",
        "stove",
        "pot",
        "cup of murky water",
        "second cup of murky water",
    ):
        assert name in hall.items, f"{name} missing from Houston Hall"
    sofia = chars["Sofia Ramirez"]
    assert game.parser.parse_command("travel to Houston Hall", actor=sofia)
    assert game.parser.parse_command("get cup of murky water", actor=sofia)
    assert game.parser.parse_command("drink cup of murky water", actor=sofia)
    assert sofia.get_property("is_sick") is True
    assert any(e.action == "sickness" for e in game.events)
    # The withheld gap (#299): the stove turns on, and nothing heats -- the
    # remaining cup stays unboiled.
    assert game.parser.parse_command("activate stove", actor=sofia)
    second = hall.items["second cup of murky water"]
    assert second.get_property("requires_boiling") is True
    assert not second.get_property("is_boiled")


def test_boil_makes_houston_water_safe_in_the_real_world():
    """In the furnished Houston Hall, boiling makes the raw cups safe: a drink
    afterward does not sicken. (Contrast test_houston_hall_is_stocked...: with
    no boil verb, activating the stove heats nothing.)"""
    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    sofia = chars["Sofia Ramirez"]
    assert game.parser.parse_command("travel to Houston Hall", actor=sofia)
    assert game.parser.parse_command("boil water", actor=sofia)
    hall = game.locations["Houston Hall"]
    assert hall.items["cup of murky water"].get_property("is_boiled") is True
    assert hall.items["second cup of murky water"].get_property("is_boiled") is True
    assert game.parser.parse_command("get cup of murky water", actor=sofia)
    assert game.parser.parse_command("drink cup of murky water", actor=sofia)
    assert not sofia.get_property("is_sick")


def test_penn_action_verbs_include_boil():
    from backend.penn.penn_world import PENN_ACTION_VERBS
    from backend.cognition import attach_agents

    personas = _normalize_personas([_commands_persona()])
    game, chars = build_world(None, personas, LOCATIONS)
    attach_agents(chars, personas, extra_action_names=PENN_ACTION_VERBS)
    assert "boil" in chars["Testa"].agent.action_names


def test_sofias_houston_hall_stop_carries_the_commands():
    pw = build_penn_world()
    sofia = next(p for p in pw.personas if p["name"] == "Sofia Ramirez")
    stop = next(s for s in sofia["schedule"] if s["place"] == "Houston Hall")
    assert stop["commands"] == ["get cup of murky water", "drink cup of murky water"]


# -- end-to-end acceptance: a mock-brain run drinks, sickens, remembers (#300) -

from backend.penn.penn_world import PENN_EXTRA_ACTIONS, _furnish_boil_water
from backend.run_simulation import simulate


def test_end_to_end_mock_run_agent_drinks_and_gets_sick():
    """#300 acceptance: in a mock-brain run, an agent drinks, gets sick, and the
    high-importance observation lands in its memory stream."""
    pw = build_penn_world()
    persona = {
        "name": "Testa Sip",
        "home": "Houston Hall",
        "persona": "I am Testa Sip, a thirsty test persona.",
        "emoji": "🥤",
        "start_tile": [25, 109],
        "schedule": [
            {
                "place": "Houston Hall",
                "activity": "getting a drink of water",
                "emoji": "🥤",
                "steps": 3,
                "commands": ["get cup of murky water", "drink cup of murky water"],
            }
        ],
    }
    personas = _normalize_personas([persona])

    def build_fn(wm):
        game, characters = build_world(
            wm, personas, pw.locations, extra_actions=PENN_EXTRA_ACTIONS
        )
        _furnish_boil_water(game)
        return game, characters

    memories = {}
    simulate(
        pw.world_map,
        10,
        personas=personas,
        build_world_fn=build_fn,
        out_memories=memories,
    )
    stream = memories["Testa Sip"]
    sick = [m for m in stream if "terribly sick" in m["text"]]
    assert sick, f"no sickness memory in {[m['text'] for m in stream]}"
    assert sick[0]["importance"] == 8.0


# -- BoilWater: the self-contained boil superaction (#300 test scaffold) -----

from backend.actions import BoilWater


def _pot():
    pot = Item("pot", "a cooking pot", "An empty steel pot. It could hold water.")
    pot.set_property(Property.GETTABLE, False)
    return pot


def _boil_world():
    """Tiny world with the boil verb + drink override, and Union stocked with a
    pot, a stove, and one unboiled cup."""
    game, char = _tiny_world(extra_actions=[BoilWater, DrinkPenn, Activate])
    union = game.locations["Union"]
    union.add_item(_pot())
    union.add_item(_stove())
    union.add_item(_cup())
    return game, char, union


def test_boil_is_registered():
    game, _ = _tiny_world(extra_actions=[BoilWater])
    assert game.parser.actions["boil"] is BoilWater


def test_boil_marks_water_safe_and_turns_stove_on():
    game, char, union = _boil_world()
    assert game.parser.parse_command("boil water", actor=char)
    assert union.items["cup of murky water"].get_property("is_boiled") is True
    assert union.items["stove"].get_property("is_on") is True


def test_boiled_event_is_logged():
    game, char, union = _boil_world()
    assert game.parser.parse_command("boil water", actor=char)
    boiled = [e for e in game.events if e.action == "boiled"]
    assert len(boiled) == 1
    assert boiled[0].payload["location"] == "Union"
    assert boiled[0].payload["items"] == ["cup of murky water"]


def test_boil_then_drink_does_not_sicken():
    # The core end-to-end signal: once boiled, drinking the same water is safe.
    game, char, union = _boil_world()
    assert game.parser.parse_command("boil water", actor=char)
    assert game.parser.parse_command("get cup of murky water", actor=char)
    assert game.parser.parse_command("drink cup of murky water", actor=char)
    assert not char.get_property("is_sick")
    assert not [e for e in game.events if e.action == "sickness"]


def test_boil_fails_without_a_pot():
    game, char = _tiny_world(extra_actions=[BoilWater])
    union = game.locations["Union"]
    union.add_item(_stove())
    union.add_item(_cup())
    assert not game.parser.parse_command("boil water", actor=char)
    assert union.items["cup of murky water"].get_property("is_boiled") is False


def test_boil_fails_without_a_stove():
    game, char = _tiny_world(extra_actions=[BoilWater])
    union = game.locations["Union"]
    union.add_item(_pot())
    union.add_item(_cup())
    assert not game.parser.parse_command("boil water", actor=char)
    assert union.items["cup of murky water"].get_property("is_boiled") is False


def test_boil_fails_with_nothing_to_boil():
    # Pot + stove present, but no unboiled water -> clean precondition failure.
    game, char = _tiny_world(extra_actions=[BoilWater])
    union = game.locations["Union"]
    union.add_item(_pot())
    union.add_item(_stove())
    union.add_item(_cup(unboiled=False))
    assert not game.parser.parse_command("boil water", actor=char)


def test_end_to_end_mock_run_boil_then_drink_stays_healthy():
    """The scaffold's payoff: a mock-brain run where the agent boils before
    drinking never gets sick, and no sickness memory lands. Mirrors
    test_end_to_end_mock_run_agent_drinks_and_gets_sick, boil-first."""
    pw = build_penn_world()
    persona = {
        "name": "Testa Boil",
        "home": "Houston Hall",
        "persona": "I am Testa Boil, a careful test persona.",
        "emoji": "🍵",
        "start_tile": [25, 109],
        "schedule": [
            {
                "place": "Houston Hall",
                "activity": "boiling water before dinner",
                "emoji": "🍵",
                "steps": 3,
                "commands": [
                    "boil water",
                    "get cup of murky water",
                    "drink cup of murky water",
                ],
            }
        ],
    }
    personas = _normalize_personas([persona])

    def build_fn(wm):
        game, characters = build_world(
            wm, personas, pw.locations, extra_actions=PENN_EXTRA_ACTIONS
        )
        _furnish_boil_water(game)
        return game, characters

    memories = {}
    simulate(
        pw.world_map,
        10,
        personas=personas,
        build_world_fn=build_fn,
        out_memories=memories,
    )
    stream = memories["Testa Boil"]
    assert not any("terribly sick" in m["text"] for m in stream), [
        m["text"] for m in stream
    ]
