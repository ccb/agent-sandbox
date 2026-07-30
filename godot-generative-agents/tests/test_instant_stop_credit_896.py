"""Credit a schedule stop satisfied by an instantaneous verb (#896).

A stop whose activity resolves through an instantaneous verb (#300
get/drink, #616 check_out_book -- no ``duration_minutes`` in the schema, no
perform latch) never reached the pre-pass that consumes ``credit_stop``, so
the pointer pinned on the finished stop forever. Live evidence: Maya, 16
``check_out_book`` calls and a 67-minute yo-yo leg in
run-20260730-000027-5118ae.

Fully offline (scripted brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_instant_stop_credit_896.py -v
"""

import datetime

from text_adventure_games.things import Item

from backend.build_world import build_world
from backend.cognition import attach_agents
from backend.run_simulation import step
from backend.sim_clock import SimClock

_LOCATIONS = [
    {"name": "Cafe", "description": "a cafe", "address": None, "hub": True},
    {"name": "Library", "description": "a library", "address": None},
]


def _schedule(next_stop_extra=None):
    return [
        {"place": "Cafe", "activity": "grabbing lunch", "emoji": None, "steps": 5},
        {
            "place": "Cafe",
            "activity": "meeting",
            "emoji": None,
            "steps": 5,
            **(next_stop_extra or {}),
        },
    ]


def _persona(schedule=None, destination="Cafe"):
    return {
        "name": "Ada",
        "home": "Cafe",
        "persona": "I am Ada.",
        "emoji": "📖",
        "start_tile": [0, 0],
        "destination": destination,
        "activity": "grabbing lunch",
        "schedule": schedule or _schedule(),
    }


def _state():
    return {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "📖",
            "desc": "grabbing lunch",
            "performing": False,
            "perform_until": None,
            "reasoning": "(lunch)",
            "memories": [],
            "chat": None,
            "stop_since": 0,
            "credit_stop": True,
            "conversing": False,
        }
    }


def _build(persona, commands):
    """World + scripted Ada: decide() pops the next command (repeating the
    last), the pattern of test_dead_talk_settle_689's _script_decide_forever
    extended to a queue so a second decide can be a *different* instantaneous
    success (a re-`get` would fail on "already in inventory")."""
    game, chars = build_world(None, [persona], _LOCATIONS)
    attach_agents(chars, [persona], llm_client=None)
    game.locations["Cafe"].add_item(Item("sandwich", "a sandwich"))
    queue = list(commands)

    def _decide(observation):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    chars["Ada"].agent.decide = _decide
    common = {
        "order": ["Ada"],
        "world_map": None,
        "emoji": {"Ada": "📖"},
        "clock": SimClock(datetime.datetime(2023, 2, 13, 8, 0)),
    }
    return game, chars, common


def test_instant_success_at_the_stop_latches_with_credit_then_advances():
    """The #896 seam: an instantaneous success at the scheduled stop settles
    for the stop's authored steps with the credit set, and the existing
    pre-pass advances the pointer at expiry."""
    game, chars, common = _build(_persona(), ["get sandwich"])
    state = _state()

    step(game, chars, state, 0, **common)
    assert state["Ada"]["performing"] is True
    assert state["Ada"]["credit_stop"] is True
    assert state["Ada"]["perform_until"] == 5
    assert chars["Ada"].agent.schedule.stop_index == 0

    step(game, chars, state, 5, **common)
    assert chars["Ada"].agent.schedule.stop_index == 1
    assert state["Ada"]["stop_since"] == 5


