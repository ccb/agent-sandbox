"""Auto-generated game module for 'Jungle Adventure'.

Source: JungleAdventure.pdf (pages 119-138).
Emitted by the ``text_adventure_games.codegen`` pipeline (since removed); this
file is now a static reference copy of what that emitter produced.
"""

from text_adventure_games import games, things, actions, blocks
from text_adventure_games.npc import make_hybrid_behavior


class JungleAdventure(games.Game):
    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)

    def is_won(self) -> bool:
        if self.game_over:
            return True
        for name, character in self.characters.items():
            if character.get_property("is_rescued") == True:
                msg = "Jim lifts off above the jungle canopy and heads for home. Your Jungle Adventure is over… for now!".format(
                    name=character.name.title()
                )
                self.game_over = True
                self.game_over_description = msg
                self.parser.ok(msg)
                return True
        return False


# ---- Custom Actions ----


class Unbuckle_Seatbelt(actions.Action):
    ACTION_NAME = "unbuckle seatbelt"
    ACTION_DESCRIPTION = "Transform: unbuckle seatbelt"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "seatbelt", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no seatbelt here."):
            return False
        if not self.has_property(
            self.item, "is_buckled", f"The seatbelt is not buckled yet."
        ):
            return False
        return True

    def apply_effects(self):
        self.parser.ok(f"You unbuckle the seatbelt. You are free to leave the plane.")
        self.item.set_property("is_buckled", False)


class Search_Wreckage(actions.Action):
    ACTION_NAME = "search wreckage"
    ACTION_DESCRIPTION = "Transform: search wreckage"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "wreckage", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no wreckage here."):
            return False
        if self.item.get_property("is_searched"):
            self.parser.fail(f"The wreckage is already searched.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(f"You rummage through the smoking wreckage and find a rifle!")
        self.item.set_property("is_searched", True)


class Cook_Egg(actions.Action):
    ACTION_NAME = "cook egg"
    ACTION_DESCRIPTION = "Transform: cook egg"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "egg", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no egg here."):
            return False
        if not self.is_in_inventory(self.character, self.item):
            return False
        if self.item.get_property("is_cooked"):
            self.parser.fail(f"The egg is already cooked.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"You hold the egg over the cooking fire. It sizzles and cooks to perfection."
        )
        self.item.set_property("is_cooked", True)


class Wear_Necklace(actions.Action):
    ACTION_NAME = "wear necklace"
    ACTION_DESCRIPTION = "Transform: wear necklace"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "necklace", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no necklace here."):
            return False
        if not self.is_in_inventory(self.character, self.item):
            return False
        if self.item.get_property("is_worn"):
            self.parser.fail(f"The necklace is already worn.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"You feel as light and as free as a bird! Your feet don't even leave tracks in the dirt."
        )
        self.item.set_property("is_worn", True)


class Put_Bones_On_Altar(actions.Action):
    ACTION_NAME = "put bones on altar"
    ACTION_DESCRIPTION = "Transform: put bones on altar"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "altar", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no altar here."):
            return False
        if self.item.get_property("is_activated"):
            self.parser.fail(f"The altar is already activated.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"You place the old bones in the shallow depression on the altar. With a deep rumble, the altar slides to one side, revealing a secret tunnel that leads south."
        )
        self.item.set_property("is_activated", True)


class Get_Monkey(actions.Action):
    ACTION_NAME = "get monkey"
    ACTION_DESCRIPTION = "Flavor response: get monkey"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Treasure Chamber":
            self.parser.fail("Nothing happens.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"The monkey is slow and lethargic from the egg. You scoop it up and stow it in your pack."
        )


class Land_Helicopter(actions.Action):
    ACTION_NAME = "signal helicopter"
    ACTION_DESCRIPTION = "Transform: signal helicopter"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "helicopter", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no helicopter here."):
            return False
        if self.item.get_property("is_landed"):
            self.parser.fail(f"The helicopter is already landed.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"The helicopter spots your signal fire and begins to descend toward the plateau!"
        )
        self.item.set_property("is_landed", True)


class Enter_Helicopter(actions.Action):
    ACTION_NAME = "enter helicopter"
    ACTION_DESCRIPTION = "Flavor response: enter helicopter"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Rocky Plateau":
            self.parser.fail("Nothing happens.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"You climb into the helicopter. Jim grins and lifts off, rising high above the jungle canopy and heading for home. Your Jungle Adventure is over… for now!"
        )


class Tiger_Growl(actions.Action):
    ACTION_NAME = "tiger growl"
    ACTION_DESCRIPTION = "NPC taunt: tiger growl"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words="tiger growl".split("|"), position="before"
        )

    def check_preconditions(self) -> bool:
        if self.character.get_property("is_dead"):
            self.parser.fail(f"{self.character.name} has been banished.")
            return False
        return True

    def apply_effects(self):
        description = (
            f"{self.character.name.capitalize()} growls menacingly from the shadows."
        )
        self.parser.npc_ok(description)


