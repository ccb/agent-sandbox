"""Tests for accrue_energy (#931): a Penn-local hunger drive, mirroring
tests/test_drives.py's thirst drive: a per-tick decay that, unlike thirst, runs
by default (an unconfigured character still decays at a fixed exponential
rate) and switches to a linear ``energy_decay_rate`` once a persona opts into
one -- see accrue_energy's docstring in backend/drives.py.

Tiredness (Property.IS_SLEEPY) used to ride this same Property.ENERGY number
and is now its own independent resource ("restedness") -- see
test_tiredness_drive.py for accrue_tiredness/sleep_accumulation.

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
    # 50 * _ENERGY_DECAY_CONSTANT (0.9933164, tuned for a 1-hour low-energy
    # onset at the configured 15 sec/turn from MAX_ENERGY -- see drives.py's
    # comment on the constant).
    assert c.get_property(Property.ENERGY) == 49.66582


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


def test_low_energy_flips_is_low_energy_flag_at_threshold():
    # Mirrors accrue_thirst's threshold flip -- a "needs food" signal.
    c = _char()
    c.set_property(Property.ENERGY, 20)
    c.set_property("energy_decay_rate", 10)
    c.set_property("energy_low_threshold", 10)
    accrue_energy(c)  # 20 -> 10, at the threshold
    assert c.get_property("is_low_energy") is True


def test_accrue_energy_never_touches_is_sleepy():
    # #931 follow-up: hunger and tiredness used to ride the same
    # Property.ENERGY number, so accrue_energy flipped IS_SLEEPY too. They're
    # independent resources now -- accrue_energy has no business touching a
    # flag that belongs entirely to accrue_tiredness/sleep_accumulation.
    c = _char()
    c.set_property(Property.ENERGY, 5)
    accrue_energy(c)
    assert c.get_property("is_low_energy") is True
    assert not c.get_property(Property.IS_SLEEPY)


def test_accrue_energy_runs_even_while_sleeping():
    # #931 follow-up: accrue_energy used to be gated on `not IS_SLEEPING`
    # because it shared a resource with sleep_accumulation's recovery. Now
    # that hunger and tiredness are independent, there's nothing to fight
    # over -- a sleeping character should just keep getting hungrier, the
    # same as thirst already does regardless of sleep.
    c = _char()
    c.set_property(Property.ENERGY, 50)
    c.set_property(Property.IS_SLEEPING, True)
    accrue_energy(c)
    assert c.get_property(Property.ENERGY) < 50
