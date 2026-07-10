"""InvisiClues, in-engine: progressive hints in the style of Infocom's
late-era in-game hint menus (Zork Zero, Arthur, the Solid Gold line).

A game registers :class:`Hint` topics -- a player-facing QUESTION and an
escalating ladder of *levels*, the first a nudge and the last walkthrough-
grade. The HINT action (:mod:`.actions.hints`) lists the questions whose
puzzles the player has actually met (``available``) and not yet beaten
(``resolved``), so the menu itself never spoils what lies ahead; asking about
a topic reveals ONE more level per ask, and revealed levels stay revealed.

Both gates are predicates over the live game, in the same house style as
triggers and hazards::

    game.add_hint(Hint(
        key="troll",
        question="How do I get past the troll?",
        levels=[
            "Have you tried talking to it?",
            "The troll is hungry, and you are not the only food here.",
            "GIVE FISH TO TROLL.",
        ],
        available=lambda g: g.locations["Bridge"].has_been_visited,
        resolved=lambda g: g.characters["troll"].get_property("is_dead"),
    ))

Progress lives in ``game.hint_progress`` and survives saves for free: HINT is
a journaled free action (it costs no turn, but enters the journal), so a
(seed, journal) replay rebuilds exactly what had been revealed.
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class Hint:
    """One hint topic: a question and its ladder of increasingly explicit
    answers.

    - *key*: short stable identifier ("troll") -- typable as ``HINT TROLL``
      and used to store reveal progress.
    - *question*: the menu line, phrased as the player would ask it.
    - *levels*: escalating reveals; order them nudge -> spoiler.
    - *available*: ``game -> bool``; the topic is listed only while true
      (default: always). Gate on the player having MET the puzzle.
    - *resolved*: ``game -> bool``; once true the topic drops off the menu
      (default: never). Gate on the puzzle being beaten.
    """

    key: str
    question: str
    levels: List[str] = field(default_factory=list)
    available: Optional[Callable] = None
    resolved: Optional[Callable] = None

    def is_available(self, game) -> bool:
        return self.available is None or bool(self.available(game))

    def is_resolved(self, game) -> bool:
        return self.resolved is not None and bool(self.resolved(game))

    def is_open(self, game) -> bool:
        """Listed on the menu: met, and not yet beaten."""
        return self.is_available(game) and not self.is_resolved(game)
