"""Vehicles / mounts: board and ride a horse, a motorcycle, a boat.

A vehicle is an Item flagged ``is_vehicle`` (``Item.make_vehicle``). The player
boards it with MOUNT (``ride``/``mount``/``board``/``get on``) and leaves it with
DISMOUNT (``dismount``/``get off``). While riding (``character.riding`` is set),
the engine brings the vehicle along whenever the rider moves (Game.relocate), and
a :class:`~text_adventure_games.blocks.RequiresVehicle` block makes an exit
passable only when mounted ("it's too far on foot").

A vehicle that must be activated first -- a key for a motorcycle, an apple/brush
for a skittish horse -- starts ``vehicle_ready=False``; a game-specific verb flips
it true, and MOUNT refuses until then (with an optional ``mount_refusal_message``).
"""

from . import base
from ..enums import ActionName


def _vehicle_here(parser, character, command):
    """Match a vehicle in the character's location from the command; if none is
    named and exactly one vehicle is present, use it."""
    here = {
        name: it for name, it in character.location.items.items() if it.is_vehicle()
    }
    if not here:
        return None
    matched = parser.match_item(command, here, hint="vehicle")
    if matched is not None:
        return matched
    return list(here.values())[0] if len(here) == 1 else None


class Mount(base.Action):
    ACTION_NAME = ActionName.MOUNT
    ACTION_DESCRIPTION = "Get on / board a vehicle or mount"
    ACTION_ALIASES = ["ride", "get on", "board", "hop on", "climb aboard"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="rider")
        self.vehicle = _vehicle_here(self.parser, self.character, command)

    def check_preconditions(self) -> bool:
        if self.vehicle is None:
            self.parser.fail("There's nothing here to ride.")
            return False
        if self.character.riding is self.vehicle:
            self.parser.fail(f"You're already aboard the {self.vehicle.name}.")
            return False
        if not self.vehicle.vehicle_ready():
            self.parser.fail(
                self.vehicle.get_property("mount_refusal_message")
                or f"You can't ride the {self.vehicle.name} yet."
            )
            return False
        return True

    def apply_effects(self):
        self.character.riding = self.vehicle
        self.parser.ok(
            f"{self.character.name.capitalize()} climbs aboard the {self.vehicle.name}."
        )


class Dismount(base.Action):
    ACTION_NAME = ActionName.DISMOUNT
    ACTION_DESCRIPTION = "Get off / dismount the vehicle you're riding"
    ACTION_ALIASES = ["dismount", "get off"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="rider")

    def check_preconditions(self) -> bool:
        if self.character.riding is None:
            self.parser.fail("You're not riding anything.")
            return False
        return True

    def apply_effects(self):
        vehicle = self.character.riding
        self.character.riding = None
        self.parser.ok(
            f"{self.character.name.capitalize()} gets down off the {vehicle.name}."
        )
