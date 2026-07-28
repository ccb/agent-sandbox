"""Arena-tier affordance verbs (issue #615): `study` in `studyable` arenas,
`eat` where an EDIBLE meal is in scope (Houston Hall).

Pins:
* `study` is offered exactly where its gate's place-check passes (#612/#617
  invariant), sets the activity label, and accumulates `studied_minutes`;
* `study` advertises the #581 pacing slots and settles like `perform`;
* `eat` needs no new code -- Houston Hall meals make the engine verb
  offerable there, and the get -> eat two-step clears `is_hungry`;
* the study/eat first-person memory lines.

Fully offline. Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_arena_verbs_615.py -v
"""

import datetime
import sys
from pathlib import Path

# Same import shim as test_pacing_authority_581.py: the Penn sim modules run
# as scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.actions import DEFAULT_STUDY_MINUTES, Study  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import (  # noqa: E402
    action_tools_for,
    attach_agents,
    observe_and_decide,
    remember_outcome,
)
from backend.prompt_templates import render  # noqa: E402
from backend.run_simulation import step  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402
from backend.sim_config import CognitionConfig  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402
from text_adventure_games.llm_client import ToolCallResult  # noqa: E402
from text_adventure_games.things import Item  # noqa: E402

# -- tiny-world harness (mirrors test_pacing_authority_581) ------------------

LOCATIONS = [
    {
        "name": "The Green",
        "description": "the central lawn",
        "address": None,
        "hub": True,
    },
    {"name": "Cafe", "description": "a coffee shop", "address": "T:Cafe:counter"},
    {
        "name": "Library",
        "description": "a small library",
        "address": "T:Library:desks",
        "properties": ["studyable"],
    },
]


def _persona(steps=None, place="Cafe", activity="reading a novel"):
    # Fresh dict per test: attach_agents + the step loop mutate the spec.
    return {
        "name": "Ada",
        "home": "The Green",
        "persona": "I am Ada, a curious first-year.",
        "emoji": "\U0001f4d6",
        "start_tile": [0, 0],
        "destination": place,
        "activity": activity,
        "schedule": [
            {
                "place": place,
                "activity": activity,
                "emoji": "\U0001f4d6",
                "steps": steps,
            }
        ],
    }


class PerActionBrain:
    """A real-shaped brain: answers with one scripted per-action tool call."""

    def __init__(self, name, arguments):
        self._name = name
        self._arguments = arguments
        self.context: dict = {}
        self.offers: list[dict] = []

    def call_tools(
        self, messages, tools, tool_choice="auto", max_tokens=256, temperature=0.0
    ):
        self.offers.append({"tools": tools, "context": dict(self.context)})
        return ToolCallResult(
            text=None,
            tool_calls=[
                {"id": "c1", "name": self._name, "arguments": dict(self._arguments)}
            ],
        )


def _world(llm_client=None, **persona_kw):
    """(game, Ada) with the #615 verbs offered and Study registered."""
    personas = [_persona(**persona_kw)]
    game, chars = build_world(None, personas, LOCATIONS, extra_actions=[Study])
    attach_agents(
        chars, personas, llm_client=llm_client, extra_action_names=["study", "eat"]
    )
    return game, chars["Ada"]


def _move(game, char, dest):
    if char.location is not None:
        char.location.remove_character(char)
    game.locations[dest].add_character(char)


def _tool_names(game, char):
    return {t["name"] for t in action_tools_for(game, char)}


# -- study: offered <=> gate place-check (the #617 invariant) -----------------


def test_study_offered_only_in_a_studyable_arena():
    game, ada = _world()
    # Home (The Green) carries no tag: not offered; universals still are.
    assert "study" not in _tool_names(game, ada)
    assert {"travel", "perform"} <= _tool_names(game, ada)
    _move(game, ada, "Library")
    assert "study" in _tool_names(game, ada)


