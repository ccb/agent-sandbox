"""Spooky Manor -- a Parsely game ported to the text_adventure_games engine.

You are a courier for Parcel-E-Delivery, sent on a rainy night to deliver a
parcel to the reclusive Lord Alastair Spooky. The front door locks behind you,
and the only way out is to solve the manor's mysteries: free the butler Manfred
from his werewolf curse, destroy the sleeping vampire Lady Vanessa for her
skeleton key, get Lord Spooky's signature on the parcel, and escape through the
front door to ride home -- all without becoming a werewolf or vampire yourself.
Source: Parsely "Spooky Manor" (pages 217-238).

Only one ending counts as a win (the courier who rides home, 100/100). The other
endings are the "sinister" ones -- becoming a werewolf or vampire, burning in the
incinerator (the Ghost), drowning in the reflecting pool, or hitching a doomed
ride home on foot -- and they all end the game as a loss.

Authored the way the reference ports are (see ``action_castle_2.py`` and
``docs/converting-parsely-games.md``): a ``build_game()`` assembling the world, a
small ``SpookyManor`` Game subclass holding the win/score logic and the per-turn
set-pieces (the front door locking behind you, the cellar wolf's patience, the
ride home), the two-object verbs via the engine's ``use_item_on`` factory, and a
handful of custom ``Action`` subclasses for the genuinely novel verbs.

Run interactively:    uv run python -m test_gen.spooky_manor.spooky_manor
Run the walkthrough:  uv run python -m test_gen.spooky_manor.spooky_manor --walk
"""

from text_adventure_games import games, things, actions, blocks

# ---------------------------------------------------------------------------
# Helpers (mirroring the reference ports' kit)
# ---------------------------------------------------------------------------


def _all_held(character):
    """Everything the character has on them: inventory + worn + wielded. WEAR
    moves an item out of ``inventory`` into ``worn``, so quest checks must look
    at the union, not bare inventory."""
    return {**character.inventory, **character.worn, **character.wielded}


def _is_holding(character, name):
    return name in _all_held(character)


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s canonical auto-reverse, so a
    named door ("enter house", "out", "crypt") doesn't silently wire a reverse
    that collides with another exit. (See the same helper in action_castle_2.py.)
    """
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


def _spawn(character, name, description, examine, **hints):
    """Create an item and hand it straight to the character (a hacked-off
    drumstick, a whittled stake, the shears fished from the pool)."""
    item = things.Item(name, description, examine)
    for hint in hints.get("hints", ()):
        item.add_command_hint(hint)
    character.add_to_inventory(item)
    return item


# Ending epilogues (Epilogues, page 238). Only VICTORY is a win.
VICTORY = (
    "You leave behind the manor and its secrets -- another job well done. "
    "Perhaps one day you may pay another visit to Lord Spooky and Manfred, but "
    "until then, only in your darkest dreams and nightmares will you return... "
    "to Spooky Manor! THE END."
)
HITCHHIKER = (
    "Walking down the dark and lonely road, you wave down a passing car. As you "
    "get inside and the doors lock, the driver turns to face you, fixing you "
    "with an evil smile. You wish you had never made this fateful trip to... "
    "Spooky Manor. THE END."
)
GHOST = (
    "Opening your eyes as if from a long and dreamless sleep, you find yourself "
    "standing over a lifeless body. With growing horror, you realize that body "
    "is your own. Once a visitor, now you are a permanent resident of... Spooky "
    "Manor! THE END."
)
WEREWOLF = (
    "The wolf overpowers you, savaging your flesh. Hours later you wake, "
    "uninjured but in bloody, torn clothing -- your senses keen, your "
    "fingernails long and sharp. As a wolf howls at the moon, you feel your own "
    "body warp and shift, and you let out a baleful howl of your own. Forever "
    "changed, you forget your former life and that fateful night at... Spooky "
    "Manor. THE END."
)
VAMPIRE = (
    "The woman sits up and locks her hands around your neck. She bites you and "
    "leaves you bleeding on the floor of the crypt; you hear the flutter of "
    "leathery wings. Flapping your own leathery wings, you rise into the night "
    "sky in search of fresh blood to sate your eternal hunger. At sunrise you "
    "will return to slumber... inside Spooky Manor. THE END."
)


# ---------------------------------------------------------------------------
# Game subclass: win condition, scoring, and the per-turn set-pieces
# ---------------------------------------------------------------------------


class SpookyManor(games.Game):
    """Won only by delivering the parcel and riding home on a locked, undamaged
    bike. Every other ending -- werewolf, vampire, Ghost, hitchhiker -- is a
    loss (``game_over`` without ``has_won``)."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        # Scoring table, page 238 (max 100): lock_bike 5, secret_study 10,
        # cure_manfred 15, recover 10, hedge_maze 10, destroy_vampire 15,
        # skeleton_key 5, deliver_parcel 5, signature 5, escape_front 10,
        # ride_home 5, finish 5.  score / _scored_keys / award() come from Game.
        self.max_score = 100
        self.entered_hall = False  # has the front door locked behind us yet?
        self.cellar_turns = 0  # turns lingered with the chained wolf

    # -- sinister endings (a loss, narrated then game_over) -----------------

    def _sinister(self, text):
        self.parser.ok(text)
        self.game_over = True
        self.game_over_description = text

    # -- the road home (the Gate has no real east/west exits) ---------------

    def _leave_by_road(self):
        if not self.player.get_property("parcel_delivered"):
            self.parser.fail('"Once you deliver your parcel you can go home."')
            return False
        locked = self.player.get_property("bike_locked")
        damaged = self.player.get_property("bike_damaged")
        if locked and not damaged:
            self.award("ride_home", 5)
            self.award("finish", 5)  # finishing without saving, page 238
            self.player.set_property("has_won", True)
            self.announce_ending(VICTORY, show_score=True)
        else:
            # Bike stolen (never locked) or damaged (ridden up the path): you
            # leave on foot, straight into the Hitchhiker's bad end.
            self._sinister(HITCHHIKER)
        return True

    # -- per-turn set-pieces ------------------------------------------------

    def do_command(self, command: str) -> bool:
        cmd = (command or "").strip().lower()
        loc = self.player.location

        # The dark and lonely road: ride or walk home from the Gate.
        if (
            loc is not None
            and loc.name == "The Gate"
            and cmd
            in (
                "east",
                "west",
                "go east",
                "go west",
                "e",
                "w",
                "ride east",
                "ride west",
                "ride home",
                "go home",
            )
        ):
            return self._leave_by_road()

        # Riding the bike up the neglected path shreds its fragile tires.
        if (
            loc is not None
            and loc.name == "The Gate"
            and cmd in ("north", "go north", "n")
            and self.player.get_property("on_bike")
        ):
            self.player.set_property("bike_damaged", True)
            self.player.set_property("on_bike", False)
            self.parser.ok(
                "You can't resist pedaling up the path. The fragile tires crunch "
                "over the broken cobblestones and go flat -- so much for riding "
                "home in style."
            )

        before = loc
        success = super().do_command(command)
        after = self.player.location

        if success and after is not None:
            # The front door swings shut and locks behind you, once.
            if (
                after is not before
                and after.name == "Great Hall"
                and not self.entered_hall
            ):
                self.entered_hall = True
                self.locations["Front Door"].set_property("locked", True)
                self.parser.ok(
                    "Behind you, the front door swings shut and locks with a "
                    "heavy click. Now there's a chilling challenge: find a way "
                    "out!"
                )
            self._cellar_watch()
        return success

    def _cellar_watch(self):
        """Page 223: linger too long in the cellar with the chained wolf and it
        snaps its chain and makes a werewolf of you."""
        cellar = self.locations.get("Dark Cellar")
        wolf = cellar.characters.get("wolf") if cellar is not None else None
        if self.player.location is cellar and wolf is not None:
            self.cellar_turns += 1
            if self.cellar_turns >= 5:
                self._sinister(WEREWOLF)
        else:
            self.cellar_turns = 0

    # -- win ----------------------------------------------------------------

    def is_won(self) -> bool:
        return bool(self.player.get_property("has_won"))


