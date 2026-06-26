"""Auto-generated game module for 'Flaming Goat'.

Source: Parsely Game File.pdf (pages 116-118).
Emitted by the ``text_adventure_games.codegen`` pipeline (since removed); this
file is now a static reference copy of what that emitter produced.
"""

from text_adventure_games import games, things, actions, blocks
from text_adventure_games.npc import make_hybrid_behavior


class FlamingGoat(games.Game):
    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)

    def is_won(self) -> bool:
        if self.game_over:
            return True
        if self.player.location.name == "Top of Escalator":
            self.game_over = True
            self.game_over_description = "You are standing at the top of a broken escalator. You may now resume your daily commute. What was up with that goat, eh? THE END. You win 1,000 points!"
            self.parser.ok(
                "You are standing at the top of a broken escalator. You may now resume your daily commute. What was up with that goat, eh? THE END. You win 1,000 points!"
            )
            return True
        return False


# ---- Custom Actions ----


class Shake_Machine(actions.Action):
    ACTION_NAME = "shake machine"
    ACTION_DESCRIPTION = "Transform: shake machine"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "soda", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no soda here."):
            return False
        if self.item.get_property("is_dispensed"):
            self.parser.fail(f"The soda is already dispensed.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"You jolt the vending machine. A can of soda drops out of the machine."
        )
        self.item.set_property("is_dispensed", True)
        self.item.set_property("gettable", True)


class Punch_Machine(actions.Action):
    ACTION_NAME = "punch machine"
    ACTION_DESCRIPTION = "Transform: punch machine"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "soda", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no soda here."):
            return False
        if self.item.get_property("is_dispensed"):
            self.parser.fail(f"The soda is already dispensed.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"You jolt the vending machine. A can of soda drops out of the machine."
        )
        self.item.set_property("is_dispensed", True)
        self.item.set_property("gettable", True)


class Kick_Machine(actions.Action):
    ACTION_NAME = "kick machine"
    ACTION_DESCRIPTION = "Transform: kick machine"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "soda", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no soda here."):
            return False
        if self.item.get_property("is_dispensed"):
            self.parser.fail(f"The soda is already dispensed.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"You jolt the vending machine. A can of soda drops out of the machine."
        )
        self.item.set_property("is_dispensed", True)
        self.item.set_property("gettable", True)


class Open_Soda(actions.Action):
    ACTION_NAME = "open soda"
    ACTION_DESCRIPTION = "Transform: open soda"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "soda", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no soda here."):
            return False
        if not self.is_in_inventory(self.character, self.item):
            return False
        if self.item.get_property("is_open"):
            self.parser.fail(f"The soda is already open.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f'You pop the top of the can. It lets out a pleasant "hssssss..."'
        )
        self.item.set_property("is_open", True)


class Pour_Soda_On_Goat(actions.Action):
    ACTION_NAME = "pour soda on goat"
    ACTION_DESCRIPTION = "Transform: pour soda on goat"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "goat", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no goat here."):
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"The flames are extinguished. The goat is no longer angry, but it remains hungry."
        )
        self.item.set_property("is_flaming", False)


class Feed_Goat(actions.Action):
    ACTION_NAME = "feed goat"
    ACTION_DESCRIPTION = "Transform: feed goat"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "goat", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no goat here."):
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"The soda can is now empty. The goat bites the can and wanders off with it, chewing noisily."
        )
        self.item.set_property("is_hungry", False)


# ---- Custom Blocks ----


class Goat_Block(blocks.Block):
    """Auto-generated property block (target='item'='goat')."""

    def __init__(self, location, obstacle):
        super().__init__(
            "Your way is blocked",
            "A flaming goat stands in the way. The goat is on fire. It looks angry and hungry.",
        )
        self.location = location
        self.obstacle = obstacle

    def is_blocked(self) -> bool:
        if not self.obstacle:
            return False
        if self.obstacle.name not in self.location.items:
            return False
        if not (self.obstacle.get_property("is_hungry")):
            return False
        return True


# ---- build_game ----


def build_game(llm_client=None) -> FlamingGoat:
    subway_platform = things.Location(
        "Subway Platform",
        "You are standing all alone on a subway platform. A vending machine is here. There is an UP escalator here.",
    )
    midway_escalator = things.Location(
        "Midway Escalator",
        "You are standing midway up a broken escalator. A flaming goat blocks your path. The escalator continues to not work.",
    )
    top_of_escalator = things.Location(
        "Top of Escalator",
        "You are standing at the top of a broken escalator. You may now resume your daily commute. What was up with that goat, eh?",
    )

    subway_platform.add_connection(
        "walk",
        midway_escalator,
        "You step onto the bottom step and are surprised to find that you go nowhere. The escalator is broken. Now it is just stairs. You trudge upward.",
    )
    midway_escalator.add_connection(
        "walk", top_of_escalator, "You make it to the top of the broken escalator."
    )

    machine = things.Item(
        "machine",
        "a battered and abused vending machine, apparently without power",
        "The battered and abused machine appears to be without power.",
    )
    machine.set_property("gettable", False)
    machine.add_command_hint("shake machine")
    machine.add_command_hint("punch machine")
    machine.add_command_hint("kick machine")
    subway_platform.add_item(machine)
    soda = things.Item(
        "soda",
        "a warm, unopened can of soda dusted with an acceptable amount of rat and insect droppings",
        "A warm, unopened can of soda. It's dusted with an acceptable amount of rat and insect droppings.",
    )
    soda.set_property("is_open", False)
    soda.set_property("is_dispensed", False)
    soda.set_property("gettable", False)
    soda.add_command_hint("examine soda")
    soda.add_command_hint("open soda")
    soda.add_command_hint("pour soda on goat")
    subway_platform.add_item(soda)
    escalator = things.Item(
        "escalator",
        "a broken escalator that is now just stairs",
        "The escalator is broken. Now it is just stairs.",
    )
    escalator.set_property("gettable", False)
    subway_platform.add_item(escalator)
    goat = things.Item(
        "goat",
        "a flaming goat. It looks angry and hungry.",
        "The goat is on fire. It looks angry and hungry.",
    )
    goat.set_property("gettable", False)
    goat.set_property("is_hungry", True)
    goat.add_command_hint("examine goat")
    goat.add_command_hint("pour soda on goat")
    goat.add_command_hint("feed goat")
    midway_escalator.add_item(goat)

    player = things.Character(
        name="Commuter",
        description="A subway commuter whose routine has been interrupted by a weird event.",
        persona="Just another day in the big city.",
    )
    player.set_property("character_type", "human")

    goat_block = Goat_Block(midway_escalator, goat)
    midway_escalator.add_block("walk", goat_block)

    characters = []

    custom_actions = [
        Shake_Machine,
        Punch_Machine,
        Kick_Machine,
        Open_Soda,
        Pour_Soda_On_Goat,
        Feed_Goat,
    ]

    return FlamingGoat(subway_platform, player, characters, custom_actions)


if __name__ == "__main__":
    build_game().game_loop()