class Tiger_Maul(actions.Action):
    ACTION_NAME = "tiger maul"
    ACTION_DESCRIPTION = "NPC kill: tiger maul"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True
    NPC_ONLY = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(
            command, split_words=["tiger maul"], position="before"
        )
        self.target = self.parser.get_character(
            command,
            split_words=["tiger maul"],
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
        description = f"{self.character.name.capitalize()} leaps from the shadows and mauls {self.target.name}. THE END."
        self.parser.npc_ok(description)
        self.target.set_property("is_dead", True)


class Examine_Compass_Action(actions.Action):
    ACTION_NAME = "examine compass"
    ACTION_DESCRIPTION = "Flavor response: examine compass"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.scope_item = self.parser.match_item(
            "compass",
            self.parser.get_items_in_scope(self.character),
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.scope_item, "There's no compass here."):
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"The brass compass points north. In the deep jungle, the true exits are: from the southwestern area go north, east, or west back to the crash site; from the southeastern area go north, south to the Village, or east to the Gorge."
        )


class Light_Bush(actions.Action):
    ACTION_NAME = "light bush"
    ACTION_DESCRIPTION = "Transform: light bush"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "bush", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no bush here."):
            return False
        if self.item.get_property("is_burning"):
            self.parser.fail(f"The bush is already burning.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"You flick the lighter and touch it to the dry bush. Dense smoke billows up into the sky… A helicopter will land after a few turns."
        )
        self.item.set_property("is_burning", True)


class Land_Helicopter_After_Fire(actions.Action):
    ACTION_NAME = "wait for helicopter"
    ACTION_DESCRIPTION = "Transform: wait for helicopter"
    ACTION_ALIASES = []
    PLAYER_CUSTOM = True

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.item = self.parser.match_item(
            "helicopter", self.parser.get_items_in_scope(self.character)
        )

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.item, "There's no helicopter here."):
            return False
        if self.item.get_property("is_landed"):
            self.parser.fail(f"The helicopter is already landed.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            f"The helicopter spots the smoke and descends to the plateau. Jim waves from the cockpit!"
        )
        self.item.set_property("is_landed", True)


# ---- Custom Blocks ----


class Seatbelt_Block(blocks.Block):
    """Auto-generated property block (target='item'='seatbelt')."""

    def __init__(self, location, obstacle):
        super().__init__(
            "Your way is blocked",
            "You're still buckled into your seat. You need to unbuckle first.",
        )
        self.location = location
        self.obstacle = obstacle

    def is_blocked(self, actor=None) -> bool:
        if not self.obstacle:
            return False
        if self.obstacle.name not in self.location.items:
            return False
        if not (self.obstacle.get_property("is_buckled")):
            return False
        return True


class Cave_Block(blocks.Block):
    """Auto-generated property block (target='character'='tiger')."""

    def __init__(self, location, obstacle):
        super().__init__(
            "Your way is blocked",
            "As you step into the cave, a huge tiger leaps from the shadows and pounces on you… With a savage sweep of its claws, the tiger quickly disembowels you. THE END.",
        )
        self.location = location
        self.obstacle = obstacle

    def is_blocked(self, actor=None) -> bool:
        if not self.obstacle:
            return False
        if self.obstacle.location is not self.location:
            return False
        if not (not self.obstacle.get_property("is_dead")):
            return False
        if not ((actor is None or not actor.get_property("has_spear"))):
            return False
        return True


