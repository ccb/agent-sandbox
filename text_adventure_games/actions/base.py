from __future__ import annotations
from ..things import Thing, Character, Item, Location
from ..enums import ActionName
import re


class Action:
    """
    In the game, rather than allowing players to do anything, we have a
    specific set of Actions that can do.  The Action class that checks
    preconditions (the set of conditions that must be true in order for the
    action to have), and applies the effects of the action by updatin the state
    of the world.

    Different actions have different arguments, so we subclass Action to create
    new actions.

    Every action must implement two functions:
      * check_preconditions()
      * apply_effects()
    """

    ACTION_NAME: str | None = None
    ACTION_DESCRIPTION: str = None
    ACTION_ALIASES: list[str] = None

    def __init__(self, game, actor=None):
        self.game = game
        self.parser = game.parser
        self.actor = actor

    def acting_character(self, command, **kwargs):
        """Resolve who performs this action: the explicit actor if one was
        supplied, else the legacy command-string scan (player default)."""
        if self.actor is not None:
            return self.actor
        return self.parser.get_character(command, **kwargs)

    def check_preconditions(self) -> bool:
        """
        Called before apply_effects to ensure the state for applying the
        action is valid
        """
        return False

    def apply_effects(self):
        """
        This method applies the action and changes the state of the game.
        """
        return self.parser.ok("no effect")

    def __call__(self):
        self._preconditions_passed = False
        if self.check_preconditions():
            self._preconditions_passed = True
            return self.apply_effects()

    @classmethod
    def action_name(cls):
        """
        This method plays a crucial role in how command strings are routed to
        actual action names. This method provides the key used in the game's
        dict of actions.
        """
        if cls.ACTION_NAME and isinstance(cls.ACTION_NAME, str):
            return cls.ACTION_NAME.lower()
        cls_name = cls.__name__
        cls_name = cls_name.replace("_", "")
        words = re.sub(r"([A-Z])", r" \1", cls_name).split()
        action_name = " ".join([w.lower() for w in words])
        return action_name

    ###
    # Preconditions - these functions are common preconditions.
    # They handle the error messages sent to the parser.
    ###

    def at(self, thing: Thing, location: Location, describe_error: bool = True) -> bool:
        """
        Checks if the thing is at the location.
        """
        # The character must be at the location
        if not location.here(thing):
            message = "{name} is not at {loc}".format(
                name=thing.name.capitalize(), loc=location.name
            )
            if describe_error:
                self.parser.fail(message)
            return False
        else:
            return True

    def has_connection(
        self, location: Location, direction: str, describe_error: bool = True
    ) -> bool:
        """
        Checks if the location has an exit in this direction.
        """
        if direction not in location.connections:  # JD logical change
            m = "{location_name} does not have an exit '{direction}'"
            message = m.format(
                location_name=location.name.capitalize(), direction=direction
            )
            if describe_error:
                self.parser.fail(message)
            return False
        else:
            return True

    def is_blocked(
        self, location: Location, direction: str, describe_error: bool = True
    ) -> bool:
        """
        Checks if the location blocked in this direction.
        """
        if location.is_blocked(direction):
            message = location.get_block_description(direction)
            if describe_error:
                self.parser.fail(message)
            return True
        else:
            return False

    def property_equals(
        self,
        thing: Thing,
        property_name: str,
        property_value: str,
        error_message: str = None,
        display_message_upon: bool = False,
        describe_error: bool = True,
    ) -> bool:
        """
        Checks whether the thing has the specified property.
        """
        if thing.get_property(property_name) != property_value:
            if display_message_upon is False:
                if not error_message:
                    error_message = "{name}'s {property_name} is not {value}".format(
                        name=thing.name.capitalize(),
                        property_name=property_name,
                        value=property_value,
                    )
                if describe_error:
                    self.parser.fail(error_message)
            return False
        else:
            if display_message_upon is True:
                if not error_message:
                    error_message = "{name}'s {property_name} is {value}".format(
                        name=thing.name.capitalize(),
                        property_name=property_name,
                        value=property_value,
                    )
                if describe_error:
                    self.parser.fail(error_message)
            return True

    def has_property(
        self,
        thing: Thing,
        property_name: str,
        error_message: str = None,
        display_message_upon: bool = False,
        describe_error: bool = True,
    ) -> bool:
        """
        Checks whether the thing has the specified property.
        """
        if not thing.get_property(property_name):
            if display_message_upon is False:
                if not error_message:
                    error_message = "{name} {property_name} is False".format(
                        name=thing.name.capitalize(), property_name=property_name
                    )
                if describe_error:
                    self.parser.fail(error_message)
            return False
        else:
            if display_message_upon is True:
                if not error_message:
                    error_message = "{name} {property_name} is True".format(
                        name=thing.name.capitalize(), property_name=property_name
                    )
                if describe_error:
                    self.parser.fail(error_message)
            return True

    def loc_has_item(
        self, location: Location, item: Item, describe_error: bool = True
    ) -> bool:
        """
        Checks to see if the location has the item.  Similar funcality to at, but
        checks for items that have multiple locations like doors.
        """
        if item.name in location.items:
            return True
        else:
            message = "{loc} does not have {item}".format(
                loc=location.name, item=item.name
            )
            if describe_error:
                self.parser.fail(message)
            return False

    def is_in_inventory(
        self, character: Character, item: Item, describe_error: bool = True
    ) -> bool:
        """
        Checks if the character has this item in their inventory.
        """
        if not character.is_in_inventory(item):
            message = "{name} does not have {item_name}".format(
                name=character.name.capitalize(), item_name=item.name
            )
            if describe_error:
                self.parser.fail(message)
            return False
        else:
            return True

    def was_matched(
        self,
        thing: Thing,
        error_message: str = None,
        describe_error: bool = True,
    ) -> bool:
        """
        Checks to see if the thing was matched by the self.parser.
        """
        if thing is None:
            if not error_message:
                error_message = "Something was not matched by the self.parser."
            if describe_error:
                self.parser.fail(error_message)
            return False
        else:
            return True


class ActionSequence(Action):
    """
    A container action that handles multiple commands entered as a single
    string of comma separated actions.

    Example: get pole, go out, south, catch fish with pole
    """

    ACTION_NAME = ActionName.SEQUENCE
    ACTION_DESCRIPTION = "Complete a sequence of actions specified in a list"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        responses = []
        for cmd in self.command.split(","):
            cmd = cmd.strip()
            responses.append(self.parser.parse_command(cmd, actor=self.actor))
        return responses


class Quit(Action):
    ACTION_NAME = ActionName.QUIT
    ACTION_DESCRIPTION = "Quit the game"
    ACTION_ALIASES = ["q"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        if not self.game.game_over:
            self.game.game_over = True
            if not self.game.game_over_description:
                self.game.game_over_description = "The End"
            return self.parser.ok(self.game.game_over_description)
        return self.parser.fail("Game already ended.")


class Wait(Action):
    ACTION_NAME = ActionName.WAIT
    ACTION_DESCRIPTION = "Wait and let time pass"
    ACTION_ALIASES = ["z"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        self.parser.ok("Time passes.")


class Describe(Action):
    ACTION_NAME = ActionName.DESCRIBE
    ACTION_DESCRIPTION = "Describe the current location"
    ACTION_ALIASES = ["look", "l"]

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        self.parser.ok(self.game.describe())
