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
            self.parser.fail(f"You can't wear the {self.item.name}.")
            return False
        # Fit gate: an item may only fit certain wearers. If it declares a
        # ``fit_property`` (the name of a matching dimension, e.g. "shoe_size"),
        # the wearer must share the item's value for that property. Unset on the
        # wearer reads as False, so it won't match a real required value. Items
        # may set ``misfit_message`` to customize the refusal.
        fit_property = self.item.get_property("fit_property")
        if fit_property and self.character.get_property(
            fit_property
        ) != self.item.get_property(fit_property):
            self.parser.fail(
                self.item.get_property("misfit_message")
                or f"The {self.item.name} won't fit."
            )
            return False
        if self.character.is_worn(self.item):
            self.parser.fail(
                f"{self.character.name.capitalize()} is already wearing the {self.item.name}."
            )
            return False
        # Wear slot: an item may declare a ``wear_slot`` (a body location, e.g.
        # "feet"/"head"/"body"). Only one item occupies a slot unless the item
        # being put on declares ``wear_over`` (it layers atop -- a cloak over a
        # gown). Otherwise the wearer must take off the occupant first.
        slot = self.item.get_property("wear_slot")
        if slot and not self.item.get_property("wear_over"):
            for worn in self.character.worn.values():
                if worn is not self.item and worn.get_property("wear_slot") == slot:
                    self.parser.fail(f"You'll have to take off the {worn.name} first.")
                    return False
        if not self.is_in_inventory(self.character, self.item):
            return False
        return True

    def apply_effects(self):
        self.character.wear(self.item)
        # Donning a carded wearable draws its card (CCB): putting a thing ON
        # is as deliberate as examining it, so it always plays -- take and
        # ambush cues stay once-per-game. Player wearers only.
        if self.character is self.game.player:
            fig = self.item.get_property("figure")
            self.game.show_figure(fig(self.game) if callable(fig) else fig, force=True)
        # Items may carry their own flavor for being put on (``wear_text``).
        self.parser.ok(
            self.item.get_property("wear_text")
            or f"{self.character.name.capitalize()} {base.conjugate(self.character, 'put', 'puts')} on the {self.item.name}."
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
            f"{self.character.name.capitalize()} {base.conjugate(self.character, 'take', 'takes')} off the {self.item.name}."
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
            self.parser.fail(f"You can't wield the {self.item.name}.")
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
            f"{self.character.name.capitalize()} {base.conjugate(self.character, 'wield', 'wields')} the {self.item.name}."
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
            f"{self.character.name.capitalize()} {base.conjugate(self.character, 'stow', 'stows')} the {self.item.name}."
        )