class Bridge_Block(blocks.Block):
    """Auto-generated property block (target='item'='bridge')."""

    def __init__(self, location, obstacle):
        super().__init__(
            "Your way is blocked",
            "The rope bridge buckles under your weight and tears free from its supports. You plunge 100 feet into the river and end up as crocodile food. THE END.",
        )
        self.location = location
        self.obstacle = obstacle

    def is_blocked(self, actor=None) -> bool:
        if not self.obstacle:
            return False
        if self.obstacle.name not in self.location.items:
            return False
        if not ((actor is None or not actor.get_property("is_wearing_necklace"))):
            return False
        return True


class Altar_Block(blocks.Block):
    """Auto-generated property block (target='item'='altar')."""

    def __init__(self, location, obstacle):
        super().__init__(
            "Your way is blocked",
            "The altar blocks the way south. Perhaps something should be placed on it.",
        )
        self.location = location
        self.obstacle = obstacle

    def is_blocked(self, actor=None) -> bool:
        if not self.obstacle:
            return False
        if self.obstacle.name not in self.location.items:
            return False
        if not (not self.obstacle.get_property("is_activated")):
            return False
        return True


class Helicopter_Block(blocks.Block):
    """Auto-generated property block (target='item'='helicopter')."""

    def __init__(self, location, obstacle):
        super().__init__(
            "Your way is blocked",
            "The helicopter hasn't landed yet. You need to signal it first by lighting a fire.",
        )
        self.location = location
        self.obstacle = obstacle

    def is_blocked(self, actor=None) -> bool:
        if not self.obstacle:
            return False
        if self.obstacle.name not in self.location.items:
            return False
        if not (not self.obstacle.get_property("is_landed")):
            return False
        return True


# ---- NPC Behavior Factories ----


def make_tiger_behavior():
    """Factory for the 'tiger' character. Escalates over turns; state lives in a closure (matching the reference pattern)."""
    commands = [
        "tiger tiger growl {player}",
    ]
    fallback = "tiger tiger maul {player}"
    state = {"turns_present": 0}

    def behavior(character, game):
        player = game.player
        if player.location is not character.location:
            state["turns_present"] = 0
            return
        if character.get_property("is_dead") != False:
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


