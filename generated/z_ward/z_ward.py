"""Z-Ward -- a Parsely game ported to the text_adventure_games engine.

Zombies have overrun the hospital where your sister Frances was admitted nine
weeks ago. Armed with nothing but a panicked email ("halp zomby apokalips xoxo
frances") and a shovel, you work your way through the wards: kill the doctor in
the gardens before he turns, rescue the survivors (Chef Peggy, Pete the orderly,
the nurse), sedate the trigger-happy chief of staff for his key, find Frances
hidden inside the padded wall of the Quiet Room, wheel her to the elevator, and
escape the hospital alive. Source: Parsely "Z-Ward" by Jared Sorensen (pages
245-265, the normal-rules game; max 100 points).

Authored the way the reference ports are (see ``action_castle_2.py`` and
``docs/converting-parsely-games.md``): a ``build_game()`` assembling the world, a
small ``ZWard`` Game subclass holding the win/score logic and the per-turn
set-pieces (the gardens man turning if you enter the hospital first, the
auditorium horde closing in if you linger, escorting Frances by elevator, the
escape), the two-object verbs via the engine's ``use_item_on`` factory, and a
handful of custom ``Action`` subclasses for the genuinely novel verbs.

A design call worth flagging (the OCR'd source is contradictory here, the kind of
ambiguity docs/converting-parsely-games.md sections 12 & 15 say a human must
resolve): the rulebook says the Auditorium can only be passed *when the power is
out*, but the sole power-outage source -- setting the EST dial to HIGH -- costs
the "+5 not causing a power outage" scoring line. As written, rescuing Pete (+10)
and the no-outage bonus (+5) would be mutually exclusive, yet the scoring table
sums to exactly 100 with both included. We honor the designer's explicit 100
total: the projector's light keeps the auditorium zombies docile (you may pass
through, but lingering is fatal), so Pete is reachable with the power on, and the
+5 rewards getting the wheelchair via the safe MEDIUM dial instead of botching it
on HIGH. The Advanced Rules (the Basement, +20 bonus) are out of scope.

Run interactively:    uv run python -m test_gen.z_ward.z_ward
Run the walkthrough:  uv run python -m test_gen.z_ward.z_ward --walk
"""

from text_adventure_games import games, things, actions, blocks

# ---------------------------------------------------------------------------
# Helpers (mirroring the reference ports' kit)
# ---------------------------------------------------------------------------


def _all_held(character):
    """Everything the character has on them: inventory + worn + wielded. Quest
    checks must look at the union, not bare ``inventory`` -- wearing or wielding
    an item moves it out of ``inventory``."""
    return {**character.inventory, **character.worn, **character.wielded}


def _is_holding(character, name):
    return name in _all_held(character)


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s canonical auto-reverse, so a
    named door ("out", "elevator", "press 1") doesn't silently wire a reverse
    that collides with another exit. (See the same helper in action_castle_2.py.)
    """
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


# The escape epilogue (page 265). The only winning ending.
VICTORY = (
    "You emerge from the elevator into a scene of utter chaos and carnage. "
    "Pieces of charred, smoking zombies litter the ground. Frances shakily "
    "stands up from the wheelchair and hugs you tight. Finally free from this "
    "nightmare, the two of you step out into the bright sunlight and leave "
    "Z-Ward behind... forever. THE END."
)


# ---------------------------------------------------------------------------
# Game subclass: win condition, scoring, and the per-turn set-pieces
# ---------------------------------------------------------------------------


class ZWard(games.Game):
    """Won only by finding Frances and escorting her -- in the wheelchair, via
    the elevator -- out the front of the hospital. Several missteps end the game
    early (the chief shoots you, Bambi enrages the horde, you abandon Frances to
    the straitjacket zombie, the auditorium closes in)."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        # Scoring table, page 265 (max 100). score / _scored_keys / award() come
        # from the base Game.
        self.max_score = 100
        self.entered_hospital = False  # has the gardens man turned yet?
        self.outage = False  # did the EST dial get cranked to HIGH?
        self.auditorium_turns = 0  # turns spent among the unpacified horde

    # -- the escape / win ---------------------------------------------------

    def _escape(self):
        self.award("escape", 25)
        self.award("finish", 5)  # finishing without saving, page 265
        self.player.set_property("has_won", True)
        self.announce_ending(VICTORY, show_score=True)

    def is_won(self) -> bool:
        return bool(self.player.get_property("has_won"))

    # -- per-turn set-pieces -------------------------------------------------

    def do_command(self, command: str) -> bool:
        before = self.player.location

        # The gardens man (Dr. Honeycutt) turns into a zombie the moment you set
        # foot in the hospital -- after which killing him no longer scores.
        going_in = (
            before is not None
            and before.name == "Hospital Entrance"
            and (command or "").strip().lower() in ("north", "go north", "n")
        )

        # Abandoning Frances: if she's out of the wall but not yet secured in the
        # wheelchair and you leave the Quiet Room, the straitjacket zombie gets
        # her (page 258).
        in_quiet = before is not None and before.name == "Quiet Room"
        frances = self.characters.get("frances")
        frances_loose = (
            frances is not None
            and frances.get_property("emerged")
            and not frances.get_property("in_wheelchair")
        )

        success = super().do_command(command)
        after = self.player.location

        if going_in and after is not None and after.name == "Hospital Intake":
            self._turn_gardens_man()

        if success and after is not before:
            if in_quiet and frances_loose and after.name != "Quiet Room":
                self.end_in_death(
                    "You step out, leaving Frances behind. The straitjacketed "
                    "zombie lurches to life and falls upon her. You escape "
                    "Z-Ward with your life, but you'll never forgive yourself "
                    "for the loss of your sister. THE END."
                )
                return success
            self._arrivals(after)

        self._auditorium_watch()
        return success

    def _turn_gardens_man(self):
        man = self.characters.get("man")
        gardens = self.locations.get("Gardens")
        if man is None or gardens is None or man.location is not gardens:
            return
        if man.get_property("dead") or man.get_property("zombified"):
            return
        man.set_property("zombified", True)
        man.description = "a zombie fumbling with a keycard clipped to its lab coat"
        man.examine_text = (
            "You see a zombie fumbling with a keycard clipped to its bloody lab "
            "coat."
        )

    def _arrivals(self, loc):
        # Getting Frances to the elevator, then out the front -- the endgame.
        frances = self.characters.get("frances")
        escorting = frances is not None and frances.get_property("in_wheelchair")
        if not escorting:
            return
        if loc.name == "Elevator":
            self.award(
                "frances_elevator",
                5,
                "You wheel Frances into the elevator. Almost there.",
            )
        elif loc.name == "Hospital Entrance":
            self._escape()

    def _auditorium_watch(self):
        """Page 252: the horde becomes agitated and closes in. You may pass
        through, but you can't linger among them."""
        aud = self.locations.get("Auditorium")
        if self.player.location is aud and not aud.get_property("pacified"):
            self.auditorium_turns += 1
            if self.auditorium_turns >= 2:
                self.end_in_death(
                    "The shuffling zombies close in from every side, and there "
                    "are far too many to fight. They drag you down. THE END."
                )
        else:
            self.auditorium_turns = 0


