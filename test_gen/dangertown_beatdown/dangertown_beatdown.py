"""Dangertown Beatdown -- a Parsely game ported to the text_adventure_games engine.

It's 1987 in Santa Morena. Detective Jack Slade wakes to a threatening phone
message: crime boss "Boss D" has kidnapped his partner, Jetta Chang, and wants
the audiotape that proves the mayor is on the take. You play Slade across the
neon-soaked city -- refusing a bribe, working contacts at a strip club and a gang
arcade, lifting the tape from the police evidence locker -- until a warehouse
ambush gets Slade shot. The story then **switches protagonists**: you become
rookie detective Jetta Chang, save Slade, gear up, and take down Boss D in his
penthouse. Source: Parsely "Dangertown Beatdown" (pages 85-115).

Authored the way the reference ports are (see ``action_castle_2.py`` and
``docs/converting-parsely-games.md``): a ``build_game()`` that assembles the
world, a small ``DangertownBeatdown`` Game subclass holding the win/score logic,
the protagonist switch, and the arrival set-pieces; the two-object verbs via the
engine's ``use_item_on`` factory; the city's motorcycle/Porsche overworld via the
engine's vehicle/mount feature (``Item.make_vehicle`` + ``blocks.RequiresVehicle``);
and custom ``Action`` subclasses for the genuinely novel verbs.

Two interpretations worth flagging (the source's two-page map separates them; the
gameplay is identical either way):

* The red-light "Gaslight District" riding hub (page 92) is folded into Southside
  (page 91) -- they are the same place, on foot vs. on the bike -- so the bike
  overworld reuses the engine's vehicle feature uniformly instead of teleporting
  between two names. You ride the bike between districts and must PARK to enter a
  building (the book's "cannot enter a location while on the bike").
* "Finishing without saving" (+5, page 115) is read as the completion bonus the
  Parsely books give for finishing the game (cf. Blackboard Jungle), awarded on
  the winning arrest.

Run interactively:    uv run python -m test_gen.dangertown_beatdown.dangertown_beatdown
Run the walkthrough:  uv run python -m test_gen.dangertown_beatdown.dangertown_beatdown --walk
"""

import re

from text_adventure_games import games, things, actions, blocks

# ---------------------------------------------------------------------------
# Helpers (mirroring the reference ports' kit). "Held" = inventory + worn +
# wielded + the contents of any OPEN container the character is carrying, so a
# quest check sees the $100 bill even while it sits in the wallet you pocketed.
# ---------------------------------------------------------------------------


def _all_held(character):
    held = {**character.inventory, **character.worn, **character.wielded}
    for store in (character.inventory, character.worn, character.wielded):
        for it in list(store.values()):
            if it.get_property("is_container") and not it.get_property("is_closed"):
                held.update(it.contents)
    return held


def _is_holding(character, name):
    return name in _all_held(character)


