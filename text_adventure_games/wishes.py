"""The action-wish record (#620): a structured "an actor wanted an action the
game doesn't have" snapshot — the demand side of the self-coding loop (#299,
epic #619).

A wish is created three ways: deliberately, via the ``propose`` verb
(``trigger="proposed"``, issue #620); automatically when a command matches no
verb at all (``trigger="parse_gap"``, issue #621); or automatically when a
crafting command (``make <target>``) routes into CRAFT — a recipe is
registered somewhere in the game — but names no recipe at all
(``trigger="craft_gap"``, issue #628). The constants are reserved here so
downstream consumers key on one vocabulary. The log itself lives on ``Game``
(``Game.wishes`` / ``Game.log_wish``); this module just defines the record
type, mirroring ``events.py``/``GameEvent``.

``goals`` and ``scope`` are snapshots of the situation the want arose in — the
consumer (a world-author reading the most-wanted report #623, or later #301's
propose_code) needs the context, not just the want.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TRIGGER_PROPOSED = "proposed"  # the actor explicitly proposed a missing action
TRIGGER_PARSE_GAP = "parse_gap"  # #621: command matched no verb at all
TRIGGER_CRAFT_GAP = "craft_gap"  # #628: CRAFT ran but named no recipe at all


@dataclass
class ActionWish:
    actor: str | None  # character name (None only if no actor resolved)
    turn: int
    location: str | None  # location name at wish time
    desired: str  # the action, as the actor stated it
    reason: str = ""  # the because-clause; "" for parse gaps
    trigger: str = TRIGGER_PROPOSED
    goals: list[str] = field(default_factory=list)  # incomplete goals, described
    scope: list[str] = field(default_factory=list)  # item/character names in scope
    raw_command: str = ""  # the full command that produced the record
    meta: dict = field(default_factory=dict)  # extension point (#41 nouns, ...)

    def to_primitive(self) -> dict:
        """A JSON-ready dict, one line of the eventual wishes.jsonl (#622)."""
        return {
            "actor": self.actor,
            "turn": self.turn,
            "location": self.location,
            "desired": self.desired,
            "reason": self.reason,
            "trigger": self.trigger,
            "goals": list(self.goals),
            "scope": list(self.scope),
            "raw_command": self.raw_command,
            "meta": dict(self.meta),
        }