# ---------------------------------------------------------------------------
# A flexible block: an exit is shut until some predicate goes true
# ---------------------------------------------------------------------------


class CondBlock(blocks.Block):
    """An exit blocked until a predicate goes true (a keycard swipe, a cleared
    zombie, an unlocked padlock) -- or blocked *while* one is true (the stairs,
    barred to the wheelchair). The predicate is a zero-arg callable returning
    True when the way is shut."""

    def __init__(self, description, predicate):
        super().__init__("The way is shut", description)
        self.predicate = predicate

    def is_blocked(self) -> bool:
        return self.predicate()


# ---------------------------------------------------------------------------
# Two-object verbs (the engine's use_item_on factory)
# ---------------------------------------------------------------------------


def _hit_man(action):
    """HIT MAN/ZOMBIE WITH SHOVEL in the gardens: bash Dr. Honeycutt, break the
    shovel, and drop the keycard. Scores +5 only if he hasn't turned yet."""
    g = action.game
    gardens = g.locations["Gardens"]
    man = action.target
    if not man.get_property("zombified"):
        g.award("honeycutt", 5)
        line = (
            "Bashing the poor man's head in breaks the handle of the shovel. The "
            "broken shovel and the man fall to the ground. You got him before he "
            "turned."
        )
    else:
        line = (
            "You bash in the zombie's skull. The shovel handle snaps, and the "
            "zombie crumples to the ground."
        )
    man.set_property("dead", True)
    gardens.remove_character(man)
    keycard = things.Item(
        "keycard",
        "Dr. Honeycutt's keycard",
        'The name on the keycard reads "Dr. Brent Honeycutt." There\'s a '
        "magnetic strip on the back.",
    )
    keycard.add_command_hint("get keycard")
    keycard.add_command_hint("use keycard")
    gardens.add_item(keycard)
    g.parser.ok(line)


HitManWithShovel = actions.use_item_on(
    "hit man with shovel",
    item="shovel",
    target="man",
    verb="hit",
    preposition="with",
    description="Bash the man (Dr. Honeycutt) with the shovel",
    aliases=[
        "hit zombie with shovel",
        "kill man with shovel",
        "kill zombie with shovel",
        "attack man with shovel",
        "use shovel on man",
        "use shovel on zombie",
    ],
    effect=_hit_man,
    consume=True,  # the handle breaks
    item_missing="You've nothing to swing -- you need the shovel.",
    target_missing="There's no one here to hit.",
)


def _hook_zombie(action):
    """USE MEAT HOOK ON ZOMBIE in the kitchen: pierce the zombie clawing at the
    walk-in; the hook is left stuck in its skull, so it's consumed."""
    zombie = action.target
    action.character.location.remove_character(zombie)
    action.character.location.set_property("kitchen_clear", True)


UseMeatHookOnZombie = actions.use_item_on(
    "use meat hook on zombie",
    item="meat hook",
    target="zombie",
    verb="use",
    preposition="on",
    description="Drive the meat hook into the kitchen zombie",
    aliases=[
        "use hook on zombie",
        "hit zombie with meat hook",
        "kill zombie with meat hook",
        "use meat hook",
    ],
    effect=_hook_zombie,
    success="You pierce its brain and it falls down. The hook is now stuck.",
    consume=True,
    requires=lambda a: (
        "There's no zombie here." if a.character.location.name != "Kitchen" else None
    ),
    item_missing="You aren't holding the meat hook.",
    target_missing="There's no zombie here.",
)


def _plunge_zombie(action):
    """USE PLUNGER ON ZOMBIE in the restroom: stick the plunger to its face. With
    the way clear, the nurse comes out of her stall and flees. +10."""
    g = action.game
    restroom = action.character.location
    zombie = action.target
    restroom.remove_character(zombie)
    nurse = g.characters.get("nurse")
    if nurse is not None and nurse.location is restroom:
        restroom.remove_character(nurse)
        nurse.set_property("rescued", True)
    g.award("nurse", 10)


UsePlungerOnZombie = actions.use_item_on(
    "use plunger on zombie",
    item="plunger",
    target="zombie",
    verb="use",
    preposition="on",
    description="Stick the plunger to the lunging zombie's face",
    aliases=["use plunger", "use toilet plunger on zombie", "plunge zombie"],
    effect=_plunge_zombie,
    success=(
        "The plunger sticks to the zombie's face, rendering it harmless. From "
        'the far stall a voice calls out, "Is it safe now?" The nurse slips past '
        "you and flees toward the hospital entrance."
    ),
    consume=True,
    requires=lambda a: (
        "There's no zombie here." if a.character.location.name != "Restroom" else None
    ),
    item_missing="You aren't holding the plunger.",
    target_missing="There's no zombie here.",
)


def _sedate_chief(action):
    action.target.set_property("sedated", True)


