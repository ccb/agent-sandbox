"""The Parser

The parser is the module that handles the natural language understanding in
the game. The players enter commands in text, and the parser interprets them
and performs the actions that the player intends.  This is the module with
the most potential for improvement using modern natural language processing.
The implementation that I have given below only uses simple keyword matching.
"""

import inspect

from text_adventure_games import games

from .things import Character, Item, Location
from . import actions, blocks
from .enums import ActionName, Direction, Role
from .reporting import Channel, Message, default_renderer, wrap_text

# Maps the one-letter direction shortcuts ("n", "s", "e", "w") onto canonical
# Direction members. Up/down/in/out have no single-letter alias today; if
# games add new shortcuts, extend here rather than in get_direction.
_DIRECTION_ALIASES: dict[str, Direction] = {
    "n": Direction.NORTH,
    "s": Direction.SOUTH,
    "e": Direction.EAST,
    "w": Direction.WEST,
}

# Direction members whose name should be detected when it appears anywhere in
# the command ("you may travel north" -> Direction.NORTH). These are the
# cardinals; up/down/in/out are too easily mistaken for unrelated words
# (e.g. "drink water" contains "in"), so they require the explicit "go up"
# form below.
_SUBSTRING_DIRECTIONS = (
    Direction.NORTH,
    Direction.SOUTH,
    Direction.EAST,
    Direction.WEST,
)

# Direction members usable as "go <name>" -- avoids the substring ambiguity.
_GO_SUFFIX_DIRECTIONS = (
    Direction.UP,
    Direction.DOWN,
    Direction.OUT,
    Direction.IN,
)


