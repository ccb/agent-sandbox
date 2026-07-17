"""React-or-continue: perception-driven interruption (issue #370).

A mid-activity agent that newly comes within mutual sight of another resident
remembers the encounter and -- behind a rule tier plus one bounded `react`
LLM call -- may pause its walk to greet (a #371 multi-tick conversation) or
replan. Default off; the mock brain never consults, so the bake stays
byte-identical.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_react_interruption_370.py -v
"""

import sys
from pathlib import Path

import pytest

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.sim_config import CognitionConfig  # noqa: E402


def test_cognition_config_react_defaults():
    cog = CognitionConfig()
    assert cog.react_enabled is False
    assert cog.react_cooldown_steps == 90
    assert cog.react_hour_cap == 4


def test_react_knobs_load_from_dict():
    from backend.sim_config import SimulationConfig

    config = SimulationConfig.from_dict(
        {"cognition": {"react_enabled": True, "react_hour_cap": 2}}
    )
    assert config.cognition.react_enabled is True
    assert config.cognition.react_hour_cap == 2
    assert config.cognition.react_cooldown_steps == 90


def test_encounter_template_pins_exact_output():
    from backend.prompt_templates import render

    text = render(
        "encounter", partner="Ayesha Khan", doing="walking to Van Pelt Library"
    )
    assert text == "I noticed Ayesha Khan nearby while walking to Van Pelt Library."


def test_react_template_renders_all_blocks():
    from backend.prompt_templates import render

    text = render(
        "react",
        partner="Ayesha Khan",
        doing="walking to Van Pelt Library",
        time="Monday 09:30 AM",
        memories=["Ayesha Khan is my study partner."],
    )
    # Substring pins (the template has optional blocks, so exact-match would be
    # brittle across Jinja whitespace): every semantic piece must appear.
    assert "It is Monday 09:30 AM." in text
    assert "While walking to Van Pelt Library, you notice Ayesha Khan nearby." in text
    assert "- Ayesha Khan is my study partner." in text
    assert '"continue"' in text and '"greet"' in text and '"replan"' in text


def test_react_template_without_time_or_memories():
    from backend.prompt_templates import render

    text = render(
        "react", partner="Ayesha Khan", doing="reading", time=None, memories=[]
    )
    assert "It is" not in text
    assert "What you remember" not in text
    assert "While reading, you notice Ayesha Khan nearby." in text