def test_study_gate_fails_elsewhere_with_actionable_feedback():
    game, ada = _world()  # Ada on The Green, untagged
    assert not game.parser.parse_command("study thermodynamics", actor=ada)
    msg = getattr(game.parser, "last_fail_message", "")
    assert "study" in msg and "here" in msg


# -- study: effects ------------------------------------------------------------


def test_study_sets_activity_and_accumulates_minutes():
    game, ada = _world()
    _move(game, ada, "Library")
    ada.agent.last_duration_minutes = 45  # what _take_pacing_args stashes (#581)
    assert game.parser.parse_command("study thermodynamics", actor=ada)
    assert ada.get_property("activity") == "studying thermodynamics"
    assert ada.get_property("studied_minutes") == 45
    assert ada.get_property("just_studied_minutes") == 45  # Task 3's one-shot
    ada.agent.last_duration_minutes = 25
    assert game.parser.parse_command("study lab reports", actor=ada)
    assert ada.get_property("studied_minutes") == 70  # accumulates across studies


def test_study_without_duration_or_topic_uses_defaults():
    game, ada = _world()
    _move(game, ada, "Library")
    ada.agent.last_duration_minutes = None
    assert game.parser.parse_command("study", actor=ada)
    assert ada.get_property("activity") == "studying"
    assert ada.get_property("studied_minutes") == DEFAULT_STUDY_MINUTES


# -- study: #581 pacing opt-in -------------------------------------------------


def test_study_tool_advertises_the_pacing_slots():
    brain = PerActionBrain("study", {"topic": "thermodynamics"})
    game, ada = _world(llm_client=brain, place="Library")
    _move(game, ada, "Library")  # offered only where afforded
    observe_and_decide(game, ada, 0)
    study = {t["name"]: t for t in brain.offers[0]["tools"]}["study"]
    props = study["parameters"]["properties"]
    assert "duration_minutes" in props
    assert "emoji" in props
    # Everything is optional -- a bare "study" must stay routable.
    assert "topic" not in study["parameters"].get("required", [])


def test_study_meta_args_stash_without_leaking_into_the_command():
    brain = PerActionBrain(
        "study",
        {"topic": "thermodynamics", "duration_minutes": 45, "emoji": "\U0001f4da"},
    )
    game, ada = _world(llm_client=brain, place="Library")
    _move(game, ada, "Library")
    command = observe_and_decide(game, ada, 0)
    assert command == "study thermodynamics"  # no "45", no emoji spliced in
    assert ada.agent.last_duration_minutes == 45
    assert ada.agent.last_emoji == "\U0001f4da"


# -- study: settles in the step loop (Task 2) ---------------------------------


class _StubMap:
    def walk_path(self, src, address, furniture=None):
        return [(1, 1)]


def _clock():
    return SimClock(datetime.datetime(2023, 2, 13, 12, 0, 0), sec_per_step=10)


def _state():
    # Minimal per-agent state; step() fills the rest via st.get(...) defaults.
    return {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "\U0001f4d6",
            "desc": "waking up",
            "performing": False,
            "perform_until": None,
            "reasoning": "(waking up)",
            "memories": [],
            "chat": None,
            "stop_since": 0,
        }
    }


def _run_step(game, chars, state, idx, clock):
    return step(
        game,
        chars,
        state,
        idx,
        order=["Ada"],
        world_map=_StubMap(),
        emoji={"Ada": "\U0001f4d6"},
        clock=clock,
        cog=CognitionConfig(),
    )


def test_study_without_a_duration_settles_instead_of_re_deciding_every_tick():
    # Scheduled at The Green (home, steps=None) so the study is on-plan;
    # tag it studyable so the verb is offered + gated there.
    brain = PerActionBrain("study", {"topic": "thermodynamics"})
    game, ada = _world(llm_client=brain, place="The Green")
    game.locations["The Green"].set_property("studyable", True)
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    st = state["Ada"]
    assert st["performing"] is True  # settled -- not the instantaneous branch
    assert st["perform_until"] is None  # on-plan stay-put, exactly like perform
    assert "studying thermodynamics" in st["desc"]


