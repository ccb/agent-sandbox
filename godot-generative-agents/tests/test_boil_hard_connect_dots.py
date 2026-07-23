"""Offline plumbing for the #728 boil_hard "connect the dots" experiment.

The research question -- does a live LLM leave the room to find the stove? --
is a manual, keyed run. Everything here is the plumbing under it, offline:
the boil_hard world builds with its Kitchen (the world loader silently drops
unknown YAML keys, so materialization must be asserted, not read off the
YAML), the stove relocates out of Houston Hall, vision_r=0 keeps it out of
the Houston observation, the arc stays solvable from the Kitchen, and the
experiment harness runs end-to-end under the scripted brain. A 0% boil rate
in both offline arms is the DOCUMENTED EXPECTATION (the scripted brain never
reasons about exploring), not a failure. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_boil_hard_connect_dots.py -v
"""

import sys
from pathlib import Path

import pytest

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); tests import them the way the scripts import each other -- off the
# sim directory itself (same shim as test_boil_from_memory.py).
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.cognition import action_tools_for, attach_agents  # noqa: E402
from backend.penn.experiments import boil_hard_connect_dots  # noqa: E402
from backend.penn.experiments.boil_from_memory import (  # noqa: E402
    _configure,
    classify_outcome,
)
from backend.penn.experiments.boil_hard_connect_dots import run_arm  # noqa: E402
from backend.penn.scripted_brain import build_scripted_brains  # noqa: E402
from penn_world import (  # noqa: E402
    WORLD_DATA_BOIL,
    WORLD_DATA_BOIL_HARD,
    build_penn_world,
    relocate_stove_to_kitchen,
)
from serve_penn import SCENARIOS, _build_parser  # noqa: E402


def _hard_world(vision_r=0):
    """The built #728 world -- stove relocated, one agent attached at the
    experiment's perception radius -- as (game, the persona's Character)."""
    pw = build_penn_world(world_data=WORLD_DATA_BOIL_HARD)
    game, chars = pw.build_world_fn(pw.world_map)
    relocate_stove_to_kitchen(game)
    personas = _configure(pw.personas, seeded=False)
    attach_agents(chars, personas, vision_r=vision_r)
    return game, chars[personas[0]["name"]]


# --- the world: Kitchen materializes, the stove moves -------------------------


def test_kitchen_materializes_and_the_stove_relocates():
    """The loader-drops-unknown-keys guard: assert the Kitchen and the moved
    stove exist on the BUILT game, not just in the YAML."""
    pw = build_penn_world(world_data=WORLD_DATA_BOIL_HARD)
    game, _chars = pw.build_world_fn(pw.world_map)
    kitchen = game.locations.get("Kitchen")
    assert kitchen is not None, "the Kitchen location never materialized"
    # Addressed to Sweeten's real kitchenette arena (furnish_alumni.py), so
    # Travel can path there; build_world's #642 check already proved it
    # resolves to tiles.
    assert kitchen.tile_address == "UPenn:Sweeten Alumni Building:Room 1: Kitchen"
    # Before relocation the base furnishing holds: the stove is in Houston Hall.
    hall = game.locations["Houston Hall"]
    assert "stove" in hall.items and "stove" not in kitchen.items

    relocate_stove_to_kitchen(game)
    assert "stove" in kitchen.items and "stove" not in hall.items
    # The murky pot (and the sink) stay put -- visible from step 0.
    assert "pot of murky water" in hall.items
    assert "sink" in hall.items


def test_relocate_without_a_kitchen_fails_loudly():
    """A world without the Kitchen (the base boil YAML) must raise, not no-op:
    a silent fallback would quietly run the EASY variant."""
    pw = build_penn_world(world_data=WORLD_DATA_BOIL)
    game, _chars = pw.build_world_fn(pw.world_map)
    with pytest.raises(ValueError, match="Kitchen"):
        relocate_stove_to_kitchen(game)


# --- perception: vision_r=0 hides the stove, Travel names the Kitchen --------


def test_stove_is_hidden_at_vision_zero_and_kitchen_is_the_only_lead():
    """The #728 setup: at vision_r=0 the Houston observation shows the murky
    pot but never the stove (#82 cross-location leak closed), and the only
    lead is "Kitchen" in Travel's destination enum (#635)."""
    game, char = _hard_world(vision_r=0)
    assert char.vision_r == 0
    # Perception can't reach past the current room, so the Kitchen's contents
    # can never fold into this agent's memory stream.
    assert game.perceivable_locations(char) == [char.location]
    obs = game.describe_for(char, agent_action_menu=False)
    assert "murky" in obs.lower()
    assert "stove" not in obs.lower()
    # The one lead: the decide tool's travel enum lists every game.locations
    # entry, Kitchen included.
    travel = {t["name"]: t for t in action_tools_for(game, char)}["travel"]
    assert "Kitchen" in travel["parameters"]["properties"]["destination"]["enum"]


