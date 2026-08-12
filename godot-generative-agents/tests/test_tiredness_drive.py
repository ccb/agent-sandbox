"""Tests for accrue_tiredness (#931 follow-up): the independent sleep drive
split off from accrue_energy so hunger and tiredness can no longer be
conflated (eating used to silently cure sleepiness, since both rode the same
Property.ENERGY number -- see backend/drives.py's module docstring).

Mirrors test_energy_drive.py's shape exactly: accrue_tiredness decays its own
"restedness" resource on the same curve accrue_energy used to use for
Property.ENERGY, flipping Property.IS_SLEEPY at the same threshold -- so
today's "sleepy after 1 in-game hour" timing is unchanged, just backed by a
resource sleeping (not eating) restores.

Run with: uv run pytest godot-generative-agents/tests/test_tiredness_drive.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.drives import accrue_tiredness, sleep_accumulation  # noqa: E402
from text_adventure_games.enums import Property  # noqa: E402
from text_adventure_games.things import Character  # noqa: E402


def _char():
    return Character("Maya", "a student", "A tired student.")


def test_tiredness_decays_at_the_default_rate():
    c = _char()
    c.set_property("restedness", 50)
    accrue_tiredness(c)
    # 50 * _RESTEDNESS_DECAY_CONSTANT (0.9933164, tuned for a 1-hour sleepy
    # onset at the configured 15 sec/turn from a full 100 -- see drives.py's
    # comment on the constant).
    assert c.get_property("restedness") == 49.66582


def test_tiredness_never_drops_below_zero():
    c = _char()
    c.set_property("restedness", 0.5)
    accrue_tiredness(c)
    assert c.get_property("restedness") >= 0


def test_low_restedness_flips_is_sleepy():
    # Mirrors accrue_thirst's threshold flip -- a "needs sleep" signal, not
    # the actual is_sleeping state Sleep's apply_effects sets while resting.
    c = _char()
    c.set_property("restedness", 20)
    accrue_tiredness(c)  # crosses the default threshold (20) via decay
    assert c.get_property(Property.IS_SLEEPY) is True


def test_default_decay_makes_a_character_sleepy_after_one_hour():
    # #931 follow-up: _RESTEDNESS_DECAY_CONSTANT is tuned so a character
    # starting fully rested (100, penn_world._furnish_starting_restedness's
    # seed) and decaying at the default rate crosses the low-restedness
    # threshold (20), flipping IS_SLEEPY, at exactly 1 in-game hour -- 240
    # turns at the configured 15 seconds/turn (penn_world.SEC_PER_STEP /
    # sim_config.sec_per_step). Unchanged from accrue_energy's old timing.
    c = _char()
    c.set_property("restedness", 100)
    turns_per_hour = 3600 // 15
    for _ in range(turns_per_hour - 1):
        accrue_tiredness(c)
    assert not c.get_property(Property.IS_SLEEPY)  # not yet, just under 1 hour
    accrue_tiredness(c)
    assert c.get_property(Property.IS_SLEEPY)  # crosses right at 1 hour (turn 240)


def test_accrue_tiredness_never_touches_hunger():
    # #931 follow-up: the whole point of the split -- getting sleepy must
    # never flip (or need) anything on the hunger side.
    c = _char()
    c.set_property("restedness", 5)
    accrue_tiredness(c)
    assert c.get_property(Property.IS_SLEEPY) is True
    assert not c.get_property("is_low_energy")
    assert c.get_property(Property.ENERGY) is False  # untouched, never set


def test_eating_full_while_tired_does_not_clear_is_sleepy():
    # #931 follow-up, the regression this whole split exists to make
    # structurally impossible: restoring Property.ENERGY (what eating does)
    # must never clear a flag that is now entirely restedness's to set and
    # clear.
    from backend.drives import clear_low_energy_if_recovered

    c = _char()
    c.set_property(Property.IS_SLEEPY, True)
    c.set_property(Property.ENERGY, 10)
    c.set_property(Property.ENERGY, 100)  # as if EatPenn just restored it
    clear_low_energy_if_recovered(c)
    assert c.get_property(Property.IS_SLEEPY) is True


def test_sleeping_actually_reaches_the_wake_threshold():
    # #931 follow-up bug (originally hit on accrue_energy, before the
    # split): the per-tick loop must gate the decay on `not IS_SLEEPING`, or
    # decay and sleep_accumulation's recovery run back-to-back every tick and
    # settle into a fixed point BELOW the 99 wake threshold (empirically
    # ~94-99 depending on the decay constant), meaning a sleeping character
    # would decay-and-recover forever without ever actually waking up. This
    # test drives the exact tick order run_simulation.py now uses (accrue_
    # tiredness gated, sleep_accumulation unconditional) and asserts
    # recovery actually terminates.
    c = _char()
    c.set_property("restedness", 15)
    c.set_property(Property.IS_SLEEPING, True)
    for _ in range(200):
        if not c.get_property(Property.IS_SLEEPING):
            accrue_tiredness(c)
        sleep_accumulation(c)
        if not c.get_property(Property.IS_SLEEPING):
            break
    else:
        assert False, "never woke up within 200 ticks -- the decay gate regressed"
    assert not c.get_property(Property.IS_SLEEPING)
    assert not c.get_property(Property.IS_SLEEPY)
    assert c.get_property("restedness") >= 99


def test_sleeping_does_not_restore_energy():
    # #931 follow-up: the other half of the split -- sleep cures tiredness,
    # not hunger. A character who sleeps hungry wakes up rested but still
    # hungry (mirrors test_eating_full_while_tired_does_not_clear_is_sleepy).
    c = _char()
    c.set_property(Property.ENERGY, 10)
    c.set_property("is_low_energy", True)
    c.set_property("restedness", 15)
    c.set_property(Property.IS_SLEEPING, True)
    for _ in range(200):
        sleep_accumulation(c)
        if not c.get_property(Property.IS_SLEEPING):
            break
    assert not c.get_property(Property.IS_SLEEPING)  # she woke up
    assert c.get_property(Property.ENERGY) == 10  # ...but still just as hungry
    assert c.get_property("is_low_energy") is True
