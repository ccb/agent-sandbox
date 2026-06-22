"""Action Castle III -- "Beneath Action Castle" -- on the text_adventure_games engine.

A faithful port of the Parsely game (Action Castle III), authored the same way as its
siblings ``action_castle.py`` / ``action_castle_2.py``: a ``build_game()`` that assembles
locations / items / characters, a small ``ActionCastle3`` Game subclass holding the score
and ending logic, custom ``Action`` subclasses for the novel verbs, follower behaviors for
the party, and reaction *triggers* for the world's set-pieces.

WHAT MAKES AC3 DIFFERENT:  it's a party-based dungeon crawl. You recruit four companions
-- an elf, a dwarf, a cleric and a wizard -- each of whom unlocks an ability-verb (SHOOT
SPIDER, USE HATCHET, TURN UNDEAD, CAST SLEEP, USE WAND), and almost every obstacle is
gated on having the right companion present with the right item. It's not a single win:
the game ends when you GO NORTH home, and one of several EPILOGUES is chosen by your
progress (max 100 points). The best ending banishes the Chaos demon AND kills the cultist.

PORTED IN PHASES (this file grows over several PRs, like AC2 did):
  * Phase 1 (engine): a reusable Darkness block (text_adventure_games.blocks.Darkness).
  * Phase 2: the world skeleton -- all rooms, exits, the three regions off the Crossroads
    hub, start inventory (a backpack container), the darkness-gated cave and dungeon
    descents, populated rooms, and the GO-NORTH-home ending stub.
  * Phase 3 (engine + THIS): GET reaches into carried containers; recruiting the party --
    INVITE (the engine follow/refusal mechanism), and the rescue chains that unlock the
    cleric (give water + free) and the dwarf (drive off the spider, free, heal the poison).
  * Phases 4-5 (TODO): the ability-verbs (SHOOT SPIDER, USE HATCHET, CAST SLEEP, USE WAND,
    TURN UNDEAD) and the puzzle chain (bow/sleep, spider, webs, baby + stew, goblin queen,
    pendant/crypt, ooze/lockbox/crown, slide trap); the endgame (javelin summons + banishes
    the demon, push the cultist) and the scored epilogues.

Run interactively:   python action_castle_3.py
"""

from text_adventure_games import games, things, actions, blocks
from text_adventure_games.enums import Property

# ---------------------------------------------------------------------------
# Helpers (shared with the patterns used in action_castle_2.py)
# ---------------------------------------------------------------------------


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s canonical auto-reverse, so a
    pair of non-opposite exits (ENTER CAVERN in, UP out) doesn't wire a phantom
    reverse and leave two exits pointing at the same room."""
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


def _die(game, text):
    """End the game with a death/THE END message."""
    game.parser.ok(text)
    game.game_over = True
    game.game_over_description = text


def _relocate(game, character, dest_name):
    """Move *character* to the named location, dragging any followers along
    (the party travels together). Routes through the engine chokepoint."""
    dest = game.locations[dest_name]
    game.relocate(character, dest)
    game.drag_followers(character)
    return dest


def _all_held(character):
    """inventory + worn + wielded -- everything the character is holding."""
    return {**character.inventory, **character.worn, **character.wielded}


def _is_holding(character, name):
    """True if the character is carrying/wearing/wielding an item by name, or
    has it inside an open carried container (the backpack)."""
    if name in _all_held(character):
        return True
    for item in character.inventory.values():
        if name in item.accessible_contents():
            return True
    return False


def _take_held(character, name):
    """Remove and return a held item by name -- from hands/worn/wielded or an
    open carried container -- else None."""
    for store in (character.inventory, character.worn, character.wielded):
        if name in store:
            return store.pop(name)
    for item in character.inventory.values():
        if name in item.accessible_contents():
            held = item.contents[name]
            item.remove_item(held)
            return held
    return None


def _fixture(name, description, examine_text=""):
    """A scenery item -- examinable but not gettable (springs, statues, pits)."""
    it = things.Item(name, description, examine_text or description)
    it.set_property(Property.GETTABLE, False)
    return it


def _item(name, description, examine_text=""):
    """A gettable item."""
    return things.Item(name, description, examine_text or description)


# ---------------------------------------------------------------------------
# Game subclass: scoring + ending
# ---------------------------------------------------------------------------


class ActionCastle3(games.Game):
    """The adventure ends by GOing NORTH home; an epilogue is chosen by progress.
    The best ending banishes the demon AND kills the Chaos cultist."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        self.score = 0
        # Scoring is event-based (rulebook page 28), not per-location; total 100.
        self.max_score = 100
        self._scored_keys = set()

    def award(self, key, points, msg=None):
        """Add *points* once per *key* (idempotent), optionally announcing *msg*."""
        if key in self._scored_keys:
            return
        self._scored_keys.add(key)
        self.score += points
        if msg:
            self.parser.ok(msg)

    def is_won(self) -> bool:
        # The "TO BE CONTINUED!" ending: the demon banished and the cultist dead.
        p = self.player
        return bool(
            p.get_property("banished_demon") and p.get_property("killed_cultist")
        )


