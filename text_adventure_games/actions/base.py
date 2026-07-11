from __future__ import annotations
from ..things import Thing, Character, Item, Location
from ..reactions import GatedEffect
from ..enums import ActionName
import re


def conjugate(character, second: str, third: str) -> str:
    """Pick the verb form for *character*: second person for the player (named
    "you"), third person for everyone else -- so messages read "You don't have
    a weapon" and "Troll doesn't have a weapon" from the same template."""
    return second if character.name.lower() == "you" else third


class Action(GatedEffect):
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

    An Action is a command-triggered :class:`~text_adventure_games.reactions.GatedEffect`:
    the parser builds it from a command, then calls it, which runs the
    gate->effect contract inherited from ``GatedEffect``. A
    :class:`~text_adventure_games.reactions.Reaction` is the same contract pulled
    by the world rather than by a command.
    """

    ACTION_NAME: str | None = None
    ACTION_DESCRIPTION: str = None
    ACTION_ALIASES: list[str] = None

    # Whether this verb is something the player issues, and so should appear in
    # the HELP listing. Defaults to True. NPC-only flavor actions (a troll's
    # "growl", a ghost's "haunt") set this False so HELP stays a player's menu.
    PLAYER_VISIBLE: bool = True

    # In-game minutes this action consumes (issue #24). None means "no declared
    # cost" — the NPC turn loop treats that as a full per-turn budget, so an
    # undeclared action takes one action per turn, exactly as before durations
    # existed. Subclasses set a positive integer to make the action cheaper.
    DURATION: int = None

    # How many room-hops the *sound* of this action carries (issue #80 hearing).
    # 0 (the default) means it's heard only in the room it happens in, so
    # perception stays room-scoped until an action opts in -- a SHOUT/SCREAM
    # might use 2, a crash 1. This is the action's physical volume, distinct from
    # the contextual "does it disturb this creature" sets used by threat triggers.
    AUDIBLE_RADIUS: int = 0

    def __init__(self, game, actor=None):
        self.game = game
        self.parser = game.parser
        self.actor = actor

    def get_duration(self):
        """In-game minutes this action consumes, or None for no declared cost.

        Override point for dynamic costs (e.g. an LLM-estimated duration);
        the default simply returns the declared ``DURATION``.
        """
        return self.DURATION

    def audible_radius(self) -> int:
        """Room-hops this action's sound carries (override for dynamic volume)."""
        return self.AUDIBLE_RADIUS

    def sound_description(self) -> str:
        """How the sound reads to someone who hears it from another room (they
        can't see what happened). Override for flavor (e.g. "a scream")."""
        return "a commotion"

    def acting_character(self, command, **kwargs):
        """Resolve who performs this action: the explicit actor if one was
        supplied, else the legacy command-string scan (player default)."""
        if self.actor is not None:
            return self.actor
        return self.parser.get_character(command, **kwargs)

    def character_in_room(self, command, looker):
        """Match a character (other than *looker*) co-located with *looker* whose
        name appears in *command*; longest name first so "old man" beats "man".

        Unlike ``parser.get_character`` this is room-scoped and never defaults to
        the player -- it returns ``None`` when no present character matches. Used
        by verbs that act on a person in the room (examine, talk)."""
        loc = getattr(looker, "location", None)
        if loc is None:
            return None
        cmd = command.lower()
        for name in sorted(loc.characters, key=len, reverse=True):
            other = loc.characters[name]
            if other is not looker and name.lower() in cmd:
                return other
        # Aliases match too ("throw gel at horror" finds the fungal horror).
        for other in loc.characters.values():
            if other is looker:
                continue
            for alias in getattr(other, "aliases", ()):
                if alias in cmd:
                    return other
        return None

    def target_character(self, command, exclude=None, **kwargs):
        """Resolve the character an action is aimed AT (its object), as opposed
        to its actor resolved by ``acting_character``.

        Excludes the actor by default so an action never targets the character
        performing it. ``parser.get_character`` returns the player as its
        no-match default; that default is right for player-issued commands but
        wrong for an agent acting on its own — so when a non-player actor refers
        to no one, we return ``None`` instead. The action's precondition gate
        then reports a missing target (e.g. "Give it to whom?") and the ReAct
        loop feeds that reason back so the agent names a target on its retry.

        A command that *does* refer to the player still targets them: an agent
        refers to the player by name or by the bare word "player" — the form
        agents are taught to use, e.g. "attack player" (see npc.py). The engine
        player is conventionally named "The player", so we accept either form.
        """
        if exclude is None:
            exclude = self.actor
        candidate = self.parser.get_character(command, exclude=exclude, **kwargs)
        player = self.game.player
        lowered = command.lower()
        player_referenced = player.name.lower() in lowered or "player" in lowered
        if (
            self.actor is not None
            and self.actor is not player
            and candidate is player
            and not player_referenced
        ):
            return None
        return candidate

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

    # __call__ (the gate->effect runner) is inherited from GatedEffect.

    def claimed_resource(self):
        """The single world resource this action reaches for — the thing two
        characters might contend over in a simultaneous round (issue #42): an
        item to pick up, a recipient to hand to, a tile to step onto.

        The simultaneous gather phase reads this (after constructing the action,
        before running it) to detect contention: when two intents claim the
        *same* object, only the higher-priority one can take it. The base action
        claims nothing; an action that competes for a resource overrides this to
        return the matched object (or ``None`` if its command matched nothing).
        Returning ``None`` means "never contended" — correct for untargeted
        actions like ``look`` or ``inventory``."""
        return None

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
            if not cmd:
                # Skip empty segments -- a trailing comma, a doubled comma, or
                # stray whitespace shouldn't fire "I'm not sure what you want
                # to do" on a blank command.
                continue
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