def test_a_second_instant_success_never_relatches_a_held_credit():
    """After the credit is consumed into a #838 anchor hold, another
    instantaneous success must not re-latch a full dwell -- that would block
    the #826 hold-retry (which requires ``not performing``) past the anchor
    hour. Mutation check: drop the ``waiting_for_anchor`` guard and this goes
    RED at the performing assertion."""
    game, chars, common = _build(
        _persona(_schedule({"start_hour": 10})),
        ["get sandwich", "drop sandwich"],
    )
    state = _state()

    # 08:00: the instantaneous success latches the stop's 5 steps with credit.
    step(game, chars, state, 0, **common)
    assert state["Ada"]["perform_until"] == 5

    # 08:00-and-5-steps: expiry credits the stop, but the 10:00 anchor holds
    # the pointer; the SAME tick's decide is another instantaneous success
    # (drop), which must leave the hold un-latched.
    step(game, chars, state, 5, **common)
    assert state["Ada"]["waiting_for_anchor"] is True
    assert state["Ada"]["performing"] is False
    assert state["Ada"]["perform_until"] is None
    assert chars["Ada"].agent.schedule.stop_index == 0

    # 10:00: the #826 retry advances the held pointer, as before the fix.
    step(game, chars, state, 720, **common)
    assert chars["Ada"].agent.schedule.stop_index == 1
    assert state["Ada"]["waiting_for_anchor"] is False
    assert state["Ada"]["stop_since"] == 720


def test_an_authored_commands_stop_never_latches_on_a_command():
    """The mock brain issues a stop's authored ``commands`` one per tick before
    a terminal perform; latching on any of them would skip the rest (Sofia's
    get/drink/boil arc). Mutation check: drop the ``_stop_has_authored_commands``
    guard and this goes RED."""
    schedule = _schedule()
    schedule[0]["commands"] = ["get sandwich"]
    persona = _persona(schedule)
    game, chars = build_world(None, [persona], _LOCATIONS)
    attach_agents(chars, [persona], llm_client=None)  # real mock _choose
    game.locations["Cafe"].add_item(Item("sandwich", "a sandwich"))
    state = _state()
    common = {
        "order": ["Ada"],
        "world_map": None,
        "emoji": {"Ada": "📖"},
        "clock": SimClock(datetime.datetime(2023, 2, 13, 8, 0)),
    }

    # Tick 0 issues the authored `get sandwich`: no latch, so the next tick's
    # decide can issue the stop's terminal perform.
    step(game, chars, state, 0, **common)
    assert state["Ada"]["performing"] is False
    assert state["Ada"]["perform_until"] is None

    # Tick 1: the terminal perform settles through the existing branch.
    step(game, chars, state, 1, **common)
    assert state["Ada"]["desc"].startswith("grabbing lunch")
    assert state["Ada"]["performing"] is True
    assert state["Ada"]["perform_until"] == 1 + 5


def test_an_off_plan_instant_success_never_latches():
    """Off the scheduled stop, an instantaneous success stays a plain one-tick
    action (the #831 deviation flow belongs to settles, not one-shot verbs).
    Mutation check: drop the ``matched`` guard and this goes RED."""
    schedule = [
        {"place": "Library", "activity": "studying", "emoji": None, "steps": 5},
        {"place": "Cafe", "activity": "meeting", "emoji": None, "steps": 5},
    ]
    game, chars, common = _build(
        _persona(schedule, destination="Library"), ["get sandwich"]
    )
    state = _state()

    step(game, chars, state, 0, **common)  # Ada stands at Cafe, stop is Library
    assert state["Ada"]["performing"] is False
    assert state["Ada"]["perform_until"] is None


def test_a_stay_put_stop_never_latches():
    """``steps: None`` means stay put (an end-of-day stop): there is nothing
    to advance to on a fixed dwell, so an instantaneous success stays a plain
    one-tick action. Mutation check: drop the ``steps is not None`` guard and
    this goes RED."""
    schedule = [
        {"place": "Cafe", "activity": "grabbing lunch", "emoji": None, "steps": None},
    ]
    game, chars, common = _build(_persona(schedule), ["get sandwich"])
    state = _state()

    step(game, chars, state, 0, **common)
    assert state["Ada"]["performing"] is False
    assert state["Ada"]["perform_until"] is None


def test_a_clockless_instant_success_never_latches():
    """No clock (the bundled bake, #640): today's behavior exactly.
    Mutation check: drop the ``clock is not None`` guard and this goes RED."""
    game, chars, common = _build(_persona(), ["get sandwich"])
    common["clock"] = None
    state = _state()

    step(game, chars, state, 0, **common)
    assert state["Ada"]["performing"] is False
    assert state["Ada"]["perform_until"] is None