UseSyringeOnChief = actions.use_item_on(
    "use syringe on chief of staff",
    item="syringe",
    target="chief of staff",
    verb="use",
    preposition="on",
    description="Inject the chief of staff with the sedative",
    aliases=[
        "use syringe on chief",
        "inject chief of staff",
        "inject chief",
        "use syringe",
        "sedate chief",
        "sedate chief of staff",
    ],
    effect=_sedate_chief,
    award=(
        "sedate",
        5,
        "You rush the doctor and inject him with the syringe before he can "
        "react. He murmurs something unintelligible, then slumps to the floor, "
        "out cold.",
    ),
    consume=True,  # the syringe is single-use
    requires=lambda a: (
        "There's no one here to sedate."
        if a.target is None
        else ("He's already out cold." if a.target.get_property("sedated") else None)
    ),
    item_missing="You haven't got the syringe.",
    target_missing="There's no one here to sedate.",
)


def _give_bunny(action):
    """GIVE BUNNY TO FRANCES: she emerges from the wall and collapses into your
    arms. She now needs the wheelchair before you can take her anywhere."""
    frances = action.target
    frances.set_property("emerged", True)
    frances.description = "Frances, weak and barely able to stand"


GiveBunnyToFrances = actions.use_item_on(
    "give bunny to frances",
    item="bunny",
    target="frances",
    verb="give",
    preposition="to",
    description="Give the stuffed bunny to Frances to coax her out",
    aliases=[
        "give stuffed bunny to frances",
        "give bunny to sister",
        "give frances the bunny",
        "show bunny to frances",
    ],
    effect=_give_bunny,
    success=(
        "Frances' eyes light up at the sight of her old stuffed bunny. She "
        "clutches it and lets you help her out of the cramped compartment, then "
        "collapses, exhausted, into your arms. She can't walk on her own -- "
        "you'll need to find something to carry her in."
    ),
    requires=lambda a: ("She's not here." if a.target is None else None),
    item_missing="You don't have the bunny.",
    target_missing="There's no one here named Frances.",
)


# ---------------------------------------------------------------------------
# Custom actions (the genuinely novel verbs)
# ---------------------------------------------------------------------------


class _Here(actions.Action):
    """Small base for the location-scoped verbs below: resolves the actor and
    the raw command, and guards that they're standing in ``ROOM``."""

    ROOM = None

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.command = command or ""
        self.character = self.acting_character(command)

    def _here(self) -> bool:
        return self.ROOM is None or self.character.location.name == self.ROOM


class ReadNote(_Here):
    ACTION_NAME = "read note"
    ACTION_DESCRIPTION = "Read the note from your sister"
    ACTION_ALIASES = [
        "examine note",
        "read the note",
        "examine the note",
        "read email",
        "read directions",
    ]

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "note"):
            self.parser.fail("You aren't holding any note.")
            return False
        return True

    def apply_effects(self):
        self.game.award(
            "read_note",
            5,
            "You read the poorly spelled email you received this morning from "
            'your sister: "halp zomby apokalips xoxo frances" Below that are your '
            "handwritten directions to this hospital.",
        )


class UseKeycard(_Here):
    ACTION_NAME = "use keycard"
    ACTION_DESCRIPTION = "Swipe the keycard on the office door reader"
    ACTION_ALIASES = ["swipe keycard", "use the keycard", "unlock office", "use card"]
    ROOM = "Hospital Intake"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no card reader here.")
            return False
        if not _is_holding(self.character, "keycard"):
            self.parser.fail("You haven't got a keycard.")
            return False
        return True

    def apply_effects(self):
        self.character.location.set_property("office_unlocked", True)
        self.parser.ok(
            'The message "Authorized" is displayed on the reader, and you hear '
            "the office door to the west unlock."
        )


class UseFireExtinguisher(_Here):
    ACTION_NAME = "use fire extinguisher"
    ACTION_DESCRIPTION = "Blast the elevator zombie with the fire extinguisher"
    ACTION_ALIASES = [
        "spray fire extinguisher",
        "use extinguisher",
        "use fire extinguisher on zombie",
        "freeze zombie",
    ]
    ROOM = "Hospital Intake"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's nothing here to spray.")
            return False
        if not _is_holding(self.character, "fire extinguisher"):
            self.parser.fail("You aren't holding the fire extinguisher.")
            return False
        return True

    def apply_effects(self):
        intake = self.character.location
        if intake.get_property("elevator_clear"):
            self.parser.ok("You've already cleared the elevator.")
            return
        intake.set_property("elevator_clear", True)
        elevator = self.game.locations.get("Elevator")
        zombie = elevator.characters.get("zombie") if elevator else None
        if zombie is not None:
            elevator.remove_character(zombie)
        # The extinguisher is spent (a single charge of CO2).
        ext = _all_held(self.character).get("fire extinguisher")
        if ext is not None:
            self.character.discard_item(ext)
        self.parser.ok(
            "The nozzle emits a blast of super-cold CO2, freezing the zombie "
            "clawing from inside the elevator. It shatters into chunks. The "
            "extinguisher sputters empty -- it only had the one charge."
        )


class SearchChief(_Here):
    ACTION_NAME = "search chief of staff"
    ACTION_DESCRIPTION = "Search the chief of staff"
    ACTION_ALIASES = ["search chief", "frisk chief", "search the chief", "loot chief"]
    ROOM = "Administrator's Office"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no one here to search.")
            return False
        return True

    def apply_effects(self):
        office = self.character.location
        chief = office.characters.get("chief of staff")
        if chief is None:
            self.parser.fail("There's no one here to search.")
            return
        if not chief.get_property("sedated"):
            self.game.end_in_death(
                '"Stay back! I\'m warning you!" the hysterical chief screams -- '
                "then panics and fires his revolver, hitting you square in the "
                "chest. THE END."
            )
            return
        if office.get_property("chief_searched"):
            self.parser.ok("You've already taken everything he had.")
            return
        office.set_property("chief_searched", True)
        key = things.Item("key", "a small padlock key", "It's a simple padlock key.")
        key.add_command_hint("get key")
        key.add_command_hint("unlock quiet room")
        revolver = things.Item(
            "revolver", "a small revolver", "There's one bullet left."
        )
        revolver.add_command_hint("get revolver")
        office.add_item(key)
        office.add_item(revolver)
        self.parser.ok("He is carrying a key and a revolver. You take them both.")


