"""The hard travel gate on pinned stops (issue #885).

#760 batch 7: an agent whose decide context truthfully said "your next stop
starts in 15 min" and "Houston Hall 53 min" still picked the 53-minute leg (a
confusable-name slip its own reasoning contradicted) and walked 55 minutes on
it. The gate refuses, at ``Travel``'s precondition, any leg whose walk cost
exceeds the minutes left before the schedule's next future-pinned stop --
unless the leg goes to that anchored stop's own building or to the current
scheduled stop, which stay legal however late.
"""

import datetime
import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.actions import Travel, anchor_travel_refusal  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents  # noqa: E402
from backend.sim_clock import SimClock  # noqa: E402

LOCATIONS = [
    {
        "name": "Penn campus",
        "description": "the campus hub",
        "address": None,
        "hub": True,
    },
    {
        "name": "Van Pelt Library",
        "description": "the lobby",
        "address": "UPenn:Van Pelt Library:lobby",
    },
    {
        "name": "Van Pelt — Moelis Reading Room",
        "description": "the reading room",
        "address": "UPenn:Van Pelt Library:Moelis",
    },
    {
        "name": "Houston Hall",
        "description": "the student union",
        "address": "UPenn:Houston Hall:lobby",
    },
    {
        "name": "Irvine Auditorium",
        "description": "the auditorium",
        "address": "UPenn:Irvine Auditorium:hall",
    },
    {
        "name": "College Hall",
        "description": "the hall",
        "address": "UPenn:College Hall:lobby",
    },
]

# Steps from Ada's tile, priced at 10 s/step: Houston 318 steps = 53 min,
# Irvine 96 steps = 16 min, everything else nearby.
_WALKS = {
    "UPenn:Houston Hall:lobby": 318,
    "UPenn:Irvine Auditorium:hall": 96,
    "UPenn:Van Pelt Library:lobby": 12,
    "UPenn:Van Pelt Library:Moelis": 18,
    "UPenn:College Hall:lobby": 30,
}


class _Map:
    def walk_steps_from(self, tile, address):
        return _WALKS.get(address, 10_000)

    def tiles_for(self, address):
        return {(0, 0)} if address in _WALKS else set()


def _persona():
    return {
        "name": "Ada",
        "home": "Van Pelt Library",
        "persona": "I am Ada.",
        "emoji": "📚",
        "start_tile": [0, 0],
        "destination": "Van Pelt Library",
        "activity": "grabbing a textbook",
        "schedule": [
            {
                "place": "Van Pelt Library",
                "activity": "grabbing a textbook",
                "emoji": "📚",
                "steps": 30,
            },
            {
                "place": "Van Pelt — Moelis Reading Room",
                "activity": "problem sets with Priya",
                "emoji": "📚",
                "steps": 300,
                "start_hour": 9,
            },
            {
                "place": "Irvine Auditorium",
                "activity": "the guest lecture",
                "emoji": "🔭",
                "steps": 300,
                "start_hour": 10,
            },
        ],
    }


def _world(*, minutes_past_8=45):
    persona = _persona()
    game, chars = build_world(None, [persona], LOCATIONS)
    attach_agents(chars, [persona])
    ada = chars["Ada"]
    ada.tile = (0, 0)
    game.world_map = _Map()
    # 10 s/step: step 270 = 08:45, fifteen minutes before the 9 AM pin.
    game.sim_clock = SimClock(datetime.datetime(2026, 7, 29, 8, 0), sec_per_step=10)
    game.sim_clock_step = minutes_past_8 * 6
    return game, ada


def _refusal(game, ada, destination):
    return anchor_travel_refusal(game, ada, game.locations[destination])


def test_gate_refuses_the_leg_that_cannot_beat_the_pin():
    # Maya's batch-7 shape: 15 min before the 9 AM pin, a 53-minute leg.
    game, ada = _world(minutes_past_8=45)
    reason = _refusal(game, ada, "Houston Hall")
    assert reason is not None
    assert "about 53 min" in reason
    assert "starts in 15 min" in reason
    assert "problem sets with Priya" in reason
    # And Travel's precondition enforces it (enum, free text and fallback all
    # route through this one gate).
    action = Travel(game, "Ada travels to Houston Hall")
    assert action.check_preconditions() is False