# ---------------------------------------------------------------------------
# A flexible block: an exit is shut until some game flag is set
# ---------------------------------------------------------------------------


class CondBlock(blocks.Block):
    """An exit blocked until a predicate goes true (knock, hang coat, unlock
    the door, clear the hedges, pry the crypt). The predicate is a zero-arg
    callable so each gate can read whatever location/player flag it likes."""

    def __init__(self, description, predicate):
        super().__init__("The way is shut", description)
        self.predicate = predicate

    def is_blocked(self) -> bool:
        return self.predicate()


# ---------------------------------------------------------------------------
# Two-object verbs (the engine's use_item_on factory)
# ---------------------------------------------------------------------------


def _carve_pheasant(action):
    _spawn(
        action.character,
        "drumstick",
        "a roast pheasant drumstick",
        "A cold pheasant drumstick, carried county fair-style. Fit for a wolf.",
        hints=["use wolfsbane on drumstick"],
    )


CarvePheasant = actions.use_item_on(
    "use cleaver on pheasant",
    item="cleaver",
    target="pheasant",
    verb="use",
    preposition="on",
    description="Hack a drumstick off the roast pheasant",
    aliases=["cut pheasant", "carve pheasant", "use the cleaver on the pheasant"],
    effect=_carve_pheasant,
    success=(
        "You hack off one of the drumsticks to carry around with you, county "
        "fair-style."
    ),
    requires=lambda a: (
        "You can carry only one drumstick at a time."
        if _is_holding(a.character, "drumstick")
        else None
    ),
    item_missing="You've nothing sharp enough to carve with.",
    target_missing="There's no pheasant here.",
)


def _sharpen_cue(action):
    _spawn(
        action.character,
        "stake",
        "a sharpened pool cue",
        "A hardwood pool cue whittled down to a wicked point -- near enough a "
        "stake.",
        hints=["use stake"],
    )


SharpenCue = actions.use_item_on(
    "use cleaver on cue",
    item="cleaver",
    target="cue",
    verb="use",
    preposition="on",
    description="Whittle a pool cue down into a sharp stake",
    aliases=[
        "use cleaver on pool cue",
        "use shears on cue",
        "sharpen cue",
        "whittle cue",
    ],
    effect=_sharpen_cue,
    success=(
        "You hack off the brass tip and whittle the cue down until it has a "
        "sharp point."
    ),
    requires=lambda a: (
        "You've already sharpened a cue." if _is_holding(a.character, "stake") else None
    ),
    item_missing="You've nothing to whittle with.",
    target_missing="There are no pool cues here.",
)


def _oil_shears(action):
    action.target.set_property("oiled", True)


OilShears = actions.use_item_on(
    "use oil on shears",
    item="oil",
    target="shears",
    verb="use",
    preposition="on",
    description="Oil the rusty gardening shears so they open and close",
    aliases=["oil shears", "use olive oil on shears", "oil the shears"],
    effect=_oil_shears,
    success="The oil allows you to smoothly open and close the shears.",
    consume=True,  # the bottle was almost empty -- one use
    requires=lambda a: (
        "The shears already work smoothly." if a.target.get_property("oiled") else None
    ),
    item_missing="You've no oil.",
    target_missing="You aren't holding the shears.",
)


def _cure_manfred(action):
    """USE WOLFSBANE ON DRUMSTICK in the cellar: the wolf eats the tainted meat
    and reverts to Manfred, the butler (page 223). +15."""
    g = action.game
    cellar = g.locations["Dark Cellar"]
    wolf = cellar.characters.get("wolf")
    if wolf is not None:
        cellar.remove_character(wolf)
    g.cellar_turns = 0
    manfred = g.characters.get("manfred")
    cellar.add_character(manfred)
    action.character.discard_item(action.target)  # the wolf eats the drumstick
    g.award("cure_manfred", 15)


CureManfred = actions.use_item_on(
    "use wolfsbane on drumstick",
    item="wolfsbane",
    target="drumstick",
    verb="use",
    preposition="on",
    description="Rub wolfsbane onto the drumstick and feed it to the wolf",
    aliases=["rub wolfsbane on drumstick", "poison drumstick", "taint drumstick"],
    effect=_cure_manfred,
    success=(
        "You rub the herb onto the meat and offer it to the wolf. It gulps the "
        "drumstick down, then howls and writhes as it reverts to human form. "
        "Where once was a wolf, now you see a man!"
    ),
    consume=True,  # the wolfsbane is used up
    requires=lambda a: (
        "There's no wolf here to feed."
        if a.character.location.name != "Dark Cellar"
        or "wolf" not in a.character.location.characters
        else None
    ),
    item_missing="You aren't holding any wolfsbane.",
    target_missing="You've no drumstick to feed it.",
)


def _cover_manfred(action):
    """Give Manfred something to wear and, no longer naked, he leaves the
    cellar to tidy himself up in the servants' quarters (page 223)."""
    g = action.game
    manfred = action.target
    manfred.set_property("rescued", True)
    manfred.description = "Manfred, the butler, smartly turned out once more"
    manfred.examine_text = (
        "Manfred the butler, restored to himself and -- now that he's covered "
        "up -- to his usual dignity."
    )
    g.relocate(manfred, g.locations["Servants' Quarters"])


CoverManfred = actions.use_item_on(
    "give pelt to manfred",
    item="pelt",
    target="manfred",
    verb="give",
    preposition="to",
    description="Give the wolf pelt to Manfred to cover himself",
    aliases=[
        "give wolf pelt to manfred",
        "give pelt to man",
        "give wolf pelt to man",
        "cover manfred",
    ],
    effect=_cover_manfred,
    success=(
        'Manfred gratefully wraps himself in the pelt. "Thank you so much for '
        "saving me from that dire fate.\" He hurries off toward the servants' "
        "quarters to find proper clothes."
    ),
    consume=True,
    requires=lambda a: (
        "He's already decently covered." if a.target.get_property("rescued") else None
    ),
    item_missing="You've nothing to offer him to wear.",
    target_missing="There's no one here who needs covering.",
)


