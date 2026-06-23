"""Jungle Adventure -- a Parsely gamebook ported to the engine.

You wake buckled into the pilot's chair of a crashed prop plane, deep in the
jungle. Salvage a rifle, navigate the maze-like Deep Jungle with your compass,
trade your way through a village (rifle -> spear, tiger fang -> a magic
necklace), spear the tiger guarding a dark cave, float across a rope bridge
wearing the necklace, light a signal fire on the Rocky Plateau, then loot the
gold skull from the Temple of the Gold Skull -- waking its stone guardian -- and
race the chopper home. A perfect run scores 100.
Source: Parsely "Jungle Adventure" (pages 119-138).

Authored the way the reference ports are (see ``action_castle_2.py`` and
``docs/converting-parsely-games.md``): a ``build_game()`` assembles the world; a
``JungleAdventure`` Game subclass holds the scoring, the win, and the handful of
location set-pieces that don't fit a single verb (the Deep Jungle compass maze,
the lethal cave/bridge/pool transitions, the awakened guardian's north-only
chase); the two-object trades (GIVE RIFLE TO WARRIORS, GIVE FANG TO WITCH
DOCTOR, GIVE EGG TO MONKEY) use the engine's ``use_item_on`` factory; small
``Action`` subclasses cover the one-off verbs.

Scoring (rulebook page 138, max 100). Egg (+5, ornithology) and monkey (+10,
zoo) are mutually exclusive -- you must cook and feed the egg to the monkey to
capture it -- so the perfect run takes the monkey and the eight lines sum to
100: temple 10 + navigate 5 + skull 30 + skirt 10 + monkey 10 + escape 30 +
finish 5.

Two faithfulness calls (the source is genuinely loose here): the book's carry
limit (wear the pack to hold two large objects, etc.) is flavor and is *not*
enforced; and the guardian's optional "duck across the bridge, it won't follow"
escape is collapsed into a plain north-only chase, since it loops back anyway.

Run interactively:    uv run python -m test_gen.jungle_adventure.jungle_adventure
Run the walkthrough:  uv run python -m test_gen.jungle_adventure.jungle_adventure --walk
"""

from text_adventure_games import games, things, actions, blocks

# ---------------------------------------------------------------------------
# Held-item helpers (held = inventory + worn + wielded + open carried holders).
# A quest check on bare ``inventory`` would miss an item tucked in the backpack
# or worn, so everything that asks "do you have X?" goes through these.
# ---------------------------------------------------------------------------


def _held_names(character):
    """Every item name the character is holding, reaching one level into any
    open container/surface they carry or wear (the backpack holds the lighter
    and compass)."""
    names = set(character.inventory) | set(character.worn) | set(character.wielded)
    holders = list(character.inventory.values()) + list(character.worn.values())
    for holder in holders:
        if holder.is_holder() and holder.is_open():
            names |= set(holder.contents)
    return names


def _is_holding(character, name):
    return name in _held_names(character)


