"""Tests for accrue_energy (#931): a Penn-local energy/tiredness drive,
mirroring tests/test_drives.py's thirst drive: a per-tick decay that, unlike
thirst, runs by default (an unconfigured character still decays at a fixed
exponential rate) and switches to a linear ``energy_decay_rate`` once a
persona opts into one -- see accrue_energy's docstring in backend/drives.py.

Run with: uv run pytest godot-generative-agents/tests/test_energy_drive.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.drives import accrue_energy  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402
from text_adventure_games.things import Character  # noqa: E402


def _char():
    return Character("Maya", "a student", "A tired student.")


def test_no_energy_decay_rate_is_a_noop():
    c = _char()
    accrue_energy(c)
    assert not c.get_property("energy_decayed")  # nothing accrued
    assert not c.get_property(Property.IS_SLEEPING)


def test_energy_decays_at_the_deafault_rate():
    c = _char()
    c.set_property(Property.ENERGY, 50)
    accrue_energy(c)
    assert c.get_property(Property.ENERGY) == 49.525000000000006


def test_energy_decays_at_the_configured_rate():
    c = _char()
    c.set_property(Property.ENERGY, 50)
    c.set_property("energy_decay_rate", 6)
    accrue_energy(c)
    assert c.get_property(Property.ENERGY) == 44


def test_energy_never_drops_below_zero():
    c = _char()
    c.set_property(Property.ENERGY, 5)
    c.set_property("energy_decay_rate", 6)
    accrue_energy(c)
    assert c.get_property(Property.ENERGY) == 0


def test_low_energy_flips_is_sleeping_flag_false_until_threshold():
    # Mirrors accrue_thirst's threshold flip -- a "needs sleep" signal, not
    # the actual is_sleeping state Sleep's apply_effects sets while resting.
    c = _char()
    c.set_property(Property.ENERGY, 20)
    c.set_property("energy_decay_rate", 10)
    c.set_property("energy_low_threshold", 10)
    accrue_energy(c)  # 20 -> 10, at the threshold
    assert c.get_property("is_low_energy") is True