class Parser:
    """
    The Parser is the class that handles the player's input.  The player
    writes commands, and the parser performs natural language understanding
    in order to interpret what the player intended, and how that intent
    is reflected in the simulated world.
    """

    def __init__(self, game, echo_commands=False, renderer=None):
        # A list of the commands that the player has issued,
        # and the respones given to the player.
        self.command_history = []

        # Build default scope of actions
        self.actions = game.default_actions()

        # Build default scope of blocks - CCB: TODO - move blocks to the game class
        self.blocks = game.default_blocks()

        # A pointer to the game.
        self.game = game
        self.game.parser = self

        # Print the user's commands
        self.echo_commands = echo_commands

        # Set by fail() so the ReAct loop can read the reason without side-effects
        self.last_fail_message: str | None = None

        # The most recent action that passed its preconditions; the NPC turn
        # loop reads its get_duration() to charge the per-turn budget (issue #24).
        self.last_action = None

        # How output is shown. The engine builds Messages (by Channel) and hands
        # them to a Renderer; the default picks a colored terminal renderer when
        # one fits, else a plain fallback. Web mode passes a WebRenderer.
        # Verbosity/color come from the game's RenderConfig when available,
        # falling back to the OUTPUT_LEVEL / NO_COLOR env vars otherwise.
        # See text_adventure_games/reporting.py.
        if renderer is not None:
            self.renderer = renderer
        else:
            render_cfg = getattr(game, "config", None)
            render_cfg = getattr(render_cfg, "render", None)
            if render_cfg is not None:
                self.renderer = default_renderer(
                    level=render_cfg.level,
                    no_color=render_cfg.no_color,
                    width=render_cfg.width,
                )
            else:
                self.renderer = default_renderer()

    def set_renderer(self, renderer):
        """Swap the renderer (e.g. a WebRenderer for the Flask app, or a
        CaptureRenderer in tests)."""
        self.renderer = renderer

    def _emit(self, channel: Channel, text: str, actor=None, meta=None):
        """Build a Message on *channel* and hand it to the renderer."""
        self.renderer.emit(
            Message(channel, text, actor=actor, turn=self.game.turn, meta=meta or {})
        )

    def ok(self, description: str):
        """Report a successful action's world narration."""
        self._emit(Channel.NARRATION, description)
        self.add_description_to_history(description)

    def fail(self, description: str):
        """Report an action blocked by its preconditions. ``last_fail_message``
        is set so the ReAct Reflect step can read the reason."""
        self.last_fail_message = description
        self._emit(Channel.BLOCKED, description)

    @staticmethod
    def wrap_text(text: str, width: int = 80) -> str:
        """
        Keeps text output narrow enough to easily be read
        """
        return wrap_text(text, width)

    def add_command_to_history(self, command: str):
        message = {"role": Role.USER, "content": command}
        self.command_history.append(message)
        # CCB - todo - manage command_history size

    def add_description_to_history(self, description: str):
        message = {"role": Role.ASSISTANT, "content": description}
        self.command_history.append(message)
        # CCB - todo - manage command_history size

    def add_action(self, action: actions.Action):
        """
        Add an Action class to the list of actions a parser can use
        """
        self.actions[action.action_name()] = action

    def add_block(self, block):
        """
        Adds a block class to the list of blocks a parser can use. This is
        primarily useful for loading game states from a save.
        """
        self.blocks[block.__class__.__name__] = block

    def init_actions(self):
        self.actions = {}
        for member in dir(actions):
            attr = getattr(actions, member)
            if inspect.isclass(attr) and issubclass(attr, actions.Action):
                # dont include base class
                if not attr == actions.Action:
                    self.add_action(attr)

    def determine_intent(self, command: str, actor=None):
        """
        This function determines what command the player wants to do.
        Here we have implemented it with a simple keyword match. Later
        we will use AI to do more flexible matching.
        """
        # Resolve the acting character (the actor, else a player-default scan).
        # Used below only to interpret directions relative to where they stand.
        character = actor if actor is not None else self.get_character(command)
        command = command.lower()
        if "," in command:
            # Let the player type in a comma separted sequence of commands
            return ActionName.SEQUENCE
        elif (
            command.startswith("say ")
            or command.startswith("speak ")
            or command in ("say", "speak")
        ):
            # Speech routes here regardless of message content (a message may
            # contain other command words), and this also handles the "speak"
            # alias, which is not auto-registered.
            return ActionName.SAY
        elif command.startswith("adopt goal"):
            # Goal-management verbs are matched explicitly: "drop goal ..." must
            # win over the inventory "drop" verb below, and both must beat the
            # generic longest-match fallback.
            return "adopt goal"
        elif command.startswith("drop goal"):
            return "drop goal"
        elif self.get_direction(command, character.location):
            # Check for the direction intent
            return ActionName.GO
        elif command == "look" or command == "l":
            # when the user issues a "look" command, re-describe what they see
            return ActionName.DESCRIBE
        elif "examine " in command or command.startswith("x "):
            return ActionName.EXAMINE
        elif command.startswith("take off") or command.startswith("remove "):
            # Must precede the "take "/get branch -- "take " is a substring of
            # "take off" and would otherwise route equipment removal to Get.
            return ActionName.TAKE_OFF
        elif command.startswith("stow ") or command.startswith("unequip "):
            return ActionName.UNWIELD
        elif "take " in command or "get " in command:
            return ActionName.GET
        elif "light" in command:
            return ActionName.LIGHT
        elif "drop " in command:
            return ActionName.DROP
        elif (
            "eat " in command
            or "eats " in command
            or "ate " in command
            or "eating " in command
        ):
            return ActionName.EAT
        elif "drink" in command:
            return ActionName.DRINK
        elif "give" in command:
            return ActionName.GIVE
        elif "attack" in command or "hit " in command or "hits " in command:
            return ActionName.ATTACK
        elif "inventory" in command or command == "i":
            return ActionName.INVENTORY
        elif command == "wait" or command == "z":
            return ActionName.WAIT
        elif "quit" in command:
            return ActionName.QUIT
        else:
            best_match = None
            for _, action in self.actions.items():
                special_command = action.action_name()
                if special_command in command:
                    if best_match is None or len(special_command) > len(best_match):
                        best_match = special_command
            return best_match

    def parse_action(self, command: str, actor=None) -> actions.Action:
        """
        Routes an action described in a command to the right action class for
        performing the action.
        """
        if self.echo_commands:
            self._emit(Channel.COMMAND, command)
        return self.peek_action(command, actor=actor)

    def peek_action(self, command: str, actor=None) -> actions.Action:
        """Build the Action a command would route to WITHOUT echoing or running
        it. Constructing the action matches its target (item/character/exit) via
        ``match_item`` / ``get_character``, but ``check_preconditions`` /
        ``apply_effects`` never run. Used by the simultaneous gather phase to read
        an intent's action name and the resource it claims (issue #42), where a
        full ``parse_command`` would prematurely echo and mutate the world."""
        command = command.lower().strip()
        if command == "":
            return None
        intent = self.determine_intent(command, actor=actor)
        if intent in self.actions:
            action = self.actions[intent]
            return action(self.game, command, actor=actor)
        return None

    def npc_ok(self, description: str):
        """Report an NPC's action narration (rendered distinctly from the
        player's own narration)."""
        self._emit(Channel.NPC_NARRATION, description)
        self.add_description_to_history(description)

    def conflict(self, actor: str, description: str):
        """Report that *actor* lost a contested resource this round (issue #42).

        Distinct from :meth:`fail`: it's not a precondition error, it's the
        outcome of two characters reaching for the same thing in a simultaneous
        round. Goes on its own ``CONFLICT`` channel so a renderer can tell the
        contention story, and is deliberately kept OUT of command_history (the
        loser's private setback must not leak into other characters'
        observations)."""
        self._emit(Channel.CONFLICT, description, actor=actor)

    # ------------------------------------------------------------------
    # Agent trace (the ReAct loop's Observe / Think / Act / Reflect).
    #
    # Each goes to the renderer on its own Channel and is deliberately NOT
    # added to command_history: an NPC's reasoning is private, so it must never
    # leak into other characters' observations.
    # ------------------------------------------------------------------

    def agent_observation(self, actor: str, text: str):
        self._emit(Channel.AGENT_OBSERVATION, text, actor=actor)

    def agent_reasoning(self, actor: str, text: str):
        self._emit(Channel.AGENT_REASONING, text, actor=actor)

    def agent_action(self, actor: str, command: str):
        self._emit(Channel.AGENT_ACTION, command, actor=actor)

    def agent_reflection(self, actor: str, text: str):
        self._emit(Channel.AGENT_REFLECTION, text, actor=actor)

    def npc_log(self, message: str):
        """Legacy agent-trace shim (a single pre-formatted line). Prefer the
        typed ``agent_*`` methods above; kept so older callers keep working."""
        self._emit(Channel.AGENT_REASONING, message)

    def turn_header(self, turn: int = None, time: str = None):
        """Ask the renderer to mark a turn boundary (terminal renderers draw a
        rule; others may ignore it)."""
        if turn is None:
            turn = self.game.turn
        if time is None:
            time = self.game.current_time()
        self.renderer.turn_header(turn, time)

    def parse_command(self, command: str, actor=None) -> bool:
        # add this command to the history
        self.add_command_to_history(command)
        action = self.parse_action(command, actor=actor)
        if not action:
            self.fail("I'm not sure what you want to do.")
            return False
        action()
        success = getattr(action, "_preconditions_passed", False)
        if success:
            # Remember the action that just ran so the NPC turn loop can read
            # its in-game duration when charging the per-turn budget (issue #24).
            self.last_action = action
            # Attribute the event to whoever is acting. The actor is threaded in
            # explicitly — the player via Game.do_command, an NPC via its
            # behavior — so we record the true subject of the command. Only fall
            # back to scanning the command for a name when no actor was supplied,
            # which keeps the field correct even for player commands that name
            # another character (e.g. "attack troll").
            #
            # (An ActionSequence re-enters parse_command per sub-command, so one
            # comma-separated command logs each sub-command plus the wrapping
            # "sequence" action — a future event-log consumer (#9) should expect that.)
            event_actor = actor if actor is not None else self.get_character(command)
            self.game.log_event(event_actor.name, action.action_name(), command)
        return success

    def get_character(
        self,
        command: str,
        hint: str = None,
        split_words=None,
        position=None,
        exclude=None,
    ) -> Character:
        """
        This method tries to match a character's name in the command.
        If no names are matched, it returns the default value. A candidate
        equal to ``exclude`` is skipped (used to keep an action's target from
        resolving to its own actor).
        """
        command = command.lower()
        if split_words:
            for word in split_words:
                if word in command:
                    parts = command.split(word, 1)
                    command_before_word = parts[0]
                    command_after_word = parts[1]
                    if position == "before":
                        command = command_before_word
                    if position == "after":
                        command = command_after_word
                    break
        for name in self.game.characters.keys():
            if name.lower() in command:
                candidate = self.game.characters[name]
                if exclude is not None and candidate is exclude:
                    continue
                return candidate
        return self.game.player

    def get_character_location(self, character: Character) -> Location:
        return character.location

    def match_item(
        self, command: str, item_dict: dict[str, Item], hint: str = None
    ) -> Item:
        """
        Check whether the name any of the items in this dictionary match the
        command. If so, return Item, else return None.
        """
        matched_items = {}
        for item_name in item_dict:
            # if this item is in the command, or in the hint then it matches
            if item_name in command:
                item = item_dict[item_name]
                matched_items[item_name] = item
            if hint and (item_name in hint or hint in item_name):
                item = item_dict[item_name]
                matched_items[item_name] = item

        if len(matched_items) == 0:
            return None
        # if there are multiple items that are matched
        # then try to return one matches the hint
        elif len(matched_items) > 1 and hint:
            # exact match with hint
            if hint in matched_items:
                item = matched_items[hint]
                return item
            # hint in item name
            for item_name in matched_items:
                if hint in item_name or item_name in hint:
                    item = matched_items[item_name]
                    return item
        for item_name in matched_items:
            item = matched_items[item_name]
            return item

    def get_items_in_scope(self, character=None) -> dict[str, Item]:
        """
        Returns a list of items in character's location and in their inventory
        """
        if character is None:
            character = self.game.player
        items_in_scope = {}
        for item_name in character.location.items:
            items_in_scope[item_name] = character.location.items[item_name]
        for item_name in character.inventory:
            items_in_scope[item_name] = character.inventory[item_name]
        return items_in_scope

    def get_direction(self, command: str, location: Location = None) -> str:
        """
        Converts aliases for directions into its canonical direction name.

        Returns the direction as a string (Direction members ARE strings via
        the str-mixin enum, so the return type is compatible with the
        existing dict lookups in Location.connections).
        """
        command = command.lower()
        # Single-letter shortcuts only fire on the bare command -- "n", "s",
        # not "open the box".
        if command in _DIRECTION_ALIASES:
            return _DIRECTION_ALIASES[command]
        # Cardinal name appearing anywhere in the command.
        for direction in _SUBSTRING_DIRECTIONS:
            if direction in command:
                return direction
        # Vertical / in-out require the explicit "go <name>" form so we don't
        # mis-fire on words like "drink" containing "in".
        for direction in _GO_SUFFIX_DIRECTIONS:
            if command.endswith(f"go {direction}"):
                return direction
        # Fall back to any exit name the location declares -- supports games
        # that invent custom direction tokens like "through the portal".
        if location:
            for exit in location.connections.keys():
                if exit.lower() in command:
                    return exit
        return None