class ExamineCabinet(_Here):
    ACTION_NAME = "examine filing cabinet"
    ACTION_DESCRIPTION = "Examine the filing cabinet for your sister's file"
    ACTION_ALIASES = [
        "examine cabinet",
        "search filing cabinet",
        "search cabinet",
        "open filing cabinet",
        "look in filing cabinet",
        "get file",
    ]
    ROOM = "Administrator's Office"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no filing cabinet here.")
            return False
        return True

    def apply_effects(self):
        if _is_holding(self.character, "file"):
            self.parser.ok("You've already got your sister's file.")
            return
        file = things.Item(
            "file",
            "your sister's file",
            'The file is stamped "Test Subject Z." It seems Frances "had trouble '
            'adjusting" and was sent to the quiet room.',
        )
        file.add_command_hint("examine file")
        self.character.add_to_inventory(file)
        self.game.award(
            "file",
            5,
            "You rifle through the filing cabinet and find your sister's file. "
            "You tuck it away.",
        )


class OpenWalkIn(_Here):
    ACTION_NAME = "open walk-in"
    ACTION_DESCRIPTION = "Open the walk-in refrigerator"
    ACTION_ALIASES = [
        "open walkin",
        "open refrigerator",
        "open fridge",
        "open the walk-in",
        "open walk in",
    ]
    ROOM = "Kitchen"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no walk-in here.")
            return False
        if not self.character.location.get_property("kitchen_clear"):
            self.parser.fail(
                "A zombie is still clawing at the refrigerator door. You can't "
                "get to it."
            )
            return False
        return True

    def apply_effects(self):
        kitchen = self.character.location
        if kitchen.get_property("peggy_rescued"):
            self.parser.ok("The refrigerator already stands open.")
            return
        kitchen.set_property("peggy_rescued", True)
        peggy = self.game.characters.get("chef peggy")
        if peggy is not None:
            peggy.set_property("rescued", True)
        self.game.award(
            "peggy",
            10,
            "You heave the heavy door open and find Chef Peggy shivering inside. "
            '"You didn\'t eat anything, did you?" she asks. She thanks you, then '
            "hurries out toward the cafeteria to flee the hospital.",
        )


class PlayNight(_Here):
    ACTION_NAME = "play night of the living dead"
    ACTION_DESCRIPTION = "Spool Night of the Living Dead onto the projector"
    ACTION_ALIASES = [
        "play night of the living dead",
        "play living dead",
        "play night",
        "play notld",
        "play horror movie",
    ]
    ROOM = "Projector Room"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no projector here.")
            return False
        return True

    def apply_effects(self):
        aud = self.game.locations["Auditorium"]
        aud.set_property("pacified", True)
        self.game.auditorium_turns = 0
        pete = self.game.characters.get("pete")
        if pete is not None:
            pete.set_property("rescued", True)
        self.game.award(
            "pete",
            10,
            "The zombies in the theater below return to their seats to watch the "
            "movie, transfixed. It's safe to move through the auditorium now. "
            'Pete claps you on the back -- "I\'ve been hiding in here for days!" '
            "-- and slips out to safety.",
        )


class PlayBambi(_Here):
    ACTION_NAME = "play bambi"
    ACTION_DESCRIPTION = "Spool Bambi onto the projector"
    ACTION_ALIASES = ["play the bambi reel", "show bambi"]
    ROOM = "Projector Room"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no projector here.")
            return False
        return True

    def apply_effects(self):
        self.game.end_in_death(
            "The zombies become enraged when Bambi's mother dies. They break "
            "down the door and pour into the projection booth, killing everyone "
            "inside. THE END."
        )


class SetDial(_Here):
    ACTION_NAME = "set dial"
    ACTION_DESCRIPTION = "Set the EST machine's dial (off / low / medium / high)"
    ACTION_ALIASES = [
        "set dial to off",
        "set dial to low",
        "set dial to medium",
        "set dial to high",
        "turn dial to low",
        "turn dial to medium",
        "turn dial to high",
        "set est dial",
    ]
    ROOM = "EST Room"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no EST machine here.")
            return False
        return True

    def apply_effects(self):
        cmd = self.command.lower()
        est = self.character.location
        if "high" in cmd:
            # HIGH destroys the zombie (the chair is freed) but blows the
            # breakers -- so the wheelchair is gettable, just not for the +5.
            est.set_property("zombie_stunned", True)
            self.game.outage = True
            self.parser.ok(
                "The machine hums, and the zombie thrashes around. Something "
                "goes wrong: the machine starts to smoke and the electrodes "
                "catch fire! The zombie's eyes burst from their sockets and the "
                "power goes out! After a few seconds, the lights flicker back "
                "on -- but you've fried the breakers. So much for keeping things "
                "quiet."
            )
        elif "medium" in cmd:
            est.set_property("zombie_stunned", True)
            self.parser.ok(
                "The machine hums, the lights flicker and the zombie jerks "
                "around. It looks dazed, unaware of its surroundings. You could "
                "pull it from the chair now."
            )
        elif "low" in cmd:
            self.parser.ok("The machine hums, but the zombie seems unaffected.")
        else:
            est.set_property("zombie_stunned", False)
            self.parser.ok("You switch the dial to Off. The machine falls silent.")


