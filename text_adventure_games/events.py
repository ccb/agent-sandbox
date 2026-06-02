"""Append-only event records for the game's event log.

A GameEvent is a small, serializable record of one thing that happened during
play: who did it (actor), what they did (action), a human-readable summary, and
an optional structured payload. The log itself lives on Game (Game.events); this
module just defines the record type. See
docs/superpowers/specs/2026-06-02-trigger-system-design.md (issue #6).
"""


class GameEvent:
    def __init__(self, turn, actor, action, summary="", payload=None):
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
