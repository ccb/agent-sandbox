from __future__ import annotations

from collections import defaultdict
import json
from typing import Union

from ..enums import Property

# Property keys are *either* a Property enum member or a plain string -- the
# two are fully interchangeable. Property inherits from ``str``, so an enum
# member IS a string at runtime (same hash, same equality, same dict key).
# The enum just gives autocomplete and a single source of truth for the
# well-known keys; ad-hoc properties stay as raw strings.
PropertyKey = Union[Property, str]


class Thing:
    """
    Supertype that will add shared functionality to Items, Locations and
    Characters.
    """

    def __init__(self, name: str, description: str):
        # A short name for the thing
        self.name = name

        # A description of the thing
        self.description = description

        # Alternate names the parser will also match -- so a multi-word "army
        # cot" answers to "cot", or "coin purse" to "purse". Lowercased; matched
        # by Parser.match_item alongside the canonical name.
        self.aliases: set[str] = set()

        # A dictionary of properties and their values. Well-known boolean keys
        # are enumerated in text_adventure_games.enums.Property (gettable,
        # is_weapon, is_locked, is_dead, ...); games may declare new keys as
        # plain strings without coordinating with the engine.
        self.properties = defaultdict(bool)

        # A set of special command associated with this item. The key is the
        # command text in invoke the special command. The command should be
        # implemented in the Parser.
        self.commands = set()

        # Stimulus-triggered reflexes owned by this thing (see reactions.py).
        # Attached with game.add_reaction and evaluated in the post-round react
        # phase. Runtime-only like a Character's behavior -- they hold live
        # callables/state, so they are re-attached by build_game, never
        # serialized (to_primitive omits them).
        self.reactions: list = []

        # Non-sight senses this thing can be perceived by, each mapped to the
        # text a probe (feel/listen/smell) or an examine-in-the-dark reveals
        # (see perception.py, Layer 2). SIGHT is implicit -- it uses the normal
        # description / examine_text. Empty by default (sight only), so nothing
        # changes until a game opts a thing in via ``perceptible_by``. Build-time
        # config like reactions/veils; not serialized.
        self._senses: dict = {}

    def perceptible_by(self, sense, text: str | None = None):
        """Tag this thing as perceptible by a non-sight *sense* (touch, hearing,
        smell), with the *text* that sense reveals -- e.g.::

            statue.perceptible_by(Sense.TOUCH, "cold stone, taller than you")
            ceiling.perceptible_by(Sense.HEARING, "leathery wings, seething")

        Sight needs no tagging (it uses ``examine_text``). Returns ``self`` so
        calls chain. See docs/design/perception.md."""
        self._senses[sense] = text
        return self

    def senses(self) -> set:
        """The senses that reach this thing: always SIGHT, plus any added."""
        from ..perception import Sense

        return {Sense.SIGHT} | set(self._senses)

    def sense_text(self, sense) -> str | None:
        """What this thing presents to *sense*, or ``None`` if that sense doesn't
        reach it. SIGHT -> ``examine_text`` (or ``description``); a tagged
        non-sight sense -> its text (or a terse generic); untagged -> ``None``."""
        from ..perception import Sense, GENERIC_SENSE_TEXT

        if sense == Sense.SIGHT:
            text = getattr(self, "examine_text", "") or self.description
            # examine_text may be a callable (see actions.things.Examine);
            # sense_text has no game handle, so call it bare.
            return text() if callable(text) else text
        if sense in self._senses:
            return self._senses[sense] or GENERIC_SENSE_TEXT.get(sense, "")
        return None

    def to_primitive(self):
        """
        Puts the main fields of this base class into a dictionary
        representation that can safely be converted to JSON
        """
        thing_data = {
            "name": self.name,
            "description": self.description,
            "commands": list(self.commands),
            "properties": self.properties,
            "aliases": sorted(self.aliases),
        }
        return thing_data

    @classmethod
    def from_primitive(cls, data, instance=None):
        """
        Converts a dictionary of values into an instance.
        """
        if not instance:
            instance = cls(data["name"], data["description"])
        if not "commands" in data:
            data["commands"] = []
        for c in data["commands"]:
            instance.add_command_hint(c)
        if not "properties" in data:
            data["properties"] = {}
        for k, v in data["properties"].items():
            instance.set_property(k, v)
        for a in data.get("aliases", []):
            instance.add_alias(a)
        return instance

    def to_json(self):
        data = self.to_primitive()
        data_json = json.dumps(data)
        return data_json

    @classmethod
    def from_json(cls, data_json):
        data = json.loads(data_json)
        instance = cls.from_primitive(data)
        return instance

    def set_property(self, property_name: PropertyKey, property):
        """
        Sets the property of this item.

        ``property_name`` is either a plain string (``"is_locked"``) or a
        :class:`~text_adventure_games.enums.Property` member
        (``Property.IS_LOCKED``). They are fully interchangeable: every enum
        member IS a string at runtime, so a value set with one form can be
        read back with the other.
        """
        self.properties[property_name] = property

    def to_be(self):
        """'is' or 'are', for number agreement in engine messages ("The
        crates ARE open"). Honors an explicit ``is_plural`` property when one
        is set; otherwise guesses from the head noun -- the word before an
        "of" phrase ("crate of dates" is singular) or the final word
        ("magnetic boots" are plural)."""
        if "is_plural" in self.properties:
            return "are" if self.properties["is_plural"] else "is"
        head = self.name.split(" of ")[0].split()[-1].lower()
        return "are" if head.endswith("s") and not head.endswith("ss") else "is"

    def get_property(self, property_name: PropertyKey):
        """
        Gets the value of this property (defaults to False if unset).

        Accepts the same dual key form as :meth:`set_property`: either a plain
        string or a :class:`~text_adventure_games.enums.Property` member.
        """
        return self.properties.get(property_name, False)

    def add_alias(self, alias: str):
        """Register an alternate name the parser will also match (e.g. ``cot``
        for an item named ``army cot``)."""
        self.aliases.add(alias.lower())

    def add_command_hint(self, command: str):
        """
        Adds a special command to this thing
        """
        self.commands.add(command)

    def get_command_hints(self):
        """
        Returns a list of special commands associated with this object
        """
        return self.commands

    def remove_command_hint(self, command: str):
        """
        Returns a list of special commands associated with this object
        """
        return self.commands.discard(command)