class GetWheelchair(_Here):
    ACTION_NAME = "get wheelchair"
    ACTION_DESCRIPTION = "Pull the stunned zombie out and take the wheelchair"
    ACTION_ALIASES = [
        "take wheelchair",
        "get the wheelchair",
        "take the wheelchair",
        "remove zombie from wheelchair",
        "free wheelchair",
    ]
    ROOM = "EST Room"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no wheelchair here.")
            return False
        if _is_holding(self.character, "wheelchair"):
            self.parser.fail("You already have the wheelchair.")
            return False
        if not self.character.location.get_property("zombie_stunned"):
            self.parser.fail(
                "The zombie is still strapped in and thrashing -- you can't use "
                "the wheelchair while it's occupied. Stun it first."
            )
            return False
        return True

    def apply_effects(self):
        wheelchair = things.Item(
            "wheelchair",
            "an old but sturdy wheelchair",
            "The wheelchair is old but in good condition -- just the thing to "
            "move someone who can't walk.",
        )
        wheelchair.add_command_hint("put frances in wheelchair")
        self.character.add_to_inventory(wheelchair)
        if not self.game.outage:
            self.game.award(
                "no_outage",
                5,
                "You drag the dazed zombie out of the chair and wheel the "
                "wheelchair free -- no fuss, no blown breakers.",
            )
        else:
            self.parser.ok(
                "You drag the dazed zombie out of the chair and take the " "wheelchair."
            )


class RemovePanel(_Here):
    ACTION_NAME = "remove panel"
    ACTION_DESCRIPTION = "Pull the loose panel out of the padded wall"
    ACTION_ALIASES = [
        "remove wall panel",
        "pull panel",
        "open panel",
        "remove the panel",
        "pry panel",
    ]
    ROOM = "Quiet Room"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no loose panel here.")
            return False
        if self.character.location.get_property("panel_removed"):
            self.parser.fail("The panel already lies on the floor.")
            return False
        return True

    def apply_effects(self):
        quiet = self.character.location
        quiet.set_property("panel_removed", True)
        frances = self.game.characters.get("frances")
        if frances is not None:
            quiet.add_character(frances)
        self.game.award(
            "frances_wall",
            10,
            "You pull the panel out of the wall, revealing a secret "
            "compartment. Your sister, Frances, is hiding inside!",
        )


class PutFrancesInWheelchair(_Here):
    ACTION_NAME = "put frances in wheelchair"
    ACTION_DESCRIPTION = "Settle Frances into the wheelchair"
    ACTION_ALIASES = [
        "put frances in the wheelchair",
        "place frances in wheelchair",
        "seat frances",
        "put sister in wheelchair",
        "use wheelchair on frances",
    ]

    def check_preconditions(self) -> bool:
        frances = self.character.location.characters.get("frances")
        if frances is None:
            self.parser.fail("Frances isn't here.")
            return False
        if not frances.get_property("emerged"):
            self.parser.fail(
                "Frances won't come out of her hiding place. Maybe something "
                "familiar would coax her out."
            )
            return False
        if not _is_holding(self.character, "wheelchair"):
            self.parser.fail("You haven't got anything to carry her in.")
            return False
        if frances.get_property("in_wheelchair"):
            self.parser.fail("She's already settled in the wheelchair.")
            return False
        return True

    def apply_effects(self):
        frances = self.character.location.characters.get("frances")
        frances.set_property("in_wheelchair", True)
        frances.following = self.character  # she rolls along wherever you go
        self.parser.ok(
            "You gently settle Frances into the wheelchair. She's safe now -- "
            "now to get her out of here. The stairs are no good with the chair; "
            "you'll have to take the elevator."
        )


class WatchTelevision(_Here):
    ACTION_NAME = "watch television"
    ACTION_DESCRIPTION = "Watch the television in the group therapy room"
    ACTION_ALIASES = ["watch tv", "watch the television", "look at television"]
    ROOM = "Group Therapy Room"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no television here.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "A blonde woman on screen is reporting from outside a wrought-iron "
            'gate. In the distance is a large manor. "Authorities investigate '
            'report of missing courier..." The zombie beside you stares at the '
            "screen, slack-jawed and harmless."
        )


class TurnOffTelevision(_Here):
    ACTION_NAME = "turn off television"
    ACTION_DESCRIPTION = "Turn off the television"
    ACTION_ALIASES = [
        "turn off tv",
        "turn off the television",
        "switch off television",
        "turn off the tv",
    ]
    ROOM = "Group Therapy Room"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no television here.")
            return False
        return True

    def apply_effects(self):
        self.game.end_in_death(
            "The screen goes dark. Deprived of its show, the zombie gets up, "
            "turns its hungry eyes on you, and attacks before you can react. "
            "THE END."
        )


