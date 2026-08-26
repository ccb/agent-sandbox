"""Minimal Penn-local needs/drives (#594, #931, #931 follow-up).

A first, deliberately small slice: a thirst counter that rises per tick and, past
a threshold, flips the engine's ``Property.IS_THIRSTY`` (which ``Drink`` already
clears). It is **opt-in per character** -- a character with no ``thirst_rate`` never
accrues, so the default mock bake is byte-identical. No incapacitation, energy, or
death: max thirst simply holds ``IS_THIRSTY`` true (a persistent drive). A generic
engine drive can be lifted later (as #464 follows #300); this stays backend-local.

``accrue_energy`` (#931) is thirst's sibling for the eat/hunger side: unlike thirst
(a separate rising counter alongside the unrelated boolean flag), energy decay acts
directly on the numeric ``Property.ENERGY`` resource ``EatPenn`` already restores,
floored at 0, flipping ``is_low_energy`` past a threshold -- the perceivable signal
a live brain reads to decide to eat, the same role ``is_thirsty`` plays for drink.
Unlike ``accrue_thirst`` this is not opt-in: every character decays by a fixed
exponential default, unless ``energy_decay_rate`` is set, which switches to a
flat per-tick subtraction instead.

``accrue_tiredness`` (#931 follow-up) is the same shape again, for sleep: its own
independent ``"restedness"`` resource, decaying exactly like ``Property.ENERGY``
does (same curve, same threshold, so today's 1-in-game-hour-to-sleepy timing is
unchanged), flipping ``Property.IS_SLEEPY``. It used to be that ``accrue_energy``
flipped ``IS_SLEEPY`` too, riding the same ``Property.ENERGY`` number hunger uses --
which meant eating (restoring ``Property.ENERGY``) could silently cure tiredness
before ``Sleep`` was ever reached, since food is available everywhere sleep is
(Houston Hall). Splitting tiredness onto its own resource makes that structurally
impossible: hunger and sleepiness are now two fully independent needs, satisfied by
two different actions, the same way thirst and hunger already were.

``accrue_wage`` (#931 follow-up) is a third opt-in sibling of ``accrue_thirst``,
for personas with a job: a ``wage_rate`` pays into ``Property.MONEY`` for every
tick actually spent on an authored ``is_work`` schedule stop, not just for
having a job at all -- Professor Tanaka teaching her own class pays; Tanaka
attending a colleague's talk doesn't.
"""

from text_adventure_games.enums import Property

_DEFAULT_THRESHOLD = 3
_DEFAULT_ENERGY_LOW_THRESHOLD = 20
# Tuned so a character starting at MAX_ENERGY (100, see penn_world.py's
# _furnish_starting_energy) crosses _DEFAULT_ENERGY_LOW_THRESHOLD (20) after
# exactly 1 in-game hour, at the configured 15 seconds/turn
# (penn_world.SEC_PER_STEP / sim_config.sec_per_step): 1*3600/15 = 240 turns,
# decay = (20/100) ** (1/240) ~= 0.9933164 (lands on turn 240 exactly at this
# precision -- fewer decimal places overshoots to turn 241).
_ENERGY_DECAY_CONSTANT = 0.9933164

# Tiredness (#931 follow-up) mirrors energy's curve exactly -- same starting
# value, same threshold, same decay constant -- so an agent still gets sleepy
# after 1 in-game hour, unchanged from before the split. Kept as separate
# constants (not literally reused) so retuning one drive's pacing later can
# never accidentally retune the other's.
_DEFAULT_RESTEDNESS_LOW_THRESHOLD = 20
_RESTEDNESS_DECAY_CONSTANT = 0.9933164


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


def accrue_wage(char) -> None:
    """Pay *char*'s wage into ``Property.MONEY`` for each tick actually spent
    on the clock (#931 follow-up). Opt-in like :func:`accrue_thirst`: a
    persona with no ``wage_rate`` never accrues, so a non-job persona's bake
    is untouched.

    "Actually on the clock" is checked against data the character and its
    schedule already carry, not new state: the current schedule stop
    (``char.agent.schedule``, the pacing object every mock- and real-brain-
    driven agent has) must be authored ``is_work: true``, the character's
    actual location must match that stop's place (on-plan, not off
    deviating), and an ``activity`` must be set (they've settled in, not
    still walking there). Having a job doesn't pay by itself -- performing
    its specific work stop does."""
    rate = char.get_property("wage_rate") or 0
    if not rate:
        return
    stop = getattr(getattr(char, "agent", None), "schedule", None)
    stop = getattr(stop, "_stop", None)
    if not stop or not stop.get("is_work"):
        return
    if char.location is None or char.location.name != stop.get("place"):
        return
    if not char.get_property("activity"):
        return
    char.set_property(Property.MONEY, (char.get_property(Property.MONEY) or 0) + rate)