def _take_held(character, name):
    """Remove and return a held item by name from wherever it lives, else None."""
    for store in (character.inventory, character.worn, character.wielded):
        if name in store:
            return store.pop(name)
    for store in (character.inventory, character.worn, character.wielded):
        for it in list(store.values()):
            if it.get_property("is_container") and name in it.contents:
                found = it.contents[name]
                it.remove_item(found)
                return found
    return None


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s canonical auto-reverse, so a
    named exit ("enter cafe") doesn't silently wire a colliding reverse. (See the
    same helper in action_castle_2.py.)"""
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


class ParkedOnly(blocks.Block):
    """A building you can only walk into: blocked while anyone present is riding
    (the book's "cannot enter a location while on the bike")."""

    def __init__(self, location, description="Park your ride first."):
        super().__init__("Park first", description)
        self.location = location

    def is_blocked(self) -> bool:
        return any(
            getattr(c, "riding", None) is not None
            for c in self.location.characters.values()
        )


class GateBlock(blocks.Block):
    """A building entrance gated both on being parked (on foot) and on a
    game-state predicate -- ``predicate(game)`` is True when the way is open."""

    def __init__(self, location, game, predicate, description):
        super().__init__("The way is shut", description)
        self.location = location
        self.game = game
        self.predicate = predicate

    def is_blocked(self) -> bool:
        if any(
            getattr(c, "riding", None) is not None
            for c in self.location.characters.values()
        ):
            return True
        return not self.predicate(self.game)


class FlagBlock(blocks.Block):
    """Generic exit gate: passable when ``predicate(game)`` is True."""

    def __init__(self, game, predicate, description):
        super().__init__("The way is shut", description)
        self.game = game
        self.predicate = predicate

    def is_blocked(self) -> bool:
        return not self.predicate(self.game)


# ---------------------------------------------------------------------------
# A tiny factory for one-shot custom verbs (the same spirit as use_item_on):
# an optional room gate, an optional `requires` predicate, an effect, a fixed
# success line, and an optional scoring award.
# ---------------------------------------------------------------------------


def _verb(
    name,
    *,
    room=None,
    requires=None,
    effect=None,
    success=None,
    award=None,
    aliases=None,
    description=None,
):
    """Build an Action subclass for one custom verb.

    requires(action) -> error string (blocks) or None (allows).
    effect(action)   -> mutate the world (may narrate itself).
    success          -> a fixed line narrated after effect + award.
    award            -> (key, points) or (key, points, msg) for game.award.
    """

    class _V(actions.Action):
        ACTION_NAME = name
        # Leave the description empty unless given one -- echoing the command
        # name back as its own "description" just clutters the HELP list.
        ACTION_DESCRIPTION = description or ""
        ACTION_ALIASES = list(aliases or [])

        def __init__(self, game, command, actor=None):
            super().__init__(game, actor=actor)
            self.character = self.acting_character(command)

        def check_preconditions(self) -> bool:
            if room is not None and self.character.location.name != room:
                self.parser.fail("You can't do that here.")
                return False
            if requires is not None:
                err = requires(self)
                if err:
                    self.parser.fail(err)
                    return False
            return True

        def apply_effects(self):
            if effect is not None:
                effect(self)
            if award is not None:
                self.game.award(*award)
            if success is not None:
                self.parser.ok(success)

    _V.__name__ = "".join(w.capitalize() for w in re.split(r"[^a-z0-9]+", name) if w)
    return _V


# ---------------------------------------------------------------------------
# Game subclass: win/score, the protagonist switch, and arrival set-pieces
# ---------------------------------------------------------------------------


class DangertownBeatdown(games.Game):
    """Won by arresting Boss D in the penthouse (the +5 "good cop" ending). The
    kill-Boss-D ending scores +0 and ends the game without a win; every other
    THE END (the bribe, the deaths) is a loss."""

    _SAVE_SLADE_DEADLINE = 8  # turns to reach the ambulance before Slade bleeds out

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        self.max_score = 100  # Slade 65 + Chang 35 (page 115)
        # --- narrative flags (kept on the GAME, not the player -- the player
        # object is swapped at the protagonist switch) -------------------------
        self.coffee_made = False
        self.rocco_at_door = False
        self.rocco_ko = False
        self.fight_pending = False
        self._fight_warned = False
        self.cat_present = False
        self.knows_boss_location = False
        self.knows_warehouse = False
        self.bleeding = False
        self.cutter_down = False
        self.coffee_served = False
        self.obrien_left = False
        self.box_found = False
        self.tape_taken = False
        self._locker_warned = False
        self.tires_slashed = False
        self.jetta_freed = False
        self.rocco_confront = False
        self.given_tape = False
        self.is_chang = False  # True once you become Jetta Chang
        self.goon_threat = False
        self._goon_warned = False
        self.goon_down = False
        self.slade_aboard = False
        self.called_911 = False
        self.slade_saved = False
        self._save_deadline = None
        self.showed_badge = False
        self.rocco_elevator_threat = False
        self._elevator_warned = False
        self.rocco_defeated = False
        self.thumb_scanned = False
        self.boss_searched = False
        self.arrested_boss = False
        # "search X" reveals loot on the floor (you then TAKE it); these guard
        # against re-searching the same body.
        self.man_searched = False
        self.goon_searched = False
        self.rocco_searched = False
        self.box_taken = False
        # references resolved in build_game()
        self.slade = None
        self.jetta = None

    # -- the protagonist switch (pages 106-107) -----------------------------

    def switch_to_chang(self):
        """The big goon shoots Slade; you become rookie detective Jetta Chang,
        who was the woman tied to the chair. Knockout (the masked vigilante) drops
        in, and a goon swings his SMG toward you both."""
        warehouse = self.locations["Warehouse"]
        slade = self.player
        slade.set_property("is_shot", True)
        slade.set_property("gettable", False)
        # Slade stays behind as a wounded, idle NPC (no behavior -> no turn).
        self.add_character(slade)
        if slade.name not in warehouse.characters:
            warehouse.add_character(slade)
        # Become Jetta (already present as the freed captive).
        self.player = self.jetta
        self.is_chang = True
        if self.jetta.location is not warehouse:
            self.relocate(self.jetta, warehouse)
        # Spawn the goon and Knockout for the fight.
        goon = self.characters.get("goon")
        if goon is not None and goon.location is None:
            warehouse.add_character(goon)
        knockout = self.characters.get("Knockout")
        if knockout is not None and knockout.location is None:
            warehouse.add_character(knockout)
        self.goon_threat = True
        self.parser.ok(
            "Whether you run, fight or negotiate, the big goon shoots Slade in "
            "the stomach. You watch with horror as Jack drops to the floor.\n\n"
            "You are now rookie detective JETTA CHANG. A masked girl -- Knockout "
            "-- drops from a shipping container and decks a goon, but another "
            "raises his SMG to waste you both. (ATTACK GOON.)"
        )

    # -- arrival set-pieces -------------------------------------------------

    def do_command(self, command: str) -> bool:
        cmd = (command or "").strip().lower()
        loc = self.player.location

        # Leaving the arcade: Cutter blocks your way and slashes your cheek the
        # first time (page 96). You don't move -- you have to deal with him.
        if (
            loc is not None
            and loc.name == "Arcade"
            and not self.cutter_down
            and cmd in ("out", "go out", "leave", "exit")
        ):
            self.bleeding = True
            self.parser.ok(
                'As you turn to leave, Cutter gets in your face. "Snitches get '
                'stitches." He flicks open his switchblade and slashes your '
                "cheek, drawing blood. He's fast, but he's left himself open. "
                "(HIT CUTTER WITH BAT.)"
            )
            self.end_turn()
            return True

        before = self.player.location
        success = super().do_command(command)
        after = self.player.location
        if success and after is not None and after is not before:
            if after.name == "Downtown":
                self._arrive_downtown()
            elif after.name == "Elevator":
                self._arrive_elevator()
        return success

    def _arrive_downtown(self):
        """Driving the wounded Slade to Downtown after calling it in delivers him
        to the waiting ambulance (page 100/108)."""
        if (
            self.is_chang
            and self.slade_aboard
            and self.called_911
            and not self.slade_saved
            and self.player.riding is not None
        ):
            self.slade_saved = True
            self.slade_aboard = False
            self._save_deadline = None
            slade = self.slade
            if slade.location is not None and slade.name in slade.location.characters:
                slade.location.remove_character(slade)
            self.award(
                "save_slade",
                5,
                "An ambulance is waiting. The paramedics load Slade inside and "
                "rush him to the hospital. You may have just saved his life.",
            )

    def _arrive_elevator(self):
        """The elevator doors open on a very surprised Rocco Falcone, who reaches
        into his jacket (page 110)."""
        if not self.rocco_defeated and not self.rocco_elevator_threat:
            self.rocco_elevator_threat = True
            self.parser.ok(
                "The doors open on a very surprised Rocco Falcone. He mutters a "
                "colorful expression and reaches inside his jacket. (SHOOT ROCCO "
                "or PUNCH ROCCO -- fast!)"
            )

    # -- win ----------------------------------------------------------------

    def is_won(self) -> bool:
        return bool(self.arrested_boss)


# ---------------------------------------------------------------------------
# Two-object verbs (the engine's use_item_on factory)
# ---------------------------------------------------------------------------


def _give_matchbook(action):
    action.game.cat_present  # (cat must be present -- gated in requires)
    action.game.knows_boss_location = True


GiveMatchbookToCat = actions.use_item_on(
    "give matchbook to cat",
    item="matchbook",
    target="cat",
    verb="give",
    preposition="to",
    description="Give Cat Marco the matchbook to write on",
    aliases=["give cat the matchbook", "show matchbook to cat"],
    effect=_give_matchbook,
    award=(
        "boss_location",
        5,
        'Cat writes an address on the matchbook: "Pacific Towers, Morena Beach." '
        '"He hired some girls for a party -- bankers, lawyers, politicians."',
    ),
    requires=lambda a: (
        None if a.game.cat_present else "There's no one here to give it to."
    ),
    item_missing="You don't have a matchbook.",
    target_missing="Cat Marco isn't here.",
)


def _give_donuts(action):
    """O'Brien wanders off for coffee, leaving his key ring and the case file."""
    g = action.game
    g.obrien_left = True
    station = g.locations["Police Station"]
    ring = things.Item(
        "key ring",
        "Sergeant O'Brien's key ring",
        "You find the evidence locker's padlock key on the ring, among others.",
    )
    ring.add_command_hint("get key ring")
    ring.add_command_hint("enter evidence locker")
    station.add_item(ring)
    case_file = things.Item(
        "case file", "a case file", "The case file number is #198X."
    )
    case_file.set_property("gettable", False)
    station.add_item(case_file)
    obrien = g.characters.get("o'brien")
    if obrien is not None and obrien.name in station.characters:
        station.remove_character(obrien)


GiveObrienDonuts = actions.use_item_on(
    "give o'brien donuts",
    item="donuts",
    target="o'brien",
    verb="give",
    preposition="to",
    description="Give Sergeant O'Brien the box of donuts",
    aliases=[
        "give donuts to o'brien",
        "give obrien donuts",
        "give donuts to obrien",
        "give o'brien the donuts",
        "give the donuts to o'brien",
    ],
    effect=_give_donuts,
    award=(
        "donuts",
        5,
        "\"Slade, you're all right. I'll go grab us some coffee. Sit tight.\" He "
        "stands and exits, leaving behind his keys and the case file.",
    ),
    requires=lambda a: (
        None
        if a.character.location.name == "Police Station" and not a.game.obrien_left
        else "O'Brien isn't here."
    ),
    item_missing="You don't have any donuts.",
    target_missing="O'Brien isn't here.",
)


def _use_key_on_porsche(action):
    """Unlock the Porsche, load Slade into the passenger seat, and climb in --
    you're now driving it (riding). Unlocking also flips the car to a ready
    vehicle, so PARK / GET ON work on it afterward like any ride. If you slashed
    the tires earlier, the getaway is doomed and Slade bleeds out (page 105)."""
    g = action.game
    porsche = action.target  # the matched Porsche item
    if g.tires_slashed:
        g.end_in_death(
            "The tires you slashed are flat -- the car isn't going anywhere. "
            "Slade bleeds out before help arrives. THE END."
        )
        return
    porsche.set_property("is_locked", False)
    porsche.set_property("vehicle_ready", True)
    action.character.riding = porsche
    if g.slade_saved:
        # Slade's already at the hospital -- this is just getting back behind
        # the wheel.
        g.parser.ok("You slide back into the driver's seat of the Porsche.")
        return
    if g.slade_aboard:
        g.parser.ok(
            "You're already behind the wheel, Slade slumped beside you. "
            "(CALL 911, then DRIVE TO DOWNTOWN.)"
        )
        return
    g.slade_aboard = True
    g._save_deadline = g.turn + DangertownBeatdown._SAVE_SLADE_DEADLINE
    g.parser.ok(
        "You unlock the car and manage to get Slade into the passenger seat. "
        "There's a car phone here. (CALL 911, then DRIVE TO DOWNTOWN.)"
    )


UseKeyOnPorsche = actions.use_item_on(
    "use key on porsche",
    item="porsche keys",
    target="porsche",
    verb="use",
    preposition="on",
    description="Unlock the Porsche with the keys you took off the goon",
    aliases=["use porsche keys on porsche", "unlock porsche", "use keys on porsche"],
    effect=_use_key_on_porsche,
    success=None,  # narrated by the effect (the success line, or the bleed-out)
    item_missing="You don't have the Porsche keys.",
    target_missing="There's no Porsche here.",
)


# ---------------------------------------------------------------------------
# Custom verbs -- Act 1 (Jack Slade)
# ---------------------------------------------------------------------------


def _man_here(a):
    return a.game.rocco_at_door and not a.game.rocco_ko


PlayMessage = _verb(
    "play message",
    room="Bedroom",
    aliases=["play the message", "play answering machine", "press play"],
    effect=lambda a: None,
    award=(
        "msg",
        5,
        "A voice says, \"Slade, you're gonna pay for shutting down our "
        'operation. We have your partner. Bring us the tape. Come alone."',
    ),
)


def _make_coffee(a):
    a.game.coffee_made = True


MakeCoffee = _verb(
    "make coffee",
    room="Apartment",
    aliases=["brew coffee", "fill the kettle"],
    requires=lambda a: "You already made coffee." if a.game.coffee_made else None,
    effect=_make_coffee,
    success="You perform the sacred ritual: fill the kettle, set it on the stove and wait.",
)


def _read_newspaper(a):
    """Reading the headlines after making coffee brings Rocco to the door
    (page 89). He kicks it in and blocks the way out until you deal with him."""
    g = a.game
    g.parser.ok(
        "Violent crime is up eight percent in Santa Morena. The mayor is pushing "
        "another waterfront deal, and some masked weirdo is beating up muggers."
    )
    if g.coffee_made and not g.rocco_at_door:
        g.rocco_at_door = True
        apartment = g.locations["Apartment"]
        man = g.characters.get("man")
        if man is not None:
            apartment.add_character(man)
        g.parser.ok(
            'Someone knocks. "Slade. Open up." He kicks in the door and enters, '
            "blocking the exit -- a large man in a suit with a baseball bat. "
            "(TALK TO MAN.)"
        )


ReadNewspaper = _verb(
    "read newspaper",
    room="Apartment",
    aliases=["read the newspaper", "read paper", "read headlines"],
    requires=lambda a: (
        None
        if a.game.coffee_made
        else "Coffee first. You can't read a word without it."
    ),
    effect=_read_newspaper,
    award=("newspaper", 5),
)


def _say_yes(a):
    a.game.end_in_death(
        "You feel sick to your stomach as you pocket the cash. Is this how you "
        "thought you'd end up -- just another cop on the take? This is why the "
        "bad guys always win. THE END."
    )


SayYes = _verb(
    "say yes",
    requires=lambda a: None if _man_here(a) else "There's no offer on the table.",
    effect=_say_yes,
    aliases=["take the bribe", "accept the bribe"],
)


def _take_envelope(a):
    """TAKE ENVELOPE/CASH (page 89-90). Before the fight it's the bribe prompt;
    after you've knocked Rocco out it's blood money you leave behind."""
    g = a.game
    if g.rocco_ko:
        g.parser.ok(
            "It's tempting, but it's blood money. When this goon wakes up, he'll "
            "take it back to his boss -- a clear message that you can't be bought. "
            "You leave it."
        )
    else:
        g.parser.ok("That's about six months' pay. Are you sure? (SAY YES or SAY NO.)")


TakeEnvelope = _verb(
    "take envelope",
    room="Apartment",
    requires=lambda a: (
        None
        if (a.game.rocco_at_door or a.game.rocco_ko)
        else "There's no envelope here."
    ),
    effect=_take_envelope,
    aliases=["take the envelope", "take cash", "take the cash", "get envelope"],
)


def _say_no(a):
    g = a.game
    g.fight_pending = True
    g.parser.ok(
        '"Figured you might turn us down." He shoulders the baseball bat: "Since '
        "the carrot ain't working, let's try the stick.\" The kettle starts "
        "whistling... (HIT MAN WITH KETTLE.)"
    )


SayNo = _verb(
    "say no",
    requires=lambda a: None if _man_here(a) else "There's no offer on the table.",
    effect=_say_no,
    award=("refuse_bribe", 5),
    aliases=["refuse", "refuse the bribe", "reject the bribe"],
)


def _hit_kettle(a):
    g = a.game
    g.rocco_ko = True
    g.fight_pending = False
    apartment = g.locations["Apartment"]
    bat = things.Item("bat", "a baseball bat", "A solid wooden Louisville Slugger.")
    bat.add_command_hint("get bat")
    apartment.add_item(bat)


HitManWithKettle = _verb(
    "hit man with kettle",
    requires=lambda a: (
        None
        if _man_here(a)
        else ("He's already out cold." if a.game.rocco_ko else "There's no one to hit.")
    ),
    effect=_hit_kettle,
    award=(
        "kettle_ko",
        5,
        "You grab the hot kettle and smash it into the gangster's skull. He "
        "collapses, dropping the baseball bat.",
    ),
    aliases=[
        "smash man with kettle",
        "hit gangster with kettle",
        "hit the man with the kettle",
    ],
)


HitManWithBat = _verb(
    "hit man with bat",
    requires=lambda a: (
        "He's already knocked out. You may be suspended, but you're still a good cop."
        if a.game.rocco_ko
        else "You don't have a bat -- and bare-handed, he'll bash you to a bloody pulp."
    ),
    effect=lambda a: None,
    aliases=["hit gangster with bat", "hit the man with the bat"],
)


def _search_man(a):
    """Turn out the KO'd gangster's pockets -- the loot lands on the floor for
    you to TAKE (matchbook, and a wallet holding the $100 bill + license)."""
    g = a.game
    room = a.character.location
    matchbook = things.Item(
        "matchbook",
        "a matchbook",
        'A snarling tiger logo above the name "TIGER\'z DEN."',
    )
    matchbook.add_command_hint("get matchbook")
    matchbook.add_command_hint("give matchbook to cat")
    room.add_item(matchbook)
    wallet = things.Item(
        "wallet",
        "a leather wallet",
        "It holds a $100 bill and a California driver's license.",
    )
    wallet.make_container()
    wallet.set_property("contents_visible", True)
    wallet.add_command_hint("get wallet")
    bill = things.Item(
        "$100 bill", "a crisp $100 bill", "A hundred bucks of blood money."
    )
    bill.add_command_hint("tip dancers")
    license_ = things.Item(
        "license",
        "a driver's license",
        "The well-dressed thug's name is Rocco Falcone.",
    )
    wallet.add_item(bill)
    wallet.add_item(license_)
    room.add_item(wallet)
    g.man_searched = True


SearchMan = _verb(
    "search man",
    requires=lambda a: (
        "You already turned out his pockets."
        if a.game.man_searched
        else (
            None
            if a.game.rocco_ko and a.character.location.name == "Apartment"
            else "There's no one to search."
        )
    ),
    effect=_search_man,
    success=(
        "You search his pockets: an empty matchbook and a wallet fall to the "
        "floor. (GET MATCHBOOK, GET WALLET.)"
    ),
    aliases=["search the man", "search gangster", "search rocco", "frisk man"],
)


def _tip_dancers(a):
    g = a.game
    _take_held(a.character, "$100 bill")
    g.cat_present = True
    waitress = g.characters.get("cat")
    club = g.locations["Strip Club"]
    if waitress is not None and waitress.name not in club.characters:
        club.add_character(waitress)


TipDancers = _verb(
    "tip dancers",
    room="Strip Club",
    requires=lambda a: (
        None
        if _is_holding(a.character, "$100 bill")
        else "You've got nothing to tip with."
    ),
    effect=_tip_dancers,
    award=(
        "tip",
        5,
        "A dancer slips the $100 bill into her G-string. Like magic, the club's "
        "lone waitress appears -- it's your ex, Cat Marco.",
    ),
    aliases=["tip the dancers", "tip dancer"],
)


UsePhone = _verb(
    "use phone",
    room="North End",
    aliases=["use the phone", "use pay phone", "use quarter on phone", "make a call"],
    effect=lambda a: None,
    success="No dial tone -- out of order. You hear the coin drop into the change slot.",
)


def _put_quarter(a):
    g = a.game
    _take_held(a.character, "quarter")
    g.knows_warehouse = True


PutQuarterOnMachine = _verb(
    "put quarter on machine",
    room="Arcade",
    requires=lambda a: (
        None if _is_holding(a.character, "quarter") else "You need a quarter to play."
    ),
    effect=_put_quarter,
    award=(
        "warehouse_num",
        5,
        'Rabbit starts a two-player game and leans in close. "Boss D has your '
        "partner holed up at the Harbor View docks, loading bay #23. You didn't "
        'hear it from me." She wipes the floor with you. "Better luck next time."',
    ),
    aliases=["put quarter in machine", "play machine", "play game with rabbit"],
)


def _hit_cutter(a):
    g = a.game
    g.cutter_down = True
    arcade = g.locations["Arcade"]
    blade = things.Item(
        "switchblade",
        "Cutter's switchblade",
        "A wicked little blade -- sharp enough to cut zip ties.",
    )
    blade.add_command_hint("take switchblade")
    arcade.add_item(blade)


HitCutterWithBat = _verb(
    "hit cutter with bat",
    room="Arcade",
    requires=lambda a: (
        "You don't have a bat."
        if not _is_holding(a.character, "bat")
        else ("Cutter's already down." if a.game.cutter_down else None)
    ),
    effect=_hit_cutter,
    award=(
        "beat_cutter",
        5,
        "You hear his collarbone snap and he goes down, dropping his switchblade. "
        "Rabbit whispers, \"This isn't your fight. Go find Gheorghe. He'll fix you up.\"",
    ),
    aliases=[
        "hit cutter",
        "attack cutter",
        "beat up cutter",
        "hit cutter with the bat",
    ],
)


def _ask_gheorghe(a):
    a.game.bleeding = False


AskGheorgheForHelp = _verb(
    "ask gheorghe for help",
    room="Gheorghe's Gym",
    effect=_ask_gheorghe,
    award=(
        "patched",
        5,
        "Gheorghe gets out a first aid kit, cleans the wound and stitches it "
        'closed. "This will leave scar, but the way you look, it will be '
        'improvement, no?"',
    ),
    aliases=["ask gheorghe for stitches", "get patched up", "ask for help"],
)


def _order_usual(a):
    a.game.coffee_served = True


OrderTheUsual = _verb(
    "order the usual",
    room="Pixel City Cafe",
    effect=_order_usual,
    success="You sit at the counter and Marge pours you a fresh cup of hot coffee.",
    aliases=["order coffee", "order usual", "order the usual coffee"],
)


DrinkCoffee = _verb(
    "drink coffee",
    room="Pixel City Cafe",
    requires=lambda a: None if a.game.coffee_served else "Order it first.",
    effect=lambda a: None,
    award=(
        "coffee",
        5,
        "You feel better -- almost like you could single-handedly take on the Mob, "
        "rescue your partner and clean up organized crime in Santa Morena.",
    ),
    aliases=["drink the coffee", "drink my coffee"],
)


FindBox = _verb(
    "find box",
    room="Evidence Locker",
    requires=lambda a: "You already found it." if a.game.box_found else None,
    effect=lambda a: setattr(a.game, "box_found", True),
    success=(
        "You find box #198X: documents, surveillance photos and a spool of "
        "reel-to-reel audiotape. (TAKE AUDIOTAPE.)"
    ),
    aliases=["find box #198x", "find the box", "search boxes", "find box 198x"],
)


TakeBox = _verb(
    "take box",
    room="Evidence Locker",
    requires=lambda a: None if a.game.box_found else "You haven't found a box yet.",
    effect=lambda a: None,
    success="Carrying the entire box out would be too conspicuous. (TAKE AUDIOTAPE.)",
    aliases=["take box #198x", "take the box", "take box 198x"],
)


def _take_audiotape(a):
    g = a.game
    tape = things.Item(
        "audiotape", "a reel of audiotape", "The tape that links Boss D to the mayor."
    )
    tape.add_command_hint("give tape")
    a.character.add_to_inventory(tape)
    g.tape_taken = True
    g.parser.ok(
        "You hear footsteps approaching down the hall... better return the keys."
    )


TakeAudiotape = _verb(
    "take audiotape",
    room="Evidence Locker",
    requires=lambda a: (
        None
        if a.game.box_found and not a.game.tape_taken
        else ("You already took it." if a.game.tape_taken else "Find the box first.")
    ),
    effect=_take_audiotape,
    award=("audiotape", 5),
    aliases=["take the audiotape", "take tape", "take reel", "get audiotape"],
)


def _return_keys(a):
    _take_held(a.character, "key ring")


ReturnKeys = _verb(
    "return keys",
    room="Police Station",
    requires=lambda a: (
        None if _is_holding(a.character, "key ring") else "You don't have the keys."
    ),
    effect=_return_keys,
    success="You set O'Brien's key ring back on the sergeant's desk. No harm, no foul.",
    aliases=["return key ring", "return the keys", "put keys on desk"],
)


SlashTires = _verb(
    "slash tires",
    room="Harbor View",
    effect=lambda a: setattr(a.game, "tires_slashed", True),
    success="You slash the tires of the flashy sports cars. That'll show 'em. (Probably a bad idea.)",
    aliases=["slash the tires", "cut tires"],
)


FindBay = _verb(
    "find bay",
    room="Harbor View",
    requires=lambda a: (
        None
        if a.game.knows_warehouse
        else "Hours of numbered bays. You'd need to know which one."
    ),
    effect=lambda a: None,
    success="Bay #23 -- yeah, you see it. Just a few doors down from the cars. (ENTER BAY #23.)",
    aliases=["find bay #23", "find bay 23", "find the bay"],
)


def _free_jetta(a):
    g = a.game
    g.jetta_freed = True
    g.rocco_confront = True
    g.parser.ok(
        "You cut through her restraints. Rocco emerges from the shadows, flanked "
        'by armed goons. "Slade. Give us the tape and we let you walk out of '
        'here." (GIVE TAPE.)'
    )


FreeJettaChang = _verb(
    "free jetta chang",
    room="Warehouse",
    requires=lambda a: (
        "You already freed her."
        if a.game.jetta_freed
        else (
            None
            if _is_holding(a.character, "switchblade")
            else "Her restraints won't budge -- you need something sharp."
        )
    ),
    effect=_free_jetta,
    award=("free_jetta", 5),
    aliases=["free jetta", "cut jetta loose", "free chang", "untie jetta"],
)


def _give_tape(a):
    g = a.game
    _take_held(a.character, "audiotape")
    g.given_tape = True
    g.parser.ok(
        'You hand over the tape. Rocco starts to walk away, then stops. "I lied. '
        "Kill 'em both.\""
    )
    g.switch_to_chang()


GiveTape = _verb(
    "give tape",
    room="Warehouse",
    requires=lambda a: (
        None
        if a.game.rocco_confront and _is_holding(a.character, "audiotape")
        else (
            "There's no one demanding it."
            if not a.game.rocco_confront
            else "You don't have the tape."
        )
    ),
    effect=_give_tape,
    aliases=[
        "give the tape",
        "hand over tape",
        "give rocco the tape",
        "give tape to rocco",
    ],
)


# ---------------------------------------------------------------------------
# Custom verbs -- Act 2 (Jetta Chang)
# ---------------------------------------------------------------------------


def _attack_goon(a):
    g = a.game
    g.goon_threat = False
    g.goon_down = True


AttackGoon = _verb(
    "attack goon",
    requires=lambda a: None if a.game.goon_threat else "There's no one to fight.",
    effect=_attack_goon,
    award=(
        "help_knockout",
        5,
        "You spin-kick the goon with the Fu Manchu mustache. He goes down like a "
        "sack of bricks. Knockout nods at you.",
    ),
    aliases=["attack the goon", "kick goon", "fight goon", "hit goon", "help knockout"],
)


def _search_goon(a):
    room = a.character.location
    candy = things.Item("candy bar", "a half-eaten candy bar", "Goon food.")
    candy.add_command_hint("get candy bar")
    keys = things.Item(
        "porsche keys", "keys to a Porsche", "Keys to a white Porsche 911."
    )
    keys.add_command_hint("get porsche keys")
    keys.add_command_hint("use key on porsche")
    room.add_item(candy)
    room.add_item(keys)
    a.game.goon_searched = True


SearchGoon = _verb(
    "search goon",
    requires=lambda a: (
        "You already searched him."
        if a.game.goon_searched
        else (None if a.game.goon_down else "Take him out first.")
    ),
    effect=_search_goon,
    success=(
        "You find a half-eaten candy bar and keys to a Porsche. " "(GET PORSCHE KEYS.)"
    ),
    aliases=["search the goon", "frisk goon"],
)


def _drag_slade(a):
    g = a.game
    harbor = g.locations["Harbor View"]
    g.relocate(g.player, harbor)
    slade = g.slade
    if slade.location is not None and slade.name in slade.location.characters:
        slade.location.remove_character(slade)
    harbor.add_character(slade)
    # Reveal the Porsche (and Slade's parked Kawasaki) in the lot.
    if "porsche" not in harbor.items:
        porsche = things.Item(
            "porsche",
            "a white Porsche 911",
            "A flashy getaway car. There's a car phone inside.",
        )
        porsche.set_property("gettable", False)
        porsche.set_property("is_locked", True)
        porsche.make_vehicle(ready=False)
        porsche.set_property(
            "mount_refusal_message", "It's locked. (USE KEY ON PORSCHE.)"
        )
        porsche.add_command_hint("use key on porsche")
        harbor.add_item(porsche)


DragSladeOut = _verb(
    "drag slade out",
    room="Warehouse",
    requires=lambda a: None if a.game.goon_down else "Deal with the goon first.",
    effect=_drag_slade,
    success=(
        "You drag Slade out from Bay #23 into the parking lot. There you find his "
        "precious Kawasaki and a white Porsche 911. (USE KEY ON PORSCHE.)"
    ),
    aliases=["drag slade", "drag jack out", "carry slade out", "drag slade outside"],
)


def _enter_porsche(a):
    porsche = a.game.locations["Harbor View"].items.get("porsche")
    if porsche is None:
        porsche = a.character.location.items.get("porsche")
    a.character.riding = porsche


EnterPorsche = _verb(
    "enter porsche",
    requires=lambda a: (
        None
        if _is_holding(a.character, "porsche keys")
        and (a.character.location.items.get("porsche") is not None)
        else (
            "There's no Porsche here."
            if a.character.location.items.get("porsche") is None
            else "It's locked -- you need the keys."
        )
    ),
    effect=_enter_porsche,
    success="You drop into the driver's seat of the Porsche.",
    aliases=[
        "get in porsche",
        "get in the porsche",
        "enter the porsche",
        "drive porsche",
    ],
)


Call911 = _verb(
    "call 911",
    requires=lambda a: (
        None
        if a.character.riding is not None and a.game.slade_aboard
        else "There's no phone in reach."
    ),
    effect=lambda a: setattr(a.game, "called_911", True),
    success=(
        'The dispatcher puts you through to the desk sergeant. "Get back downtown '
        "as soon as you can. We'll have an ambulance ready and waiting.\" "
        "(DRIVE TO DOWNTOWN.)"
    ),
    aliases=[
        "call police station",
        "call police",
        "call for help",
        "call 9-1-1",
        "use car phone",
    ],
)


def _show_badge(a):
    a.game.showed_badge = True


ShowBadge = _verb(
    "show badge",
    room="Morena Beach",
    requires=lambda a: (
        None if _is_holding(a.character, "badge") else "You don't have a badge to show."
    ),
    effect=_show_badge,
    success="The guards let you pass. The man at the front desk picks up a phone and makes a call.",
    aliases=["show the badge", "flash badge", "show badge to guards"],
)


def _take_rocco(a):
    g = a.game
    g.rocco_elevator_threat = False
    g.rocco_defeated = True


PunchRocco = _verb(
    "punch rocco",
    room="Elevator",
    requires=lambda a: (
        "Rocco's already dealt with." if a.game.rocco_defeated else None
    ),
    effect=_take_rocco,
    award=(
        "defeat_rocco",
        5,
        "You make short work of the gangster. He'll live. The doors close behind you.",
    ),
    aliases=[
        "kick rocco",
        "punch the gangster",
        "punch/kick rocco",
        "kick the gangster",
        "fight rocco",
    ],
)


def _shoot_rocco(a):
    _take_rocco(a)


ShootRocco = _verb(
    "shoot rocco",
    room="Elevator",
    requires=lambda a: (
        "Rocco's already dealt with."
        if a.game.rocco_defeated
        else (None if _is_holding(a.character, "gun") else "You don't have a gun.")
    ),
    effect=_shoot_rocco,
    award=(
        "defeat_rocco",
        5,
        "You fire. Rocco gasps, clutches his chest, then falls. The doors close behind you.",
    ),
    aliases=["shoot the gangster", "shoot rocco falcone"],
)


def _scan_thumb(a):
    a.game.thumb_scanned = True


ScanThumb = _verb(
    "scan rocco's thumb",
    room="Elevator",
    requires=lambda a: (
        None if a.game.rocco_defeated else "Rocco's in no state to cooperate yet."
    ),
    effect=_scan_thumb,
    success="You place Rocco's thumb on the scanner. The button marked P lights up. (PUSH P.)",
    aliases=[
        "scan thumb",
        "scan rocco thumb",
        "use rocco's thumb",
        "scan rocco's thumbprint",
    ],
)


def _search_rocco_elevator(a):
    colt = things.Item("colt .45", "a Colt .45 pistol", "Rocco's sidearm.")
    colt.add_command_hint("get colt .45")
    a.character.location.add_item(colt)
    a.game.rocco_searched = True


SearchRoccoElevator = _verb(
    "search rocco",
    room="Elevator",
    requires=lambda a: (
        None
        if a.game.rocco_defeated and not a.game.rocco_searched
        else (
            "You've already searched him."
            if a.game.rocco_searched
            else "Deal with him first."
        )
    ),
    effect=_search_rocco_elevator,
    success="You find a Colt .45 pistol. (GET COLT .45.)",
    aliases=["search rocco falcone", "frisk rocco"],
)


def _push_p(a):
    g = a.game
    penthouse = g.locations["Penthouse"]
    g.relocate(g.player, penthouse)
    g.award("enter_penthouse", 5)
    g.parser.ok(
        "The elevator ascends. Eventually you reach the penthouse:\n\n"
        + penthouse.description
    )


PushP = _verb(
    "push p",
    room="Elevator",
    requires=lambda a: (
        None
        if a.game.thumb_scanned
        else "The P button is locked. (SCAN ROCCO'S THUMB.)"
    ),
    effect=_push_p,
    aliases=["press p", "push button p", "push p button"],
)


OpenAttache = _verb(
    "open attache",
    room="Penthouse",
    effect=lambda a: None,
    success="You open the attaché case. There's close to a million dollars inside.",
    aliases=[
        "open attache case",
        "open the attache",
        "open attaché",
        "open the attaché case",
    ],
)


TakeAttache = _verb(
    "take attache",
    room="Penthouse",
    effect=lambda a: a.game.end_in_death(
        "Is this how you thought you'd end up, just another cop on the take? This "
        "is why the bad guys always win. THE END."
    ),
    aliases=[
        "take attache case",
        "take the attache",
        "take attaché",
        "take the money",
        "take the attaché case",
    ],
)


def _search_boss(a):
    g = a.game
    g.boss_searched = True
    room = a.character.location
    tape = things.Item(
        "audiotape",
        "the stolen audiotape",
        "Evidence linking Boss D to your kidnapping.",
    )
    tape.add_command_hint("get audiotape")
    revolver = things.Item(
        "s&w .38 special",
        "a pearl-handled S&W .38 Special",
        "Boss D's revolver -- now yours.",
    )
    revolver.add_command_hint("get .38 special")
    room.add_item(tape)
    room.add_item(revolver)


SearchBossD = _verb(
    "search boss d",
    room="Penthouse",
    requires=lambda a: "You've already searched him." if a.game.boss_searched else None,
    effect=_search_boss,
    success=(
        "You find a pearl-handled S&W .38 Special and the stolen audiotape, which "
        "links him to your kidnapping. More than enough to put him away. "
        "(ARREST BOSS D.)"
    ),
    aliases=["search boss", "search boss d.", "disarm boss d", "frisk boss d"],
)


def _arrest_boss(a):
    g = a.game
    g.arrested_boss = True
    g.award("arrest", 5)
    g.award("finish", 5)  # "finishing without saving" -- the completion bonus
    g.announce_ending(
        "You knock Boss D to his knees and read him his rights. A SWAT team barges "
        'in: "EVERYONE GET DOWN ON THE GROUND!" Boss D turns witness, pleads down '
        "to 20 years and sends the mayor to jail. Slade recovers and gets the "
        "Purple Heart; you get the Meritorious Service Award and a promotion to "
        "lieutenant. Best of all, you get to see Jack in his dress uniform at the "
        "medal ceremony. You never let him live it down. THE END.",
        show_score=True,
    )


ArrestBossD = _verb(
    "arrest boss d",
    room="Penthouse",
    requires=lambda a: (
        None
        if a.game.boss_searched
        else None  # handled in effect (unsearched -> he shoots you)
    ),
    effect=lambda a: (
        _arrest_boss(a)
        if a.game.boss_searched
        else a.game.end_in_death(
            "You move to arrest him, but you never searched him. Boss D draws a "
            ".38 Special, shoots you dead and escapes. THE END."
        )
    ),
    aliases=["arrest boss", "arrest boss d.", "cuff boss d"],
)


def _shoot_boss(a):
    g = a.game
    g.award("kill_boss", 0)
    g.announce_ending(
        "You fire at point-blank range, killing Boss D in cold blood. The SWAT "
        "team finds you standing over his body. The case never goes to trial; the "
        "mayor never goes to jail. Your career is finished -- busted down to beat "
        "cop, writing parking tickets. You got vengeance, but did you get justice? "
        "THE END.",
        show_score=True,
    )
    g.game_over = True
    g.game_over_description = "THE END"


ShootBossD = _verb(
    "shoot boss d",
    room="Penthouse",
    requires=lambda a: (
        None
        if _is_holding(a.character, "gun")
        or _is_holding(a.character, "colt .45")
        or _is_holding(a.character, "s&w .38 special")
        else "You're not armed."
    ),
    effect=_shoot_boss,
    aliases=["shoot boss", "shoot boss d.", "kill boss d"],
)


# Penthouse flavor on the mayor (non-progress).
SearchMayor = _verb(
    "search mayor",
    room="Penthouse",
    effect=lambda a: None,
    success="You don't find anything incriminating.",
    aliases=["search the mayor", "frisk mayor"],
)
ArrestMayor = _verb(
    "arrest mayor",
    room="Penthouse",
    effect=lambda a: None,
    success="You'll need more evidence before you can arrest the mayor.",
    aliases=["arrest the mayor", "cuff mayor"],
)
ShootMayor = _verb(
    "shoot mayor",
    room="Penthouse",
    effect=lambda a: None,
    success="Although you feel the burning fires of revenge, they're not for this loser.",
    aliases=["shoot the mayor", "kill mayor"],
)


def _talk_to_chief(a):
    g = a.game
    if g.is_chang:
        g.parser.ok(
            "\"Detective Chang, consider yourself back on the case. Here's your "
            "badge and gun. Now get the hell out of here and do what you gotta "
            'do!" (GET BADGE, GET GUN.)'
        )
    else:
        g.parser.ok(
            '"Dammit, Slade! I thought I gave you a two-week suspension?! Now get '
            'the hell out of my office before I make it a month!"'
        )


TalkToChief = _verb(
    "talk to chief",
    room="Chief's Office",
    effect=_talk_to_chief,
    aliases=["talk to the chief", "talk chief", "speak to chief"],
)


# ---------------------------------------------------------------------------
# The motorcycle / Porsche overworld (the engine's vehicle feature)
# ---------------------------------------------------------------------------


def _start_bike(a):
    a.character.riding = a.game.locations and a.character.location.items.get(
        "motorcycle"
    )


GetOnMotorcycle = _verb(
    "get on motorcycle",
    requires=lambda a: (
        "There's no bike here."
        if a.character.location.items.get("motorcycle") is None
        else (
            None
            if _is_holding(a.character, "keys")
            else "You need your keys to start the bike. (They jingle in your jacket pocket.)"
        )
    ),
    effect=_start_bike,
    success="You climb onto your bike and start it up. Baby purrs.",
    aliases=[
        "get on bike",
        "get on the motorcycle",
        "ride motorcycle",
        "ride bike",
        "ride the motorcycle",
        "ride the bike",
        "start bike",
        "start the motorcycle",
        "mount motorcycle",
        "hop on the bike",
    ],
)


def _park(a):
    veh = a.character.riding
    a.character.riding = None
    return veh


ParkVehicle = _verb(
    "park bike",
    requires=lambda a: (
        None if a.character.riding is not None else "You're not riding anything."
    ),
    effect=_park,
    success="You park your ride and hit the streets on foot.",
    aliases=[
        "park motorcycle",
        "park the bike",
        "park porsche",
        "park the porsche",
        "park car",
        "get off bike",
        "get off the bike",
        "get off the motorcycle",
        "get out",
        "get out of porsche",
        "get out of the porsche",
        "get out of car",
    ],
)


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> DangertownBeatdown:
    L = things.Location

    # --- Sub-locations (on foot) ------------------------------------------
    bedroom = L(
        "Bedroom",
        "You're roused from sleep by neon light. It's 11:58 p.m. There's a closet "
        "and a mirror here. Your answering machine is flashing. A door leads out.",
    )
    apartment = L(
        "Apartment",
        "Home sweet home. A kettle and some instant coffee are on the counter by "
        "the stove. There's a newspaper on the table. Your bedroom is here, and a "
        "door leads out to Southside.",
    )
    southside = L(
        "Southside",
        "You're outside a rundown apartment building in the Gaslight District. "
        "There's a strip club here. Your motorcycle is parked at the curb. "
        "Gaslight's North End is a short walk away; the open road is a ride away.",
    )
    strip_club = L(
        "Strip Club",
        "Tiger'z Den is a seedy strip joint with animal-print decor. Some dancers "
        "sway onstage. You don't see anyone here to wait on you.",
    )
    north_end = L(
        "North End",
        "Gaslight's North End. Some gang members loiter outside an arcade. A pay "
        "phone is on the corner. Southside is a short walk south.",
    )
    arcade = L(
        "Arcade",
        "Dream Warriors is an arcade full of young toughs in gang colors. You "
        "recognize Cutter and his Southside Blades; a friendlier face is Trina "
        '"Rabbit" Rodriguez.',
    )
    little_italy = L(
        "Little Italy",
        "A charming neighborhood where the Old World meets the new. The 24-hour "
        "Pixel City Café is open; across the street is Gheorghe's boxing gym.",
    )
    cafe = L(
        "Pixel City Cafe",
        "A 24-hour coffee shop with a lunch counter and a well-lit pastry case. "
        'Marge is here. "What\'ll it be, hon? The usual?"',
    )
    gym = L(
        "Gheorghe's Gym",
        "You're inside the boxing gym. Gheorghe, who coached the Romanian Olympic "
        "team in '84, is here.",
    )
    downtown = L(
        "Downtown",
        "Downtown: a few struggling tech startups and Santa Morena's police "
        "department. Graffiti reads DANGERTOWN over the old city slogan.",
    )
    police_station = L(
        "Police Station",
        "Sergeant O'Brien is at his desk going over paperwork. You see the police "
        "chief's office and the hallway leading to the evidence locker.",
    )
    evidence_locker = L(
        "Evidence Locker",
        "A storage area crammed with cardboard boxes, each assigned a case number.",
    )
    chiefs_office = L("Chief's Office", "The police chief is here at his desk.")
    harbor_view = L(
        "Harbor View",
        "A rundown industrial area on the water's edge. Numbered loading bays "
        "stretch into the dark. Some flashy sports cars are parked here.",
    )
    warehouse = L(
        "Warehouse",
        "A maze of crates and shipping containers, dark save for a single "
        "floodlight illuminating a lone woman tied to a chair.",
    )
    morena_beach = L(
        "Morena Beach",
        "Where the money lives: gated communities, seaside mansions and luxury "
        "high-rises. Pacific Towers is one of Santa Morena's tallest buildings.",
    )
    pacific_towers = L(
        "Pacific Towers",
        "An imposing tower of concrete, glass and steel. Guards are posted in the "
        "lobby. There's an elevator here.",
    )
    elevator = L("Elevator", "You're in an elevator. There's a control panel here.")
    penthouse = L(
        "Penthouse",
        "A spacious apartment all done up in chrome and white. Boss D is here, "
        "enjoying a glass of wine with the mayor of Santa Morena. The mayor "
        "nervously clutches a leather attaché case.",
    )

    all_locations = [
        bedroom,
        apartment,
        southside,
        strip_club,
        north_end,
        arcade,
        little_italy,
        cafe,
        gym,
        downtown,
        police_station,
        evidence_locker,
        chiefs_office,
        harbor_view,
        warehouse,
        morena_beach,
        pacific_towers,
        elevator,
        penthouse,
    ]

    # --- Connections -------------------------------------------------------
    # On-foot walks and building entrances (named one-way exits so auto-reverse
    # collisions can't strand a room).
    _one_way(bedroom, "out", apartment)
    _one_way(apartment, "enter bedroom", bedroom)
    _one_way(apartment, "out", southside)
    _one_way(southside, "enter apartment", apartment)
    _one_way(southside, "enter strip club", strip_club)
    _one_way(strip_club, "out", southside)
    _one_way(southside, "north", north_end)
    _one_way(north_end, "south", southside)
    _one_way(north_end, "enter arcade", arcade)
    _one_way(arcade, "out", north_end)
    _one_way(little_italy, "enter cafe", cafe)
    _one_way(cafe, "out", little_italy)
    _one_way(little_italy, "enter gym", gym)
    _one_way(gym, "out", little_italy)
    _one_way(downtown, "enter police station", police_station)
    _one_way(police_station, "out", downtown)
    _one_way(police_station, "enter evidence locker", evidence_locker)
    _one_way(evidence_locker, "out", police_station)
    _one_way(police_station, "enter chief's office", chiefs_office)
    _one_way(chiefs_office, "out", police_station)
    _one_way(harbor_view, "enter bay #23", warehouse)
    _one_way(warehouse, "out", harbor_view)
    _one_way(morena_beach, "enter pacific towers", pacific_towers)
    _one_way(pacific_towers, "out", morena_beach)
    _one_way(pacific_towers, "enter elevator", elevator)
    _one_way(elevator, "out", pacific_towers)
    # (Elevator -> Penthouse is via PUSH P, an action, not a walkable exit.)

    # Ride links between districts (gated by RequiresVehicle). Named "to X" so the
    # parser's movement-verb strip ("drive to X" -> "to X") lands on the exit.
    ride_links = [
        (southside, "to downtown", downtown),
        (southside, "to little italy", little_italy),
        (little_italy, "to gaslight", southside),
        (little_italy, "to downtown", downtown),
        (little_italy, "to harbor view", harbor_view),
        (little_italy, "to morena beach", morena_beach),
        (downtown, "to little italy", little_italy),
        (downtown, "to harbor view", harbor_view),
        (harbor_view, "to morena beach", morena_beach),
        (harbor_view, "to little italy", little_italy),
        (harbor_view, "to downtown", downtown),
        (morena_beach, "to little italy", little_italy),
        (morena_beach, "to harbor view", harbor_view),
    ]
    for frm, direction, to in ride_links:
        _one_way(frm, direction, to)
        frm.add_block(
            direction,
            blocks.RequiresVehicle(
                frm, "That's across town -- too far on foot. Hop on your ride."
            ),
        )

    # --- Items: scenery helper --------------------------------------------
    def scenery(name, desc, examine, loc, hints=()):
        it = things.Item(name, desc, examine)
        it.set_property("gettable", False)
        for h in hints:
            it.add_command_hint(h)
        loc.add_item(it)
        return it

    # Bedroom: mirror, window, sign, answering machine, closet (uniform + jacket).
    scenery(
        "mirror",
        "a mirror",
        'Black jeans and a T-shirt that reads "Gheorghe\'s Gym -- Little Italy." Coffee required.',
        bedroom,
        ["examine mirror"],
    )
    scenery(
        "window",
        "the window",
        "A neon sign blinks across the street. Your motorcycle is parked where you left it.",
        bedroom,
        ["examine window"],
    )
    scenery(
        "sign",
        "the neon sign",
        '"TIGER\'z DEN" blinks below a neon tiger.',
        bedroom,
        ["examine sign"],
    )
    scenery(
        "answering machine",
        "the answering machine",
        "The PLAY MESSAGE button is flashing.",
        bedroom,
        ["play message"],
    )
    closet = things.Item(
        "closet", "a closet", "Inside: a police dress uniform and a leather jacket."
    )
    closet.set_property("gettable", False)
    closet.make_container()
    closet.set_property("is_closed", True)
    closet.set_property("contents_visible", True)  # listed in LOOK once opened
    closet.add_command_hint("open closet")
    uniform = things.Item(
        "uniform", "a police dress uniform", 'The brass nameplate reads "J. SLADE."'
    )
    uniform.set_property("wearable", True)
    uniform.set_property(
        "wear_text", "You wear your dress blues only for commendations and funerals."
    )
    jacket = things.Item(
        "jacket",
        "a leather jacket",
        "Your apartment and motorcycle keys are in the pocket.",
    )
    jacket.set_property("wearable", True)
    jacket.set_property(
        "wear_text", "You put on the leather jacket. Your keys jingle in the pocket."
    )
    # The keys literally live in the jacket pocket (a small open container), so
    # they come with the jacket and the held-scope helpers find them whether the
    # jacket is carried or worn.
    jacket.make_container()
    jacket.set_property("contents_visible", True)
    keys = things.Item(
        "keys", "your keys", "The keys to your apartment and motorcycle."
    )
    keys.add_command_hint("get on motorcycle")
    jacket.add_item(keys)
    jacket.add_command_hint("wear jacket")
    closet.add_item(uniform)
    closet.add_item(jacket)
    bedroom.add_item(closet)

    # Apartment: the kettle, the newspaper, the locked door + peephole.
    scenery(
        "kettle",
        "a kettle",
        "An old kettle on the stove. Good for coffee -- or, in a pinch, a weapon.",
        apartment,
        ["make coffee"],
    )
    newspaper = things.Item(
        "newspaper",
        "a newspaper",
        "Headlines about violent crime and the mayor's waterfront deal.",
    )
    newspaper.add_command_hint("read newspaper")
    apartment.add_item(newspaper)
    scenery(
        "door",
        "the front door",
        "Locked, with a peephole.",
        apartment,
        ["examine door"],
    )
    scenery(
        "peephole",
        "the peephole",
        "You spy a large man in a suit holding a baseball bat. He raps hard on the door.",
        apartment,
        ["examine peephole"],
    )
    scenery(
        "envelope",
        "an envelope of cash",
        "That's a lot of cash just for gas and tolls -- about six months' pay. Blood money.",
        apartment,
        ["examine envelope"],
    )

    # Strip club dancers (scenery).
    scenery(
        "dancers",
        "the dancers",
        "They feign interest for a few seconds, then move on to the next customer.",
        strip_club,
        ["tip dancers"],
    )

    # North End: the pay phone (out of order) with a quarter in the slot.
    scenery(
        "pay phone",
        "a pay phone",
        "There's a quarter in the change slot. It's 25 cents to make a call.",
        north_end,
        ["use phone", "get quarter"],
    )
    quarter = things.Item(
        "quarter", "a quarter", "Twenty-five cents. Enough for the arcade."
    )
    quarter.add_command_hint("get quarter")
    quarter.add_command_hint("put quarter on machine")
    north_end.add_item(quarter)

    # Arcade: the machines (scenery) -- the quarter goes here.
    scenery(
        "games",
        "rows of coin-op video games",
        "Gang members have placed quarters on the machines to reserve their place in line.",
        arcade,
        ["put quarter on machine"],
    )

    # Cafe: the pastry case with the box of donuts.
    scenery(
        "case",
        "the pastry case",
        "Day-old donuts. \"They're yours if you want 'em,\" Marge says.",
        cafe,
        ["get donuts"],
    )
    donuts = things.Item(
        "donuts",
        "a box of day-old donuts",
        "A box of day-old donuts -- a sergeant's best friend.",
    )
    donuts.add_command_hint("get donuts")
    donuts.add_command_hint("give o'brien donuts")
    cafe.add_item(donuts)

    # Chief's office: the badge and the gun (Chang takes them).
    badge = things.Item(
        "badge",
        "a Santa Morena detective's badge",
        "Detective Chang's badge. Your badge.",
    )
    badge.add_command_hint("get badge")
    badge.add_command_hint("show badge")
    gun = things.Item("gun", "a loaded Beretta 92S", "Your service pistol.")
    gun.add_command_hint("get gun")
    chiefs_office.add_item(badge)
    chiefs_office.add_item(gun)

    # Warehouse: the woman (Jetta) + Rocco + the attaché lives in the penthouse.
    scenery(
        "woman",
        "a woman tied to a chair",
        "It's your partner, Jetta Chang! She's zip-tied to a chair.",
        warehouse,
        ["free jetta chang"],
    )
    scenery(
        "attache",
        "a leather attaché case",
        "There's close to a million dollars inside.",
        penthouse,
        ["open attache"],
    )
    scenery(
        "control panel",
        "the elevator control panel",
        "Buttons L to 26. At the top is a thumbprint scanner next to a button marked P.",
        elevator,
        ["scan rocco's thumb", "push p"],
    )

    # The motorcycle (a vehicle that needs the keys to start).
    motorcycle = things.Item(
        "motorcycle",
        "a black Kawasaki GPZ900R",
        'A black Kawasaki GPZ900R. You call it "Baby."',
    )
    motorcycle.set_property("gettable", False)
    motorcycle.make_vehicle(ready=False)
    motorcycle.set_property(
        "mount_refusal_message", "Start it with your keys. (GET ON MOTORCYCLE.)"
    )
    motorcycle.add_command_hint("get on motorcycle")
    southside.add_item(motorcycle)

    # --- Characters --------------------------------------------------------
    slade = things.Character(
        "Jack Slade",
        "a hard-boiled detective in a leather jacket",
        "I have to get the tape and save my partner -- without becoming what I'm hunting.",
    )

    jetta = things.Character(
        "Jetta Chang",
        "rookie detective Jetta Chang",
        "I'm in over my head, but I'll fight my way out and finish what Slade started.",
    )
    jetta.talk_text = '"I figured dummy here would go full Rambo, so I tailed him. Get him out of here and call 911 before he dies!"'
    warehouse.add_character(jetta)

    man = things.Character(
        "man",
        "a large man in a suit -- Rocco Falcone",
        "Boss D sent me to make Slade a problem that goes away.",
    )
    man.talk_text = (
        "\"Boss D says it's time for you to take a vacation. Maybe a drive up the "
        'coast." He places an envelope on the table. "An advance, to cover gas '
        'and tolls." (SAY YES or SAY NO.)'
    )

    cat = things.Character(
        "cat",
        "Cat Marco, the waitress -- your ex",
        "Jack again. He never knows when to quit.",
    )
    cat.talk_text = '"Hi, Jack. Big spender! Did you finally bet on the right horse?"'
    cat.talk_topics = {
        "rocco": '"Yeah, I know him. Gets a little too hands-on with the staff, but he works for Boss D, so nobody\'s got the guts to throw him out."',
        "boss": '"He hired some girls for a party at his place -- bankers, lawyers, politicians. I have an address. Got something to write on?"',
    }

    cutter = things.Character(
        "cutter", "Cutter, of the Southside Blades", "Nobody snitches on my turf."
    )
    cutter.talk_text = 'Cutter sneers, "Get lost, pig." His gang snickers.'
    arcade.add_character(cutter)
    rabbit = things.Character(
        "rabbit",
        'Trina "Rabbit" Rodriguez, of Los Dragóns',
        "I keep an eye on Slade -- he's gonna need it.",
    )
    rabbit.talk_text = (
        '"Hola, Slade. Wanna talk? Put up a quarter." (PUT QUARTER ON MACHINE.)'
    )
    arcade.add_character(rabbit)

    gheorghe = things.Character(
        "gheorghe",
        "Gheorghe, the old boxing coach",
        "These kids need someone in their corner.",
    )
    gheorghe.talk_text = (
        '"Ah, Jack, my friend... What happened?" (ASK GHEORGHE FOR HELP.)'
    )
    gym.add_character(gheorghe)

    marge = things.Character(
        "marge", "Marge, the café owner", "Slade and Chang are heroes around here."
    )
    marge.talk_text = "\"I haven't seen your partner in a while. Hope she's well.\""
    marge.talk_topics = {
        "partner": '"You and Officer Chang are heroes around these parts! Free coffee for life."'
    }
    cafe.add_character(marge)

    obrien = things.Character(
        "o'brien", "Sergeant O'Brien", "I'm just waiting for retirement."
    )
    obrien.talk_text = '"Evening, Jack. I thought the chief suspended you. You and Chang sure messed up this time." (GIVE O\'BRIEN DONUTS.)'
    obrien.talk_topics = {
        "report": '"Wiretapping the mayor? Sounds like career suicide to me. You don\'t know when to shut up."',
        "tape": 'He pats his key ring. "Locked up safe and sound."',
        "chang": '"She got off easy. Funny though... she never came in for traffic duty. Nobody\'s home."',
    }
    police_station.add_character(obrien)

    # Act-2 fighters (spawned at the switch / present from the start, idle).
    goon = things.Character(
        "goon",
        "a big goon with a submachine gun",
        "Boss says nobody walks out of here.",
    )
    knockout = things.Character(
        "Knockout",
        "Knockout, a masked vigilante",
        "Somebody has to fight for this city.",
    )

    boss_d = things.Character(
        "boss d", "Boss D, the crime lord", "This city is mine. Cops included."
    )
    boss_d.talk_text = '"Ah, Officer Chang. Such an unexpected surprise. I do hope your partner pulls through." (SEARCH BOSS D.)'
    mayor = things.Character(
        "mayor",
        "the mayor of Santa Morena",
        "Just some totally legal campaign contributions.",
    )
    mayor.talk_text = (
        '"Uhh... just discussing some totally legal campaign contributions!"'
    )
    penthouse.add_character(boss_d)
    penthouse.add_character(mayor)

    chief = things.Character(
        "chief",
        "the police chief",
        "He looks exactly how you picture him, but 25 percent meaner.",
    )
    # Static fallback line; TALK TO CHIEF (custom) branches Slade vs. Chang.
    chief.talk_text = (
        '"Dammit, Slade! I thought I gave you a two-week suspension?! '
        'Now get the hell out of my office before I make it a month!"'
    )
    chiefs_office.add_character(chief)

    # --- Assemble ----------------------------------------------------------
    custom_actions = [
        # Act 1
        PlayMessage,
        MakeCoffee,
        ReadNewspaper,
        SayYes,
        SayNo,
        HitManWithKettle,
        HitManWithBat,
        SearchMan,
        TakeEnvelope,
        TipDancers,
        GiveMatchbookToCat,
        UsePhone,
        PutQuarterOnMachine,
        HitCutterWithBat,
        AskGheorgheForHelp,
        OrderTheUsual,
        DrinkCoffee,
        GiveObrienDonuts,
        FindBox,
        TakeBox,
        TakeAudiotape,
        ReturnKeys,
        SlashTires,
        FindBay,
        FreeJettaChang,
        GiveTape,
        TalkToChief,
        # Act 2
        AttackGoon,
        SearchGoon,
        DragSladeOut,
        UseKeyOnPorsche,
        EnterPorsche,
        Call911,
        ShowBadge,
        PunchRocco,
        ShootRocco,
        ScanThumb,
        SearchRoccoElevator,
        PushP,
        OpenAttache,
        TakeAttache,
        SearchBossD,
        ArrestBossD,
        ShootBossD,
        SearchMayor,
        ArrestMayor,
        ShootMayor,
        # Overworld
        GetOnMotorcycle,
        ParkVehicle,
    ]
    characters = [
        jetta,
        man,
        cat,
        cutter,
        rabbit,
        gheorghe,
        marge,
        obrien,
        goon,
        knockout,
        boss_d,
        mayor,
        chief,
    ]
    game = DangertownBeatdown(bedroom, slade, characters, custom_actions)
    game.slade = slade
    game.jetta = jetta

    # Register every room by name (named one-way exits and arrival hooks look
    # rooms up by name).
    for loc in all_locations:
        game.locations.setdefault(loc.name, loc)

    # The goon and Knockout don't exist on the map until the switch spawns them.
    for c in (goon, knockout):
        if c.location is not None:
            c.location.remove_character(c)

    # --- Blocks gating building entrances ---------------------------------
    # On-foot-only entrances.
    for loc, direction in [
        (southside, "enter apartment"),
        (southside, "enter strip club"),
        (southside, "north"),
        (little_italy, "enter gym"),
        (downtown, "enter police station"),
        (north_end, "enter arcade"),
    ]:
        loc.add_block(direction, ParkedOnly(loc))
    # Conditional entrances.
    little_italy.add_block(
        "enter cafe",
        GateBlock(
            little_italy,
            game,
            lambda g: not g.bleeding,
            "Marge will kill you if you bleed all over her floor. Get patched up first.",
        ),
    )
    harbor_view.add_block(
        "enter bay #23",
        GateBlock(
            harbor_view,
            game,
            lambda g: g.knows_warehouse,
            "Hours of numbered loading bays. You'd need to know which one. (Ask around.)",
        ),
    )
    morena_beach.add_block(
        "enter pacific towers",
        GateBlock(
            morena_beach,
            game,
            lambda g: g.showed_badge,
            'Armed security guards stop you: "Private property." You\'re strong-armed back to the curb.',
        ),
    )
    # The evidence locker needs O'Brien's key ring in hand.
    police_station.add_block(
        "enter evidence locker",
        FlagBlock(
            game,
            lambda g: _is_holding(g.player, "key ring"),
            "You'll need someone to unlock it for you.",
        ),
    )
    # Once Rocco kicks the apartment door in, he blocks the exit until you knock
    # him out (page 89: "He kicks in the door and enters -- blocking the exit").
    apartment.add_block(
        "out",
        FlagBlock(
            game,
            lambda g: not (g.rocco_at_door and not g.rocco_ko),
            "The large man fills the doorway, baseball bat in hand. You're not "
            "getting past him -- deal with him first.",
        ),
    )
    # The warehouse goons block the exit until you give Rocco the tape.
    warehouse.add_block(
        "out",
        FlagBlock(
            game,
            lambda g: not (g.rocco_confront and not g.given_tape),
            'Rocco\'s goons block the exit. "Give us the tape, Slade."',
        ),
    )

    # --- Triggers ----------------------------------------------------------
    # Refusing the bribe but failing to knock the gangster out -> bloody pulp.
    def _fight_death(g):
        if not g.fight_pending:
            return
        if g._fight_warned:
            g.end_in_death("The gangster bashes you to a bloody pulp. THE END.")
        else:
            g._fight_warned = True

    game.add_trigger(
        "fight_timeout", lambda g: g.fight_pending, _fight_death, repeatable=True
    )

    # Lingering in the evidence locker after taking the tape -> busted.
    def _locker_death(g):
        if g.player.location.name != "Evidence Locker" or not g.tape_taken:
            return
        if g._locker_warned:
            g.end_in_death(
                "The sergeant busts you for tampering with evidence. Your "
                "suspension becomes permanent; your partner is never found. THE END."
            )
        else:
            g._locker_warned = True

    game.add_trigger(
        "locker_timeout",
        lambda g: g.player.location.name == "Evidence Locker" and g.tape_taken,
        _locker_death,
        repeatable=True,
    )

    # Failing to take out the goon while Knockout fights -> riddled with bullets.
    def _goon_death(g):
        if not g.goon_threat:
            return
        if g._goon_warned:
            g.end_in_death("You and the masked girl are riddled with bullets. THE END.")
        else:
            g._goon_warned = True

    game.add_trigger(
        "goon_timeout", lambda g: g.goon_threat, _goon_death, repeatable=True
    )

    # Failing to take out Rocco in the elevator -> he shoots you.
    def _elevator_death(g):
        if not g.rocco_elevator_threat:
            return
        if g._elevator_warned:
            g.end_in_death("Rocco draws his Colt .45 and shoots you. THE END.")
        else:
            g._elevator_warned = True

    game.add_trigger(
        "elevator_timeout",
        lambda g: g.rocco_elevator_threat,
        _elevator_death,
        repeatable=True,
    )

    # Slade bleeds out if you don't reach the ambulance in time.
    def _bleed_out(g):
        if (
            g._save_deadline is not None
            and not g.slade_saved
            and g.slade_aboard
            and g.turn > g._save_deadline
        ):
            g.end_in_death(
                "Slade bleeds out in the passenger seat before you reach help. THE END."
            )

    game.add_trigger(
        "bleed_out",
        lambda g: g._save_deadline is not None and not g.slade_saved,
        _bleed_out,
        repeatable=True,
    )

    # Getting both the badge and the gun from the chief scores once.
    game.add_trigger(
        "badge_gun",
        lambda g: _is_holding(g.player, "badge") and _is_holding(g.player, "gun"),
        lambda g: g.award(
            "badge_gun",
            5,
            '"Detective Chang, consider yourself back on the case. Now do what you gotta do!"',
        ),
        repeatable=True,
    )

    return game


# ---------------------------------------------------------------------------
# Walkthrough (also the win test) -- wins at 100/100
# ---------------------------------------------------------------------------

WALKTHROUGH = [
    # --- Act 1: Jack Slade -------------------------------------------------
    "play message",  # +5 msg
    "open closet",
    "get jacket",
    "wear jacket",  # -> keys jingle in pocket
    "out",  # -> Apartment
    "make coffee",
    "read newspaper",  # +5 newspaper; the knock + Rocco
    "say no",  # +5 refuse_bribe; the fight
    "hit man with kettle",  # +5 kettle_ko; Rocco drops the bat
    "get bat",
    "search man",  # spills matchbook + wallet onto the floor
    "get matchbook",
    "get wallet",  # holds the $100 bill + license
    "out",  # -> Southside
    "enter strip club",  # -> Strip Club
    "tip dancers",  # +5 tip; Cat Marco appears
    "give matchbook to cat",  # +5 boss_location -> Pacific Towers, Morena Beach
    "out",  # -> Southside
    "north",  # -> North End
    "get quarter",
    "enter arcade",  # -> Arcade
    "put quarter on machine",  # +5 warehouse_num -> bay #23
    "out",  # Cutter slashes you (bleeding); you don't move
    "hit cutter with bat",  # +5 beat_cutter; drops switchblade
    "take switchblade",
    "out",  # -> North End
    "south",  # -> Southside
    "get on motorcycle",  # start the bike (needs keys)
    "drive to little italy",  # -> Little Italy (riding)
    "park bike",
    "enter gym",  # -> Gheorghe's Gym
    "ask gheorghe for help",  # +5 patched; bleeding cleared
    "out",  # -> Little Italy
    "enter cafe",  # -> Pixel City Café (no longer bleeding)
    "order the usual",
    "drink coffee",  # +5 coffee
    "get donuts",
    "out",  # -> Little Italy
    "get on motorcycle",
    "drive to downtown",  # -> Downtown
    "park bike",
    "enter police station",  # -> Police Station
    "give o'brien donuts",  # +5 donuts; key ring + case file left behind
    "get key ring",
    "enter evidence locker",  # -> Evidence Locker
    "find box",  # box #198X
    "take audiotape",  # +5 audiotape; footsteps warning
    "out",  # -> Police Station (leaving avoids the bust)
    "return keys",
    "out",  # -> Downtown
    "get on motorcycle",
    "drive to harbor view",  # -> Harbor View
    "park bike",
    "find bay",  # bay #23
    "enter bay #23",  # -> Warehouse
    "free jetta chang",  # +5 free_jetta; Rocco confrontation
    "give tape",  # shooting -> SWITCH to Jetta Chang
    # --- Act 2: Jetta Chang ------------------------------------------------
    "attack goon",  # +5 help_knockout
    "search goon",  # spills candy bar + Porsche keys onto the floor
    "get porsche keys",
    "drag slade out",  # -> Harbor View; reveals the Porsche
    "use key on porsche",  # unlock + Slade aboard + drive
    "call 911",  # ambulance on the way
    "drive to downtown",  # -> Downtown; +5 save_slade
    "get out",  # park the Porsche
    "enter police station",  # -> Police Station (chief wants you)
    "enter chief's office",  # -> Chief's Office
    "get badge",
    "get gun",  # +5 badge_gun (both in hand)
    "out",  # -> Police Station
    "out",  # -> Downtown
    "enter porsche",  # back behind the wheel
    "drive to harbor view",  # -> Harbor View
    "drive to morena beach",  # -> Morena Beach
    "get out",
    "show badge",  # guards let you pass
    "enter pacific towers",  # -> Pacific Towers
    "enter elevator",  # -> Elevator; Rocco!
    "punch rocco",  # +5 defeat_rocco
    "scan rocco's thumb",
    "push p",  # -> Penthouse; +5 enter_penthouse
    "search boss d",  # disarm + evidence
    "arrest boss d",  # +5 arrest, +5 finish -> WIN
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
