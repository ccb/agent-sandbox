"""Auto-generated game module for 'Action Castle'.

Source: ActionCastle.pdf (pages 15-28).
Emitted by the ``text_adventure_games.codegen`` pipeline (since removed); this
file is now a static reference copy of what that emitter produced.
"""

from text_adventure_games import games, things, actions, blocks
from text_adventure_games.npc import make_hybrid_behavior


class ActionCastle(games.Game):
    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)

    def is_won(self) -> bool:
        if self.game_over:
            return True
        for name, character in self.characters.items():
            if character.get_property("is_reigning") == True:
                msg = "You are now the new ruler of Action Castle! THE END.".format(
                    name=character.name.title()
                )
                self.game_over = True
                self.game_over_description = msg
                self.parser.ok(msg)
                return True
        return False


# ---- Custom Actions ----


class Read_Runes(actions.Action):
    ACTION_NAME = "read runes"
    ACTION_DESCRIPTION = "Read the inscription on the candle"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.inscribed = self.parser.match_item(
            "candle", self.parser.get_items_in_scope(self.character)
        )
        self.target = self.parser.get_character("ghost")

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.inscribed, "You don't see anything to read here."):
            return False
        if not self.is_in_inventory(self.character, self.inscribed):
            return False
        if not self.was_matched(
            self.target,
            "The inscription is a banishment spell, but there is nothing to banish here.",
        ):
            return False
        if not self.at(
            self.target,
            self.character.location,
            "The inscription is a banishment spell, but there is nothing to banish here.",
        ):
            return False
        if not self.has_property(
            self.inscribed,
            "is_lit",
            "Nothing happens. Perhaps the candle needs to be lit?",
        ):
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"{self.character.name.capitalize()} reads the inscription on the candle."
        )

        # Drop target's inventory before removing them from the scene.
        items = list(self.target.inventory.keys())
        for item_name in items:
            item = self.target.inventory[item_name]
            drop = actions.Drop(self.game, f"{self.target.name} drops {item.name}")
            if drop.check_preconditions():
                drop.apply_effects()

        self.target.set_property("is_banished", True)
        self.parser.ok(f"{self.target.name} is banished.")
        if self.target.location is not None:
            self.target.location.remove_character(self.target)


class Sit_Throne(actions.Action):
    ACTION_NAME = "sit on throne"
    ACTION_DESCRIPTION = "Sit on the throne"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.furniture = self.parser.match_item(
            "throne", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No character was matched."):
            return False
        if not self.was_matched(self.furniture, "The throne couldn't be found."):
            return False
        if not self.at(
            self.furniture, self.character.location, "The throne isn't here."
        ):
            return False
        if not self.has_property(
            self.character,
            "is_crowned",
            "You must be crowned to sit on the throne.",
        ):
            return False
        return True

    def apply_effects(self):
        self.character.set_property("is_reigning", True)
        self.parser.ok(f"{self.character.name.title()} sits on the throne.")


class Wear_Crown(actions.Action):
    ACTION_NAME = "wear crown"
    ACTION_DESCRIPTION = "Put on the crown"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "crown", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "I don't see it."):
            return False
        if not self.is_in_inventory(self.character, self.item):
            return False
        if not self.has_property(
            self.character, "is_royal", "You must be royal to wear the crown."
        ):
            return False
        return True

    def apply_effects(self):
        self.character.set_property("is_crowned", True)
        self.parser.ok(f"{self.character.name.capitalize()} dons the crown.")


