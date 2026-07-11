from . import base
from ..enums import ActionName, Direction, Property

# from . import preconditions as P

# from ..things import Character, Item  # , Location


class Go(base.Action):
    ACTION_NAME = ActionName.GO
    ACTION_DESCRIPTION = "Go in a direction"
    # Aliases mix canonical Direction members with the one-letter shortcuts
    # the parser also accepts; Direction members are strings, so the list
    # type stays homogeneous.
    ACTION_ALIASES = [
        Direction.NORTH,
        "n",
        Direction.SOUTH,
        "s",
        Direction.EAST,
        "e",
        Direction.WEST,
        "w",
        Direction.OUT,
        Direction.IN,
        Direction.UP,
        Direction.DOWN,
    ]

    def __init__(
        self,
        game,
        command: str,
        # location: Location, direction: str
        actor=None,
    ):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command, hint="traveler")
        self.location = self.character.location
        self.direction = self.parser.get_direction(command, self.location)
        self.command = command

    def claimed_resource(self):
        """The destination tile: two characters heading to the same place
        contend for it (#42; matters when a tile is single-occupancy)."""
        if self.direction is None:
            return None
        return self.location.get_connection(self.direction)

    def check_preconditions(self) -> bool:
        """
        Preconditions:
        * The character must be at the location.
        * The location must have an exit in the specified direction
        * The direction must not be blocked
        """
        if self.direction is None:
            # A malformed move ("go" with no/unknown direction) -- don't render
            # "does not have an exit 'None'".
            self.parser.fail("Go where?")
            return False

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

        # Vaarn item slots (slots.py): an encumbered character cannot use exits
        # the game marks as climbs (location.set_property("climb_exits", {...})).
        climbs = self.location.get_property("climb_exits")
        if climbs and self.direction in climbs and self.character.is_encumbered():
            self.parser.fail(
                "Loaded as you are, the climb is out of the question. Something "
                "must be left behind."
            )
            return False

        return True

    def apply_effects(self):
        """
        Moves a character. (Assumes that the preconditions are met.)
        """
        is_main_player = self.character == self.game.player

        # Move via the engine relocate chokepoint (location bookkeeping). The
        # mover's followers are dragged afterward, so the "moved to" line and
        # room description come first, then "X follows you."
        to_loc = self.location.connections[self.direction]
        self.game.relocate(self.character, to_loc)
        if is_main_player:
            # On the LOCATION (a long-lived bug set it on this Action object,
            # so the flag never stuck and everything gated on it -- visit-gated
            # hints, the approach card -- stayed dark forever).
            to_loc.has_been_visited = True

        # An encumbered mover clatters (slots.py): their movement is a real
        # sound, heard here and one room out -- listeners, reactions, and any
        # noise-keyed hazard treat it like any other noise. Overload yourself
        # and you cannot creep.
        if self.character.is_encumbered():
            self.game.emit_sound(
                to_loc,
                1,
                f"the clatter of {self.character.name}'s overloaded pack",
            )

        # The arrival line. "X moved to PLACE" by default; when the mover is
        # riding a vehicle, the verb comes from the vehicle ("rides" by default,
        # but e.g. a boat can set ride_verb="rows" -> "X rows the boat to PLACE").
        # (Followers dragged along get their own "X follows you" line in
        # drag_followers -- a separate movement mode.)
        riding = getattr(self.character, "riding", None)
        if riding is not None:
            verb = riding.get_property("ride_verb") or "rides"
            description = "{name} {verb} the {vehicle} to {place}".format(
                name=self.character.name.capitalize(),
                verb=verb,
                vehicle=riding.name,
                place=to_loc.name,
            )
        else:
            # On foot, the verb comes from (most specific first): the exit's own
            # verb ("climbs", "falls"), then the traveller's condition/gait
            # ("limps", "staggers"; a move_verb property set on the character),
            # then the default "moved". (Riding is handled above, so a mounted
            # character never shows their on-foot gait.)
            verb = (
                # An action subclass may declare its own verb (Sneak: "slip
                # silently") -- it wins over the exit's and the character's.
                getattr(self, "MOVE_VERB", None)
                or self.location.move_verbs.get(self.direction)
                or self.character.get_property("move_verb")
                or "moved"
            )
            description = "{character_name} {verb} to {place}".format(
                character_name=self.character.name.capitalize(),
                verb=verb,
                place=to_loc.name,
            )
        # A travel description may be a plain string or a callable(game) -> str
        # computed at traversal time (e.g. an outcome that depends on what the
        # traveller is wearing). Either is appended after the arrival line.
        travel = self.location.travel_descriptions[self.direction]
        if callable(travel):
            travel = travel(self.game)
        if travel:
            description += " " + travel
        self.parser.ok(description)

        # Some locations finish game
        if to_loc.get_property(Property.GAME_OVER) and is_main_player:
            self.game.game_over = True
            self.game.game_over_description = to_loc.description
            self.parser.ok(to_loc.description)
        else:
            # A location may carry a ``figure``: its card draws ABOVE the room
            # description -- a title plate for the arrival, not a footnote
            # (CCB). Same contract as the Examine hook: once per game, player
            # only, callable(game) -> key for state-dependent cards.
            if is_main_player:
                fig = to_loc.get_property("figure")
                self.game.show_figure(fig(self.game) if callable(fig) else fig)
            action = base.Describe(self.game, command=self.command)
            action()

        # Pull along anyone following the mover (after the room is described).
        self.game.drag_followers(self.character)
