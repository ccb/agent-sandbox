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
"""

from text_adventure_games.enums import Property

_DEFAULT_THRESHOLD = 3
_DEFAULT_ENERGY_LOW_THRESHOLD = 20


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


def accrue_energy(char) -> None:
    """Decay *char*'s ``Property.ENERGY`` by its ``energy_decay_rate`` and flip
    ``is_low_energy`` at the threshold. A no-op when ``energy_decay_rate`` is
    0/absent (the default), so a non-experiment persona is untouched -- same
    opt-in shape as :func:`accrue_thirst`."""
    rate = char.get_property("energy_decay_rate") or 0
    if not rate:
        return
    threshold = (
        char.get_property("energy_low_threshold") or _DEFAULT_ENERGY_LOW_THRESHOLD
    )
    energy = max(0, (char.get_property(Property.ENERGY) or 0) - rate)
    char.set_property(Property.ENERGY, energy)
    if energy <= threshold:
        char.set_property("is_low_energy", True)