class Propose_To_Princess(actions.Action):
    ACTION_NAME = "propose"
    ACTION_DESCRIPTION = "Propose marriage to someone"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        words = ["propose", "marry"]
        self.proposer = self.acting_character(
            command, hint="proposer", split_words=words, position="before"
        )
        self.propositioned = self.parser.get_character(
            command,
            hint="propositioned",
            split_words=words,
            position="after",
            exclude=self.proposer,
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.proposer, "They aren't here."):
            return False
        if not self.was_matched(self.propositioned, "They aren't here."):
            return False
        if self.proposer == self.propositioned:
            self.parser.fail(f"{self.proposer.name} cannot marry themself")
            return False
        if not self.at(
            self.propositioned,
            self.proposer.location,
            f"{self.propositioned.name} and {self.proposer.name} aren't in the same location.",
        ):
            return False
        if not self.property_equals(self.proposer, "emotional_state", "happy"):
            return False
        if not self.property_equals(self.propositioned, "emotional_state", "happy"):
            return False
        if self.has_property(
            self.proposer,
            "is_married",
            f"{self.proposer.name} is already married",
            display_message_upon=True,
        ):
            return False
        if self.has_property(
            self.propositioned,
            "is_married",
            f"{self.propositioned.name} is already married",
            display_message_upon=True,
        ):
            return False
        return True

    def apply_effects(self):
        self.parser.ok(f"{self.propositioned.name.capitalize()} says YES!")
        self.proposer.set_property("is_married", True)
        self.propositioned.set_property("is_married", True)
        self.parser.ok(
            f"{self.propositioned.name} and {self.proposer.name} are now married."
        )
        if self.proposer.get_property("is_royal") or self.propositioned.get_property(
            "is_royal"
        ):
            self.proposer.set_property("is_royal", True)
            self.propositioned.set_property("is_royal", True)


class Unlock_Door(actions.Action):
    ACTION_NAME = "unlock door"
    ACTION_DESCRIPTION = "Unlock a door with a key"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.key = self.parser.match_item(
            "key", self.parser.get_items_in_scope(self.character)
        )
        self.lock = self.parser.match_item(
            "door", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.lock, "There's no door here."):
            return False
        if not self.loc_has_item(self.character.location, self.lock):
            return False
        if not self.has_property(self.lock, "is_locked", "The door is not locked."):
            return False
        if not self.was_matched(
            self.key, f"{self.character.name} does not have the key."
        ):
            return False
        if not self.is_in_inventory(self.character, self.key):
            return False
        return True

    def apply_effects(self):
        self.lock.set_property("is_locked", False)
        self.parser.ok(f"{self.character.name} unlocked the door.")


class Troll_Growl(actions.Action):
    ACTION_NAME = "troll growl"
    ACTION_DESCRIPTION = "NPC taunt: troll growl"
    ACTION_ALIASES = []
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words="troll growl".split("|"), position="before"
        )
        self.target = self.parser.get_character(
            command,
            split_words=["troll growl"],
            position="after",
            exclude=self.character,
        )

    def check_preconditions(self) -> bool:
        if not self.at(self.character, self.target.location):
            return False
        if self.character.get_property("is_dead"):
            self.parser.fail(f"{self.character.name} has been banished.")
            return False
        return True

    def apply_effects(self):
        description = f"{self.character.name.capitalize()} growls menacingly at {self.target.name}."
        self.parser.npc_ok(description)


class Troll_Threaten(actions.Action):
    ACTION_NAME = "troll threaten"
    ACTION_DESCRIPTION = "NPC taunt: troll threaten"
    ACTION_ALIASES = []
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words="troll threaten".split("|"), position="before"
        )
        self.target = self.parser.get_character(
            command,
            split_words=["troll threaten"],
            position="after",
            exclude=self.character,
        )

    def check_preconditions(self) -> bool:
        if not self.at(self.character, self.target.location):
            return False
        if self.character.get_property("is_dead"):
            self.parser.fail(f"{self.character.name} has been banished.")
            return False
        return True

    def apply_effects(self):
        description = f"{self.character.name.capitalize()} bares its teeth and threatens to rip {self.target.name} limb from limb!"
        self.parser.npc_ok(description)


class Troll_Attack(actions.Action):
    ACTION_NAME = "troll attack"
    ACTION_DESCRIPTION = "NPC kill: troll attack"
    ACTION_ALIASES = []
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words=["troll attack"], position="before"
        )
        self.target = self.parser.get_character(
            command,
            split_words=["troll attack"],
            position="after",
            exclude=self.character,
        )

    def check_preconditions(self) -> bool:
        if not self.at(self.character, self.target.location):
            return False
        if self.character.get_property("is_dead"):
            self.parser.fail(f"{self.character.name} has been banished.")
            return False
        return True

    def apply_effects(self):
        description = f"{self.character.name.capitalize()} rips {self.target.name} limb from limb! THE END."
        self.parser.npc_ok(description)
        self.target.set_property("is_dead", True)


