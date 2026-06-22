"""Posed prompts (issue #110): the game asking the player a question.

A lot of interactive fiction puts the player at a fork that expects a *reply*
rather than a fresh command: "Choose a weapon: wits or steel.", a riddle to
answer, "Do you accept? (yes/no)". Historically each game wired this as a set
of bespoke verbs (``choose wits``, ``say yes``) and then leaked the syntax to
the player in parentheses so they'd know the magic words.

A :class:`Prompt` lets the game *pose* the question (``Game.pose_prompt``) and
describe the answers once. While a prompt is pending, the parser consults it
**as a fallback** -- only after a command fails to resolve to a real action --
so the player can still ``look`` / check ``inventory`` mid-conversation; it is
never modal. A bare ``wits`` then resolves to the ``choose wits`` command, and
a free-text riddle answer is forwarded to the answering verb.

Two shapes, both expressed with the same dataclass:

* **choice** -- ``options`` maps each answer keyword to the command to run when
  the player picks it (``{"wits": "choose wits", "steel": "choose steel"}``).
* **free-text** -- ``forward_as`` is set; the player's whole reply is appended
  to it (``forward_as="answer riddle"`` turns ``a wise man`` into
  ``answer riddle a wise man``). ``options`` is ignored.

Prompts are transient conversational state, like a character's ``behavior`` --
they are not serialized. A prompt is cleared when it is answered, when another
is posed in its place, or when the player leaves the room it was posed in
(unless ``sticky``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Prompt:
    """A question the game has posed to the player. See the module docstring."""

    text: str = ""
    # Choice prompts: answer keyword -> command to dispatch when chosen.
    options: dict[str, str] = field(default_factory=dict)
    # Free-text prompts: the verb the player's whole reply is forwarded to.
    # When set, the prompt is free-text and `options` is ignored.
    forward_as: str | None = None
    # Who posed it (flavor; available to a renderer/LLM for context).
    speaker: str | None = None
    # If True, the prompt survives the player moving to another location.
    sticky: bool = False
    # Stamped by Game.pose_prompt: the location name where it was posed, used
    # for expiry-on-move. Authors don't set this.
    location: str | None = None

    @property
    def free_text(self) -> bool:
        return self.forward_as is not None
