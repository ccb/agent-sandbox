"""The propose verb (#620): the deliberate half of the action-wish channel.

``propose <what I need> [because <why>]`` records a structured
:class:`~text_adventure_games.wishes.ActionWish` via ``Game.log_wish`` and
spends the turn — articulating a capability gap is itself measurable behavior
(the demand side of the self-coding loop, #299/epic #619). The verb is
universal: ``init_actions`` registers it for every game, and any actor —
player included — may use it (player wishes are demand data too).
"""

from __future__ import annotations

from ..enums import ActionName
from ..wishes import ActionWish, TRIGGER_PROPOSED
from .base import Action


class Propose(Action):
    ACTION_NAME = ActionName.PROPOSE
    ACTION_DESCRIPTION = "Record a request for an action the game doesn't offer"
    ARGUMENTS_SCHEMA = {
        "desired": {
            "type": "string",
            "description": (
                "the action you need but don't have, "
                "e.g. 'fill the pot from the sink'"
            ),
            "required": True,
        },
        "reason": {
            "type": "string",
            "description": "why you need it — what it would let you accomplish",
            "connector": "because",
        },
    }

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        payload = command.strip()
        first, _, rest = payload.partition(" ")
        if first.lower() == "propose":
            payload = rest.strip()
        desired, _, reason = payload.partition(" because ")
        self.desired = desired.strip()
        self.reason = reason.strip()
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if not self.desired:
            self.parser.fail(
                "Propose what? Say: propose <the action you need> because <why>."
            )
            return False
        return True

    def apply_effects(self):
        actor = self.character
        location = getattr(actor, "location", None)
        scope: list[str] = []
        if actor is not None:
            scope = sorted(self.parser.get_items_in_scope(actor).keys())
            if location is not None:
                scope += sorted(n for n in location.characters if n != actor.name)
        goals = [
            g.description
            for g in getattr(actor, "goals", []) or []
            if not getattr(g, "done", False)
        ]
        self.game.log_wish(
            ActionWish(
                actor=actor.name if actor is not None else None,
                turn=self.game.turn,
                location=location.name if location is not None else None,
                desired=self.desired,
                reason=self.reason,
                trigger=TRIGGER_PROPOSED,
                goals=goals,
                scope=scope,
                raw_command=self.command,
            )
        )
        return self.parser.ok(
            "Noted — your request was recorded for the world's designers."
        )
