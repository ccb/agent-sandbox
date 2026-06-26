"""Flaming Goat -- a Parsely one-joke micro-game ported to the engine.

You step off a train onto a deserted subway platform. The UP escalator is dead
(it's "just stairs" now), so you must WALK UP it -- only to find, midway, a
flaming goat blocking your path. The goat is angry *and* hungry. Coax a can of
soda out of the busted vending machine, douse the goat to put out the fire
(angry -> merely hungry), then feed it the empty can; it wanders off chewing and
you're free to finish your commute. Reaching the top wins 1,000 points.
Source: Parsely "Flaming Goat" (pages 116-118).

Authored the way the reference ports are (see ``action_castle_2.py`` and
``docs/converting-parsely-games.md``): a ``build_game()`` that assembles the
world, a tiny ``FlamingGoat`` Game subclass holding the win/score logic and the
escalator's WALK-only gag, the two two-object verbs (POUR SODA ON GOAT, FEED CAN
TO GOAT) via the engine's ``use_item_on`` factory, and a few small ``Action``
subclasses for the one-off verbs.

The one place the source needs interpreting: Parsely distinguishes GO UP (the
escalator "goes nowhere") from WALK UP (you climb the dead steps). The engine
treats both as the direction "up", so the WALK-only gag is enforced in
``do_command`` -- a plain GO/ride UP is intercepted with the book's line, and
only an explicit WALK UP / WALK DOWN actually climbs the stairs.

Run interactively:    uv run python -m test_gen.flaming_goat.flaming_goat
Run the walkthrough:  uv run python -m test_gen.flaming_goat.flaming_goat --walk
"""

from text_adventure_games import games, things, actions, blocks


