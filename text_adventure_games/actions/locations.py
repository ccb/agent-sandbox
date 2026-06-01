from . import base

# from . import preconditions as P

# from ..things import Character, Item  # , Location


class Go(base.Action):
    ACTION_NAME = "go"
    ACTION_DESCRIPTION = "Go in a direction"
    ACTION_ALIASES = [
        "north",
        "n",
        "south",
        "s",
        "east",
        "e",
        "west",
        "w",
        "out",
        "in",
        "up",
        "down",
    ]

    def __init__(
        self,
        game,
        command: str,
        # location: Location, direction: str
    ):
        super().__init__(game)
        self.character = self.parser.get_character(command, hint="traveler")
        self.location = self.character.location
        self.direction = self.parser.get_direction(command, self.location)
        self.command = command

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The character must be at the location.
        * The location must have an exit in the specified direction
        * The direction must not be blocked
        """
        if not self.location.here(self.character):
            message = "{name} is not at {location_name}".format(
                name=self.character.capitalize(),
                location_name=self.location.name.capitalize(),
            )
            self.parser.fail(message)
            return False

        if not self.location.get_connection(self.direction):
            d = "{location_name} does not have an exit '{direction}'"
            description = d.format(
                location_name=self.location.name.capitalize(), direction=self.direction
            )
            self.parser.fail(description)
            return False

        if self.location.is_blocked(self.direction):
            description = self.location.get_block_description(self.direction)
            if not description:
                d = "{location_name} is blocked towards {direction}"
                description = d.format(
                    location_name=self.location.name.capitalize(),
                    direction=self.direction,
                )
            self.parser.fail(description)
            return False

        return True

    def apply_effects(self):
        """
        Moves a character. (Assumes that the preconditions are met.)
        """
        is_main_player = self.character == self.game.player

        # move from
        from_loc = self.location
        if self.character.name in from_loc.characters:
            from_loc.remove_character(self.character)

        # move to
        to_loc = self.location.connections[self.direction]
        to_loc.add_character(self.character)
        if is_main_player:
            self.has_been_visited = True

        # CCB - we don't need to describe this action
        description = "{character_name} moved to {place}".format(
            character_name=self.character.name, place=to_loc.name
        )
        if self.location.travel_descriptions[self.direction]:
            description += " " + self.location.travel_descriptions[self.direction]
        self.parser.ok(description)

        # Some locations finish game
        if to_loc.get_property("game_over") and is_main_player:
            self.game.game_over = True
            self.game.game_over_description = to_loc.description
            self.parser.ok(to_loc.description)
        else:
            action = base.Describe(self.game, command=self.command)
            action()