def accrue_energy(char) -> None:
    """Decay *char*'s ``Property.ENERGY`` every tick and flip ``is_low_energy``
    past a threshold. Unlike :func:`accrue_thirst` this is NOT opt-in: with no
    ``energy_decay_rate`` set, energy still decays by a fixed exponential
    default; setting one switches to a flat per-tick subtraction instead.
    Floored at 0 either way.

    Unconditional -- unlike :func:`accrue_tiredness`, this is never gated on
    ``Property.IS_SLEEPING`` (#931 follow-up): hunger is its own resource now,
    untouched by :func:`sleep_accumulation`, so there is no recovery to fight
    over and nothing wrong with getting hungrier while asleep (the same as
    thirst already does)."""
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


def clear_low_energy_if_recovered(char) -> None:
    """Clear ``is_low_energy`` once ``Property.ENERGY`` climbs back above the
    low-energy threshold (#931 follow-up).

    ``accrue_energy`` only ever *sets* this flag -- it has no ``else`` branch
    to clear it -- because the established pattern in this file is that the
    accrual function signals the need and the action that satisfies it does
    the clearing (mirroring how ``accrue_thirst`` sets ``IS_THIRSTY`` but only
    the engine's ``Drink.apply_effects`` clears it). ``EatPenn``/``DrinkPenn``
    restore ``Property.ENERGY`` directly, bypassing ``accrue_energy``
    entirely, so without this call hunger was a one-way street: eating a
    sandwich fixed the number but never told a live brain the need was met,
    unlike thirst (already handled).

    Never touches ``Property.IS_SLEEPY``: since the tiredness split, that flag
    is entirely :func:`accrue_tiredness`/:func:`sleep_accumulation`'s to set
    and clear -- eating has no more business touching it than it does
    ``IS_THIRSTY``."""
    threshold = (
        char.get_property(Property.ENERGY_LOW_THRESHOLD)
        or _DEFAULT_ENERGY_LOW_THRESHOLD
    )
    if (char.get_property(Property.ENERGY) or 0) > threshold:
        char.set_property("is_low_energy", False)


def accrue_tiredness(char) -> None:
    """Decay *char*'s ``"restedness"`` every tick and flip ``Property.IS_SLEEPY``
    past a threshold (#931 follow-up). The independent sibling of
    :func:`accrue_energy`: same exponential-decay shape, same starting value
    and threshold, so today's "sleepy after 1 in-game hour" timing carries
    over unchanged -- but it is its own resource, restored only by
    :func:`sleep_accumulation`, never by eating.

    Call this gated on ``not Property.IS_SLEEPING`` (mirroring how
    ``accrue_energy`` used to be gated, before hunger and tiredness split):
    decay and :func:`sleep_accumulation`'s recovery fighting over the same
    tick would settle into a fixed point below the wake threshold, and a
    sleeping character would never actually wake up."""
    threshold = _DEFAULT_RESTEDNESS_LOW_THRESHOLD
    restedness = max(
        0, (char.get_property("restedness") or 0) * _RESTEDNESS_DECAY_CONSTANT
    )
    char.set_property("restedness", restedness)
    if restedness <= threshold:
        char.set_property(Property.IS_SLEEPY, True)


SLEEP_RECOVERY_DECAY = 0.9  # mirrors Action Castle's recover_and_wake_up:
# shrinks the deficit from full (100) by this factor each tick (not the
# current value directly), so recovery converges toward full regardless of
# how depleted the resource started.
_WAKE_RESTEDNESS_THRESHOLD = 99  # the deficit only shrinks asymptotically, so
# wake up once nearly full rather than waiting on exact float equality.


def sleep_accumulation(char) -> None:
    """Restore a sleeping character's ``"restedness"`` each tick, and wake
    them once nearly full. A no-op for anyone not currently
    ``Property.IS_SLEEPING`` -- the flag :class:`backend.actions.Sleep` sets
    -- this is the per-tick recovery half of that action, the same "act now,
    drive restores over time" split ``EatPenn``/``accrue_energy`` use for
    eating.

    Restores ``"restedness"`` only (#931 follow-up) -- never
    ``Property.ENERGY``: sleeping cures tiredness, not hunger, the same way
    drinking cures thirst but not hunger. A character who sleeps hungry
    wakes up rested but still hungry."""
    if not char.get_property(Property.IS_SLEEPING):
        return
    deficit = 100 - (char.get_property("restedness") or 0)
    restedness = 100 - deficit * SLEEP_RECOVERY_DECAY
    char.set_property("restedness", restedness)
    if restedness >= _WAKE_RESTEDNESS_THRESHOLD:
        char.set_property(Property.IS_SLEEPING, False)
        char.set_property(Property.IS_SLEEPY, False)
