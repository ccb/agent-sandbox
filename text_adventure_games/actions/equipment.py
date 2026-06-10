from . import base
from ..enums import ActionName, Property


class Wear(base.Action):
    ACTION_NAME = ActionName.WEAR
    ACTION_DESCRIPTION = "Put on a wearable item from your inventory"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wearer")
        scope = {**self.character.inventory, **self.character.worn}
        self.item = self.parser.match_item(command, scope, hint="thing to wear")

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be matched
        * The item must be wearable
        * The item must be in the character's inventory (not already worn)
        """
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not self.item.get_property(Property.WEARABLE):
            self.parser.fail(f"{self.item.name.capitalize()} is not wearable.")
            return False
        if self.character.is_worn(self.item):
            self.parser.fail(
                f"{self.character.name.capitalize()} is already wearing the {self.item.name}."
            )
            return False
        if not self.is_in_inventory(self.character, self.item):
            return False
        return True

    def apply_effects(self):
        self.character.wear(self.item)
        self.parser.ok(
            f"{self.character.name.capitalize()} puts on the {self.item.name}."
        )


class Take_Off(base.Action):
    ACTION_NAME = ActionName.TAKE_OFF
    ACTION_DESCRIPTION = "Take off a worn item"
    ACTION_ALIASES = ["remove"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wearer")
        self.item = self.parser.match_item(
            command, self.character.worn, hint="thing to take off"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be matched
        * The item must currently be worn by the character
        """
        if not self.was_matched(
            self.item, f"{self.character.name.capitalize()} isn't wearing that."
        ):
            return False
        return True

    def apply_effects(self):
        self.character.take_off(self.item)
        self.parser.ok(
            f"{self.character.name.capitalize()} takes off the {self.item.name}."
        )


class Wield(base.Action):
    ACTION_NAME = ActionName.WIELD
    ACTION_DESCRIPTION = "Wield a wieldable item from your inventory"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wielder")
        scope = {**self.character.inventory, **self.character.wielded}
        self.item = self.parser.match_item(command, scope, hint="thing to wield")

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be matched
        * The item must be wieldable
        * The item must be in the character's inventory (not already wielded)
        """
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not self.item.get_property(Property.WIELDABLE):
            self.parser.fail(f"{self.item.name.capitalize()} is not wieldable.")
            return False
        if self.character.is_wielded(self.item):
            self.parser.fail(
                f"{self.character.name.capitalize()} is already wielding the {self.item.name}."
            )
            return False
        if not self.is_in_inventory(self.character, self.item):
            return False
        return True

    def apply_effects(self):
        self.character.wield(self.item)
        self.parser.ok(
            f"{self.character.name.capitalize()} wields the {self.item.name}."
        )


class Unwield(base.Action):
    ACTION_NAME = ActionName.UNWIELD
    ACTION_DESCRIPTION = "Stow a wielded item back in your inventory"
    ACTION_ALIASES = ["stow", "unequip"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wielder")
        self.item = self.parser.match_item(
            command, self.character.wielded, hint="thing to stow"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be matched
        * The item must currently be wielded by the character
        """
        if not self.was_matched(
            self.item, f"{self.character.name.capitalize()} isn't wielding that."
        ):
            return False
        return True

    def apply_effects(self):
        self.character.unwield(self.item)
        self.parser.ok(
            f"{self.character.name.capitalize()} stows the {self.item.name}."
        )