# ---------------------------------------------------------------------------
# Custom actions
# ---------------------------------------------------------------------------


class GoHome(actions.Action):
    """Return home up the northern road, ending the adventure. The rulebook asks
    "Are you sure?"; we pose that as a yes/no prompt (engine #110), and on YES we
    relocate to Home, where an arrival trigger reads the epilogue."""

    ACTION_NAME = "go home"
    ACTION_DESCRIPTION = "Return home up the northern road (ends the adventure)"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.game.player

    def check_preconditions(self) -> bool:
        if (
            self.character.location is None
            or self.character.location.name != "Crossroads"
        ):
            self.parser.fail("The road home lies north of the Crossroads.")
            return False
        return True

    def apply_effects(self):
        from text_adventure_games import Prompt

        self.parser.ok("Are you sure you want to return home and end your adventure?")
        self.game.pose_prompt(
            Prompt(
                text="Return home and end your adventure?",
                options={"yes": "confirm home", "no": "stay"},
                speaker="narrator",
            )
        )


class ConfirmHome(actions.Action):
    """The YES branch of GoHome's prompt: go home for good."""

    ACTION_NAME = "confirm home"
    ACTION_DESCRIPTION = "Confirm returning home"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.game.player

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        self.parser.ok("You set off up the northern road toward home.")
        _relocate(self.game, self.character, "Home")  # arrival trigger -> epilogue


class Stay(actions.Action):
    """The NO branch: think better of it and stay."""

    ACTION_NAME = "stay"
    ACTION_DESCRIPTION = "Decide not to go home yet"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        self.parser.ok("You decide your adventure isn't over yet.")


# ---------------------------------------------------------------------------
# The party: recruitment (#112 follow) + the chains that unlock it
# ---------------------------------------------------------------------------
#
# Companions follow the player (Game.drag_followers cascades the whole party
# along), and an ability-verb is gated on the right companion being present.
# A companion that isn't recruitable yet REFUSES to follow (the engine's
# refuses_follow / follow_refusal_message): the elf and wizard join on sight,
# while the cleric and dwarf must be rescued first (give water + free; free +
# heal the poison). Clearing the refusal is what "rescues" them.


def _present(game, name):
    """The named character if it's in the player's location, else None."""
    return game.player.location.characters.get(name) if game.player.location else None


def _in_party(game, name):
    """The named character if it has joined the party (is following you) and is
    here with you, else None. Ability-verbs gate on this."""
    ch = _present(game, name)
    return ch if (ch is not None and ch.following is game.player) else None


class Invite(actions.Action):
    """Recruit a co-located character into the party (rulebook: INVITE <X>).

    Routes through the engine's following mechanism: a recruit that isn't ready
    refuses (refuses_follow), so INVITE reports why ("too weak to follow"); once
    its chain is done the refusal is cleared and INVITE makes it follow. Each
    companion prints its own join line (``join_text``); rescuing the cleric or
    dwarf scores."""

    ACTION_NAME = "invite"
    ACTION_DESCRIPTION = "Invite a companion to join your party"
    ACTION_ALIASES = ["recruit"]

    SCORES = {"cleric": ("cleric", 10), "dwarf": ("dwarf", 10)}

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        # The target is the named character in the room (never the player).
        self.target = self.parser.get_character(
            command, hint="companion", exclude=self.player
        )

    def check_preconditions(self) -> bool:
        if self.target is None or self.target.location is not self.player.location:
            self.parser.fail("There's no one here by that name to invite.")
            return False
        if self.target.following is self.player:
            self.parser.fail(f"{self.target.name.capitalize()} is already with you.")
            return False
        if self.target.get_property("refuses_follow"):
            self.parser.fail(
                self.target.get_property("follow_refusal_message")
                or f"{self.target.name.capitalize()} won't come with you yet."
            )
            return False
        return True

    def apply_effects(self):
        self.target.following = self.player
        self.parser.ok(
            getattr(self.target, "join_text", None)
            or f"{self.target.name.capitalize()} joins your party."
        )
        scored = self.SCORES.get(self.target.name)
        if scored:
            key, points = scored
            self.game.award(key, points)