def _take_held(character, name):
    """Remove and return a held item by name from wherever it lives (a direct
    slot or an open carried holder), else None."""
    for store in (character.inventory, character.worn, character.wielded):
        if name in store:
            return store.pop(name)
    holders = list(character.inventory.values()) + list(character.worn.values())
    for holder in holders:
        if holder.is_holder() and name in holder.contents:
            item = holder.contents[name]
            holder.remove_item(item)
            return item
    return None


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s canonical auto-reverse, so
    the many ``out``->Village hut exits don't collide over Village's ``in``.
    (Same helper as the reference ports.)"""
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


VILLAGE_CLUSTER = {"Village", "Warriors Hut", "Womens Hut", "Witch Doctors Hut"}
TEMPLE_CLUSTER = {"Temple of the Gold Skull", "Sacrificial Chamber", "Treasure Chamber"}

# Commands that trigger the lethal/transform transitions handled in do_command.
_ENTER_CAVE = {"enter cave", "enter the cave", "enter dark cave", "cave", "go cave"}
_CROSS_GORGE = {
    "east",
    "e",
    "go east",
    "cross bridge",
    "cross the bridge",
    "cross rope bridge",
}
_ENTER_POOL = {
    "enter pool",
    "enter the pool",
    "swim",
    "swim in pool",
    "dive in",
    "wade into the pool",
}


# ---------------------------------------------------------------------------
# Blocks: non-lethal gates (seatbelt, the compass maze, the altar tunnel).
# ---------------------------------------------------------------------------


class SeatbeltBlock(blocks.Block):
    """GO OUT of the plane is barred until the seatbelt is unbuckled."""

    def __init__(self, seatbelt):
        super().__init__(
            "Still buckled in",
            "You're still buckled into your seat. You need to UNBUCKLE SEATBELT first.",
        )
        self.seatbelt = seatbelt

    def is_blocked(self) -> bool:
        return bool(self.seatbelt.get_property("is_buckled"))


class CompassBlock(blocks.Block):
    """The Deep Jungle is a maze of identical clearings: without the compass in
    hand every direction is a U-turn, so the player just wanders in circles.
    With the compass the true exits open up."""

    def __init__(self, game):
        super().__init__(
            "Lost in the jungle",
            "Without a compass you wander in circles through identical clearings "
            "and end up right back where you started.",
        )
        self.game = game

    def is_blocked(self) -> bool:
        return not _is_holding(self.game.player, "compass")


class AltarBlock(blocks.Block):
    """The tunnel south from the Sacrificial Chamber stays sealed until old
    bones are placed on the altar."""

    def __init__(self, altar):
        super().__init__(
            "A sealed wall",
            "The altar blocks the way south. Perhaps something should be placed "
            "in the shallow depression on its surface.",
        )
        self.altar = altar

    def is_blocked(self) -> bool:
        return not self.altar.get_property("is_activated")


# ---------------------------------------------------------------------------
# Game subclass: scoring, win, and the location set-pieces.
# ---------------------------------------------------------------------------


class JungleAdventure(games.Game):
    """Won by escaping the jungle in Jim's helicopter (a perfect run = 100)."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        self.max_score = 100
        self.guardian_active = False  # the stone guardian wakes when the skull moves
        self.monkey_has_skull = False  # the monkey snatches the skull in the chamber
        self.monkey_captured = False  # fed the egg, scooped into the pack
        self.escaped = False  # boarded the chopper -> win
        self.chopper_delay = 0  # turns since the signal fire was lit
        # Filled in by build_game so the set-pieces can reach key objects.
        self.bush = None
        self.helicopter = None
        self.monkey = None
        self.skull = None

    # --- movement / set-piece routing --------------------------------------

    def do_command(self, command: str) -> bool:
        cmd = (command or "").strip().lower()
        loc = self.player.location
        here = loc.name if loc is not None else ""

        # Entering the dark cave: fatal unarmed, a tiger-slaying triumph if you
        # carry the spear (which then sticks fast in the carcass).
        if here == "Outside the Dark Cave" and cmd in _ENTER_CAVE:
            return self._enter_cave()

        # Crossing the gorge eastward: the rope bridge tears free under your
        # weight unless the magic necklace is making you light as a bird.
        if here == "The Gorge" and cmd in _CROSS_GORGE:
            return self._cross_gorge()

        # Wading into the cool pool: deadly water snakes.
        if here == "Cool Pool" and cmd in _ENTER_POOL:
            self.end_in_death(
                "As you wade into the refreshing pool, something slithers against "
                "your leg -- a water snake sinks its fangs into your ankle. The "
                "poison spreads, and you slip into unconsciousness. THE END."
            )
            return True

        # While the awakened guardian gives chase, only NORTH is open.
        if self.guardian_active and here in TEMPLE_CLUSTER:
            direction = self.parser.get_direction(cmd, loc)
            if direction and direction != "north":
                self.parser.fail(
                    "The stone guardian lunges to cut you off -- your only escape "
                    "is NORTH!"
                )
                return False

        before = loc
        success = super().do_command(command)
        after = self.player.location
        if success and after is not None and after is not before:
            # +5 for threading the Deep Jungle with the compass (a successful
            # exit means the compass let you through -- the maze block stops you
            # otherwise).
            if before is not None and before.name == "Deep Jungle":
                self.award(
                    "navigate",
                    5,
                    "With the compass to guide you, you cross the deep jungle "
                    "without a single false turn.",
                )
            self._on_arrive(before, after)
        return success

    def _enter_cave(self) -> bool:
        if not _is_holding(self.player, "spear"):
            self.end_in_death(
                "As you step into the cave, a huge tiger leaps from the shadows "
                "and pounces on you. With a savage sweep of its claws it "
                "disembowels you, then drags you inside to eat. THE END."
            )
            return True
        spear = _take_held(self.player, "spear")  # it lodges in the tiger
        if spear is not None:
            spear.set_property("gettable", False)
            spear.examine_text = (
                "The ceremonial spear is buried in the tiger's carcass."
            )
        inside = self.locations["Inside the Dark Cave"]
        tiger = self.characters.get("tiger")
        if tiger is not None:
            tiger.set_property("is_dead", True)
        self.parser.ok(
            "Acting on pure instinct, you plunge the spear into the tiger's belly "
            "as it lunges. It falls dead at your feet, and you step over it into "
            "the cave."
        )
        self.relocate(self.player, inside)
        self.parser.ok(self.describe())
        self.end_turn()
        return True

    def _cross_gorge(self) -> bool:
        if "necklace" not in self.player.worn:
            self.end_in_death(
                "The rope bridge buckles under your weight and tears free from its "
                "supports. You plunge a hundred feet into the river and end up as "
                "crocodile food. THE END."
            )
            return True
        temple = self.locations["Temple of the Gold Skull"]
        before = self.player.location
        self.parser.ok(
            "Light as a bird, you float over the rotting planks of the ramshackle "
            "bridge and reach the far side safe and sound."
        )
        self.relocate(self.player, temple)
        self.parser.ok(self.describe())
        self._on_arrive(before, temple)
        self.end_turn()
        return True

    # --- arrivals -----------------------------------------------------------

    def _on_arrive(self, before, after):
        name = after.name

        # The witch doctor's curse: leaving the village dooms you to the ants.
        if self.player.get_property("is_cursed") and name not in VILLAGE_CLUSTER:
            self.end_in_death(
                "As you leave the village you are overwhelmed by a swarm of fire "
                "ants pouring out of the jungle! Your flesh is consumed, and all "
                "that's left are your bones. THE END."
            )
            return

        if name == "Temple of the Gold Skull":
            self.award(
                "temple",
                10,
                "You stand before the mythical Temple of the Gold Skull at last!",
            )
            # The monkey is endearing and starts tagging along from here (it was
            # waiting at the temple, so it only follows once you arrive).
            if (
                self.monkey is not None
                and self.monkey.location is after
                and self.monkey.following is None
                and not self.monkey_captured
            ):
                self.monkey.following = self.player

        if name == "Treasure Chamber":
            self._monkey_grab_skull()

        if name == "Rocky Plateau" and self.guardian_active:
            if self.helicopter is not None and self.helicopter.get_property(
                "is_landed"
            ):
                self.parser.ok(
                    "You scramble onto the plateau. The guardian thunders up the "
                    "path right behind you -- get to the chopper!"
                )
            else:
                self.end_in_death(
                    "You burst onto the bare plateau -- but there's no helicopter "
                    "in sight. The stone guardian's shadow falls over you, and it "
                    "makes sure you never tell tales of your jungle adventure. "
                    "THE END."
                )

    def _monkey_grab_skull(self):
        monkey = self.monkey
        treasure = self.locations["Treasure Chamber"]
        if (
            monkey is not None
            and monkey.location is treasure
            and self.skull is not None
            and self.skull.name in treasure.items
            and not self.monkey_has_skull
        ):
            treasure.remove_item(self.skull)
            monkey.add_to_inventory(self.skull)
            self.monkey_has_skull = True
            self.parser.ok(
                "The mischievous monkey scampers up the statue and snatches the "
                "gold skull from its palm! It clutches the prize just out of reach."
            )

    # --- guardian / chopper bookkeeping (called from the trigger) ----------

    def _advance_chopper(self):
        if self.helicopter is None or self.helicopter.get_property("is_landed"):
            return
        self.chopper_delay += 1
        if self.chopper_delay >= 2:
            self.helicopter.set_property("is_landed", True)
            self.parser.ok(
                "A helicopter swoops down out of the sky and sets down on the "
                "plateau. Your old friend Jim waves from the cockpit!"
            )

    def is_won(self) -> bool:
        return bool(self.escaped)