def _holding(character, name):
    """True if *character* carries *name* in hand, on body, or wielded."""
    return (
        name in character.inventory
        or name in character.worn
        or name in character.wielded
    )


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s auto-reverse, so the dead
    escalator's "up"/"down" don't silently wire colliding reverse exits. (Same
    helper as the other ports.)"""
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


# ---------------------------------------------------------------------------
# Block: the goat bars the way up the broken escalator until it wanders off.
# ---------------------------------------------------------------------------


class GoatBlock(blocks.Block):
    """Blocks WALK UP from the Broken Escalator while the goat is in the way.
    Its description tracks the goat's state (refreshed each time it's queried,
    right before the location reads it) so the failure line reads true whether
    the goat is still aflame or merely hungry."""

    def __init__(self, game):
        super().__init__("A flaming goat", "A flaming goat stands in the way.")
        self.game = game

    def is_blocked(self) -> bool:
        if self.game.goat_gone:
            return False
        if self.game.goat_on_fire:
            self.description = "A flaming goat stands in the way."
        else:
            self.description = (
                "The goat -- no longer aflame, but still hungry -- blocks your path."
            )
        return True


# ---------------------------------------------------------------------------
# Game subclass: the WALK-only escalator gag, the win, and the score.
# ---------------------------------------------------------------------------


class FlamingGoat(games.Game):
    """Won by walking up to the top of the broken escalator (+1,000 points)."""

    # Bare/ridden movement that the dead escalator refuses -- you must WALK.
    _DEAD_UP = {"up", "u", "go up", "go u", "ride up", "ascend", "climb up"}
    _DEAD_DOWN = {"down", "d", "go down", "go d", "ride down", "descend", "climb down"}

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        self.max_score = 1000  # the lone scoring event (page 118)
        self.can_dropped = False  # the vending machine yields its can once
        self.goat_on_fire = True  # doused by POUR SODA ON GOAT
        self.goat_gone = False  # sent packing by FEED CAN TO GOAT
        self.escaped = False  # reached the top -> win
        self.goat = None  # resolved in build_game()

    def do_command(self, command: str) -> bool:
        cmd = (command or "").strip().lower()
        loc = self.player.location

        # The escalator is dead: GO/ride UP "goes nowhere"; you must WALK UP.
        if loc is not None and loc.name == "Subway Platform" and cmd in self._DEAD_UP:
            self.parser.ok(
                "You step onto the bottom step and are surprised to find that "
                "you go nowhere. (The escalator is broken -- you'll have to WALK UP.)"
            )
            self.end_turn()
            return True
        if (
            loc is not None
            and loc.name == "Broken Escalator"
            and (cmd in self._DEAD_UP or cmd in self._DEAD_DOWN)
        ):
            self.parser.ok("The escalator continues to not work.")
            self.end_turn()
            return True

        before = self.player.location
        success = super().do_command(command)
        after = self.player.location
        if (
            success
            and after is not None
            and after is not before
            and after.name == "Top of Broken Escalator"
        ):
            self._arrive_top()
        return success

    def _arrive_top(self):
        """Cresting the dead escalator ends the commute -- and the game. (Go has
        already printed the room's THE END description, this room being a
        ``game_over`` location; here we just bank the 1,000 points.)"""
        if not self.escaped:
            self.escaped = True
            self.award("escape", 1000)

    def is_won(self) -> bool:
        return bool(self.escaped)


# ---------------------------------------------------------------------------
# One-off verbs (Subway Platform)
# ---------------------------------------------------------------------------


class ShakeVendingMachine(actions.Action):
    """SHAKE / PUNCH / KICK the vending machine -- a can of soda drops out."""

    ACTION_NAME = "shake vending machine"
    ACTION_DESCRIPTION = "Shake, punch or kick the vending machine"
    ACTION_ALIASES = [
        "punch vending machine",
        "kick vending machine",
        "hit vending machine",
        "shake the vending machine",
        "punch the vending machine",
        "kick the vending machine",
        "shake machine",
        "punch machine",
        "kick machine",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Subway Platform":
            self.parser.fail("There's no vending machine here.")
            return False
        return True

    def apply_effects(self):
        if self.game.can_dropped:
            self.parser.ok("You give it another whack, but nothing else comes out.")
            return
        self.game.can_dropped = True
        can = things.Item(
            "can",
            "a can of soda",
            "A warm, unopened can of soda. It's dusted with an acceptable amount "
            "of rat and insect droppings.",
        )
        can.add_command_hint("get can")
        can.add_command_hint("pour soda on goat")
        self.character.location.add_item(can)
        self.parser.ok("A can of soda drops out of the machine.")


class OpenCan(actions.Action):
    """OPEN CAN -- pure flavor; pops the top with a satisfying hiss."""

    ACTION_NAME = "open can"
    ACTION_DESCRIPTION = "Pop the top of the can of soda"
    ACTION_ALIASES = [
        "open the can",
        "open can of soda",
        "open soda",
        "pop the can",
        "open the soda",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if not _holding(self.character, "can"):
            self.parser.fail("You don't have a can to open.")
            return False
        return True

    def apply_effects(self):
        can = self.character.inventory.get("can")
        if can is not None and can.get_property("is_open"):
            self.parser.ok("The can is already open.")
            return
        if can is not None:
            can.set_property("is_open", True)
        self.parser.ok(
            'You pop the top of the can. It lets out a pleasant "hssssss..."'
        )


class DrinkSoda(actions.Action):
    """DRINK SODA -- pure flavor; you're not thirsty, and it's warm anyway."""

    ACTION_NAME = "drink soda"
    ACTION_DESCRIPTION = "Drink the soda"
    ACTION_ALIASES = ["drink the soda", "drink can", "drink the can", "drink soda can"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if not _holding(self.character, "can"):
            self.parser.fail("You don't have anything to drink.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok("You're not thirsty. Also, it's warm.")


# ---------------------------------------------------------------------------
# Two-object verbs (Broken Escalator) -- the engine's use_item_on factory
# ---------------------------------------------------------------------------


def _pour_soda(action):
    g = action.game
    g.goat_on_fire = False
    action.item.set_property("is_empty", True)
    action.item.examine_text = "An empty soda can. Goats are said to love these."
    goat = g.goat
    goat.examine_text = "The goat is no longer on fire, but it still looks hungry."
    goat.description = "a goat, no longer aflame but still hungry"


PourSodaOnGoat = actions.use_item_on(
    "pour soda on goat",
    item="can",
    target="goat",
    verb="pour",
    preposition="on",
    description="Pour the can of soda over the flaming goat",
    aliases=[
        "pour can on goat",
        "pour soda over goat",
        "pour the soda on the goat",
        "pour soda on the goat",
        "empty can on goat",
    ],
    effect=_pour_soda,
    success=(
        "The flames hiss and die. The goat is no longer angry -- but it remains "
        "hungry. The soda can is now empty."
    ),
    requires=lambda a: (
        "The goat has already wandered off."
        if a.game.goat_gone
        else ("The goat's flames are already out." if not a.game.goat_on_fire else None)
    ),
    item_missing="You don't have a can of soda.",
    target_missing="There's no goat here.",
)


def _feed_goat(action):
    g = action.game
    g.goat_gone = True
    goat = g.goat
    loc = goat.location
    if loc is not None and goat.name in loc.characters:
        loc.remove_character(goat)
    g.parser.ok(
        "The goat bites the can and wanders off with it, chewing noisily. The "
        "way up is clear at last. (WALK UP.)"
    )


FeedCanToGoat = actions.use_item_on(
    "feed can to goat",
    item="can",
    target="goat",
    verb="feed",
    preposition="to",
    description="Feed the empty can to the goat",
    aliases=[
        "give can to goat",
        "give the can to the goat",
        "feed the can to the goat",
        "feed goat",
        "feed the goat",
        "give can",
        "give goat the can",
    ],
    effect=_feed_goat,
    consume=True,  # the goat takes the can with it
    requires=lambda a: (
        "The goat has already wandered off."
        if a.game.goat_gone
        else (
            "The goat is on fire and far too angry to take anything from you. "
            "Put it out first."
            if a.game.goat_on_fire
            else None
        )
    ),
    item_missing="You don't have the can.",
    target_missing="There's no goat here.",
)


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> FlamingGoat:
    L = things.Location

    subway = L(
        "Subway Platform",
        "You exit the train and find yourself standing all alone on a subway "
        "platform. A battered vending machine hums against the wall. A dead UP "
        "escalator leads out -- you'll have to WALK UP it.",
    )
    escalator = L(
        "Broken Escalator",
        "You are standing midway up a broken escalator. A flaming goat blocks "
        "your path.",
    )
    top = L(
        "Top of Broken Escalator",
        "You are standing at the top of a broken escalator. You may now resume "
        "your daily commute. What was up with that goat, eh? THE END.",
    )
    # Cresting the top finishes the game (the "return home" ending pattern from
    # the conversion guide -- Go honors a destination's game_over property).
    top.set_property("game_over", True)

    all_locations = [subway, escalator, top]

    # The only real exits are WALKED: up the steps and back down. (Plain GO/ride
    # UP is intercepted in FlamingGoat.do_command with the book's gag line.)
    _one_way(subway, "up", escalator)  # WALK UP
    _one_way(escalator, "down", subway)  # WALK DOWN
    _one_way(escalator, "up", top)  # WALK UP, once the goat is gone

    # --- Scenery (examinable, not gettable) -------------------------------
    def scenery(name, desc, examine, loc, hints=()):
        it = things.Item(name, desc, examine)
        it.set_property("gettable", False)
        for h in hints:
            it.add_command_hint(h)
        loc.add_item(it)
        return it

    scenery(
        "vending machine",
        "a battered vending machine",
        "The battered and abused machine appears to be without power.",
        subway,
        ["shake vending machine"],
    )
    scenery(
        "escalator",
        "a broken escalator",
        "The escalator is broken. Now it is just stairs. (WALK UP.)",
        subway,
        ["walk up"],
    )

    # --- The goat ---------------------------------------------------------
    goat = things.Character(
        "goat",
        "a goat wreathed in flame",
        "I am angry. I am hungry. I am on fire.",
    )
    goat.examine_text = "The goat is on fire. It looks angry and hungry."
    escalator.add_character(goat)

    # --- Player -----------------------------------------------------------
    player = things.Character(
        "the player",
        "a weary late-night commuter",
        "I just want to get home.",
    )

    custom_actions = [
        ShakeVendingMachine,
        OpenCan,
        DrinkSoda,
        PourSodaOnGoat,
        FeedCanToGoat,
    ]
    game = FlamingGoat(subway, player, characters=[goat], custom_actions=custom_actions)
    game.goat = goat

    # Register every room by name (the do_command arrival hook looks rooms up by
    # name, and the named one-way exits resolve through game.locations).
    for loc in all_locations:
        game.locations.setdefault(loc.name, loc)

    # The goat bars the way up until it has been doused and fed.
    escalator.add_block("up", GoatBlock(game))

    return game


# ---------------------------------------------------------------------------
# Walkthrough (also the win test) -- wins at 1000/1000
# ---------------------------------------------------------------------------

WALKTHROUGH = [
    "shake vending machine",  # a can of soda drops out
    "get can",
    "walk up",  # -> Broken Escalator (the goat bars the way up)
    "pour soda on goat",  # douse the flames: angry -> merely hungry
    "feed can to goat",  # it takes the can and wanders off
    "walk up",  # -> Top of Broken Escalator; +1000 -> WIN
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