class UnlockQuietRoom(_Here):
    ACTION_NAME = "unlock quiet room"
    ACTION_DESCRIPTION = "Unlock the padlocked Quiet Room door with the key"
    ACTION_ALIASES = [
        "unlock door",
        "use key on door",
        "use key on padlock",
        "unlock padlock",
        "open quiet room",
        "unlock the quiet room",
    ]
    ROOM = "Examination Room"

    def check_preconditions(self) -> bool:
        if not self._here():
            self.parser.fail("There's no padlocked door here.")
            return False
        if not _is_holding(self.character, "key"):
            self.parser.fail("It's padlocked. You'll need a key.")
            return False
        return True

    def apply_effects(self):
        exam = self.character.location
        if exam.get_property("quiet_unlocked"):
            self.parser.ok("The Quiet Room door already stands unlocked.")
            return
        exam.set_property("quiet_unlocked", True)
        self.parser.ok(
            "The padlock key turns and the heavy door to the Quiet Room clicks " "open."
        )


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> ZWard:
    L = things.Location

    entrance = L(
        "Hospital Entrance",
        "You're outside the hospital where your sister was admitted nine weeks "
        "ago. You may enter to the north. The hospital grounds continue east. "
        "You're holding a note.",
    )
    gardens = L(
        "Gardens",
        "You are in the gardens. Someone's been digging graves. There is a "
        "shovel here. A man staggers nearby. The hospital entrance is west.",
    )
    intake = L(
        "Hospital Intake",
        "You are in the hospital intake, where patients are admitted. A small "
        "fire extinguisher hangs on the blood-spattered wall. There is an "
        "elevator here. Stairs lead up. Doors lead south, west and east.",
    )
    elevator = L(
        "Elevator",
        "You are in the elevator. There is a control panel here with buttons "
        "for floors (1) and (2).",
    )
    office = L(
        "Administrator's Office",
        "You are in the administrator's office. There is a personal computer "
        "here and a filing cabinet. The way out is east.",
    )
    cafeteria = L(
        "Cafeteria",
        "You are standing in a large cafeteria. Flies buzz around half-eaten "
        "trays of food. Several corpses litter the floor. The kitchen is to the "
        "east, a darker room lies to the north, and the intake is west.",
    )
    kitchen = L(
        "Kitchen",
        "You are in the hospital's kitchen. There's a meat hook next to a meat "
        "grinder. A zombie claws at the door of a walk-in refrigerator. The "
        "cafeteria is west.",
    )
    auditorium = L(
        "Auditorium",
        "The theater is filled with the shuffling bodies of zombified patients "
        "and staff! The light from a film projector illuminates a large screen, "
        "and the shufflers gaze at it, transfixed. A short set of stairs leads "
        "up to the projector room. The cafeteria is south. Don't linger -- if "
        "they notice you, they'll close in.",
    )
    projector = L(
        "Projector Room",
        "You're standing by an electrical panel next to a film projector. Pete, "
        "the orderly, is here. There are two film reels here: Bambi and Night of "
        "the Living Dead. The way out is back down to the auditorium.",
    )
    group = L(
        "Group Therapy Room",
        "You are in the group therapy room. Stairs lead down. There's an "
        "elevator here. A bathroom is north, with exits east and west. A zombie "
        "sits watching television with its mouth wide open.",
    )
    sleeping = L(
        "Sleeping Quarters",
        "This dimly lit room is filled with small cots. Beneath one is a stuffed "
        "bunny and a child's chalk drawing. The way out is back east.",
    )
    restroom = L(
        "Restroom",
        "You are in the restroom. Bloody footprints lead into one stall; a pair "
        "of white nurse's shoes is visible under another. There's a toilet "
        "plunger here, and a pants-less zombie lurching at you. The way out is "
        "south.",
    )
    exam = L(
        "Examination Room",
        "You are in one of the hospital's examination rooms. At the north side "
        'is a padlocked door with a sign reading "Quiet Room." There is a '
        "syringe here. Exits are east and west.",
    )
    quiet = L(
        "Quiet Room",
        "You stand in a padded cell. One wall panel has a deep rip in the "
        "padding. A straitjacketed zombie is here, staring off into space. The "
        "way out is south.",
    )
    est = L(
        "EST Room",
        "You're in the electroshock therapy room. A zombie is strapped into a "
        "wheelchair, electrodes running from its skull to a nearby machine with "
        "a four-setting dial. The way out is west.",
    )

    # --- Connections -------------------------------------------------------
    # Clean canonical pairs (auto-reverse is exactly what we want).
    entrance.add_connection("north", intake)  # intake --south--> entrance
    entrance.add_connection("east", gardens)  # gardens --west--> entrance
    intake.add_connection("east", cafeteria)  # cafeteria --west--> intake
    intake.add_connection("up", group)  # group --down--> intake (the stairs)
    cafeteria.add_connection("east", kitchen)  # kitchen --west--> cafeteria
    cafeteria.add_connection("north", auditorium)  # auditorium --south--> cafeteria
    group.add_connection("east", exam)  # exam --west--> group

    # Named / non-opposite exits: wire by hand so no auto-reverse collides.
    _one_way(intake, "west", office)
    _one_way(office, "out", intake)
    _one_way(intake, "elevator", elevator)
    _one_way(group, "elevator", elevator)
    _one_way(elevator, "press 1", intake)
    _one_way(elevator, "press 2", group)
    _one_way(auditorium, "up", projector)
    _one_way(projector, "out", auditorium)
    _one_way(group, "north", restroom)
    _one_way(restroom, "out", group)
    _one_way(group, "west", sleeping)
    _one_way(sleeping, "out", group)
    _one_way(exam, "east", est)
    _one_way(est, "out", exam)
    _one_way(exam, "north", quiet)
    _one_way(quiet, "out", exam)

    # --- Item helpers ------------------------------------------------------
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

    # Gardens.
    gettable(
        "shovel",
        "a shovel",
        "It's a shovel, a staple of any good horror-themed scenario.",
        gardens,
        ["get shovel", "hit man with shovel"],
    )
    # Hospital Intake.
    gettable(
        "fire extinguisher",
        "a small fire extinguisher",
        "This extinguisher contains carbon dioxide, a nonflammable gas. There's "
        "a warning not to spray people with it. It looks good for one blast.",
        intake,
        ["get fire extinguisher", "use fire extinguisher"],
    )
    scenery(
        "elevator panel",
        "the elevator's call panel",
        "Buttons for floors (1) and (2). Step in and PRESS 1 or PRESS 2.",
        intake,
    )
    # Office.
    scenery(
        "computer",
        "a personal computer",
        "You read a memo about a drug designed to treat antisocial behavior. The "
        "hospital was selected to host the first trials of the drug.",
        office,
        ["examine computer"],
    )
    scenery(
        "filing cabinet",
        "a metal filing cabinet",
        "A dented filing cabinet. Your sister's file might be in here.",
        office,
        ["examine filing cabinet"],
    )
    # Cafeteria.
    scenery(
        "trays",
        "half-eaten trays of food",
        "Looks like it was meatloaf day.",
        cafeteria,
    )
    scenery(
        "corpses",
        "several corpses",
        "They're dead. They're all messed up.",
        cafeteria,
    )
    # Kitchen.
    gettable(
        "meat hook",
        "a meat hook",
        "A hook used to grab sides of meat.",
        kitchen,
        ["get meat hook", "use meat hook on zombie"],
    )
    scenery(
        "walk-in",
        "a walk-in refrigerator",
        "A heavy refrigerator door. Something -- or someone -- might be inside.",
        kitchen,
        ["open walk-in"],
    )
    # Auditorium.
    scenery(
        "screen",
        "a large film screen",
        "The screen flickers with the light of the projector overhead, holding "
        "the shuffling crowd's attention.",
        auditorium,
    )
    # Projector Room.
    scenery(
        "projector",
        "an old film projector",
        "An old-fashioned movie projector. You could spool a reel onto it.",
        projector,
        ["play night of the living dead", "play bambi"],
    )
    scenery(
        "film reels",
        "two film reels",
        "Two classic movies: Bambi and Night of the Living Dead. They're too "
        "cumbersome to carry, but you could spool one onto the projector.",
        projector,
        ["play night of the living dead", "play bambi"],
    )
    scenery(
        "electrical panel",
        "an electrical panel",
        "A master reset switch for the circuit breakers. The power's on for now.",
        projector,
    )
    # Group Therapy Room.
    scenery(
        "television",
        "a flickering television",
        "A news broadcast plays. The watching zombie is rapt -- best leave it on.",
        group,
        ["watch television"],
    )
    # Sleeping Quarters.
    gettable(
        "bunny",
        "a stuffed bunny",
        "You gave this to your sister before she went away.",
        sleeping,
        ["get bunny", "give bunny to frances"],
    )
    scenery(
        "drawing",
        "a child's chalk drawing",
        "It's a child's drawing of an iguana. The name \"Lulu\" is written next "
        "to it.",
        sleeping,
    )
    # Restroom.
    gettable(
        "plunger",
        "a toilet plunger",
        "A rubber toilet plunger on a wooden handle.",
        restroom,
        ["get plunger", "use plunger on zombie"],
    )
    # Examination Room.
    gettable(
        "syringe",
        "a syringe",
        "The syringe contains a powerful sedative. It can be used once, and it "
        "won't affect zombies.",
        exam,
        ["get syringe", "use syringe on chief of staff"],
    )
    scenery(
        "sign",
        "a sign on the padlocked door",
        'It reads "Quiet Room."',
        exam,
    )
    # EST Room.
    scenery(
        "est machine",
        "the EST machine",
        "It administers electrical currents to a patient's brain. A dial has "
        "four settings: Off, Low, Medium and High. It's currently set to Off.",
        est,
        ["set dial to medium"],
    )

    # --- Characters --------------------------------------------------------
    player = things.Character(
        "The player",
        "the frantic sibling of a hospital patient",
        "I have to find my sister Frances and get us both out of here alive.",
    )
    note = things.Item(
        "note",
        "a crumpled note",
        "Your sister's email and your directions to the hospital.",
    )
    note.add_command_hint("read note")
    player.add_to_inventory(note)

    # The gardens man (Dr. Honeycutt). Stays a "man" by name throughout so HIT
    # MAN WITH SHOVEL resolves whether or not he's turned; the description flips
    # to zombie flavor if you enter the hospital before dealing with him.
    man = things.Character(
        "man",
        "a man in a white coat, staggering",
        "Uhh... so hungry...",
    )
    man.examine_text = (
        "He is dressed in a white coat with a keycard clipped to the pocket. "
        "There is a ragged tear in his throat; blood is everywhere."
    )
    man.talk_text = "The only person who should be talking to this man is a priest."
    gardens.add_character(man)

    chief = things.Character(
        "chief of staff",
        "the hysterical chief of staff, cowering behind the filing cabinet",
        "Stay back! I'm warning you!",
    )
    chief.examine_text = (
        'The hysterical chief of staff yells, "Stay back! I\'m warning you!" He '
        "holds a small revolver. Although he's not a zombie, he'll open fire "
        "unless he's sedated."
    )
    chief.talk_text = '"Stay back! Don\'t come any closer!"'
    office.add_character(chief)

    peggy = things.Character(
        "chef peggy",
        "Chef Peggy, in a white apron",
        "Did anyone eat the meatloaf? Please say no.",
    )
    peggy.examine_text = (
        'She\'s wearing a white apron and a nametag that reads "Chef Peggy."'
    )
    peggy.talk_text = '"You didn\'t eat anything, did you?"'
    peggy.talk_topics = {
        "meatloaf": '"The chief of staff told me to add Vitamin Z to the '
        "meatloaf. He said it would calm down the difficult patients. After "
        'that, everything just went to hell."',
        "vitamin z": "\"That's what they put in the meatloaf. After that, "
        'everything went to hell."',
    }

    pete = things.Character(
        "pete",
        "Pete, a hospital orderly",
        "I've been hiding in here for days!",
    )
    pete.examine_text = (
        "Pete wears the white uniform of a hospital orderly. \"I've been hiding "
        'in here for days!"'
    )
    pete.talk_text = '"You here to get me out? Bless you."'
    projector.add_character(pete)

    nurse = things.Character(
        "nurse",
        "a nurse hiding in a stall",
        "Is it safe to come out?",
    )
    nurse.examine_text = (
        "A pair of feet in nurse's shoes. A voice asks, \"Is it safe to come " 'out?"'
    )
    nurse.talk_text = '"Is it safe? Please tell me it\'s safe."'
    nurse.talk_topics = {
        "meatloaf": "\"I'm vegan. I don't eat meatloaf.\"",
        "quiet room": "\"It's just down the hall. You'll need a key to get in.\"",
    }
    restroom.add_character(nurse)

    # Frances starts offstage -- revealed by REMOVE PANEL in the Quiet Room.
    frances = things.Character(
        "frances",
        "Frances, hidden in the wall",
        "Is someone there? I've been so scared.",
    )
    frances.examine_text = (
        "Frances is weak, dehydrated and terrified, clutching at the secret "
        "compartment she's been hiding in."
    )
    frances.talk_text = '"You came for me. I knew you would."'

    # The room-only zombies (kitchen, restroom, elevator, quiet room, EST). They
    # are NOT registered in game.characters -- each is named "zombie" so the
    # two-object verbs resolve "zombie" room-scoped, and keeping them out of the
    # global roster avoids a name collision (the roster is name-keyed).
    kitchen.add_character(
        things.Character("zombie", "a zombie clawing at the walk-in", "Braaains.")
    )
    restroom.add_character(
        things.Character("zombie", "a pants-less zombie", "Braaains.")
    )
    elevator.add_character(
        things.Character("zombie", "a zombie clawing from the elevator", "Braaains.")
    )
    quiet.add_character(
        things.Character("zombie", "a straitjacketed zombie, staring into space", "...")
    )
    est.add_character(
        things.Character("zombie", "a zombie strapped into the wheelchair", "Mmmnnghh.")
    )

    # --- Assemble ----------------------------------------------------------
    custom_actions = [
        HitManWithShovel,
        UseMeatHookOnZombie,
        UsePlungerOnZombie,
        UseSyringeOnChief,
        GiveBunnyToFrances,
        ReadNote,
        UseKeycard,
        UseFireExtinguisher,
        SearchChief,
        ExamineCabinet,
        OpenWalkIn,
        PlayNight,
        PlayBambi,
        SetDial,
        GetWheelchair,
        RemovePanel,
        PutFrancesInWheelchair,
        WatchTelevision,
        TurnOffTelevision,
        UnlockQuietRoom,
    ]
    characters = [man, chief, peggy, pete, nurse, frances]
    game = ZWard(entrance, player, characters, custom_actions)

    # Register every room by name -- several hang off named one-way exits, and
    # the custom actions / set-pieces look rooms up by name.
    for loc in (
        entrance,
        gardens,
        intake,
        elevator,
        office,
        cafeteria,
        kitchen,
        auditorium,
        projector,
        group,
        sleeping,
        restroom,
        exam,
        quiet,
        est,
    ):
        game.locations.setdefault(loc.name, loc)

    # --- Gates (blocks) ----------------------------------------------------
    intake.add_block(
        "west",
        CondBlock(
            "The office door is locked. You need a keycard to enter. (USE " "KEYCARD)",
            lambda: not intake.get_property("office_unlocked"),
        ),
    )
    intake.add_block(
        "elevator",
        CondBlock(
            "A zombie claws at you from inside the elevator! You'd better "
            "neutralize it before riding.",
            lambda: not intake.get_property("elevator_clear"),
        ),
    )
    group.add_block(
        "elevator",
        CondBlock(
            "The elevator won't come -- there's still a zombie loose in the "
            "shaft on the floor below.",
            lambda: not intake.get_property("elevator_clear"),
        ),
    )
    exam.add_block(
        "north",
        CondBlock(
            "The Quiet Room door is padlocked. (UNLOCK QUIET ROOM)",
            lambda: not exam.get_property("quiet_unlocked"),
        ),
    )

    # The wheelchair can't take the stairs -- once Frances is aboard, the stair
    # exits are barred and you must use the elevator (page 254).
    def _escorting():
        f = game.characters.get("frances")
        return f is not None and f.get_property("in_wheelchair")

    group.add_block(
        "down",
        CondBlock(
            "You can't push the wheelchair down the stairs. You'll have to take "
            "the elevator.",
            _escorting,
        ),
    )
    intake.add_block(
        "up",
        CondBlock(
            "You can't push the wheelchair up the stairs. Take the elevator.",
            _escorting,
        ),
    )

    return game


