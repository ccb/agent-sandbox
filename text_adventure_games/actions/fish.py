from . import base
from ..things import Item
from ..enums import ActionName, Property


class Catch_Fish(base.Action):
    ACTION_NAME = ActionName.CATCH_FISH
    ACTION_DESCRIPTION = "Catch fish with a pole"
    ACTION_ALIASES = ["go fishing"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command.lower()
        self.character = self.acting_character(command, hint="fisherman")
        self.pond = self.character.location
        self.pole = self.parser.match_item(
            command,
            self.parser.get_items_in_scope(self.character),
            hint="fishing pole",
        )
        # Track whether the player explicitly asked to use a pole.  This helps
        # us distinguish between ``catch fish`` and ``catch fish with pole``.
        self.use_pole = "pole" in self.command

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * There must be a pond
        * The character must be at the pond
        * The character must have a fishing pole in their inventory
        """
        if not self.was_matched(self.pond, "There's no pond here."):
            return False
        if not self.pond.get_property(Property.HAS_FISH):
            self.parser.fail("The pond has no fish.")
            return False
        no_pole_msg = f"{self.character.name} does not have a fishing pole."

        hands_msg = "".join(
            [
                f"{self.character.name} reaches into the pond and tries to ",
                "catch a fish with their hands, but the fish are too fast.",
            ]
        )

        if not self.use_pole:
            self.parser.fail(hands_msg)
            return False

        if not self.was_matched(self.pole, no_pole_msg):
            return False

        if not self.is_in_inventory(self.character, self.pole, describe_error=False):
            self.parser.fail(no_pole_msg)
            return False

        return True

    def apply_effects(self):
        """
        Effects:
        * Creates a new item for the fish
        * Adds the fish to the character's inventory
        * Sets the 'has_fish' property of the pond to False.
        """

        fish = Item("fish", "a dead fish", "IT SMELLS TERRIBLE.")
        fish.add_command_hint("eat fish")
        fish.set_property(Property.EDIBLE, True)
        fish.set_property(
            Property.TASTE, "disgusting! It's raw! And definitely not sashimi-grade!"
        )
        self.pond.set_property(Property.HAS_FISH, False)
        self.character.add_to_inventory(fish)

        d = "".join(
            [
                f"{self.character.name} dips their hook into the pond and ",
                "catches a fish",
            ]
        )
        description = d.format(character_name=self.character.name)
        self.parser.ok(description)