def test_hard_world_is_solvable_from_the_kitchen():
    """The full arc still completes once the agent actually stands in the
    Kitchen -- so a 0% live result is cognition, not a broken world. `make`
    must fail in Houston Hall (the tool is gone) and succeed in the Kitchen."""
    game, char = _hard_world()
    parse = game.parser.parse_command
    assert parse("get pot of murky water", actor=char)
    assert not parse("make boiled water", actor=char)  # no stove in the hall
    # Stand the agent in the Kitchen (the sim walks there via Travel; the
    # engine-level room hop is all the Recipe's tool check reads).
    game.locations["Houston Hall"].remove_character(char)
    game.locations["Kitchen"].add_character(char)
    assert parse("make boiled water", actor=char)
    assert parse("drink pot of boiled water", actor=char)
    assert classify_outcome(char) == "boiled_then_drank"


# --- the experiment harness ---------------------------------------------------


def test_run_arm_wires_vision_zero_relocation_and_stop_when(monkeypatch):
    """Pin run_arm's simulate() wiring without a full sim: the cognition config
    forces vision_r=0, the per-trial build relocates the stove, and stop_when
    flips the moment DrinkPenn's authoritative stamp lands."""
    seen = {}

    def fake_simulate(world_map, steps, **kw):
        game, chars = kw["build_world_fn"](world_map)
        seen["steps"] = steps
        seen["cognition"] = kw["cognition"]
        seen["kitchen_items"] = set(game.locations["Kitchen"].items)
        seen["hall_items"] = set(game.locations["Houston Hall"].items)
        stop_when = kw["stop_when"]
        assert not stop_when(game)  # no outcome yet
        char = next(iter(chars.values()))
        char.set_property("drank_unboiled", 1)
        assert stop_when(game)  # ...latches on the authoritative counter
        return []

    monkeypatch.setattr(boil_hard_connect_dots, "simulate", fake_simulate)
    result = run_arm(seeded=True, trials=1, steps=400, make_client=lambda _l: None)
    assert seen["steps"] == 400
    assert seen["cognition"].vision_r == 0
    assert "stove" in seen["kitchen_items"]
    assert "stove" not in seen["hall_items"]
    assert result["drank_raw"] == 1  # classified from the stamp fake_simulate set


def test_run_arm_offline_scripted_is_zero_boil_in_both_arms():
    """End-to-end offline smoke: one scripted trial per arm runs the whole
    harness (fresh world, relocation, sim loop, classification). ~0% boil is
    the documented offline expectation -- the scripted brain never reasons
    about exploring for a stove -- so 0 here is the baseline, not a failure.
    Steps are kept small: the trial's plumbing is identical at any budget."""
    for seeded in (True, False):
        result = run_arm(
            seeded=seeded,
            trials=1,
            steps=40,
            make_client=lambda ledger: build_scripted_brains(ledger=ledger)[0],
        )
        assert result["boiled_then_drank"] == 0 and result["rate"] == 0.0
        tally = result["boiled_then_drank"] + result["drank_raw"] + result["neither"]
        assert tally == 1  # every trial classified to exactly one valid outcome


# --- the live-serving seam (#728) ----------------------------------------------


def test_serve_penn_scenario_flag_and_registry():
    """`--scenario` defaults to the full campus (the byte-guarded path, #640)
    and offers boil_hard; the boil_hard entry pins vision_r=0."""
    args = _build_parser().parse_args([])
    assert args.scenario == "penn"
    assert set(SCENARIOS) == {"penn", "boil", "boil_hard"}
    assert SCENARIOS["penn"]["vision_r"] is None
    assert SCENARIOS["boil_hard"]["vision_r"] == 0


def test_serve_penn_boil_hard_stepper_pins_vision_and_survives_reset():
    """The served boil_hard world has the stove in the Kitchen and vision_r=0
    all the way to the viewer handshake -- and a POST /reset rebuilds the SAME
    scenario instead of quietly swapping back to the default world."""
    from serve_penn import PennStepper

    scenario = SCENARIOS["boil_hard"]
    stepper = PennStepper(
        num_steps=2,
        world=scenario["world"](),
        world_builder=scenario["world"],
        vision_r=scenario["vision_r"],
    )
    assert stepper.cog.vision_r == 0
    assert stepper.meta()["vision_r"] == 0
    assert "stove" in stepper.game.locations["Kitchen"].items
    assert "stove" not in stepper.game.locations["Houston Hall"].items
    stepper.reset()  # rebuilds through the scenario's builder
    assert stepper.cog.vision_r == 0
    assert "stove" in stepper.game.locations["Kitchen"].items
    assert "stove" not in stepper.game.locations["Houston Hall"].items
