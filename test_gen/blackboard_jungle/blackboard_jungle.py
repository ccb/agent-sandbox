"""Blackboard Jungle — a Parsely game ported to the text_adventure_games engine.

You're a perpetually-in-trouble student at Parsely High. To survive one more day
you must dig your English homework out of your own combination locker and hand it
to Mr. Bushel — which means cracking your locker's combination (the clue is split
between the library cubby and a margin note in a book), and to even reach the
library you have to return the librarian's lost cat-eye glasses and mop up a
puddle of sick that will otherwise put you in the nurse's office. Source: Parsely
"Blackboard Jungle" (pages 75-84).

Authored the way the reference ports are (see ``action_castle_2.py`` and
``docs/converting-parsely-games.md``): a ``build_game()`` assembling the world, a
small ``BlackboardJungle`` Game subclass holding the win/score logic + the
"glasses make you blind" gag, the two-object gift/clean verbs via the engine's
``use_item_on`` factory, and a few custom ``Action`` subclasses for the genuinely
novel verbs (the combination lock).

Run interactively:    uv run python -m test_gen.blackboard_jungle.blackboard_jungle
Run the walkthrough:  uv run python -m test_gen.blackboard_jungle.blackboard_jungle --walk
"""

from text_adventure_games import games, things, actions, blocks

# ---------------------------------------------------------------------------
# Helpers (mirroring the reference ports' kit)
# ---------------------------------------------------------------------------


def _all_held(character):
    """Everything the character has on them: inventory + worn + wielded. WEAR
    moves an item out of ``inventory`` into ``worn``, so quest checks ("do you
    still have the glasses?") must look at the union, not bare inventory."""
    return {**character.inventory, **character.worn, **character.wielded}


def _is_holding(character, name):
    return name in _all_held(character)


