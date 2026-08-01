"""Co-settled pair-steps count under every brain (issue #825).

A co-settled pair-step is pure geometry -- two agents settled within earshot
at the same step (#795) -- with no LLM dependency, but the counter sat inside
step()'s ``if conversation_enabled:`` block (wired from serve_penn as
``llm_client is not None``). Under the default mock brain the accumulators
never moved: two sprites could visibly settle together at an authored
rendezvous all day while ``GET /usage`` served ``co_settled_pair_steps: 0`` --
masking real co-settlement regressions in exactly the $0 runs meant to catch
them, and leaving mock A/B baselines blind to the metric.

Only the #795 run-end warning stays gated on a conversation-capable brain
(test_penn_live_llm.test_a_socially_dead_mock_run_never_warns): a mock run
"failing to converse" is not a warning.

Fully offline (mock brain). Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_mock_pair_steps_825.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents  # noqa: E402
from backend.run_simulation import step  # noqa: E402
from backend.world_map import WorldMap  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from serve_penn import PennStepper  # noqa: E402

_LOCATIONS = [
    {"name": "Plaza", "description": "the plaza", "address": None, "hub": True},
    {"name": "Cafe", "description": "a cafe", "address": "T:Cafe:counter"},
]


def _persona(name):
    return {
        "name": name,
        "home": "Plaza",
        "persona": f"I am {name}.",
        "emoji": "\U0001f9d1",
        "start_tile": [0, 0],
        "destination": "Cafe",
        "activity": "reading",
        "schedule": [
            {"place": "Cafe", "activity": "reading", "emoji": None, "steps": 5}
        ],
    }


def _settled_mock_pair():
    """Two mock-brain agents (llm_client=None -- what every offline run gets)
    settled together in one room, state fleshed out to what step() reads."""
    personas = [_persona("Maria Lopez"), _persona("Ayesha Khan")]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas, llm_client=None)  # the mock brain
    plaza = game.locations["Plaza"]
    order = ["Maria Lopez", "Ayesha Khan"]
    for name in order:
        ch = chars[name]
        if ch.location is not None:
            ch.location.remove_character(ch)
        plaza.add_character(ch)
    state = {
        n: {
            "performing": True,  # settled mid-activity...
            "perform_until": None,  # ...with no completion due this tick
            "path": [],
            "conversing": False,
            "chat": None,
            "tile": (0, 0),
            "pron": "\U0001f9d1",
            "desc": "reading",
            "reasoning": "",
            "memories": [],
            "stop_since": 0,
        }
        for n in order
    }
    return game, chars, state, order


def test_step_counts_pair_steps_with_conversation_disabled():
    # The mock gate: simulate() and PennStepper.tick() pass
    # conversation_enabled=False whenever llm_client is None. Co-settling is
    # pure geometry, so the count must not depend on that flag.
    game, chars, state, order = _settled_mock_pair()
    wm = WorldMap.__new__(WorldMap)  # unused: nobody walks this tick
    emoji = {n: "\U0001f9d1" for n in order}
    social_info: dict = {}
    step(
        game,
        chars,
        state,
        0,
        order=order,
        world_map=wm,
        emoji=emoji,
        conversation_enabled=False,
        social_info=social_info,
    )
    assert social_info == {
        "co_settled": 1,
        "pairs": [("Maria Lopez", "Ayesha Khan")],
    }


def test_a_mock_penn_run_reports_nonzero_pair_steps():
    # End-to-end on the real mock path (#825's complaint): a bare PennStepper
    # -- no llm dict, so llm_client is None, exactly what serve_penn's default
    # brain runs -- with two agents settled together must move the
    # accumulators that GET /usage and run.yaml serve.
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    assert stepper.llm_client is None  # the mock arm, not scripted
    a, b = stepper.order[:2]
    cha, chb = stepper.chars[a], stepper.chars[b]
    # Put B in A's room, standing on A's tile (inside any vision_r), both
    # settled mid-activity: the co-settle geometry arranged by hand rather
    # than hoping two mock schedules happen to rendezvous on tick 0.
    if chb.location is not None:
        chb.location.remove_character(chb)
    cha.location.add_character(chb)
    tile = tuple(stepper.state[a]["tile"])
    for name, ch in ((a, cha), (b, chb)):
        ch.tile = tile
        st = stepper.state[name]
        st["tile"] = tile
        st["path"] = []
        st["performing"] = True
        st["perform_until"] = None
    stepper.tick()
    assert stepper._co_settled_total >= 1
    assert stepper._co_settled_by_pair.get((a, b), 0) >= 1
    social = stepper.run_usage()["social"]
    assert social["co_settled_pair_steps"] >= 1
    assert social["by_pair"].get(f"{a} + {b}", 0) >= 1


def test_mock_zero_is_a_measured_zero():
    # #819 gave the wire a `counted` flag so the dashboard could tell the mock
    # brain's permanent "not measured" 0 from a real #795 drought. With #825
    # fixed there is no unmeasured brain left, so `counted` is always True --
    # a mock zero is a real zero. (The field stays on the wire so older
    # dashboards can still feature-detect backends that never counted.)
    stepper = PennStepper(num_steps=1, world=build_penn_world())
    assert stepper.run_usage()["social"]["counted"] is True