def _give_parcel(action):
    action.character.set_property("parcel_delivered", True)


GiveParcel = actions.use_item_on(
    "give parcel to lord spooky",
    item="parcel",
    target="lord spooky",
    verb="give",
    preposition="to",
    description="Deliver the parcel to Lord Spooky",
    aliases=["give parcel to spooky", "deliver parcel", "hand parcel to lord spooky"],
    effect=_give_parcel,
    award=(
        "deliver_parcel",
        5,
        'Lord Spooky takes the parcel and turns it over. "Do you have a pen?"',
    ),
    consume=True,
    item_missing="You aren't carrying the parcel.",
    target_missing="There's no one here to take it.",
)


GivePen = actions.use_item_on(
    "give pen to lord spooky",
    item="pen",
    target="lord spooky",
    verb="give",
    preposition="to",
    description="Lend Lord Spooky the silver pen so he can sign for the parcel",
    aliases=["give pen to spooky", "give silver pen to lord spooky", "lend pen"],
    award=("signature", 5, "He signs for the parcel and thanks you warmly."),
    consume=True,
    requires=lambda a: (
        None
        if a.character.get_property("parcel_delivered")
        else "He looks at you blankly -- give him the parcel first."
    ),
    item_missing="You haven't got a pen.",
    target_missing="There's no one here who wants a pen.",
)


def _use_garlic(action):
    action.target.set_property("garlic_in_mouth", True)


UseGarlic = actions.use_item_on(
    "use garlic on vanessa",
    item="garlic",
    target="vanessa",
    verb="use",
    preposition="on",
    description="Stuff the garlic into the sleeping vampire's mouth",
    aliases=["use garlic", "put garlic in mouth", "feed garlic to vanessa"],
    effect=_use_garlic,
    success=(
        "You place the garlic in Vanessa's mouth. She wakes from her slumber, "
        "snarling and choking on it -- unable to bite."
    ),
    consume=True,
    requires=lambda a: (
        "There's no one here to feed garlic to."
        if a.target is None or a.target.get_property("destroyed")
        else None
    ),
    item_missing="You aren't carrying any garlic.",
    target_missing="There's no one here.",
)


def _use_stake(action):
    """Stake Lady Vanessa. Only safe once the garlic has stopped her biting;
    otherwise she wakes and turns you (page 232)."""
    g = action.game
    vanessa = action.target
    if not vanessa.get_property("garlic_in_mouth"):
        g._sinister(VAMPIRE)
        return
    vanessa.set_property("destroyed", True)
    crypt = g.locations["Family Crypt"]
    crypt.remove_character(vanessa)
    key = things.Item(
        "key",
        "a skeleton key on a ribbon",
        "A skeleton key -- it should unlock any door in the manor.",
    )
    key.add_command_hint("get key")
    key.add_command_hint("use skeleton key on door")
    crypt.add_item(key)
    g.award("destroy_vampire", 15)
    g.parser.ok(
        "You plunge the stake into her heart and she turns to dust. A skeleton "
        "key on a ribbon is all that's left."
    )
    action.character.discard_item(action.item)


UseStake = actions.use_item_on(
    "use stake on vanessa",
    item="stake",
    target="vanessa",
    verb="use",
    preposition="on",
    description="Drive the stake through the vampire's heart",
    aliases=["use stake", "stake vanessa", "stake her", "plunge stake"],
    effect=_use_stake,
    requires=lambda a: (
        "There's no one here to stake."
        if a.target is None or a.target.get_property("destroyed")
        else None
    ),
    item_missing="You've nothing sharp enough to use as a stake.",
    target_missing="There's no one here.",
)


# ---------------------------------------------------------------------------
# Custom actions (the genuinely novel verbs)
# ---------------------------------------------------------------------------


class _Here(actions.Action):
    """Small base for the location-scoped verbs below: resolves the actor and
    guards that they're standing in ``ROOM`` before doing anything."""

    ROOM = None

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def _here(self) -> bool:
        return self.ROOM is None or self.character.location.name == self.ROOM


class LockBike(_Here):
    ACTION_NAME = "lock bike"
    ACTION_DESCRIPTION = "Chain and padlock your bike to keep it from being stolen"
    ACTION_ALIASES = ["lock up bike", "lock the bike", "padlock bike", "chain bike"]
    ROOM = "The Gate"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("Your bike isn't here.")
            return False
        if self.character.get_property("bike_locked"):
            self.parser.fail("Your bike is already chained up.")
            return False
        return True

    def apply_effects(self):
        self.character.set_property("bike_locked", True)
        self.character.set_property("on_bike", False)
        self.game.award(
            "lock_bike",
            5,
            "You wrap the heavy chain around the frame and snap the padlock "
            "shut with the key from your coat pocket. Your bike is safe.",
        )


class Knock(_Here):
    ACTION_NAME = "knock"
    ACTION_DESCRIPTION = "Knock"
    ACTION_ALIASES = ["knock on door", "use knocker", "knock on the door"]

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        loc = self.character.location.name
        if loc == "Front Door":
            self.character.location.set_property("knocked", True)
            self.parser.ok(
                "Nobody answers, but the door cracks open, seemingly on its own!"
            )
        elif loc == "Master Suite":
            self.parser.ok("The music is too loud for anyone to hear you.")
        else:
            self.parser.ok("Nobody answers.")


class HangRaincoat(_Here):
    ACTION_NAME = "hang raincoat"
    ACTION_DESCRIPTION = "Hang your dripping raincoat on the coat tree"
    ACTION_ALIASES = [
        "hang up raincoat",
        "hang coat",
        "hang up coat",
        "hang up my coat",
    ]
    ROOM = "Vestibule"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no coat tree here.")
            return False
        if "raincoat" not in self.character.worn:
            self.parser.fail("You aren't wearing a raincoat.")
            return False
        return True

    def apply_effects(self):
        coat = self.character.worn.pop("raincoat")
        coat.set_owner(None)
        tree = self.character.location.items.get("coat tree")
        if tree is not None:
            tree.add_item(coat)
        self.character.location.set_property("raincoat_hung", True)
        self.parser.ok(
            "You hang your dripping raincoat on the coat tree. Much more polite."
        )


class ReadHerbalism(_Here):
    ACTION_NAME = "read herbalism for beginners"
    ACTION_DESCRIPTION = "Read the herbalism book"
    ACTION_ALIASES = [
        "read herbalism",
        "read herbalism book",
        "read the herbalism book",
        "read book on herbalism",
    ]
    ROOM = "Library"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no such book here.")
            return False
        return True

    def apply_effects(self):
        self.character.set_property("knows_herbalism", True)
        self.parser.ok(
            'You read the first entry: "Aconitum vulparia, a poisonous plant '
            'known as wolfsbane, is rumored to cure lycanthropy." Yawn, boring -- '
            "but you'd recognize the plant now if you saw it."
        )


