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
from .reporting import Channel, Message, default_renderer, wrap_text


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

        # How output is shown. The engine builds Messages (by Channel) and hands
        # them to a Renderer; the default picks a colored terminal renderer when
        # one fits, else a plain fallback. Web mode passes a WebRenderer.
        # See text_adventure_games/reporting.py.
        self.renderer = renderer if renderer is not None else default_renderer()

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
        message = {"role": "user", "content": command}
        self.command_history.append(message)
        # CCB - todo - manage command_history size

    def add_description_to_history(self, description: str):
        message = {"role": "assistant", "content": description}
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
            return "sequence"
        elif (
            command.startswith("say ")
            or command.startswith("speak ")
            or command in ("say", "speak")
        ):
            # Speech routes here regardless of message content (a message may
            # contain other command words), and this also handles the "speak"
            # alias, which is not auto-registered.
            return "say"
        elif self.get_direction(command, character.location):
            # Check for the direction intent
            return "go"
        elif command == "look" or command == "l":
            # when the user issues a "look" command, re-describe what they see
            return "describe"
        elif "examine " in command or command.startswith("x "):
            return "examine"
        elif "take " in command or "get " in command:
            return "get"
        elif "light" in command:
            return "light"
        elif "drop " in command:
            return "drop"
        elif (
            "eat " in command
            or "eats " in command
            or "ate " in command
            or "eating " in command
        ):
            return "eat"
        elif "drink" in command:
            return "drink"
        elif "give" in command:
            return "give"
        elif "attack" in command or "hit " in command or "hits " in command:
            return "attack"
        elif "inventory" in command or command == "i":
            return "inventory"
        elif command == "wait" or command == "z":
            return "wait"
        elif "quit" in command:
            return "quit"
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
        Converts aliases for directions into its primary direction name.
        """
        command = command.lower()
        if command == "n" or "north" in command:
            return "north"
        if command == "s" or "south" in command:
            return "south"
        if command == "e" or "east" in command:
            return "east"
        if command == "w" or "west" in command:
            return "west"
        if command.endswith("go up"):
            return "up"
        if command.endswith("go down"):
            return "down"
        if command.endswith("go out"):
            return "out"
        if command.endswith("go in"):
            return "in"
        if location:
            for exit in location.connections.keys():
                if exit.lower() in command:
                    return exit
        return None
