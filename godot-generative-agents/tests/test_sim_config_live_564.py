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