def test_study_settles_for_the_model_duration():
    # 20 minutes at 10s/step = 120 steps, same arithmetic the #581 tests pin.
    brain = PerActionBrain("study", {"topic": "thermodynamics", "duration_minutes": 20})
    game, ada = _world(llm_client=brain, place="The Green")
    game.locations["The Green"].set_property("studyable", True)
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    assert state["Ada"]["performing"] is True
    assert state["Ada"]["perform_until"] == 0 + 120
    assert ada.get_property("studied_minutes") == 20  # the accumulator saw 20


def test_step_loop_clamps_the_model_duration_for_ledger_and_settle_alike():
    # 500 min is beyond CognitionConfig's duration_max_minutes (90). The step
    # loop clamps the stash once, before the command routes, so the
    # studied_minutes ledger and the wall-time settle agree instead of the
    # memory overstating the settle by the clamp width.
    brain = PerActionBrain(
        "study", {"topic": "thermodynamics", "duration_minutes": 500}
    )
    game, ada = _world(llm_client=brain, place="The Green")
    game.locations["The Green"].set_property("studyable", True)
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    assert ada.get_property("studied_minutes") == 90
    assert state["Ada"]["perform_until"] == 0 + 90 * 6  # 90 min @ 10s/step


def test_sub_minute_model_duration_never_ledgers_zero_minutes():
    # duration_minutes is a JSON "number", so a brain may pick 0.5. The clamp
    # floors it to duration_min_minutes (1): the ledger records 1 minute
    # instead of int-truncating to a "studied for 0 minutes" no-op while the
    # character visibly settles.
    brain = PerActionBrain("study", {"duration_minutes": 0.5})
    game, ada = _world(llm_client=brain, place="The Green")
    game.locations["The Green"].set_property("studyable", True)
    state = _state()
    _run_step(game, {"Ada": ada}, state, 0, _clock())
    assert ada.get_property("studied_minutes") == 1


# -- memory lines (Task 3) -----------------------------------------------------


def test_render_pins_the_study_and_eat_reflections():
    assert (
        render("reflection", verb="study", topic="thermodynamics", minutes=45)
        == "I studied thermodynamics for 45 minutes."
    )
    assert (
        render("reflection", verb="study", topic="", minutes=30)
        == "I studied for 30 minutes."
    )
    # Hunger-neutral on purpose: the engine's eat clears IS_HUNGRY whether or
    # not the persona was hungry, so "no longer hungry" could be a false memory.
    assert render("reflection", verb="eat", item="sandwich") == "I ate the sandwich."


def _spy_memory(char):
    seen = {}
    orig = char.agent.memory.add_observation

    # **kw, not an enumerated signature: `perceive` also calls add_observation
    # with actor= and source_event_ids=, and enumerating the kwargs means every
    # future one breaks this spy (as tags= already did once).
    def spy(text, **kw):
        seen["text"], seen["importance"] = text, kw.get("importance", 1.0)
        return orig(text, **kw)

    char.agent.memory.add_observation = spy
    return seen


def test_remember_outcome_writes_the_study_memory_and_consumes_the_marker():
    game, ada = _world()
    _move(game, ada, "Library")
    ada.agent.last_duration_minutes = 45
    assert game.parser.parse_command("study thermodynamics", actor=ada)
    seen = _spy_memory(ada)
    remember_outcome(ada, "study thermodynamics", 3)
    assert seen["text"] == "I studied thermodynamics for 45 minutes."
    assert seen["importance"] == 2.0
    # One-shot consumed, so a later unrelated outcome can't re-read it.
    assert not ada.get_property("just_studied_minutes")


def test_remember_outcome_writes_the_eat_memory():
    game, ada = _world()
    seen = _spy_memory(ada)
    remember_outcome(ada, "eat sandwich", 3)
    assert seen["text"] == "I ate the sandwich."
    assert seen["importance"] == 2.0


