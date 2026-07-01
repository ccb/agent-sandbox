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

COMPLETE -- the port is winnable end to end (WALKTHROUGH scores 100/100). It was
built over several PRs, each driving a reusable engine feature where one was
warranted (like AC2 before it):
  * Engine features extracted along the way: a reusable Darkness block; GET that
    reaches into a carried open container; and a declarative crafting system
    (crafting.py) -- the mushroom stew is a Recipe.
  * The party (elf/dwarf/cleric/wizard) rides on the follow system; recruitment
    is the engine's refuses_follow gate, cleared by each rescue chain.
  * The interlock: pendant -> crypt (turn undead) -> spell book -> wizard ->
    CAST SLEEP -> bow -> elf -> SHOOT SPIDER; dwarf -> USE HATCHET -> the west
    path; freeze the ooze (USE WAND) -> the crown; rescue + feed the baby ->
    past the stirges -> the goblin queen -> baby + crown -> the bronze javelin
    -> banish the demon (THROW JAVELIN) -> kill the cultist (PUSH CULTIST).
  * GO NORTH home ends the adventure with a score-branched epilogue.

Flavor verbs the rulebook calls out, all now ported: topic dialogue (ASK ELF
ABOUT SPRING -- the elf vouches for the spring water; talk_topics), the wizard's
telescope/prophecy (USE TELESCOPE) and the Ecology-of-the-Ooze journal hint
(READ JOURNAL), and the two fatal wrong answers -- FIGHT BANDITS (CAST SLEEP is
the intended path) and ATTACK WIZARD.

Run interactively:   python action_castle_3.py
"""

from text_adventure_games import games, things, actions, blocks, Recipe
from text_adventure_games import reactions
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
    """End the game with a death/THE END message. Thin wrapper over the
    engine's ``Game.end_in_death`` so existing call sites keep their local name."""
    game.end_in_death(text)


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


# The gray ooze drops and digests you if you disturb the lockbox while it lives.
_OOZE_DEATH = (
    "Something slimy and wet drops from the ceiling and engulfs you in corrosive "
    "gray slime. You try to scream, but no sound comes out as you are slowly "
    "dissolved and digested. THE END."
)


# ---------------------------------------------------------------------------
# Game subclass: scoring + ending
# ---------------------------------------------------------------------------