def test_walking_to_the_pinned_stop_stays_legal_however_late():
    game, ada = _world(minutes_past_8=45)
    assert _refusal(game, ada, "Van Pelt — Moelis Reading Room") is None
    # Same building as the pin counts as walking to the pin.
    assert _refusal(game, ada, "Van Pelt Library") is None


def test_a_leg_that_fits_the_window_passes():
    # A 5-minute cross-building hop against the 15-minute window: legal.
    game, ada = _world(minutes_past_8=45)
    assert _refusal(game, ada, "College Hall") is None


def test_only_the_binding_pin_exempts_its_own_place():
    # At 08:45 the 9 AM pin binds: even the 10 AM pin's own place is a
    # 16-minute walk against a 15-minute window, so it is refused -- skipping
    # an imminent pin is a plan revision, not a walk.
    game, ada = _world(minutes_past_8=45)
    reason = _refusal(game, ada, "Irvine Auditorium")
    assert reason is not None and "starts in 15 min" in reason
    # Once the 9 AM pin has passed, Irvine IS the binding pin's place: legal.
    game2, ada2 = _world(minutes_past_8=105)  # 09:45
    assert _refusal(game2, ada2, "Irvine Auditorium") is None


def test_gate_is_inert_without_a_clock_or_without_pins():
    # No clock stamped (the bake): inert.
    game, ada = _world()
    game.sim_clock = None
    assert _refusal(game, ada, "Houston Hall") is None
    # Pins gone (an authored schedule): inert.
    game2, ada2 = _world()
    for entry in ada2.agent.schedule.schedule:
        entry.pop("start_hour", None)
    assert _refusal(game2, ada2, "Houston Hall") is None


def test_step_stamps_the_clock_on_the_game():
    # The seam (#862's lesson): the gate reads game.sim_clock(_step), and
    # only step() writes them -- drop the stamp and the gate never fires live.
    from backend.run_simulation import step

    persona = _persona()
    game, chars = build_world(None, [persona], LOCATIONS)
    attach_agents(chars, [persona])
    clock = SimClock(datetime.datetime(2026, 7, 29, 8, 0), sec_per_step=10)
    state = {
        "Ada": {
            "tile": (0, 0),
            "path": [],
            "pron": "📚",
            "desc": "",
            "performing": False,
            "perform_until": None,
            "reasoning": "",
            "memories": [],
            "chat": None,
            "stop_since": 0,
            "waiting_for_anchor": False,
            "conversing": False,
        }
    }
    step(
        game,
        chars,
        state,
        7,
        order=["Ada"],
        world_map=None,
        emoji={"Ada": "📚"},
        clock=clock,
    )
    assert game.sim_clock is clock
    assert game.sim_clock_step == 7


def test_anchor_held_agent_is_offered_its_next_stop():
    # The batch-7 trap: pointer held on a finished stop, prompt says "your
    # next stop is <same-building room>", and a current-stop-only menu offered
    # no same-building destination at all -- the model then picked a lookalike
    # room in a building 53 minutes away. The next stop's place must be legal.
    from backend.actions import travel_destination_allowed

    game, ada = _world(minutes_past_8=45)
    # Ada stands at her (finished, anchor-held) first stop; the next stop is
    # Moelis, same building, pinned to 9 AM.
    moelis = game.locations["Van Pelt — Moelis Reading Room"]
    assert travel_destination_allowed(game, ada, moelis)
    from backend.cognition import action_tools_for

    tools = {t["name"]: t for t in action_tools_for(game, ada, 12)}
    enum = tools["travel"]["parameters"]["properties"]["destination"].get("enum")
    assert "Van Pelt — Moelis Reading Room" in enum
