from . import base
from ..enums import ActionName, Property

# from ..things import Character  # , Item


def _conj(character, second: str, third: str) -> str:
    """Conjugate a verb for the actor: the player (named "you") gets second
    person ("You eat"), everyone else third ("Troll eats")."""
    return second if character.name.lower() == "you" else third


class Eat(base.Action):
    ACTION_NAME = ActionName.EAT
    ACTION_DESCRIPTION = "Eat something"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="eater")
        self.item = self.parser.match_item(
            command, self.character.carried_items(), hint="food"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * There must be a matched item
        * The item must be food
        * The food must be carried by the character (in hand or a container)
        """
        if not self.was_matched(
            self.item, error_message="I don't know what you want to eat"
        ):
            return False
        elif not self.item.get_property(Property.EDIBLE):
            description = "That's not edible."
            self.parser.fail(description)
            return False
        elif self.item.name not in self.character.carried_items():
            description = "You don't have it."
            self.parser.fail(description)
            return False
        return True

    def apply_effects(self):
        """
        Effects:
        * Removes the food from wherever it is carried so it is consumed.
        * Causes the character's hunger to end
        * Describes the taste (if the "taste" property is set)
        * If the food is poisoned, it causes the character to die.
        """
        self.character.discard_item(self.item)
        self.character.set_property(Property.IS_HUNGRY, False)
        description = "{name} {verb} the {food}.".format(
            name=self.character.name.capitalize(),
            verb=_conj(self.character, "eat", "eats"),
            food=self.item.name,
        )

        if self.item.get_property(Property.TASTE):
            description += " It tastes {taste}".format(
                taste=self.item.get_property(Property.TASTE)
            )

        if self.item.get_property(Property.IS_POISONOUS):
            self.character.set_property(Property.IS_DEAD, True)
            description += " The {food} is poisonous. {name} died.".format(
                food=self.item.name, name=self.character.name.capitalize()
            )
        self.parser.ok(description)


class Drink(base.Action):
    ACTION_NAME = ActionName.DRINK
    ACTION_DESCRIPTION = "Drink something"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="drinker")
        self.item = self.parser.match_item(
            command, self.character.carried_items(), hint="drink"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * There must be a matched item
        * The item must be a drink
        * The drink must be carried by the character (in hand or a container)
        """
        if not self.was_matched(
            self.item, error_message="I don't know what you want to drink"
        ):
            return False
        elif not self.item.get_property(Property.DRINKABLE):
            description = "That's not drinkable."
            self.parser.fail(description)
            return False
        elif self.item.name not in self.character.carried_items():
            description = "You don't have it."
            self.parser.fail(description)
            return False
        return True

    def apply_effects(self):
        """
        Effects:
        * Removes the drink from wherever it is carried so it is consumed.
        * Causes the character's thirst to end
        * Describes the taste (if the "taste" property is set)
        * If the drink is poisoned, it causes the character to die.
        """
        self.character.discard_item(self.item)
        self.character.set_property(Property.IS_THIRSTY, False)
        description = "{name} {verb} the {drink}.".format(
            name=self.character.name.capitalize(),
            verb=_conj(self.character, "drink", "drinks"),
            drink=self.item.name,
        )
        self.parser.ok(description)

        if self.item.get_property(Property.TASTE):
            description = "It tastes {taste}".format(
                taste=self.item.get_property(Property.TASTE)
            )
            self.parser.ok(description)

        if self.item.get_property(Property.IS_POISONOUS):
            self.character.set_property(Property.IS_DEAD, True)
            description = "The {drink} is poisonous. {name} died.".format(
                drink=self.item.name, name=self.character.name.capitalize()
            )
            self.parser.ok(description)

        if self.item.get_property(Property.IS_ALCOHOL):
            self.character.set_property(Property.IS_DRUNK, True)
            description = "{name} {verb} now drunk from {drink}.".format(
                drink=self.item.name,
                name=self.character.name.capitalize(),
                verb=_conj(self.character, "are", "is"),
            )
            self.parser.ok(description)


class Light(base.Action):
    ACTION_NAME = ActionName.LIGHT
    ACTION_DESCRIPTION = "Light something flammable like a lamp or a candle"
    ACTION_ALIASES = ["turn on"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="lighting fire")
        self.item = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="flamable"
        )

    @staticmethod
    def _is_held(character, item) -> bool:
        """True if *character* is carrying *item* -- in hand, worn, wielded, or
        inside an open container they carry (a lantern stowed in a backpack).
        Mirrors Darkness._carries_light, so you can LIGHT a lantern without
        fishing it out of the pack first."""
        for slot in (character.inventory, character.worn, character.wielded):
            if item.name in slot:
                return True
        for holder in character.inventory.values():
            if item.name in holder.accessible_contents():
                return True
        return False

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * There must be a matched item
        * The item must be held (in hand, worn, wielded, or a carried container)
        * The item must be lightable
        """
        if not self.was_matched(
            self.item, error_message="I don't know what you want to light"
        ):
            return False
        if not self._is_held(self.character, self.item):
            self.parser.fail(
                "{name} does not have {item_name}".format(
                    name=self.character.name.capitalize(), item_name=self.item.name
                )
            )
            return False
        if not self.item.get_property(Property.FLAMMABLE):
            description = "That's not something that can be lit."
            self.parser.fail(description)
            return False
        if self.item.get_property(Property.IS_LIT):
            description = "It is already lit."
            self.parser.fail(description)
            return False
        return True

    def apply_effects(self):
        """
        Effects:
        * Changes the state to lit
        """
        self.item.set_property(Property.IS_LIT, True)
        # Item-subject phrasing so it reads right for any actor -- "You lights the
        # lamp" (player named "you") would be ungrammatical.
        description = "The {item} flares alight and glows.".format(item=self.item.name)
        self.parser.ok(description)


class Douse(base.Action):
    """Put out something you've lit -- the inverse of :class:`Light`. Turns a lit
    lamp/torch/lantern back off, so a light source can be a toggle: light it to
    see (or to satisfy a Darkness block/veil), douse it to go dark and quiet
    again."""

    ACTION_NAME = ActionName.DOUSE
    ACTION_DESCRIPTION = "Put out something you've lit (a lamp, torch, or lantern)"
    ACTION_ALIASES = [
        "extinguish",
        "put out",
        "turn off",
        "snuff",
        "snuff out",
        "dim",
        "darken",
    ]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="dousing a light")
        self.item = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="lit light"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * There must be a matched item
        * The item must be held (in hand, worn, wielded, or a carried container)
        * The item must currently be lit
        """
        if not self.was_matched(
            self.item, error_message="I don't know what you want to put out"
        ):
            return False
        if not Light._is_held(self.character, self.item):
            self.parser.fail(
                "{name} does not have {item_name}".format(
                    name=self.character.name.capitalize(), item_name=self.item.name
                )
            )
            return False
        if not self.item.get_property(Property.IS_LIT):
            self.parser.fail("It isn't lit.")
            return False
        return True

    def apply_effects(self):
        """
        Effects:
        * Changes the state to not lit
        """
        self.item.set_property(Property.IS_LIT, False)
        description = "The {item} goes dark.".format(item=self.item.name)
        self.parser.ok(description)