class TakeMysteries(_Here):
    ACTION_NAME = "take mysteries of ancient egypt"
    ACTION_DESCRIPTION = "Take the book Mysteries of Ancient Egypt"
    ACTION_ALIASES = [
        "take mysteries",
        "get mysteries of ancient egypt",
        "read mysteries of ancient egypt",
        "take the book on egypt",
    ]
    ROOM = "Library"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no such book here.")
            return False
        if self.character.location.get_property("study_open"):
            self.parser.fail("The sarcophagus already stands open.")
            return False
        return True

    def apply_effects(self):
        library = self.character.location
        library.set_property("study_open", True)
        # Reveal the secret door south to the study (the reverse is wired).
        library.connections["south"] = self.game.locations["Secret Study"]
        library.travel_descriptions["south"] = "You slip through the secret door."
        self.game.award(
            "secret_study",
            10,
            "As you lift the book, the heavy sarcophagus slides open with a "
            "grinding of stone, revealing a secret door to the south!",
        )


class TakeDante(_Here):
    ACTION_NAME = "take dante's inferno"
    ACTION_DESCRIPTION = "Take the first edition of Dante's Inferno"
    ACTION_ALIASES = [
        "take dantes inferno",
        "take inferno",
        "take dante",
        "read dantes inferno",
        "get dantes inferno",
    ]
    ROOM = "Library"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no such book here.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "A trapdoor opens beneath your feet, sending you down a chute into "
            "the manor's incinerator. You're immolated in the fire and turn to "
            "ash."
        )
        self.game._sinister(GHOST)


class TakeWolfsbane(_Here):
    ACTION_NAME = "take wolfsbane"
    ACTION_DESCRIPTION = "Pick the wolfsbane growing in the garden"
    ACTION_ALIASES = ["get wolfsbane", "pick wolfsbane", "take the wolfsbane"]
    ROOM = "Garden"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no wolfsbane here.")
            return False
        if not self.character.get_property("knows_herbalism"):
            self.parser.fail(
                "Gardening isn't your area of expertise; the plants all look "
                "the same to you."
            )
            return False
        if _is_holding(self.character, "wolfsbane"):
            self.parser.fail("You've already picked some wolfsbane.")
            return False
        return True

    def apply_effects(self):
        _spawn(
            self.character,
            "wolfsbane",
            "a sprig of wolfsbane",
            "Aconitum vulparia -- poisonous, but rumored to cure lycanthropy.",
            hints=["use wolfsbane on drumstick"],
        )
        self.parser.ok("You carefully pick a sprig of the poisonous wolfsbane.")


class EnterPool(_Here):
    ACTION_NAME = "enter pool"
    ACTION_DESCRIPTION = "Wade into the reflecting pool to fetch the shears"
    ACTION_ALIASES = ["enter the pool", "wade into pool", "get shears", "take shears"]
    ROOM = "Reflecting Pool"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no pool here.")
            return False
        if _is_holding(self.character, "shears"):
            self.parser.fail("You've already got the shears.")
            return False
        return True

    def apply_effects(self):
        _spawn(
            self.character,
            "shears",
            "a pair of gardening shears",
            "Old, rusted gardening shears, fished from the reflecting pool.",
            hints=["use oil on shears", "use shears"],
        )
        self.character.set_property("wet_cold", True)
        self.parser.ok(
            "You wade in and snatch the gardening shears from the middle of the "
            "pool. The water is cold and you're soon soaked to the bone. Achoo! "
            "You're a shivering wreck now -- too weak for anything strenuous "
            "until you warm up."
        )


class Dive(_Here):
    ACTION_NAME = "dive into pool"
    ACTION_DESCRIPTION = "Dive into the reflecting pool"
    ACTION_ALIASES = ["dive", "dive in", "swim in pool", "jump into pool"]
    ROOM = "Reflecting Pool"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's nothing here to dive into.")
            return False
        return True

    def apply_effects(self):
        self.game.end_in_death(
            "You dive in headfirst. The water is shallow; you hit your head on "
            "the marble bottom and drown. THE END."
        )


class SitByFire(_Here):
    ACTION_NAME = "sit by fire"
    ACTION_DESCRIPTION = "Sit by the roaring fire in the lounge"
    ACTION_ALIASES = ["sit by the fire", "sit", "sit down", "warm up", "warm yourself"]
    ROOM = "Lounge"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no fire here to sit by.")
            return False
        return True

    def apply_effects(self):
        self.character.set_property("sat_by_fire", True)
        self.parser.ok(
            "You settle into the overstuffed chair and let the roaring fire warm "
            "your bones."
        )


class DrinkBrandy(_Here):
    ACTION_NAME = "drink brandy"
    ACTION_DESCRIPTION = "Drink the snifter of brandy"
    ACTION_ALIASES = ["drink the brandy", "drink snifter", "sip brandy"]
    ROOM = "Lounge"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no brandy here.")
            return False
        return True

    def apply_effects(self):
        if not self.character.get_property("wet_cold"):
            self.parser.ok("No drinking on the job!")
            return
        dry = "jacket" in self.character.worn or "pelt" in self.character.worn
        if not dry:
            self.parser.ok(
                "You're still soaked to the skin. You should get into some dry "
                "clothing first."
            )
            return
        if not self.character.get_property("sat_by_fire"):
            self.parser.ok("You're shivering too hard. Warm up by the fire first.")
            return
        self.character.set_property("wet_cold", False)
        self.game.award(
            "recover",
            10,
            "Warm, dry, and with a glow of brandy inside you, you finally stop "
            "shivering. You feel hale enough for anything now.",
        )


class CutHedge(_Here):
    ACTION_NAME = "use shears"
    ACTION_DESCRIPTION = "Cut a path through the hedge maze with the shears"
    ACTION_ALIASES = [
        "cut hedge",
        "cut hedges",
        "clear hedge",
        "clear a path",
        "prune hedge",
    ]
    ROOM = "Hedge Maze"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's nothing here to cut.")
            return False
        if not _is_holding(self.character, "shears"):
            self.parser.fail("You've nothing to cut the hedges with.")
            return False
        shears = _all_held(self.character)["shears"]
        if not shears.get_property("oiled"):
            self.parser.fail("The shears are rusty and difficult to use.")
            return False
        return True

    def apply_effects(self):
        self.character.location.set_property("cleared", True)
        self.game.award(
            "hedge_maze",
            10,
            "With the oiled shears you cut a clear path straight through the "
            "hedges. A way south opens up.",
        )


