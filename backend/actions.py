"""Custom engine actions for the Smallville port.

Smallville is a map you travel across, not a compass maze, and agents spend most
of their time *doing an activity* in place. Two small ``Action`` subclasses model
that, each going through the engine's precondition gate like any built-in action:

* :class:`Travel` -- move to a named location anywhere in town (the spatial,
  tile-by-tile walk is handled afterwards by the exporter via the pathfinder).
* :class:`Act` -- perform an activity at the current location, recorded on the
  character so the exporter can render it as the on-screen action label.
"""

from text_adventure_games.actions import base


class Travel(base.Action):
    """Move the acting character to a named location (matched from the command).

    e.g. ``"travel to Hobbs Cafe"``. The logical move happens here; turning it
    into a believable on-screen walk is the exporter's job (it reads the new
    location's tile address and asks the pathfinder for a route)."""

    ACTION_NAME = "travel"
    ACTION_DESCRIPTION = "Travel to a named location in town"

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command, hint="traveler")
        self.destination = self._match_destination(command)

    def _match_destination(self, command: str):
        """Longest location name appearing in the command (case-insensitive)."""
        cmd = command.lower()
        best = None
        for name, loc in self.game.locations.items(): #why items here? why self.location.items()? why do you care there's a stick on garden path?
            if name.lower() in cmd and (best is None or len(name) > len(best.name)): #this second line I don't get - if name is longer than best then what? why care?
                best = loc
        return best

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No one is traveling."):
            return False
        if not self.was_matched(
            self.destination, "I don't know how to get to that place."
        ):
            return False
        return True

    def apply_effects(self):
        from_loc = self.character.location
        if from_loc is not None and self.character.name in from_loc.characters:
            from_loc.remove_character(self.character)
        self.destination.add_character(self.character)
        return self.parser.ok(
            f"{self.character.name} sets off for {self.destination.name}."
        )


class Act(base.Action):
    """Perform an activity in place, e.g. ``"perform tending the cafe counter"``.

    The activity text (everything after the verb) is stored on the character as
    the ``activity`` property; the exporter renders it as the action label."""

    ACTION_NAME = "perform"
    ACTION_DESCRIPTION = "Perform an activity at the current location"

    def __init__(self, game, command: str, actor=None): #still not 100% sure why this is?
        super().__init__(game, actor=actor)
        self.command = command
        self.character = self.acting_character(command, hint="actor")
        parts = command.split(" ", 1)
        self.activity = parts[1].strip() if len(parts) > 1 else ""

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No one is acting."):
            return False
        if self.character.location is None:
            self.parser.fail("There is nowhere to do that.")
            return False
        if not self.activity:
            self.parser.fail("There is no activity to perform.")
            return False
        return True

    def apply_effects(self):
        self.character.set_property("activity", self.activity)
        return self.parser.ok(f"{self.character.name} is {self.activity}.")
