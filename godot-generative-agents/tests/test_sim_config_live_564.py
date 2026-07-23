"""serve_penn --config: the #564 live-tuning seam.

Pins that a SimulationConfig loaded from a file reaches the live path:
retrieval weights into every decide (via step()'s existing retrieval param),
temperature / reflection_threshold onto each agent (via attach_agents), and
the cognition knobs into PennStepper.cog -- with NO --config byte-identical to
today by construction. Fully offline (mock brain). Run from the repo root:

    uv run pytest godot-generative-agents/tests/test_sim_config_live_564.py -v
"""

import sys
from pathlib import Path

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); tests import them the way the scripts import each other -- off the
# sim directory itself (same shim as test_penn_live_llm.py).
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402
from penn_world import build_penn_world  # noqa: E402
from serve_penn import PennStepper, _build_parser  # noqa: E402

from backend.cognition import attach_agents  # noqa: E402
from backend.run_simulation import observe_and_decide  # noqa: E402
from backend.sim_config import (  # noqa: E402
    CognitionConfig,
    RetrievalConfig,
    SimulationConfig,
)


def _cfg(data: dict) -> SimulationConfig:
    return SimulationConfig.from_dict(data)


# -- Task 1: attach_agents threads temperature / reflection_threshold --------


def test_attach_agents_threads_temperature_and_reflection_threshold():
    world = build_penn_world()
    _game, chars = world.build_world_fn(world.world_map)
    attach_agents(chars, world.personas, temperature=0.0, reflection_threshold=10.0)
    for p in world.personas:
        agent = chars[p["name"]].agent
        assert agent.temperature == 0.0
        assert agent.reflection_threshold == 10.0


def test_attach_agents_defaults_are_unchanged():
    world = build_penn_world()
    _game, chars = world.build_world_fn(world.world_map)
    attach_agents(chars, world.personas)
    for p in world.personas:
        agent = chars[p["name"]].agent
        assert agent.temperature == 0.7  # LLMAgent's own default
        assert agent.reflection_threshold == 30.0  # DEFAULT_REFLECTION_THRESHOLD


# -- Task 2: PennStepper holds the config and applies it at _build -----------


def test_stepper_sim_config_threads_cognition_and_temperature():
    cfg = _cfg(
        {
            "game": {"agent": {"temperature": 0.0, "reflection_threshold": 10.0}},
            "cognition": {"vision_r": 2, "conversation_cooldown_steps": 5},
            "retrieval": {"max_records": 1},
        }
    )
    stepper = PennStepper(num_steps=2, world=build_penn_world(), sim_config=cfg)
    assert stepper.cog.vision_r == 2
    assert stepper.cog.conversation_cooldown_steps == 5
    assert stepper.retrieval.max_records == 1
    for char in stepper.chars.values():
        assert char.agent.temperature == 0.0
        assert char.agent.reflection_threshold == 10.0
        assert char.vision_r == 2  # attach_agents' vision_r came from cog


def test_stepper_sim_config_survives_reset():
    cfg = _cfg({"cognition": {"vision_r": 2}})
    stepper = PennStepper(num_steps=2, world=build_penn_world(), sim_config=cfg)
    stepper.reset()  # POST /reset re-runs _build -- the config must re-apply
    assert stepper.cog.vision_r == 2


def test_stepper_without_config_keeps_todays_defaults():
    stepper = PennStepper(num_steps=2, world=build_penn_world())
    assert stepper.sim_config is None
    assert stepper.retrieval is None
    assert stepper.cog == CognitionConfig()  # mock brain: no flag couplings fire
    for char in stepper.chars.values():
        assert char.agent.temperature == 0.7


def test_cli_flag_still_forces_cognition_tools_on_over_config():
    cfg = _cfg({"cognition": {"cognition_tools": False}})
    stepper = PennStepper(
        num_steps=2, world=build_penn_world(), sim_config=cfg, cognition_tools=True
    )
    assert stepper.cog.cognition_tools is True


def test_config_can_switch_cognition_tools_and_react_on():
    cfg = _cfg({"cognition": {"cognition_tools": True, "react_enabled": True}})
    stepper = PennStepper(num_steps=2, world=build_penn_world(), sim_config=cfg)
    assert stepper.cognition_tools is True
    assert stepper.cog.cognition_tools is True
    assert stepper.react is True
    assert stepper.cog.react_enabled is True
