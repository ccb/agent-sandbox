"""Switch fixed devices on and off -- a stove, a sink, a generator (#464).

:class:`Activate` / :class:`Deactivate` are the no-flame cousins of
:class:`~text_adventure_games.actions.consume.Light` and
:class:`~text_adventure_games.actions.consume.Douse`: where Light/Douse set
fire to something FLAMMABLE you are *holding*, these toggle the power state
(``is_on``) of a fixture marked ``is_device``. A device is usually bolted to
the room, so it only needs to be in the actor's scope, not in their hands.

Lifted from the Penn backend's boil-water verbs (#300), where switching on the
stove is the first step of the drink -> sicken -> boil -> recover arc. The
effect is deliberately just the ``is_on`` flag -- switching a stove on heats
nothing by itself; a game gives the flag meaning through recipes, triggers, or
its own actions.
"""

from . import base
from ..enums import ActionName, Property


class Activate(base.Action):
    ACTION_NAME = ActionName.ACTIVATE
    ACTION_DESCRIPTION = "Switch on a device (a stove, a sink)"
    ACTION_ALIASES = ["switch on"]
    # Offered to an agent only where a device is in scope (issue #612); the
    # gate below reads the same declaration as its place-check.
    REQUIRED_AFFORDANCES = (Property.IS_DEVICE,)

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="operator")
        # Scope, not inventory: a device is a room fixture, so you can switch
        # it on without picking it up.
        self.item = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="device"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * A device must be in scope (the #612 place-check)
        * There must be a matched item
        * The item must be a device
        * The device must currently be off
        """
        if not self.has_affordance_in_scope(
            self.character, error_message="There is no device here to switch on."
        ):
            return False
        if not self.was_matched(
            self.item, error_message="I don't know what you want to switch on."
        ):
            return False
        if not self.item.get_property(Property.IS_DEVICE):
            self.parser.fail(f"The {self.item.name} isn't something you can switch on.")
            return False
        if self.item.get_property(Property.IS_ON):
            self.parser.fail(f"The {self.item.name} is already on.")
            return False
        return True

    def apply_effects(self):
        """
        Effects:
        * Changes the state to on
        """
        self.item.set_property(Property.IS_ON, True)
        return self.parser.ok(f"The {self.item.name} hums to life.")


class Deactivate(base.Action):
    """Switch off a device -- the inverse of :class:`Activate`."""

    ACTION_NAME = ActionName.DEACTIVATE
    ACTION_DESCRIPTION = "Switch off a device (a stove, a sink)"
    ACTION_ALIASES = ["switch off"]
    REQUIRED_AFFORDANCES = (Property.IS_DEVICE,)

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="operator")
        self.item = self.parser.match_item(
            command, self.parser.get_items_in_scope(self.character), hint="device"
        )

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * A device must be in scope (the #612 place-check)
        * There must be a matched item
        * The item must be a device
        * The device must currently be on
        """
        if not self.has_affordance_in_scope(
            self.character, error_message="There is no device here to switch off."
        ):
            return False
        if not self.was_matched(
            self.item, error_message="I don't know what you want to switch off."
        ):
            return False
        if not self.item.get_property(Property.IS_DEVICE):
            self.parser.fail(
                f"The {self.item.name} isn't something you can switch off."
            )
            return False
        if not self.item.get_property(Property.IS_ON):
            self.parser.fail(f"The {self.item.name} is already off.")
            return False
        return True

    def apply_effects(self):
        """
        Effects:
        * Changes the state to off
        """
        self.item.set_property(Property.IS_ON, False)
        return self.parser.ok(f"The {self.item.name} winds down and goes quiet.")
