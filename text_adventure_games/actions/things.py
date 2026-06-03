from . import base
from .consume import Drink, Eat
from .rose import Smell_Rose


class Get(base.Action):
    ACTION_NAME = "get"
    ACTION_DESCRIPTION = "Get something and add it to the inventory"
    ACTION_ALIASES = ["take"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to get something")
        self.location = self.character.location
        self.item = self.parser.match_item(
            command, self.location.items, hint="thing to get"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be matched.
        * The character must be at the location
        * The item must be at the location
        * The item must be gettable
        """
        if not self.was_matched(self.item, "I don't see it."):
            message = "I don't see it."
            self.parser.fail(message)
            return False
        if not self.at(self.character, self.location):
            return False
        if not self.at(self.item, self.location):
            return False
        if not self.has_property(
            self.item,
            "gettable",
            error_message="{name} is not gettable.".format(
                name=self.item.name.capitalize()
            ),
        ):
            return False
        return True

    def apply_effects(self):
        """
        Get's an item from the location and adds it to the character's
        inventory, assuming preconditions are met.
        """
        self.location.remove_item(self.item)
        self.character.add_to_inventory(self.item)
        description = "{character_name} got the {item_name}.".format(
            character_name=self.character.name, item_name=self.item.name
        )
        self.parser.ok(description)


class Drop(base.Action):
    ACTION_NAME = "drop"
    ACTION_DESCRIPTION = "Drop something from the character's inventory"
    ACTION_ALIASES = ["toss", "get rid of"]

    def __init__(
        self,
        game,
        command: str,
        actor=None,
    ):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="wants to drop something")
        self.location = self.character.location
        self.item = self.parser.match_item(
            command, self.character.inventory, hint="thing being dropped"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be in the character's inventory
        """
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not self.is_in_inventory(self.character, self.item):
            return False
        return True

    def apply_effects(self):
        """
        Drop removes an item from character's inventory and adds it to the
        current location, assuming preconditions are met
        """
        self.character.remove_from_inventory(self.item)
        self.item.location = self.location
        self.location.add_item(self.item)
        d = "{character_name} dropped the {item_name} in the {location}."
        description = d.format(
            character_name=self.character.name.capitalize(),
            item_name=self.item.name,
            location=self.location.name,
        )
        self.parser.ok(description)


class Inventory(base.Action):
    ACTION_NAME = "inventory"
    ACTION_DESCRIPTION = "Check the character's inventory"
    ACTION_ALIASES = ["i"]

    def __init__(
        self,
        game,
        command: str,
        actor=None,
    ):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No character was matched."):
            return False
        return True

    def apply_effects(self):
        if len(self.character.inventory) == 0:
            description = f"{self.character.name}'s inventory is empty."
            self.parser.ok(description)
        else:
            description = f"{self.character.name}'s inventory contains:\n"
            for item_name in self.character.inventory:
                item = self.character.inventory[item_name]
                description += "* {item}\n".format(item=item.description)
            self.parser.ok(description)


class Examine(base.Action):
    ACTION_NAME = "examine"
    ACTION_DESCRIPTION = "Examine an item"
    ACTION_ALIASES = ["look at", "x"]

    def __init__(
        self,
        game,
        command: str,
        actor=None,
    ):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="looker")
        self.matched_item = self.parser.match_item(
            command,
            self.parser.get_items_in_scope(self.character),
            hint="thing being looked at",
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No character was matched."):
            return False
        return True

    def apply_effects(self):
        """The player wants to examine an item"""
        if self.matched_item:
            if self.matched_item.examine_text:
                self.parser.ok(self.matched_item.examine_text)
            else:
                self.parser.ok(self.matched_item.description)
        else:
            self.parser.ok("You don't see anything special.")


class Give(base.Action):
    ACTION_NAME = "give"
    ACTION_DESCRIPTION = "Give something to someone"
    ACTION_ALIASES = ["hand"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        give_words = ["give", "hand"]
        self.giver = self.acting_character(
            command, hint="giver", split_words=give_words, position="before"
        )
        self.recipient = self.parser.get_character(
            command,
            hint="recipient",
            split_words=give_words,
            position="after",
            exclude=self.giver,
        )
        self.item = self.parser.match_item(
            command, self.giver.inventory, hint="item being given"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The item must be in the giver's inventory
        * The character must be at the same location as the recipient
        """
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not self.is_in_inventory(self.giver, self.item):
            return False
        if not self.at(self.recipient, self.giver.location):
            return False
        return True

    def apply_effects(self):
        """The giver hands the item to the recipient.

        If the recipient is hungry and the item is food, they will eat it.
        If the recipient is thirsty and the item is drink, they will drink it.
        """
        self.giver.remove_from_inventory(self.item)
        self.recipient.add_to_inventory(self.item)
        description = "{giver} gave the {item_name} to {recipient}".format(
            giver=self.giver.name.capitalize(),
            item_name=self.item.name,
            recipient=self.recipient.name.capitalize(),
        )
        self.parser.ok(description)

        if self.recipient.get_property("is_hungry") and self.item.get_property(
            "is_food"
        ):
            command = "{name} eat {food}".format(
                name=self.recipient.name, food=self.item.name
            )
            eat = Eat(self.game, command)
            eat()

        if self.recipient.get_property("is_thirsty") and self.item.get_property(
            "is_drink"
        ):
            command = "{name} drink {drink}".format(
                name=self.recipient.name, drink=self.item.name
            )
            drink = Drink(self.game, command)
            drink()

        if self.item.get_property("scent"):
            command = "{name} smell {thing}".format(
                name=self.recipient.name, thing=self.item.name
            )
            smell = Smell_Rose(self.game, command)
            smell()


class Unlock_Door(base.Action):
    ACTION_NAME = "unlock door"
    ACTION_DESCRIPTION = "Unlock a door"

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command)
        self.key = self.parser.match_item(
            "key", self.parser.get_items_in_scope(self.character), hint="key"
        )
        self.door = self.parser.match_item(
            "door", self.parser.get_items_in_scope(self.character), hint="door"
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.door, "There's no door here."):
            return False
        if not self.was_matched(self.key, "There's no key here."):
            return False
        if self.has_property(
            self.door, "is_locked", error_message="The door is not locked."
        ):
            return False
        return True

    def apply_effects(self):
        self.door.set_property("is_locked", False)
        self.parser.ok("Door is unlocked")