class FillWaterskin(actions.Action):
    """Fill the waterskin at the spring (Cavern Entrance)."""

    ACTION_NAME = "fill waterskin"
    ACTION_DESCRIPTION = "Fill your waterskin at the spring"
    ACTION_ALIASES = ["fill the waterskin", "fill waterskin at spring"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Cavern Entrance":
            self.parser.fail("There's no spring here to fill it from.")
            return False
        if not _is_holding(self.player, "waterskin"):
            self.parser.fail("You have no waterskin to fill.")
            return False
        return True

    def apply_effects(self):
        skin = _held_item(self.player, "waterskin")
        skin.set_property("has_water", True)
        self.parser.ok("You replenish your water supply.")


def _held_item(character, name):
    """The held Item by name, including inside a carried open container."""
    held = _all_held(character)
    if name in held:
        return held[name]
    for item in character.inventory.values():
        if name in item.accessible_contents():
            return item.contents[name]
    return None


def _heal_cleric_if_ready(game, cleric):
    """Once the captive has been given water AND freed, he heals himself and is
    ready to be invited (the refusal lifts)."""
    if cleric.get_property("given_water") and cleric.get_property("freed"):
        if cleric.get_property("refuses_follow"):
            cleric.set_property("refuses_follow", False)
            game.parser.ok(
                'The cleric invokes a prayer -- "By the Power of the Light..." -- '
                "and his wounds knit shut. He climbs to his feet, restored."
            )


class GiveWater(actions.Action):
    """Give the tortured cleric a drink (rulebook: he croaks 'Water...')."""

    ACTION_NAME = "give water"
    ACTION_DESCRIPTION = "Give water to the tortured man"
    ACTION_ALIASES = ["give water to man", "give water to cleric", "give the man water"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.cleric = _present(game, "cleric")

    def check_preconditions(self) -> bool:
        if self.cleric is None:
            self.parser.fail("There's no one here who needs water.")
            return False
        skin = _held_item(self.player, "waterskin")
        if skin is None or not skin.get_property("has_water"):
            self.parser.fail("Your waterskin is empty.")
            return False
        return True

    def apply_effects(self):
        skin = _held_item(self.player, "waterskin")
        skin.set_property("has_water", False)
        self.cleric.set_property("given_water", True)
        self.parser.ok("The man drinks greedily. Some color returns to his face.")
        _heal_cleric_if_ready(self.game, self.cleric)


class FreeCaptive(actions.Action):
    """Cut the tortured cleric loose from the table."""

    ACTION_NAME = "free man"
    ACTION_DESCRIPTION = "Free the tortured man from his bonds"
    ACTION_ALIASES = [
        "free cleric",
        "untie man",
        "untie cleric",
        "release man",
        "free the man",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.cleric = _present(game, "cleric")

    def check_preconditions(self) -> bool:
        if self.cleric is None:
            self.parser.fail("There's no one here to free.")
            return False
        if self.cleric.get_property("freed"):
            self.parser.fail("He's already free.")
            return False
        return True

    def apply_effects(self):
        self.cleric.set_property("freed", True)
        self.parser.ok("You cut the man loose from the table.")
        _heal_cleric_if_ready(self.game, self.cleric)


class FreeDwarf(actions.Action):
    """Cut the cocooned dwarf down. Fatal if the spider is still here -- you must
    drive it off (SHOOT SPIDER) first."""

    ACTION_NAME = "free dwarf"
    ACTION_DESCRIPTION = "Cut the captured dwarf out of his cocoon"
    ACTION_ALIASES = [
        "free the dwarf",
        "cut dwarf loose",
        "untie dwarf",
        "release dwarf",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.dwarf = _present(game, "dwarf")
        self.spider = _present(game, "spider")

    def check_preconditions(self) -> bool:
        if self.dwarf is None:
            self.parser.fail("There's no captive dwarf here.")
            return False
        if self.dwarf.get_property("freed"):
            self.parser.fail("The dwarf is already free.")
            return False
        return True

    def apply_effects(self):
        if self.spider is not None and not self.spider.get_property("driven_off"):
            _die(
                self.game,
                "The spider pounces as you approach, sinking its fangs into your body. "
                "Paralyzed, you're wrapped in a cocoon and hung from the ceiling. THE END.",
            )
            return
        self.dwarf.set_property("freed", True)
        self.parser.ok(
            "You cut the dwarf's bonds. He slumps down, too weak to move -- a pair of "
            "puncture marks on his leg ooze a dark, foul-smelling poison."
        )


class HealDwarf(actions.Action):
    """The cleric cures the dwarf's spider poison so he can travel."""

    ACTION_NAME = "heal dwarf"
    ACTION_DESCRIPTION = "Have the cleric heal the poisoned dwarf"
    ACTION_ALIASES = ["cure dwarf", "heal the dwarf"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.dwarf = _present(game, "dwarf")
        self.cleric = _in_party(game, "cleric")

    def check_preconditions(self) -> bool:
        if self.dwarf is None:
            self.parser.fail("There's no dwarf here to heal.")
            return False
        if self.cleric is None:
            self.parser.fail("Only the cleric can heal him, and he isn't here.")
            return False
        if not self.dwarf.get_property("freed"):
            self.parser.fail("He's still cocooned -- free him first.")
            return False
        if not self.dwarf.get_property("poisoned"):
            self.parser.fail("The dwarf isn't poisoned.")
            return False
        return True

    def apply_effects(self):
        self.dwarf.set_property("poisoned", False)
        self.dwarf.set_property("refuses_follow", False)  # now fit to join
        self.parser.ok(
            "The cleric utters a prayer and the poisoned bite is healed. The dwarf "
            "stands, hefting his pickaxe."
        )


# ---------------------------------------------------------------------------
# The bow chain: search -> pendant -> crypt (turn undead) -> spell book ->
# wizard -> CAST SLEEP -> bow -> elf. This is the long interlock that arms the
# elf so she can later drive off the spider; it threads the cleric (pendant) and
# wizard (spell book) abilities through it.
# ---------------------------------------------------------------------------


class Search(actions.Action):
    """Search the dungeon cells -- turns up a pewter holy symbol (the pendant)."""

    ACTION_NAME = "search"
    ACTION_DESCRIPTION = "Search your surroundings"
    ACTION_ALIASES = ["search cells", "search the cells"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        loc = self.player.location
        if (
            loc is not None
            and loc.name == "Dungeon"
            and not loc.get_property("searched")
        ):
            loc.set_property("searched", True)
            pendant = _item(
                "pendant",
                "a pewter holy symbol",
                "A holy symbol shaped like a fist holding a lightning bolt. Cheap "
                "pewter, worth only a few copper pieces.",
            )
            loc.add_item(pendant)
            self.parser.ok(
                "You search the cells and find a shiny pendant buried under the straw."
            )
        else:
            self.parser.ok("You search around but find nothing of interest.")


class GivePendantToCleric(actions.Action):
    """Hand the holy symbol to the cleric -- with it he can turn the undead."""

    ACTION_NAME = "give pendant to cleric"
    ACTION_DESCRIPTION = "Give the holy symbol to the cleric"
    ACTION_ALIASES = [
        "give the pendant to the cleric",
        "give cleric pendant",
        "give pendant",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.cleric = _in_party(game, "cleric")

    def check_preconditions(self) -> bool:
        if self.cleric is None:
            self.parser.fail("The cleric isn't here with you.")
            return False
        if not _is_holding(self.player, "pendant"):
            self.parser.fail("You have no pendant to give.")
            return False
        return True

    def apply_effects(self):
        self.cleric.add_to_inventory(_take_held(self.player, "pendant"))
        self.cleric.set_property("has_pendant", True)
        self.parser.ok(
            '"Thank you! With this I can destroy any undead that plagues the living," '
            "says the cleric."
        )


class TurnUndead(actions.Action):
    """The cleric turns the risen skeletons to ash (needs the pendant)."""

    ACTION_NAME = "turn undead"
    ACTION_DESCRIPTION = "Have the cleric turn the undead"
    ACTION_ALIASES = ["use pendant", "use the pendant", "turn the undead"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.cleric = _in_party(game, "cleric")

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Crypt":
            self.parser.fail("There's nothing unholy here to turn.")
            return False
        if self.cleric is None or not self.cleric.get_property("has_pendant"):
            self.parser.fail("Only the cleric, holding his holy symbol, can do that.")
            return False
        return True

    def apply_effects(self):
        self.player.location.set_property("skeletons_cleared", True)
        self.parser.ok(
            "A flash of light from the pendant turns the skeletal warriors to ash."
        )


class TakeBook(actions.Action):
    """Take the spell book from the skeleton's grip. The skeletons rise -- the
    cleric (with the pendant) must turn them, or you join their ranks."""

    ACTION_NAME = "take book"
    ACTION_DESCRIPTION = "Take the spell book from the skeleton"
    ACTION_ALIASES = [
        "take spell book",
        "take spellbook",
        "take the spell book",
        "get spell book",
        "get spellbook",
        "get book",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.cleric = _in_party(game, "cleric")

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Crypt":
            self.parser.fail("There's no spell book here.")
            return False
        return True

    def apply_effects(self):
        loc = self.player.location
        book = loc.items.get("spell book")
        cleric_ready = self.cleric is not None and self.cleric.get_property(
            "has_pendant"
        )
        if not loc.get_property("skeletons_cleared"):
            if cleric_ready:
                loc.set_property("skeletons_cleared", True)
                self.parser.ok(
                    "The skeletal warriors rise, weapons drawn -- but the cleric "
                    "raises his pendant and a flash of light turns them to ash."
                )
            else:
                _die(
                    self.game,
                    "The skeletal warriors rise, weapons drawn. They close in, and you "
                    "soon join their unholy ranks! THE END.",
                )
                return
        if book is not None:
            book.set_property(Property.GETTABLE, True)
            loc.remove_item(book)
            self.player.add_to_inventory(book)
            self.parser.ok("You take the spell book.")


class GiveSpellbookToWizard(actions.Action):
    """Return the wizard's lost spell book -- and with it, his magic (CAST SLEEP)."""

    ACTION_NAME = "give spell book to wizard"
    ACTION_DESCRIPTION = "Return the spell book to the wizard"
    ACTION_ALIASES = [
        "give spellbook to wizard",
        "give book to wizard",
        "give the spell book to the wizard",
        "show spell book to wizard",
        "show the wizard the spell book",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.wizard = _in_party(game, "wizard")

    def check_preconditions(self) -> bool:
        if self.wizard is None:
            self.parser.fail("The wizard isn't here with you.")
            return False
        if not _is_holding(self.player, "spell book"):
            self.parser.fail("You have no spell book to give.")
            return False
        return True

    def apply_effects(self):
        self.wizard.add_to_inventory(_take_held(self.player, "spell book"))
        self.wizard.set_property("has_spellbook", True)
        self.game.award(
            "spellbook",
            5,
            '"My spell book! I must have dropped it when I fled the crypt," says the '
            "wizard, leafing through it eagerly.",
        )


class CastSleep(actions.Action):
    """The wizard casts Sleep. Its use here: put the bandits under so you can
    take the elf's bow (needs the wizard and his returned spell book)."""

    ACTION_NAME = "cast sleep"
    ACTION_DESCRIPTION = "Have the wizard cast the Sleep spell"
    ACTION_ALIASES = [
        "cast sleep on bandits",
        "cast the sleep spell",
        "cast sleep spell",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.wizard = _in_party(game, "wizard")
        self.bandits = _present(game, "bandits")

    def check_preconditions(self) -> bool:
        if self.wizard is None or not self.wizard.get_property("has_spellbook"):
            self.parser.fail("You'd need the wizard and his spell book to cast that.")
            return False
        if self.bandits is None or self.bandits.get_property("asleep"):
            self.parser.fail("There's no one here to put to sleep.")
            return False
        return True

    def apply_effects(self):
        self.bandits.set_property("asleep", True)
        bow = self.game.locations["Bandit Camp"].items.get("bow")
        if bow is not None:
            bow.set_property(Property.GETTABLE, True)
        self.parser.ok(
            "The wizard intones the Spell of Sleep. One by one the bandits slump "
            "snoring to the ground. The elvish bow lies unguarded."
        )


class GiveBowToElf(actions.Action):
    """Return the elf's bow -- armed, she can shoot the spider (a later step)."""

    ACTION_NAME = "give bow to elf"
    ACTION_DESCRIPTION = "Return the bow to the elf"
    ACTION_ALIASES = ["give the bow to the elf", "give elf bow", "give bow"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.elf = _in_party(game, "elf")

    def check_preconditions(self) -> bool:
        if self.elf is None:
            self.parser.fail("The elf isn't here with you.")
            return False
        if not _is_holding(self.player, "bow"):
            self.parser.fail("You have no bow to give.")
            return False
        return True

    def apply_effects(self):
        self.elf.add_to_inventory(_take_held(self.player, "bow"))
        self.elf.set_property("has_bow", True)
        self.game.award(
            "bow",
            5,
            'The elf takes up her bow. "Now I can fight at your side!"',
        )


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> ActionCastle3:
    L = things.Location

    # --- Locations ---------------------------------------------------------
    # Surface
    crossroads = L(
        "Crossroads",
        "You stand at a crossroads. The ruins of the once-glorious Action Castle lie to "
        "the east. A dark forest looms to the west. The road north will take you home.",
    )
    dark_forest = L(
        "Dark Forest",
        "You stand at the edge of a dark forest. Smoke rises to the west. A trail leads "
        "south. Through the trees you spy a shadowy figure watching your every move.",
    )
    bandit_camp = L(
        "Bandit Camp",
        "Through the trees you spy a clearing where a group of bandits has made camp. A "
        "stew pot hangs over their campfire.",
    )
    cavern_entrance = L(
        "Cavern Entrance",
        "You come across an outcrop of mossy boulders. A gap between the rocks leads down "
        "into darkness. A natural spring bubbles up from the ground nearby.",
    )
    # Caves
    dark_cavern = L(
        "Dark Cavern",
        "You emerge into a large cavern. A steep slope leads back to the surface. To the "
        "east is a cramped passage. You hear soft mewling cries from a crack in the wall.",
    )
    fissure = L(
        "Fissure",
        "You're barely able to squeeze in. Wedged deep inside is a bundle wrapped in rags.",
    )
    mushroom_garden = L(
        "Mushroom Garden",
        "You are in a wide chamber carpeted with purple-spotted cave mushrooms. To the "
        "south is a tunnel choked with cobwebs. A cramped passage leads west.",
    )
    spider_lair = L(
        "Spider Lair",
        "The tunnel ends in a large web that spans the western exit, beyond which is a "
        "sheer drop-off. A narrow tunnel leads north. A pair of bodies hangs from the ceiling.",
    )
    deep_ravine = L(
        "Deep Ravine",
        "Steps carved into the rock lead down from the eastern tunnel into a deep ravine. "
        "A flock of leathery-winged creatures feeds on the body of a large spider.",
    )
    goblin_caves = L(
        "Goblin Caves",
        "A maze of twisting passages, switchbacks and flooded grottoes. The air smells of "
        "goblins.",
    )
    throne_room = L(
        "Throne Room",
        "Balanced atop a pile of treasure is an ornate gold throne. On it sits a diminutive "
        "goblin dressed in furs, feathers and looted jewelry.",
    )
    # Castle / temple
    castle_ruins = L(
        "Castle Ruins",
        "All that's left of Action Castle is this courtyard, a lonely tower and a few "
        "crumbling walls. A rickety stairway leads up to the tower; a dark stairwell "
        "descends to the dungeon.",
    )
    wizard_tower = L(
        "Wizard's Tower",
        "The tower is cluttered with old books. A wizard is here, peering through a telescope.",
    )
    dungeon = L(
        "Dungeon",
        "You enter the dungeon. A dark corridor runs east to west. A stone stair leads up. "
        "There are a few dark and dingy cells here.",
    )
    vault = L(
        "Vault",
        "A vaulted chamber filled with broken crates and empty shelves, looted long ago. "
        "A large stone statue stands here.",
    )
    dark_corridor = L(
        "Dark Corridor",
        "A long, dark corridor. At the far end is an iron door covered in spikes. There "
        "are some human remains here.",
    )
    torture_chamber = L(
        "Torture Chamber",
        "A blood-spattered chamber. An iron maiden stands in the corner. A man is tied "
        "down, stretched across a wooden table.",
    )
    sanctum = L(
        "Sanctum",
        "The inner sanctum of a hidden temple. A large tome rests on a lectern. A spiral "
        "staircase leads up. You smell burning incense to the west.",
    )
    chaos_chapel = L(
        "Chaos Chapel",
        "The chapel is lit by flickering oil lamps, thick with incense. In the center is a "
        "large pit ringed with spikes. To the south is the crypt.",
    )
    crypt = L(
        "Crypt",
        "A long, narrow chamber adorned with skulls and bones. Many skeletal bodies are "
        "entombed here, still clad in mouldering armor.",
    )
    # The road home -- arriving here ends the game (see the epilogue trigger).
    home = L(
        "Home", "The road winds north, back toward your village and the life you knew."
    )

    # --- Connections -------------------------------------------------------
    # Surface hub
    crossroads.add_connection(
        "east", castle_ruins
    )  # auto: castle_ruins west -> crossroads
    crossroads.add_connection(
        "west", dark_forest
    )  # auto: dark_forest east -> crossroads
    _one_way(
        crossroads, "north", home
    )  # GoHome confirms first; this is the literal road
    dark_forest.add_connection("south", cavern_entrance)
    dark_forest.add_connection("west", bandit_camp)
    # Caves (enter cavern / enter fissure are custom one-way exits; UP/OUT lead back)
    _one_way(cavern_entrance, "enter cavern", dark_cavern)
    _one_way(dark_cavern, "up", cavern_entrance)
    dark_cavern.add_connection("east", mushroom_garden)
    _one_way(dark_cavern, "enter fissure", fissure)
    _one_way(fissure, "out", dark_cavern)
    mushroom_garden.add_connection("south", spider_lair)
    spider_lair.add_connection("west", deep_ravine)  # web-blocked (TODO Phase 4)
    _one_way(deep_ravine, "down", goblin_caves)
    _one_way(goblin_caves, "north", deep_ravine)
    goblin_caves.add_connection("east", throne_room)
    # Castle / temple
    castle_ruins.add_connection("up", wizard_tower)
    castle_ruins.add_connection("down", dungeon)  # darkness-gated
    dungeon.add_connection("west", vault)
    dungeon.add_connection("east", dark_corridor)
    dark_corridor.add_connection("east", torture_chamber)  # door-gated (TODO Phase 4)
    torture_chamber.add_connection("down", sanctum)  # iron-maiden-gated (TODO Phase 4)
    sanctum.add_connection("west", chaos_chapel)
    chaos_chapel.add_connection("south", crypt)

    # --- Darkness gates (engine Darkness block) ----------------------------
    # You can't enter the caverns or descend to the dungeon without a lit lantern.
    cavern_entrance.add_block("enter cavern", blocks.Darkness(cavern_entrance))
    castle_ruins.add_block("down", blocks.Darkness(castle_ruins))

    # --- World items -------------------------------------------------------
    bandit_camp.add_item(
        _fixture(
            "pot",
            "a stew pot",
            "It's empty now, but you could cook a meal if you had ingredients.",
        )
    )
    bandit_camp.add_item(
        _fixture(
            "bow",
            "a fine elvish bow",
            "A fine elvish bow -- strong, supple and light as a feather. A bandit is admiring it.",
        )
    )
    cavern_entrance.add_item(
        _fixture(
            "spring",
            "a natural spring",
            "The water looks clean and clear, but looks can be deceiving.",
        )
    )
    fissure.add_item(
        _item(
            "bundle",
            "a bundle wrapped in rags",
            "A wrinkly green face with yellow catlike eyes and a tuft of red hair. It's a baby goblin, probably abandoned.",
        )
    )
    mushroom_garden.add_item(
        _fixture(
            "mushrooms",
            "purple-spotted cave mushrooms",
            "The purple-spotted mushrooms are carefully laid out in rows.",
        )
    )
    spider_lair.add_item(
        _fixture(
            "web",
            "a thick spiderweb",
            "A spiderweb blocks the passage west. A large wolf spider sits in the center, venom dripping from its fangs.",
        )
    )
    spider_lair.add_item(
        _fixture(
            "bodies",
            "two cocooned bodies",
            "A desiccated goblin corpse and a freshly caught dwarf wrapped in spider silk. The dwarf struggles weakly.",
        )
    )
    wizard_tower.add_item(
        _fixture(
            "telescope", "a brass telescope", "A telescope pointed at the night sky."
        )
    )
    wizard_tower.add_item(
        _fixture(
            "books",
            "shelves of occult tomes",
            "A dizzying array of occult tomes. One you can read is a journal: Ecology of the Ooze.",
        )
    )
    wizard_tower.add_item(
        _item(
            "wand",
            "an icy wand",
            "Carved from a piece of ice and covered in runes. One rune still glows with dim blue light.",
        )
    )
    dungeon.add_item(
        _fixture(
            "cells",
            "dingy cells",
            "The dirty cells are empty save for straw bedding strewn about.",
        )
    )
    vault.add_item(
        _fixture(
            "statue",
            "a large stone statue",
            "A stern figure clad in armor, its fist raised to the heavens. Some fingers are broken off, as if something was pried loose.",
        )
    )
    dark_corridor.add_item(
        _fixture(
            "remains",
            "grisly human remains",
            "A pair of severed arms clutching a small metal lockbox. The stone underneath is stained and corroded.",
        )
    )
    torture_chamber.add_item(
        _fixture(
            "iron maiden",
            "a rusting iron maiden",
            "A rusting metal sarcophagus cast in the shape of a young woman.",
        )
    )
    sanctum.add_item(
        _fixture(
            "tome",
            "a large leather-bound tome",
            "Opened to an illustration of an armored man throwing a lightning bolt at a massive horned demon.",
        )
    )
    chaos_chapel.add_item(
        _fixture(
            "pit", "a spiked pit", "It's deep and dark; you cannot see the bottom."
        )
    )
    crypt.add_item(
        _fixture(
            "skeletal bodies",
            "armored skeletons",
            "One of the skeletons grips a spell book in its bony hands.",
        )
    )
    # The spell book is in a skeleton's grip; TAKE BOOK is the real path (it
    # wakes the skeletons), so it starts non-gettable as a backstop against a
    # plain GET sneaking it out without consequence.
    spell_book = _item(
        "spell book",
        "an arcane spell book",
        "It's covered in cosmological symbols. The contents are indecipherable to you.",
    )
    spell_book.set_property(Property.GETTABLE, False)
    crypt.add_item(spell_book)

    # --- Characters --------------------------------------------------------
    player = things.Character(
        name="adventurer",
        description="a brave adventurer delving beneath Action Castle",
        persona="I am an adventurer seeking glory beneath the ruins of Action Castle.",
    )

    # The four would-be companions. The elf and wizard join on sight; the cleric
    # and dwarf REFUSE (refuses_follow) until rescued -- clearing the refusal is
    # what recruits them. Each has a join_text the Invite action prints.
    elf = things.Character(
        "elf",
        "a green-cloaked elf with pointed ears",
        "I am an elf who fled bandits in the ruins.",
    )
    elf.talk_text = '"A group of bandits ambushed me in the ruins. I dropped my bow during my escape."'
    elf.join_text = 'The elf clasps your wrist. "Together, nothing can stop us!"'

    wizard = things.Character(
        "wizard",
        "an old wizard in star-spangled blue robes",
        "I am a wizard who has misplaced his spell book.",
    )
    wizard.talk_text = '"Have you come across a spell book in your travels? I seem to have misplaced mine!"'
    wizard.join_text = 'The wizard puts on his hat. "May the stars guide us!"'

    dwarf = things.Character(
        "dwarf",
        "a stout, red-bearded dwarf, wounded and poisoned",
        "I am a dwarf who was searching for gold when the spider ambushed me.",
    )
    dwarf.talk_text = '"I was searching for gold and gems when the spider ambushed me!"'
    dwarf.join_text = 'The dwarf hefts his pickaxe. "Aye, let\'s go bash some heads!"'
    # Cocooned and poisoned: must be freed (FREE DWARF, only safe once the spider
    # is driven off) and healed (HEAL DWARF, by the cleric) before he'll join.
    dwarf.set_property("refuses_follow", True)
    dwarf.set_property(
        "follow_refusal_message", "The dwarf is in no shape to travel yet."
    )
    dwarf.set_property("freed", False)
    dwarf.set_property("poisoned", True)

    # The captured cleric -- named "cleric" (the rulebook calls him "the man"
    # until rescued; his description keeps that flavor). He must be given water
    # and freed before he heals himself and can be invited.
    cleric = things.Character(
        "cleric",
        "a tortured man with a lightning-bolt sigil on his tabard -- a captive cleric",
        "I am a cleric of the Lord of Law, taken and tortured by the cultists.",
    )
    cleric.talk_text = '"Water..."'
    cleric.join_text = '"By the Light, we shall defeat the forces of Chaos!"'
    cleric.set_property("refuses_follow", True)
    cleric.set_property("follow_refusal_message", "The man is too weak to follow you.")
    cleric.set_property("given_water", False)
    cleric.set_property("freed", False)

    spider = things.Character(
        "spider",
        "a wolf spider the size of a small horse",
        "I am a great wolf spider, nearly camouflaged against the rock.",
    )
    spider.set_property("driven_off", False)

    bandits = things.Character(
        "bandits",
        "a group of bandits gathered around a campfire",
        "We are bandits. Don't even think about it.",
    )
    bandits.talk_text = "The bandits jeer and wave you off."
    bandits.set_property("asleep", False)
    queen = things.Character(
        "goblin queen",
        "the goblin queen, in looted finery",
        "I am the goblin queen. Tribute!",
    )
    queen.talk_text = 'The goblin queen shrieks, "Tribute!"'

    dark_forest.add_character(elf)
    wizard_tower.add_character(wizard)
    spider_lair.add_character(dwarf)
    spider_lair.add_character(spider)
    torture_chamber.add_character(cleric)
    throne_room.add_character(queen)
    bandit_camp.add_character(bandits)

    # --- Player start inventory --------------------------------------------
    # The rulebook starts you with a backpack containing a lantern, dagger,
    # lockpicks and a waterskin. GET reaches into a carried open container, so
    # the player pulls gear out of the pack as needed ("take lantern", "light
    # lantern"). DROP BACKPACK (the fissure puzzle) drops the whole kit.
    backpack = _item("backpack", "a sturdy leather backpack").make_container()
    lantern = _item("lantern", "a brass lantern", "A brass lantern, currently unlit.")
    lantern.set_property(Property.FLAMMABLE, True)
    lantern.set_property(Property.IS_LIT, False)
    backpack.add_item(lantern)
    backpack.add_item(
        _item("dagger", "a simple dagger", "A plain but serviceable dagger.")
    )
    backpack.add_item(
        _item("lockpicks", "a set of lockpicks", "A slim set of lockpicks.")
    )
    backpack.add_item(
        _item("waterskin", "a waterskin", "A leather waterskin. It's empty.")
    )

    # --- Assemble ----------------------------------------------------------
    characters = [elf, wizard, dwarf, cleric, spider, queen, bandits]
    custom_actions = [
        GoHome,
        ConfirmHome,
        Stay,
        Invite,
        FillWaterskin,
        GiveWater,
        FreeCaptive,
        FreeDwarf,
        HealDwarf,
        Search,
        GivePendantToCleric,
        TurnUndead,
        TakeBook,
        GiveSpellbookToWizard,
        CastSleep,
        GiveBowToElf,
    ]
    game = ActionCastle3(crossroads, player, characters, custom_actions)
    player.add_to_inventory(backpack)

    # Going north ends the adventure: arriving Home reads the epilogue.
    def epilogue(g):
        # Phase 5 will branch this by score/flags; for now, one stub ending.
        g.award("home", 10)
        g.parser.ok(
            "You return to your village. (Scored epilogues arrive in a later phase.)  "
            f"THE END.  (Score: {g.score}/{g.max_score})"
        )
        g.game_over = True
        g.game_over_description = "You returned home."

    game.add_trigger(
        "epilogue_home",
        lambda g: g.player.location is not None and g.player.location.name == "Home",
        epilogue,
        repeatable=False,
    )

    return game


# ---------------------------------------------------------------------------
# Skeleton navigation smoke-path (a real walkthrough comes with the puzzles)
# ---------------------------------------------------------------------------

WALKTHROUGH_SKELETON = [
    "take lantern",  # out of the backpack
    "light lantern",
    "west",  # Crossroads -> Dark Forest
    "south",  # -> Cavern Entrance
    "enter cavern",  # darkness gate: passable now the lantern is lit
    "east",  # Dark Cavern -> Mushroom Garden
    "west",  # back to Dark Cavern
    "up",  # -> Cavern Entrance
    "north",  # -> Dark Forest
    "east",  # -> Crossroads
    "east",  # -> Castle Ruins
    "down",  # darkness gate -> Dungeon
    "up",  # -> Castle Ruins
    "up",  # -> Wizard's Tower
    "down",  # -> Castle Ruins
    "west",  # -> Crossroads
    "go home",
    "yes",  # confirm -> Home -> epilogue
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
        _run(WALKTHROUGH_SKELETON)
    else:
        build_game().game_loop()