class Guard_Warn(actions.Action):
    ACTION_NAME = "guard warn"
    ACTION_DESCRIPTION = "NPC taunt: guard warn"
    ACTION_ALIASES = []
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words="guard warn".split("|"), position="before"
        )

    def check_preconditions(self) -> bool:
        if self.character.get_property("is_unconscious"):
            self.parser.fail(f"{self.character.name} has been banished.")
            return False
        return True

    def apply_effects(self):
        description = f'{self.character.name.capitalize()} holds up a hand. "Halt! State your business!"'
        self.parser.npc_ok(description)


class Guard_Threaten(actions.Action):
    ACTION_NAME = "guard threaten"
    ACTION_DESCRIPTION = "NPC taunt: guard threaten"
    ACTION_ALIASES = []
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words="guard threaten".split("|"), position="before"
        )

    def check_preconditions(self) -> bool:
        if self.character.get_property("is_unconscious"):
            self.parser.fail(f"{self.character.name} has been banished.")
            return False
        return True

    def apply_effects(self):
        description = f'{self.character.name.capitalize()} draws his sword. "I warned you! Move along or face the consequences!"'
        self.parser.npc_ok(description)


class Guard_Attack(actions.Action):
    ACTION_NAME = "guard attack"
    ACTION_DESCRIPTION = "NPC kill: guard attack"
    ACTION_ALIASES = []
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words=["guard attack"], position="before"
        )
        self.target = self.parser.get_character(
            command,
            split_words=["guard attack"],
            position="after",
            exclude=self.character,
        )

    def check_preconditions(self) -> bool:
        if not self.at(self.character, self.target.location):
            return False
        if self.character.get_property("is_unconscious"):
            self.parser.fail(f"{self.character.name} has been banished.")
            return False
        return True

    def apply_effects(self):
        description = f"{self.character.name.capitalize()} strikes {self.target.name} down. THE END."
        self.parser.npc_ok(description)
        self.target.set_property("is_dead", True)


class Ghost_Drift(actions.Action):
    ACTION_NAME = "ghost drift"
    ACTION_DESCRIPTION = "NPC taunt: ghost drift"
    ACTION_ALIASES = []
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words="ghost drift".split("|"), position="before"
        )
        self.target = self.parser.get_character(
            command,
            split_words=["ghost drift"],
            position="after",
            exclude=self.character,
        )

    def check_preconditions(self) -> bool:
        if not self.at(self.character, self.target.location):
            return False
        if self.character.get_property("is_banished"):
            self.parser.fail(f"{self.character.name} has been banished.")
            return False
        return True

    def apply_effects(self):
        description = f"{self.character.name.capitalize()} drifts closer, its hollow eyes fixed on {self.target.name}."
        self.parser.npc_ok(description)


class Ghost_Loom(actions.Action):
    ACTION_NAME = "ghost loom"
    ACTION_DESCRIPTION = "NPC taunt: ghost loom"
    ACTION_ALIASES = []
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words="ghost loom".split("|"), position="before"
        )
        self.target = self.parser.get_character(
            command,
            split_words=["ghost loom"],
            position="after",
            exclude=self.character,
        )

    def check_preconditions(self) -> bool:
        if not self.at(self.character, self.target.location):
            return False
        if self.character.get_property("is_banished"):
            self.parser.fail(f"{self.character.name} has been banished.")
            return False
        return True

    def apply_effects(self):
        description = f"{self.character.name.capitalize()} looms over {self.target.name}, its bony fingers reaching out!"
        self.parser.npc_ok(description)


class Ghost_Drain(actions.Action):
    ACTION_NAME = "ghost drain"
    ACTION_DESCRIPTION = "NPC kill: ghost drain"
    ACTION_ALIASES = []
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words=["ghost drain"], position="before"
        )
        self.target = self.parser.get_character(
            command,
            split_words=["ghost drain"],
            position="after",
            exclude=self.character,
        )

    def check_preconditions(self) -> bool:
        if not self.at(self.character, self.target.location):
            return False
        if self.character.get_property("is_banished"):
            self.parser.fail(f"{self.character.name} has been banished.")
            return False
        return True

    def apply_effects(self):
        description = f"{self.character.name.capitalize()} reaches out a skeletal hand and drains {self.target.name}'s life force. THE END."
        self.parser.npc_ok(description)
        self.target.set_property("is_dead", True)