class PryDoor(_Here):
    ACTION_NAME = "pry door"
    ACTION_DESCRIPTION = "Pry open the rusted crypt door with the spade"
    ACTION_ALIASES = [
        "pry crypt",
        "pry open crypt",
        "pry door open",
        "force crypt door",
    ]
    ROOM = "Graveyard"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no crypt door here.")
            return False
        if not _is_holding(self.character, "spade"):
            self.parser.fail("You need something sturdy to pry with.")
            return False
        if self.character.get_property("wet_cold"):
            self.parser.fail(
                "You're a shivering wreck; you haven't the strength to pry it "
                "open. Best warm up first."
            )
            return False
        if self.character.location.get_property("crypt_open"):
            self.parser.fail("The crypt door already stands open.")
            return False
        return True

    def apply_effects(self):
        graveyard = self.character.location
        graveyard.set_property("crypt_open", True)
        self.parser.ok("You pry open the rusted door to the crypt.")


class DigGrave(_Here):
    ACTION_NAME = "dig grave"
    ACTION_DESCRIPTION = "Dig a hole with the spade"
    ACTION_ALIASES = ["dig", "dig a grave", "dig hole"]
    ROOM = "Graveyard"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("The ground here is too hard to dig.")
            return False
        if not _is_holding(self.character, "spade"):
            self.parser.fail("You've nothing to dig with.")
            return False
        if self.character.get_property("wet_cold"):
            self.parser.fail("You're too sick and shivery for such hard work.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "It takes a while, but you manage to dig a pretty impressive hole in "
            "the ground."
        )


class StopPhonograph(_Here):
    ACTION_NAME = "stop phonograph"
    ACTION_DESCRIPTION = "Stop the phonograph's music"
    ACTION_ALIASES = [
        "stop music",
        "stop the music",
        "stop the phonograph",
        "stop victrola",
    ]
    ROOM = "Master Suite"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no phonograph here.")
            return False
        return True

    def apply_effects(self):
        suite = self.character.location
        if suite.get_property("music_stopped"):
            self.parser.ok("The room is already quiet.")
            return
        suite.set_property("music_stopped", True)
        spooky = self.game.characters.get("lord spooky")
        suite.add_character(spooky)
        self.parser.ok(
            "You lift the stylus and the music stops. The bathroom door opens, "
            "and an elderly man in a purple bathrobe emerges -- the reclusive "
            "master of the manor, Lord Spooky himself."
        )


class UseSkeletonKeyOnDoor(_Here):
    ACTION_NAME = "use skeleton key on door"
    ACTION_DESCRIPTION = "Unlock a door with the skeleton key"
    ACTION_ALIASES = [
        "unlock door",
        "use key on door",
        "unlock the door",
        "use skeleton key on front door",
        "use skeleton key on master suite door",
        "open door with key",
    ]

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "key"):
            self.parser.fail("You don't have a key.")
            return False
        return True

    def apply_effects(self):
        loc = self.character.location
        if loc.name == "Hallway":
            if loc.get_property("master_unlocked"):
                self.parser.ok("That door is already unlocked.")
            else:
                loc.set_property("master_unlocked", True)
                self.parser.ok(
                    "The skeleton key turns the lock on the west door, and the "
                    "classical music swells louder. It's open."
                )
        elif loc.name == "Front Door":
            front = loc
            if front.get_property("unlocked"):
                self.parser.ok("The front door already stands open.")
            else:
                front.set_property("unlocked", True)
                self.game.award(
                    "escape_front",
                    10,
                    "The skeleton key turns smoothly in the front door's lock. "
                    "It swings open onto the rainy night -- you're free of "
                    "Spooky Manor at last!",
                )
        else:
            self.parser.ok("There's nothing here the key will fit.")


class TakeSkeletonKey(_Here):
    ACTION_NAME = "take skeleton key"
    ACTION_DESCRIPTION = "Take the skeleton key"
    ACTION_ALIASES = [
        "get skeleton key",
        "take key",
        "get key",
        "take the key",
        "grab key",
    ]
    ROOM = "Family Crypt"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no key here.")
            return False
        return True

    def apply_effects(self):
        crypt = self.character.location
        vanessa = crypt.characters.get("vanessa")
        if vanessa is not None and not vanessa.get_property("destroyed"):
            # Reaching for the key without first dealing with her wakes the
            # sleeping vampire -- and turns you (page 232).
            self.game._sinister(VAMPIRE)
            return
        key = crypt.items.get("key")
        if key is None:
            self.parser.fail("There's no key here.")
            return
        self.character.add_to_inventory(key)
        self.game.award("skeleton_key", 5, "You take the skeleton key.")


class AttackWolf(_Here):
    ACTION_NAME = "attack wolf"
    ACTION_DESCRIPTION = "Attack the chained wolf"
    ACTION_ALIASES = ["kill wolf", "hit wolf", "fight wolf", "attack the wolf"]
    ROOM = "Dark Cellar"

    def check_preconditions(self) -> bool:
        if not self._here() or "wolf" not in self.character.location.characters:
            self.parser.fail("There's no wolf here to attack.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "You raise your weapon. With a savage lunge the wolf snaps its chain "
            "and is on you!"
        )
        self.game._sinister(WEREWOLF)


class OpenTrapdoor(_Here):
    ACTION_NAME = "open trapdoor"
    ACTION_DESCRIPTION = "Pull open the trapdoor in the hallway ceiling"
    ACTION_ALIASES = ["open the trapdoor", "pull trapdoor", "open hatch"]
    ROOM = "Hallway"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no trapdoor here.")
            return False
        return True

    def apply_effects(self):
        self.character.location.set_property("trapdoor_open", True)
        self.parser.ok("The trapdoor opens, revealing a stepladder leading up.")


