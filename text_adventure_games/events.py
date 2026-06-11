"""Append-only event records for the game's event log.

A GameEvent is a small, serializable record of one thing that happened during
play: who did it (actor), what they did (action), a human-readable summary, and
an optional structured payload. The log itself lives on Game (Game.events); this
module just defines the record type (issue #6).

The ``action`` field is most often an action keyword ("go", "attack", ...);
the engine reserves :data:`~text_adventure_games.enums.EventKind` for
non-command kinds (today, just ``EventKind.TRIGGER`` for trigger-fired events).
"""

from __future__ import annotations

from typing import Union

from .enums import ActionName, EventKind

# Accepted values for ``GameEvent.action``. Stored as a plain string at
# runtime; this alias is purely for IDE/type-checker discoverability.
ActionKind = Union[EventKind, ActionName, str]


class GameEvent:
    def __init__(
        self,
        turn: int,
        actor,
        action: ActionKind,
        summary: str = "",
        payload=None,
    ):
        self.turn = turn
        self.actor = actor
        self.action = action
        self.summary = summary
        self.payload = payload or {}

    def to_primitive(self):
        return {
            "turn": self.turn,
            "actor": self.actor,
            "action": self.action,
            "summary": self.summary,
            "payload": self.payload,
        }

    def __repr__(self):
        return (
            f"GameEvent(turn={self.turn}, actor={self.actor!r}, "
            f"action={self.action!r})"
        )