# ---- Custom Blocks ----


class Troll_Block(blocks.Block):
    """Auto-generated property block (target='character'='troll')."""

    def __init__(self, location, obstacle):
        super().__init__(
            "Your way is blocked", "The troll blocks your path across the bridge."
        )
        self.location = location
        self.obstacle = obstacle

    def is_blocked(self) -> bool:
        if not self.obstacle:
            return False
        if self.obstacle.location is not self.location:
            return False
        if not (not self.obstacle.get_property("is_dead")):
            return False
        if not (self.obstacle.get_property("is_hungry")):
            return False
        return True


class Guard_Block(blocks.Block):
    """Auto-generated property block (target='character'='guard')."""

    def __init__(self, location, obstacle):
        super().__init__(
            "Your way is blocked",
            "The guard blocks the eastern passage. You must get past him first.",
        )
        self.location = location
        self.obstacle = obstacle

    def is_blocked(self) -> bool:
        if not self.obstacle:
            return False
        if self.obstacle.location is not self.location:
            return False
        if not (not self.obstacle.get_property("is_dead")):
            return False
        if not (not self.obstacle.get_property("is_unconscious")):
            return False
        return True


class Door_Block(blocks.Block):
    """Auto-generated property block (target='item'='door')."""

    def __init__(self, location, obstacle):
        super().__init__(
            "Your way is blocked", "The door is locked. You need a key to unlock it."
        )
        self.location = location
        self.obstacle = obstacle

    def is_blocked(self) -> bool:
        if not self.obstacle:
            return False
        if self.obstacle.name not in self.location.items:
            return False
        if not (self.obstacle.get_property("is_locked")):
            return False
        return True


class Darkness_Block(blocks.Block):
    """Auto-generated darkness block: unblocks if any character carries an
    item with property 'is_lit'."""

    def __init__(self, location):
        super().__init__("Darkness blocks your way", "It's too dark to see!")
        self.location = location
        self.location.set_property("is_dark", True)

    def is_blocked(self) -> bool:
        if not self.location.get_property("is_dark"):
            return False
        for character in self.location.characters.values():
            for item in character.inventory.values():
                if item.get_property("is_lit"):
                    return False
        return True


# ---- NPC Behavior Factories ----


def make_troll_behavior():
    """Factory for the 'troll' character. Escalates over turns; state lives in a closure (matching the reference pattern)."""
    commands = [
        "troll troll growl {player}",
        "troll troll threaten {player}",
    ]
    fallback = "troll troll attack {player} with club"
    state = {"turns_present": 0}

    def behavior(character, game):
        player = game.player
        if player.location is not character.location:
            state["turns_present"] = 0
            return
        if character.get_property("is_hungry") != True:
            return
        state["turns_present"] += 1
        idx = state["turns_present"] - 1
        if idx >= len(commands):
            if fallback:
                game.parser.parse_command(
                    fallback.format(player=player.name),
                    actor=character,
                )
            return
        cmd = commands[idx].format(player=player.name)
        game.parser.parse_command(cmd, actor=character)

    return behavior


def make_guard_behavior():
    """Factory for the 'guard' character. Escalates over turns; state lives in a closure (matching the reference pattern)."""
    commands = [
        "guard guard warn {player}",
        "guard guard threaten {player}",
    ]
    fallback = "guard guard attack {player} with sword"
    state = {"turns_present": 0}

    def behavior(character, game):
        player = game.player
        if player.location is not character.location:
            state["turns_present"] = 0
            return
        if character.get_property("is_unconscious") != False:
            return
        state["turns_present"] += 1
        idx = state["turns_present"] - 1
        if idx >= len(commands):
            if fallback:
                game.parser.parse_command(
                    fallback.format(player=player.name),
                    actor=character,
                )
            return
        cmd = commands[idx].format(player=player.name)
        game.parser.parse_command(cmd, actor=character)

    return behavior


