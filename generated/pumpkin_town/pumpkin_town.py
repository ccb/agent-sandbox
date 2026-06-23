"""Pumpkin Town -- a Parsely gamebook ported to the engine.

It's Halloween night. You grab a trick-or-treat bag and a costume, fish a coin
out of a storm drain, and climb a bone ladder that drops from the sky into
Pumpkin Town -- a sprawling candy-themed underworld. Trick-or-treat your way
across town for sixteen different treats (a candy lab, a tentacle lake, a swamp,
a ghost-train carnival, a forest cathedral, a gingerbread mine, and Pumpkin Town
Hell), dodge the calamities that would land you in the Graveyard, then climb the
ladder home. A perfect run scores 100.
Source: Parsely "Pumpkin Town" (the Parsely r31 collection).

Authored the way the reference ports are (see ``action_castle_2.py`` and
``docs/converting-parsely-games.md``): a ``build_game()`` assembles the world; a
``PumpkinTown`` Game subclass holds the scoring, the win, and the "emergency trip
to the Graveyard" relocation that several fail-states share; the two-object
interactions (USE PITCHFORK ON CHICKS, WHIP DEVIL) use the engine's
``use_item_on`` factory; small ``Action`` subclasses cover the one-off verbs.

Scoring (max 100): sixteen treats at +5 each (=80), +5 for returning home, and
three +5 bonuses for *avoiding* pitfalls -- not being kicked off the Ghost Train,
not being kicked out of Pumpkin Town Hell, and never taking an emergency trip to
the Graveyard.

Faithfulness calls (the rulebook is a sprawling two-column gamebook, so a few
decisions are the porter's -- see docs section 12):

* The big one -- *the coin/costume contradiction.* A perfect 100 needs cotton
  candy (bought with the one Funland coin) AND a free ride to Funland (so the
  coin survives the fare). The coin can only be fished from the Elm Street storm
  drain with the pirate's hook hand, but only the *ghost* (invisible) rides the
  train free -- and you may wear only one costume. Strict rules make 100
  impossible. Resolution: the canonical run wears the **ghost** costume and also
  carries the pirate's **hook hand** as a loose prop (TAKE HOOK). The "one
  costume" rule still holds (you wear only the ghost sheet); the hook is just a
  tool. This is the single change that makes a perfect run reachable.
* The forest's "you'll never make it home" is modeled as a *gate* (the east exit
  to the cathedral is blocked until you MARK TRAIL with a candy), not a death.
* The Bell Tower's milk-and-cookies gingerbread puzzle is left as flavor; the
  rulebook offers an alternate gingerbread source (pour molasses in Gingerbread
  Fields), which is the one the canonical run uses.
* A handful of rhetorical yes/no confirmations (CLIMB LADDER, GET LICORICE,
  ENTER SWAMP) are collapsed into their direct verbs; only the devil's
  "have you been good?" uses a posed prompt, since both answers matter.

Run interactively:    uv run python -m test_gen.pumpkin_town.pumpkin_town
Run the walkthrough:  uv run python -m test_gen.pumpkin_town.pumpkin_town --walk
"""

from text_adventure_games import games, things, actions, blocks, Prompt

Action = actions.Action


# ---------------------------------------------------------------------------
# Held-item helpers (held = inventory + worn + wielded + open carried holders).
# A quest check on bare ``inventory`` would miss a worn item or one tucked in a
# carried bag, so everything that asks "do you have X?" goes through these.
# ---------------------------------------------------------------------------


def _held_names(character):
    names = set(character.inventory) | set(character.worn) | set(character.wielded)
    holders = list(character.inventory.values()) + list(character.worn.values())
    for holder in holders:
        if holder.is_holder() and holder.is_open():
            names |= set(holder.contents)
    return names


def _is_holding(character, name):
    return name in _held_names(character)


def _take_held(character, name):
    """Remove and return a held item by name, else None."""
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
    """A connection WITHOUT add_connection()'s canonical auto-reverse, so the
    many ``out``->hub exits don't collide over the hub's ``in``."""
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


def _costume(character):
    """The kind of costume the character is wearing (witch/pirate/ghost/hobo),
    or None."""
    for item in character.worn.values():
        kind = item.get_property("costume_kind")
        if kind:
            return kind
    return None


def _wear_costume(character, kind):
    """Create and equip a costume of *kind* (replacing the worn-costume slot)."""
    name = f"{kind} costume"
    item = things.Item(name, f"a {kind} costume", f"You're dressed as a {kind}.")
    item.set_property("costume_kind", kind)
    item.set_property("wearable", True)
    character.add_to_inventory(item)
    character.wear(item)
    return item


# The sixteen treats and the scoring key each books for. The item NAME is the
# dict key; a repeatable trigger awards a treat the first turn the player holds
# it (with the trick-or-treat bag) -- so most treats are just items you collect.
TREATS = {
    "bubble gum": "bubble_gum",
    "candy corn": "candy_corn",
    "jawbreaker": "jawbreaker",
    "cookies": "cookies",
    "gummi worms": "gummi_worms",
    "licorice": "licorice",
    "chocolate": "chocolate",
    "butterscotch": "butterscotch",
    "pixie dust": "pixie_dust",
    "cotton candy": "cotton_candy",
    "circus peanuts": "circus_peanuts",
    "candy cane": "candy_cane",
    "gingerbread person": "gingerbread",
    "marshmallow chicks": "chicks",
    "rock candy": "rock_candy",
    "cinnamon hearts": "cinnamon_hearts",
}


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


class GuardBlock(blocks.Block):
    """The Candy Lab is shut to all but a ghost (who sneaks past unseen) or
    someone the guard has waved in after SHOW ID TO GUARD."""

    def __init__(self, game):
        super().__init__(
            "The factory is closed",
            '"Sorry, the factory is closed for Halloween," says the prickly guard.',
        )
        self.game = game

    def is_blocked(self) -> bool:
        return not (_costume(self.game.player) == "ghost" or self.game.guard_satisfied)


class TrailBlock(blocks.Block):
    """The Forest of Death won't let you press on to the cathedral until you've
    marked a trail so you can find your way back."""

    def __init__(self, forest):
        super().__init__(
            "A nameless dread",
            "A Nameless Primal Dread fills you! If you got lost in here you'd "
            "never make it home. If only there were a way to mark a trail... "
            "(try MARK TRAIL)",
        )
        self.forest = forest

    def is_blocked(self) -> bool:
        return not self.forest.get_property("trail_marked")


# ---------------------------------------------------------------------------
# Game subclass: scoring, the win, and the shared "emergency Graveyard" trip.
# ---------------------------------------------------------------------------