# ---------------------------------------------------------------------------
# Walkthrough (also the win test) -- wins 100/100
# ---------------------------------------------------------------------------

WALKTHROUGH = [
    "read note",  # +5 read_note
    "east",  # -> Gardens
    "get shovel",
    "hit man with shovel",  # +5 honeycutt (before he turns)
    "get keycard",
    "west",  # -> Hospital Entrance
    "north",  # -> Hospital Intake
    "get fire extinguisher",
    "use fire extinguisher",  # clear the elevator zombie
    "use keycard",  # unlock the office (west)
    # Floor-1 rescues: Chef Peggy and Pete.
    "east",  # -> Cafeteria
    "east",  # -> Kitchen
    "get meat hook",
    "use meat hook on zombie",  # clear the kitchen zombie
    "open walk-in",  # +10 peggy
    "west",  # -> Cafeteria
    "north",  # -> Auditorium (don't linger)
    "up",  # -> Projector Room
    "play night of the living dead",  # +10 pete; pacifies the horde
    "out",  # -> Auditorium (now safe)
    "south",  # -> Cafeteria
    "west",  # -> Hospital Intake
    # Floor 2: nurse, bunny, syringe, wheelchair.
    "up",  # -> Group Therapy Room
    "west",  # -> Sleeping Quarters
    "get bunny",
    "out",  # -> Group Therapy Room
    "north",  # -> Restroom
    "get plunger",
    "use plunger on zombie",  # +10 nurse
    "out",  # -> Group Therapy Room
    "east",  # -> Examination Room
    "get syringe",
    "east",  # -> EST Room
    "set dial to medium",  # stun the strapped zombie (NOT high -> no outage)
    "get wheelchair",  # +5 no_outage
    "out",  # -> Examination Room
    "west",  # -> Group Therapy Room
    # Down to the office: sedate the chief, grab the key and the file.
    "down",  # -> Hospital Intake (stairs; not escorting yet)
    "west",  # -> Administrator's Office
    "use syringe on chief of staff",  # +5 sedate
    "search chief of staff",  # drops key + revolver
    "get key",
    "examine filing cabinet",  # +5 file
    "out",  # -> Hospital Intake
    # Back up to the Quiet Room to rescue Frances.
    "up",  # -> Group Therapy Room
    "east",  # -> Examination Room
    "unlock quiet room",  # padlock open
    "north",  # -> Quiet Room
    "remove panel",  # +10 frances_wall
    "give bunny to frances",  # Frances emerges, can't walk
    "put frances in wheelchair",  # she's secured; now escorting
    "out",  # -> Examination Room
    "west",  # -> Group Therapy Room
    "elevator",  # -> Elevator (+5 frances_elevator)
    "press 1",  # -> Hospital Intake
    "south",  # -> Hospital Entrance: +25 escape, +5 finish -> VICTORY
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
