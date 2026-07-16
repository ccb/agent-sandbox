"""Brain-authoritative pacing (issue #581).

The executed action -- not the ScheduleMockClient stop pointer -- owns an
agent's duration, emoji, and stop-advance. Pins:

* the ``perform`` tool's optional ``duration_minutes`` / ``emoji`` meta-args
  reach the agent without leaking into the routed command string;
* the step loop honors a model duration (clamped) and emoji, falling back to
  the schedule when absent -- so the mock bake stays byte-identical;
* ``advance()`` fires only when the activity completed at the scheduled place;
  a place deviation keeps the pointer and fires one cooldown-guarded revision;
* new duration-bearing verbs settle like ``perform`` while the #300
  instantaneous verbs keep falling through.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_pacing_authority_581.py -v
"""

import datetime
import sys
from pathlib import Path

# Same import shim as test_per_action_decide.py: the Penn sim modules run as
# scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.sim_config import CognitionConfig  # noqa: E402


def test_cognition_config_has_pacing_knobs_with_defaults():
    cog = CognitionConfig()
    assert cog.duration_min_minutes == 1
    assert cog.duration_max_minutes == 90
    assert cog.deviation_cooldown_steps == 30


def test_cognition_config_round_trips_pacing_knobs():
    import pytest

    from backend.sim_config import SimulationConfig

    cfg = SimulationConfig.from_dict(
        {"cognition": {"duration_max_minutes": 45, "deviation_cooldown_steps": 12}}
    )
    assert cfg.cognition.duration_max_minutes == 45
    assert cfg.cognition.deviation_cooldown_steps == 12
    # Unknown keys are still rejected by the section validator (no silent drop).
    with pytest.raises(ValueError):
        SimulationConfig.from_dict({"cognition": {"duration_bogus": 1}})
