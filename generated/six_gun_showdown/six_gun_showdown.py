"""Six-Gun Showdown -- a Parsely game ported to the text_adventure_games engine.

You're a washed-up sheriff's son, fresh out of the drunk tank with shaking hands,
a copper penny and your pa's silver badge. To reclaim your name you must: strap on
pa's pistol, get fleeced into (and win) a hand of poker with the outlaw Black Jack
Baker, lift the treasure map off his table, grub a rucksack of supplies from Mariah
Cooper, cross the badlands alive (rationing water, surviving a night's camp and the
rattlesnake in your boot), dig the buried gold out of Parson's claim, trade a dead
snake to a traveling snake-oil doctor to cure your tremors, and finally out-draw
Black Jack in a high-noon showdown -- then pin the badge back on. Source: Parsely
"Six-Gun Showdown" (pages 169-190).

Authored the way the reference ports are (see ``action_castle_2.py`` and
``docs/converting-parsely-games.md``): a ``build_game()`` assembling the world, a
``SixGunShowdown`` Game subclass holding the win/score logic plus the cross-cutting
state machines (the thirst counter, the poker hand, the night's camp, the duel),
two-object verbs via the engine's ``use_item_on`` factory, a few ``blocks.Block``
gates, and custom ``Action`` subclasses for the genuinely novel verbs.

Run interactively:    uv run python -m test_gen.six_gun_showdown.six_gun_showdown
Run the walkthrough:  uv run python -m test_gen.six_gun_showdown.six_gun_showdown --walk
"""

from text_adventure_games import games, things, actions, blocks

# ---------------------------------------------------------------------------
# Helpers (mirroring the reference ports' kit)
# ---------------------------------------------------------------------------


def _all_held(character):
    """Everything the character can reach: inventory + the contents of any
    carried (open) container + worn + wielded. WEAR/WIELD move an item out of
    ``inventory``, and gear often rides inside the rucksack, so quest checks
    must look at the union -- not bare inventory (see the guide's pitfalls)."""
    return {**character.carried_items(), **character.worn, **character.wielded}


def _is_holding(character, name):
    return name in _all_held(character)


