"""Config field *value type* validation (issue #754).

``SimulationConfig.from_dict`` / ``GameConfig.from_dict`` already reject an
unknown section or an unknown key within a section; this pins that a
wrong-typed *value* is now also rejected at load time, with a clear
``ValueError`` naming the field -- rather than building the dataclass with a
bad value that fails deep at runtime. Fully offline.

    uv run pytest godot-generative-agents/tests/test_sim_config_field_types_754.py -v
"""

import pytest

from backend.sim_config import SimulationConfig


def test_rejects_wrong_type_in_retrieval_section():
    with pytest.raises(
        ValueError, match="retrieval.alpha_recency.*must be float.*got str"
    ):
        SimulationConfig.from_dict({"retrieval": {"alpha_recency": "high"}})


def test_accepts_int_for_float_field():
    cfg = SimulationConfig.from_dict({"retrieval": {"alpha_recency": 1}})
    assert cfg.retrieval.alpha_recency == 1


def test_rejects_wrong_type_through_nested_game_section():
    """The issue's own repro: a bad value nested under `game` must also fail --
    this exercises GameConfig's copy of the same validator, not SimulationConfig's."""
    with pytest.raises(ValueError, match="agent.temperature.*must be float.*got str"):
        SimulationConfig.from_dict({"game": {"agent": {"temperature": "hot"}}})


def test_rejects_bool_for_int_field():
    with pytest.raises(ValueError, match="cognition.vision_r.*must be int.*got bool"):
        SimulationConfig.from_dict({"cognition": {"vision_r": True}})


def test_valid_config_still_builds():
    cfg = SimulationConfig.from_dict(
        {"retrieval": {"alpha_recency": 2.0, "max_records": 3}}
    )
    assert cfg.retrieval.alpha_recency == 2.0
    assert cfg.retrieval.max_records == 3