def _take_held(character, name):
    """Remove and return a held item by name from wherever it lives, else None."""
    for store in (character.inventory, character.worn, character.wielded):
        if name in store:
            return store.pop(name)
    return None


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s canonical auto-reverse, so a
    named door ("enter library") doesn't silently wire a reverse that collides
    with another exit. (See the same helper in action_castle_2.py.)"""
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


# ---------------------------------------------------------------------------
# Game subclass: win condition, scoring, and the cat-eye-glasses blindness gag
# ---------------------------------------------------------------------------


class BlackboardJungle(games.Game):
    """Won by handing your English homework to Mr. Bushel. Every other ending
    (slipping on the puddle, getting locked in the library, four hours staring
    at the wall) is a loss -- ``game_over`` without ``handed_homework``."""

    # What you "see" while wearing the librarian's glasses (page 78: "The player
    # cannot see room contents, exits or examine objects while wearing the
    # glasses.").
    _BLUR = (
        "Everything is blurry and indistinct -- those aren't your prescription. "
        "Maybe TAKE OFF GLASSES."
    )

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        # Scoring table, page 84 (max 50): glasses 5, sweep 1, freshman 1,
        # return glasses 10, unlock locker 10, first try 2, homework 20,
        # finish 1.  score / _scored_keys / award() come from the base Game.
        self.max_score = 50
        self.tried_wrong_combo = False
        self.library_visits = 0

    # -- the glasses gag ----------------------------------------------------

    def _glasses_on(self) -> bool:
        return "glasses" in self.player.worn

    def describe(self) -> str:
        # Obscure the post-move room narration too, not just LOOK.
        if self._glasses_on():
            return self._BLUR
        return super().describe()

    def do_command(self, command: str) -> bool:
        cmd = (command or "").strip().lower()
        # While wearing the glasses you can't make out room contents or examine
        # anything -- intercept LOOK/EXAMINE before the parser narrates.
        if self._glasses_on() and (
            cmd in ("look", "l") or cmd.startswith(("look ", "l ", "examine ", "x "))
        ):
            self.parser.ok(self._BLUR)
            self.end_turn()
            return True

        before = self.player.location
        success = super().do_command(command)
        after = self.player.location
        if success and after is not None and after is not before:
            if after.name == "Classroom":
                self._arrive_classroom()
            elif after.name == "Library":
                self._arrive_library()
        return success

    # -- arrival set-pieces -------------------------------------------------

    def _arrive_classroom(self):
        """Mr. Bushel demands the homework on sight; with none to turn in he
        packs you off to the library for detention (page 83)."""
        if not _is_holding(self.player, "homework"):
            self.parser.ok(
                '"Late as usual, and no homework either?" Mr. Bushel sends you '
                "off to the library for detention."
            )
            library = self.locations["Library"]
            self.relocate(self.player, library)
            self._arrive_library()

    def _arrive_library(self):
        """Page 82: with no glasses to hand back, or on a second trip to
        detention, the day is lost -- you stare at the wall until the bell."""
        self.library_visits += 1
        if not _is_holding(self.player, "glasses") or self.library_visits > 1:
            self.end_in_death(
                "You spend the next four hours staring at the wall. THE END."
            )

    # -- win ---------------------------------------------------------------

    def is_won(self) -> bool:
        if self.player.get_property("handed_homework"):
            # +1 for finishing (page 84). Idempotent; announce_ending prints once.
            self.award("finish", 1)
            self.announce_ending(
                "Your scheme seems to have worked out, allowing you to survive "
                "one more day in the Blackboard Jungle. THE END.",
                show_score=True,
            )
            return True
        return False


# ---------------------------------------------------------------------------
# Two-object verbs (the engine's use_item_on factory)
# ---------------------------------------------------------------------------


def _clean_puddle(action):
    """Cover the puddle with pink sawdust and make the east hallway safe: flip
    Hallway West's east exit off the nurse's-office death and onto Hallway East."""
    g = action.game
    hw, he = g.locations["Hallway West"], g.locations["Hallway East"]
    hw.connections["east"] = he
    hw.travel_descriptions["east"] = "You walk to the eastern end of the hallway."
    he.connections["west"] = hw
    action.target.set_property("is_cleaned", True)


CleanPuddle = actions.use_item_on(
    "use sawdust on puddle",
    item="bucket",
    target="puddle",
    verb="use",
    preposition="on",
    description="Cover the puddle of sick with pink sawdust",
    aliases=[
        "use pink sawdust",
        "use bucket on puddle",
        "pour sawdust on puddle",
        "sprinkle sawdust on puddle",
        "clean puddle",
        "clean up the puddle",
    ],
    effect=_clean_puddle,
    award=("sweep", 1, "You cover up the slippery puddle. The hallway is now safe."),
    requires=lambda a: (
        "You've already cleaned that up."
        if a.target.get_property("is_cleaned")
        else None
    ),
    item_missing="You've nothing to soak it up with.",
    target_missing="There's nothing to clean up here.",
)


def _give_glasses(action):
    _take_held(action.character, "glasses")
    action.target.set_property("has_glasses", True)  # unblocks the library exit


GiveGlassesToLibrarian = actions.use_item_on(
    "give glasses to librarian",
    item="glasses",
    target="librarian",
    verb="give",
    preposition="to",
    description="Return the cat-eye glasses to the librarian",
    aliases=[
        "give glasses to ms. green",
        "return glasses",
        "hand glasses to librarian",
    ],
    effect=_give_glasses,
    award=(
        "return_glasses",
        10,
        "\"Oh, thank you so much for these! I can't see a thing without them! "
        'Now, run along." The librarian steps aside.',
    ),
    item_missing="You don't have the glasses.",
    target_missing="There's no one here to give them to.",
)


def _give_homework(action):
    action.character.set_property("handed_homework", True)


GiveHomeworkToBushel = actions.use_item_on(
    "give homework to bushel",
    item="homework",
    target="bushel",
    verb="give",
    preposition="to",
    description="Hand your English homework to Mr. Bushel",
    aliases=[
        "give homework to mr. bushel",
        "give homework to teacher",
        "hand in homework",
        "turn in homework",
    ],
    effect=_give_homework,
    award=("homework", 20, '"Well, well. Color me impressed!"'),
    item_missing="You have no homework to hand in.",
    target_missing="Mr. Bushel isn't here.",
)


# ---------------------------------------------------------------------------
# Custom actions (the combination lock + locker-room flavor)
# ---------------------------------------------------------------------------


class UseCombination(actions.Action):
    """The correct combination (8-16-32 -- the cubby's 16-32-64 "divided by
    two", per the book's margin note) opens the locker."""

    ACTION_NAME = "use combination 8-16-32"
    ACTION_DESCRIPTION = "Dial 8-16-32 into your locker's combination lock"
    ACTION_ALIASES = ["enter combination 8-16-32", "try 8-16-32"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.locker = self.game.locations["Hallway East"].items.get("locker")

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Hallway East":
            self.parser.fail("There's no locker here.")
            return False
        if self.locker is None or not self.locker.get_property("is_locked"):
            self.parser.fail("Your locker is already open.")
            return False
        return True

    def apply_effects(self):
        self.locker.set_property("is_locked", False)
        self.locker.set_property("is_closed", False)  # contents now reachable
        self.parser.ok("The locker opens. There are some typewritten papers inside.")
        self.game.award("locker", 10)
        if not self.game.tried_wrong_combo:
            self.game.award("first_try", 2, "Nailed it on the first try!")


class UseWrongCombination(actions.Action):
    ACTION_NAME = "use combination 16-32-64"
    ACTION_DESCRIPTION = "Dial 16-32-64 into your locker's combination lock"
    ACTION_ALIASES = ["enter combination 16-32-64", "try 16-32-64"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Hallway East":
            self.parser.fail("There's no locker here.")
            return False
        return True

    def apply_effects(self):
        self.game.tried_wrong_combo = True
        self.parser.ok("The numbers on the lock don't go that high.")


class OpenLocker(actions.Action):
    ACTION_NAME = "open locker"
    ACTION_DESCRIPTION = "Try to open your locker"
    ACTION_ALIASES = ["open my locker"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.locker = self.game.locations["Hallway East"].items.get("locker")

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Hallway East":
            self.parser.fail("There's no locker here.")
            return False
        return True

    def apply_effects(self):
        if self.locker.get_property("is_locked"):
            self.parser.ok("It's locked. There's a combination lock on it.")
        else:
            self.parser.ok(
                "Your locker hangs open. There are typewritten papers inside."
            )


class HelpFreshman(actions.Action):
    ACTION_NAME = "help freshman"
    ACTION_DESCRIPTION = "Help the freshman cowering in the janitor's cart"
    ACTION_ALIASES = ["free freshman", "rescue freshman", "help the freshman"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.freshman = self.parser.get_character("freshman")

    def check_preconditions(self) -> bool:
        if (
            self.freshman is None
            or self.freshman.location is not self.character.location
        ):
            self.parser.fail("There's no one here to help.")
            return False
        return True

    def apply_effects(self):
        self.character.location.remove_character(self.freshman)
        self.game.award("freshman", 1, "The freshman runs off crying.")


class PushCart(actions.Action):
    ACTION_NAME = "push cart"
    ACTION_DESCRIPTION = "Give the janitor's cart a shove"
    ACTION_ALIASES = ["push the cart"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Locker Room":
            self.parser.fail("There's no cart here.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "You hear someone cry out in alarm from inside the cart's trash can."
        )


class Sweep(actions.Action):
    ACTION_NAME = "sweep"
    ACTION_DESCRIPTION = "Sweep up with the broom"
    ACTION_ALIASES = ["sweep up", "sweep the floor"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "broom"):
            self.parser.fail("You've nothing to sweep with.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok("You'll make a fine janitor some day.")


# ---------------------------------------------------------------------------
# A block: the librarian keeps you in detention until her glasses come back
# ---------------------------------------------------------------------------


class LibrarianBlock(blocks.Block):
    """Page 82: GO OUT -> "You're here until the end of day!" -- the library
    exit is shut until the librarian has her cat-eye glasses back."""

    def __init__(self, librarian):
        super().__init__(
            "The librarian blocks your path",
            "The librarian blocks your path and squints at you. \"You're here "
            'until the end of day!"',
        )
        self.librarian = librarian

    def is_blocked(self) -> bool:
        return not self.librarian.get_property("has_glasses")


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> BlackboardJungle:
    L = things.Location

    gymnasium = L(
        "Gymnasium",
        "You are in the gym. It's currently devoid of sweaty athletes and "
        "cheering fans. You smell a locker room to the south. The exit is to "
        "the east. You see an eyeglasses case on the ground.",
    )
    locker_room = L(
        "Locker Room",
        "You are in one of Parsely High's locker rooms. There is a janitor's "
        "cart here.",
    )
    hallway_west = L(
        "Hallway West",
        "You're at the western end of a long hallway. Someone appears to have "
        "had tummy troubles; there's a puddle of sick on the floor. There's a "
        "classroom door here. The gym is to the west.",
    )
    hallway_east = L(
        "Hallway East",
        "You stand at the eastern end of a long hallway. There are rows of "
        "lockers on either side of you. You see the door leading to the library.",
    )
    library = L(
        "Library",
        "You're in the library, where you usually spend much of your time... "
        "after school, in detention. There is a study cubby here. There is a "
        "book here. Ms. Green, the librarian, is here.",
    )
    classroom = L(
        "Classroom",
        "You step into the classroom, and your English teacher, Mr. Bushel, "
        "clears his throat.",
    )
    # A game-over room: slipping on the uncleaned puddle (page 80) drops you here.
    nurse = L(
        "Nurse's Office",
        "You slip on the puddle of sick and fall, sustaining a mild concussion. "
        "You wake up in the nurse's office with a terrible headache and blurred "
        "vision. The school nurse sends you to the hospital for an MRI, just in "
        "case. THE END.",
    )
    nurse.set_property("game_over", True)

    # --- Connections -------------------------------------------------------
    gymnasium.add_connection("south", locker_room, "You head into the locker room.")
    gymnasium.add_connection(
        "east", hallway_west, "You step into the western end of the hallway."
    )
    # Hallway West's EAST starts as the puddle death; CleanPuddle re-points it to
    # Hallway East. The classroom door is a named one-way (its auto-reverse would
    # otherwise collide with the east exit's reverse).
    _one_way(hallway_west, "east", nurse)
    _one_way(hallway_west, "enter classroom", classroom)
    _one_way(classroom, "out", hallway_west)
    # Hallway East <-> Library through the library door (named, so no stray
    # auto-reverse); the way back out is gated by the LibrarianBlock.
    _one_way(hallway_east, "enter library", library)
    _one_way(hallway_east, "west", hallway_west)
    _one_way(library, "out", hallway_east)

    # --- Items: scenery helper --------------------------------------------
    def scenery(name, desc, examine, loc, hints=()):
        it = things.Item(name, desc, examine)
        it.set_property("gettable", False)
        for h in hints:
            it.add_command_hint(h)
        loc.add_item(it)
        return it

    # Gym: the eyeglasses case is an (open) container holding the glasses.
    case = things.Item(
        "case", "an eyeglasses case", "Inside the case are a pair of cat-eye glasses."
    )
    case.set_property("gettable", False)
    case.make_container()
    case.add_command_hint("examine case")
    glasses = things.Item(
        "glasses",
        "a pair of bedazzled cat-eye glasses",
        "The bedazzled cat-eye glasses aren't really your style.",
    )
    glasses.set_property("wearable", True)
    glasses.add_command_hint("wear glasses")
    glasses.add_command_hint("give glasses to librarian")
    case.add_item(glasses)
    gymnasium.add_item(case)

    # Locker Room: the janitor's cart, its takeable bucket + broom, the freshman.
    cart = scenery(
        "cart",
        "a janitor's cart",
        "The janitor's cart is more or less a trash can on wheels. A bucket of "
        "pink sawdust and a broom hang from the cart.",
        locker_room,
        ["examine cart", "push cart"],
    )
    scenery(
        "trash can",
        "the cart's trash can",
        "You peer inside and find a freshman cowering at the bottom.",
        locker_room,
        ["examine trash can"],
    )
    bucket = things.Item(
        "bucket",
        "a bucket of pink sawdust",
        "A bucket of pink sawdust -- the janitor's best friend for a wet floor.",
    )
    bucket.add_command_hint("get bucket")
    bucket.add_command_hint("use pink sawdust")
    locker_room.add_item(bucket)
    broom = things.Item("broom", "a broom", "A sturdy janitor's broom.")
    broom.add_command_hint("get broom")
    broom.add_command_hint("sweep")
    locker_room.add_item(broom)

    # Hallway West: the puddle (cleaned by sawdust) + the classroom door.
    puddle = scenery(
        "puddle",
        "a puddle of sick on the floor",
        "Yuck. Looks like it was Salisbury steak day. Where's the school janitor "
        "when you need him?",
        hallway_west,
        ["use pink sawdust"],
    )
    puddle.set_property("is_cleaned", False)
    scenery(
        "door",
        "a classroom door",
        "Through the window you see Mr. Bushel discussing last night's homework. "
        "Oops.",
        hallway_west,
        ["examine door", "enter classroom"],
    )

    # Hallway East: the lockers, the lock, and your locker (a locked container
    # holding the homework).
    scenery(
        "lockers",
        "rows of lockers",
        "You find your locker. At least you think it's your locker -- it's been "
        "a while since you opened it.",
        hallway_east,
        ["examine lockers", "open locker"],
    )
    scenery(
        "lock",
        "a combination lock",
        "The lock is your basic tempered steel, 32-digit combination lock. Very "
        "hard to crack! You've tried.",
        hallway_east,
        ["examine lock", "use combination 8-16-32"],
    )
    locker = things.Item(
        "locker", "your locker", "Your locker, with a combination lock on it."
    )
    locker.set_property("gettable", False)
    locker.make_container()
    locker.set_property("is_closed", True)
    locker.set_property("is_locked", True)
    homework = things.Item(
        "homework",
        "your typewritten English homework",
        "It's your English homework -- something about something you were "
        "supposed to read. You paid good money for this!",
    )
    homework.add_command_hint("get homework")
    homework.add_command_hint("give homework to bushel")
    locker.add_item(homework)
    hallway_east.add_item(locker)

    # Library: the book (the combination clue) and the study cubby.
    book = things.Item(
        "book",
        "a copy of Cryptography for Dummies",
        "The book's title is Cryptography for Dummies. You remember skimming it "
        "during detention yesterday, but that seems like a long time ago.",
    )
    book.set_property("is_readable", True)
    book.set_property(
        "read_text",
        'You flip it open. Someone wrote "Divide by two" in the margin. Oh, that '
        "was you!",
    )
    book.add_command_hint("read book")
    library.add_item(book)
    scenery(
        "cubby",
        "a study cubby",
        "The wood desk has the numbers 16-32-64 scratched into it.",
        library,
        ["examine cubby"],
    )

    # --- Characters --------------------------------------------------------
    player = things.Character(
        "The player",
        "a student at Parsely High trying to survive another day",
        "I just need to hand in my English homework before I get in more trouble.",
    )

    freshman = things.Character(
        "freshman",
        "a frightened freshman hiding in the trash can",
        "I'm hiding in the trash can. Please don't tell anyone!",
    )
    freshman.talk_text = '"Are you serious? Someone might see you!"'
    locker_room.add_character(freshman)

    librarian = things.Character(
        "librarian", "Ms. Green, the librarian", "Detention again, I see."
    )
    librarian.examine_text = 'She squints at you and asks, "Back again, eh?"'
    librarian.talk_text = 'She squints at you. "You\'re here until the end of day!"'
    librarian.set_property("has_glasses", False)
    library.add_character(librarian)

    bushel = things.Character(
        "bushel", "Mr. Bushel, your English teacher", "I expect homework on time."
    )
    bushel.examine_text = "Your English teacher, holding out an expectant hand."
    bushel.talk_text = '"Late as usual. I sincerely hope you remembered your homework."'
    classroom.add_character(bushel)

    # --- Assemble ----------------------------------------------------------
    custom_actions = [
        CleanPuddle,
        GiveGlassesToLibrarian,
        GiveHomeworkToBushel,
        UseCombination,
        UseWrongCombination,
        OpenLocker,
        HelpFreshman,
        PushCart,
        Sweep,
    ]
    characters = [freshman, librarian, bushel]
    game = BlackboardJungle(gymnasium, player, characters, custom_actions)

    # Register every room by name -- the nurse's office and the classroom/library
    # hang off named one-way exits, and _arrive_classroom() looks the library up
    # by name for the detention relocation.
    for loc in (
        gymnasium,
        locker_room,
        hallway_west,
        hallway_east,
        library,
        classroom,
        nurse,
    ):
        game.locations.setdefault(loc.name, loc)

    library.add_block("out", LibrarianBlock(librarian))

    # +5 the moment you pick up the librarian's glasses (page 84). Idempotent
    # award via a repeatable trigger, phrasing-independent (get glasses / take
    # them from the case both trip it).
    game.add_trigger(
        "score_glasses",
        lambda g: _is_holding(g.player, "glasses"),
        lambda g: g.award("glasses", 5),
        repeatable=True,
    )
    return game


# ---------------------------------------------------------------------------
# Walkthrough (also the win test)
# ---------------------------------------------------------------------------

WALKTHROUGH = [
    "get glasses",  # +5 (from the eyeglasses case)
    "south",  # -> Locker Room
    "help freshman",  # +1
    "get bucket",
    "north",  # -> Gymnasium
    "east",  # -> Hallway West
    "use pink sawdust",  # +1; makes the east hallway safe
    "east",  # -> Hallway East
    "enter library",  # -> Library (holding glasses, first visit: safe)
    "examine cubby",  # clue: 16-32-64
    "read book",  # clue: "divide by two" -> 8-16-32
    "give glasses to librarian",  # +10; unblocks the exit
    "out",  # -> Hallway East
    "use combination 8-16-32",  # +10 unlock, +2 first try
    "get homework",
    "west",  # -> Hallway West
    "enter classroom",  # -> Classroom (homework in hand: no detention)
    "give homework to bushel",  # +20, +1 finish -> win
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