class ShakeParcel(_Here):
    ACTION_NAME = "shake parcel"
    ACTION_DESCRIPTION = "Shake the parcel"
    ACTION_ALIASES = ["shake the parcel", "rattle parcel"]

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "parcel"):
            self.parser.fail("You aren't holding the parcel.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok("It rattles.")


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> SpookyManor:
    L = things.Location

    gate = L(
        "The Gate",
        "You stop your bicycle by a forbidding wrought-iron gate. A cobblestone "
        "path winds north toward the manor. To the east and west stretches a "
        "dark and lonely road. It is raining.",
    )
    front_door = L(
        "Front Door",
        "You stand at Spooky Manor's imposing front door. There is a brass "
        "knocker here. The path leads south back to the gate.",
    )
    vestibule = L(
        "Vestibule",
        "You are standing in a vestibule. Rain drips from your coat onto the "
        "floor. To the north is the manor's great hall. There is a coat tree "
        "here.",
    )
    great_hall = L(
        "Great Hall",
        "Archways lead to the east and west wings of the manor. Oil paintings "
        "and a large mirror hang on the wall. A staircase leads up to the "
        "second floor. The vestibule is to the south.",
    )
    dining = L(
        "Dining Room",
        "The dining room contains a long banquet table. A whole roast pheasant "
        "rests in its center. Exits are north, south and east.",
    )
    lounge = L(
        "Lounge",
        "You enter the lounge, where a fire roars in the hearth. A smoking "
        "jacket rests on an overstuffed chair, and there is a snifter of brandy "
        "here. The dining room is north.",
    )
    kitchen = L(
        "Kitchen",
        "The kitchen is old-fashioned. There is a meat cleaver here and a small "
        "bottle of olive oil. A cellar door leads down; the dining room is "
        "south.",
    )
    cellar = L(
        "Dark Cellar",
        "You enter the dark cellar and see a monstrous wolf chained to the "
        "wall! There are cloves of garlic here. Stairs lead up.",
    )
    library = L(
        "Library",
        "The library is home to many old books. An Egyptian sarcophagus stands "
        "in the corner. Exits are north and west.",
    )
    study = L(
        "Secret Study",
        "Lord Spooky's private study is a spartan room with a writing desk and "
        "chair. The only way out is north.",
    )
    billiard = L(
        "Billiard Room",
        "The billiard room holds a rack of pool cues and a large billiard "
        "table. Trophy heads and stuffed animals are everywhere. Moonlight "
        "streams in from the north; the library is south.",
    )
    conservatory = L(
        "Conservatory",
        "This glass-enclosed room affords a view of the night sky. A set of "
        "double doors stands open to the garden, east. The billiard room is "
        "south.",
    )
    garden = L(
        "Garden",
        "You are in the garden, full of unusual plants. A hedge maze is east, "
        "running water sounds to the north, and the conservatory is west.",
    )
    pool = L(
        "Reflecting Pool",
        "You've come to a marble-tiled reflecting pool with a wolf-shaped "
        "fountain. The garden is south.",
    )
    maze = L(
        "Hedge Maze",
        "You stand at the entrance to a towering hedge maze. The garden is back "
        "to the west.",
    )
    graveyard = L(
        "Graveyard",
        "You've stumbled into a cemetery of crumbling tombstones. There is a "
        "crypt here and a gravedigger's spade. The hedge maze is north.",
    )
    family_crypt = L(
        "Family Crypt",
        "The crypt smells of mold and decay, but its sole occupant lies "
        "perfectly preserved on a granite slab. The way out is back to the "
        "graveyard.",
    )
    hallway = L(
        "Hallway",
        "You stand in a long hallway at the top of the stairs. There is an open "
        "door east and a closed door west. A trapdoor is set in the ceiling. "
        "The stairs lead down.",
    )
    attic = L(
        "Attic",
        "You are in a dark attic lit by moonlight from a small broken window. "
        "There is an old steamer trunk here. The way down is the stepladder.",
    )
    servants = L(
        "Servants' Quarters",
        "A servants' room with a bed, wardrobe and dresser. The hallway is back "
        "out the door.",
    )
    master = L(
        "Master Suite",
        "The master suite of Spooky Manor. An old phonograph plays classical "
        "music. The door to the bathroom is closed. The hallway is back out.",
    )

    # --- Connections -------------------------------------------------------
    # Ground floor and grounds (canonical pairs auto-reverse).
    gate.add_connection("north", front_door, "You walk up the path on foot.")
    _one_way(front_door, "enter house", vestibule)
    _one_way(vestibule, "out", front_door)
    vestibule.add_connection("north", great_hall, "You step into the great hall.")
    great_hall.add_connection("west", dining)
    great_hall.add_connection("east", library)
    great_hall.add_connection("up", hallway)
    dining.add_connection("south", lounge)
    dining.add_connection("north", kitchen)
    kitchen.add_connection("down", cellar)
    library.add_connection("north", billiard)
    _one_way(study, "north", library)  # the secret south door is revealed later
    billiard.add_connection("north", conservatory)
    conservatory.add_connection("east", garden)
    garden.add_connection("north", pool)
    garden.add_connection("east", maze)
    maze.add_connection("south", graveyard)  # gated by the hedge block
    _one_way(graveyard, "crypt", family_crypt)  # gated by the crypt block
    _one_way(family_crypt, "out", graveyard)
    # Upstairs.
    _one_way(hallway, "east", servants)
    _one_way(servants, "out", hallway)
    _one_way(hallway, "west", master)
    _one_way(master, "out", hallway)
    hallway.add_connection("up", attic)

    # --- Items: scenery helper --------------------------------------------
    def scenery(name, desc, examine, loc, hints=()):
        it = things.Item(name, desc, examine)
        it.set_property("gettable", False)
        for h in hints:
            it.add_command_hint(h)
        loc.add_item(it)
        return it

    def gettable(name, desc, examine, loc, hints=()):
        it = things.Item(name, desc, examine)
        for h in hints:
            it.add_command_hint(h)
        loc.add_item(it)
        return it

    # The Gate: the parcel (in the bike basket) and scenery.
    gettable(
        "parcel",
        "a small parcel",
        'A box wrapped in paper and tied with twine, addressed to "Lord '
        'Alastair Spooky." It rattles when shaken.',
        gate,
        ["get parcel", "shake parcel", "give parcel to lord spooky"],
    )
    scenery(
        "bike",
        "your delivery bicycle",
        "A heavy chain and padlock are wrapped around the frame. The basket "
        "holds your parcel. Lock it up before you leave it, or it'll be stolen.",
        gate,
        ["lock bike", "examine bike"],
    )
    scenery(
        "gate",
        "a wrought-iron gate",
        "The gate features the Spooky family crest. It's closed.",
        gate,
    )

    # Front Door.
    scenery(
        "knocker",
        "a brass door knocker",
        "A heavy brass knocker shaped like a snarling gargoyle.",
        front_door,
        ["knock"],
    )

    # Vestibule: the coat tree (a surface for the hung raincoat).
    tree = scenery(
        "coat tree",
        "a coat tree",
        "An ornate coat tree, currently empty.",
        vestibule,
        ["hang raincoat"],
    )
    tree.make_surface()

    # Great Hall scenery.
    scenery(
        "paintings",
        "oil paintings",
        "Portraits of a distinguished-looking man and a pale-skinned woman.",
        great_hall,
    )
    scenery(
        "mirror",
        "a large mirror",
        "You see yourself: a damp, bedraggled courier in a green raincoat. "
        "Nothing unusual -- you still cast a perfectly ordinary reflection.",
        great_hall,
    )

    # Dining Room.
    scenery(
        "pheasant",
        "a whole roast pheasant",
        "Cold and unappetizing, with two drumsticks still attached. The meat "
        "smells like it would suit a wolf.",
        dining,
        ["use cleaver on pheasant"],
    )

    # Lounge: the gettable smoking jacket; brandy is fixed (you'll spill it).
    jacket = gettable(
        "jacket",
        "a red satin smoking jacket",
        "A red satin smoking jacket bearing the Spooky family crest.",
        lounge,
        ["get jacket", "wear jacket"],
    )
    jacket.set_property("wearable", True)
    scenery(
        "brandy",
        "a snifter of brandy",
        "A generous snifter of brandy, warming by the fire.",
        lounge,
        ["drink brandy", "sit by fire"],
    )

    # Kitchen: cleaver and olive oil.
    gettable(
        "cleaver",
        "a meat cleaver",
        "A heavy, well-honed meat cleaver.",
        kitchen,
        ["get cleaver", "use cleaver on pheasant"],
    )
    gettable(
        "oil",
        "a small bottle of olive oil",
        "The bottle of olive oil is almost empty -- enough for one good use.",
        kitchen,
        ["get oil", "use oil on shears"],
    )

    # Cellar: the garlic (gettable for a human courier).
    gettable(
        "garlic",
        "a few cloves of garlic",
        "Pungent cloves of garlic. They say vampires can't abide them.",
        cellar,
        ["get garlic", "use garlic on vanessa"],
    )

    # Library: the books (read/take are custom verbs).
    scenery(
        "books",
        "shelves of old books",
        "Most are dusty, but three catch your eye: Herbalism for Beginners, "
        "Mysteries of Ancient Egypt, and a first edition of Dante's Inferno.",
        library,
        [
            "read herbalism for beginners",
            "take mysteries of ancient egypt",
            "take dante's inferno",
        ],
    )
    scenery(
        "sarcophagus",
        "an Egyptian sarcophagus",
        "A heavy stone sarcophagus -- an antique, or a clever copy.",
        library,
    )

    # Secret Study: the silver pen (a human can take it) and the journal.
    gettable(
        "pen",
        "a silver fountain pen",
        "A beautiful silver fountain pen.",
        study,
        ["get pen", "give pen to lord spooky"],
    )
    journal = scenery(
        "journal",
        "Lord Spooky's journal",
        "It lies open to a week-old entry about a hunting trip, a rabid wolf, "
        "and his wounded servant Manfred. Something strange is afoot.",
        study,
        ["read journal"],
    )
    journal.set_property("is_readable", True)
    journal.set_property(
        "read_text",
        '"My servant Manfred and I went hunting today. A rabid wolf attacked '
        'and wounded him. Something strange is afoot..."',
    )
    scenery("desk", "a writing desk", "A spartan writing desk.", study)

    # Billiard Room: the pool cue (sharpen it) and the wolf pelt (gettable).
    scenery(
        "cue",
        "a hardwood pool cue",
        "Fine hardwood, tipped with a blunt brass cap. Sharpened, it could pass "
        "for a stake.",
        billiard,
        ["use cleaver on cue"],
    )
    gettable(
        "pelt",
        "a shaggy wolf pelt",
        "A shaggy wolf pelt from the trophy wall. Warm enough to ward off a "
        "chill -- or to clothe a naked man.",
        billiard,
        ["get pelt", "give pelt to manfred"],
    )
    scenery(
        "table",
        "a billiard table",
        "Billiard balls lie scattered mid-game.",
        billiard,
    )

    # Garden: the wolfsbane (recognized only after reading the herbalism book).
    scenery(
        "plants",
        "unusual plants",
        "All sorts of unusual plants. One of them, if you knew your herbalism, "
        "might be wolfsbane.",
        garden,
        ["examine wolfsbane", "take wolfsbane"],
    )
    scenery(
        "wolfsbane",
        "a sprig of wolfsbane growing in the garden",
        "You recall it's poisonous, but rumored to cure lycanthropes.",
        garden,
        ["take wolfsbane"],
    )

    # Reflecting Pool.
    scenery(
        "pool",
        "a marble reflecting pool",
        "You can see gardening shears resting in the middle of the pool. You'd "
        "have to wade in to reach them.",
        pool,
        ["enter pool"],
    )
    scenery(
        "fountain",
        "a wolf-shaped fountain",
        'A marble wolf bays at the moon. The Spooky motto is inscribed: "Mors '
        'Certa, Hora Incerta."',
        pool,
    )

    # Graveyard: the spade.
    gettable(
        "spade",
        "a gravedigger's spade",
        "An old but sturdy spade -- good for digging, or prying.",
        graveyard,
        ["get spade", "pry door"],
    )
    scenery(
        "crypt",
        "a moss-covered crypt",
        'An inscription reads "Lady Vanessa Spooky, RIP." The hinges are thick '
        "with rust; you'd need to pry the door open.",
        graveyard,
        ["pry door"],
    )

    # Hallway / Attic scenery.
    scenery(
        "trapdoor",
        "a trapdoor in the ceiling",
        "It looks like you can pull it open.",
        hallway,
        ["open trapdoor"],
    )
    scenery(
        "trunk",
        "an old steamer trunk",
        'The trunk is old but sturdy, labeled "Transylvania." It is locked.',
        attic,
    )

    # Master Suite scenery.
    scenery(
        "phonograph",
        "an old Victrola phonograph",
        "A trumpet-shaped speaker and a stylus, playing classical music.",
        master,
        ["stop phonograph"],
    )

    # --- Characters --------------------------------------------------------
    player = things.Character(
        "The player",
        "a courier for Parcel-E-Delivery",
        "I just need to deliver this parcel and get home through the rain.",
    )
    # The courier starts wearing a raincoat (padlock key in the pocket) and on
    # the bike (page 217).
    raincoat = things.Item(
        "raincoat",
        "a dark-green raincoat",
        "Your dark-green Parcel-E-Delivery raincoat. There's a padlock key in "
        "the pocket.",
    )
    raincoat.set_property("wearable", True)
    raincoat.set_owner(player)
    player.worn["raincoat"] = raincoat
    player.set_property("on_bike", True)

    wolf = things.Character(
        "wolf",
        "a monstrous wolf chained to the wall",
        "I strain against this chain. So hungry...",
    )
    wolf.examine_text = "The savage beast strains at the chain around its neck."
    wolf.talk_text = "The wolf only growls and snaps."
    cellar.add_character(wolf)

    # Manfred is created now but kept offstage until the wolf is cured; the cure
    # adds him to the cellar, and covering him moves him to the servants' room.
    manfred = things.Character(
        "manfred",
        "Manfred, the butler, naked but for a tin of peaches",
        "I was attacked while hunting with Lord Spooky. After that it's a blur.",
    )
    manfred.examine_text = (
        "A tall, gaunt man with thinning hair and a pencil-thin mustache, "
        "covering himself with a large tin of peaches."
    )
    manfred.talk_text = (
        '"I was attacked while hunting with Lord Spooky last week. Everything '
        'after that is just a blur."'
    )

    vanessa = things.Character(
        "vanessa",
        "the crypt's perfectly preserved occupant",
        "I sleep, and I hunger.",
    )
    vanessa.examine_text = (
        "A lovely young woman lies cold and motionless, a skeleton key on a "
        "ribbon around her pale throat -- and twin puncture wounds in her neck. "
        "A sleeping vampire, surely."
    )
    vanessa.talk_text = "She does not stir."
    family_crypt.add_character(vanessa)

    lord_spooky = things.Character(
        "lord spooky",
        "Lord Alastair Spooky, in a purple bathrobe",
        "Ah, a visitor. How novel.",
    )
    lord_spooky.examine_text = (
        "An elderly man with an immaculately groomed beard, smelling of "
        "peppermint shampoo and expensive aftershave."
    )
    lord_spooky.talk_text = '"Do you have a pen? One must sign for these things."'
    lord_spooky.talk_topics = {
        "front door": "\"Oh, I haven't left the manor for years. Manfred should "
        'have the key."',
        "manfred": '"Good chap. Terrible what happened. He will be missed."',
        "key": '"The front door? Manfred should have that key."',
    }

    # --- Assemble ----------------------------------------------------------
    custom_actions = [
        CarvePheasant,
        SharpenCue,
        OilShears,
        CureManfred,
        CoverManfred,
        GiveParcel,
        GivePen,
        UseGarlic,
        UseStake,
        LockBike,
        Knock,
        HangRaincoat,
        ReadHerbalism,
        TakeMysteries,
        TakeDante,
        TakeWolfsbane,
        EnterPool,
        Dive,
        SitByFire,
        DrinkBrandy,
        CutHedge,
        PryDoor,
        DigGrave,
        StopPhonograph,
        UseSkeletonKeyOnDoor,
        TakeSkeletonKey,
        AttackWolf,
        OpenTrapdoor,
        ShakeParcel,
    ]
    characters = [wolf, manfred, vanessa, lord_spooky]
    game = SpookyManor(gate, player, characters, custom_actions)

    # Register every room by name -- several hang off named one-way exits, and
    # the custom actions / set-pieces look rooms up by name.
    for loc in (
        gate,
        front_door,
        vestibule,
        great_hall,
        dining,
        lounge,
        kitchen,
        cellar,
        library,
        study,
        billiard,
        conservatory,
        garden,
        pool,
        maze,
        graveyard,
        family_crypt,
        hallway,
        attic,
        servants,
        master,
    ):
        game.locations.setdefault(loc.name, loc)

    # --- Gates (blocks) ----------------------------------------------------
    front_door.add_block(
        "enter house",
        CondBlock(
            "The door is shut. Perhaps you should KNOCK.",
            lambda: not front_door.get_property("knocked"),
        ),
    )
    vestibule.add_block(
        "north",
        CondBlock(
            '"And drip water all over the floor? Perhaps it would be polite to '
            'hang up your raincoat first." (HANG RAINCOAT)',
            lambda: not vestibule.get_property("raincoat_hung"),
        ),
    )
    front_door.add_block(
        "south",
        CondBlock(
            "The front door is locked tight -- it swung shut behind you. You'll "
            "need a key.",
            lambda: front_door.get_property("locked")
            and not front_door.get_property("unlocked"),
        ),
    )
    maze.add_block(
        "south",
        CondBlock(
            "The hedges are far too thick and tall to pass. You'd need to cut a "
            "way through.",
            lambda: not maze.get_property("cleared"),
        ),
    )
    graveyard.add_block(
        "crypt",
        CondBlock(
            "The crypt's stone door is rusted shut.",
            lambda: not graveyard.get_property("crypt_open"),
        ),
    )
    hallway.add_block(
        "west",
        CondBlock(
            "The west door is locked, and classical music plays behind it.",
            lambda: not hallway.get_property("master_unlocked"),
        ),
    )
    hallway.add_block(
        "up",
        CondBlock(
            "The trapdoor overhead is closed.",
            lambda: not hallway.get_property("trapdoor_open"),
        ),
    )

    return game


# ---------------------------------------------------------------------------
# Walkthrough (also the win test) -- wins 100/100
# ---------------------------------------------------------------------------

WALKTHROUGH = [
    "get parcel",
    "lock bike",  # +5 lock_bike
    "north",  # -> Front Door
    "knock",
    "enter house",  # -> Vestibule
    "hang raincoat",
    "north",  # -> Great Hall (front door locks behind you)
    "west",  # -> Dining Room
    "south",  # -> Lounge
    "get jacket",
    "north",  # -> Dining Room
    "north",  # -> Kitchen
    "get cleaver",
    "get oil",
    "down",  # -> Dark Cellar
    "get garlic",
    "up",  # -> Kitchen
    "south",  # -> Dining Room
    "use cleaver on pheasant",  # -> drumstick
    "east",  # -> Great Hall
    "east",  # -> Library
    "read herbalism for beginners",  # learn to recognize wolfsbane
    "take mysteries of ancient egypt",  # +10 secret_study (opens the study)
    "south",  # -> Secret Study
    "get pen",  # the silver pen (a human can take it)
    "read journal",
    "north",  # -> Library
    "north",  # -> Billiard Room
    "use cleaver on cue",  # -> stake
    "get pelt",
    "north",  # -> Conservatory
    "east",  # -> Garden
    "take wolfsbane",
    "north",  # -> Reflecting Pool
    "enter pool",  # -> shears; soaked & sick
    "south",  # -> Garden
    "use oil on shears",  # oil the shears (for the maze)
    "west",  # -> Conservatory
    "south",  # -> Billiard Room
    "south",  # -> Library
    "west",  # -> Great Hall
    "west",  # -> Dining Room
    "south",  # -> Lounge
    "wear jacket",
    "sit by fire",
    "drink brandy",  # +10 recover (now healthy enough to pry)
    "north",  # -> Dining Room
    "north",  # -> Kitchen
    "down",  # -> Dark Cellar
    "use wolfsbane on drumstick",  # +15 cure_manfred
    "give pelt to manfred",  # Manfred dressed; leaves
    "up",  # -> Kitchen
    "south",  # -> Dining Room
    "east",  # -> Great Hall
    "east",  # -> Library
    "north",  # -> Billiard Room
    "north",  # -> Conservatory
    "east",  # -> Garden
    "east",  # -> Hedge Maze
    "use shears",  # +10 hedge_maze (clears the path south)
    "south",  # -> Graveyard
    "get spade",
    "pry door",  # open the crypt (needs to be healthy)
    "crypt",  # -> Family Crypt
    "use garlic",  # stop her biting
    "use stake",  # +15 destroy_vampire; key drops
    "get key",  # +5 skeleton_key
    "out",  # -> Graveyard
    "north",  # -> Hedge Maze
    "west",  # -> Garden
    "west",  # -> Conservatory
    "south",  # -> Billiard Room
    "south",  # -> Library
    "west",  # -> Great Hall
    "up",  # -> Hallway
    "use skeleton key on door",  # unlock the master suite
    "west",  # -> Master Suite
    "stop phonograph",  # Lord Spooky emerges
    "give parcel to lord spooky",  # +5 deliver_parcel
    "give pen to lord spooky",  # +5 signature
    "out",  # -> Hallway
    "down",  # -> Great Hall
    "south",  # -> Vestibule
    "out",  # -> Front Door
    "use skeleton key on door",  # +10 escape_front (unlock the front door)
    "south",  # -> The Gate
    "east",  # ride home -> VICTORY (+5 ride_home, +5 finish)
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
