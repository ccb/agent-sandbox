from .things import Location, Character
from .clock import GameClock
from . import parsing, actions, blocks
from .enums import EventKind, Property
from .events import GameEvent
from .triggers import Trigger, MAX_CASCADE_PASSES, at_turn

import json
import inspect
from collections import namedtuple


class Game:
    """
    The Game class keeps track of the state of the world, and describes what
    the player sees as they move through different locations.

    Internally, we use a graph of Location objects and Item objects, which can
    be at a Location or in the player's inventory.  Each locations has a set of
    exits which are the directions that a player can move to get to an
    adjacent location. The player can move from one location to another
    location by typing a command like "Go North".
    """

    def __init__(
        self,
        start_at: Location,
        player: Character,
        characters=None,
        custom_actions=None,
        time_config=None,
    ):
        self.start_at = start_at
        self.player = player

        # Print the special commands associated with items in the game (helpful
        # for debugging and for novice players).
        self.give_hints = True

        # Records history of commands, states, and descriptions
        self.game_history = []

        self.game_over = False
        self.game_over_description = None

        # Add player to game and put them on starting point
        self.characters = {}
        self.add_character(player)
        self.start_at.add_character(player)
        self.start_at.has_been_visited = True

        # Add NPCs to game
        if characters:
            for c in characters:
                if isinstance(c, Character):
                    self.add_character(c)
                else:
                    err_msg = f"ERROR: invalid character ({c})"
                    raise Exception(err_msg)

        # Look up table for locations
        def location_map(location, acc):
            acc[location.name] = location
            for _, connection in location.connections.items():
                if connection.name not in acc:
                    acc = location_map(connection, acc)
            return acc

        self.locations = location_map(self.start_at, {})

        # Turn counter
        self.turn = 0

        # Event log (issue #6): append-only record of what happened each round
        self.events = []

        # Triggers (issue #6): rules fired in the post-round react phase
        self.triggers = []

        # Optional in-game clock (issue #7). Time is opt-in: with no
        # time_config the turn counter still increments but no clock exists.
        # Accepts a GameClock, a dict of GameClock kwargs, or None.
        if time_config is None:
            self.clock = None
        elif isinstance(time_config, GameClock):
            self.clock = time_config
        elif isinstance(time_config, dict):
            self.clock = GameClock(**time_config)
        else:
            err_msg = f"ERROR: invalid time_config ({time_config})"
            raise Exception(err_msg)

        # Parser
        self.custom_actions = custom_actions
        self.set_parser(parsing.Parser(self))

        # Visit each location and add any blocks found to parser
        seen_before = {}
        for name, location in self.locations.items():
            if len(location.blocks) > 0 and name not in seen_before:
                for b in location.blocks:
                    self.parser.add_block(b)
                    seen_before[name] = True

    def do_command(self, command: str) -> bool:
        """
        Public entry point for processing a player command. Parses the command
        and, if successful, runs the end-of-turn phase (increment turn counter,
        run NPC behaviors).
        """
        # The player is the subject of any command entered here, so pass them as
        # the explicit actor. This keeps the event log correct even when the
        # command names another character (e.g. "attack troll") — without it the
        # parser falls back to scanning the command for a name and would mis-log
        # the event under the named target instead of the player.
        success = self.parser.parse_command(command, actor=self.player)
        if success:
            self.end_turn()
        return success

    def end_turn(self):
        """
        Called after a successful player command. Increments the turn counter,
        gives each living, conscious NPC a chance to act, and then runs the
        react phase: triggers (including scheduled events) whose conditions
        are now true.
        """
        self.turn += 1
        for character in list(self.characters.values()):
            if character is self.player:
                continue
            if character.get_property(Property.IS_DEAD) or character.get_property(
                Property.IS_UNCONSCIOUS
            ):
                continue
            if character.location is None:
                continue
            character.take_turn(self)
            if self.is_game_over():
                break
        if not self.is_game_over():
            self._run_triggers()

    def log_event(self, actor, action, summary="", payload=None):
        """Append a GameEvent to the event log (issue #6)."""
        self.events.append(GameEvent(self.turn, actor, action, summary, payload))

    def add_trigger(self, name, condition, action, repeatable=False):
        """Register a Trigger evaluated in the post-round react phase (issue #6)."""
        trigger = Trigger(name, condition, action, repeatable)
        self.triggers.append(trigger)
        return trigger

    def _run_triggers(self):
        """React phase: fire triggers whose conditions are now true.

        Re-evaluates in bounded passes so a trigger can enable another one
        (cascading), but each trigger fires at most once per round and the chain
        is capped at MAX_CASCADE_PASSES to prevent infinite loops.
        """
        fired_this_round = set()
        for _ in range(MAX_CASCADE_PASSES):
            newly_fired = False
            for trigger in self.triggers:
                if trigger in fired_this_round:
                    continue
                if trigger.fired and not trigger.repeatable:
                    continue
                if trigger.condition(self):
                    trigger.action(self)
                    trigger.fired = True
                    fired_this_round.add(trigger)
                    self.log_event(EventKind.TRIGGER, trigger.name, f"{trigger.name} fired")
                    newly_fired = True
            if not newly_fired:
                break

    def schedule_event(self, turn: int, callback, name=None):
        """
        Schedule a one-shot event: `callback(game)` will run in the react phase
        of the round in which the turn counter reaches `turn` (after all
        characters have acted). Scheduling for a turn that has already passed
        fires the event in the next round's react phase.

        This is convenience sugar for the trigger system (issue #6): it
        registers a non-repeatable trigger with an `at_turn(turn)` condition,
        so scheduled events follow trigger semantics — they fire at most once,
        run in the react phase, and are recorded in the event log. Returns the
        underlying Trigger.

        For a recurring event, schedule a future turn from the callback:

            def every_morning(game):
                ...do something...
                game.schedule_event(game.turn + 4, every_morning)

        (Or use `add_trigger` with the `every(n)` condition and
        `repeatable=True` for a fixed cadence.)
        """
        if not isinstance(turn, int) or turn < 0:
            err_msg = f"ERROR: invalid schedule turn ({turn})"
            raise Exception(err_msg)
        if not callable(callback):
            err_msg = f"ERROR: schedule callback is not callable ({callback})"
            raise Exception(err_msg)
        if name is None:
            name = f"scheduled@turn{turn}"
        return self.add_trigger(name, at_turn(turn), callback, repeatable=False)

    def current_time(self):
        """
        The in-game time as a string, e.g. '8:45 AM (morning)', or None if
        this game has no clock configured.
        """
        if self.clock is None:
            return None
        return self.clock.describe(self.turn)

    def game_loop(self):
        """
        A simple loop that starts the game, loops over commands from the user,
        and then stops if the game's state says the game is over.
        """
        self.parser.parse_command("look")

        while True:
            # When a clock is configured, show the in-game time in the prompt.
            time_str = self.current_time()
            prompt = f"\n[{time_str}] > " if time_str else "\n> "
            command = input(prompt)
            self.do_command(command)
            if self.is_game_over():
                break

    def is_won(self) -> bool:
        """
        A conditional check intended for subclasses to use for defining the
        game's winning conditions.
        """
        return False

    def is_game_over(self) -> bool:
        """
        A conditional check that determines if the game is over. By default it
        checks if the player has died or won.
        """
        # Something has set the game over state
        if self.game_over:
            return True
        # The player has died
        if self.player.get_property(Property.IS_DEAD):
            self.game_over_description = "You have died. THE END"
            return True
        # The player has been knocked unconscious
        if self.player.get_property(Property.IS_UNCONSCIOUS):
            self.game_over_description = "You have been knocked unconscious. THE END"
            return True
        # Has the game has been won?
        return self.is_won()

    def add_character(self, character: Character):
        """
        Puts characters in the game
        """
        self.characters[character.name] = character

    def describe(self) -> str:
        """
        Describe the current game state by first describing the current
        location, then listing any exits, and then describing any objects
        in the current location.
        """
        description = self.player.location.name.upper() + "\n"
        if self.clock is not None:
            description += f"({self.current_time()})\n"
        description += self.describe_current_location() + "\n"
        description += self.describe_exits() + "\n"
        description += self.describe_items() + "\n"
        description += self.describe_characters() + "\n"
        # self.parser.ok(description)
        return description

    def describe_current_location(self) -> str:
        """
        Describe the current location by printing its description field.
        """
        return self.player.location.description

    def describe_exits(self) -> str:
        """
        List the directions that the player can take to exit from the current
        location.
        """
        exits = []
        for direction in self.player.location.connections.keys():
            location = self.player.location.connections[direction]
            exits.append(f" * {direction.capitalize()} to {location.name}")
        description = ""
        if len(exits) > 0:
            description = "Exits:\n"
            for exit in exits:
                description += exit + "\n"
        return description

    def describe_items(self) -> str:
        """
        Describe what items are in the current location.
        """
        description = ""
        if len(self.player.location.items) > 0:
            description = "You see:"
            for item_name in self.player.location.items:
                item = self.player.location.items[item_name]
                description += f"\n * {item.name} - {item.description}"
                if self.give_hints:
                    special_commands = item.get_command_hints()
                    for cmd in special_commands:
                        description += "\n\t" + cmd
        return description

    def describe_characters(self) -> str:
        """
        Describe what characters are in the current location.
        """
        description = ""

        if len(self.player.location.characters) > 1:
            description = "Characters:"
            for character_name in self.player.location.characters:
                if character_name == self.player.name:
                    continue
                character = self.player.location.characters[character_name]
                description += f"\n * {character.name} - {character.description}"
        return description

    def describe_inventory(self) -> str:
        """
        Describes the player's inventory.
        """
        if len(self.player.inventory) == 0:
            empty_inventory = "You don't have anything."
            self.ok(empty_inventory, [], "Describe the player's inventory.")
        else:
            # descriptions = []  # JD logical issue?
            inventory_description = "In your inventory, you have:\n"
            for item_name in self.player.inventory:
                item = self.player.inventory[item_name]
                d = "* {item} - {item_description}\n"
                inventory_description += d.format(
                    item=item_name, item_description=item.description
                )
            self.ok(inventory_description)

    def describe_for(self, character: Character) -> str:
        """
        Describe the game world from a specific character's perspective.
        Used by NPC behaviors and the ReAct loop to observe their environment.
        """
        loc = character.location
        lines = []

        # Location
        lines.append(loc.name.upper())
        lines.append(loc.description)

        # Exits
        if loc.connections:
            lines.append("Exits:")
            for direction, dest in loc.connections.items():
                lines.append(f" * {direction.capitalize()} to {dest.name}")

        # Items at location
        if loc.items:
            lines.append("Items here:")
            for item_name, item in loc.items.items():
                lines.append(f" * {item.name} - {item.description}")

        # Other characters present
        others = [c for name, c in loc.characters.items() if name != character.name]
        if others:
            lines.append("Characters here:")
            for c in others:
                lines.append(f" * {c.name} - {c.description}")

        # Inventory
        if character.inventory:
            lines.append("Inventory:")
            for item_name, item in character.inventory.items():
                lines.append(f" * {item.name} - {item.description}")
        else:
            lines.append("Inventory: empty")

        # Available actions
        action_names = sorted(self.parser.actions.keys())
        lines.append(f"Available actions: {', '.join(action_names)}")

        # Turn (with the in-game time when a clock is configured)
        if self.clock is not None:
            lines.append(f"Turn: {self.turn} ({self.current_time()})")
        else:
            lines.append(f"Turn: {self.turn}")

        return "\n".join(lines)

    def set_parser(self, parser):
        """
        Use a different parser for this game.
        """
        self.parser = parser
        if self.custom_actions:
            for ca in self.custom_actions:
                if inspect.isclass(ca) and issubclass(ca, actions.Action):
                    self.parser.add_action(ca)
                else:
                    err_msg = f"ERROR: invalid custom action ({ca})"
                    raise Exception(err_msg)

    # The methods below read and write a game to JSON
    def to_primitive(self):
        """
        Serialize a game to json.

        Note: the clock's configuration is saved, but triggers (including
        scheduled events) are not — their conditions and actions are arbitrary
        functions and can't be serialized. Games that rely on them should
        re-register them after loading.
        """
        data = {
            "player": self.player.name,
            "start_at": self.start_at.name,
            "turn": self.turn,
            "time_config": self.clock.to_primitive() if self.clock else None,
            "game_history": self.game_history,  # TODO this is empty?
            "game_over": self.game_over,
            "game_over_description": self.game_over_description,
            "characters": [c.to_primitive() for c in self.characters.values()],
            "locations": [l.to_primitive() for l in self.locations.values()],
            "actions": sorted([a for a in self.parser.actions]),
        }
        return data

    @classmethod
    def default_actions(self):
        """
        Generates a dictionary of all actions packaged as part of this library
        """
        actions_found = {}
        for member in dir(actions):
            attr = getattr(actions, member)
            if inspect.isclass(attr) and issubclass(attr, actions.Action):
                # dont include base class
                if not attr == actions.Action:
                    actions_found[attr.action_name()] = attr
        return actions_found

    @classmethod
    def default_blocks(self):
        """
        Generates as dictionary of all blocks packaged as part of this library
        """
        blocks_found = {}
        for member in dir(blocks):
            attr = getattr(blocks, member)
            if inspect.isclass(attr) and issubclass(attr, blocks.Block):
                # dont include base class
                if not attr == blocks.Block:
                    # if this changes, also adjust _type in blocks.Block
                    blocks_found[attr.__name__] = attr
        return blocks_found

    @classmethod
    def from_primitive(cls, data, custom_actions=None, custom_blocks=None):
        """
        This complex method performs the huge job of converting a game from its
        primitive representation to fully formed python objects.

        There are three main parts to this method:

        1. Create skeletons for all characters and locations. Currently, items
           exist by being in a location or a character's inventory, and so this
           step also creates item skeletons. See the from_primitive methods for
           characters and locations for more.
        2. Replace fields in skeletons where an object's name exists with the
           actual objects. This step replaces fields where an object's name is
           stored instead of the actual object.
        3. Instantiate anything left that requires full object instances to
           work properly. Blocks require actual instances for everything.

        Once those steps are done, this method simply adds any remaining game
        fields to the game instance.
        """
        SkeletonContext = namedtuple(
            "SkeletonContext", ["characters", "locations", "items"]
        )

        # FIRST PASS

        characters = {
            c["name"]: Character.from_primitive(c) for c in data["characters"]
        }
        locations = {l["name"]: Location.from_primitive(l) for l in data["locations"]}
        items = {}
        context = SkeletonContext(characters, locations, items)

        # SECOND PASS

        # Characters
        for c in context.characters.values():
            # locations
            l = context.locations[c.location]
            c.location = l
            # inventory
            for item_name, item in c.inventory.items():
                #                if hasattr(item, "location") and item.location:
                #                    l_obj = context.locations[item.location]
                #                    item.location = l_obj
                #                elif hasattr(item, "owner") and item.owner:
                #                    c_obj = context.characters[item.owner]
                #                    item.owner = c_obj
                context.items[item_name] = item

        # Locations
        for l in context.locations.values():
            # characters
            for char_name, c in l.characters.items():
                c_obj = context.characters[char_name]
                l.characters[char_name] = c_obj
            # connections
            for dir_name, connection in l.connections.items():
                c_obj = context.locations[connection]
                l.connections[dir_name] = c_obj
            # items
            for item_name, item in l.items.items():
                if hasattr(item, "location") and item.location:
                    l_obj = context.locations[item.location]
                    item.location = l_obj
                elif hasattr(item, "owner") and item.owner:
                    c_obj = context.characters[item.owner]
                    item.owner = c_obj
                context.items[item_name] = item

        # THIRD PASS

        # Actions
        action_map = cls.default_actions()

        # Validate custom actions
        if custom_actions:
            for ca in custom_actions:
                if inspect.isclass(ca) and issubclass(ca, actions.Action):
                    action_map[ca.action_name()] = ca
                else:
                    err_msg = f"ERROR: invalid custom action ({ca})"
                    raise Exception(err_msg)

        # verify all commands from primitive data have an associated action
        action_names = list(action_map.keys())
        for action_name in data["actions"]:
            if action_name not in action_names:
                err_msg = "".join(
                    [
                        f"ERROR: unmapped action ({action_name}) found in ",
                        "primitive data",
                    ]
                )
                raise Exception(err_msg)

        # Blocks
        block_map = cls.default_blocks()

        # Validate custom blocks
        if custom_blocks:
            for cb in custom_blocks:
                if inspect.isclass(cb) and issubclass(cb, blocks.Block):
                    block_map[cb.__name__] = cb
                else:
                    err_msg = f"ERROR: invalid custom block ({cb})"
                    raise Exception(err_msg)

        # Instantiate all blocks for all locations
        # CCB - temporarially removing this.
        # for l in context.locations.values():
        #     for direction, block_data in l.blocks.items():
        #         # it is possible for two locations to have the same block, so
        #         # skip any that have already been instantiated
        #         if isinstance(block_data, blocks.Block):
        #             continue
        #         cls_type = block_map[block_data["_type"]]
        #         del block_data["_type"]
        #         # we will copy the properties of relevant items before we
        #         # install the block, so we can restore them after
        #         prop_map = {}
        #         # replace thing names in primitive with thing instances
        #         for param_name, param in block_data.items():
        #             if param in context.items:
        #                 param_instance = context.items[param]
        #             elif param in context.locations:
        #                 param_instance = context.locations[param]
        #             block_data[param_name] = param_instance
        #             prop_map[param_name] = param_instance.properties.copy()
        #         instance = cls_type.from_primitive(block_data)
        #         # restore properties found in primitive data
        #         for param_name, param in block_data.items():
        #             param.properties = prop_map[param_name]

        start_at = context.locations[data["start_at"]]
        player = context.characters[data["player"]]

        instance = cls(start_at, player, custom_actions=action_map.values())
        instance.turn = data.get("turn", 0)
        time_config = data.get("time_config")
        if time_config:
            instance.clock = GameClock.from_primitive(time_config)
        instance.game_history = data["game_history"]
        instance.game_over = data["game_over"]
        instance.game_over_description = data["game_over_description"]

        return instance

    def to_json(self):
        """
        Creates a JSON version of a game's primitive data.
        """
        data = self.to_primitive()
        data_json = json.dumps(data)
        return data_json

    @classmethod
    def from_json(cls, data_json, **kw):
        """
        Goes from JSON into actual game instances.
        """
        data = json.loads(data_json)
        instance = cls.from_primitive(data, **kw)
        return instance

    def save_game(self, filename):
        """
        Converts a game's state to JSON and then saves it to a file
        """
        save_data = self.to_json()
        with open(filename, "w") as f:
            f.write(save_data)

    @classmethod
    def load_game(cls, filename, **kw):
        """
        Reads a file with a game's state stored as JSON and converts it to a
        game instance.
        """
        with open(filename, "r") as f:
            save_data = f.read()
            return cls.from_json(save_data, **kw)
