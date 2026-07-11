"""Probe verbs -- feel / listen / smell (perception Layer 2).

These exercise the non-sight senses a thing was tagged ``perceptible_by`` (see
perception.py). Unlike ``examine``, a probe works *regardless of light* -- that's
the point: you can ``feel`` your way through a pitch-dark room, or ``listen`` for
what you can't see.

They are **opt-in**: a game turns them on with ``game.enable_senses()`` (which
registers these), so games that don't want them keep a lean verb set. For that
reason this module is intentionally NOT imported by ``actions/__init__`` -- the
engine's auto-discovery of default actions would otherwise make them always-on.
"""

from . import base
from ..enums import Property
from ..perception import Sense


def _join(items) -> str:
    """'a', 'a and b', or 'a, b, and c'."""
    items = list(items)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


class _Probe(base.Action):
    """Shared plumbing for the sense probes. A probe matches an optional target
    (an item in scope or a character in the room); with no target it probes the
    room itself. Subclasses set :attr:`SENSE` and supply the room-level text."""

    SENSE: Sense = None

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command, hint="the one sensing")
        self.matched_item = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="thing sensed"
        )
        self.matched_character = (
            None
            if self.matched_item
            else self.character_in_room(command, self.character)
        )

    def check_preconditions(self) -> bool:
        return self.was_matched(self.character, "No character was matched.")

    def apply_effects(self):
        target = self.matched_item or self.matched_character
        if target is not None:
            self.parser.ok(target.sense_text(self.SENSE) or self._nothing_from(target))
        else:
            self.parser.ok(self._probe_room(self.character.location))

    # -- subclass hooks --
    def _nothing_from(self, target) -> str:
        raise NotImplementedError

    def _probe_room(self, loc) -> str:
        raise NotImplementedError

    def _room_texts(self, loc) -> list:
        """The sense-texts of every visible thing in *loc* tagged for this sense
        (items and characters), skipping hidden ones."""
        out = []
        for holder in (loc.items, loc.characters):
            for thing in holder.values():
                if thing is self.character:
                    continue
                if thing.get_property("is_hidden"):
                    continue
                if self.SENSE in thing.senses():
                    out.append(thing.sense_text(self.SENSE))
        return out


class Feel(_Probe):
    """Feel your way around -- the canonical dark-navigation probe. ``feel`` (with
    no target) gropes the room, revealing its exits and any TOUCH-tagged fixtures;
    ``feel <thing>`` reads that thing's touch text."""

    ACTION_NAME = "feel"
    ACTION_DESCRIPTION = (
        "Feel your way around, or feel a specific thing (works in the dark)"
    )
    ACTION_ALIASES = ["grope", "grope around", "feel around", "feel your way", "touch"]
    SENSE = Sense.TOUCH

    def _nothing_from(self, target) -> str:
        return f"You run your hands over {target.name} -- nothing you couldn't already tell."

    def _probe_room(self, loc) -> str:
        found = [f"a way {d}" for d in loc.connections]
        for it in loc.items.values():
            if Sense.TOUCH in it.senses() and not it.get_property("is_hidden"):
                found.append(
                    it.description
                )  # the noun-phrase, not the full touch sentence
        if not found:
            return "You grope around but feel nothing -- no way out within reach, and nothing to touch."
        return "You feel your way around and find " + _join(found) + "."


class Listen(_Probe):
    """Listen -- for a thing, or (no target) for whatever the room is making."""

    ACTION_NAME = "listen"
    ACTION_DESCRIPTION = "Listen -- to a thing, or to the room around you"
    ACTION_ALIASES = ["listen to", "listen for"]
    SENSE = Sense.HEARING

    def _nothing_from(self, target) -> str:
        return f"You listen to {target.name}, but hear nothing telling."

    def _probe_room(self, loc) -> str:
        heard = self._room_texts(loc)
        return (
            " ".join(heard) if heard else "You listen. Nothing but your own breathing."
        )


class Smell(_Probe):
    """Smell -- a thing, or (no target) the air of the room."""

    ACTION_NAME = "smell"
    ACTION_DESCRIPTION = "Smell -- a thing, or the air around you"
    ACTION_ALIASES = ["sniff", "smell of"]
    SENSE = Sense.SMELL

    def _nothing_from(self, target) -> str:
        return f"You smell {target.name}, but it has no notable scent."

    def _probe_room(self, loc) -> str:
        smelled = self._room_texts(loc)
        return (
            " ".join(smelled)
            if smelled
            else "The air here smells of nothing in particular."
        )


class Taste(_Probe):
    """Taste (or LICK) a thing -- the cautious cousin of EAT. A taste never
    consumes anything; it reads the thing's flavor and owns up to whether it
    is food. Sources, in order: a ``perceptible_by(Sense.TASTE, ...)`` tag
    (a full authored sentence), the ``Property.TASTE`` string Eat/Drink
    already narrate ("It tastes of ..."), and finally an edibility verdict."""

    ACTION_NAME = "taste"
    ACTION_DESCRIPTION = (
        "Taste a thing -- a lick tells you if it's food (never eats it)"
    )
    ACTION_ALIASES = ["lick"]
    SENSE = Sense.TASTE

    def _nothing_from(self, target) -> str:
        if target is self.matched_character:
            return (
                f"You are not going to lick {target.name}. Some questions "
                "are better asked out loud."
            )
        line = None
        taste = target.get_property(Property.TASTE)
        if taste:
            line = f"You touch the {target.name} to your tongue. It tastes {taste}"
            if not line.endswith((".", "!", "?")):
                line += "."
        if target.get_property(Property.IS_POISONOUS):
            return (
                (line or f"You touch the {target.name} to your tongue.")
                + " Something under the taste your body flatly refuses -- swallowing this would be worse."
            )
        if target.get_property(Property.EDIBLE):
            return (
                line
                or f"You taste the {target.name}: plain, but nothing wrong with it."
            ) + " But you could eat it."
        return (
            line
            or f"You touch your tongue to the {target.name}. It is not food, "
            "and now you are both certain of it."
        )

    def _probe_room(self, loc) -> str:
        tasted = self._room_texts(loc)
        return (
            " ".join(tasted)
            if tasted
            else "You taste the air: stone, dust, and your own thirst."
        )
