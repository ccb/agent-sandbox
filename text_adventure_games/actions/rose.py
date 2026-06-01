import random

from . import base
from ..things import Item


class Pick_Rose(base.Action):
    ACTION_NAME = "pick rose"
    ACTION_DESCRIPTION = "Pick a rose from a rosebush"

    def __init__(self, game, command: str):
        super().__init__(game)
        self.character = self.parser.get_character(command, hint="picker")
        self.rosebush = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="rosebush"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * There must be a rosebush.
        * The rose bush has to have a rose.
        * The character must be at the location of the rosebush.
        """
        if not self.was_matched(self.rosebush, "There's no rosebush here."):
            return False
        if not self.rosebush.get_property("has_rose"):
            description = "The rosebush is bare."
            self.game.parser.fail(description)
            return False
        if not self.rosebush.location.here(self.character):
            return False
        return True

    def apply_effects(self):
        """
        Effects:
        * Creates a new item for the rose
        * Adds the rose to the character's inventory
        * Sets the 'has_rose' property of the rosebush to False.
        """
        rose = Item(
            "rose",
            "a red rose",
            "IT SMELLS GOOD.",
        )
        rose.add_command_hint("smell rose")
        self.rosebush.set_property("has_rose", False)
        self.character.add_to_inventory(rose)
        d = "{character_name} picked the lone rose from the rosebush"
        description = d.format(character_name=self.character.name)
        self.parser.ok(description)
        return rose


# Special Action: Smell Rose


class Smell_Rose(base.Action):
    ACTION_NAME = "smell rose"
    ACTION_DESCRIPTION = "Smell the rose"

    def __init__(self, game, command: str):
        super().__init__(game)
        self.character = self.parser.get_character(command, hint="smeller")
        self.rose = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="rose"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * There must be a rose in the player's inventory.
        """
        if not self.was_matched(self.rose, "I don't see a rose."):
            return False
        if not self.is_in_inventory(self.character, self.rose):
            return False
        return True

    def apply_effects(self):
        """
        For fun, each time the character smells the rose, I'm going to give it
        a different random smell.
        """
        rose_smells = [
            "sweetly intoxicating",
            "delicately fragrant",
            "richly floral",
            "subtly perfumed",
            "freshly aromatic",
            "gently alluring",
            "deeply romantic",
            "lightly scented",
            "heady and potent",
            "warmly inviting",
            "softly enchanting",
            "luxuriously opulent",
            "tenderly soothing",
            "earthy with a hint of sweetness",
            "vividly refreshing",
            "seductively spicy",
            "velvety and smooth",
            "brightly invigorating",
            "elegantly refined",
            "sumptuously heavy",
            "whisper-soft and delicate",
            "bold and commanding",
            "dreamily nostalgic",
            "exotically rich",
            "sensuously captivating",
            "dew-kissed and fresh",
            "radiantly vibrant",
            "comfortingly familiar",
            "playfully fruity",
            "serenely peaceful",
            "misty and mysterious",
            "lusciously full-bodied",
            "daintily sweet",
            "intensely passionate",
            "crisp and clean",
            "majestically royal",
            "sunny and cheerful",
            "tranquilly serene",
            "festively joyful",
            "timelessly classic",
        ]
        self.rose.set_property("scent", random.choice(rose_smells))

        d = "{character_name} smells the rose. It smells {scent}."
        description = d.format(
            character_name=self.character.name.capitalize(),
            scent=self.rose.get_property("scent"),
        )
        self.parser.ok(description)

        self.character.set_property("emotional_state", "happy")
        description = "{character_name} is happy.".format(
            character_name=self.character.name.capitalize()
        )
        self.parser.ok(description)
