"""
Per-character knowledge / beliefs (issue #45).

A :class:`Knowledge` is a small bag of :class:`Belief`s that a character holds
about the world. Beliefs are what the character *thinks is true* -- they may be
incomplete (the troll doesn't know a key exists) or even wrong (a belief whose
text contradicts the world graph). Some are known up front (the guard knows the
tower is locked); some are learned during play via :meth:`Knowledge.learn`.

This is deliberately distinct from memory (#37):

* **Memory** is the episodic *log* of what a character observed or did.
* **Knowledge** is the character's current *world-model* -- "what's true now".

Beliefs are context, not authority: the world graph stays the single source of
truth. A belief only shapes what the agent reasons about (and, via a matching
``secret_topic``, what it can perceive); it never mutates the world. Only actions
through the precondition gate do that.

This module is pure data with no engine imports, so it stays easy to unit-test
and easy for a first-year student to read.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Belief:
    """A single thing a character believes about the world.

    Kept to three fields on purpose (mirroring the restraint of ``Goal``):

    * ``text`` -- the belief in plain language, e.g.
      "The tower door is locked and I hold the only brass key."
    * ``topic`` -- an optional lookup key. A belief whose ``topic`` matches a
      Thing's ``secret_topic`` property unlocks perception of that hidden Thing
      (see :meth:`Knowledge.knows_about` and ``Game.describe_for``).
    * ``learned_turn`` -- ``None`` for prior knowledge known up front; otherwise
      the turn number on which the belief was learned during play.

    There is intentionally no ``confidence`` or ``source`` field: the
    "uncertain or wrong" axis lives in the belief text itself.
    """

    text: str
    topic: str | None = None
    learned_turn: int | None = None


class Knowledge:
    """The set of beliefs a single character holds.

    One flat list of beliefs is the single source of truth -- there is no
    separate "known secrets" set. The belief that unlocks a secret *is* a
    belief, so it renders into the observation like any other.
    """

    def __init__(self, owner: str = ""):
        self.owner = owner
        self.beliefs: list[Belief] = []

    def add(
        self, text: str, topic: str | None = None, learned_turn: int | None = None
    ) -> Belief:
        """Add a belief and return it. Used for prior knowledge seeded up front
        (``learned_turn`` left as ``None``)."""
        belief = Belief(text=text, topic=topic, learned_turn=learned_turn)
        self.beliefs.append(belief)
        return belief

    def learn(self, text: str, turn: int, topic: str | None = None) -> Belief:
        """Learn a belief during play, stamping it with the current turn.

        Sugar over :meth:`add` that records *when* the belief was acquired so
        it can be distinguished from up-front priors.
        """
        return self.add(text, topic=topic, learned_turn=turn)

    def knows_about(self, topic: str | None) -> bool:
        """Whether any belief carries this ``topic``.

        This is the perception-gating hook: a Thing flagged
        ``secret_topic="runes"`` is visible only to a character for whom
        ``knows_about("runes")`` is true. An empty/``None`` topic never matches
        (so a topicless belief can't accidentally unlock anything)."""
        if not topic:
            return False
        return any(b.topic == topic for b in self.beliefs)

    def believes(self, substr: str) -> bool:
        """Case-insensitive scan of belief text. Handy for tests and for
        rule-based agents that branch on what the character believes."""
        needle = substr.lower()
        return any(needle in b.text.lower() for b in self.beliefs)

    def render(self) -> str:
        """Render the beliefs as an observation section.

        Returns ``""`` when there are no beliefs -- this empty-render guard is
        load-bearing: an un-seeded character's observation stays byte-identical
        to before this feature existed. Otherwise returns a "What you know:"
        header followed by one bullet per belief.
        """
        if not self.beliefs:
            return ""
        lines = ["What you know:"]
        for b in self.beliefs:
            lines.append(f" - {b.text}")
        return "\n".join(lines)

    def to_primitive(self) -> dict:
        """Serialize to JSON-safe primitives (mirrors ``Goal`` serialization)."""
        return {
            "owner": self.owner,
            "beliefs": [
                {"text": b.text, "topic": b.topic, "learned_turn": b.learned_turn}
                for b in self.beliefs
            ],
        }

    @classmethod
    def from_primitive(cls, data: dict) -> "Knowledge":
        """Reconstruct a Knowledge from :meth:`to_primitive` output."""
        instance = cls(owner=data.get("owner", ""))
        for b in data.get("beliefs", []):
            instance.beliefs.append(
                Belief(
                    text=b["text"],
                    topic=b.get("topic"),
                    learned_turn=b.get("learned_turn"),
                )
            )
        return instance
