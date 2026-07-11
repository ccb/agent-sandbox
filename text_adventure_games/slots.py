"""Item slots and wounds -- Vaults of Vaarn's shared carrying/harm gauge.

In Vaarn (Issue 1, pp. 4-6) a character has a fixed number of **item slots**
that both their luggage and their injuries occupy: carrying past capacity makes
you *Encumbered*, and damage past 0 HP becomes **Wounds** that fill the same
slots -- "if a character fills [their] item slots with Wounds they will die."
Body and baggage share one gauge: the more broken you are, the less you can
carry.

This layer is **opt-in and zero-cost**: ``Character.slot_capacity`` is ``None``
by default (unlimited carrying, no wounds tracked against a limit), so every
existing game is unchanged. A game opts in per character::

    player.slot_capacity = 10          # Vaarn-typical
    sword.set_property("slots", 2)     # heavy; unset items cost 1

Consequences the engine wires when capacity is set:

- Capacity is a **hard limit**: ``Get`` refuses anything that would not fit,
  and warns when the gauge fills (a FULL pack is Encumbered).
- An encumbered character's movement emits a sound (the clatter of an
  overloaded pack) and cannot use exits the game marks as climbs
  (``location.set_property("climb_exits", {"up"})``).
- A new wound always fits: it shoves random gear out of the pack to make room
  (``add_wound`` returns what was displaced).
- ``INVENTORY`` reports ``Slots: used/capacity`` and lists wounds.

Wounds are added by games (a hazard's final tick, a lost fight) via
``character.add_wound(...)`` or the d20 :data:`WOUND_TABLE` via
:func:`roll_wound`. A wound is fatal when wounds alone fill capacity.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass

from .enums import Property


def item_slot_cost(item) -> int:
    """The slots *item* occupies: its ``slots`` property, defaulting to 1."""
    return int(item.get_property("slots") or 1)


@dataclass
class Wound:
    """An injury occupying item slots (0-slot wounds are narrative-only)."""

    name: str
    slots: int
    description: str


#: The d20 wound table (Vaults of Vaarn Issue 1, p. 6). Index by roll - 1.
#: Rolls 2 (Damaged Item), 19 (Bloody Mess), and 20 (FATALITY) are specials
#: handled by :func:`roll_wound`.
WOUND_TABLE = [
    Wound("Just a Scratch", 0, "You were lucky, this time."),
    Wound("Damaged Item", 0, "A random inventory item is destroyed."),
    Wound("Bloody Mouth", 1, "Your mouth drools blood and your speech slurs."),
    Wound("Scrambled Nerves", 1, "Your hands answer you a half-beat late."),
    Wound("Teeth Knocked Out", 1, "You count the gaps with your tongue."),
    Wound("Addling Blow", 1, "The room keeps arriving a moment after you look at it."),
    Wound("Stomach Wound", 1, "You fold around it and keep moving."),
    Wound("Weakening Wound", 1, "Your grip has lost its conviction."),
    Wound("Crippling Blow", 1, "One leg negotiates every step."),
    Wound("Bloody Gash", 1, "It will scar, if you live to own it."),
    Wound("Major Fracture", 2, "A limb answers only under protest."),
    Wound("Lost an Eye", 2, "Half the world becomes rumor."),
    Wound("Cracked Skull", 2, "Your thoughts walk with a limp."),
    Wound("Mangled Guts", 2, "You hold yourself together, literally."),
    Wound("Severed Hand", 2, "The hand is gone. The habit of it remains."),
    Wound("Severed Arm", 3, "The arm is gone at the shoulder."),
    Wound("Severed Leg", 3, "The leg is gone. The ground is far."),
    Wound("Braindead", 3, "Something essential has gone dark."),
    Wound("Bloody Mess", 0, "Everything, everywhere, at once."),
    Wound("FATALITY", 99, "You are dead."),
]


def roll_wound(character, roll=None, rng=None, game=None):
    """Apply the d20 wound table to *character*.

    *roll* forces a row (1-20) for scripted/deterministic use; otherwise *rng*
    (default: the module's random) rolls. Returns ``(wounds, messages, fatal)``
    -- the Wound records added, the narration lines for the caller to print,
    and whether the character is now dead (FATALITY, or wounds filling
    capacity). Specials:

    - **2 Damaged Item**: destroys a random carried item instead of wounding.
    - **19 Bloody Mess**: rolls three more wounds.
    - **20 FATALITY**: death outright.
    """
    rng = rng or _random
    roll = roll if roll is not None else rng.randint(1, 20)
    row = WOUND_TABLE[max(1, min(20, roll)) - 1]
    messages, wounds = [], []

    def _say(line):
        """Every table outcome is harm and speaks in the damage voice (CCB):
        red on the terminal, one consistent channel. Without a game (bare
        mechanical use) the line rides the messages list as before."""
        if game is not None:
            game.parser.damage(line)
        else:
            messages.append(line)

    if row.name == "Damaged Item":
        pool = list(character.inventory.values())
        if pool:
            item = rng.choice(pool)
            character.remove_from_inventory(item)
            _say(
                f"{row.name} - The blow lands on your pack: the {item.name} "
                "is smashed beyond use."
            )
        else:
            _say(
                f"{row.name} - The blow lands on your pack, which is mercifully empty."
            )
        return wounds, messages, False

    if row.name == "FATALITY":
        # The kill keeps the ledger honest (CCB): the fatal blow lands as a
        # real wound sized to every slot the body has left, so death always
        # reads as wounds filling capacity -- never as bookkeeping magic.
        cap = character.slot_capacity
        slots_n = max(1, cap - character.wound_slots()) if cap else row.slots
        wound = Wound(row.name, slots_n, row.description)
        fatal, _ = character.add_wound(wound, rng=rng)
        wounds.append(wound)
        if game is not None:
            game.parser.damage(f"{row.name} - {row.description}")
        else:
            messages.append(f"{row.name}: {row.description}")
        if not fatal:  # no slot system configured: the row still kills outright
            character.set_property(Property.IS_DEAD, True)
        return wounds, messages, True

    if row.name == "Bloody Mess":
        fatal = False
        for _ in range(3):
            w, m, f = roll_wound(character, roll=rng.randint(1, 18), rng=rng, game=game)
            wounds.extend(w)
            messages.extend(m)
            fatal = fatal or f
        return wounds, messages, fatal

    if row.name == "Just a Scratch":
        _say(f"{row.name} - {row.description}")
        return wounds, messages, False

    fatal, dropped = character.add_wound(
        Wound(row.name, row.slots, row.description), rng=rng
    )
    wounds.append(row)
    if game is not None:
        # The standard damage line, on its own channel ("[damage] Cracked
        # Skull - Your thoughts walk with a limp.").
        game.parser.damage(f"{row.name} - {row.description}")
    else:
        messages.append(f"{row.name}: {row.description}")
    for item in dropped:
        _say(f"Your grip fails: the {item.name} spills from your pack.")
    if fatal:
        _say("Your body has no room left to be hurt in. You are dead.")
    return wounds, messages, fatal