def build_game(llm_client=None) -> JungleAdventure:
    crashed_plane = things.Location(
        "Crashed Plane",
        "You wake up to find yourself buckled into the pilot's chair of a single-engine prop plane. Through the cockpit window you can see the deep jungle. There is a backpack here.",
    )
    edge_of_the_deep_jungle = things.Location(
        "Edge of the Deep Jungle",
        "You stand in a clearing, the site of a terrible plane crash. The crash site is surrounded by smoking wreckage and inhospitable jungle.",
    )
    deep_jungle = things.Location(
        "Deep Jungle",
        "You are lost in the deep jungle. The trees press in on all sides. You can go north, south, east, or west, but without a compass you may end up going in circles.",
    )
    village = things.Location(
        "Village",
        "You enter a village. There is a cooking fire here. There are three huts here. A path leads west, and the deep jungle is to the north.",
    )
    warriors_hut = things.Location(
        "Warriors Hut",
        "You enter the warriors' hut. The warriors scowl at you and mutter to themselves, brandishing their weapons.",
    )
    womens_hut = things.Location(
        "Womens Hut",
        "You enter the women's hut. The women of the village greet you warmly and present you with a beaded skirt.",
    )
    witch_doctors_hut = things.Location(
        "Witch Doctors Hut",
        "You enter the witch doctor's hut. The village witch doctor is here.",
    )
    jungle_path = things.Location(
        "Jungle Path",
        "You are on a jungle path that heads east–west. There is a bird's nest here.",
    )
    outside_the_dark_cave = things.Location(
        "Outside the Dark Cave",
        "You stand outside a dark cave. You hear the growls of a large animal from within.",
    )
    inside_the_dark_cave = things.Location(
        "Inside the Dark Cave",
        "You are inside a dark cave. It smells of tiger and death. There is a fresh tiger carcass here next to some old bones.",
    )
    the_gorge = things.Location(
        "The Gorge",
        "You stand on the western edge of a vast, deep gorge. There's an old rope bridge here. A trail leads south.",
    )
    cool_pool = things.Location(
        "Cool Pool",
        "You've arrived at the cool pool. It's surrounded on all sides by swaying palm trees.",
    )
    temple_of_the_gold_skull = things.Location(
        "Temple of the Gold Skull",
        "You stand outside the ruins of a magnificent temple. This is the mythical Temple of the Gold Skull! There is a mischievous monkey here. There's a rope bridge to the west and a clearing to the north.",
    )
    rocky_plateau = things.Location(
        "Rocky Plateau",
        "You stand on a wide, flat plateau. There is a thorny bush here. Far off in the distance, you can make out the sound of a helicopter. The temple lies to the south.",
    )
    sacrificial_chamber = things.Location(
        "Sacrificial Chamber",
        "You are inside the Temple of the Gold Skull. There is a stone altar here.",
    )
    treasure_chamber = things.Location(
        "Treasure Chamber",
        "You are in a treasure chamber. The walls are inscribed with ancient symbols. A huge statue holds a gold skull in its palm. A tunnel leads north.",
    )

    crashed_plane.add_connection(
        "out",
        edge_of_the_deep_jungle,
        "You climb out of the wrecked plane into the jungle clearing.",
    )
    edge_of_the_deep_jungle.add_connection(
        "jungle",
        deep_jungle,
        "You push into the deep jungle.",
        reverse_direction="south",
        reverse_travel_description="You emerge from the jungle back at the crash site.",
    )
    deep_jungle.add_connection(
        "south", village, "You push south through the jungle and emerge at a village."
    )
    deep_jungle.add_connection(
        "east", the_gorge, "You push east through the jungle and reach the gorge."
    )
    village.add_connection("north", deep_jungle, "You head north into the deep jungle.")
    village.add_connection("west", jungle_path, "You follow the path west.")
    village.add_connection(
        "enter warriors hut",
        warriors_hut,
        "You enter the warriors' hut.",
        reverse_direction="exit warriors hut",
        reverse_travel_description="You step back out into the village.",
    )
    village.add_connection(
        "enter womens hut",
        womens_hut,
        "You enter the women's hut.",
        reverse_direction="exit womens hut",
        reverse_travel_description="You step back out into the village.",
    )
    village.add_connection(
        "enter witch doctors hut",
        witch_doctors_hut,
        "You enter the witch doctor's hut.",
        reverse_direction="exit witch doctors hut",
        reverse_travel_description="You step back out into the village.",
    )
    jungle_path.add_connection(
        "east", village, "You follow the path east to the village."
    )
    jungle_path.add_connection(
        "west", outside_the_dark_cave, "You follow the path west toward the dark cave."
    )
    outside_the_dark_cave.add_connection(
        "cave",
        inside_the_dark_cave,
        "You step into the dark cave.",
        reverse_direction="out",
        reverse_travel_description="You step back out of the cave into the daylight.",
    )
    the_gorge.add_connection(
        "south", cool_pool, "You follow the trail south to a cool pool."
    )
    the_gorge.add_connection(
        "east", temple_of_the_gold_skull, "You cross the rope bridge to the other side."
    )
    the_gorge.add_connection("west", deep_jungle, "You head west into the deep jungle.")
    cool_pool.add_connection("north", the_gorge, "You head north back to the gorge.")
    temple_of_the_gold_skull.add_connection(
        "north", rocky_plateau, "You climb up to the rocky plateau."
    )
    temple_of_the_gold_skull.add_connection(
        "south", sacrificial_chamber, "You enter the temple's sacrificial chamber."
    )
    temple_of_the_gold_skull.add_connection(
        "west", the_gorge, "You cross the rope bridge back to the gorge."
    )
    rocky_plateau.add_connection(
        "south", temple_of_the_gold_skull, "You head south back to the temple."
    )
    sacrificial_chamber.add_connection(
        "north", temple_of_the_gold_skull, "You head north back outside the temple."
    )
    sacrificial_chamber.add_connection(
        "south",
        treasure_chamber,
        "You descend through the secret tunnel to the treasure chamber.",
    )
    treasure_chamber.add_connection(
        "north",
        sacrificial_chamber,
        "You climb back up the tunnel to the sacrificial chamber.",
    )

    backpack = things.Item(
        "backpack",
        "a sturdy backpack",
        "It contains a lighter and a compass. You can wear the backpack to automatically stow small items.",
    )
    backpack.set_property("wearable", True)
    backpack.set_property("is_worn", False)
    backpack.set_property("gettable", True)
    backpack.add_command_hint("wear backpack")
    backpack.add_command_hint("get backpack")
    crashed_plane.add_item(backpack)
    lighter = things.Item(
        "lighter",
        "a silver lighter engraved with the words 'From your colleagues at the university'",
        "The silver lighter is engraved with the words, 'From your colleagues at the university.' You give it a shake. It's still full of lighter fluid.",
    )
    lighter.set_property("flammable", False)
    lighter.set_property("is_lit", False)
    lighter.set_property("gettable", True)
    lighter.add_command_hint("get lighter")
    lighter.add_command_hint("use lighter on bush")
    crashed_plane.add_item(lighter)
    compass = things.Item(
        "compass",
        "a brass compass",
        "The brass compass points toward the north. It will help you navigate the deep jungle.",
    )
    compass.set_property("gettable", True)
    compass.add_command_hint("get compass")
    compass.add_command_hint("examine compass")
    crashed_plane.add_item(compass)
    seatbelt = things.Item(
        "seatbelt",
        "a buckled seatbelt holding you in the pilot's chair",
        "You are still buckled into your seat. You'll need to unbuckle before you can leave.",
    )
    seatbelt.set_property("gettable", False)
    seatbelt.set_property("is_buckled", True)
    seatbelt.add_command_hint("unbuckle seatbelt")
    crashed_plane.add_item(seatbelt)
    rifle = things.Item(
        "rifle",
        "a hunting rifle in good condition",
        "The rifle is in good condition, but it's not loaded. You find no ammunition in the wreckage. It could be traded to the warriors for a spear.",
    )
    rifle.set_property("gettable", True)
    rifle.set_property("is_weapon", False)
    rifle.add_command_hint("get rifle")
    rifle.add_command_hint("give rifle to warriors")
    edge_of_the_deep_jungle.add_item(rifle)
    wreckage = things.Item(
        "wreckage",
        "smoking plane wreckage",
        "The plane is beyond repair, but you may be able to salvage some supplies from the wreckage.",
    )
    wreckage.set_property("gettable", False)
    wreckage.set_property("is_searched", False)
    wreckage.add_command_hint("search wreckage")
    edge_of_the_deep_jungle.add_item(wreckage)
    nest = things.Item("nest", "a bird's nest", "A large bird's nest. Someone's home!")
    nest.set_property("gettable", False)
    nest.add_command_hint("search nest")
    jungle_path.add_item(nest)
    egg = things.Item(
        "egg",
        "a large spotted egg covered with green and purple spots",
        "The egg is covered with green and purple spots. It could be cooked and eaten, fed to the monkey, or brought back for the university's ornithology department.",
    )
    egg.set_property("gettable", True)
    egg.set_property("is_cooked", False)
    egg.set_property("edible", True)
    egg.add_command_hint("get egg")
    egg.add_command_hint("cook egg")
    egg.add_command_hint("give egg to monkey")
    jungle_path.add_item(egg)
    fire = things.Item(
        "fire",
        "a cooking fire burning hot and bright",
        "The village's cooking fire burns hot and bright. You could cook an egg here.",
    )
    fire.set_property("gettable", False)
    fire.set_property("is_lit", True)
    fire.add_command_hint("cook egg")
    village.add_item(fire)
    skirt = things.Item(
        "skirt",
        "a beaded skirt handmade by the village women",
        "The beaded skirt is quite beautiful — handmade by the village women.",
    )
    skirt.set_property("gettable", True)
    skirt.set_property("wearable", True)
    skirt.add_command_hint("get skirt")
    skirt.add_command_hint("wear skirt")
    womens_hut.add_item(skirt)
    fang = things.Item(
        "fang",
        "a broken tiger fang",
        "A broken tiger fang from the enormous tiger. The witch doctor might want this.",
    )
    fang.set_property("gettable", True)
    fang.add_command_hint("get fang")
    fang.add_command_hint("give fang to witch doctor")
    inside_the_dark_cave.add_item(fang)
    bones = things.Item(
        "bones",
        "old bones — the remains of a villager killed by the tiger",
        "The bones look to be the remains of a villager killed by the tiger.",
    )
    bones.set_property("gettable", True)
    bones.add_command_hint("get bones")
    bones.add_command_hint("put bones on altar")
    inside_the_dark_cave.add_item(bones)
    altar = things.Item(
        "altar",
        "a stone altar inscribed with ancient symbols",
        "The altar is made of solid stone and inscribed with ancient symbols. A smooth, shallow depression is carved into the surface. Perhaps something should be placed here.",
    )
    altar.set_property("gettable", False)
    altar.set_property("is_activated", False)
    altar.add_command_hint("put bones on altar")
    sacrificial_chamber.add_item(altar)
    skull = things.Item(
        "skull",
        "a gold skull made of solid gold",
        "It's made of solid gold. It belongs in a museum!",
    )
    skull.set_property("gettable", True)
    skull.add_command_hint("get skull")
    skull.add_command_hint("examine skull")
    treasure_chamber.add_item(skull)
    statue = things.Item(
        "statue",
        "a large stone statue combining the features of a tiger, a monkey and a human",
        "The stone statue is large and humanoid in appearance, combining the features of a tiger, a monkey and a human. It holds a gold skull in its palm.",
    )
    statue.set_property("gettable", False)
    statue.add_command_hint("examine statue")
    treasure_chamber.add_item(statue)
    bush = things.Item(
        "bush",
        "a thorny bush, bone dry",
        "The thorny bush is bone dry and looks like it will catch a spark quite easily.",
    )
    bush.set_property("gettable", False)
    bush.set_property("is_burning", False)
    bush.add_command_hint("use lighter on bush")
    bush.add_use_response(
        tool="lighter",
        response_text="Dense smoke billows up into the sky… A helicopter will land after a few turns.",
        requires_target_properties={"is_burning": False},
        sets_target_properties={"is_burning": True},
    )
    rocky_plateau.add_item(bush)
    helicopter = things.Item(
        "helicopter",
        "a rescue helicopter piloted by your old friend Jim",
        "You see your old friend Jim at the controls. He waves!",
    )
    helicopter.set_property("gettable", False)
    helicopter.set_property("is_landed", False)
    helicopter.add_command_hint("enter helicopter")
    rocky_plateau.add_item(helicopter)
    bridge = things.Item(
        "bridge",
        "an old rope bridge spanning the gorge",
        "The bridge looks quite old and creaks in the wind. I wouldn't trust it without some magical protection!",
    )
    bridge.set_property("gettable", False)
    bridge.add_command_hint("examine bridge")
    the_gorge.add_item(bridge)
    pool = things.Item(
        "pool",
        "a cool, tranquil pool surrounded by palm trees",
        "You see deadly water snakes lurking beneath the pool's tranquil waters. Do not enter!",
    )
    pool.set_property("gettable", False)
    pool.add_command_hint("examine pool")
    cool_pool.add_item(pool)

    warriors = things.Character(
        name="warriors",
        description="fierce warriors armed with spears who scowl at you",
        persona="We are fierce warriors. We do not talk to strangers. But we might trade.",
    )
    warriors.set_property("is_dead", False)
    warriors.set_property("emotional_state", "suspicious")
    spear = things.Item(
        "spear",
        "a ceremonial spear decorated with bird feathers and tiger teeth",
        "The ceremonial spear is decorated with bird feathers and tiger teeth.",
    )
    spear.set_property("gettable", True)
    spear.set_property("is_weapon", True)
    spear.add_command_hint("get spear")
    warriors.add_to_inventory(spear)
    warriors_hut.add_character(warriors)
    warriors.add_give_response(
        item="rifle",
        response_text="The warriors examine the hunting rifle with great interest. They nod and hand you a ceremonial spear in return.",
        sets_recipient_properties={"emotional_state": "happy"},
    )
    warriors.set_greeting(
        "The warriors scowl at you and mutter to themselves, brandishing their spears."
    )

    witch_doctor = things.Character(
        name="witch doctor",
        description="an ancient man wearing a necklace made from bones and feathers",
        persona="I am the witch doctor. I glare at strangers. Bring me something worthy.",
    )
    witch_doctor.set_property("is_dead", False)
    witch_doctor.set_property("emotional_state", "suspicious")
    necklace = things.Item(
        "necklace",
        "a necklace made from bones and feathers featuring a bird skull",
        "The necklace features a bird skull surrounded by feathers. It radiates magic! Wearing it makes you feel as light and free as a bird — your feet don't even leave tracks.",
    )
    necklace.set_property("gettable", True)
    necklace.set_property("wearable", True)
    necklace.set_property("is_worn", False)
    necklace.set_property("is_magical", True)
    necklace.add_command_hint("get necklace")
    necklace.add_command_hint("wear necklace")
    witch_doctor.add_to_inventory(necklace)
    witch_doctors_hut.add_character(witch_doctor)
    witch_doctor.add_give_response(
        item="fang",
        response_text="The witch doctor takes the fang and gives you the necklace from around his neck.",
        sets_recipient_properties={"emotional_state": "happy"},
    )
    witch_doctor.set_greeting("The witch doctor glares at you.")
    witch_doctor.add_dialogue(
        "bones",
        "The witch doctor nods and draws a map in the dirt. He refuses the old bones.",
    )
    witch_doctor.add_dialogue(
        "map",
        "A crude drawing that depicts a gorge, a temple, a skull and a strange beast.",
    )
    witch_doctor.add_dialogue(
        "necklace",
        "The necklace features a bird skull surrounded by feathers. It radiates magic!",
    )

    tiger = things.Character(
        name="tiger",
        description="a huge tiger lurking in the dark cave",
        persona="ROAR.",
    )
    tiger.set_property("is_dead", False)
    inside_the_dark_cave.add_character(tiger)

    monkey = things.Character(
        name="monkey",
        description="a mischievous monkey that follows you around",
        persona="Ook ook, eek eek!",
    )
    monkey.set_property("is_dead", False)
    monkey.set_property("is_lethargic", False)
    monkey.set_property("emotional_state", "curious")
    temple_of_the_gold_skull.add_character(monkey)
    monkey.add_give_response(
        item="egg",
        response_text="The monkey grabs the cooked egg and devours it eagerly. It becomes slow and lethargic.",
        requires_recipient_properties={"is_lethargic": False},
        sets_recipient_properties={"is_lethargic": True, "emotional_state": "sleepy"},
    )
    monkey.set_greeting("The noisy monkey follows you. Ook ook, eek eek!")

    jim = things.Character(
        name="Jim",
        description="your old friend Jim, pilot of the rescue helicopter",
        persona="I'm paid by the hour. Ready to fly when you are!",
    )
    jim.set_property("is_dead", False)
    jim.set_property("is_landed", False)
    rocky_plateau.add_character(jim)
    jim.set_greeting("Jim waves at you from the helicopter controls!")
    jim.add_dialogue("helicopter", "Ready to go? Just climb in!")
    jim.add_dialogue(
        "skull", "Is that a gold skull? Incredible! Let's get it to a museum!"
    )

    player = things.Character(
        name="The archaeologist",
        description="A daring archaeologist who survived a crash landing in the jungle.",
        persona="I am a daring archaeologist on a quest to retrieve a legendary treasure.",
    )
    player.set_property("character_type", "human")
    player.set_property("is_rescued", False)
    player.set_property("has_spear", False)
    player.set_property("is_wearing_necklace", False)

    if llm_client:
        tiger.set_behavior(make_hybrid_behavior(llm_client, make_tiger_behavior()))
    else:
        tiger.set_behavior(make_tiger_behavior())

    seatbelt_block = Seatbelt_Block(crashed_plane, seatbelt)
    crashed_plane.add_block("out", seatbelt_block)
    cave_block = Cave_Block(outside_the_dark_cave, tiger)
    outside_the_dark_cave.add_block("cave", cave_block)
    bridge_block = Bridge_Block(the_gorge, bridge)
    the_gorge.add_block("east", bridge_block)
    altar_block = Altar_Block(sacrificial_chamber, altar)
    sacrificial_chamber.add_block("south", altar_block)
    helicopter_block = Helicopter_Block(rocky_plateau, helicopter)
    rocky_plateau.add_block("enter helicopter", helicopter_block)

    characters = [
        warriors,
        witch_doctor,
        tiger,
        monkey,
        jim,
    ]

    custom_actions = [
        Unbuckle_Seatbelt,
        Search_Wreckage,
        Cook_Egg,
        Wear_Necklace,
        Put_Bones_On_Altar,
        Get_Monkey,
        Land_Helicopter,
        Enter_Helicopter,
        Tiger_Growl,
        Tiger_Maul,
        Examine_Compass_Action,
        Light_Bush,
        Land_Helicopter_After_Fire,
    ]

    return JungleAdventure(crashed_plane, player, characters, custom_actions)


if __name__ == "__main__":
    build_game().game_loop()