class PumpkinTown(games.Game):
    """Won by climbing the bone ladder home from Main Street (a perfect run = 100)."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        self.max_score = 100
        self.returned = False
        # Pitfall flags: each starts clean (False) and the matching +5 bonus is
        # awarded at the end if it's still clean.
        self.kicked_off_train = False
        self.kicked_out_of_hell = False
        self.emergency_graveyard = False
        # One-off interaction state.
        self.knocked = False
        self.bell_rung = False
        self.ladder_dropped = False
        self.guard_satisfied = False
        self.devil_whipped = False
        self.beach_closed = False

    def emergency_to_graveyard(self, text, ruin_costume=False):
        """A calamity knocks the player out; they wake up in the Graveyard. This
        forfeits the 'no emergency trip' bonus, and a ruined costume is replaced
        by the night nurse with a hobo costume."""
        self.emergency_graveyard = True
        self.parser.ok(text)
        if ruin_costume:
            for nm, it in list(self.player.worn.items()):
                if it.get_property("costume_kind"):
                    self.player.worn.pop(nm)
            _wear_costume(self.player, "hobo")
            self.parser.ok(
                "The night nurse tuts and re-dresses you as a hobo: a bowler hat, "
                "a bow tie and floppy shoes. Your bindle holds a hobo nickel and a "
                "tin of beans."
            )
        self.relocate(self.player, self.locations["Graveyard"])
        self.parser.ok(self.describe())

    def finish(self):
        """Climb the ladder home from Main Street: tally the return point and the
        three pitfall-avoidance bonuses, then end the game."""
        self.returned = True
        self.award(
            "return",
            5,
            "You climb the bone ladder. Halfway up you grow dizzy, your fingers "
            "slip, and you fall for an eternity... only to wake up in bed, "
            "clutching your trick-or-treat bag!",
        )
        if not self.kicked_off_train:
            self.award(
                "bonus_train", 5, "Bonus: you were never kicked off the Ghost Train!"
            )
        if not self.kicked_out_of_hell:
            self.award(
                "bonus_hell",
                5,
                "Bonus: you were never kicked out of Pumpkin Town Hell!",
            )
        if not self.emergency_graveyard:
            self.award(
                "bonus_graveyard", 5, "Bonus: no emergency trips to the Graveyard!"
            )
        self.announce_ending("Was it all a dream? THE END.", show_score=True)

    def is_won(self) -> bool:
        return bool(self.returned)


def _score_treats(game):
    """React-phase trigger: award any treat the player is holding (the bag is
    required to collect treats and score points, per the rulebook)."""
    player = game.player
    if not _is_holding(player, "bag"):
        return
    for name in _held_names(player):
        key = TREATS.get(name)
        if key:
            game.award(key, 5, f"(+5) You bag the {name}.")


# ---------------------------------------------------------------------------
# Costume + prop pickup (Your House)
# ---------------------------------------------------------------------------


def _take_costume_action(kind):
    class _TakeCostume(Action):
        ACTION_NAME = f"take {kind} costume"
        ACTION_DESCRIPTION = f"Take and put on the {kind} costume"
        ACTION_ALIASES = [
            f"wear {kind} costume",
            f"put on {kind} costume",
            f"take the {kind} costume",
            f"get {kind} costume",
            f"don {kind} costume",
        ]

        def __init__(self, game, command, actor=None):
            super().__init__(game, actor=actor)
            self.character = self.acting_character(command)

        def check_preconditions(self) -> bool:
            if "boxes" not in self.character.location.items:
                self.parser.fail("There are no costume boxes here.")
                return False
            if _costume(self.character):
                self.parser.fail(
                    "You may take only one costume. You're already wearing one."
                )
                return False
            return True

        def apply_effects(self):
            _wear_costume(self.character, kind)
            self.parser.ok(f"You pull on the {kind} costume. Spooky!")

    _TakeCostume.__name__ = f"Take{kind.capitalize()}Costume"
    return _TakeCostume


TakeWitchCostume = _take_costume_action("witch")
TakePirateCostume = _take_costume_action("pirate")
TakeGhostCostume = _take_costume_action("ghost")


class TakeHook(Action):
    ACTION_NAME = "take hook"
    ACTION_DESCRIPTION = "Take the pirate costume's hook hand as a tool"
    ACTION_ALIASES = [
        "take hook hand",
        "get hook",
        "get hook hand",
        "take the hook hand",
        "grab hook",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "boxes" not in self.character.location.items:
            self.parser.fail("There's no hook hand here.")
            return False
        if _is_holding(self.character, "hook"):
            self.parser.fail("You already have the hook hand.")
            return False
        return True

    def apply_effects(self):
        hook = things.Item(
            "hook",
            "the pirate costume's wicked hook hand",
            "A wicked hook hand from the Pirate Bill costume -- handy for reaching "
            "things your fingers can't.",
        )
        hook.add_command_hint("stick gum on hook")
        self.character.add_to_inventory(hook)
        self.parser.ok("You snap the wicked hook hand off the Pirate Bill costume.")


# ---------------------------------------------------------------------------
# Elm Street: the coin, the neighbors, the bone ladder
# ---------------------------------------------------------------------------


class ChewGum(Action):
    ACTION_NAME = "chew gum"
    ACTION_DESCRIPTION = "Chew the bubble gum"
    ACTION_ALIASES = ["chew bubble gum", "chew the gum"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "bubble gum"):
            self.parser.fail("You don't have any bubble gum to chew.")
            return False
        return True

    def apply_effects(self):
        self.character.set_property("gum_chewed", True)
        self.parser.ok(
            "You chew the bubble gum until it loses its flavor and your jaw hurts."
        )


class StickGumOnHook(Action):
    ACTION_NAME = "stick gum on hook"
    ACTION_DESCRIPTION = "Stick the chewed gum on the hook hand"
    ACTION_ALIASES = [
        "put gum on hook",
        "stick the gum on the hook",
        "stick gum on hook hand",
        "stick gum on the hook hand",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "hook"):
            self.parser.fail("You don't have a hook hand.")
            return False
        if not self.character.get_property("gum_chewed"):
            self.parser.fail("You should chew the gum first so it's nice and sticky.")
            return False
        return True

    def apply_effects(self):
        self.character.set_property("gum_on_hook", True)
        self.parser.ok("You stick the wad of gum on the end of your hook hand.")


class UseHookOnCoin(Action):
    ACTION_NAME = "use hook on coin"
    ACTION_DESCRIPTION = "Fish the coin out of the storm drain with the gummed hook"
    ACTION_ALIASES = [
        "get coin with hook",
        "fish out coin",
        "fish coin",
        "reach for the coin with the hook",
        "use hook hand on coin",
        "use the hook on the coin",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Elm Street":
            self.parser.fail("There's no storm drain here.")
            return False
        if _is_holding(self.character, "coin"):
            self.parser.fail("You already fished out the coin.")
            return False
        if not _is_holding(self.character, "hook"):
            self.parser.fail("Your hand is too big to fit through the narrow grate.")
            return False
        if not self.character.get_property("gum_on_hook"):
            self.parser.fail(
                "The coin is just out of reach. If only the hook were a little... "
                "stickier."
            )
            return False
        return True

    def apply_effects(self):
        coin = things.Item(
            "coin",
            "a silver Funland coin",
            'A silver coin -- heads is a jester\'s cap, tails reads "FUNLAND."',
        )
        coin.add_command_hint("buy cotton candy")
        self.character.add_to_inventory(coin)
        self.parser.ok(
            "You reach through the narrow grate with your hook and stick the gum to "
            "the coin. You now have a coin!"
        )


class GetCoin(Action):
    ACTION_NAME = "get coin"
    ACTION_DESCRIPTION = "Try to grab the coin in the storm drain"
    ACTION_ALIASES = ["take coin", "grab coin", "reach for coin"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Elm Street":
            self.parser.fail("There's no coin here.")
            return False
        return True

    def apply_effects(self):
        if _is_holding(self.character, "coin"):
            self.parser.ok("You already have the coin.")
        else:
            self.parser.fail("Your hand is too big to fit through the narrow grate.")


class KnockOnDoor(Action):
    ACTION_NAME = "knock on door"
    ACTION_DESCRIPTION = "Knock on the neighbor's door"
    ACTION_ALIASES = ["knock", "knock on the door", "knock door"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Elm Street":
            self.parser.fail("There's no door to knock on here.")
            return False
        return True

    def apply_effects(self):
        self.game.knocked = True
        self.parser.ok(
            "You knock. The door opens and you're greeted by an elderly couple -- "
            "your neighbors, the Parsons -- holding a bowl of candy."
        )


class TrickOrTreat(Action):
    ACTION_NAME = "say trick or treat"
    ACTION_DESCRIPTION = "Say the magic words"
    ACTION_ALIASES = ["trick or treat", "say trick-or-treat", "trick-or-treat"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        loc = self.character.location.name
        if loc == "Elm Street":
            if not self.game.knocked:
                self.parser.fail("Maybe you should knock first?")
                return False
            return True
        if loc == "Tentacle Hill":
            if not self.game.bell_rung:
                self.parser.fail("Maybe you should ring the doorbell first?")
                return False
            return True
        self.parser.fail("There's no one here to trick-or-treat.")
        return False

    def apply_effects(self):
        loc = self.character.location.name
        costumed = _costume(self.character) is not None
        if loc == "Elm Street":
            self.game.ladder_dropped = True
            if costumed:
                self.character.add_to_inventory(
                    things.Item(
                        "candy corn",
                        "a handful of stale candy corn",
                        "Stale candy corn from the Parsons.",
                    )
                )
                self.parser.ok(
                    '"Oh, aren\'t you a cute little trick-or-treater!" They give you '
                    "the last of their candy: some stale candy corn, then say good "
                    "night and turn off their lights. A mysterious ladder drops from "
                    "the night sky!"
                )
            else:
                self.parser.ok(
                    'Your neighbors yell at you for "horsing around," then close and '
                    "lock their door and turn off the light. A mysterious ladder "
                    "drops from the night sky!"
                )
        else:  # Tentacle Hill
            if not costumed:
                self.parser.fail('"You\'re not in costume!" She closes the door.')
                return
            self.character.add_to_inventory(
                things.Item(
                    "cookies",
                    "warm homemade chocolate chip cookies",
                    "Warm chocolate chip cookies from the lady on Tentacle Hill.",
                )
            )
            self.parser.ok(
                '"Oh my, look at you! How scary!" She gives you some homemade '
                "chocolate chip cookies, then says goodbye and closes the door."
            )


class RingBell(Action):
    ACTION_NAME = "ring bell"
    ACTION_DESCRIPTION = "Ring the bell"
    ACTION_ALIASES = [
        "ring the bell",
        "ring doorbell",
        "ring the doorbell",
        "pull rope",
        "pull the rope",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        loc = self.character.location.name
        if loc not in ("Tentacle Hill", "Bell Tower"):
            self.parser.fail("There's no bell here.")
            return False
        return True

    def apply_effects(self):
        loc = self.character.location
        if loc.name == "Tentacle Hill":
            self.game.bell_rung = True
            self.parser.ok(
                'You ring the bell and hear a voice say, "Just a moment!" The door '
                "opens and a woman in an apron greets you with a tray of warm "
                'chocolate chip cookies. "Oh my, how scary!"'
            )
        else:  # Bell Tower
            if "bell ringer" in loc.characters:
                self.parser.fail(
                    'The bell ringer stands in front of the rope. "Oi! Get your own '
                    'bell!"'
                )
                return
            if "gingerbread person" not in loc.items and not loc.get_property(
                "bell_rung"
            ):
                loc.set_property("bell_rung", True)
                gp = things.Item(
                    "gingerbread person",
                    "a gingerbread person, one arm broken off",
                    "Five-second rule! An arm broke off, but it otherwise looks okay.",
                )
                gp.add_command_hint("get gingerbread person")
                loc.add_item(gp)
            self.parser.ok(
                "The bell rings loudly, disturbing a bat in the belfry. It flies "
                "away, dropping the gingerbread person it was carrying."
            )


class ClimbLadder(Action):
    ACTION_NAME = "climb ladder"
    ACTION_DESCRIPTION = "Climb the bone ladder"
    ACTION_ALIASES = [
        "climb the ladder",
        "climb bone ladder",
        "climb the bone ladder",
        "climb",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        loc = self.character.location.name
        if loc == "Elm Street":
            if not self.game.ladder_dropped:
                self.parser.fail("There's no ladder here.")
                return False
            return True
        if loc == "Main Street":
            return True
        self.parser.fail("There's no ladder here.")
        return False

    def apply_effects(self):
        if self.character.location.name == "Elm Street":
            self.game.relocate(self.character, self.game.locations["Main Street"])
            self.parser.ok(
                "You climb. Halfway up, you look down and see that Elm Street is "
                "gone -- and then you're stepping off the ladder onto an unfamiliar "
                "street. Welcome to Pumpkin Town!"
            )
            self.parser.ok(self.game.describe())
        else:  # Main Street -> home (the win)
            self.game.finish()


# ---------------------------------------------------------------------------
# The Candy Factory / Candy Lab
# ---------------------------------------------------------------------------


class ShowIdToGuard(Action):
    ACTION_NAME = "show id to guard"
    ACTION_DESCRIPTION = "Show the ID badge to the security guard"
    ACTION_ALIASES = [
        "show id",
        "show badge to guard",
        "show id badge to guard",
        "give id to guard",
        "show the id to the guard",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "guard" not in self.character.location.characters:
            self.parser.fail("There's no guard here.")
            return False
        if not _is_holding(self.character, "id badge"):
            self.parser.fail("You don't have an ID badge to show.")
            return False
        return True

    def apply_effects(self):
        self.game.guard_satisfied = True
        self.parser.ok(
            'The guard glances blankly at your ID, not even looking up. "Working '
            'late, Norm? Go on in."'
        )


# ---------------------------------------------------------------------------
# The Ghost Train / Funland
# ---------------------------------------------------------------------------


class BoardTrain(Action):
    ACTION_NAME = "board train"
    ACTION_DESCRIPTION = "Board the ghost train to Funland"
    ACTION_ALIASES = [
        "board the train",
        "get on the train",
        "get on train",
        "board ghost train",
        "ride train",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Ghost Train":
            self.parser.fail("There's no train to board here.")
            return False
        return True

    def apply_effects(self):
        kind = _costume(self.character)
        if kind == "ghost":
            self._ride(
                "Invisible in your ghost costume, you slip past the "
                "conductor and sneak aboard unseen."
            )
        elif kind == "hobo" and _is_holding(self.character, "bindle"):
            self._ride(
                "You flash the hobo nickel from your bindle. The conductor waves "
                "you aboard to ride the rails for free."
            )
        elif kind == "witch":
            self.parser.fail(
                'The conductor blocks your path. "Fare, please!" (A witch could '
                "just FLY TO FUNLAND on her broom.)"
            )
        elif _is_holding(self.character, "coin"):
            self.parser.fail(
                'The conductor blocks your path. "Fare, please!" (Try GIVE COIN TO '
                "CONDUCTOR.)"
            )
        else:
            self.game.kicked_off_train = True
            self.parser.fail("Without a fare, the conductor boots you off the train.")

    def _ride(self, text):
        self.game.relocate(self.character, self.game.locations["Funland"])
        self.parser.ok(text)
        self.parser.ok(
            "After a while you find yourself approaching the circus tents and "
            "rides of Funland!"
        )
        self.parser.ok(self.game.describe())


class GiveCoinToConductor(Action):
    ACTION_NAME = "give coin to conductor"
    ACTION_DESCRIPTION = "Pay the ghost-train fare"
    ACTION_ALIASES = [
        "pay fare",
        "pay the fare",
        "give the coin to the conductor",
        "pay conductor",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Ghost Train":
            self.parser.fail("There's no conductor here.")
            return False
        if not _is_holding(self.character, "coin"):
            self.parser.fail("You don't have a coin for the fare.")
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "coin")
        self.game.relocate(self.character, self.game.locations["Funland"])
        self.parser.ok(
            "You hand the conductor the coin and climb aboard. After a while you "
            "find yourself approaching Funland!"
        )
        self.parser.ok(self.game.describe())


class FlyToFunland(Action):
    ACTION_NAME = "fly to funland"
    ACTION_DESCRIPTION = "Fly to Funland on the witch's broom"
    ACTION_ALIASES = ["fly to funland on broom", "fly on broom to funland"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if _costume(self.character) != "witch":
            self.parser.fail("You can't fly without the witch's broom.")
            return False
        return True

    def apply_effects(self):
        self.game.relocate(self.character, self.game.locations["Funland"])
        self.parser.ok("On the old-timey broom you soar over Pumpkin Town to Funland!")
        self.parser.ok(self.game.describe())


class BuyCottonCandy(Action):
    ACTION_NAME = "buy cotton candy"
    ACTION_DESCRIPTION = "Buy cotton candy from the snack witch"
    ACTION_ALIASES = [
        "ask for cotton candy",
        "buy cotton candy from witch",
        "give coin to witch",
        "ask the witch for cotton candy",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "snack witch" not in self.character.location.characters:
            self.parser.fail("There's no one here selling cotton candy.")
            return False
        if _is_holding(self.character, "cotton candy"):
            self.parser.fail("You already have cotton candy.")
            return False
        if not _is_holding(self.character, "coin"):
            self.parser.fail('"One coin, please!" -- and you don\'t have one.')
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "coin")
        self.character.add_to_inventory(
            things.Item(
                "cotton candy",
                "a cone of pink-and-blue cotton candy",
                "Pink and blue spun sugar on a cone.",
            )
        )
        self.parser.ok(
            "You hand over the coin. The snack witch gives you a cone of cotton candy."
        )


class BuyApple(Action):
    ACTION_NAME = "buy apple"
    ACTION_DESCRIPTION = "Ask the snack witch for an apple"
    ACTION_ALIASES = ["ask for apple", "ask for an apple", "buy an apple", "get apple"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "snack witch" not in self.character.location.characters:
            self.parser.fail("There's no one here selling apples.")
            return False
        return True

    def apply_effects(self):
        if _costume(self.character) == "witch":
            self.parser.fail(
                '"Oh dearie..." The snack witch eyes your witch costume. "You should '
                "really know better!\" She won't give a witch any apples."
            )
            return
        if not _is_holding(self.character, "apple"):
            apple = things.Item(
                "apple",
                "a shiny red apple",
                "A suspiciously shiny red apple. Definitely safe to eat. Definitely.",
            )
            apple.set_property("poisoned", True)
            self.character.add_to_inventory(apple)
        self.parser.ok(
            '"For you, free of charge!" The witch cackles as she hands you a shiny '
            'red apple. "Oh dearie... you should really know better!"'
        )


class ThrowJawbreaker(Action):
    ACTION_NAME = "throw jawbreaker"
    ACTION_DESCRIPTION = "Throw the exploding jawbreaker"
    ACTION_ALIASES = [
        "throw the jawbreaker",
        "throw jawbreaker at bottles",
        "throw jawbreaker at carny",
        "throw jawbreaker at booth",
        "throw jawbreaker at tentacle",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "jawbreaker"):
            self.parser.fail("You don't have a jawbreaker to throw.")
            return False
        return True

    def apply_effects(self):
        loc = self.character.location.name
        if loc == "Inside the Big Top":
            _take_held(self.character, "jawbreaker")
            self.character.add_to_inventory(
                things.Item(
                    "circus peanuts",
                    "a bag of orange circus peanuts",
                    "The grossest candy in the world. Still, you won something!",
                )
            )
            self.parser.ok(
                "It explodes! The heavy milk bottles are sent flying. The carny "
                "reluctantly hands over a bag of orange circus peanuts."
            )
        elif loc == "Cauldron Point":
            self.parser.ok(
                "The tentacle is not there -- whatever's in that lake is submerged "
                "below the surface."
            )
        else:
            self.parser.fail("There's nothing here worth throwing it at.")


# ---------------------------------------------------------------------------
# The Swamp
# ---------------------------------------------------------------------------


class GetLicorice(Action):
    ACTION_NAME = "get licorice"
    ACTION_DESCRIPTION = "Pull down some black licorice whips"
    ACTION_ALIASES = [
        "take licorice",
        "get black licorice",
        "take black licorice",
        "grab licorice",
        "pick licorice",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Mucky-Muck Swamp":
            self.parser.fail("There's no licorice here.")
            return False
        if _is_holding(self.character, "licorice"):
            self.parser.fail("You've already got some licorice whips.")
            return False
        return True

    def apply_effects(self):
        whip = things.Item(
            "licorice",
            "a tangle of black licorice whips",
            "Tangled black licorice whips. You could crack one like a whip.",
        )
        whip.add_command_hint("whip devil")
        self.character.add_to_inventory(whip)
        self.parser.ok(
            '"Do you really like black licorice, or are you just trying to score '
            'points?" You insist, and pull down some black licorice whips.'
        )


class GetChocolate(Action):
    ACTION_NAME = "get chocolate"
    ACTION_DESCRIPTION = "Scavenge dark chocolate from the trees"
    ACTION_ALIASES = [
        "take chocolate",
        "get dark chocolate",
        "grab chocolate",
        "pick chocolate",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Mucky-Muck Swamp":
            self.parser.fail("There's no chocolate here.")
            return False
        if _is_holding(self.character, "chocolate"):
            self.parser.fail("You've already gathered some chocolate.")
            return False
        return True

    def apply_effects(self):
        self.character.add_to_inventory(
            things.Item(
                "chocolate",
                "dark chocolate bark and bittersweet twigs",
                "Dark chocolate bark and bittersweet twigs from the chocolate trees.",
            )
        )
        self.parser.ok(
            "You scavenge some dark chocolate bark and bittersweet twigs from the "
            "trees."
        )


class FillBucket(Action):
    ACTION_NAME = "fill bucket"
    ACTION_DESCRIPTION = "Scoop a bucketful of molasses"
    ACTION_ALIASES = [
        "get molasses",
        "scoop molasses",
        "use bucket",
        "fill bucket with molasses",
        "fill the bucket",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Mucky-Muck Swamp":
            self.parser.fail("There's no molasses to scoop here.")
            return False
        if not _is_holding(self.character, "bucket"):
            self.parser.fail("You need an empty bucket to scoop molasses.")
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "bucket")
        molasses = things.Item(
            "bucket of molasses",
            "a bucket of sticky molasses",
            "A bucket brimming with sticky molasses -- good for trapping a "
            "gingerbread person.",
        )
        molasses.add_command_hint("pour molasses")
        self.character.add_to_inventory(molasses)
        self.parser.ok("You scoop a bucketful of sticky molasses from a bubbling pool.")


class EnterSwamp(Action):
    ACTION_NAME = "enter swamp"
    ACTION_DESCRIPTION = "Dare to enter the swamp"
    ACTION_ALIASES = [
        "enter the swamp",
        "go into swamp",
        "wade into swamp",
        "dare enter swamp",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Mucky-Muck Swamp":
            self.parser.fail("There's no swamp to enter here.")
            return False
        return True

    def apply_effects(self):
        if _is_holding(self.character, "candy cane"):
            self.game.relocate(self.character, self.game.locations["Tin Shack"])
            self.parser.ok(
                "Feeling your way through the treacherous swamp with the candy cane, "
                "you come across a tin shack."
            )
            self.parser.ok(self.game.describe())
        else:
            self.game.emergency_to_graveyard(
                "You foolishly wander into the swamp and fall into a sticky pool of "
                "molasses. It sucks you under and you pass out.",
                ruin_costume=True,
            )


# ---------------------------------------------------------------------------
# Pitchfork Farms / Gingerbread Fields / Sugar Mines
# ---------------------------------------------------------------------------


class MilkCow(Action):
    ACTION_NAME = "milk cow"
    ACTION_DESCRIPTION = "Milk the zombie cow into the bucket"
    ACTION_ALIASES = ["milk the cow", "use bucket on cow"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "cow" not in self.character.location.items:
            self.parser.fail("There's no cow here.")
            return False
        if not _is_holding(self.character, "bucket"):
            self.parser.fail("You need an empty bucket to milk the cow.")
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "bucket")
        self.character.add_to_inventory(
            things.Item(
                "bucket of milk",
                "a bucket of milk",
                "A bucket of fresh (well, zombie-fresh) milk.",
            )
        )
        self.parser.ok("The cow shambles over to be milked. You get a bucket of milk.")


class PourMolasses(Action):
    ACTION_NAME = "pour molasses"
    ACTION_DESCRIPTION = "Pour the molasses to snare a gingerbread person"
    ACTION_ALIASES = [
        "use molasses",
        "pour the molasses",
        "pour molasses on ground",
        "empty bucket",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Gingerbread Fields":
            self.parser.fail("There's nothing here to catch with molasses.")
            return False
        if not _is_holding(self.character, "bucket of molasses"):
            self.parser.fail("You don't have any molasses to pour.")
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "bucket of molasses")
        self.character.add_to_inventory(
            things.Item("bucket", "an empty bucket", "An empty bucket.")
        )
        self.character.add_to_inventory(
            things.Item(
                "gingerbread person",
                "a gingerbread person, stuck and squirming",
                "A gingerbread person caught in the molasses. Tasty!",
            )
        )
        self.parser.ok(
            "The sticky syrup covers the ground and snares a gingerbread person as "
            "they try to run across it! You scoop it up."
        )


class MineRockCandy(Action):
    ACTION_NAME = "mine rock candy"
    ACTION_DESCRIPTION = "Mine blue rock candy with the pickaxe"
    ACTION_ALIASES = [
        "mine rock candy with pickaxe",
        "use pickaxe on rock candy",
        "mine",
        "chip rock candy",
        "mine candy",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Sugar Mines":
            self.parser.fail("There's no rock candy to mine here.")
            return False
        if not _is_holding(self.character, "pickaxe"):
            self.parser.fail("You'd need a pickaxe to chip out the rock candy.")
            return False
        if _is_holding(self.character, "rock candy"):
            self.parser.fail("You've already mined a chunk of rock candy.")
            return False
        return True

    def apply_effects(self):
        self.character.add_to_inventory(
            things.Item(
                "rock candy",
                "a chunk of blue rock candy",
                "A good-sized chunk of blue rock candy. Do you know the street value?",
            )
        )
        self.parser.ok("You chip off a good-sized chunk of blue rock candy.")


# ---------------------------------------------------------------------------
# Cauldron Point
# ---------------------------------------------------------------------------


class EnterLake(Action):
    ACTION_NAME = "enter lake"
    ACTION_DESCRIPTION = "Wade into the bubbling lake"
    ACTION_ALIASES = [
        "enter the lake",
        "swim",
        "dive in",
        "wade into the lake",
        "go in lake",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Cauldron Point":
            self.parser.fail("There's no lake here.")
            return False
        if self.game.beach_closed:
            self.parser.fail('A sign reads, "BEACH CLOSED UNTIL FURTHER NOTICE."')
            return False
        return True

    def apply_effects(self):
        armed = (
            _is_holding(self.character, "pitchfork")
            or _costume(self.character) == "pirate"
        )
        if armed:
            if _is_holding(self.character, "gummi worms"):
                self.parser.ok('Gill grins. "Already got your worms, bro. Stay dry!"')
                return
            self.character.add_to_inventory(
                things.Item(
                    "gummi worms",
                    "a bag of gummi worms",
                    "A squishy bag of gummi worms from Gill the lifeguard.",
                )
            )
            self.parser.ok(
                "A tentacle grabs you from below -- but you jab it hard and it lets "
                "go! Gill is impressed by your bravery and offers you a bag of gummi "
                "worms."
            )
        else:
            self.game.beach_closed = True
            self.game.emergency_to_graveyard(
                "A tentacle grabs you from below and pulls you under! You struggle, "
                "but you're no match for it -- until Gill hauls you out and loads "
                "you into a hearse.",
                ruin_costume=True,
            )


# ---------------------------------------------------------------------------
# The Forest of Death / Cathedral / Bell Tower
# ---------------------------------------------------------------------------


class MarkTrail(Action):
    ACTION_NAME = "mark trail"
    ACTION_DESCRIPTION = "Mark a trail through the Forest of Death"
    ACTION_ALIASES = [
        "mark a trail",
        "mark trail with candy corn",
        "leave a trail",
        "lay a trail",
    ]
    _MARKERS = ("candy corn", "circus peanuts", "cinnamon hearts")

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Forest of Death":
            self.parser.fail("There's no trail to mark here.")
            return False
        if not any(_is_holding(self.character, m) for m in self._MARKERS):
            self.parser.fail(
                "You need something to drop as a trail -- candy corn, circus "
                "peanuts or red-hot cinnamon hearts would do."
            )
            return False
        return True

    def apply_effects(self):
        self.character.location.set_property("trail_marked", True)
        self.parser.ok(
            "You drop a trail of candy behind you. Now you can find your way back "
            "if you get lost! Summoning your courage, you press on toward the "
            "abandoned cathedral to the east."
        )


# ---------------------------------------------------------------------------
# Pumpkin Town Hell
# ---------------------------------------------------------------------------


class TalkToDevil(Action):
    ACTION_NAME = "talk to devil"
    ACTION_DESCRIPTION = "Talk to the devil"
    ACTION_ALIASES = ["talk devil", "ask devil", "speak to devil", "talk to the devil"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "devil" not in self.character.location.characters:
            self.parser.fail("There's no devil here.")
            return False
        return True

    def apply_effects(self):
        question = (
            "The big devil holds out a goblet of red-hot cinnamon hearts and asks, "
            '"Tell me, have you been a good little trick-or-treater this Halloween?"'
        )
        self.parser.ok(question)
        self.game.pose_prompt(
            Prompt(text=question, options={"no": "devil no", "yes": "devil yes"})
        )


class DevilNo(Action):
    ACTION_NAME = "devil no"
    ACTION_DESCRIPTION = "Tell the devil you've been bad"
    ACTION_ALIASES = ["tell devil no", "say no to devil"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "devil" not in self.character.location.characters:
            self.parser.fail("There's no devil here.")
            return False
        return True

    def apply_effects(self):
        if _is_holding(self.character, "cinnamon hearts"):
            self.parser.ok("The devil chuckles. You already have your cinnamon hearts.")
            return
        self.character.add_to_inventory(
            things.Item(
                "cinnamon hearts",
                "a handful of red-hot cinnamon hearts",
                "Red-hot cinnamon hearts straight from the devil's goblet.",
            )
        )
        self.parser.ok(
            '"Naughty, eh?" The devil gives you a handful of red-hot cinnamon hearts.'
        )


class DevilYes(Action):
    ACTION_NAME = "devil yes"
    ACTION_DESCRIPTION = "Tell the devil you've been good"
    ACTION_ALIASES = ["tell devil yes", "say yes to devil"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if "devil" not in self.character.location.characters:
            self.parser.fail("There's no devil here.")
            return False
        return True

    def apply_effects(self):
        self.game.kicked_out_of_hell = True
        self.game.relocate(self.character, self.game.locations["Creepy Catacombs"])
        self.parser.ok(
            '"THEN GET OUT!" The devil kicks you out, back to the creepy catacombs.'
        )
        self.parser.ok(self.game.describe())


def _whip_devil_effect(action):
    hell = action.character.location
    if not action.game.devil_whipped:
        pitchfork = things.Item(
            "pitchfork",
            "the devil's three-tined pitchfork",
            "A sturdy three-tined pitchfork the devil dropped.",
        )
        pitchfork.add_command_hint("get pitchfork")
        hell.add_item(pitchfork)
        action.game.devil_whipped = True


WhipDevil = actions.use_item_on(
    "whip devil",
    item="licorice",
    target="devil",
    verb="whip",
    preposition="with",
    description="Crack the licorice whip at the devil",
    aliases=["whip the devil", "use licorice on devil", "crack whip at devil"],
    effect=_whip_devil_effect,
    success=(
        "He yelps and drops his pitchfork. \"I'm a bad devil! Haha, that was fun! "
        'Do it again!"'
    ),
    item_missing="You don't have a whip to crack.",
    target_missing="There's no devil here.",
)


# ---------------------------------------------------------------------------
# Pitchfork on the marshmallow chicks (the engine's two-object verb)
# ---------------------------------------------------------------------------


def _spear_chicks(action):
    if "marshmallow chicks" not in action.character.inventory:
        action.character.add_to_inventory(
            things.Item(
                "marshmallow chicks",
                "a few marshmallow chicks",
                "Soft marshmallow chicks, freshly impaled.",
            )
        )


UsePitchforkOnChicks = actions.use_item_on(
    "use pitchfork on chicks",
    item="pitchfork",
    target="chicks",
    verb="use",
    preposition="on",
    description="Spear the marshmallow chicks with the pitchfork",
    aliases=[
        "spear chicks",
        "stab chicks",
        "impale chicks",
        "use the pitchfork on the chicks",
    ],
    effect=_spear_chicks,
    success="You impale some marshmallow chicks.",
    requires=lambda a: (
        "You already speared some chicks."
        if "marshmallow chicks" in a.character.inventory
        else None
    ),
    item_missing="You don't have a pitchfork.",
    target_missing="There are no chicks here.",
)


# ---------------------------------------------------------------------------
# Eat / drop fail-states (each lands you in the Graveyard)
# ---------------------------------------------------------------------------


def _consume_failstate(action_name, aliases, item_name, text):
    class _Fail(Action):
        ACTION_NAME = action_name
        ACTION_DESCRIPTION = f"{action_name.capitalize()} (a very bad idea)"
        ACTION_ALIASES = aliases

        def __init__(self, game, command, actor=None):
            super().__init__(game, actor=actor)
            self.character = self.acting_character(command)

        def check_preconditions(self) -> bool:
            if not _is_holding(self.character, item_name):
                self.parser.fail(f"You don't have any {item_name}.")
                return False
            return True

        def apply_effects(self):
            _take_held(self.character, item_name)
            self.game.emergency_to_graveyard(text)

    _Fail.__name__ = "".join(w.capitalize() for w in action_name.split())
    return _Fail


EatApple = _consume_failstate(
    "eat apple",
    ["eat the apple"],
    "apple",
    "*crunch!* Oh no, those are definitely NOT safe to eat! The world goes "
    "blurry and you collapse.",
)
EatPixieDust = _consume_failstate(
    "eat pixie dust",
    ["eat the pixie dust", "drink pixie dust", "snort pixie dust"],
    "pixie dust",
    "You instantly go into sugar shock and collapse. A hearse is called and you "
    "are taken away for detox.",
)
EatJawbreaker = _consume_failstate(
    "eat jawbreaker",
    ["eat the jawbreaker", "bite jawbreaker"],
    "jawbreaker",
    "You bite down on the prototype jawbreaker and it EXPLODES!",
)
DropJawbreaker = _consume_failstate(
    "drop jawbreaker",
    ["drop the jawbreaker"],
    "jawbreaker",
    "The jawbreaker hits the floor and EXPLODES! (The whiteboard did say not to "
    "drop it.)",
)


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> PumpkinTown:
    L = things.Location

    your_house = L(
        "Your House",
        "You are all alone in your house on Halloween night. You see a trick-or-"
        "treat bag and a pile of boxes on the floor. There's a plastic jack-o'-"
        "lantern filled with Halloween candy by the front door.",
    )
    elm_street = L(
        "Elm Street",
        "You are outside your house on Elm Street. It is late, and all the houses "
        "are dark except for your neighbor's across the street. There is a storm "
        "drain here.",
    )
    main_street = L(
        "Main Street",
        "You are in the center of Pumpkin Town. Exits lead in every direction, and "
        "fortunately there's a signpost here. A bone ladder hangs in midair.",
    )
    factory = L(
        "Yum-Yum Candy Factory",
        "You feel like a kid in... some kind of store. No one seems to be working "
        "today except a prickly security guard sitting outside the candy lab.",
    )
    candy_lab = L(
        "Candy Lab",
        "The lab is full of weird equipment: hydrometers, beakers, Bunsen burners. "
        "You see a jawbreaker and a whiteboard.",
    )
    tentacle_hill = L(
        "Tentacle Hill",
        "You can see all of Pumpkin Town from this hill. There is a normal-looking "
        "house here, with a car parked in the driveway.",
    )
    cauldron_point = L(
        "Cauldron Point",
        "You walk along to a beach by a bubbling lake. A fishy-looking lifeguard "
        "sits in a high wooden chair, and bats fly overhead.",
    )
    swamp = L(
        "Mucky-Muck Swamp",
        "You arrive at the edge of a dark, sinister swamp. Pools of molasses bubble "
        "up and tangled black licorice whips hang from the chocolate trees. Glowing "
        "red eyes watch you from the shadows.",
    )
    tin_shack = L(
        "Tin Shack",
        "You're in a derelict shack. Inside is a table and a bottle of butterscotch.",
    )
    ghost_train = L(
        "Ghost Train",
        "You're on the ghost train platform at Pumpkin Town Station. There's a sign "
        "here, and a vial lying on the ground.",
    )
    funland = L(
        "Funland",
        "You're in the midway of Funland, an old carnival. A circus tent stands "
        "before you, the snack witch is here with her cart, and the ghost train "
        "waits to return you to Pumpkin Town.",
    )
    big_top = L(
        "Inside the Big Top",
        "You stand amid a bustling community of circus freaks, clowns and acrobats. "
        "A shifty carny runs a game of skill and stares blankly at you.",
    )
    graveyard = L(
        "Graveyard",
        "You're in the graveyard, where townsfolk recover from a lack of Halloween "
        "spirit. The night nurse stands beside an open grave. There is a bucket "
        "here, and a cane.",
    )
    forest = L(
        "Forest of Death",
        "Through the gloom you make out a bell tower rising from the trees. Owls "
        "hoot from the shadows and a cold fear grips your soul.",
    )
    cathedral = L(
        "Abandoned Cathedral",
        "You wander through the crumbling cathedral and marvel at its gothic "
        "beauty. A rickety staircase leads up to the bell tower.",
    )
    bell_tower = L(
        "Bell Tower",
        "Leathery wings rustle in the belfry. A bell ringer stands beside a pull "
        "rope.",
    )
    pitchfork_farms = L(
        "Pitchfork Farms",
        "This farm raises candy corn, candy pumpkins, marshmallow chicks and zombie "
        "cows. You hear giggling and screaming to the east.",
    )
    gingerbread_fields = L(
        "Gingerbread Fields",
        "Little gingerbread people frolic in the fields. You see a mineshaft here. "
        "Now and then a bat swoops down and snatches one of them away.",
    )
    sugar_mines = L(
        "Sugar Mines",
        "Zombie miners patrol the twisting tunnels, searching for veins of rock "
        "candy. A passage leads up, and the catacombs lie east.",
    )
    catacombs = L(
        "Creepy Catacombs",
        "A network of tunnels beneath Pumpkin Town. One tunnel has collapsed -- "
        "debris litters the ground. An arched passage leads south into the unknown.",
    )
    hell = L(
        "Pumpkin Town Hell",
        "Little devils with pitchforks dance around gouts of flame to old-time "
        "jazz. It is uncomfortably hot. A large devil in a suit and tie approaches.",
    )

    all_locations = [
        your_house,
        elm_street,
        main_street,
        factory,
        candy_lab,
        tentacle_hill,
        cauldron_point,
        swamp,
        tin_shack,
        ghost_train,
        funland,
        big_top,
        graveyard,
        forest,
        cathedral,
        bell_tower,
        pitchfork_farms,
        gingerbread_fields,
        sugar_mines,
        catacombs,
        hell,
    ]

    # --- exits -------------------------------------------------------------
    _one_way(your_house, "out", elm_street)
    _one_way(elm_street, "home", your_house)
    # The bone ladder (Elm Street <-> Main Street) is travelled via CLIMB LADDER.

    # Main Street's seven spokes. add_connection only auto-reverses the canonical
    # axes (n/s, e/w, u/d, in/out), NOT the diagonals -- so wire every return by
    # hand to match the signpost.
    for direction, back, dest in [
        ("north", "south", cauldron_point),
        ("northwest", "southeast", tentacle_hill),
        ("south", "north", factory),
        ("southeast", "northwest", pitchfork_farms),
        ("southwest", "northeast", swamp),
        ("east", "west", forest),
        ("west", "east", ghost_train),
    ]:
        _one_way(main_street, direction, dest)
        _one_way(dest, back, main_street)

    _one_way(factory, "enter candy lab", candy_lab)
    _one_way(candy_lab, "out", factory)

    # Swamp interior (Tin Shack) is reached via ENTER SWAMP; only the way out is
    # a plain exit.
    _one_way(tin_shack, "out", swamp)

    # Ghost Train -> Funland is BOARD TRAIN / FLY TO FUNLAND; the return is a
    # plain exit.
    _one_way(funland, "east", ghost_train)
    _one_way(funland, "tent", big_top)
    _one_way(big_top, "out", funland)

    forest.add_connection("east", cathedral)  # cathedral west -> forest (gated)
    cathedral.add_connection("east", graveyard)  # graveyard west -> cathedral
    cathedral.add_connection("up", bell_tower)  # bell_tower down -> cathedral
    _one_way(graveyard, "enter grave", catacombs)  # one-way chute down

    pitchfork_farms.add_connection("east", gingerbread_fields)  # fields west -> farms
    gingerbread_fields.add_connection("down", sugar_mines)  # mines up -> fields
    sugar_mines.add_connection("east", catacombs)  # catacombs west -> mines
    catacombs.add_connection("south", hell)  # hell north -> catacombs

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

    def treasure(name, desc, examine, loc, hints=()):
        it = things.Item(name, desc, examine)
        for h in hints:
            it.add_command_hint(h)
        loc.add_item(it)
        return it

    # --- Your House --------------------------------------------------------
    bag = treasure(
        "bag",
        "an empty trick-or-treat bag",
        "An empty trick-or-treat bag. You'll need it to collect treats and score "
        "points.",
        your_house,
        hints=["get bag"],
    )
    scenery(
        "boxes",
        "a pile of costume boxes",
        "The boxes hold Halloween costumes your mom brought down from the attic: a "
        'vintage witch costume (with an old-timey broom), an official "Pirate Bill" '
        'costume (with a wicked hook hand) and an "Action Spooky Ghost Costume." '
        "You may take only one costume.",
        your_house,
        hints=["take ghost costume", "take hook"],
    )
    scenery(
        "jack-o-lantern",
        "a plastic jack-o'-lantern",
        "Inside the plastic pumpkin are individually wrapped pieces of bubble gum.",
        your_house,
        hints=["get bubble gum"],
    )
    treasure(
        "bubble gum",
        "a handful of bubble gum",
        "Individually wrapped pieces of bubble gum.",
        your_house,
        hints=["chew gum"],
    )

    # --- Elm Street --------------------------------------------------------
    scenery(
        "storm drain",
        "a storm drain with a narrow grate",
        "Looking down through the grate you spy the glint of a coin! Your hand is "
        "too big to fit through, though.",
        elm_street,
        hints=["use hook on coin"],
    )

    # --- Candy Lab ---------------------------------------------------------
    treasure(
        "jawbreaker",
        "a baseball-sized jawbreaker",
        "A baseball-sized jawbreaker covered in sparkles and swirls -- the "
        "prototype Exploding Jawbreaker. Do NOT drop it or eat it!",
        candy_lab,
        hints=["get jawbreaker"],
    )
    scenery(
        "whiteboard",
        "a whiteboard",
        'It reads: "Norm, our prototype Yum-Yum Exploding Jawbreaker is ready for '
        'testing. Do not drop it!"',
        candy_lab,
    )

    # --- Tentacle Hill -----------------------------------------------------
    scenery(
        "car",
        "a modern-looking car",
        "Through the window you spy an ID badge hanging from the rearview mirror.",
        tentacle_hill,
        hints=["get id badge", "ring bell"],
    )
    treasure(
        "id badge",
        'an ID badge reading "Norman Johnson, Yum-Yum Marketing"',
        'The ID reads "Norman Johnson, Yum-Yum Marketing."',
        tentacle_hill,
        hints=["show id to guard"],
    )

    # --- Cauldron Point ----------------------------------------------------
    scenery(
        "lake",
        "a huge, bubbling lake",
        "It's actually a huge, bubbling kettle half-buried in the ground. Now and "
        "then a tentacle erupts and plucks a bat from the sky.",
        cauldron_point,
        hints=["enter lake"],
    )

    # --- Swamp -------------------------------------------------------------
    scenery(
        "trees",
        "chocolate trees hung with licorice",
        "Chocolate trees draped with tangled black licorice whips.",
        swamp,
        hints=["get licorice", "get chocolate", "enter swamp"],
    )

    # --- Tin Shack ---------------------------------------------------------
    treasure(
        "butterscotch",
        "a bottle of butterscotch",
        "A half-full (or half-empty) bottle of the good stuff.",
        tin_shack,
        hints=["get butterscotch"],
    )

    # --- Ghost Train -------------------------------------------------------
    treasure(
        "pixie dust",
        "a vial of pixie dust",
        "A vial of sparkly purple, red and gold pixie dust -- 99 percent pure "
        "sugar. Don't eat it!",
        ghost_train,
        hints=["get pixie dust", "board train"],
    )
    scenery(
        "sign",
        "a sign",
        'The sign reads "This way to Funland!" with an arrow pointing west. You\'ll '
        "need to board the ghost train.",
        ghost_train,
    )

    # --- Graveyard ---------------------------------------------------------
    treasure(
        "bucket",
        "an empty bucket",
        "An empty bucket. It looks freshly kicked.",
        graveyard,
        hints=["get bucket", "fill bucket"],
    )
    treasure(
        "candy cane",
        "a peppermint candy cane",
        "A red-and-white-striped peppermint candy cane -- a sturdy hooked stick.",
        graveyard,
        hints=["get candy cane"],
    )
    scenery(
        "grave",
        "an open grave",
        "You look down into the open grave but can't see the bottom! (You could "
        "ENTER GRAVE to slide down to the catacombs.)",
        graveyard,
        hints=["enter grave"],
    )

    # --- Catacombs ---------------------------------------------------------
    scenery(
        "debris",
        "a pile of fallen rocks",
        "Beneath the rubble a twitching hand holds a pickaxe.",
        catacombs,
        hints=["get pickaxe"],
    )
    treasure(
        "pickaxe",
        "a miner's pickaxe",
        "A pickaxe; its former owner doesn't seem to need it anymore.",
        catacombs,
        hints=["get pickaxe", "mine rock candy"],
    )

    # --- Pitchfork Farms ---------------------------------------------------
    scenery(
        "chicks",
        "hopping marshmallow chicks",
        "They hop around and make peeping noises. No use picking up chicks here -- "
        "unless you had a pitchfork.",
        pitchfork_farms,
        hints=["use pitchfork on chicks"],
    )
    scenery(
        "cow",
        "a sickly zombie cow",
        "A cow moos in a sickly fashion and shambles over to be milked.",
        pitchfork_farms,
        hints=["milk cow"],
    )

    # --- Main Street -------------------------------------------------------
    scenery(
        "signpost",
        "a wooden signpost",
        "NORTH: Cauldron Point  NORTHWEST: Tentacle Hill  SOUTH: Yum-Yum Candy "
        "Factory  SOUTHEAST: Pitchfork Farms  SOUTHWEST: Mucky-Muck Swamp  EAST: "
        "Forest of Death  WEST: Ghost Train to Funland",
        main_street,
        hints=["climb ladder"],
    )

    # --- characters --------------------------------------------------------
    guard = things.Character(
        "guard", "a prickly security guard", "I just want to read my paper in peace."
    )
    guard.talk_text = "The guard's green skin is covered in cactus spines. He grunts."
    factory.add_character(guard)

    gill = things.Character(
        "Gill", "a scaly lifeguard named Gill", "S'up, bro? I'm Gill."
    )
    gill.talk_text = "\"S'up, bro? I'm Gill. Watch out for that tentacle.\""
    cauldron_point.add_character(gill)

    snack_witch = things.Character(
        "snack witch", "an old woman selling cotton candy and apples", "Cackle!"
    )
    snack_witch.talk_text = (
        'The snack witch cackles. "Cotton candy? Apples? One coin for the candy, '
        'dearie."'
    )
    funland.add_character(snack_witch)

    carny = things.Character(
        "carny", "a shifty carny in dirty overalls", "Play a game, win a prize."
    )
    carny.talk_text = (
        '"Knock down three bottles with a beanbag, win a prize. Easy as pie."'
    )
    big_top.add_character(carny)

    nurse = things.Character(
        "nurse", "the night nurse, Abby Cadaver", "You're looking positively alive!"
    )
    nurse.talk_text = '"Oh, dear! You\'re looking positively alive! How dreadful!"'
    graveyard.add_character(nurse)

    bell_ringer = things.Character(
        "bell ringer", "a hunched bell ringer", "Is it snack time yet?"
    )
    bell_ringer.talk_text = '"Is it snack time yet?"'
    bell_tower.add_character(bell_ringer)

    devil = things.Character(
        "devil", "a large devil in a suit and tie", "Have you been good this Halloween?"
    )
    devil.talk_text = (
        'The devil holds out a goblet of cinnamon hearts. "Have you been a good '
        'little trick-or-treater?"'
    )
    hell.add_character(devil)

    zombies = things.Character(
        "zombies", "shambling zombie miners", "Mine your own business."
    )
    zombies.talk_text = '"Hey! Mine your own business!"'
    sugar_mines.add_character(zombies)

    player = things.Character(
        "you",
        "a kid out trick-or-treating on Halloween night",
        "I'm a kid out for the best Halloween haul ever.",
    )

    custom_actions = [
        TakeWitchCostume,
        TakePirateCostume,
        TakeGhostCostume,
        TakeHook,
        ChewGum,
        StickGumOnHook,
        UseHookOnCoin,
        GetCoin,
        KnockOnDoor,
        TrickOrTreat,
        RingBell,
        ClimbLadder,
        ShowIdToGuard,
        BoardTrain,
        GiveCoinToConductor,
        FlyToFunland,
        BuyCottonCandy,
        BuyApple,
        ThrowJawbreaker,
        GetLicorice,
        GetChocolate,
        FillBucket,
        EnterSwamp,
        MilkCow,
        PourMolasses,
        MineRockCandy,
        EnterLake,
        MarkTrail,
        TalkToDevil,
        DevilNo,
        DevilYes,
        WhipDevil,
        UsePitchforkOnChicks,
        EatApple,
        EatPixieDust,
        EatJawbreaker,
        DropJawbreaker,
    ]

    game = PumpkinTown(
        your_house,
        player,
        characters=[
            guard,
            gill,
            snack_witch,
            carny,
            nurse,
            bell_ringer,
            devil,
            zombies,
        ],
        custom_actions=custom_actions,
    )

    for loc in all_locations:
        game.locations.setdefault(loc.name, loc)

    # --- blocks ------------------------------------------------------------
    factory.add_block("enter candy lab", GuardBlock(game))
    forest.add_block("east", TrailBlock(forest))

    # --- triggers ----------------------------------------------------------
    game.add_trigger("score_treats", lambda g: True, _score_treats, repeatable=True)

    return game


# ---------------------------------------------------------------------------
# Walkthrough (also the win test) -- wins at 100/100
# ---------------------------------------------------------------------------

WALKTHROUGH = [
    # --- Your House: bag, ghost costume, the hook prop, bubble gum ----------
    "get bag",
    "examine boxes",
    "take ghost costume",
    "take hook",
    "get bubble gum",
    "out",  # -> Elm Street
    # --- Elm Street: fish the coin, trick-or-treat, climb to Pumpkin Town ---
    "examine storm drain",
    "chew gum",
    "stick gum on hook",
    "use hook on coin",  # the Funland coin
    "knock on door",
    "say trick or treat",  # candy corn; the bone ladder drops
    "climb ladder",  # -> Main Street
    # --- Tentacle Hill: cookies (and the ID badge) -------------------------
    "northwest",
    "examine car",
    "get id badge",
    "ring bell",
    "say trick or treat",  # cookies
    "southeast",  # -> Main Street
    # --- Yum-Yum Candy Factory: sneak in as a ghost for the jawbreaker ------
    "south",
    "enter candy lab",  # ghost slips past the guard
    "get jawbreaker",
    "out",
    "north",  # -> Main Street
    # --- Ghost Train -> Funland: pixie dust, cotton candy, circus peanuts ---
    "west",
    "get pixie dust",
    "board train",  # ghost rides free -> Funland (keeps the coin + train bonus)
    "buy cotton candy",
    "tent",  # -> Inside the Big Top
    "throw jawbreaker",  # explodes the bottles -> circus peanuts
    "out",
    "east",  # -> Ghost Train
    "east",  # -> Main Street
    # --- Forest -> Cathedral -> Graveyard: candy cane + bucket -------------
    "east",  # -> Forest of Death
    "mark trail",  # candy corn unlocks the way east
    "east",  # -> Abandoned Cathedral
    "east",  # -> Graveyard
    "get candy cane",
    "get bucket",
    "west",  # -> Cathedral
    "west",  # -> Forest of Death
    "west",  # -> Main Street
    # --- Swamp: licorice, chocolate, molasses, then the Tin Shack ----------
    "southwest",  # -> Mucky-Muck Swamp
    "get licorice",
    "get chocolate",
    "fill bucket",  # bucket of molasses
    "enter swamp",  # candy cane guides you -> Tin Shack
    "get butterscotch",
    "out",  # -> Mucky-Muck Swamp
    "northeast",  # -> Main Street
    # --- Pitchfork Farms -> the underground loop --------------------------
    "southeast",  # -> Pitchfork Farms
    "east",  # -> Gingerbread Fields
    "pour molasses",  # snares a gingerbread person
    "down",  # -> Sugar Mines
    "east",  # -> Creepy Catacombs
    "get pickaxe",
    "south",  # -> Pumpkin Town Hell
    "talk to devil",
    "no",  # cinnamon hearts (and you're not kicked out)
    "whip devil",  # he drops his pitchfork
    "get pitchfork",
    "north",  # -> Creepy Catacombs
    "west",  # -> Sugar Mines
    "mine rock candy",
    "up",  # -> Gingerbread Fields
    "west",  # -> Pitchfork Farms
    "use pitchfork on chicks",  # marshmallow chicks
    "northwest",  # -> Main Street
    # --- Cauldron Point: gummi worms (the pitchfork fends off the tentacle) -
    "north",  # -> Cauldron Point
    "enter lake",  # gummi worms
    "south",  # -> Main Street
    # --- Climb the bone ladder home ---------------------------------------
    "climb ladder",  # +5 return, +15 bonuses -> WIN at 100/100
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
