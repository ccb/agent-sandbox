"""Bound the dead-talk retry loop through the pair cooldown (issue #689).

A decide-level `talk to <partner>` never produces a real conversation for a
Penn resident -- that's `maybe_converse`/`maybe_react`'s job, not the agent's
own decide (Penn characters never set `talk_text`/`talk_topics` on the shared
engine `Talk` action). Without a settle, a talk that resolves empty ("has
nothing to say") or blocked ("no one here to talk to") leaves the agent
immediately `due` for its next paid decide, every tick, for as long as the
#86 pair cooldown blocks a real conversation.

Fully offline (fake brains). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_dead_talk_settle_689.py -v
"""

from backend.sim_config import CognitionConfig


def test_cognition_config_dead_talk_settle_default():
    cog = CognitionConfig()
    assert cog.dead_talk_settle_steps == 30


def test_dead_talk_settle_knob_loads_from_dict():
    from backend.sim_config import SimulationConfig

    config = SimulationConfig.from_dict({"cognition": {"dead_talk_settle_steps": 10}})
    assert config.cognition.dead_talk_settle_steps == 10
    assert config.cognition.deviation_cooldown_steps == 30  # untouched sibling default