# ---------------------------------------------------------------------------
# One-off verbs
# ---------------------------------------------------------------------------


class UnbuckleSeatbelt(actions.Action):
    ACTION_NAME = "unbuckle seatbelt"
    ACTION_DESCRIPTION = "Unbuckle the seatbelt holding you in the pilot's chair"
    ACTION_ALIASES = ["unbuckle", "unbuckle the seatbelt", "unfasten seatbelt"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        seatbelt = self.character.location.items.get("seatbelt")
        if seatbelt is None:
            self.parser.fail("There's no seatbelt here.")
            return False
        if not seatbelt.get_property("is_buckled"):
            self.parser.fail("You've already unbuckled the seatbelt.")
            return False
        self.seatbelt = seatbelt
        return True

    def apply_effects(self):
        self.seatbelt.set_property("is_buckled", False)
        self.parser.ok("You unbuckle the seatbelt. You're free to leave the plane.")


class SearchWreckage(actions.Action):
    ACTION_NAME = "search wreckage"
    ACTION_DESCRIPTION = "Salvage supplies from the smoking wreckage"
    ACTION_ALIASES = ["salvage wreckage", "search the wreckage", "salvage the wreckage"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        wreckage = self.character.location.items.get("wreckage")
        if wreckage is None:
            self.parser.fail("There's no wreckage to search here.")
            return False
        if wreckage.get_property("is_searched"):
            self.parser.fail("You've already picked the wreckage clean.")
            return False
        self.wreckage = wreckage
        return True

    def apply_effects(self):
        self.wreckage.set_property("is_searched", True)
        rifle = things.Item(
            "rifle",
            "a hunting rifle in good condition",
            "The rifle is in good condition, but it's not loaded and there's no "
            "ammunition to be found. It could be traded to the warriors for a spear.",
        )
        rifle.add_command_hint("get rifle")
        rifle.add_command_hint("give rifle to warriors")
        self.character.location.add_item(rifle)
        self.parser.ok("You rummage through the smoking wreckage and find a rifle!")


class SearchNest(actions.Action):
    ACTION_NAME = "search nest"
    ACTION_DESCRIPTION = "Search the bird's nest"
    ACTION_ALIASES = ["search the nest", "search birds nest", "look in nest"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        nest = self.character.location.items.get("nest")
        if nest is None:
            self.parser.fail("There's no nest here.")
            return False
        if nest.get_property("is_searched"):
            self.parser.fail("The nest is empty now.")
            return False
        self.nest = nest
        return True

    def apply_effects(self):
        self.nest.set_property("is_searched", True)
        egg = things.Item(
            "egg",
            "a large egg covered with green and purple spots",
            "The egg is covered with green and purple spots. It could be cooked "
            "and fed to the monkey, or brought back for the ornithology department.",
        )
        egg.set_property("is_cooked", False)
        egg.add_command_hint("get egg")
        egg.add_command_hint("cook egg")
        egg.add_command_hint("give egg to monkey")
        self.character.location.add_item(egg)
        self.parser.ok("You part the twigs and find a large, spotted egg!")


class CookEgg(actions.Action):
    ACTION_NAME = "cook egg"
    ACTION_DESCRIPTION = "Cook the egg over the village cooking fire"
    ACTION_ALIASES = ["cook the egg", "cook egg on fire", "roast egg"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "fire" not in self.character.location.items:
            self.parser.fail("There's no cooking fire here.")
            return False
        if not _is_holding(self.character, "egg"):
            self.parser.fail("You don't have an egg to cook.")
            return False
        self.egg = (
            self.character.inventory.get("egg")
            or self.character.worn.get("egg")
            or self._egg_in_holder()
        )
        if self.egg is not None and self.egg.get_property("is_cooked"):
            self.parser.fail("The egg is already cooked.")
            return False
        return True

    def _egg_in_holder(self):
        holders = list(self.character.inventory.values()) + list(
            self.character.worn.values()
        )
        for holder in holders:
            if holder.is_holder() and "egg" in holder.contents:
                return holder.contents["egg"]
        return None

    def apply_effects(self):
        if self.egg is not None:
            self.egg.set_property("is_cooked", True)
            self.egg.examine_text = (
                "A cooked egg -- just the thing for a hungry monkey."
            )
        self.parser.ok(
            "You hold the egg over the cooking fire. It sizzles and cooks through."
        )


class WearNecklace(actions.Action):
    ACTION_NAME = "wear necklace"
    ACTION_DESCRIPTION = "Wear the magic bone-and-feather necklace"
    ACTION_ALIASES = ["put on necklace", "wear the necklace", "don necklace"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "necklace" in self.character.worn:
            self.parser.fail("You're already wearing the necklace.")
            return False
        if not _is_holding(self.character, "necklace"):
            self.parser.fail("You don't have the necklace.")
            return False
        return True

    def apply_effects(self):
        # Character.wear pops from inventory, so make sure it's there (it may be
        # tucked in the backpack) before wearing it.
        if "necklace" not in self.character.inventory:
            self.character.add_to_inventory(_take_held(self.character, "necklace"))
        self.character.wear(self.character.inventory["necklace"])
        self.parser.ok(
            "You feel as light and as free as a bird! Your feet don't even leave "
            "tracks in the dirt."
        )


class PutBonesOnAltar(actions.Action):
    ACTION_NAME = "put bones on altar"
    ACTION_DESCRIPTION = "Place the old bones in the altar's depression"
    ACTION_ALIASES = [
        "place bones on altar",
        "put the bones on the altar",
        "put bones on the altar",
        "place the bones on the altar",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        altar = self.character.location.items.get("altar")
        if altar is None:
            self.parser.fail("There's no altar here.")
            return False
        if altar.get_property("is_activated"):
            self.parser.fail("The altar has already slid aside.")
            return False
        if not _is_holding(self.character, "bones"):
            self.parser.fail("You don't have any bones to place.")
            return False
        self.altar = altar
        return True

    def apply_effects(self):
        bones = _take_held(self.character, "bones")
        if bones is not None:
            self.altar.location.add_item(bones)
            bones.set_property("gettable", False)
        self.altar.set_property("is_activated", True)
        self.parser.ok(
            "You set the old bones in the shallow depression. With a deep rumble, "
            "the altar slides aside, revealing a secret tunnel leading south."
        )


class GetMonkey(actions.Action):
    ACTION_NAME = "get monkey"
    ACTION_DESCRIPTION = "Scoop up the lethargic monkey"
    ACTION_ALIASES = [
        "take monkey",
        "grab monkey",
        "catch monkey",
        "get the monkey",
        "take the monkey",
        "grab the monkey",
        "catch the monkey",
        "capture monkey",
        "capture the monkey",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        monkey = self.game.monkey
        if monkey is None or monkey.location is not self.character.location:
            self.parser.fail("There's no monkey here to grab.")
            return False
        if not monkey.get_property("is_lethargic"):
            self.parser.fail(
                "The monkey scurries out of reach, chattering. You'll never catch "
                "it while it's this lively."
            )
            return False
        return True

    def apply_effects(self):
        monkey = self.game.monkey
        loc = monkey.location
        if loc is not None and monkey.name in loc.characters:
            loc.remove_character(monkey)
        monkey.following = None
        self.game.monkey_captured = True
        self.character.set_property("has_monkey", True)
        self.parser.ok(
            "The monkey is slow and sleepy from the egg. You scoop it up and stow "
            "it safely in your pack."
        )


class GetSkull(actions.Action):
    ACTION_NAME = "get skull"
    ACTION_DESCRIPTION = "Take the gold skull from the statue"
    ACTION_ALIASES = [
        "take skull",
        "grab skull",
        "get the skull",
        "take the skull",
        "get gold skull",
        "take gold skull",
        "grab the gold skull",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.game.monkey_has_skull:
            self.parser.fail(
                "The monkey is clutching the gold skull just out of your reach."
            )
            return False
        loc = self.character.location
        if self.game.skull is None or self.game.skull.name not in loc.items:
            self.parser.fail("There's no gold skull here.")
            return False
        return True

    def apply_effects(self):
        loc = self.character.location
        skull = loc.items.get("skull")
        loc.remove_item(skull)
        self.character.add_to_inventory(skull)
        self.game.guardian_active = True
        self.parser.ok(
            "You lift the gold skull from the statue's palm. With a grinding roar "
            "the stone guardian shudders to life! It blocks every exit but the "
            'way north. "Get to the chopper!"'
        )


class EatEgg(actions.Action):
    ACTION_NAME = "eat egg"
    ACTION_DESCRIPTION = "Eat the egg"
    ACTION_ALIASES = ["eat the egg", "eat egg raw"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "egg"):
            self.parser.fail("You don't have an egg.")
            return False
        return True

    def apply_effects(self):
        # Flavor only -- the book makes you "too tired for adventure", but the egg
        # is far too valuable to actually eat, so we just wave you off.
        self.parser.ok(
            "One bite and you feel full and sleepy -- too tired for adventure. "
            "Best save this egg for something more useful."
        )


class AttackWitchDoctor(actions.Action):
    ACTION_NAME = "attack witch doctor"
    ACTION_DESCRIPTION = "Attack the witch doctor (a very bad idea)"
    ACTION_ALIASES = [
        "kill witch doctor",
        "attack the witch doctor",
        "hit witch doctor",
        "fight witch doctor",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "witch doctor" not in self.character.location.characters:
            self.parser.fail("There's no witch doctor here.")
            return False
        return True

    def apply_effects(self):
        wd = self.character.location.characters.get("witch doctor")
        if wd is not None and wd.location is not None:
            wd.location.remove_character(wd)
        self.character.set_property("is_cursed", True)
        self.parser.ok(
            "The witch doctor curses you and flees the hut, vanishing into the "
            "jungle. A fire ant stings your ankle... then another. You'd better "
            "not leave the village now."
        )


class AttackWarriors(actions.Action):
    ACTION_NAME = "attack warriors"
    ACTION_DESCRIPTION = "Attack the warriors (a very bad idea)"
    ACTION_ALIASES = ["kill warriors", "attack the warriors", "fight warriors"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "warriors" not in self.character.location.characters:
            self.parser.fail("There are no warriors here.")
            return False
        return True

    def apply_effects(self):
        self.parser.fail(
            "These are fierce warriors, armed to the teeth. Attacking them would "
            "be a very bad idea."
        )


# ---------------------------------------------------------------------------
# Two-object trades (the engine's use_item_on factory)
# ---------------------------------------------------------------------------


def _give_rifle_to_warriors(action):
    _take_held(action.character, "rifle")  # the warriors keep it
    spear = things.Item(
        "spear",
        "a ceremonial spear decorated with bird feathers and tiger teeth",
        "The ceremonial spear is decorated with bird feathers and tiger teeth. "
        "Sharp enough to face a tiger.",
    )
    spear.add_command_hint("get spear")
    action.character.add_to_inventory(spear)


GiveRifleToWarriors = actions.use_item_on(
    "give rifle to warriors",
    item="rifle",
    target="warriors",
    verb="give",
    preposition="to",
    description="Trade the hunting rifle to the warriors",
    aliases=[
        "give the rifle to the warriors",
        "trade rifle to warriors",
        "give warriors rifle",
    ],
    effect=_give_rifle_to_warriors,
    success=(
        "The warriors examine the hunting rifle with great interest. They nod and "
        "hand you a ceremonial spear in return."
    ),
    item_missing="You don't have a rifle to give.",
    target_missing="There are no warriors here.",
)


def _give_fang_to_witch_doctor(action):
    _take_held(action.character, "fang")
    necklace = things.Item(
        "necklace",
        "a necklace of bones and feathers, set with a bird skull",
        "The necklace features a bird skull surrounded by feathers. It radiates "
        "magic! Wearing it makes you light as a bird.",
    )
    necklace.set_property("wearable", True)
    necklace.add_command_hint("wear necklace")
    action.character.add_to_inventory(necklace)


GiveFangToWitchDoctor = actions.use_item_on(
    "give fang to witch doctor",
    item="fang",
    target="witch doctor",
    verb="give",
    preposition="to",
    description="Give the tiger fang to the witch doctor",
    aliases=[
        "give tiger fang to witch doctor",
        "give the fang to the witch doctor",
        "give witch doctor fang",
    ],
    effect=_give_fang_to_witch_doctor,
    success=(
        "The witch doctor takes the fang and lifts the necklace from around his "
        "own neck, pressing it into your hands."
    ),
    item_missing="You don't have a tiger fang.",
    target_missing="There's no witch doctor here.",
)


def _give_egg_to_monkey(action):
    g = action.game
    egg = _take_held(action.character, "egg")  # the monkey devours it
    monkey = g.monkey
    monkey.set_property("is_lethargic", True)
    if g.monkey_has_skull:
        skull = monkey.inventory.pop("skull", None)
        if skull is not None:
            monkey.location.add_item(skull)
        g.monkey_has_skull = False
        action.parser.ok(
            "The monkey grabs the cooked egg and gobbles it down, dropping the "
            "gold skull at your feet. It slumps, slow and lethargic."
        )
    else:
        action.parser.ok(
            "The monkey grabs the cooked egg and gobbles it down. It slumps, slow "
            "and lethargic."
        )


GiveEggToMonkey = actions.use_item_on(
    "give egg to monkey",
    item="egg",
    target="monkey",
    verb="give",
    preposition="to",
    description="Feed the cooked egg to the monkey",
    aliases=[
        "feed egg to monkey",
        "feed monkey egg",
        "give the egg to the monkey",
        "feed the monkey the egg",
        "feed monkey",
    ],
    effect=_give_egg_to_monkey,
    requires=lambda a: (
        "The monkey has already had its fill."
        if a.game.monkey.get_property("is_lethargic")
        else (
            None
            if (
                a.character.inventory.get("egg")
                or a.character.worn.get("egg")
                or any(
                    h.is_holder() and "egg" in h.contents
                    for h in list(a.character.inventory.values())
                    + list(a.character.worn.values())
                )
            )
            and _egg_is_cooked(a.character)
            else "The monkey sniffs the raw egg and turns up its nose. Cook it first."
        )
    ),
    item_missing="You don't have an egg.",
    target_missing="There's no monkey here.",
)


def _egg_is_cooked(character):
    egg = character.inventory.get("egg") or character.worn.get("egg")
    if egg is None:
        for holder in list(character.inventory.values()) + list(
            character.worn.values()
        ):
            if holder.is_holder() and "egg" in holder.contents:
                egg = holder.contents["egg"]
                break
    return egg is not None and egg.get_property("is_cooked")


class EnterHelicopter(actions.Action):
    ACTION_NAME = "enter helicopter"
    ACTION_DESCRIPTION = "Climb aboard the rescue helicopter"
    ACTION_ALIASES = [
        "board helicopter",
        "get in helicopter",
        "get in the helicopter",
        "enter chopper",
        "board the helicopter",
        "climb into helicopter",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Rocky Plateau":
            self.parser.fail("There's no helicopter here.")
            return False
        heli = self.game.helicopter
        if heli is None or not heli.get_property("is_landed"):
            self.parser.fail(
                "The helicopter hasn't landed yet. Light the signal fire and wait "
                "for it to descend."
            )
            return False
        return True

    def apply_effects(self):
        g = self.game
        player = self.character
        g.award("escape", 30)
        if _is_holding(player, "skull"):
            g.award("skull", 30, "The gold skull is bound for a museum's collection!")
        if _is_holding(player, "skirt"):
            g.award(
                "skirt", 10, "The beaded skirt will grace the arts-and-culture exhibit."
            )
        if g.monkey_captured or player.get_property("has_monkey"):
            g.award("monkey", 10, "A live monkey for the zoo!")
        if _is_holding(player, "egg"):
            g.award("egg", 5, "The spotted egg goes to the ornithology department.")
        g.award("finish", 5)
        g.escaped = True
        self.parser.ok(
            "You climb in and Jim guns the engine. The helicopter lifts off, "
            "rising high above the jungle canopy and turning for home."
        )
        g.announce_ending(
            "Your Jungle Adventure is over... for now! THE END.", show_score=True
        )


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> JungleAdventure:
    L = things.Location

    crashed_plane = L(
        "Crashed Plane",
        "You wake buckled into the pilot's chair of a single-engine prop plane. "
        "Through the cockpit window you see the deep jungle. There is a backpack here.",
    )
    edge = L(
        "Edge of the Deep Jungle",
        "You stand in a clearing, the site of a terrible crash, ringed by smoking "
        "wreckage and inhospitable jungle.",
    )
    deep_jungle = L(
        "Deep Jungle",
        "You are lost in the deep jungle. Identical clearings press in on every "
        "side -- north, south, east and west all look the same. Without a compass "
        "you'll only wander in circles.",
    )
    village = L(
        "Village",
        "You enter a village. A cooking fire crackles here, and three huts stand "
        "around it. A path leads west, and the deep jungle is to the north.",
    )
    warriors_hut = L(
        "Warriors Hut",
        "Inside the warriors' hut, fierce warriors scowl and mutter, brandishing "
        "their spears.",
    )
    womens_hut = L(
        "Womens Hut",
        "Inside the women's hut, the village women greet you warmly and present "
        "you with a beaded skirt.",
    )
    witch_hut = L(
        "Witch Doctors Hut",
        "Inside the witch doctor's hut, an ancient man glares at you. A necklace "
        "of bones and feathers hangs at his neck.",
    )
    jungle_path = L(
        "Jungle Path",
        "You are on a jungle path running east and west. A bird's nest sits in the "
        "branches here.",
    )
    outside_cave = L(
        "Outside the Dark Cave",
        "You stand outside a dark cave. From within come the growls of a large "
        "animal.",
    )
    inside_cave = L(
        "Inside the Dark Cave",
        "You are inside a dark cave that smells of tiger and death. A fresh tiger "
        "carcass lies here beside some old bones.",
    )
    gorge = L(
        "The Gorge",
        "You stand on the western edge of a vast, deep gorge. An old rope bridge "
        "spans it to the east. A trail leads south, and the jungle lies west.",
    )
    cool_pool = L(
        "Cool Pool",
        "You reach a cool pool, ringed by swaying palm trees. The way back north "
        "leads to the gorge.",
    )
    temple = L(
        "Temple of the Gold Skull",
        "You stand before the ruins of a magnificent temple -- the mythical Temple "
        "of the Gold Skull! A rope bridge lies west, a clearing north, and a dark "
        "doorway leads south into the temple.",
    )
    rocky_plateau = L(
        "Rocky Plateau",
        "A wide, flat plateau. A thorny bush grows here, bone dry. Far off you can "
        "make out the beat of a helicopter. The temple lies to the south.",
    )
    sacrificial_chamber = L(
        "Sacrificial Chamber",
        "You are inside the Temple of the Gold Skull. A stone altar stands here.",
    )
    treasure_chamber = L(
        "Treasure Chamber",
        "A treasure chamber, its walls inscribed with ancient symbols. A huge "
        "statue holds a gold skull in its palm. A tunnel leads north.",
    )

    all_locations = [
        crashed_plane,
        edge,
        deep_jungle,
        village,
        warriors_hut,
        womens_hut,
        witch_hut,
        jungle_path,
        outside_cave,
        inside_cave,
        gorge,
        cool_pool,
        temple,
        rocky_plateau,
        sacrificial_chamber,
        treasure_chamber,
    ]

    # --- exits -------------------------------------------------------------
    _one_way(crashed_plane, "out", edge)
    _one_way(edge, "plane", crashed_plane)
    _one_way(edge, "jungle", deep_jungle)
    # Deep Jungle's real exits (gated by the compass maze block, below).
    _one_way(deep_jungle, "south", village)
    _one_way(deep_jungle, "east", gorge)
    _one_way(deep_jungle, "west", edge)
    _one_way(village, "north", deep_jungle)
    village.add_connection(
        "west", jungle_path
    )  # auto-reverses jungle_path east->village
    _one_way(village, "enter warriors hut", warriors_hut)
    _one_way(warriors_hut, "out", village)
    _one_way(village, "enter womens hut", womens_hut)
    _one_way(womens_hut, "out", village)
    _one_way(village, "enter witch doctors hut", witch_hut)
    _one_way(witch_hut, "out", village)
    jungle_path.add_connection("west", outside_cave)  # auto-reverses outside_cave east
    _one_way(inside_cave, "out", outside_cave)  # cave entry handled in do_command
    gorge.add_connection("south", cool_pool)  # auto-reverses cool_pool north->gorge
    _one_way(gorge, "west", deep_jungle)
    _one_way(temple, "west", gorge)  # gorge east (the bridge) handled in do_command
    temple.add_connection("north", rocky_plateau)  # auto-reverses plateau south->temple
    temple.add_connection("south", sacrificial_chamber)  # auto-reverses chamber north
    sacrificial_chamber.add_connection("south", treasure_chamber)  # auto-reverses north

    # --- scenery helper ----------------------------------------------------
    def scenery(name, desc, examine, loc, props=None, hints=()):
        it = things.Item(name, desc, examine)
        it.set_property("gettable", False)
        for k, v in (props or {}).items():
            it.set_property(k, v)
        for h in hints:
            it.add_command_hint(h)
        loc.add_item(it)
        return it

    # --- Crashed Plane: backpack (with lighter + compass) and the seatbelt --
    backpack = things.Item(
        "backpack",
        "a sturdy backpack",
        "A sturdy backpack. It contains a lighter and a compass. Worn or carried "
        "open, you can reach what's inside.",
    )
    backpack.set_property("wearable", True)
    backpack.make_container()  # unlimited, open
    backpack.add_command_hint("get backpack")
    backpack.add_command_hint("wear backpack")
    lighter = things.Item(
        "lighter",
        "a silver lighter",
        "A silver lighter engraved 'From your colleagues at the university.' Still "
        "full of fluid -- just the thing to light a signal fire.",
    )
    lighter.add_command_hint("use lighter on bush")
    compass = things.Item(
        "compass",
        "a brass compass",
        "The brass compass points true north. Hold it and the deep jungle's real "
        "exits are: from here, SOUTH to the village, EAST to the gorge, WEST back "
        "to the crash site.",
    )
    backpack.add_item(lighter)
    backpack.add_item(compass)
    crashed_plane.add_item(backpack)
    seatbelt = scenery(
        "seatbelt",
        "the seatbelt holding you in the pilot's chair",
        "You're buckled snugly into the pilot's chair.",
        crashed_plane,
        props={"is_buckled": True},
        hints=["unbuckle seatbelt"],
    )

    # --- Edge of the Deep Jungle -------------------------------------------
    scenery(
        "wreckage",
        "the smoking wreckage of the plane",
        "The plane is beyond repair, but you might salvage some supplies.",
        edge,
        props={"is_searched": False},
        hints=["search wreckage"],
    )

    # --- Village -----------------------------------------------------------
    scenery(
        "fire",
        "a hot, bright cooking fire",
        "The village's cooking fire burns hot and bright -- good for cooking an egg.",
        village,
        hints=["cook egg"],
    )

    # --- Women's hut: the beaded skirt -------------------------------------
    skirt = things.Item(
        "skirt",
        "a beaded skirt, handmade by the village women",
        "The beaded skirt is beautiful -- handmade by the village women. The "
        "university's arts-and-culture exhibit would treasure it.",
    )
    skirt.set_property("wearable", True)
    skirt.add_command_hint("get skirt")
    womens_hut.add_item(skirt)

    # --- Jungle Path: the nest --------------------------------------------
    scenery(
        "nest",
        "a large bird's nest",
        "A large bird's nest wedged in the branches. Someone's home!",
        jungle_path,
        props={"is_searched": False},
        hints=["search nest"],
    )

    # --- Inside the Dark Cave: bones, fang, carcass ------------------------
    bones = things.Item(
        "bones",
        "a pile of old bones",
        "The bones look to be the remains of a villager killed by the tiger.",
    )
    bones.add_command_hint("get bones")
    bones.add_command_hint("put bones on altar")
    inside_cave.add_item(bones)
    fang = things.Item(
        "fang",
        "a broken tiger fang",
        "A broken fang from the enormous tiger. The witch doctor might want it.",
    )
    fang.add_command_hint("get fang")
    fang.add_command_hint("give fang to witch doctor")
    inside_cave.add_item(fang)
    scenery(
        "carcass",
        "the tiger's carcass",
        "The enormous tiger, dead, impaled on your spear.",
        inside_cave,
    )

    # --- The Gorge ---------------------------------------------------------
    scenery(
        "bridge",
        "an old rope bridge",
        "The bridge is old and creaks in the wind. I wouldn't trust it without "
        "some magical protection!",
        gorge,
    )
    scenery(
        "gorge",
        "a vast, deep gorge",
        "It's gorgeous! Far below, a winding river churns with crocodiles.",
        gorge,
    )

    # --- Cool Pool ---------------------------------------------------------
    scenery(
        "pool",
        "a cool, tranquil pool",
        "Deadly water snakes lurk beneath the tranquil surface. Do not enter!",
        cool_pool,
    )

    # --- Rocky Plateau: the bush and the helicopter ------------------------
    bush = scenery(
        "bush",
        "a thorny bush, bone dry",
        "The thorny bush is bone dry -- it'll catch a spark easily.",
        rocky_plateau,
        props={"is_burning": False},
        hints=["use lighter on bush"],
    )
    helicopter = scenery(
        "helicopter",
        "a rescue helicopter",
        "Your old friend Jim is at the controls. He waves!",
        rocky_plateau,
        props={"is_landed": False},
        hints=["enter helicopter"],
    )

    # --- Sacrificial Chamber: the altar ------------------------------------
    altar = scenery(
        "altar",
        "a stone altar inscribed with ancient symbols",
        "Solid stone, inscribed with ancient symbols, with a smooth shallow "
        "depression carved into the surface. Something should be placed here.",
        sacrificial_chamber,
        props={"is_activated": False},
        hints=["put bones on altar"],
    )

    # --- Treasure Chamber: the gold skull and the guardian statue ----------
    skull = things.Item(
        "skull",
        "a skull of solid gold",
        "It's made of solid gold. It belongs in a museum!",
    )
    skull.add_command_hint("get skull")
    treasure_chamber.add_item(skull)
    scenery(
        "statue",
        "a huge stone statue",
        "A large humanoid statue blending the features of a tiger, a monkey and a "
        "human. It holds the gold skull in its palm.",
        treasure_chamber,
    )

    # --- characters --------------------------------------------------------
    warriors = things.Character(
        "warriors",
        "fierce warriors armed with spears",
        "We are fierce warriors. We don't talk to strangers -- but we might trade.",
    )
    warriors.talk_text = (
        "The warriors scowl and brandish their spears. They won't talk."
    )
    warriors_hut.add_character(warriors)

    witch_doctor = things.Character(
        "witch doctor",
        "an ancient man wearing a bone-and-feather necklace",
        "Bring me something worthy, stranger.",
    )
    witch_doctor.talk_text = "The witch doctor glares at you and says nothing."
    witch_doctor.talk_topics = {
        "map": "A crude dirt drawing: a gorge, a temple, a skull and a strange beast.",
        "bones": "The witch doctor nods at the bones and draws a map in the dirt, "
        "but he won't take them.",
        "necklace": "The necklace radiates magic -- it makes the wearer light as a bird.",
    }
    witch_hut.add_character(witch_doctor)

    tiger = things.Character("tiger", "a huge tiger lurking in the dark", "ROAR.")
    tiger.set_property("is_dead", False)
    inside_cave.add_character(tiger)

    monkey = things.Character(
        "monkey",
        "a mischievous monkey",
        "Ook ook, eek eek!",
    )
    monkey.set_property("is_lethargic", False)
    monkey.talk_text = "The monkey chatters and turns a somersault. Ook ook!"
    temple.add_character(monkey)

    jim = things.Character(
        "Jim", "your old friend Jim, the helicopter pilot", "Paid by the hour."
    )
    jim.talk_text = (
        '"Ready when you are! Just light a fire so I can find you, then climb aboard."'
    )
    rocky_plateau.add_character(jim)

    player = things.Character(
        "the archaeologist",
        "a daring archaeologist, lately the survivor of a crash landing",
        "I'm a daring archaeologist after a legendary treasure.",
    )

    custom_actions = [
        UnbuckleSeatbelt,
        SearchWreckage,
        SearchNest,
        CookEgg,
        WearNecklace,
        PutBonesOnAltar,
        GetMonkey,
        GetSkull,
        EatEgg,
        AttackWitchDoctor,
        AttackWarriors,
        GiveRifleToWarriors,
        GiveFangToWitchDoctor,
        GiveEggToMonkey,
        EnterHelicopter,
        LightBush,
    ]

    game = JungleAdventure(
        crashed_plane,
        player,
        characters=[warriors, witch_doctor, tiger, monkey, jim],
        custom_actions=custom_actions,
    )

    # Register every room by name (named exits + arrival hooks look rooms up).
    for loc in all_locations:
        game.locations.setdefault(loc.name, loc)

    # Hand the set-pieces their key objects.
    game.bush = bush
    game.helicopter = helicopter
    game.monkey = monkey
    game.skull = skull

    # The monkey starts following once you reach the temple (set in _on_arrive),
    # but it won't follow you into the snake-ridden Cool Pool.
    monkey.follow_filter = lambda dest: dest.name != "Cool Pool"

    # --- blocks ------------------------------------------------------------
    crashed_plane.add_block("out", SeatbeltBlock(seatbelt))
    compass_block = CompassBlock(game)
    for direction in ("south", "east", "west"):
        deep_jungle.add_block(direction, compass_block)
    sacrificial_chamber.add_block("south", AltarBlock(altar))

    # Lighting the bush summons the chopper a couple of turns later.
    game.add_trigger(
        "land_chopper",
        lambda g: g.bush.get_property("is_burning")
        and not g.helicopter.get_property("is_landed"),
        lambda g: g._advance_chopper(),
        repeatable=True,
    )

    return game


# Lighting the signal fire: USE LIGHTER ON BUSH (the engine's two-object verb).
def _light_bush(action):
    action.target.set_property("is_burning", True)


LightBush = actions.use_item_on(
    "use lighter on bush",
    item="lighter",
    target="bush",
    verb="light",
    preposition="on",
    description="Light the dry bush with the lighter to send up a signal",
    aliases=[
        "light bush",
        "light the bush",
        "use the lighter on the bush",
        "light bush with lighter",
        "set bush on fire",
    ],
    effect=_light_bush,
    success=(
        "You touch the flame to the bone-dry bush. It catches at once and dense "
        "smoke billows into the sky. A helicopter will spot it before long!"
    ),
    requires=lambda a: (
        "The bush is already ablaze." if a.target.get_property("is_burning") else None
    ),
    item_missing="You don't have a lighter.",
    target_missing="There's no bush here.",
)


# ---------------------------------------------------------------------------
# Walkthrough (also the win test) -- wins at 100/100
# ---------------------------------------------------------------------------

WALKTHROUGH = [
    "unbuckle seatbelt",  # free yourself from the pilot's chair
    "get backpack",  # pack holds the lighter + compass (reachable while carried)
    "out",  # -> Edge of the Deep Jungle
    "search wreckage",  # a rifle turns up
    "get rifle",
    "go jungle",  # -> Deep Jungle (compass in pack lets you navigate)
    "south",  # -> Village (+5 navigate)
    "enter warriors hut",
    "give rifle to warriors",  # rifle -> ceremonial spear
    "out",
    "enter womens hut",
    "get skirt",  # +10 at the end (arts & culture)
    "out",
    "west",  # -> Jungle Path
    "search nest",  # an egg turns up
    "get egg",
    "west",  # -> Outside the Dark Cave
    "enter cave",  # spear in hand: slay the tiger, step inside (spear lost)
    "get fang",
    "get bones",
    "out",  # -> Outside the Dark Cave
    "east",  # -> Jungle Path
    "east",  # -> Village
    "cook egg",  # over the cooking fire -- now the monkey will eat it
    "enter witch doctors hut",
    "give fang to witch doctor",  # fang -> magic necklace
    "wear necklace",  # light as a bird: safe to cross the bridge
    "out",
    "north",  # -> Deep Jungle
    "east",  # -> The Gorge
    "east",  # cross the bridge -> Temple of the Gold Skull (+10 temple)
    "north",  # -> Rocky Plateau (monkey follows)
    "use lighter on bush",  # signal fire: the chopper will land
    "south",  # -> Temple
    "south",  # -> Sacrificial Chamber
    "put bones on altar",  # opens the tunnel south
    "south",  # -> Treasure Chamber (the monkey snatches the skull)
    "give egg to monkey",  # it drops the skull and goes lethargic
    "get monkey",  # +10 zoo: scoop up the sleepy monkey
    "get skull",  # +30 museum: wakes the guardian -- flee north!
    "north",  # -> Sacrificial Chamber
    "north",  # -> Temple
    "north",  # -> Rocky Plateau (chopper has landed)
    "enter helicopter",  # +30 escape, +5 finish -> WIN at 100/100
]


def _run(commands):
    game = build_game()
    game.parser.parse_command("look")
    for cmd in commands:
        print(f"\n>>> {cmd}")
        game.do_command(cmd)
        if game.is_game_over():
            break
    print("\n" + "=" * 60)
    print(
        f"WON: {game.is_won()}   GAME_OVER: {game.is_game_over()}   "
        f"SCORE: {game.score}/{game.max_score}"
    )
    return game


if __name__ == "__main__":
    import sys

    if "--walk" in sys.argv:
        _run(WALKTHROUGH)
    else:
        build_game().game_loop()
