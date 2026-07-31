"""TDD scaffold (implementation pending) for a Penn-local energy/tiredness
drive, mirroring tests/test_drives.py's thirst drive exactly: a per-tick
accrual, opt-in per character via a rate property, that is a no-op for any
persona that never sets it (so the default mock bake stays byte-identical).

Expect failures (an ImportError at collection, until backend/drives.py grows
`accrue_energy`) -- see the TODOs discussed for wiring an energy/sleep system
into the Penn sim, analogous to Action Castle's SleepGate/Sleep/energy work.

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


def test_energy_decays_at_the_configured_rate():
    c = _char()
    c.set_property(Property.ENERGY, 50)
    c.set_property("energy_decay_rate", 5)
    accrue_energy(c)
    assert c.get_property(Property.ENERGY) == 45


def test_energy_never_drops_below_zero():
    c = _char()
    c.set_property(Property.ENERGY, 2)
    c.set_property("energy_decay_rate", 5)
    accrue_energy(c)
    assert c.get_property(Property.ENERGY) == 0


def test_low_energy_flips_is_sleeping_flag_false_until_threshold():
    # Mirrors accrue_thirst's threshold flip -- a "needs sleep" signal, not
    # the actual is_sleeping state Sleep's apply_effects sets while resting.
    c = _char()
    c.set_property(Property.ENERGY, 15)
    c.set_property("energy_decay_rate", 10)
    c.set_property("energy_low_threshold", 10)
    accrue_energy(c)  # 15 -> 5, below the threshold
    assert c.get_property("is_low_energy") is True