class Help(Action):
    """List the actions the player can take right now.

    The parser keys every registered action by ``action_name()`` (see
    ``Game.default_actions`` / ``Parser.add_action``), so this reads that live
    dict and reports each verb with its description and aliases -- game-defined
    actions included, for free. A few engine-internal verbs that aren't typed by
    a player (the comma-sequence wrapper) are hidden."""

    ACTION_NAME = ActionName.HELP
    FREE_ACTION = True  # pure UI: costs no turn (see meta_actions_cost_turns)
    ACTION_DESCRIPTION = "List the commands you can use"
    ACTION_ALIASES = ["h", "commands", "?"]

    # action_name() keys for verbs that exist for the engine's own plumbing
    # rather than as something a player would type, so they're left off the list.
    _HIDDEN = {ActionName.SEQUENCE}

    def __init__(self, game, command: str, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        entries = []
        for name, action in self.parser.actions.items():
            if name in self._HIDDEN or not action.PLAYER_VISIBLE:
                continue
            description = action.ACTION_DESCRIPTION or ""
            aliases = getattr(action, "ACTION_ALIASES", None) or []
            entries.append((name, description, aliases))
        entries.sort()
        # Align descriptions against the command NAMES only (capped) -- never
        # against the alias lists, whose length used to blow the column width out
        # and wrap every line. Any aliases trail at the end of their own line, so
        # a verb with many of them no longer pads every other command.
        width = min(max((len(name) for name, _, _ in entries), default=0), 20)
        lines = ["You can try these commands:"]
        for name, description, aliases in entries:
            line = f"  {name.ljust(width)}  {description}".rstrip()
            if aliases:
                line += f"  ({', '.join(aliases)})"
            lines.append(line)
        self.parser.ok("\n".join(lines))


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
        cmd = (self.command or "").strip().lower()
        rest = cmd
        for lead in ("look at ", "look ", "l "):
            if cmd.startswith(lead):
                rest = cmd[len(lead) :].strip()
                break
        # "look <direction>" surveys an exit instead of re-describing the room.
        if rest and rest != cmd and rest not in ("around", "round", "here"):
            looker = self.actor if self.actor is not None else self.game.player
            loc = looker.location
            direction = self.parser.get_direction(rest, loc)
            if direction:
                if loc.is_blocked(direction):
                    return self.parser.ok(loc.get_block_description(direction))
                dest = loc.connections.get(direction)
                if dest is None:
                    return self.parser.ok("You see nothing special that way.")
                travel = loc.travel_descriptions.get(direction) or ""
                line = f"To the {direction}, you see {dest.name}."
                return self.parser.ok(f"{line} {travel}".strip())
        # An explicit LOOK replays the room's illustration (CCB): the arrival
        # plate is once-per-game, but asking to look again re-earns it. Only
        # the bare look forms count -- Go's internal describe passes the
        # movement command through here and must not re-cue.
        looker = self.actor if self.actor is not None else self.game.player
        if looker is self.game.player and cmd in (
            "look",
            "l",
            "describe",
            "look around",
            "look round",
            "look here",
        ):
            loc = looker.location
            if loc is not None:
                fig = loc.get_property("figure")
                self.game.show_figure(
                    fig(self.game) if callable(fig) else fig, force=True
                )
        self.parser.ok(self.game.describe())