# -- eat: curation + the get -> eat two-step (Task 4) --------------------------


def test_eat_offered_only_where_something_edible_is_in_scope():
    game, ada = _world()
    assert "eat" not in _tool_names(game, ada)  # nothing EDIBLE on The Green
    snack = Item("granola bar", "a granola bar")
    snack.set_property(Property.EDIBLE, True)
    game.locations["The Green"].add_item(snack)
    assert "eat" in _tool_names(game, ada)  # offered <=> place-check passes


def test_eat_gate_feedback_on_no_food_here_is_actionable():
    game, ada = _world()
    assert not game.parser.parse_command("eat sandwich", actor=ada)
    assert getattr(game.parser, "last_fail_message", "") == (
        "There is nothing to eat here."
    )


def test_meals_are_gated_on_the_authored_dining_tag():
    # The isolated boil scenario (#299/#301) authors no `dining` tag on its
    # Houston Hall -- and its sole resident LIVES there, so stocking meals
    # would put `eat` on that experiment's decision surface every tick. The
    # furnish is gated on the #613 arena tag: only a world that authors
    # `dining` (the full Penn world) gets meals.
    from penn_world import _furnish_meals

    locs = LOCATIONS + [
        {"name": "Houston Hall", "description": "the union", "address": "T:HH:lobby"}
    ]
    game, _chars = build_world(None, [_persona()], locs)
    hall = game.locations["Houston Hall"]
    _furnish_meals(game)
    assert not hall.items  # untagged (the boil world's shape): no meals
    hall.set_property("dining", True)
    _furnish_meals(game)
    edible = [i for i in hall.items.values() if i.get_property(Property.EDIBLE)]
    assert len(edible) == 3  # tagged (the full world's shape): stocked


def test_penn_world_offers_the_615_verbs():
    from penn_world import PENN_ACTION_VERBS

    assert "eat" in PENN_ACTION_VERBS
    assert "study" in PENN_ACTION_VERBS


def test_houston_hall_meals_support_the_get_eat_two_step():
    from penn_world import build_penn_world

    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    hall = game.locations["Houston Hall"]
    # Three discrete meals ARE the portions (engine Eat has none -- #615
    # issue-comment decision): each is EDIBLE and gettable.
    meals = [i for i in hall.items.values() if i.get_property(Property.EDIBLE)]
    assert len(meals) == 3
    assert all(m.get_property(Property.GETTABLE) for m in meals)

    char = next(iter(chars.values()))
    _move(game, char, "Houston Hall")
    char.set_property(Property.IS_HUNGRY, True)
    # Eating before getting fails -- Eat only matches carried items, so the
    # two-step is the shape (documented in the #615 issue comment).
    assert not game.parser.parse_command("eat sandwich", actor=char)
    assert game.parser.parse_command("get sandwich", actor=char)
    assert game.parser.parse_command("eat sandwich", actor=char)
    assert not char.get_property(Property.IS_HUNGRY)  # satiety (engine-modeled)
    assert "sandwich" not in char.inventory  # consumed whole -- one portion
    assert "sandwich" not in hall.items


def test_study_offered_in_van_pelt_reading_rooms_only():
    from penn_world import PENN_ACTION_VERBS, build_penn_world

    pw = build_penn_world()
    game, chars = pw.build_world_fn(pw.world_map)
    attach_agents(chars, pw.personas, extra_action_names=PENN_ACTION_VERBS)
    char = next(iter(chars.values()))
    _move(game, char, "Van Pelt — Moelis Reading Room")  # studyable (#613)
    assert "study" in _tool_names(game, char)
    assert game.parser.parse_command("study medieval history", actor=char)
    assert char.get_property("studied_minutes") == DEFAULT_STUDY_MINUTES
    _move(game, char, "College Hall")  # untagged
    assert "study" not in _tool_names(game, char)