def make_ghost_behavior():
    """Factory for the 'ghost' character. Escalates over turns; state lives in a closure (matching the reference pattern)."""
    commands = [
        "ghost ghost drift {player}",
        "ghost ghost loom {player}",
    ]
    fallback = "ghost ghost drain {player}"
    state = {"turns_present": 0}

    def behavior(character, game):
        player = game.player
        if player.location is not character.location:
            state["turns_present"] = 0
            return
        if character.get_property("is_banished") != False:
            return
        state["turns_present"] += 1
        idx = state["turns_present"] - 1
        if idx >= len(commands):
            if fallback:
                game.parser.parse_command(
                    fallback.format(player=player.name),
                    actor=character,
                )
            return
        cmd = commands[idx].format(player=player.name)
        game.parser.parse_command(cmd, actor=character)

    return behavior


# ---- build_game ----


def build_game(llm_client=None) -> ActionCastle:
    cottage = things.Location(
        "Cottage",
        "You are standing in a small cottage. There is a fishing pole here. A door leads outside.",
    )
    garden_path = things.Location(
        "Garden Path",
        "You're on a lush garden path that leads north and south. There is a rosebush here. There is a cottage here.",
    )
    fish_pond = things.Location(
        "Fish Pond", "You are at the edge of a fish pond. A path leads north."
    )
    fish_pond.set_property("has_fish", True)
    winding_path = things.Location(
        "Winding Path",
        "You are walking along a winding path that leads south and east. There is a tall tree here.",
    )
    treetop = things.Location(
        "Treetop",
        "You are at the top of a tall tree. There is a stout dead branch here. From your perch you can see the tower of Action Castle.",
    )
    dead = things.Location(
        "Dead", "You leap from the tree and do not survive the fall. THE END."
    )
    dead.set_property("game_over", True)
    drawbridge = things.Location(
        "Drawbridge",
        "You come to the drawbridge of Action Castle. There is a mean troll guarding the bridge.",
    )
    courtyard = things.Location(
        "Courtyard",
        "You are in the courtyard of Action Castle. A castle guard stands watch to the east. Stairs lead up into the tower and down into darkness.",
    )
    tower_stairs = things.Location(
        "Tower Stairs", "You climb the tower stairs until you come to a door."
    )
    tower = things.Location(
        "Tower", "You are in the tower. There is a princess here. Stairs lead down."
    )
    dungeon_stairs = things.Location(
        "Dungeon Stairs", "You are on the dungeon stairs. It's very dark here."
    )
    dungeon_stairs.set_property("is_dark", True)
    dungeon = things.Location(
        "Dungeon",
        "You are in the dungeon. There is a spooky ghost here. Stairs lead up.",
    )
    great_feasting_hall = things.Location(
        "Great Feasting Hall",
        "You stand inside the great feasting hall. There is a strange candle here. Exits are to the east and west.",
    )
    throne_room = things.Location(
        "Throne Room",
        "This is the throne room of Action Castle. There is an ornate gold throne here.",
    )

    cottage.add_connection("out", garden_path, "You step outside onto the garden path.")
    garden_path.add_connection(
        "north", winding_path, "You walk north along the winding path."
    )
    garden_path.add_connection(
        "south", fish_pond, "You head south toward the fish pond."
    )
    winding_path.add_connection(
        "east", drawbridge, "You head east toward the drawbridge of Action Castle."
    )
    winding_path.add_connection(
        "climb up tree", treetop, "You climb up the tree -- it takes a long time."
    )
    treetop.add_connection("jump", dead, "You leap from the treetop.")
    drawbridge.add_connection(
        "east", courtyard, "You cross the drawbridge and enter the courtyard."
    )
    courtyard.add_connection(
        "east", great_feasting_hall, "You enter the great feasting hall."
    )
    courtyard.add_connection(
        "up", tower_stairs, "You climb the stairs up toward the tower."
    )
    courtyard.add_connection(
        "down", dungeon_stairs, "You descend the stairs into darkness."
    )
    tower_stairs.add_connection(
        "up", tower, "You push through the unlocked door and climb up to the tower."
    )
    dungeon_stairs.add_connection("down", dungeon, "You descend into the dungeon.")
    great_feasting_hall.add_connection(
        "east", throne_room, "You enter the throne room."
    )

    pole = things.Item(
        "pole", "a simple fishing pole", "You see a simple fishing pole."
    )
    pole.add_command_hint("catch fish with pole")
    cottage.add_item(pole)
    rosebush = things.Item(
        "rosebush", "a rosebush with a single red rose", "You find a single red rose."
    )
    rosebush.set_property("gettable", False)
    rosebush.set_property("has_rose", True)
    rosebush.add_command_hint("pick rose")
    rosebush.add_command_hint("smell rose")
    garden_path.add_item(rosebush)
    pond = things.Item("pond", "a fish pond", "A calm pond teeming with fish.")
    pond.set_property("gettable", False)
    pond.set_property("has_fish", True)
    pond.add_command_hint("catch fish")
    pond.add_command_hint("catch fish with pole")
    fish_pond.add_item(pond)
    branch = things.Item(
        "branch", "a stout dead branch", "You think it would make a good club."
    )
    branch.set_property("is_weapon", True)
    branch.set_property("is_fragile", True)
    branch.add_command_hint("get branch")
    branch.add_command_hint("attack guard with branch")
    treetop.add_item(branch)
    door = things.Item(
        "door", "a locked door at the top of the tower stairs", "The door is locked."
    )
    door.set_property("gettable", False)
    door.set_property("is_locked", True)
    door.set_property("is_openable", True)
    door.add_command_hint("unlock door")
    tower_stairs.add_item(door)
    candle = things.Item(
        "candle",
        "a strange candle covered in mysterious runes",
        "You see that the strange candle is covered in mysterious runes.",
    )
    candle.set_property("flammable", True)
    candle.set_property("is_lit", False)
    candle.add_command_hint("light candle")
    candle.add_command_hint("read runes")
    candle.read_text = (
        "The odd runes are part of an exorcism ritual used to dispel evil spirits."
    )
    great_feasting_hall.add_item(candle)
    throne = things.Item(
        "throne", "an ornate gold throne", "You see an ornate gold throne."
    )
    throne.set_property("gettable", False)
    throne.add_command_hint("sit on throne")
    throne_room.add_item(throne)

    troll = things.Character(
        name="troll",
        description="a mean troll with a warty green hide",
        persona="I am a hungry troll. I guard this bridge and will not let anyone pass.",
    )
    troll.set_property("is_hungry", True)
    troll.set_property("character_type", "troll")
    troll.set_property("is_invulerable", True)
    club = things.Item(
        "club", "a heavy wooden club", "A heavy wooden club studded with iron."
    )
    club.set_property("is_weapon", True)
    troll.add_to_inventory(club)
    drawbridge.add_character(troll)
    troll.add_give_response(
        item="fish",
        response_text="The troll snatches the fish and runs off to eat its prize! The bridge is clear.",
        requires_recipient_properties={"is_hungry": True},
        sets_recipient_properties={"is_hungry": False, "is_dead": True},
    )
    troll.set_greeting("The troll snarls at you.")

    guard = things.Character(
        name="guard",
        description="a castle guard in chainmail armor with no helmet",
        persona="I guard the eastern passage. A key hangs from my belt.",
    )
    guard.set_property("is_unconscious", False)
    guard.set_property("character_type", "human")
    guard.set_property("emotional_state", "suspicious")
    key = things.Item(
        "key", "a key hanging from the guard's belt", "A sturdy iron key."
    )
    key.add_command_hint("get key")
    key.add_command_hint("unlock door")
    guard.add_to_inventory(key)
    sword = things.Item("sword", "a sharp iron sword", "A sharp iron sword.")
    sword.set_property("is_weapon", True)
    guard.add_to_inventory(sword)
    courtyard.add_character(guard)
    guard.set_greeting("The guard eyes you suspiciously.")

    ghost = things.Character(
        name="ghost",
        description="a spooky ghost with bony, claw-like fingers wearing a gold crown",
        persona="I am the restless spirit of the king. I haunt this dungeon.",
    )
    ghost.set_property("is_banished", False)
    ghost.set_property("character_type", "ghost")
    ghost.set_property("is_invulerable", True)
    crown = things.Item(
        "crown",
        "a gold crown that once belonged to the king of Action Castle",
        "You see the gold crown that once belonged to the king of Action Castle.",
    )
    crown.set_property("wearable", True)
    crown.add_command_hint("get crown")
    crown.add_command_hint("wear crown")
    ghost.add_to_inventory(crown)
    dungeon.add_character(ghost)

    princess = things.Character(
        name="princess",
        description="a beautiful, sad and lonely princess",
        persona="I am the princess of Action Castle. I am sad and lonely in this tower.",
    )
    princess.set_property("is_royal", True)
    princess.set_property("emotional_state", "sad")
    princess.set_property("character_type", "human")
    tower.add_character(princess)
    princess.add_give_response(
        item="rose",
        response_text="The princess smiles warmly as she accepts the rose. She seems to warm up to you.",
        sets_recipient_properties={"emotional_state": "happy"},
        sets_giver_properties={"emotional_state": "happy"},
    )
    princess.add_give_response(
        item="crown",
        response_text='"My father\'s crown! You have put his soul to rest and may now take his place as ruler of this land!" She places the crown on your head.',
        requires_recipient_properties={"emotional_state": "happy"},
        sets_giver_properties={"is_crowned": True, "is_royal": True},
    )
    princess.set_greeting("The princess looks at you sadly.")
    princess.add_dialogue(
        "ghost",
        "The guards whisper that the ghost of the king haunts the dungeons as a restless spirit!",
    )
    princess.add_dialogue("crown", "My father's crown was lost after he died.")
    princess.add_dialogue("tower", "I cannot leave the tower until I'm wed!")
    princess.add_dialogue(
        "throne", "Only the rightful ruler of Action Castle may claim the throne!"
    )

    player = things.Character(
        name="The player",
        description="A brave adventurer seeking to claim the throne of Action Castle.",
        persona="I am an adventurer exploring Action Castle.",
    )
    player.set_property("character_type", "human")
    player.set_property("emotional_state", "neutral")
    player.set_property("is_royal", False)
    player.set_property("is_crowned", False)
    player.set_property("is_reigning", False)
    player.set_property("is_married", False)
    lamp = things.Item(
        "lamp", "an old lamp", "You see an old lamp; it's currently unlit."
    )
    lamp.set_property("flammable", True)
    lamp.set_property("is_lit", False)
    lamp.add_command_hint("light lamp")
    player.add_to_inventory(lamp)

    if llm_client:
        troll.set_behavior(make_hybrid_behavior(llm_client, make_troll_behavior()))
        guard.set_behavior(make_hybrid_behavior(llm_client, make_guard_behavior()))
        ghost.set_behavior(make_hybrid_behavior(llm_client, make_ghost_behavior()))
    else:
        troll.set_behavior(make_troll_behavior())
        guard.set_behavior(make_guard_behavior())
        ghost.set_behavior(make_ghost_behavior())

    troll_block = Troll_Block(drawbridge, troll)
    drawbridge.add_block("east", troll_block)
    guard_block = Guard_Block(courtyard, guard)
    courtyard.add_block("east", guard_block)
    door_block = Door_Block(tower_stairs, door)
    tower_stairs.add_block("up", door_block)
    darkness_block = Darkness_Block(dungeon_stairs)
    dungeon_stairs.add_block("down", darkness_block)

    characters = [
        troll,
        guard,
        ghost,
        princess,
    ]

    custom_actions = [
        Read_Runes,
        Sit_Throne,
        Wear_Crown,
        Propose_To_Princess,
        Unlock_Door,
        Troll_Growl,
        Troll_Threaten,
        Troll_Attack,
        Guard_Warn,
        Guard_Threaten,
        Guard_Attack,
        Ghost_Drift,
        Ghost_Loom,
        Ghost_Drain,
    ]

    return ActionCastle(cottage, player, characters, custom_actions)


if __name__ == "__main__":
    build_game().game_loop()