def _take_held(character, name):
    """Remove and return a held item by name from wherever it lives, else None."""
    item = _all_held(character).get(name)
    if item is not None:
        character.discard_item(item)
    return item


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s canonical auto-reverse, so a
    named exit ("cave", "back to town") doesn't silently wire a reverse that
    collides with another exit. (Same helper as action_castle_2.py.)"""
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


def _fixture(name, description, examine, loc, hints=()):
    """A non-gettable scenery item you can EXAMINE but not pick up."""
    it = things.Item(name, description, examine)
    it.set_property("gettable", False)
    for h in hints:
        it.add_command_hint(h)
    loc.add_item(it)
    return it


class CondBlock(blocks.Block):
    """A one-off gate: blocked while ``predicate()`` is true, with a fixed
    message. Used for the supplies gate, the camp gate, the cave squeeze, the
    'nothing north yet' gate and the wagon ride."""

    def __init__(self, name, description, predicate):
        super().__init__(name, description)
        self._predicate = predicate

    def is_blocked(self) -> bool:
        return self._predicate()


# ---------------------------------------------------------------------------
# Game subclass: win/score logic + the cross-cutting set-piece state machines
# ---------------------------------------------------------------------------


class SixGunShowdown(games.Game):
    """Won by out-drawing Black Jack and pinning your pa's badge back on. The
    journey threads several state machines that don't belong to any one verb --
    the desert thirst counter, the poker hand, the overnight camp, the noon duel
    -- so they live here and are driven from ``do_command`` and small helpers."""

    # The four desert rooms that prompt a drink; you carry water for three sips,
    # and cutting the cactus buys a fourth -- exactly enough to cross (page 178).
    DRINK_ROOMS = {
        "Desert",
        "Desert (Creosote Bushes)",
        "Desert (Arroyo)",
        "Desert (Cow Skull)",
    }

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        # Scoring table, page 190 (max 100). score / _scored_keys / award() come
        # from the base Game; the keys mirror the rulebook's lines.
        self.max_score = 100

        # Curable affliction: the shakes. Blocks WEAR BADGE and any chance in the
        # duel until the snake-oil cure (page 189).
        self.player.set_property("hands_shaky", True)

        # Saloon / poker flags.
        self.seen_blackjack = False  # the bartender's warning reveals him
        self.has_cards = False  # anted the badge, holding a hand
        self.drew_card = False  # drew the third deuce -> full house
        self.bj_enraged = False  # called his bluff; he's drawn his knife
        self.bj_out = False  # knocked cold with the bottle

        # Desert thirst counter.
        self.water_rations = 3
        self._drunk_at = set()
        self._pending_drink = None
        self._thirst_strikes = 0

        # Overnight camp state machine.
        self.fire_built = False
        self.fire_lit = False
        self.beans_cooked = False
        self.beans_eaten = False
        self.camp_morning = False
        self.snake_seen = False
        self.snake_out = False
        self.snake_dead = False
        self.boots_back_on = False
        self.camp_complete = False

        # Endgame flags.
        self.sun_ready = False  # the sun's in Black Jack's eyes
        self.bj_defeated = False

        # The badge leaves your pocket when you ante it; we keep a handle so
        # Mariah can fish it back out of Black Jack's pocket at the end.
        self._badge = None

    # -- command interception ----------------------------------------------

    def do_command(self, command: str) -> bool:
        cmd = (command or "").strip().lower()
        here = self.player.location.name if self.player.location else ""

        # Saloon: once the bartender has nodded toward the back table, meeting
        # Black Jack's eyes drags you into his poker game (page 172 -> 174).
        if (
            here == "Saloon"
            and self.seen_blackjack
            and self._examines(cmd, "black jack")
        ):
            self._start_poker()
            return True

        # Showdown: it's a waiting game. Any WAIT or EXAMINE lets the sun climb
        # over the clock tower into Black Jack's eyes (page 190).
        if (
            here == "The Six-Gun Showdown"
            and not self.bj_defeated
            and (cmd in ("wait", "z") or cmd.startswith(("examine ", "x ", "look")))
        ):
            self._sun_climbs()
            return True

        before = self.player.location
        success = super().do_command(command)
        if success:
            self._after_move(before, self.player.location)
        return success

    @staticmethod
    def _examines(cmd, noun):
        return noun in cmd and cmd.startswith(("examine ", "x ", "look"))

    def _after_move(self, before, after):
        """Thirst bookkeeping and a couple of arrival set-pieces."""
        if before is after or after is None:
            return

        # Left a drink-room without drinking? Two strikes and the desert takes you.
        if (
            before is not None
            and before.name in self.DRINK_ROOMS
            and self._pending_drink == before.name
        ):
            self._pending_drink = None
            self._thirst_strikes += 1
            if self._thirst_strikes >= 2:
                self.end_in_death(
                    "Tired and parched, you stagger on. A lizard runs over your "
                    'boot, looks up and says, "Howdy, pardner!" Surely that can\'t '
                    "be right. You collapse and perish. THE END."
                )
                return
            self.parser.ok(
                "Your throat is bone dry and your head is swimming. You'd best "
                "drink while you still can."
            )

        # Arriving at a fresh drink-room: dry-mouth prompt.
        if after.name in self.DRINK_ROOMS and after.name not in self._drunk_at:
            self._pending_drink = after.name
            self.parser.ok(
                "Your mouth is awful dry. Maybe it's time for a drink of water."
            )

        # The gang lies in wait the moment you hike back into town.
        if after.name == "Main Street Clock Tower":
            bj = self.characters.get("black jack")
            if bj is not None and bj.location is not after:
                self.relocate(bj, after)

        # Stepping out of the cave, you spot Doc Hensley's dust to the north.
        if after.name == "Rocky Bluff" and before.name == "Dark Cave":
            self.parser.ok(
                "You emerge blinking into the morning sun. To the north, you can "
                "just make out a cloud of dust -- a buckboard wagon rolling across "
                "the desert."
            )

    # -- the poker set-piece (Black Jack's Table) ---------------------------

    def _start_poker(self):
        table = self.locations["Black Jack's Table"]
        saloon = self.locations["Saloon"]
        bj = self.characters["black jack"]
        self.parser.ok(
            'Black Jack stands, idly thumbing his bowie knife. "Well, well. How '
            "the mighty have fallen. Why don't you sit yourself down and play a "
            "hand with me and the boys, for old times' sake?\" It does not look "
            "like he's asking."
        )
        if bj.location is saloon:
            saloon.remove_character(bj)
        table.add_character(bj)
        self.relocate(self.player, table)
        self.parser.ok(self.describe())
        self.end_turn()

    def _sun_climbs(self):
        self.sun_ready = True
        self.parser.ok(
            "The sun climbs higher into the sky, peeking up over the clock tower. "
            "Black Jack squints and shades his eyes against the harsh glare."
        )
        self.end_turn()

    # -- win ----------------------------------------------------------------

    def is_won(self) -> bool:
        if self.player.get_property("is_sheriff"):
            self.award("finish", 5)  # +5 for finishing without saving (page 190)
            self.announce_ending(
                "You pin the badge on your chest. The Law is back in town. THE END.",
                show_score=True,
            )
            return True
        return False


# ---------------------------------------------------------------------------
# Two-object verbs (the engine's use_item_on factory)
# ---------------------------------------------------------------------------


def _show_map_to_mariah(action):
    """Mariah recognizes Parson's claim and offers a grubstake -- a yes/no the
    player answers in plain words via a posed prompt (engine feature #110)."""
    from text_adventure_games import Prompt

    action.game.pose_prompt(
        Prompt(
            text=(
                "\"That's the old Parson claim! Long since dried up, they say, but "
                "if you're fool enough to walk ten miles through the desert, I'll "
                "grubstake you so you don't die out there -- for a share of whatever "
                'you find. Agreed?"'
            ),
            options={
                "yes": "seal the deal",
                "shake hand": "seal the deal",
                "shake": "seal the deal",
                "no": "refuse the deal",
            },
        )
    )


ShowMapToMariah = actions.use_item_on(
    "show map to mariah",
    item="map",
    target="mariah",
    verb="show",
    preposition="to",
    description="Show Mariah Cooper the treasure map",
    aliases=["show poster to mariah", "show map", "show mariah the map"],
    effect=_show_map_to_mariah,
    item_missing="You don't have any map to show.",
    target_missing="There's no one here to show it to.",
)


def _cut_cactus(action):
    action.game.water_rations += 1  # one extra ration of water (page 180)


CutCactus = actions.use_item_on(
    "cut cactus",
    item="knife",
    target="cactus",
    verb="cut",
    preposition="with",
    description="Cut into the cactus with your bowie knife for water",
    aliases=["cut open cactus", "cut the cactus", "use knife on cactus"],
    effect=_cut_cactus,
    award=(
        "cactus",
        5,
        "You cut into the cactus and catch some precious drops of water in your "
        "canteen.",
    ),
    requires=lambda a: (
        "You've already wrung this cactus dry."
        if a.target.get_property("cut_open")
        else None
    ),
    item_missing="You'll need something sharp to cut it open.",
    target_missing="There's no cactus here.",
)


def _mark_cactus_cut(action):  # set after the award fires
    action.target.set_property("cut_open", True)


def _kill_snake(action):
    camp = action.game.locations["Campsite"]
    snake = camp.items.get("snake")
    if snake is not None:
        camp.remove_item(snake)
    dead = things.Item(
        "snake",
        "a dead rattlesnake",
        "A headless rattlesnake. Them's good eatin' -- and good trade goods.",
    )
    dead.add_command_hint("get snake")
    camp.add_item(dead)
    action.game.snake_dead = True


KillSnakeWithKnife = actions.use_item_on(
    "kill snake with knife",
    item="knife",
    target="snake",
    verb="kill",
    preposition="with",
    description="Hack the rattlesnake apart with your bowie knife",
    aliases=["kill rattlesnake with knife", "stab snake", "use knife on snake"],
    effect=_kill_snake,
    award=(
        "kill_snake",
        10,
        "You hack at the snake and clumsily separate its head from its body. Just "
        "to be safe, you bury the head like a good cowboy. There's now a headless "
        "rattlesnake here.",
    ),
    requires=lambda a: (
        "There's no live snake to kill." if not a.game.snake_out else None
    ),
    item_missing="Your hands shake too much to shoot -- you'll need a blade.",
    target_missing="There's no snake here.",
)


def _hit_black_jack(action):
    g = action.game
    table = g.locations["Black Jack's Table"]
    bj = table.characters.get("black jack")
    if bj is not None:
        table.remove_character(bj)  # his men heave him outside
    g.bj_out = True
    action.character.discard_item(action.item)  # the bottle shatters
    # His bowie knife and the wanted poster clatter onto the table.
    knife = things.Item(
        "knife",
        "Black Jack's bowie knife",
        "A wicked bowie knife, good for carving tables -- and cactus, and snakes.",
    )
    knife.add_command_hint("get knife")
    table.add_item(knife)
    poster = things.Item(
        "map",
        "a wanted poster",
        "Black Jack Baker's scowling face -- but turn it over and the back is a "
        "crude map of the badlands, a line running from town to a drawn cave.",
    )
    poster.add_command_hint("get map")
    poster.add_command_hint("examine map")
    table.add_item(poster)


HitBlackJackWithBottle = actions.use_item_on(
    "hit black jack with bottle",
    item="bottle",
    target="black jack",
    verb="hit",
    preposition="with",
    description="Smash the empty bottle over Black Jack's head",
    aliases=[
        "smash bottle on black jack",
        "hit black jack",
        "use bottle on black jack",
    ],
    effect=_hit_black_jack,
    success=(
        "You smash the bottle over his cranium, knocking him out cold! His bowie "
        "knife clatters onto the table next to the wanted poster. A shotgun blast "
        "rings out as the bartender restores order, and Black Jack's men scatter, "
        "one pausing to heave his boss outside."
    ),
    requires=lambda a: (
        None
        if a.game.bj_enraged and not a.game.bj_out
        else (
            "Black Jack is already out cold."
            if a.game.bj_out
            else "Black Jack is watching you too closely for that."
        )
    ),
    item_missing="You've nothing to swing at him.",
    target_missing="Black Jack isn't here.",
)


def _give_snake_to_doc(action):
    vial = things.Item(
        "snake oil",
        "a vial of Doc Hensley's Fabulous Elixir",
        'A vial labeled "Doc Hensley\'s Fabulous Elixir," otherwise known as snake '
        "oil. For topical use -- a remedy for snakebite and, just maybe, the shakes.",
    )
    vial.add_command_hint("use snake oil on hands")
    action.character.add_to_inventory(vial)


GiveSnakeToDoc = actions.use_item_on(
    "give snake to doc",
    item="snake",
    target="doc",
    verb="give",
    preposition="to",
    description="Trade the dead rattlesnake to Doc Hensley",
    aliases=["give rattlesnake to doc", "give snake to doc hensley", "trade snake"],
    effect=_give_snake_to_doc,
    consume=True,
    success=(
        '"Ah yes, a crucial component for this healing concoction. A fair trade!" '
        "Doc Hensley hands you a vial of his snake oil."
    ),
    item_missing="You've no snake to trade.",
    target_missing="There's no one here to trade with.",
)


def _show_gold_to_mariah(action):
    g = action.game
    if g._badge is not None and not _is_holding(g.player, "badge"):
        g.player.add_to_inventory(g._badge)  # she fishes it from Black Jack's pocket


ShowGoldToMariah = actions.use_item_on(
    "show gold to mariah",
    item="gold",
    target="mariah",
    verb="show",
    preposition="to",
    description="Show Mariah the gold and square your account",
    aliases=["give gold to mariah", "show pouch to mariah", "show gold"],
    effect=_show_gold_to_mariah,
    award=(
        "square",
        5,
        "\"Wasn't sure you'd be back. Even less sure you'd keep your word. Seems "
        "I had you all wrong... sheriff.\" She reaches into Black Jack's pocket and "
        "retrieves your pa's badge, pressing it into your hand.",
    ),
    requires=lambda a: (
        None if a.game.bj_defeated else "There's no time for that just now."
    ),
    item_missing="You've no gold to show her.",
    target_missing="Mariah isn't here.",
)


# ---------------------------------------------------------------------------
# Custom actions
# ---------------------------------------------------------------------------


class _LocAction(actions.Action):
    """Small base for the many single-room verbs: resolves the actor and offers
    a ``require_here`` precondition helper."""

    ROOM = None  # subclasses set the room name this verb belongs to

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def _here(self):
        return self.character.location.name if self.character.location else ""

    def require_here(self, message):
        if self._here() != self.ROOM:
            self.parser.fail(message)
            return False
        return True


# --- Main Street -------------------------------------------------------------


class ExaminePockets(_LocAction):
    ACTION_NAME = "examine pockets"
    ACTION_DESCRIPTION = "Take stock of what's in your pockets"
    ACTION_ALIASES = ["search pockets", "check pockets", "look in pockets"]

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        self.parser.ok(
            "You find your pa's old silver sheriff's badge and a copper penny. "
            "Your hands are shakin' like the devil -- seems a little hair of the "
            "dog is required. Fortunately, you've still got that bottle back home."
        )


# --- Saloon ------------------------------------------------------------------


class OrderDrink(_LocAction):
    ROOM = "Saloon"
    ACTION_NAME = "order drink"
    ACTION_DESCRIPTION = "Order a drink from the bartender"
    ACTION_ALIASES = ["order a drink", "ask for a drink"]

    def check_preconditions(self) -> bool:
        return self.require_here("There's no bar here.")

    def apply_effects(self):
        self.parser.ok(
            "The bartender says, \"Sarsaparilla's one cent, friend.\" He won't "
            "sell anything harder to a drunk like you."
        )


class BuySarsaparilla(_LocAction):
    ROOM = "Saloon"
    ACTION_NAME = "buy sarsaparilla"
    ACTION_DESCRIPTION = "Buy a bottle of sarsaparilla for a penny"
    ACTION_ALIASES = ["order sarsaparilla", "buy a sarsaparilla", "buy drink"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no bar here."):
            return False
        if _is_holding(self.character, "bottle"):
            self.parser.fail("You've already got your sarsaparilla.")
            return False
        if not _is_holding(self.character, "penny"):
            self.parser.fail("You're flat broke -- not even a penny to your name.")
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "penny")
        bottle = things.Item(
            "bottle",
            "a bottle of sarsaparilla",
            "Not the kind of drink you were after...",
        )
        bottle.add_command_hint("drink bottle")
        self.character.add_to_inventory(bottle)
        self.parser.ok(
            "You pay, and the bartender slides the bottle down to you. You now "
            "have a bottle of sarsaparilla."
        )
        self.game.award("sarsaparilla", 5)


class DrinkSarsaparilla(_LocAction):
    ROOM = "Saloon"
    ACTION_NAME = "drink sarsaparilla"
    ACTION_DESCRIPTION = "Down your bottle of sarsaparilla"
    ACTION_ALIASES = ["drink bottle", "drink the bottle", "drink sarsaparilla bottle"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's nothing to drink here."):
            return False
        bottle = _all_held(self.character).get("bottle")
        if bottle is None:
            self.parser.fail("You don't have anything to drink.")
            return False
        if bottle.get_property("is_empty"):
            self.parser.fail("The bottle's already empty.")
            return False
        return True

    def apply_effects(self):
        bottle = _all_held(self.character).get("bottle")
        bottle.set_property("is_empty", True)
        bottle.description = "an empty sarsaparilla bottle"
        self.game.seen_blackjack = True
        self.parser.ok(
            "Mmm... refreshing. The bottle is now empty. \"You'd best be careful. "
            "Black Jack Baker is still mighty sore from when your pa brought the "
            "law down on him and his gang.\" You follow the bartender's gaze to a "
            "table toward the back of the saloon, where Black Jack sits with a "
            "motley crew of desperadoes."
        )


# --- Black Jack's Table ------------------------------------------------------


class WagerBadge(_LocAction):
    ROOM = "Black Jack's Table"
    ACTION_NAME = "wager badge"
    ACTION_DESCRIPTION = "Ante your pa's badge into the poker game"
    ACTION_ALIASES = ["ante badge", "bet badge", "wager my badge"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no game here."):
            return False
        if self.game.has_cards:
            self.parser.fail("You've already anted up. Now play your hand.")
            return False
        if not _is_holding(self.character, "badge"):
            self.parser.fail("You've nothing left worth wagering.")
            return False
        return True

    def apply_effects(self):
        self.game._badge = _take_held(self.character, "badge")
        cards = _fixture(
            "cards",
            "your hand of cards",
            "An ace, a pair of deuces and a pair of fours. Not a bad hand. Black "
            'Jack asks, "So? Fold, draw or call?"',
            self.character.location,
            ["draw", "call"],
        )
        self.game.has_cards = True
        self.parser.ok(
            'Black Jack nods and pockets your badge. He deals the cards. "If you '
            'win, we let you walk away." You now have a hand of cards.'
        )
        self.game.award("ante", 5)


class WagerSomething(_LocAction):
    """Flavor: he won't take your life, pistol or boots (page 174)."""

    ROOM = "Black Jack's Table"
    ACTION_NAME = "wager pistol"
    ACTION_DESCRIPTION = "Try to wager something other than the badge"
    ACTION_ALIASES = [
        "wager life",
        "wager my life",
        "wager boots",
        "bet pistol",
        "bet boots",
        "bet life",
    ]

    def check_preconditions(self) -> bool:
        return self.require_here("There's no game here.")

    def apply_effects(self):
        self.parser.ok(
            "Black Jack shakes his head. Pa's pistol you can't part with, nobody "
            "wants those old boots, and your life? You wagered that when you sat "
            "down. Only the badge will do."
        )


class Draw(_LocAction):
    ROOM = "Black Jack's Table"
    ACTION_NAME = "draw"
    ACTION_DESCRIPTION = "Discard and draw a card"
    ACTION_ALIASES = ["draw card", "draw a card", "draw cards"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no game here."):
            return False
        if not self.game.has_cards:
            self.parser.fail("You haven't anted up yet.")
            return False
        if self.game.bj_enraged:
            self.parser.fail("The time for drawing cards is past.")
            return False
        return True

    def apply_effects(self):
        if self.game.drew_card:
            self.parser.ok("You've already drawn. Time to fold or call.")
            return
        self.game.drew_card = True
        self.parser.ok(
            "You discard a four and draw another deuce... a full house! Now you "
            "just have to call."
        )


class Call(_LocAction):
    ROOM = "Black Jack's Table"
    ACTION_NAME = "call"
    ACTION_DESCRIPTION = "Call Black Jack's hand"
    ACTION_ALIASES = ["bluff", "check", "call hand", "show hand"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no game here."):
            return False
        if not self.game.has_cards:
            self.parser.fail("You haven't anted up yet.")
            return False
        if self.game.bj_enraged:
            self.parser.fail("You've already shown your hand.")
            return False
        return True

    def apply_effects(self):
        self.game.bj_enraged = True
        # Two pair beats his queens (+5); the drawn full house is worth more (+10).
        if self.game.drew_card:
            self.game.award("poker", 10)
        else:
            self.game.award("poker", 5)
        self.parser.ok(
            "You put on your best poker face and call. Black Jack grins. \"Pair o' "
            'ladies," he says, laying down two queens. Then you show your hand -- '
            'and he flies into a rage, snatching up his bowie knife. "You dirty, '
            "snake-in-the-grass, chislin' cheat!\" Better do something, and fast."
        )


class ShootBlackJack(_LocAction):
    """Reaching for your pistol is fatal both at the poker table (page 174) and
    in the noon showdown before the sun's in his eyes (page 190). One action,
    routed by where you're standing."""

    ACTION_NAME = "shoot black jack"
    ACTION_DESCRIPTION = "Reach for your pistol"
    ACTION_ALIASES = ["shoot blackjack", "draw pistol", "fire at black jack"]

    _ROOMS = ("Black Jack's Table", "The Six-Gun Showdown")

    def check_preconditions(self) -> bool:
        if self._here() not in self._ROOMS:
            self.parser.fail("There's no one to shoot here.")
            return False
        return True

    def apply_effects(self):
        if self._here() == "Black Jack's Table":
            self.game.end_in_death(
                "You fumble for your pistol -- too slow! Black Jack is quicker on "
                "the draw and hurls his bowie knife into your chest, killing you "
                "dead. THE END."
            )
        else:
            self.game.end_in_death(
                "Black Jack sees you reach for your pistol and draws. You're fast, "
                "but he's faster. The bullet catches you in the stomach, and you "
                "die in the dirt like a dog. THE END."
            )


class Fold(_LocAction):
    ROOM = "Black Jack's Table"
    ACTION_NAME = "fold"
    ACTION_DESCRIPTION = "Fold your hand"
    ACTION_ALIASES = ["fold hand", "give up"]

    def check_preconditions(self) -> bool:
        return self.require_here("There's no game here.")

    def apply_effects(self):
        self.game.end_in_death(
            "You fold your hand, sighing in despair. Black Jack laughs as his gang "
            "throws you out into the dirt. That old badge was the last thing to "
            "remind you of who you once were. Without it, you're nothin'. THE END."
        )


class StandUp(_LocAction):
    ROOM = "Black Jack's Table"
    ACTION_NAME = "stand up"
    ACTION_DESCRIPTION = "Stand up and head back to Main Street"
    ACTION_ALIASES = ["stand", "get up", "leave table"]

    def check_preconditions(self) -> bool:
        if not self.require_here("You're not seated anywhere."):
            return False
        if not self.game.bj_out:
            self.parser.fail(
                "One of Black Jack's men insists you finish the hand. He pats his "
                "sidearm."
            )
            return False
        return True

    def apply_effects(self):
        self.parser.ok("You head back outside to Main Street.")
        self.game.relocate(self.character, self.game.locations["Main Street"])
        self.parser.ok(self.game.describe())


# --- General Store -----------------------------------------------------------


class SealDeal(_LocAction):
    ROOM = "General Store"
    ACTION_NAME = "seal the deal"
    ACTION_DESCRIPTION = "Shake on Mariah's grubstake offer"
    ACTION_ALIASES = ["seal deal", "shake hand", "shake hands", "say yes"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no deal to be had here."):
            return False
        if _is_holding(self.character, "rucksack"):
            self.parser.fail("You've already got your supplies.")
            return False
        if not self.character.get_property("mariah_offered"):
            self.parser.fail("Mariah hasn't offered you anything. Show her the map.")
            return False
        return True

    def apply_effects(self):
        rucksack = _build_rucksack()
        self.character.add_to_inventory(rucksack)
        self.parser.ok(
            'Mariah spits in her hand and you shake on it. "Deal!" She hands you a '
            "rucksack of much-needed supplies: a flint and steel, a bedroll, a tin "
            "of beans and a full canteen."
        )
        self.game.award("supplies", 5)


class RefuseDeal(_LocAction):
    ROOM = "General Store"
    ACTION_NAME = "refuse the deal"
    ACTION_DESCRIPTION = "Turn down Mariah's offer"
    ACTION_ALIASES = ["refuse deal", "say no"]

    def check_preconditions(self) -> bool:
        return self.require_here("There's no deal to be had here.")

    def apply_effects(self):
        self.parser.ok(
            "Mariah shrugs. \"Suit yourself. But you won't last an hour out there "
            'without supplies." The offer still stands if you change your mind.'
        )


# --- The desert: water, camp, cave ------------------------------------------


class DrinkWater(_LocAction):
    ACTION_NAME = "drink water"
    ACTION_DESCRIPTION = "Drink sparingly from your canteen"
    ACTION_ALIASES = ["drink from canteen", "drink canteen", "sip water", "drink"]

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "canteen"):
            self.parser.fail("You've no canteen to drink from.")
            return False
        return True

    def apply_effects(self):
        g = self.game
        here = self._here()
        # Only the desert's dry stretches actually draw down (and clear) the
        # thirst prompt; sipping in town is harmless flavor.
        if here in g.DRINK_ROOMS and g._pending_drink == here:
            if g.water_rations <= 0:
                self.parser.ok("You tip the canteen back, but it's bone dry.")
                return
            g.water_rations -= 1
            g._drunk_at.add(here)
            g._pending_drink = None
            if g.water_rations <= 0:
                self.parser.ok("You drink the last of it. And... now it's gone.")
            else:
                self.parser.ok("You drink sparingly, trying to save some for later.")
        else:
            self.parser.ok("You take a small sip from the canteen.")


class TakeTinder(_LocAction):
    ROOM = "Desert (Creosote Bushes)"
    ACTION_NAME = "take tinder"
    ACTION_DESCRIPTION = "Collect dry creosote brush for tinder"
    ACTION_ALIASES = ["get tinder", "take brush", "get brush", "gather tinder"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's nothing like that here."):
            return False
        if _is_holding(self.character, "tinder"):
            self.parser.fail("You've already gathered plenty of tinder.")
            return False
        return True

    def apply_effects(self):
        tinder = things.Item(
            "tinder",
            "a bundle of dry creosote",
            "Dry-as-a-bone creosote brush -- " "perfect tinder for building a fire.",
        )
        tinder.add_command_hint("build fire")
        self.character.add_to_inventory(tinder)
        self.parser.ok(
            "It's a simple matter to collect tinder from the dry creosote bushes."
        )


class TakeFirewood(_LocAction):
    ROOM = "Desert (Pine Tree)"
    ACTION_NAME = "take firewood"
    ACTION_DESCRIPTION = "Break off pine branches for firewood"
    ACTION_ALIASES = [
        "get firewood",
        "take branches",
        "get branches",
        "gather firewood",
    ]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no firewood here."):
            return False
        if _is_holding(self.character, "firewood"):
            self.parser.fail("You've already got enough firewood.")
            return False
        return True

    def apply_effects(self):
        wood = things.Item(
            "firewood",
            "an armful of pine branches",
            "The pine's lower branches " "make good firewood.",
        )
        wood.add_command_hint("build fire")
        self.character.add_to_inventory(wood)
        self.parser.ok("You break off some branches for firewood.")


class MakeCamp(_LocAction):
    ROOM = "Desert (Pine Tree)"
    ACTION_NAME = "make camp"
    ACTION_DESCRIPTION = "Make camp for the night under the pine"
    ACTION_ALIASES = ["set up camp", "camp", "make a camp"]

    def check_preconditions(self) -> bool:
        if not self.require_here("This is no place to make camp."):
            return False
        if self.game.camp_complete:
            self.parser.fail("You've already camped here. Best move on.")
            return False
        return True

    def apply_effects(self):
        g = self.game
        camp = g.locations["Campsite"]
        camp.description = (
            "You hunker down for the night. You're hungry, cold, tired and, darn "
            "it, your feet hurt. You'll want to build a fire, cook those beans and "
            "get some sleep."
        )
        # Reset the night's state machine in case of a replay.
        for flag in (
            "fire_built",
            "fire_lit",
            "beans_cooked",
            "beans_eaten",
            "camp_morning",
            "snake_seen",
            "snake_out",
            "snake_dead",
            "boots_back_on",
        ):
            setattr(g, flag, False)
        g.relocate(self.character, camp)
        self.parser.ok(camp.description)


class BuildFire(_LocAction):
    ROOM = "Campsite"
    ACTION_NAME = "build fire"
    ACTION_DESCRIPTION = "Lay a fire from tinder and firewood"
    ACTION_ALIASES = ["build a fire", "make fire", "lay fire"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no place for a fire here."):
            return False
        if self.game.camp_morning:
            self.parser.fail("Your fire's burned down to embers. It's morning now.")
            return False
        if self.game.fire_built:
            self.parser.fail("You've already laid the fire.")
            return False
        if not (
            _is_holding(self.character, "tinder")
            and _is_holding(self.character, "firewood")
        ):
            self.parser.fail(
                "You'll need tinder and firewood to start a fire. (The map can't "
                "be used -- you need it to find Parson's claim.)"
            )
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "tinder")
        _take_held(self.character, "firewood")
        self.game.fire_built = True
        self.parser.ok(
            "You build a small nest of creosote and lay the pine branches over it."
        )


class UseFlintAndSteel(_LocAction):
    ROOM = "Campsite"
    ACTION_NAME = "use flint and steel"
    ACTION_DESCRIPTION = "Strike the flint and steel to light your fire"
    ACTION_ALIASES = ["light fire", "strike flint", "use flint", "light the fire"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's nothing to light here."):
            return False
        if not self.game.fire_built:
            self.parser.fail("Build the fire first.")
            return False
        if self.game.fire_lit:
            self.parser.fail("The fire's already going.")
            return False
        if not _is_holding(self.character, "flint and steel"):
            self.parser.fail("You don't have a flint and steel.")
            return False
        return True

    def apply_effects(self):
        self.game.fire_lit = True
        self.parser.ok(
            "Your hands shake so much it takes several tries, but you get a fire "
            "going. After a while, you no longer feel cold."
        )


class CookBeans(_LocAction):
    ROOM = "Campsite"
    ACTION_NAME = "cook beans"
    ACTION_DESCRIPTION = "Cook your tin of beans over the fire"
    ACTION_ALIASES = ["cook the beans", "heat beans", "cook beans over fire"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no fire here to cook on."):
            return False
        if not self.game.fire_lit:
            self.parser.fail("You'll need a lit fire to cook on.")
            return False
        if not _is_holding(self.character, "beans"):
            self.parser.fail("You've no beans to cook.")
            return False
        if self.game.beans_cooked:
            self.parser.fail("The beans are already cooked.")
            return False
        return True

    def apply_effects(self):
        self.game.beans_cooked = True
        self.parser.ok("Mmm, mmm. Smells like heaven.")


class EatBeans(_LocAction):
    ROOM = "Campsite"
    ACTION_NAME = "eat beans"
    ACTION_DESCRIPTION = "Eat your cooked beans"
    ACTION_ALIASES = ["eat the beans", "eat beans now"]

    def check_preconditions(self) -> bool:
        if not self.require_here("You've no beans here."):
            return False
        if not _is_holding(self.character, "beans"):
            self.parser.fail("You've no beans to eat.")
            return False
        if not self.game.beans_cooked:
            self.parser.fail("Best cook those beans first.")
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "beans")
        self.game.beans_eaten = True
        self.parser.ok(
            "You no longer feel hungry. Maybe it's time to get some shut-eye."
        )


class Sleep(_LocAction):
    ROOM = "Campsite"
    ACTION_NAME = "sleep"
    ACTION_DESCRIPTION = "Bed down for the night"
    ACTION_ALIASES = ["go to sleep", "rest", "lie down"]

    def check_preconditions(self) -> bool:
        return self.require_here("This is no place to sleep.")

    def apply_effects(self):
        g = self.game
        if g.camp_morning:
            self.parser.ok("You're up with the sun. No more sleeping.")
            return
        if not g.beans_eaten:
            self.parser.ok("Your stomach's growling too loud to sleep. Eat first.")
            return
        if "boots" in self.character.worn:
            self.parser.ok(
                "Aw, heck. Your feet hurt from walking all day, and you just can't "
                "get settled. Maybe TAKE OFF BOOTS."
            )
            return
        # A full night passes.
        g.camp_morning = True
        camp = g.locations["Campsite"]
        camp.description = (
            "Your eyes blink open to the sun rising in the distance. Looks like "
            "you can get a head start and beat the heat. You'd best put your boots "
            "back on before you BREAK CAMP -- that desert sand gets mighty hot."
        )
        self.parser.ok(
            "You stretch out on your bedroll and fall into an uneasy sleep.\n\n"
            + camp.description
        )


class ExamineBoots(_LocAction):
    ROOM = "Campsite"
    ACTION_NAME = "examine boots"
    ACTION_DESCRIPTION = "Check your boots before putting them on"
    ACTION_ALIASES = [
        "examine boot",
        "check boots",
        "check boot",
        "look in boots",
        "x boots",
    ]

    def check_preconditions(self) -> bool:
        return self.require_here("You're not at camp.")

    def apply_effects(self):
        g = self.game
        if not g.camp_morning:
            self.parser.ok("A worn but trusty pair of leather boots.")
            return
        if g.snake_dead:
            self.parser.ok("Just your boots now. Safe to wear.")
            return
        g.snake_seen = True
        self.parser.ok(
            "You peer inside and see a sleeping rattlesnake coiled up in your left "
            "boot! Good thing you looked. Best SHAKE BOOT to get it out."
        )
        self.game.award("check_boot", 5)


class ShakeBoot(_LocAction):
    ROOM = "Campsite"
    ACTION_NAME = "shake boot"
    ACTION_DESCRIPTION = "Shake the snake out of your boot"
    ACTION_ALIASES = ["shake boots", "shake out boot", "empty boot"]

    def check_preconditions(self) -> bool:
        if not self.require_here("You're not at camp."):
            return False
        if not self.game.camp_morning:
            self.parser.fail("There's nothing in your boots right now.")
            return False
        if not self.game.snake_seen:
            self.parser.fail("Best look in your boots first.")
            return False
        if self.game.snake_dead or self.game.snake_out:
            self.parser.fail("The snake's already out.")
            return False
        return True

    def apply_effects(self):
        g = self.game
        g.snake_out = True
        snake = _fixture(
            "snake",
            "a coiled rattlesnake",
            "A mean-looking rattlesnake, coiled and hissing, its tail rattling.",
            self.character.location,
            ["kill snake with knife"],
        )
        self.parser.ok(
            "A mean-looking rattlesnake falls out, and you drop the boot in "
            "surprise. The varmint coils up, hisses and rattles its tail."
        )


class ShootSnake(_LocAction):
    ROOM = "Campsite"
    ACTION_NAME = "shoot snake"
    ACTION_DESCRIPTION = "Try to shoot the rattlesnake"
    ACTION_ALIASES = ["shoot rattlesnake", "shoot the snake"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no snake here."):
            return False
        if not self.game.snake_out:
            self.parser.fail("There's no snake to shoot.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "Your hands are shaking too much to get off a clean shot! You'll have "
            "to use the knife."
        )


class WearBoots(_LocAction):
    ACTION_NAME = "wear boots"
    ACTION_DESCRIPTION = "Put your boots back on"
    ACTION_ALIASES = ["put on boots", "put boots on", "wear boot"]

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        g = self.game
        if "boots" in self.character.worn:
            self.parser.ok("You're already wearing your boots.")
            return
        boots = self.character.inventory.get("boots")
        # The lethal version: pulling them on with the snake still inside.
        if self._here() == "Campsite" and g.camp_morning and not g.snake_dead:
            g.end_in_death(
                "You fail to notice the rattlesnake sleeping in your boot. Its "
                "fangs sink into your foot, and after a few painful hours, you die. "
                "THE END."
            )
            return
        if boots is None:
            self.parser.fail("You don't have your boots.")
            return
        self.character.wear(boots)
        if self._here() == "Campsite":
            g.boots_back_on = True
            self.parser.ok("You slip on your boots. Time to break camp and mosey on.")
        else:
            self.parser.ok("You pull on your boots.")


class BreakCamp(_LocAction):
    ROOM = "Campsite"
    ACTION_NAME = "break camp"
    ACTION_DESCRIPTION = "Pack up camp and move on"
    ACTION_ALIASES = ["leave camp", "pack up camp", "pack up"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no camp to break here."):
            return False
        if not self.game.camp_morning:
            self.parser.fail("It's the middle of the night. Get some sleep first.")
            return False
        if not self.game.boots_back_on:
            self.parser.fail(
                "You best put your boots on first. That desert sand gets mighty hot."
            )
            return False
        return True

    def apply_effects(self):
        g = self.game
        g.camp_complete = True
        pine = g.locations["Desert (Pine Tree)"]
        self.parser.ok(
            "You pack up your gear and kick some sand over the embers of your fire."
        )
        g.relocate(self.character, pine)
        self.parser.ok(g.describe())


# --- Dark Cave ---------------------------------------------------------------


class BurnMap(_LocAction):
    ROOM = "Dark Cave"
    ACTION_NAME = "burn map"
    ACTION_DESCRIPTION = "Set the map alight as a makeshift torch"
    ACTION_ALIASES = ["light map", "burn the map", "light fire", "make torch"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's nothing to burn here."):
            return False
        if self.character.location.get_property("cave_lit"):
            self.parser.fail("Your torch is already burning.")
            return False
        if not (
            _is_holding(self.character, "map")
            and _is_holding(self.character, "flint and steel")
        ):
            self.parser.fail(
                "It's pitch dark. You'd need the map and your flint and steel to "
                "make a light -- and they're no good to you in the rucksack outside."
            )
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "map")
        self.character.location.set_property("cave_lit", True)
        self.parser.ok(
            "You spark flint and steel and set the map ablaze, turning it into a "
            "makeshift torch. The light illuminates the cave."
        )


class SearchCave(_LocAction):
    ROOM = "Dark Cave"
    ACTION_NAME = "search cave"
    ACTION_DESCRIPTION = "Search the cave floor"
    ACTION_ALIASES = ["search", "search the cave", "look around cave"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no cave to search here."):
            return False
        if not self.character.location.get_property("cave_lit"):
            self.parser.fail("It's too dark to see more than a few feet.")
            return False
        return True

    def apply_effects(self):
        self.character.location.set_property("mound_found", True)
        self.parser.ok(
            "The floor is mostly sand blown in from the desert. You belly-crawl "
            "toward the back and spy a mound of dirt and sand near the far wall."
        )


class Dig(_LocAction):
    ROOM = "Dark Cave"
    ACTION_NAME = "dig"
    ACTION_DESCRIPTION = "Dig into the mound"
    ACTION_ALIASES = ["dig mound", "dig in sand", "dig sand"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's nothing to dig here."):
            return False
        loc = self.character.location
        if not loc.get_property("cave_lit"):
            self.parser.fail("It's too dark to find anything.")
            return False
        if not loc.get_property("mound_found"):
            self.parser.fail("You'll have to find something worth digging at first.")
            return False
        if _is_holding(self.character, "gold"):
            self.parser.fail("You've already dug up the gold.")
            return False
        return True

    def apply_effects(self):
        loc = self.character.location
        gold = things.Item(
            "gold",
            "a pouch of gold nuggets",
            "A small leather pouch holding a small fortune in gold nuggets. "
            "You're rich!",
        )
        gold.add_command_hint("show gold to mariah")
        self.character.add_to_inventory(gold)
        loc.set_property("cave_lit", False)  # your torch dies
        self.parser.ok(
            "You drop the torch and burrow into the sand like a prairie dog, "
            "digging up a small leather pouch! Then your fire dies, leaving you in "
            "darkness. Best feel your way back out into the daylight."
        )
        self.game.award("gold", 10)


# --- Doc Hensley's Wagon -----------------------------------------------------


class UseSnakeOilOnHands(_LocAction):
    ACTION_NAME = "use snake oil on hands"
    ACTION_DESCRIPTION = "Rub the snake oil into your shaking hands"
    ACTION_ALIASES = [
        "rub snake oil on hands",
        "apply snake oil",
        "use snake oil",
        "rub snake oil on my hands",
    ]

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "snake oil"):
            self.parser.fail("You don't have any snake oil.")
            return False
        if not self.character.get_property("hands_shaky"):
            self.parser.fail("Your hands are already steady as a rock.")
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "snake oil")
        self.character.set_property("hands_shaky", False)
        self.parser.ok(
            "You rub the elixir into your skin. The oily substance smells foul, "
            "but it makes your hands tingle with warmth. Your stiff fingers relax "
            "and your tremors fade away!"
        )
        self.game.award("cure", 5)


# --- Main Street Clock Tower -------------------------------------------------


class DuelBlackJack(_LocAction):
    ROOM = "Main Street Clock Tower"
    ACTION_NAME = "duel black jack"
    ACTION_DESCRIPTION = "Challenge Black Jack to a duel"
    ACTION_ALIASES = [
        "challenge black jack",
        "talk to black jack",
        "duel blackjack",
        "challenge blackjack",
        "fight black jack",
    ]

    def check_preconditions(self) -> bool:
        if not self.require_here("Black Jack isn't here."):
            return False
        if self.character.get_property("hands_shaky"):
            self.parser.fail(
                "With your hands shaking like this, you wouldn't stand a chance. "
                "You need to steady them first."
            )
            return False
        return True

    def apply_effects(self):
        g = self.game
        showdown = g.locations["The Six-Gun Showdown"]
        bj = self.character.location.characters.get("black jack")
        self.parser.ok(
            '"Think you\'re faster than me? Not a chance." A crowd gathers. Mariah '
            "watches from her shop window. Behind you, the clock's hands creep "
            "toward noon as the sun rises in the sky."
        )
        if bj is not None:
            self.character.location.remove_character(bj)
            showdown.add_character(bj)
        g.relocate(self.character, showdown)
        self.parser.ok(
            "You and Black Jack stand on Main Street, staring each other down. "
            "It's a waiting game now; whoever fires first is going to lose -- "
            "you're fast, but he's faster. Best WAIT for your moment."
        )


# --- The Six-Gun Showdown ----------------------------------------------------


class DrawAndFire(_LocAction):
    ROOM = "The Six-Gun Showdown"
    ACTION_NAME = "draw and fire"
    ACTION_DESCRIPTION = "Draw steel and fire while the sun blinds him"
    ACTION_ALIASES = ["draw steel", "draw and shoot", "fire", "quickdraw"]

    def check_preconditions(self) -> bool:
        if not self.require_here("There's no duel here."):
            return False
        if not self.game.sun_ready:
            return True  # premature -- resolved as a death below
        return True

    def apply_effects(self):
        g = self.game
        if not g.sun_ready:
            g.end_in_death(
                "You draw too early. Black Jack matches you and his bullet finds "
                "your chest. You die in the dirt like a dog. THE END."
            )
            return
        g.bj_defeated = True
        showdown = self.character.location
        bj = showdown.characters.get("black jack")
        if bj is not None:
            showdown.remove_character(bj)
        # Mariah runs out from her shop to greet the new sheriff.
        mariah = g.characters.get("mariah")
        if mariah is not None and mariah.location is not showdown:
            g.relocate(mariah, showdown)
        self.parser.ok(
            "With lightning speed, you draw steel and fire while the sun's in "
            "Black Jack's eyes. He grunts in surprise and keels over, dead as a "
            "doornail. His men make themselves scarce, and the crowd erupts in "
            "cheers! Mariah runs out from her shop to greet you."
        )
        g.award("defeat", 10)


class WearBadge(_LocAction):
    ACTION_NAME = "wear badge"
    ACTION_DESCRIPTION = "Pin your pa's badge on your chest"
    ACTION_ALIASES = ["put on badge", "pin badge", "pin on badge", "wear my badge"]

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "badge"):
            self.parser.fail("You don't have the badge.")
            return False
        if self.character.get_property("hands_shaky"):
            self.parser.fail(
                "The tremor in your hands makes even this simple task impossible."
            )
            return False
        return True

    def apply_effects(self):
        g = self.game
        if not g.bj_defeated:
            # Steady hands but the showdown's not yet won: just pin it on.
            badge = _take_held(self.character, "badge")
            self.character.worn[badge.name] = badge
            self.parser.ok("You pin the badge on your chest.")
            return
        badge = _take_held(self.character, "badge")
        self.character.worn[badge.name] = badge
        self.character.set_property("is_sheriff", True)
        self.game.award("sheriff", 10)
        # is_won() narrates the ending and the final score.


# ---------------------------------------------------------------------------
# Rucksack of supplies (Mariah's grubstake)
# ---------------------------------------------------------------------------


def _build_rucksack():
    rucksack = things.Item(
        "rucksack",
        "a rucksack of supplies",
        "A canvas rucksack holding a flint "
        "and steel, a bedroll, a tin of beans and a full canteen.",
    )
    rucksack.make_container()  # open, so its contents are reachable one level deep
    for item in (
        things.Item("flint and steel", "a flint and steel", "For striking a spark."),
        things.Item(
            "bedroll", "a bedroll", "A roll of blankets for the cold desert night."
        ),
        things.Item("beans", "a tin of beans", "A tin of beans. Cowboy caviar."),
        things.Item(
            "canteen",
            "a canteen of water",
            "A canteen -- your lifeline in the badlands.",
        ),
    ):
        rucksack.add_item(item)
    rucksack.add_command_hint("drop rucksack")
    return rucksack


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> SixGunShowdown:
    L = things.Location

    main_street = L(
        "Main Street",
        "You're fresh out of the drunk tank, down to a pair of worn leather boots "
        "and whatever's left in your pockets. The saloon is to the north and "
        "Cooper's general store is to the east. Your shack is to the west. A road "
        "leads south to the edge of town.",
    )
    shack = L(
        "Rundown Shack",
        "Home sweet home. Pa's pistol and holster hang on a hook here. There's a "
        "broken whiskey bottle on the floor. The way out is east, back to Main "
        "Street.",
    )
    saloon = L(
        "Saloon",
        "You belly up to the bar. The bartender gives you a polite nod and keeps "
        'polishing a shot glass. "What\'ll it be?" The way out is back to Main '
        "Street.",
    )
    table = L(
        "Black Jack's Table",
        "A ragged poker table toward the back of the saloon, ringed by Black "
        "Jack's desperadoes.",
    )
    store = L(
        "General Store",
        'Mariah Cooper, the proprietress, takes one look at you and frowns. "The '
        'usual? A bottle of whiskey and a can of beans?" Various supplies and '
        "sundries line the shelves. The way out leads back to Main Street.",
    )
    outskirts = L(
        "Outskirts of Town",
        "You head out on foot, the sun beating down on your hatless head. The "
        "badlands stretch out to the south. Town is back to the north.",
    )
    desert = L(
        "Desert",
        "All the critters are sleeping underground to keep out of the sun, and "
        "here you are wandering the desert like a darn fool. The map says go west. "
        "Town lies back to the north.",
    )
    creosote = L(
        "Desert (Creosote Bushes)",
        "Miles into the desert, you're heartened to see a cluster of creosote "
        "bushes, just as the map promised. The map says head south next. Back east "
        "is the open desert.",
    )
    cactus = L(
        "Desert (Lonely Cactus)",
        "A lonely cactus stands here, two arms jutting from its sides. The map "
        "shows a river to the east. The creosote bushes are back to the north.",
    )
    arroyo = L(
        "Desert (Arroyo)",
        "You meander down a bone-dry arroyo, alert for flash floods. The map says "
        "keep south to a pine tree. The cactus is back to the west.",
    )
    pine = L(
        "Desert (Pine Tree)",
        "A gnarled bristlecone pine stands here -- a good place to make camp as "
        "the sun goes down and the desert turns cold. The map shows a cow skull to "
        "the east. The arroyo is back to the north.",
    )
    campsite = L(
        "Campsite",
        "A sheltered spot beneath the pine.",
    )
    cow_skull = L(
        "Desert (Cow Skull)",
        "A cow skull lies half-buried in the sand, your footprints trailing back "
        "to the west. Your mouth is awful dry. The map says keep north to a rocky "
        "bluff -- X marks the spot.",
    )
    bluff = L(
        "Rocky Bluff",
        "You reach the rocky bluff from the map -- Parson's claim! There's a small "
        "cave entrance low to the ground here. The desert is back to the south.",
    )
    cave = L(
        "Dark Cave",
        "The sunlight barely reaches inside the cramped cave. You can't see more "
        "than a few feet in front of you. The way out is behind you.",
    )
    wagon = L(
        "Doc Hensley's Wagon",
        "You ride along beside Doc Hensley for a few hours, making small talk. He "
        "agrees to carry you back to town. A clapboard sign reads \"Doc Hensley's "
        'Fabulous Elixir." An open crate of supplies sits among his goods.',
    )
    clock_tower = L(
        "Main Street Clock Tower",
        "Doc drops you at the edge of town and you hike back to Main Street, where "
        "Black Jack Baker and his gang wait under the old clock tower. Scatterguns "
        "and rifles bulge under their dusters. There's no running from this -- if "
        "you won't fight, they'll cut you down where you stand.",
    )
    showdown = L(
        "The Six-Gun Showdown",
        "You and Black Jack face each other down the length of Main Street, hands "
        "hovering over your pistols. The clock creeps toward noon.",
    )

    # --- Connections -------------------------------------------------------
    # Main Street is a hub whose four spokes each return via "out" (or, for the
    # outskirts, "north"). add_connection()'s auto-reverse would make every
    # "out" collide on Main Street's "in", so we wire every edge one-way by hand
    # and give Main Street its four forward exits explicitly. The result: each
    # room has exactly one exit to each neighbor (no duplicate destinations).
    _one_way(main_street, "north", saloon)
    _one_way(main_street, "east", store)
    _one_way(main_street, "west", shack)
    _one_way(main_street, "south", outskirts)
    _one_way(saloon, "out", main_street)
    _one_way(store, "out", main_street)
    _one_way(shack, "out", main_street)
    _one_way(table, "out", main_street)  # FOLD/STAND fall back here too

    _one_way(outskirts, "north", main_street)
    _one_way(outskirts, "south", desert)
    _one_way(desert, "north", outskirts)
    _one_way(desert, "west", creosote)
    _one_way(creosote, "east", desert)
    _one_way(creosote, "south", cactus)
    _one_way(cactus, "north", creosote)
    _one_way(cactus, "east", arroyo)
    _one_way(arroyo, "west", cactus)
    _one_way(arroyo, "south", pine)
    _one_way(pine, "north", arroyo)
    _one_way(pine, "east", cow_skull)
    _one_way(cow_skull, "west", pine)
    _one_way(cow_skull, "north", bluff)
    _one_way(bluff, "south", cow_skull)
    _one_way(bluff, "enter cave", cave)
    _one_way(cave, "out", bluff)
    _one_way(bluff, "north", wagon)
    _one_way(wagon, "back to town", clock_tower)
    # clock_tower -> showdown is handled by the DuelBlackJack action (relocate).

    # --- Items -------------------------------------------------------------
    # Main Street / pockets: the player starts with these (added below).
    _fixture(
        "pockets",
        "your pockets",
        "Best EXAMINE POCKETS to take stock.",
        main_street,
        ["examine pockets"],
    )

    # Shack: pa's pistol (wearable) and the broken bottle (scenery).
    pistol = things.Item(
        "pistol",
        "pa's pistol and holster",
        "As fine a piece of steel as there ever was. You check the cylinder -- "
        "still loaded, for old times' sake. But your gunslinger days are behind you.",
    )
    pistol.set_property("wearable", True)
    pistol.set_property("wear_slot", "hip")
    pistol.set_property(
        "wear_text",
        "You sling the pistol onto your hip. The belt buckle is tricky, what with "
        "your hands shaking, but you manage.",
    )
    pistol.add_command_hint("wear pistol")
    shack.add_item(pistol)
    _fixture(
        "whiskey bottle",
        "a broken whiskey bottle",
        "Yep, that might explain last night's sleeping arrangements.",
        shack,
        ["examine whiskey bottle"],
    )

    # Saloon scenery: the back table.
    _fixture(
        "table",
        "the desperadoes' table",
        "Black Jack sits there with a motley crew of desperadoes. A wanted poster "
        "is laid out across the table.",
        saloon,
        ["examine table", "examine black jack"],
    )

    # Lonely cactus (scenery you cut for water).
    _fixture(
        "cactus",
        "a lonely cactus",
        "A barrel cactus, two arms jutting from its sides. Cut into it and you "
        "might catch some water.",
        cactus,
        ["cut cactus"],
    )

    # Pine / creosote scenery hints.
    _fixture(
        "bushes",
        "the creosote bushes",
        "The dry, scraggly brush would make good tinder for a fire.",
        creosote,
        ["take tinder"],
    )
    _fixture(
        "tree",
        "the bristlecone pine",
        "The lower branches would make good firewood.",
        pine,
        ["take firewood"],
    )

    # Rocky Bluff cave-entrance scenery.
    _fixture(
        "cave entrance",
        "a small cave entrance",
        "The crevice is small and low. It'll be a tight squeeze -- you'll have to "
        "drop your rucksack and crawl in on your hands and knees.",
        bluff,
        ["drop rucksack", "enter cave"],
    )

    # Doc's wagon crate (scenery / flavor).
    _fixture(
        "crate",
        "an open crate of vials",
        "Eight compartments, each holding a glass vial of Doc Hensley's snake oil "
        '-- "a remedy for all manner of ailments, from gout to snakebite."',
        wagon,
        ["examine crate"],
    )

    # --- Characters --------------------------------------------------------
    player = things.Character(
        "you",
        "a washed-up sheriff's son with shaking hands",
        "I aim to get my pa's badge back and run Black Jack Baker out of town.",
    )
    badge = things.Item(
        "badge",
        "pa's silver sheriff's badge",
        "Your pa's badge. He kept the peace in this town until a cattle rustler "
        "shot him in the back. You still remember the day.",
    )
    badge.set_property("wearable", True)
    badge.add_command_hint("wear badge")
    penny = things.Item(
        "penny",
        "a copper penny",
        "Quite literally your last cent.",
    )
    boots = things.Item("boots", "a pair of worn leather boots", "Worn but trusty.")
    boots.set_property("wearable", True)
    boots.set_property("wear_slot", "feet")
    player.add_to_inventory(badge)
    player.add_to_inventory(penny)
    player.add_to_inventory(boots)
    player.wear(boots)

    bartender = things.Character(
        "bartender", "the saloon bartender", "I keep the peace in my bar."
    )
    bartender.examine_text = "A polite man in shirtsleeves, polishing a glass."
    bartender.talk_text = '"You\'d best be careful around Black Jack Baker, friend."'
    saloon.add_character(bartender)

    black_jack = things.Character(
        "black jack", "Black Jack Baker, an outlaw", "I run this town now."
    )
    black_jack.examine_text = (
        "Black Jack is idly carving the tabletop with his trusty bowie knife. As "
        "his eyes meet yours, he stands up."
    )
    black_jack.talk_text = '"Sit down and play a hand, for old times\' sake."'
    saloon.add_character(black_jack)  # revealed by the bartender's warning

    mariah = things.Character(
        "mariah",
        "Mariah Cooper, the shopkeeper",
        "I run a fair store and I keep my word.",
    )
    mariah.examine_text = "A winsome woman in a shopkeeper's apron."
    mariah.talk_text = '"Wind up your tab and we\'ll talk."'
    store.add_character(mariah)

    doc = things.Character(
        "doc",
        "Doc Hensley, a traveling snake-oil salesman",
        "The healing arts are my stock-in-trade.",
    )
    doc.examine_text = "An elderly dude in a suit, tie and bowler hat."
    doc.talk_text = (
        "\"Doc Hensley's the name, and the healing arts are my stock-in-trade. You "
        'look like you could use some assistance. Climb aboard!"'
    )
    wagon.add_character(doc)

    # --- Assemble ----------------------------------------------------------
    custom_actions = [
        ExaminePockets,
        OrderDrink,
        BuySarsaparilla,
        DrinkSarsaparilla,
        WagerBadge,
        WagerSomething,
        Draw,
        Call,
        HitBlackJackWithBottle,
        ShootBlackJack,
        Fold,
        StandUp,
        ShowMapToMariah,
        SealDeal,
        RefuseDeal,
        DrinkWater,
        TakeTinder,
        TakeFirewood,
        CutCactus,
        MakeCamp,
        BuildFire,
        UseFlintAndSteel,
        CookBeans,
        EatBeans,
        Sleep,
        ExamineBoots,
        ShakeBoot,
        ShootSnake,
        KillSnakeWithKnife,
        WearBoots,
        BreakCamp,
        BurnMap,
        SearchCave,
        Dig,
        GiveSnakeToDoc,
        UseSnakeOilOnHands,
        DuelBlackJack,
        DrawAndFire,
        ShowGoldToMariah,
        WearBadge,
    ]
    characters = [bartender, black_jack, mariah, doc]
    game = SixGunShowdown(main_street, player, characters, custom_actions)

    # Register every room by name; several hang off named one-way exits and the
    # set-piece relocations (poker, camp, duel) look rooms up by name.
    for loc in (
        main_street,
        shack,
        saloon,
        table,
        store,
        outskirts,
        desert,
        creosote,
        cactus,
        arroyo,
        pine,
        campsite,
        cow_skull,
        bluff,
        cave,
        wagon,
        clock_tower,
        showdown,
    ):
        game.locations.setdefault(loc.name, loc)

    # --- Gates -------------------------------------------------------------
    # Can't enter the badlands without food, water and fire (page 177).
    outskirts.add_block(
        "south",
        CondBlock(
            "No supplies",
            "Gonna venture into the badlands without food, water or fire? Where'd "
            "you grow up, New York City? Best get a rucksack of supplies from "
            "Mariah first.",
            lambda: not _is_holding(player, "rucksack"),
        ),
    )
    # Must MAKE CAMP before pushing east past the pine (page 181).
    pine.add_block(
        "east",
        CondBlock(
            "Must camp",
            "The sun's going down and it's getting cold. You'd best MAKE CAMP "
            "before pressing on.",
            lambda: not game.camp_complete,
        ),
    )
    # The cave's a tight squeeze: drop the rucksack to crawl in (page 185).
    bluff.add_block(
        "enter cave",
        CondBlock(
            "Tight squeeze",
            "It's a tight squeeze. You'll have to DROP your rucksack to crawl in "
            "on your hands and knees.",
            lambda: _is_holding(player, "rucksack"),
        ),
    )
    # Nothing draws you north until you've struck it rich and spot Doc's dust.
    bluff.add_block(
        "north",
        CondBlock(
            "Nothing yet",
            "Nothing but empty desert to the north -- no reason to head that way "
            "yet.",
            lambda: not _is_holding(player, "gold"),
        ),
    )
    # Can't ride to town until Doc's given you the elixir -- and once you have
    # it, used or not, the trip's on (page 188 -> 189). So the gate opens the
    # moment your hands are cured OR you're still carrying the unused vial.
    wagon.add_block(
        "back to town",
        CondBlock(
            "No elixir yet",
            "Doc won't drive on until you've settled your business -- trade him "
            "the snake and get that elixir.",
            lambda: player.get_property("hands_shaky")
            and not _is_holding(player, "snake oil"),
        ),
    )

    # --- Triggers (idempotent, phrasing-independent scoring) ---------------
    # +5 the moment pa's pistol is strapped on (page 190).
    game.add_trigger(
        "score_pistol",
        lambda g: "pistol" in g.player.worn,
        lambda g: g.award("pistol", 5),
        repeatable=True,
    )
    # +5 for lifting the treasure map off the table (page 190).
    game.add_trigger(
        "score_map",
        lambda g: _is_holding(g.player, "map"),
        lambda g: g.award("find_map", 5),
        repeatable=True,
    )
    # Showing the map sets Mariah's offer flag (so SealDeal knows it's live).
    game.add_trigger(
        "mariah_offered",
        lambda g: g.pending_prompt() is not None
        and "Parson" in (g.pending_prompt().text or ""),
        lambda g: g.player.set_property("mariah_offered", True),
        repeatable=True,
    )
    # Mark the cactus dry once its +5 has scored (keeps CUT CACTUS one-shot).
    game.add_trigger(
        "cactus_cut",
        lambda g: "cactus" in g._scored_keys,
        lambda g: (
            g.locations["Desert (Lonely Cactus)"]
            .items["cactus"]
            .set_property("cut_open", True)
            if "cactus" in g.locations["Desert (Lonely Cactus)"].items
            else None
        ),
        repeatable=True,
    )
    return game


# ---------------------------------------------------------------------------
# Walkthrough (also the win test) -- wins 100/100
# ---------------------------------------------------------------------------

WALKTHROUGH = [
    # Town: pistol, poker, the map, supplies.
    "west",  # -> Rundown Shack
    "get pistol",  # lift pa's pistol off its hook
    "wear pistol",  # +5 (strapping on the pistol)
    "out",  # -> Main Street
    "north",  # -> Saloon
    "order drink",
    "buy sarsaparilla",  # +5 (need the penny)
    "drink bottle",  # empties the bottle, reveals Black Jack
    "examine black jack",  # -> Black Jack's Table (poker)
    "wager badge",  # +5 (anteing the badge)
    "draw",  # full house
    "call",  # +10 (winning with a full house); Black Jack rages
    "hit black jack with bottle",  # knock him out; knife + map drop on the table
    "get map",  # +5 (finding the treasure map)
    "get knife",
    "stand up",  # -> Main Street
    "east",  # -> General Store
    "show map to mariah",  # poses the grubstake deal
    "yes",  # seal the deal: +5 (procuring supplies), get the rucksack
    "out",  # -> Main Street
    "south",  # -> Outskirts of Town
    "south",  # -> Desert (needs the rucksack)
    "drink water",  # ration 3 -> 2
    "west",  # -> Creosote Bushes
    "take tinder",
    "drink water",  # 2 -> 1
    "south",  # -> Lonely Cactus
    "cut cactus",  # +5; ration 1 -> 2
    "east",  # -> Arroyo
    "drink water",  # 2 -> 1
    "south",  # -> Pine Tree
    "take firewood",
    "make camp",  # -> Campsite (night)
    "build fire",
    "use flint and steel",
    "cook beans",
    "eat beans",
    "take off boots",
    "sleep",  # -> morning
    "examine boots",  # +5 (checking your boot for snakes)
    "shake boot",
    "kill snake with knife",  # +10 (killing the rattlesnake)
    "get snake",  # the dead rattlesnake -- trade goods for Doc
    "wear boots",
    "break camp",  # -> Pine Tree
    "east",  # -> Cow Skull (camp now complete)
    "drink water",  # 1 -> 0 ("now it's gone")
    "north",  # -> Rocky Bluff
    "get flint and steel",  # pull it from the rucksack before dropping it
    "drop rucksack",
    "enter cave",  # -> Dark Cave (carrying map + flint and steel)
    "burn map",  # light the cave
    "search cave",
    "dig",  # +10 (finding the buried gold)
    "out",  # -> Rocky Bluff (spot Doc's dust to the north)
    "north",  # -> Doc Hensley's Wagon
    "give snake to doc",  # trade the snake for snake oil
    "use snake oil on hands",  # +5 (curing your ailment)
    "back to town",  # -> Main Street Clock Tower
    "duel black jack",  # -> The Six-Gun Showdown
    "wait",  # the sun climbs into Black Jack's eyes
    "draw and fire",  # +10 (defeating Black Jack and his gang)
    "show gold to mariah",  # +5 (squaring up with Mariah); she returns the badge
    "wear badge",  # +10 (becoming sheriff) + 5 (finishing) -> WIN
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
