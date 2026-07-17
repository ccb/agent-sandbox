"""Minimal Penn-local thirst drive (#594): a per-tick accrual that flips the
engine's IS_THIRSTY once a threshold is crossed. Opt-in per character so
non-experiment runs never accrue. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_drives.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.drives import accrue_thirst  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402
from text_adventure_games.things import Character  # noqa: E402


def _char():
    return Character("Maya", "a student", "A thirsty student.")


def test_no_thirst_rate_is_a_noop():
    c = _char()
    accrue_thirst(c)
    assert not c.get_property(Property.IS_THIRSTY)
    assert not c.get_property("thirst")  # nothing accrued


def test_thirst_accrues_and_flips_is_thirsty_at_threshold():
    c = _char()
    c.set_property("thirst_rate", 1)
    c.set_property("thirst_threshold", 3)
    accrue_thirst(c)  # 1
    accrue_thirst(c)  # 2
    assert not c.get_property(Property.IS_THIRSTY)
    accrue_thirst(c)  # 3 -> threshold
    assert c.get_property(Property.IS_THIRSTY)
    assert c.get_property("thirst") == 3


def test_thirst_rate_greater_than_one_reaches_threshold_faster():
    c = _char()
    c.set_property("thirst_rate", 3)
    c.set_property("thirst_threshold", 3)
    accrue_thirst(c)
    assert c.get_property(Property.IS_THIRSTY)