class ActionCastle3(games.Game):
    """The adventure ends by GOing NORTH home; an epilogue is chosen by progress.
    The best ending banishes the demon AND kills the Chaos cultist."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        # Scoring is event-based (rulebook page 28), not per-location; total 100.
        # score / _scored_keys / award() come from the base Game.
        self.max_score = 100

    def is_won(self) -> bool:
        # The "TO BE CONTINUED!" ending: you returned home (the game is over and
        # you're alive) having banished the demon AND killed the cultist. Gated on
        # game_over so it doesn't end the game early -- is_game_over() consults
        # is_won(); the adventure only finishes when you GO NORTH home (or die).
        p = self.player
        return bool(
            self.game_over
            and not p.get_property("is_dead")
            and p.get_property("banished_demon")
            and p.get_property("killed_cultist")
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
        if "water" in skin.contents:
            self.parser.ok("Your waterskin is already full.")
            return
        skin.add_item(_item("water", "spring water", "Cool, clear spring water."))
        self.parser.ok("You fill the waterskin at the spring.")


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


# The gift / use-on-character interactions below are two-object actions -- hold
# X, recipient present, then transfer + side effects -- so they're built with
# the engine's ``use_item_on`` factory (actions/use.py) rather than a bespoke
# Action subclass. Effects reuse the existing held-item helpers, so items move
# exactly as before; party-gated gifts add a ``requires=`` that the recipient be
# following you (mirroring the old ``_in_party`` check).


def _give_water(action):
    _take_held(action.character, "water")  # he drinks it (from the waterskin)
    action.target.set_property("given_water", True)
    action.parser.ok("The man drinks greedily. Some color returns to his face.")
    _heal_cleric_if_ready(action.game, action.target)


GiveWater = actions.use_item_on(
    "give water",
    item="water",
    target="cleric",
    verb="give",
    preposition="to",
    description="Give water to the tortured man",
    aliases=["give water to man", "give water to cleric", "give the man water"],
    effect=_give_water,
    item_missing="You have no water to give -- your waterskin is empty.",
    target_missing="There's no one here who needs water.",
)


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


def _following_or(message):
    """A ``use_item_on`` ``requires`` gate: the matched recipient must be
    following the player (the old ``_in_party`` check), else fail with
    *message*. ``requires`` runs only after the target was matched in the room,
    so ``action.target`` is never None here."""
    return lambda action: (
        None if action.target.following is action.game.player else message
    )


def _give_pendant_to_cleric(action):
    action.target.add_to_inventory(_take_held(action.character, "pendant"))
    action.target.set_property("has_pendant", True)
    action.parser.ok(
        '"Thank you! With this I can destroy any undead that plagues the living," '
        "says the cleric."
    )


GivePendantToCleric = actions.use_item_on(
    "give pendant to cleric",
    item="pendant",
    target="cleric",
    verb="give",
    preposition="to",
    description="Give the holy symbol to the cleric",
    aliases=[
        "give the pendant to the cleric",
        "give cleric pendant",
        "give pendant",
    ],
    requires=_following_or("The cleric isn't here with you."),
    effect=_give_pendant_to_cleric,
    item_missing="You have no pendant to give.",
    target_missing="The cleric isn't here with you.",
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


def _give_spellbook_to_wizard(action):
    action.target.add_to_inventory(_take_held(action.character, "spell book"))
    action.target.set_property("has_spellbook", True)


GiveSpellbookToWizard = actions.use_item_on(
    "give spell book to wizard",
    item="spell book",
    target="wizard",
    verb="give",
    preposition="to",
    description="Return the spell book to the wizard",
    aliases=[
        "give spellbook to wizard",
        "give book to wizard",
        "give the spell book to the wizard",
        "show spell book to wizard",
        "show the wizard the spell book",
    ],
    requires=_following_or("The wizard isn't here with you."),
    effect=_give_spellbook_to_wizard,
    award=(
        "spellbook",
        5,
        '"My spell book! I must have dropped it when I fled the crypt," says the '
        "wizard, leafing through it eagerly.",
    ),
    item_missing="You have no spell book to give.",
    target_missing="The wizard isn't here with you.",
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


def _give_bow_to_elf(action):
    action.target.add_to_inventory(_take_held(action.character, "bow"))
    action.target.set_property("has_bow", True)


GiveBowToElf = actions.use_item_on(
    "give bow to elf",
    item="bow",
    target="elf",
    verb="give",
    preposition="to",
    description="Return the bow to the elf",
    aliases=["give the bow to the elf", "give elf bow", "give bow"],
    requires=_following_or("The elf isn't here with you."),
    effect=_give_bow_to_elf,
    award=(
        "bow",
        5,
        'The elf takes up her bow. "Now I can fight at your side!"',
    ),
    item_missing="You have no bow to give.",
    target_missing="The elf isn't here with you.",
)


# ---------------------------------------------------------------------------
# Spider + web: open the western path out of the Spider Lair
# ---------------------------------------------------------------------------


class ShootSpider(actions.Action):
    """The armed elf shoots the wolf spider, driving it off (rulebook: it
    retreats west). Needed before the dwarf can safely clear the web."""

    ACTION_NAME = "shoot spider"
    ACTION_DESCRIPTION = "Have the elf shoot the spider with her bow"
    ACTION_ALIASES = ["shoot the spider", "fire at spider", "shoot bow at spider"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.elf = _in_party(game, "elf")
        self.spider = _present(game, "spider")

    def check_preconditions(self) -> bool:
        if self.spider is None:
            self.parser.fail("There's no spider here to shoot.")
            return False
        if self.elf is None or not self.elf.get_property("has_bow"):
            self.parser.fail("You'd need the elf and her bow to make that shot.")
            return False
        return True

    def apply_effects(self):
        self.spider.set_property("driven_off", True)
        self.player.location.remove_character(self.spider)  # it flees west
        self.game.award(
            "spider",
            10,
            "The elf draws back her bow and fires an arrow deep into the spider's "
            "abdomen. The creature hisses and retreats through the western exit.",
        )


class UseHatchet(actions.Action):
    """The dwarf hacks the web blocking the western exit -- but only once the
    spider is gone; disturbing the web while it watches is fatal."""

    ACTION_NAME = "use hatchet"
    ACTION_DESCRIPTION = "Have the dwarf clear the web with his hatchet"
    ACTION_ALIASES = [
        "use the hatchet",
        "chop web",
        "cut web",
        "cut the web",
        "clear web",
        "clear the web",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.dwarf = _in_party(game, "dwarf")
        self.spider = _present(game, "spider")

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Spider Lair":
            self.parser.fail("There's no web here to clear.")
            return False
        if loc.get_property("web_cleared"):
            self.parser.fail("The way west is already clear.")
            return False
        if self.dwarf is None:
            self.parser.fail("You have no one here who can hack through the web.")
            return False
        return True

    def apply_effects(self):
        if self.spider is not None and not self.spider.get_property("driven_off"):
            _die(
                self.game,
                "As the dwarf hacks at the web, the spider pounces and sinks its fangs "
                "into you. Paralyzed, you're wrapped in a cocoon. THE END.",
            )
            return
        self.player.location.set_property("web_cleared", True)
        self.parser.ok(
            "The dwarf hacks the great web apart with his hatchet. The way west is clear."
        )


class TakeMushroom(actions.Action):
    """Break off a chunk of cave mushroom (a stew ingredient). Repeatable."""

    ACTION_NAME = "take mushroom"
    ACTION_DESCRIPTION = "Break off a chunk of cave mushroom"
    ACTION_ALIASES = [
        "take cave mushroom",
        "take a mushroom",
        "get mushroom",
        "pick mushroom",
        "take mushrooms",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Mushroom Garden":
            self.parser.fail("There are no mushrooms here.")
            return False
        if not self.player.can_accept_item():
            self.parser.fail("Your hands are full.")
            return False
        return True

    def apply_effects(self):
        self.player.accept_item(
            _item(
                "cave mushroom",
                "a chunk of cave mushroom",
                "A fist-sized hunk of purple-spotted cave mushroom.",
            )
        )
        self.parser.ok(
            "You break off a chunk of cave mushroom and stuff it into your pack."
        )


# ---------------------------------------------------------------------------
# The goblin baby: rescue it, then keep it quiet (it cries on entering a new
# room; mushroom stew sates it). A crying baby is fatal at the Bandit Camp and
# the Deep Ravine -- handled by triggers wired in build_game.
# ---------------------------------------------------------------------------


class TakeBaby(actions.Action):
    """Pick the abandoned goblin baby out of the fissure. It starts crying."""

    ACTION_NAME = "take baby"
    ACTION_DESCRIPTION = "Pick up the goblin baby"
    ACTION_ALIASES = [
        "take bundle",
        "take the baby",
        "take baby goblin",
        "get baby",
        "pick up baby",
        "pick up the baby",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.baby = (
            self.player.location.items.get("baby goblin")
            if self.player.location
            else None
        )

    def check_preconditions(self) -> bool:
        if self.baby is None:
            self.parser.fail("There's no baby here to take.")
            return False
        if not self.player.can_accept_item():
            self.parser.fail("Your hands are full.")
            return False
        return True

    def apply_effects(self):
        self.player.location.remove_item(self.baby)
        self.baby.set_property("gettable", True)
        self.baby.set_property("crying", True)
        self.player.accept_item(self.baby)
        self.game.award(
            "baby_rescue",
            5,
            "The hungry baby shrieks and cries as you pick it up. You can't just "
            "leave the little guy here.",
        )


class DropBaby(actions.Action):
    """You can't abandon the baby (rulebook)."""

    ACTION_NAME = "drop baby"
    ACTION_DESCRIPTION = "Try to put the baby down"
    ACTION_ALIASES = ["drop baby goblin", "drop bundle", "abandon baby", "leave baby"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if not _is_holding(self.player, "baby goblin"):
            self.parser.fail("You're not carrying a baby.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "Being a parent is an awesome responsibility. You can't just abandon "
            "the little guy."
        )


# FEED BABY is "use stew on baby" where the baby is a carried item (the engine
# matches inventory items as targets too). ``requires`` re-imposes the original
# "must be holding the baby" gate, since a dropped baby would otherwise match.
def _feed_baby(action):
    _take_held(action.character, "stew")
    _held_item(action.character, "baby goblin").set_property("crying", False)
    action.parser.ok(
        "The baby greedily eats the mushroom stew, then yawns and falls fast "
        "asleep in your arms."
    )


FeedBaby = actions.use_item_on(
    "feed baby",
    item="stew",
    target="baby goblin",
    verb="feed",
    description="Feed the goblin baby",
    aliases=[
        "feed the baby",
        "feed baby goblin",
        "feed baby stew",
        "give stew to baby",
        "give baby stew",
    ],
    requires=lambda a: (
        None if _is_holding(a.character, "baby goblin") else "You have no baby to feed."
    ),
    effect=_feed_baby,
    item_missing="The baby turns up its nose -- it only wants mushroom stew.",
    target_missing="You have no baby to feed.",
)


# ---------------------------------------------------------------------------
# The goblin queen: the Goblin Caves net trap (SHOW BABY) and the Throne Room
# exchanges (GIVE BABY to be let go; GIVE CROWN as tribute -> the bronze javelin).
# ---------------------------------------------------------------------------


class ShowBaby(actions.Action):
    """Show the netted goblins the baby -- they recognize it and free you."""

    ACTION_NAME = "show baby"
    ACTION_DESCRIPTION = "Show the goblins the baby"
    ACTION_ALIASES = [
        "show the baby",
        "show baby to goblins",
        "show baby goblin",
        "show the goblins the baby",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Goblin Caves":
            self.parser.fail("There's no one here to show the baby to.")
            return False
        if not _is_holding(self.player, "baby goblin"):
            self.parser.fail("You have no baby to show.")
            return False
        return True

    def apply_effects(self):
        self.player.location.set_property("baby_shown", True)
        self.parser.ok(
            "The goblins whisper to one another, and you are freed from the net. "
            "One of them prods you toward the eastern exit with a spear."
        )


def _give_baby(action):
    action.target.add_to_inventory(_take_held(action.character, "baby goblin"))
    action.target.set_property("baby_given", True)


GiveBaby = actions.use_item_on(
    "give baby",
    item="baby goblin",
    target="goblin queen",
    verb="give",
    preposition="to",
    description="Give the baby to the goblin queen",
    aliases=[
        "give baby to queen",
        "give the baby to the queen",
        "give baby goblin",
        "give the queen the baby",
    ],
    effect=_give_baby,
    award=(
        "baby_to_queen",
        5,
        "The goblin queen showers the baby with kisses and coos lovingly at it.",
    ),
    item_missing="You have no baby to give.",
    target_missing="The goblin queen isn't here.",
)


def _give_crown(action):
    action.target.add_to_inventory(_take_held(action.character, "crown"))
    action.target.set_property("crown_given", True)
    action.character.accept_item(
        _item(
            "bronze javelin",
            "a tarnished bronze javelin",
            "A hammered bronze javelin shaped like a lightning bolt.",
        )
    )


GiveCrown = actions.use_item_on(
    "give crown",
    item="crown",
    target="goblin queen",
    verb="give",
    preposition="to",
    description="Give the gold crown to the goblin queen",
    aliases=[
        "give crown to queen",
        "give the crown to the queen",
        "give the queen the crown",
    ],
    effect=_give_crown,
    award=(
        "crown_to_queen",
        5,
        "The goblin queen claps with delight and crowns herself, then rummages "
        "through her hoard and throws a tarnished bronze javelin at your feet. "
        "You pick it up.",
    ),
    item_missing="You have no crown to give.",
    target_missing="The goblin queen isn't here.",
)


# ---------------------------------------------------------------------------
# The gray ooze + the crown: an ooze lurks on the Dark Corridor ceiling; freeze
# it with the wizard's wand, then pick the lockbox for the gold crown (the
# queen's tribute). Disturbing the lockbox while the ooze lives is fatal.
# ---------------------------------------------------------------------------


class LookUp(actions.Action):
    """Look at the ceiling -- in the Dark Corridor, that reveals the gray ooze."""

    ACTION_NAME = "look up"
    ACTION_DESCRIPTION = "Look up at the ceiling"
    ACTION_ALIASES = [
        "look ceiling",
        "look at ceiling",
        "look at the ceiling",
        "examine ceiling",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        loc = self.player.location
        if loc is not None and loc.name == "Dark Corridor":
            loc.set_property("ooze_revealed", True)
            self.parser.ok(
                "Looking up, you see an undulating mass of translucent gray "
                "protoplasm clinging to the ceiling, almost invisible in the "
                "flickering lantern light. A gray ooze!"
            )
        else:
            self.parser.ok("You look up. Nothing out of the ordinary.")


# USE WAND ON OOZE -- a two-object interaction now that the ooze is a real
# fixture (added in build_game). Freezing sets the ooze's own ``is_frozen`` and
# mirrors it onto the location's ``ooze_frozen`` flag, which the lockbox trap
# reads. The ooze lives only in the Dark Corridor, so being elsewhere yields the
# original "nothing here to use the wand on" via target_missing.
def _freeze_ooze(action):
    action.target.set_property("is_frozen", True)
    action.character.location.set_property("ooze_frozen", True)


UseWand = actions.use_item_on(
    "use wand",
    item="wand",
    target="ooze",
    description="Use the icy wand on the ooze",
    aliases=[
        "use wand on ooze",
        "use the wand",
        "use wand on the ooze",
        "use the wand on the ooze",
        "freeze ooze",
        "zap ooze",
    ],
    requires=lambda a: (
        "The ooze is already frozen." if a.target.get_property("is_frozen") else None
    ),
    effect=_freeze_ooze,
    award=(
        "ooze",
        10,
        "A ray of frost from the wand strikes the ceiling. The gray blob "
        "freezes solid, falls to the floor and shatters.",
    ),
    item_missing="You have no wand.",
    target_missing="There's nothing here to use the wand on.",
)


class TakeLockbox(actions.Action):
    """Grab the lockbox from the severed arms -- fatal while the ooze lurks."""

    ACTION_NAME = "take lockbox"
    ACTION_DESCRIPTION = "Take the lockbox"
    ACTION_ALIASES = ["take the lockbox", "get lockbox", "take box", "grab lockbox"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Dark Corridor":
            self.parser.fail("There's no lockbox here.")
            return False
        return True

    def apply_effects(self):
        if not self.player.location.get_property("ooze_frozen"):
            _die(self.game, _OOZE_DEATH)
            return
        self.parser.ok("The lockbox is locked tight. You'll have to pick the lock.")


class PickLock(actions.Action):
    """Pick the lockbox (needs lockpicks) -- inside is the gold crown. Fatal if
    the ooze hasn't been dealt with first."""

    ACTION_NAME = "pick lock"
    ACTION_DESCRIPTION = "Pick the lock on the lockbox"
    ACTION_ALIASES = [
        "pick the lock",
        "pick lockbox",
        "pick the lockbox",
        "unlock lockbox",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Dark Corridor":
            self.parser.fail("There's no lock here to pick.")
            return False
        if not _is_holding(self.player, "lockpicks"):
            self.parser.fail("You have no lockpicks.")
            return False
        lockbox = loc.items.get("lockbox")
        if lockbox is None or "crown" not in lockbox.contents:
            self.parser.fail("You've already emptied the lockbox.")
            return False
        return True

    def apply_effects(self):
        loc = self.player.location
        if not loc.get_property("ooze_frozen"):
            _die(self.game, _OOZE_DEATH)
            return
        lockbox = loc.items["lockbox"]
        crown = lockbox.contents["crown"]
        crown.set_property("gettable", True)
        lockbox.remove_item(crown)
        lockbox.set_property("is_closed", False)
        self.player.accept_item(crown)
        self.parser.ok(
            "It takes time, but you pick the lock. Inside is a gold crown -- you "
            "take it."
        )


class PushStatue(actions.Action):
    """Tampering with the Vault statue springs a slide trap to the caves below."""

    ACTION_NAME = "push statue"
    ACTION_DESCRIPTION = "Push (or pull) the stone statue"
    ACTION_ALIASES = [
        "pull statue",
        "move statue",
        "push the statue",
        "pull the statue",
        "tamper with statue",
        "shove statue",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Vault":
            self.parser.fail("There's no statue here to push.")
            return False
        return True

    def apply_effects(self):
        self.player.location.set_property("trap_sprung", True)
        self.game.locations["Mushroom Garden"].set_property("mushrooms_smashed", True)
        self.parser.ok(
            "A trapdoor opens beneath your feet, dropping you down a steep chute. "
            "You land in a heap atop a cluster of cave mushrooms -- they break your "
            "fall, leaving only minor bruises."
        )
        _relocate(self.game, self.player, "Mushroom Garden")


# ---------------------------------------------------------------------------
# The endgame: carrying the bronze javelin into the Chaos Chapel summons the
# cultist and the demon. THROW JAVELIN banishes the demon; then PUSH CULTIST
# (into the pit) finishes him. Doing anything else while the demon looms is
# fatal. Also the two flavor gates the rulebook puts on the way down: OPEN DOOR
# (the spiked door) and OPEN IRON MAIDEN (the staircase to the Sanctum).
# ---------------------------------------------------------------------------

# Actions that don't count as "doing something" in front of the demon -- you may
# look at it before you act, but anything else gets you devoured.
_DEMON_DEATH = (
    "The demon falls upon you with tooth, tusk and tentacle. When it is done, "
    "there is nothing left to bury. THE END."
)


class DemonDevours(reactions.Countdown):
    """The summoned demon's clock (docs/design/reactions.md): once it claws up
    from the pit you have a beat to THROW JAVELIN -- you may look once, but dawdle
    past the window and it devours you. The throw sets ``banished_demon``, which
    calls the strike off."""

    DELAY = 2

    def stimulus(self) -> bool:
        return bool(self.game.locations["Chaos Chapel"].get_property("demon_present"))

    def cancelled(self) -> bool:
        return bool(self.game.player.get_property("banished_demon"))

    def consequence(self, game):
        _die(game, _DEMON_DEATH)


class OpenDoor(actions.Action):
    """Wrench open the spiked iron door at the end of the Dark Corridor."""

    ACTION_NAME = "open door"
    ACTION_DESCRIPTION = "Open the spiked iron door"
    ACTION_ALIASES = [
        "open the door",
        "open spiked door",
        "open the spiked door",
        "open iron door",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Dark Corridor":
            self.parser.fail("There's no such door here.")
            return False
        if loc.get_property("door_open"):
            self.parser.fail("The door is already open.")
            return False
        return True

    def apply_effects(self):
        self.player.location.set_property("door_open", True)
        self.parser.ok(
            "The massive door makes an awful screech as you wrench it open. "
            "Fortunately, nothing else happens -- the noise is just to scare you."
        )


class OpenIronMaiden(actions.Action):
    """Open the iron maiden in the Torture Chamber -- a staircase spirals down."""

    ACTION_NAME = "open iron maiden"
    ACTION_DESCRIPTION = "Open the iron maiden"
    ACTION_ALIASES = ["open the iron maiden", "open maiden", "open the maiden"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Torture Chamber":
            self.parser.fail("There's no iron maiden here.")
            return False
        if loc.get_property("maiden_open"):
            self.parser.fail("The iron maiden is already open.")
            return False
        return True

    def apply_effects(self):
        self.player.location.set_property("maiden_open", True)
        self.parser.ok(
            "The front of the maiden swings open, revealing a spiked interior... "
            "and a descending spiral staircase."
        )


# THROW JAVELIN AT DEMON -- the demon is a real Character (summoned into the
# Chaos Chapel), so this targets it directly. The effect still clears the
# chapel's ``demon_present`` flag, which PushCultist and the demon-devours
# trigger read.
def _banish_demon(action):
    _take_held(action.character, "bronze javelin")  # it becomes a bolt of energy
    chapel = action.game.locations["Chaos Chapel"]
    chapel.set_property("demon_present", False)
    if action.target.location is chapel:
        chapel.remove_character(action.target)
    action.character.set_property("banished_demon", True)


ThrowJavelin = actions.use_item_on(
    "throw javelin",
    item="bronze javelin",
    target="demon",
    verb="throw",
    preposition="at",
    description="Throw the bronze javelin at the demon",
    aliases=[
        "throw javelin at demon",
        "throw the javelin",
        "throw javelin at the demon",
        "throw the javelin at the demon",
        "hurl javelin",
    ],
    effect=_banish_demon,
    award=(
        "banish_demon",
        10,
        "The javelin transforms into a bolt of pure energy and pierces the "
        "demon's heart. Thunder cracks, white light dazzles you -- and the demon "
        "is gone! The cultist sneers, \"You fool! You've only delayed the "
        'inevitable!" and begins to chant; the room darkens.',
    ),
    item_missing="You have no javelin to throw.",
    target_missing="There's nothing here to throw it at.",
)


class PushCultist(actions.Action):
    """Shove the Chaos cultist into his own pit (once the demon is banished)."""

    ACTION_NAME = "push cultist"
    ACTION_DESCRIPTION = "Push the cultist into the pit"
    ACTION_ALIASES = [
        "push cultist into pit",
        "push the cultist",
        "push the cultist into the pit",
        "shove cultist",
        "shove cultist into pit",
        "kick cultist into pit",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.chapel = self.game.locations["Chaos Chapel"]

    def check_preconditions(self) -> bool:
        if not self.chapel.get_property("cultist_present"):
            self.parser.fail("There's no cultist here.")
            return False
        if self.chapel.get_property("demon_present"):
            self.parser.fail("The demon is between you and the cultist!")
            return False
        return True

    def apply_effects(self):
        self.chapel.set_property("cultist_present", False)
        cultist = self.game.characters.get("cultist")
        if cultist is not None and cultist.location is self.chapel:
            self.chapel.remove_character(cultist)
        self.player.set_property("killed_cultist", True)
        self.game.award(
            "kill_cultist",
            10,
            "You rush the chanting cultist and shove him into the spiked pit. His "
            "scream is cut short. The darkness lifts.",
        )


# ---------------------------------------------------------------------------
# Flavor verbs the rulebook calls out: the two fatal fights (FIGHT BANDITS /
# ATTACK WIZARD -- both wrong answers, fatal) and the wizard's telescope.
# ---------------------------------------------------------------------------


class FightBandits(actions.Action):
    """Wading into the bandit camp swinging is suicide -- they're too many. The
    intended path is CAST SLEEP (rulebook). Fatal while they're awake."""

    ACTION_NAME = "fight bandits"
    ACTION_DESCRIPTION = "Attack the bandits (a very bad idea)"
    ACTION_ALIASES = [
        "attack bandits",
        "fight the bandits",
        "attack the bandits",
        "kill bandits",
        "kill the bandits",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.bandits = _present(game, "bandits")

    def check_preconditions(self) -> bool:
        if self.bandits is None:
            self.parser.fail("There are no bandits here to fight.")
            return False
        return True

    def apply_effects(self):
        if self.bandits.get_property("asleep"):
            self.parser.ok(
                "The bandits are fast asleep. There's no honor in butchering them "
                "-- and no need."
            )
            return
        _die(
            self.game,
            "You charge the bandits with your dagger drawn. There are far too many "
            "of them; they swarm you, and the last thing you see is the glint of a "
            "dozen blades. THE END.",
        )


class AttackWizard(actions.Action):
    """Turning on the wizard is a fatal mistake -- he is, after all, a wizard."""

    ACTION_NAME = "attack wizard"
    ACTION_DESCRIPTION = "Attack the wizard (a very bad idea)"
    ACTION_ALIASES = [
        "fight wizard",
        "attack the wizard",
        "fight the wizard",
        "kill wizard",
        "kill the wizard",
        "stab wizard",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.wizard = _present(game, "wizard")

    def check_preconditions(self) -> bool:
        if self.wizard is None:
            self.parser.fail("There's no wizard here to attack.")
            return False
        return True

    def apply_effects(self):
        _die(
            self.game,
            "You raise your blade against the wizard. He barely looks up -- a word "
            "of power, a flash of light, and you are reduced to a smoking pair of "
            "boots. Never attack a wizard. THE END.",
        )


class UseTelescope(actions.Action):
    """Peer through the wizard's telescope -- a glimpse of the ill-omened stars
    the cultist's prophecy turns on (rulebook flavor)."""

    ACTION_NAME = "use telescope"
    ACTION_DESCRIPTION = "Peer through the wizard's telescope"
    ACTION_ALIASES = [
        "look through telescope",
        "look through the telescope",
        "peer through telescope",
        "peer through the telescope",
        "use the telescope",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "Wizard's Tower":
            self.parser.fail("There's no telescope here.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "You squint through the brass telescope. The night sky wheels with "
            "cold, unfamiliar constellations, slowly grinding into alignment. "
            '"When the stars are right," the wizard murmurs at your shoulder, "the '
            'Dark One stirs beneath the castle. Pray we are not too late."'
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
    spider_lair.add_connection("west", deep_ravine)  # web-blocked (WebBlock, below)
    _one_way(deep_ravine, "down", goblin_caves)
    _one_way(goblin_caves, "north", deep_ravine)
    goblin_caves.add_connection("east", throne_room)
    # Castle / temple
    castle_ruins.add_connection("up", wizard_tower)
    castle_ruins.add_connection("down", dungeon)  # darkness-gated
    dungeon.add_connection("west", vault)
    dungeon.add_connection("east", dark_corridor)
    dark_corridor.add_connection(
        "east", torture_chamber
    )  # gated by OPEN DOOR (FlagBlock)
    torture_chamber.add_connection(
        "down", sanctum
    )  # gated by OPEN IRON MAIDEN (FlagBlock)
    sanctum.add_connection("west", chaos_chapel)
    chaos_chapel.add_connection("south", crypt)

    # --- Darkness gates (engine Darkness block) ----------------------------
    # You can't enter the caverns or descend to the dungeon without a lit lantern.
    cavern_entrance.add_block("enter cavern", blocks.Darkness(cavern_entrance))
    castle_ruins.add_block("down", blocks.Darkness(castle_ruins))

    # The spider's web blocks the way west out of the Spider Lair until the
    # dwarf hacks it apart (USE HATCHET, only safe once the spider is driven off).
    class WebBlock(blocks.Block):
        def __init__(self, lair):
            super().__init__(
                "A great web blocks your way",
                "A thick spiderweb blocks the passage west.",
            )
            self.lair = lair

        def is_blocked(self) -> bool:
            return not self.lair.get_property("web_cleared")

    spider_lair.add_block("west", WebBlock(spider_lair))

    # You can't squeeze into the fissure while wearing your pack (rulebook):
    # DROP BACKPACK in the Dark Cavern first.
    class PackBlock(blocks.Block):
        def __init__(self, cavern):
            super().__init__(
                "Too tight with the pack on",
                "You can't squeeze into the fissure while wearing your pack. "
                "(Try DROP BACKPACK first.)",
            )
            self.cavern = cavern

        def is_blocked(self) -> bool:
            return any(
                "backpack" in ch.inventory for ch in self.cavern.characters.values()
            )

    dark_cavern.add_block("enter fissure", PackBlock(dark_cavern))

    # The goblin net: once it drops, the goblins hold you until you SHOW BABY,
    # then prod you east to the queen. North stays barred during the captivity;
    # after the throne-room audience (audience_done) the caves are free.
    class NetBlock(blocks.Block):
        def __init__(self, caves, direction):
            super().__init__(
                "The goblins block your way",
                "The goblins poke at you with their spears, herding you east.",
            )
            self.caves = caves
            self.direction = direction

        def is_blocked(self) -> bool:
            if self.caves.get_property("audience_done"):
                return False
            if not self.caves.get_property("net_dropped"):
                return False
            if self.direction == "east":
                return not self.caves.get_property("baby_shown")
            return True  # north: barred for the whole captivity

    goblin_caves.add_block("east", NetBlock(goblin_caves, "east"))
    goblin_caves.add_block("north", NetBlock(goblin_caves, "north"))

    # Two flavor gates on the way down to the temple: the spiked door (OPEN
    # DOOR) and the iron maiden's hidden staircase (OPEN IRON MAIDEN).
    class FlagBlock(blocks.Block):
        def __init__(self, loc, flag, description):
            super().__init__("The way is shut", description)
            self.loc = loc
            self.flag = flag

        def is_blocked(self) -> bool:
            return not self.loc.get_property(self.flag)

    dark_corridor.add_block(
        "east", FlagBlock(dark_corridor, "door_open", "The spiked iron door is closed.")
    )
    torture_chamber.add_block(
        "down",
        FlagBlock(
            torture_chamber,
            "maiden_open",
            "The only way down is through the iron maiden -- and it's shut.",
        ),
    )

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
    # The goblin baby (a "bundle" until you look): TAKE BABY is the path (it
    # starts crying), so it's not a plain GET.
    baby = _item(
        "baby goblin",
        "a bundle wrapped in rags",
        "A wrinkly green face with yellow catlike eyes and a tuft of red hair. It's a "
        "baby goblin, probably abandoned.",
    )
    baby.set_property("gettable", False)
    baby.set_property("crying", False)
    fissure.add_item(baby)
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
    # READ JOURNAL -- the wizard's field notes, a hint that the gray ooze hangs
    # from the ceiling and dislikes cold (USE WAND freezes it). Read by the
    # built-in READ verb (it prints an item's ``read_text``).
    journal = _fixture(
        "journal",
        'a journal titled "Ecology of the Ooze"',
        'A naturalist\'s journal, "Ecology of the Ooze."',
    )
    journal.set_property(
        "read_text",
        'From "Ecology of the Ooze": "The gray ooze is a patient ambusher, '
        "clinging unseen to cave ceilings and dropping on prey below to dissolve "
        "it alive. Look up in its haunts. Sluggish and nearly mindless, it has but "
        'one dread: cold, which freezes its protoplasm solid in an instant."',
    )
    wizard_tower.add_item(journal)
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
    # The lockbox holds the gold crown -- a closed fixture; PICK LOCK is the path
    # (and a gray ooze on the ceiling kills the careless: see USE WAND / PickLock).
    lockbox = _fixture(
        "lockbox", "a small metal lockbox", "It's a box. It's locked. It's a lockbox."
    )
    lockbox.make_container()
    lockbox.set_property("is_closed", True)
    lockbox.add_item(
        _item(
            "crown",
            "a gold crown",
            "It must have belonged to the ruler of Action Castle -- solid gold, "
            "encrusted with gems, and fit for a king... or a queen.",
        )
    )
    dark_corridor.add_item(lockbox)
    # The gray ooze is a real fixture on the ceiling -- so USE WAND ON OOZE
    # targets an actual Thing (see UseWand). ``is_frozen`` on the ooze is the
    # Thing-level state; the ``ooze_frozen`` location flag is kept in sync by
    # UseWand because the lethal lockbox trap (TakeLockbox / PickLock) reads it.
    ooze = _fixture(
        "ooze",
        "a gray ooze clinging to the ceiling",
        "An undulating mass of translucent gray protoplasm clinging to the "
        "ceiling, almost invisible in the flickering lantern light.",
    )
    ooze.set_property("is_frozen", False)
    dark_corridor.add_item(ooze)
    dark_corridor.set_property("ooze_frozen", False)
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
    # ASK ELF ABOUT SPRING / WATER -- she vouches for the spring (rulebook hint).
    elf.talk_topics = {
        "spring": '"That spring by the cavern mouth? Sweet and clean -- the water is '
        'safe to drink. Fill your skin there," says the elf.',
        "water": '"The spring water is safe to drink -- I refilled there myself," '
        "says the elf.",
        "bandits": '"They ambushed me in the ruins and took my bow. Foul company," '
        "the elf mutters.",
    }

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

    # The cultist + demon don't start on stage; the summon trigger drops them
    # into the Chaos Chapel when you arrive there carrying the bronze javelin.
    cultist = things.Character(
        "cultist",
        "a black-robed Chaos cultist",
        "I serve the Dark One; when the stars are right, he will rise.",
    )
    demon = things.Character(
        "demon",
        "a twelve-foot horned, tusked demon wreathed in writhing tentacles",
        "I am a demon of Chaos, clawed up from the infernal pit.",
    )

    dark_forest.add_character(elf)
    wizard_tower.add_character(wizard)
    spider_lair.add_character(dwarf)
    spider_lair.add_character(spider)
    torture_chamber.add_character(cleric)
    throne_room.add_character(queen)
    bandit_camp.add_character(bandits)

    # --- Player start inventory --------------------------------------------
    # The rulebook starts you with a backpack of gear plus a waterskin. GET
    # reaches into a carried open container, so the player pulls gear out of the
    # pack as needed ("take lantern", "light lantern"); DROP BACKPACK (the
    # fissure puzzle) drops the kit. The waterskin is its own carried container
    # (FILL WATERSKIN puts a `water` item in it) -- held directly rather than
    # nested in the pack, so its water is one level deep and reachable by GET /
    # crafting / GIVE WATER (the engine's held-scope helpers look one level in).
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
    waterskin = _item(
        "waterskin", "a waterskin", "A leather waterskin."
    ).make_container()

    # --- Assemble ----------------------------------------------------------
    characters = [elf, wizard, dwarf, cleric, spider, queen, bandits, cultist, demon]
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
        ShootSpider,
        UseHatchet,
        TakeMushroom,
        TakeBaby,
        DropBaby,
        FeedBaby,
        ShowBaby,
        GiveBaby,
        GiveCrown,
        LookUp,
        UseWand,
        TakeLockbox,
        PickLock,
        PushStatue,
        OpenDoor,
        OpenIronMaiden,
        ThrowJavelin,
        PushCultist,
        FightBandits,
        AttackWizard,
        UseTelescope,
    ]
    game = ActionCastle3(crossroads, player, characters, custom_actions)
    player.add_to_inventory(backpack)
    player.add_to_inventory(waterskin)

    # Mushroom stew (crafting): spring water + a cave mushroom, simmered at the
    # bandits' pot. Feeds the crying goblin baby (the baby/stew slice wires that).
    game.add_recipe(
        Recipe(
            name="stew",
            aliases=["mushroom stew"],
            inputs=["water", "cave mushroom"],
            tools=["pot"],
            output=lambda g: _item(
                "stew",
                "a bowl of mushroom stew",
                "Hot mushroom stew. A hungry goblin baby might just eat this.",
            ),
            result_text=(
                "You simmer the cave mushrooms in spring water at the bandits' pot "
                "until you have a passable mushroom stew."
            ),
        )
    )

    # Going north ends the adventure: arriving Home reads one of several
    # epilogues, chosen by how much you accomplished (rulebook page 72).
    def epilogue(g):
        p = g.player
        g.award("home", 10)  # returning home
        g.award("finish", 5)  # finishing without saving (no save mechanic here)
        if p.get_property("banished_demon") and p.get_property("killed_cultist"):
            text = (
                "Word of your exploits travels far and wide. You retire a celebrated "
                "hero. Years later, while drinking at the local tavern, a familiar "
                "party appears -- an elf, a dwarf, a cleric and a wizard -- and from "
                "behind them a red-haired goblin warrior steps forward with a treasure "
                'map and asks, "Will you join us?" TO BE CONTINUED!'
            )
        elif p.get_property("banished_demon"):
            text = (
                "Weeks later you find yourself gazing up at the stars, pondering the "
                "cultist's prophecy. When the stars are right once more, will you dare "
                "journey beneath Action Castle again? THE END?"
            )
        elif _is_holding(p, "bronze javelin"):
            g.award("return_artifact", 5)
            text = (
                "Your party journeys to the cleric's stronghold, where he returns the "
                "artifact. You are awarded a medal and a certificate of heroism at a "
                "ceremony, after which there is a small but tasteful reception. Wine "
                "and cheese are served. THE END."
            )
        elif _is_holding(p, "crown"):
            text = (
                "You sell the crown to an antiques dealer and make a small fortune, "
                "which you promptly and foolishly gamble away. THE END."
            )
        elif _is_holding(p, "baby goblin"):
            g.award("raise_baby", 5)
            text = (
                "You return to your village and raise the baby as your own. Years "
                "later, inspired by your tales of adventure, the young goblin sets off "
                "to explore Action Castle. You never see him again, but one day a "
                "letter arrives -- from Mipple, the Goblin Prince. You couldn't be "
                "more proud. THE END."
            )
        else:
            text = (
                "It seems a life of adventure just isn't for you. You return to your "
                "village, grow old, and die alone and unloved. THE END."
            )
        g.parser.ok(f"{text}  (Score: {g.score}/{g.max_score})")
        g.game_over = True
        g.game_over_description = text

    game.add_trigger(
        "epilogue_home",
        lambda g: g.player.location is not None and g.player.location.name == "Home",
        epilogue,
        repeatable=False,
    )

    # Noise gives you away at an ambush spot. Two sources: the goblin baby's
    # wailing (it cries in each new room until fed mushroom stew), and any loud
    # action of your own -- yelling aloud or smashing something (_NOISY_ACTIONS).
    # Quiet moves are safe -- sneaking in, CASTing SLEEP on the bandits, taking
    # the bow, even TALKing (they only jeer) -- which is the whole point of the
    # stealth here. The Bandit Camp and the Deep Ravine (stirges) are the spots
    # where a racket gets you killed.
    _NOISY_ACTIONS = {"say", "break"}  # racket loud enough to give you away

    def _carrying_crying_baby(g):
        baby = _held_item(g.player, "baby goblin")
        return baby is not None and baby.get_property("crying")

    def _baby_wailing(g):
        return "the baby's wailing" if _carrying_crying_baby(g) else None

    def _ambush(g, cause, fate):
        _die(g, f"{cause[0].upper()}{cause[1:]} alerts {fate}")

    # Event-based (multi-agent-safe): at an ambush spot, the baby's wailing or any
    # loud action of yours gives you away. Reads the round's events, not
    # parser.last_action, so it survives a switch to per-agent turns.
    game.add_disturbance_trigger(
        "Bandit Camp",
        lambda g, cause: _ambush(
            g,
            cause,
            "the bandits. They overwhelm you and drag you off into the woods to be "
            "eaten by wild animals. THE END.",
        ),
        loud=_NOISY_ACTIONS,
        extra=_baby_wailing,
        present=lambda g: g.player.location is not None
        and g.player.location.name == "Bandit Camp",
        name="noise_alerts_bandits",
    )
    game.add_disturbance_trigger(
        "Deep Ravine",
        lambda g, cause: _ambush(
            g,
            cause,
            "the stirges. They swarm you, stabbing with their needle beaks and "
            "draining your blood. THE END.",
        ),
        loud=_NOISY_ACTIONS,
        extra=_baby_wailing,
        present=lambda g: g.player.location is not None
        and g.player.location.name == "Deep Ravine",
        name="noise_alerts_stirges",
    )

    # Flavor: the baby wails once each time you carry it into a new room (so the
    # danger is signposted before the fatal rooms).
    def baby_wails(g):
        baby = _held_item(g.player, "baby goblin")
        baby.set_property("last_cry_loc", g.player.location.name)
        g.parser.ok("The goblin baby wails as you enter.")
        # The wail is a real emitted sound (the source owns its volume): perception
        # picks it up and it carries to the next room. The Bandit Camp / Deep Ravine
        # ambush still keys on the crying baby through its own disturbance trigger;
        # this just puts the noise into the world model.
        g.emit_sound(g.player.location, 1, "the baby's wailing")

    game.add_trigger(
        "baby_wails",
        lambda g: _carrying_crying_baby(g)
        and g.player.location is not None
        and _held_item(g.player, "baby goblin").get_property("last_cry_loc")
        != g.player.location.name,
        baby_wails,
        repeatable=True,
    )

    # Goblin Caves net trap: on arrival the net drops. No baby -> enslaved (THE
    # END). With the baby you're held until SHOW BABY; the audience pacifies the
    # caves for good.
    def goblin_net(g):
        if not _is_holding(g.player, "baby goblin"):
            _die(
                g,
                "The goblins enslave you and your allies; you spend the rest of your "
                "miserable lives turning big rocks into little rocks. THE END.",
            )
            return
        goblin_caves.set_property("net_dropped", True)
        g.parser.ok(
            "A net drops from the ceiling, ensnaring you! Goblins emerge brandishing "
            "spears and surround you. (Try SHOW BABY.)"
        )

    game.add_trigger(
        "goblin_net",
        lambda g: g.player.location is goblin_caves
        and not goblin_caves.get_property("net_dropped")
        and not goblin_caves.get_property("audience_done"),
        goblin_net,
        repeatable=True,
    )

    # After the audience (baby given, and the crown too if you carried one), the
    # goblins escort you back up to the surface and the caves are pacified.
    def throne_escort(g):
        g.parser.ok(
            "The audience over, the goblins march you out through the caverns and "
            "back up to the Cavern Entrance."
        )
        goblin_caves.set_property("audience_done", True)
        _relocate(g, g.player, "Cavern Entrance")

    game.add_trigger(
        "throne_escort",
        lambda g: g.player.location is throne_room
        and queen.get_property("baby_given")
        and (not _is_holding(g.player, "crown") or queen.get_property("crown_given"))
        and not goblin_caves.get_property("audience_done"),
        throne_escort,
        repeatable=False,
    )

    # Endgame: carrying the bronze javelin into the Chaos Chapel summons the
    # cultist, who calls up the demon from the pit.
    def summon_demon(g):
        chaos_chapel.set_property("demon_summoned", True)
        chaos_chapel.set_property("demon_present", True)
        chaos_chapel.set_property("cultist_present", True)
        chaos_chapel.set_property("demon_summoned_turn", g.turn)
        chaos_chapel.add_character(cultist)
        chaos_chapel.add_character(demon)
        g.parser.ok(
            "A black-robed man is here, chanting in a foul tongue. He utters a word "
            "of power and green flame erupts from the pit -- a monstrous demon claws "
            "its way up from the infernal depths! (THROW JAVELIN at it -- fast.)"
        )

    game.add_trigger(
        "summon_demon",
        lambda g: g.player.location is chaos_chapel
        and _is_holding(g.player, "bronze javelin")
        and not chaos_chapel.get_property("demon_summoned")
        and not g.player.get_property("banished_demon"),
        summon_demon,
        repeatable=True,
    )

    # The demon is a Countdown (see DemonDevours): its appearance starts a clock,
    # and THROW JAVELIN cancels it. A thing-owned reaction on the demon, replacing
    # the old location standoff. Registered after summon_demon so, in the same
    # react phase, demon_present is set before the countdown reads it.
    game.add_reaction(demon, DemonDevours())

    return game


# ---------------------------------------------------------------------------
# Walkthroughs
# ---------------------------------------------------------------------------

# The full max-score (100/100) run: recruit the whole party, work the interlock
# (pendant -> crypt -> spell book -> wizard -> sleep -> bow -> elf; freeze the
# ooze -> crown; rescue + feed the baby; spider + web), trade baby + crown to
# the goblin queen for the javelin, banish the demon and kill the cultist, then
# go home. Also serves as the end-to-end regression test for the whole game.
WALKTHROUGH = [
    "take lantern",
    "light lantern",
    # Elf + water + a cave mushroom (stew ingredient) on the way through.
    "west",
    "invite elf",  # Dark Forest
    "south",
    "fill waterskin",  # Cavern Entrance
    "enter cavern",
    "east",
    "take mushroom",  # Mushroom Garden
    "west",
    "up",  # back to Cavern Entrance
    # Castle: wizard (+ his wand), pendant, the crown (freeze the ooze), the
    # cleric, and the crypt's spell book.
    "north",
    "east",
    "east",  # -> Castle Ruins
    "up",
    "invite wizard",
    "take wand",
    "down",
    "down",  # -> Dungeon
    "search",
    "take pendant",
    "east",  # -> Dark Corridor
    "use wand on ooze",
    "pick lock",  # freeze the ooze (+10), take the crown
    "open door",
    "east",  # -> Torture Chamber
    "give water",
    "free man",
    "invite cleric",
    "give pendant to cleric",
    "open iron maiden",
    "down",  # -> Sanctum
    "west",
    "south",  # -> Chaos Chapel -> Crypt (no javelin yet)
    "turn undead",
    "take book",
    "give spell book to wizard",
    # Climb back to the surface.
    "north",
    "east",
    "up",  # Crypt -> Chapel -> Sanctum -> Torture
    "west",
    "west",
    "up",
    "west",  # Torture -> Corridor -> Dungeon -> Ruins -> Crossroads
    # Refill water; cook the stew and free the bow at the bandit camp.
    "west",
    "south",
    "fill waterskin",  # Cavern Entrance
    "north",
    "west",  # Dark Forest -> Bandit Camp
    "make stew",
    "cast sleep",
    "take bow",
    "give bow to elf",
    # Rescue and feed the baby.
    "east",
    "south",
    "enter cavern",  # -> Dark Cavern
    "drop backpack",
    "enter fissure",
    "take baby",
    "feed baby",
    "out",
    "take backpack",
    # Cave combat: spider, dwarf, web.
    "east",
    "south",  # -> Spider Lair
    "shoot spider",
    "free dwarf",
    "heal dwarf",
    "invite dwarf",
    "use hatchet",
    # The goblin queen: baby + crown -> the bronze javelin.
    "west",
    "down",  # Spider Lair -> Deep Ravine -> Goblin Caves
    "show baby",
    "east",  # -> Throne Room
    "give baby",
    "give crown",  # -> javelin; escorted to the Cavern Entrance
    # Carry the javelin to the Chaos Chapel and finish it.
    "north",
    "east",
    "east",  # -> Castle Ruins
    "down",
    "east",
    "east",
    "down",  # Dungeon -> Corridor -> Torture -> Sanctum
    "west",  # -> Chaos Chapel (the javelin summons the demon)
    "throw javelin at demon",
    "push cultist",
    # Home.
    "east",
    "up",
    "west",
    "west",
    "up",
    "west",  # back to the Crossroads
    "go home",
    "yes",
]


# A short navigation smoke-path (kept for the topology/ending regression).
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
        _run(WALKTHROUGH)
    elif "--walk-skeleton" in sys.argv:
        _run(WALKTHROUGH_SKELETON)
    else:
        build_game().game_loop()
