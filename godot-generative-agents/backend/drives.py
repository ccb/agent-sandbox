"""Minimal Penn-local needs/drives (#594, #931).

A first, deliberately small slice: a thirst counter that rises per tick and, past
a threshold, flips the engine's ``Property.IS_THIRSTY`` (which ``Drink`` already
clears). It is **opt-in per character** -- a character with no ``thirst_rate`` never
accrues, so the default mock bake is byte-identical. No incapacitation, energy, or
death: max thirst simply holds ``IS_THIRSTY`` true (a persistent drive). A generic
engine drive can be lifted later (as #464 follows #300); this stays backend-local.

``accrue_energy`` (#931) is thirst's sibling for the eat/energy side: unlike thirst
(a separate rising counter alongside the unrelated boolean flag), energy decay acts
directly on the numeric ``Property.ENERGY`` resource ``EatPenn`` already restores,
floored at 0, flipping ``is_low_energy`` past a threshold -- the perceivable signal
a live brain reads to decide to eat, the same role ``is_thirsty`` plays for drink.
Unlike ``accrue_thirst`` this is not opt-in: every character decays by a fixed
exponential default, unless ``energy_decay_rate`` is set, which switches to a
flat per-tick subtraction instead.
"""

from text_adventure_games.enums import Property

_DEFAULT_THRESHOLD = 3
_DEFAULT_ENERGY_LOW_THRESHOLD = 20
_ENERGY_DECAY_CONSTANT = 0.9905


def accrue_thirst(char) -> None:
    """Advance *char*'s thirst by its ``thirst_rate`` and flip ``IS_THIRSTY`` at
    the threshold. A no-op when ``thirst_rate`` is 0/absent (the default), so a
    non-experiment persona is untouched."""
    rate = char.get_property("thirst_rate") or 0
    if not rate:
        return
    threshold = char.get_property("thirst_threshold") or _DEFAULT_THRESHOLD
    thirst = (char.get_property("thirst") or 0) + rate
    char.set_property("thirst", thirst)
    if thirst >= threshold:
        char.set_property(Property.IS_THIRSTY, True)
        char.set_property("drank_amount", 0)


def accrue_energy(char) -> None:
    """Decay *char*'s ``Property.ENERGY`` every tick and flip ``is_low_energy``
    (and ``Property.IS_SLEEPY``) past a threshold. Unlike :func:`accrue_thirst`
    this is NOT opt-in: with no ``energy_decay_rate`` set, energy still decays
    by a fixed exponential default; setting one switches to a flat per-tick
    subtraction instead. Floored at 0 either way."""
    rate = char.get_property("energy_decay_rate")

    threshold = (
        char.get_property(Property.ENERGY_LOW_THRESHOLD)
        or _DEFAULT_ENERGY_LOW_THRESHOLD
    )
    if not rate:
        energy = max(0, (char.get_property(Property.ENERGY)) * _ENERGY_DECAY_CONSTANT)
    else:
        energy = max(0, (char.get_property(Property.ENERGY)) - rate)

    char.set_property(Property.ENERGY, energy)
    if energy <= threshold:
        char.set_property(
            "is_low_energy", True
        )  # if low energy some actions cannot be performed
        char.set_property(Property.IS_SLEEPY, True)


SLEEP_RECOVERY_DECAY = 0.9  # mirrors Action Castle's recover_and_wake_up:
# shrinks the energy *deficit* from MAX_ENERGY by this factor each tick (not
# current energy directly), so recovery converges toward full regardless of
# how low energy started.
_WAKE_ENERGY_THRESHOLD = 99  # the deficit only shrinks asymptotically, so
# wake up once nearly full rather than waiting on exact float equality.


def sleep_accumulation(char) -> None:
    """Restore a sleeping character's ``Property.ENERGY`` each tick, and wake
    them once nearly full. A no-op for anyone not currently
    ``Property.IS_SLEEPING`` -- the flag :class:`backend.actions.Sleep` sets
    -- this is the per-tick recovery half of that action, the same "act now,
    drive restores over time" split ``EatPenn``/``accrue_energy`` use for
    eating."""
    if not char.get_property(Property.IS_SLEEPING):
        return
    deficit = 100 - (char.get_property(Property.ENERGY) or 0)
    energy = 100 - deficit * SLEEP_RECOVERY_DECAY
    char.set_property(Property.ENERGY, energy)
    if energy >= _WAKE_ENERGY_THRESHOLD:
        char.set_property(Property.IS_SLEEPING, False)
        char.set_property(Property.IS_SLEEPY, False)
        char.set_property("is_low_energy", False)
