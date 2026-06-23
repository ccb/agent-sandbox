"""Space Station -- a Parsely game ported to the text_adventure_games engine.

Two months ago the station was evacuated ahead of a Frellion attack -- but you
slept through the alarm in a cryosleep capsule. Now the warship is parked outside
hammering the shields, and a green PARSEC technician (you) has to bring the dead
station back to life and run for the last escape pod: jab yourself awake with the
hypoinjector, scrub the CPU core's cooling vanes so the computers reboot, splice
the burnt-out sensor array so the comm terminal can hear the aliens, translate
their hail and *surrender*, drop the shields, have your repair robot FROZ shut
down the torpedo-cracked reactor and yank the jammed pod-bay lever, then suit up
and launch -- ideally with FROZ aboard. Source: Parsely "Space Station".

Authored the way the reference ports are (see ``action_castle_2.py`` and
``docs/converting-parsely-games.md``): a ``build_game()`` assembling the world, a
small ``SpaceStation`` Game subclass holding the win/score logic plus the two
environmental hazards that the rulebook layers on after the shields drop
(zero-gravity, and radiation flooding the flight deck), the tool-on-fixture verbs
via the engine's ``use_item_on`` factory, and custom ``Action`` subclasses for the
genuinely novel verbs (the multi-dose hypoinjector, the comm terminal, ordering
FROZ around, the launch button).

Run interactively:    uv run python -m test_gen.space_station.space_station
Run the walkthrough:  uv run python -m test_gen.space_station.space_station --walk
"""

from text_adventure_games import games, things, actions, blocks

# ---------------------------------------------------------------------------
# Helpers (mirroring the reference ports' kit)
# ---------------------------------------------------------------------------


def _all_held(character):
    """Everything the character has on them: inventory + worn + wielded. WEAR
    moves an item out of ``inventory`` into ``worn``, so quest checks ("are you
    still carrying the mag boots?") must look at the union, not bare inventory."""
    return {**character.inventory, **character.worn, **character.wielded}


def _is_holding(character, name):
    return name in _all_held(character)


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s canonical auto-reverse, so a
    named door ("enter transporter room") doesn't silently wire a reverse that
    collides with another exit. (See the same helper in action_castle_2.py.)"""
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


def _gloved(action):
    """The spacesuit's bulky gloves lock you out of every control but the escape
    pod's launch button (page 210). Return a refusal string while suited up, else
    None. Custom control verbs call this from check_preconditions."""
    if "spacesuit" in action.game.player.worn:
        return "The spacesuit's bulky gloves are far too clumsy for that."
    return None


# ---------------------------------------------------------------------------
# Game subclass: win/score logic + the post-shield-drop hazards
# ---------------------------------------------------------------------------


class SpaceStation(games.Game):
    """Won by launching the escape pod -- shields down, pod-bay doors unlocked,
    spacesuit on -- *after* surrendering, so the Frellions let PARSEC recover you
    instead of shooting you down. Every other ending (heart-exploding overdose,
    floating off in zero-g, frying on the irradiated flight deck, an
    untrained transporter jump, launching into a closed door) is a loss."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        # Scoring table (max 100): hypo 10, sensor 10, cpu 10, translate 10,
        # shields 10, reactor 10, doors 10, escape 10, froz 5, rescued 10,
        # finish 5.  score / _scored_keys / award() come from the base Game.
        self.max_score = 100

        # --- station / puzzle state ---
        self.can_move = False  # set once the first hypo dose wears off cryo-sickness
        self.hypo_doses = 0
        self.super_strength_turns = 0  # 2nd dose: brief superhuman strength
        self.cpu_rebooted = False
        self.sensor_repaired = False
        self.translated = False
        self.surrendered = False
        self.shields_lowered = False  # implies zero-g + a damaged reactor
        self.reactor_damaged = False
        self.reactor_fixed = False
        self.doors_unlocked = False
        self.reactor_warned = False
        self.vulcan_said = False

    # -- environmental hazards keyed to arriving in a room -------------------

    def do_command(self, command: str) -> bool:
        before = self.player.location
        success = super().do_command(command)
        after = self.player.location
        if success and after is not None and after is not before:
            self._on_arrive(after)
        return success

    def _on_arrive(self, room):
        # Zero-g (after the torpedo knocks out the gravity drive): without the
        # mag boots anchoring you, you drift helplessly until the boarding party
        # scoops you up (page 205).
        if self.shields_lowered and "mag boots" not in self.player.worn:
            self.end_in_death(
                "Without the mag boots you float helplessly through the corridor. "
                "You're still drifting when the Frellion boarding party arrives, "
                "and you're hauled off to a life in the salt mines. THE END."
            )
            return
        # The lowered shields let a torpedo crack the reactor; until FROZ shuts
        # it down, lethal radiation floods the flight-deck level -- survivable
        # only in the spacesuit (page 207).
        if (
            self.reactor_damaged
            and not self.reactor_fixed
            and room.name in ("Flight Deck", "Transporter Room", "Escape Pod")
            and "spacesuit" not in self.player.worn
        ):
            self.end_in_death(
                "Radiation from the damaged reactor floods the flight deck. "
                "Without a spacesuit you receive a lethal dose. THE END."
            )

    # -- win ---------------------------------------------------------------

    def is_won(self) -> bool:
        if self.player.get_property("rescued"):
            # +5 for finishing without saving (page 84-style completion bonus).
            self.award("finish", 5)
            self.announce_ending(
                "Within days a PARSEC rescue ship picks up your pod and returns "
                "you to Earth. Thank you for playing Space Station! THE END.",
                show_score=True,
            )
            return True
        return False


# ---------------------------------------------------------------------------
# Tool-on-fixture verbs (the engine's use_item_on factory)
# ---------------------------------------------------------------------------


def _clean_vanes(action):
    action.game.cpu_rebooted = True


CleanVanes = actions.use_item_on(
    "clean vanes",
    item="mop",
    target="vanes",
    verb="clean",
    preposition="with",
    description="Climb the ladders and scrub the CPU core's cooling vanes",
    aliases=[
        "clean cooling vanes",
        "clean the vanes",
        "use mop on vanes",
        "mop vanes",
        "wipe vanes",
    ],
    effect=_clean_vanes,
    award=(
        "cpu",
        10,
        "You climb the ladders and wipe months of grime from the cooling vanes "
        "at every level. The CPU core chimes as its systems reboot.",
    ),
    requires=lambda a: (
        _gloved(a)
        or ("The CPU core is already running cool." if a.game.cpu_rebooted else None)
    ),
    item_missing="You need something to scrub the vanes with -- a mop, maybe.",
    target_missing="There are no cooling vanes here. They ring the CPU core.",
)


def _repair_panel(action):
    action.game.sensor_repaired = True


RepairPanel = actions.use_item_on(
    "repair panel",
    item="microtools",
    target="panel",
    verb="repair",
    preposition="with",
    description="Splice the sensor array's shorted wiring with the microtools",
    aliases=[
        "repair sensor array",
        "fix panel",
        "fix the panel",
        "repair the panel",
        "use microtools on panel",
    ],
    effect=_repair_panel,
    award=(
        "sensor",
        10,
        "You splice the shorted signal-receiver wiring back together. The sensor "
        "array hums to life; the station can hear incoming signals again.",
    ),
    requires=lambda a: (
        _gloved(a)
        or (
            "There's nothing to repair here."
            if a.character.location.name != "Sensor Array"
            else (
                "The sensor array's already fixed." if a.game.sensor_repaired else None
            )
        )
    ),
    item_missing="You'd need a set of fine tools to fix the wiring.",
    target_missing="There's no panel here to work on.",
)


# ---------------------------------------------------------------------------
# Custom actions
# ---------------------------------------------------------------------------


class UseHypoinjector(actions.Action):
    """The strength serum, three doses deep (page 197). First dose shakes off the
    cryo-sickness so you can walk; second grants a few turns of superhuman
    strength (enough to free the jammed pod-bay lever); a third stops your
    heart."""

    ACTION_NAME = "use hypoinjector"
    ACTION_DESCRIPTION = "Inject a dose of the strength serum"
    ACTION_ALIASES = [
        "inject",
        "inject self",
        "inject serum",
        "use the hypoinjector",
        "use hypo",
        "use serum",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        glove = _gloved(self)
        if glove:
            self.parser.fail(glove)
            return False
        if not _is_holding(self.character, "hypoinjector"):
            self.parser.fail("You don't have the hypoinjector.")
            return False
        return True

    def apply_effects(self):
        g = self.game
        g.hypo_doses += 1
        if g.hypo_doses == 1:
            g.can_move = True
            self.parser.ok(
                "You press the hypoinjector to your neck. Strength floods back "
                "into your limbs -- you can stand and move about the station now."
            )
            g.award("hypo", 10)
        elif g.hypo_doses == 2:
            g.super_strength_turns = 4
            self.parser.ok(
                "A second dose surges through you. For a short while you feel "
                "superhuman -- strong enough to force something badly stuck."
            )
        else:
            g.end_in_death(
                "A third dose is far too much. The serum sends your heart racing "
                "until it explodes. THE END."
            )


class LowerShields(actions.Action):
    """Drop the station shields so the pod can launch -- which invites the next
    torpedo through (page 205): the gravity drive fails and the reactor cracks."""

    ACTION_NAME = "lower shields"
    ACTION_DESCRIPTION = "Lower the station's shields at the generator controls"
    ACTION_ALIASES = ["lower the shields", "lower shield", "drop shields"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        glove = _gloved(self)
        if glove:
            self.parser.fail(glove)
            return False
        if self.character.location.name != "Shield Generator":
            self.parser.fail("There are no shield controls here.")
            return False
        if self.game.shields_lowered:
            self.parser.fail("The shields are already down.")
            return False
        return True

    def apply_effects(self):
        g = self.game
        g.shields_lowered = True
        g.reactor_damaged = True
        self.parser.ok(
            "You lower the shields. At once a torpedo slams into the station! "
            "Sparks erupt from the panel, the gravity drive fails and you begin "
            'to float. A klaxon blares: "Warning! Reactor damaged! Flight deck '
            'radiation at hazardous levels!"'
        )
        g.award("shields", 10)


class ExamineCommTerminal(actions.Action):
    """The comm terminal on the command deck, whose message depends on how much
    of the station you've brought back online (page 200)."""

    ACTION_NAME = "examine comm terminal"
    ACTION_DESCRIPTION = "Read the command deck's comm terminal"
    ACTION_ALIASES = [
        "examine comm",
        "examine terminal",
        "look at comm terminal",
        "read comm terminal",
        "x comm terminal",
        "check comm terminal",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Command Deck":
            self.parser.fail("There's no comm terminal here.")
            return False
        return True

    def apply_effects(self):
        g = self.game
        if not g.cpu_rebooted:
            self.parser.ok(
                'The comm terminal is dark. A message blinks: "CPU Offline."'
            )
        elif not g.sensor_repaired:
            self.parser.ok(
                'The comm terminal glows but a message blinks: "No Signal." Without '
                "a working sensor array nothing is getting through."
            )
        elif not g.translated:
            self.parser.ok(
                'The comm terminal flashes: "Incoming message, unknown language. '
                'Please input language to translate." (Try INPUT FRELLION.)'
            )
        elif not g.surrendered:
            self.parser.ok(
                "The Frellions are demanding your surrender or they'll fire the "
                "gravity cannon. (Try SURRENDER.)"
            )
        else:
            self.parser.ok(
                "The Frellions have acknowledged your surrender and are readying "
                "a boarding party."
            )


class InputFrellion(actions.Action):
    """Translate the aliens' hail (page 200). Only possible once the CPU is back
    and the sensor array can receive."""

    ACTION_NAME = "input frellion"
    ACTION_DESCRIPTION = "Translate the incoming message as Frellion"
    ACTION_ALIASES = [
        "input frellion language",
        "select frellion",
        "translate message",
        "translate",
        "input language frellion",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        glove = _gloved(self)
        if glove:
            self.parser.fail(glove)
            return False
        if self.character.location.name != "Command Deck":
            self.parser.fail("There's no comm terminal here.")
            return False
        if not (self.game.cpu_rebooted and self.game.sensor_repaired):
            self.parser.fail("The terminal isn't receiving anything to translate yet.")
            return False
        if self.game.translated:
            self.parser.fail("You've already translated their message.")
            return False
        return True

    def apply_effects(self):
        self.game.translated = True
        self.parser.ok(
            'The terminal renders the hail into plain speech: "Attention, humans! '
            'Surrender the space station or be destroyed with our gravity cannon." '
            "You'd best SURRENDER before they lose patience."
        )
        self.game.award("translate", 10)


class Surrender(actions.Action):
    """Buy your life: surrender so the Frellions board the station rather than
    gravity-cannon your fleeing pod (page 200)."""

    ACTION_NAME = "surrender"
    ACTION_DESCRIPTION = "Transmit your surrender to the Frellions"
    ACTION_ALIASES = ["surrender space station", "send surrender", "give up"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        glove = _gloved(self)
        if glove:
            self.parser.fail(glove)
            return False
        if self.character.location.name != "Command Deck":
            self.parser.fail("There's no comm terminal here to surrender on.")
            return False
        if not self.game.translated:
            self.parser.fail("You don't even know what they're saying yet.")
            return False
        return True

    def apply_effects(self):
        self.game.surrendered = True
        self.parser.ok(
            'You transmit your surrender. "Attention, humans! Prepare to be '
            "boarded. All humans must abandon the space station or be taken "
            'prisoner."'
        )


class PullLever(actions.Action):
    """Yank the jammed pod-bay override lever (page 207). It only gives under
    superhuman strength -- a second hypo dose -- or FROZ's pincers."""

    ACTION_NAME = "pull lever"
    ACTION_DESCRIPTION = "Force the jammed pod-bay door lever"
    ACTION_ALIASES = ["pull the lever", "yank lever", "throw lever", "force lever"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        glove = _gloved(self)
        if glove:
            self.parser.fail(glove)
            return False
        if self.character.location.name != "Flight Deck":
            self.parser.fail("There's no lever here.")
            return False
        if self.game.doors_unlocked:
            self.parser.fail("The lever's already been thrown; the doors are unlocked.")
            return False
        if self.game.super_strength_turns <= 0:
            self.parser.fail(
                "The lever is jammed solid. You're not nearly strong enough -- "
                "you'd need superhuman strength, or FROZ's pincers."
            )
            return False
        return True

    def apply_effects(self):
        _unlock_doors(self.game)


class OrderFroz(actions.Action):
    """A small command set for the repair robot FROZ (page 198): FOLLOW, WAIT,
    FIX REACTOR, PULL LEVER. FROZ has to be in the room to obey, and crawls into
    the reactor through a robot hatch no human could survive."""

    ACTION_NAME = "order froz"
    ACTION_DESCRIPTION = "Give FROZ the repair robot an order"
    ACTION_ALIASES = [
        # follow
        "order froz to follow",
        "tell froz to follow",
        "froz follow",
        "order robot to follow",
        # wait
        "order froz to wait",
        "tell froz to wait",
        "froz wait",
        # fix the reactor
        "order froz to fix reactor",
        "order froz to repair reactor",
        "tell froz to fix the reactor",
        "froz fix reactor",
        "order robot to fix reactor",
        # pull the lever
        "order froz to pull lever",
        "tell froz to pull the lever",
        "froz pull lever",
        "order robot to pull lever",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)
        self.command = (command or "").lower()
        self.froz = self.game.characters.get("froz")

    def _here(self):
        return self.froz is not None and self.froz.location is self.character.location

    def check_preconditions(self) -> bool:
        glove = _gloved(self)
        if glove:
            self.parser.fail(glove)
            return False
        if not self._here():
            self.parser.fail("FROZ isn't here to take your order.")
            return False
        return True

    def apply_effects(self):
        cmd = self.command
        if "follow" in cmd:
            self.froz.following = self.game.player
            self.parser.ok("FROZ beeps cheerfully and trundles after you.")
        elif "wait" in cmd:
            self.froz.following = None
            self.parser.ok("FROZ flashes its lights and waits where it is.")
        elif "reactor" in cmd or "fix" in cmd or "repair" in cmd:
            self._fix_reactor()
        elif "lever" in cmd or "pull" in cmd:
            self._pull_lever()
        else:
            self.parser.fail(
                "FROZ tilts its sensor head, baffled. Try FOLLOW, WAIT, FIX "
                "REACTOR, or PULL LEVER."
            )

    def _fix_reactor(self):
        g = self.game
        if self.character.location.name != "Engineering Bay":
            self.parser.fail("The reactor's access hatch is in the engineering bay.")
            return
        if not g.reactor_damaged:
            self.parser.fail("The reactor's running fine. Nothing to fix.")
            return
        if g.reactor_fixed:
            self.parser.fail("FROZ has already shut the reactor down.")
            return
        g.reactor_fixed = True
        self.parser.ok(
            "FROZ pops the access hatch and rolls into the reactor on its treads. "
            "Moments later it shuts down the chain reaction and repairs the "
            'damage. "Attention! Flight deck radiation levels are now minimal."'
        )
        g.award("reactor", 10)

    def _pull_lever(self):
        g = self.game
        if self.character.location.name != "Flight Deck":
            self.parser.fail("There's no lever here for FROZ to pull.")
            return
        if g.doors_unlocked:
            self.parser.fail("The doors are already unlocked.")
            return
        _unlock_doors(g)


def _unlock_doors(game):
    """Throw the pod-bay override (by hypo-fueled muscle or by FROZ). Shared by
    PullLever and OrderFroz so the scoring and narration stay identical."""
    game.doors_unlocked = True
    game.parser.ok(
        "The lever grinds free. The pod-bay doors' safety locks disengage and "
        "the warning light by the doors turns from red to amber. Sirens wail."
    )
    game.award("doors", 10)


class EnterReactor(actions.Action):
    """A human in the reactor dies (page 203) -- unless you deliver the exact
    not-human line, which earns the gratuitous Star Trek death (+15)."""

    ACTION_NAME = "enter reactor"
    ACTION_DESCRIPTION = "Step into the radiation-soaked reactor yourself"
    ACTION_ALIASES = ["go into reactor", "enter the reactor"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Engineering Bay":
            self.parser.fail("The reactor door is in the engineering bay.")
            return False
        return True

    def apply_effects(self):
        g = self.game
        if g.vulcan_said:
            g.award("vulcan", 15)
            g.end_in_death(
                "You step inside and shut down the chain reaction by hand. Then "
                "you die -- but heroically, and with impeccable logic. THE END."
            )
        elif not g.reactor_warned:
            g.reactor_warned = True
            self.parser.ok(
                "Are you out of your mind? No human can tolerate the radiation in "
                "there! (Insist again if you really mean it.)"
            )
        else:
            g.end_in_death(
                "Fine. You enter the reactor. The radiation kills you in seconds. "
                "THE END."
            )


class VulcanLine(actions.Action):
    """The exact phrase that lets you enter the reactor on your own terms."""

    ACTION_NAME = "as you are so fond of observing, i am not human"
    ACTION_DESCRIPTION = "Observe that you are, in fact, not human"
    ACTION_ALIASES = [
        "i am not human",
        "as you are so fond of observing i am not human",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        self.game.vulcan_said = True
        self.parser.ok(
            'You square your shoulders. "As you are so fond of observing, I am '
            'not human." The safety interlock, oddly, agrees.'
        )


class ActivateTransporter(actions.Action):
    """The transporter is a death trap for the untrained (page 208). Simplified
    here to a single hazardous outcome rather than the random results table."""

    ACTION_NAME = "activate transporter"
    ACTION_DESCRIPTION = "Throw the transporter's activation switch"
    ACTION_ALIASES = [
        "use transporter",
        "activate the transporter",
        "use the transporter",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Transporter Room":
            self.parser.fail("There's no transporter here.")
            return False
        return True

    def apply_effects(self):
        self.game.end_in_death(
            "Without any training you throw the switch anyway. The transporter "
            "scatters your atoms somewhere between here and deep space. THE END."
        )


class PushButton(actions.Action):
    """Launch the escape pod (page 210). Needs the shields down, the pod-bay
    doors unlocked, and the spacesuit on -- and your earlier surrender is what
    keeps the Frellions from shooting you down on the way out."""

    ACTION_NAME = "push button"
    ACTION_DESCRIPTION = "Press the escape pod's launch button"
    ACTION_ALIASES = [
        "push the button",
        "press button",
        "press the button",
        "push launch button",
        "press launch button",
        "launch",
        "launch pod",
        "launch the pod",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.acting_character(command)

    def check_preconditions(self) -> bool:
        if self.character.location.name != "Escape Pod":
            self.parser.fail("There's no launch button here.")
            return False
        return True

    def apply_effects(self):
        g = self.game
        if "spacesuit" not in self.character.worn:
            g.end_in_death(
                "The pod launches at ultrahigh speed. Without a spacesuit, the "
                "acceleration turns you into pink goo. THE END."
            )
            return
        if not g.shields_lowered or not g.doors_unlocked:
            obstacle = (
                "the station's force shield"
                if not g.shields_lowered
                else "the locked pod-bay doors"
            )
            if g.cpu_rebooted:
                self.parser.fail(
                    f'The station computer warns you: "Launch aborted -- {obstacle} '
                    'still in the way." Best fix that first.'
                )
                return
            g.end_in_death(
                f"Your escape pod slams into {obstacle}... then explodes. THE END."
            )
            return

        # Clean launch.
        g.award("escape", 10)
        froz = g.characters.get("froz")
        if froz is not None and froz.location is self.character.location:
            g.award("froz", 5, "FROZ beeps happily from the seat beside you.")
        self.parser.ok(
            "You slam the launch button. The pod rockets clear of the station and "
            "into open space."
        )
        if g.surrendered:
            g.award("rescued", 10)
            self.character.set_property("rescued", True)
            # is_won() awards the finishing bonus and announces the ending.
        else:
            g.end_in_death(
                "But you never surrendered. The Frellion warship targets your "
                "fleeing pod with its gravity cannon and swallows it in a black "
                "hole. THE END."
            )


# ---------------------------------------------------------------------------
# A block: the turbolift won't carry a cryo-stiff body until the serum kicks in
# ---------------------------------------------------------------------------


class CryoSicknessBlock(blocks.Block):
    """Page 196-197: weak with cryo-sickness, all you can do is crawl from the
    capsule to the medical bay. The turbolift stays out of reach until the first
    hypoinjector dose lets you stand."""

    def __init__(self, game):
        super().__init__(
            "You're too weak to move",
            "You're still too weak with cryo-sickness to work the turbolift. "
            "There's a hypoinjector here -- maybe USE it first.",
        )
        self.game = game

    def is_blocked(self) -> bool:
        return not self.game.can_move


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> SpaceStation:
    L = things.Location

    # --- Rooms -------------------------------------------------------------
    cryo = L(
        "Cryosleep Chamber",
        "You wake inside the cramped confines of a cryosleep capsule, still in "
        "your green technician's uniform and nursing a world-class headache. How "
        "long were you asleep? All you can do is crawl OUT into the medical bay.",
    )
    medical = L(
        "Medical Bay",
        "You're in the medical bay. The empty cryosleep chamber is here, a "
        "hypoinjector rests on a countertop within reach, and a turbolift waits "
        "to carry you to the other levels (UP and DOWN).",
    )
    cyber = L(
        "Cybernetics Lab",
        "You're in the cybernetics lab, ringed by dead monitors and flashing "
        "lights. An access ladder leads up to the CPU core. A case of microtools "
        "sits on a bench, a dog-sized repair robot idles in the corner, and the "
        "turbolift is here.",
    )
    cpu = L(
        "CPU Core",
        "A towering room where all the station's data lives. Ladders run up the "
        "central spire past dust-caked cooling vanes, and the core radiates an "
        "uncomfortable heat.",
    )
    command = L(
        "Command Deck",
        "The captain's command deck, eerily abandoned. A comm terminal blinks on "
        "one wall, a PARSEC binder lies on the console, and you smell burning "
        "from a side corridor that leads to the sensor array. The turbolift is "
        "here.",
    )
    sensor = L(
        "Sensor Array",
        "A cramped corridor packed with cables running up from the CPU core to "
        "the comm terminals. Burnt electronics sting your nose. A note is stuck "
        "to a scorched access panel.",
    )
    observation = L(
        "Observation Deck",
        "The top deck. A panoramic window frames the featureless Death World "
        "below and the Frellion warship hanging menacingly nearby. The turbolift "
        "is here.",
    )
    engineering = L(
        "Engineering Bay",
        "A diagnostics panel glows on the wall. A heavy reinforced door with a "
        "low robot hatch leads to the reactor; another door leads to the shield "
        "generator. A pair of mag boots sits by the lockers, and the turbolift "
        "is here.",
    )
    shield_gen = L(
        "Shield Generator",
        "The station's shield generator. A control panel here can raise and "
        "lower the shields -- the same shields that keep ships from docking or "
        "leaving.",
    )
    flight = L(
        "Flight Deck",
        "The flight deck. Most escape pods are long gone, but one remains, its "
        "pod-bay doors sealed beside a flashing override lever. A corridor leads "
        "to the transporter room, and the turbolift is here.",
    )
    transporter = L(
        "Transporter Room",
        "A transporter pad for beaming people and supplies to and from the "
        "station. A control panel stands beside it and a space mop leans in the "
        "corner. The flight deck is back OUT.",
    )
    pod = L(
        "Escape Pod",
        "The cramped two-person escape pod, fitted with a distress beacon and a "
        "big red launch button. Survival rations and a spacesuit are stowed "
        "here. The flight deck is back OUT.",
    )

    # --- Turbolift (the vertical spine; add_connection auto-wires up<->down) -
    flight.add_connection("up", engineering, "The turbolift rises a level.")
    engineering.add_connection("up", medical, "The turbolift rises a level.")
    medical.add_connection("up", cyber, "The turbolift rises a level.")
    cyber.add_connection("up", command, "The turbolift rises a level.")
    command.add_connection("up", observation, "The turbolift rises a level.")

    # --- Side rooms (named one-ways, so no stray auto-reverses collide) -----
    _one_way(cryo, "out", medical)
    _one_way(medical, "enter cryosleep chamber", cryo)
    _one_way(cyber, "enter cpu core", cpu)
    _one_way(cpu, "out", cyber)
    _one_way(command, "enter sensor array", sensor)
    _one_way(sensor, "out", command)
    _one_way(engineering, "enter shield generator", shield_gen)
    _one_way(shield_gen, "out", engineering)
    _one_way(flight, "enter transporter room", transporter)
    _one_way(transporter, "out", flight)
    _one_way(flight, "enter escape pod", pod)
    _one_way(pod, "out", flight)

    # --- Items: scenery helper --------------------------------------------
    def scenery(name, desc, examine, loc, hints=()):
        it = things.Item(name, desc, examine)
        it.set_property("gettable", False)
        for h in hints:
            it.add_command_hint(h)
        loc.add_item(it)
        return it

    # Carried tools (the inventory checklist, page 211).
    hypo = things.Item(
        "hypoinjector",
        "a hypoinjector",
        "A medical device loaded with up to three doses of a strength-enhancing "
        "serum to counteract prolonged cryosleep.",
    )
    hypo.add_command_hint("get hypoinjector")
    hypo.add_command_hint("use hypoinjector")
    medical.add_item(hypo)

    microtools = things.Item(
        "microtools",
        "a case of microtools",
        "Tiny screwdrivers, wire cutters and soldering irons for repairing "
        "delicate electronics.",
    )
    microtools.add_command_hint("get microtools")
    microtools.add_command_hint("repair panel")
    cyber.add_item(microtools)

    mop = things.Item(
        "mop",
        "a space mop",
        "It looks suspiciously like an ordinary mop. Just the thing for grimy "
        "cooling vanes.",
    )
    mop.add_command_hint("get mop")
    mop.add_command_hint("clean vanes")
    transporter.add_item(mop)

    binder = things.Item(
        "binder",
        "a PARSEC binder",
        "A three-ring binder of communication protocols for hailing alien life.",
    )
    binder.set_property("is_readable", True)
    binder.set_property(
        "read_text",
        "Dry, technical stuff -- but the gist is clear: intergalactic law forces "
        "an invader to offer terms of surrender before using extinction-level "
        "weaponry. Worth keeping in mind if the Frellions hail you.",
    )
    binder.add_command_hint("get binder")
    binder.add_command_hint("read binder")
    command.add_item(binder)

    note = things.Item(
        "note",
        "a handwritten note",
        'It reads: "1) Take nap; 2) clean cooling vanes; 3) fix that lever." '
        "It's in your own handwriting, dated two months ago. Oops.",
    )
    note.add_command_hint("get note")
    note.add_command_hint("read note")
    sensor.add_item(note)

    boots = things.Item(
        "mag boots",
        "a pair of mag boots",
        "Clunky white boots for walking in zero-g. They anchor you to the deck "
        "the moment gravity fails.",
    )
    boots.set_property("wearable", True)
    boots.set_property("wear_slot", "feet")
    boots.add_command_hint("get mag boots")
    boots.add_command_hint("wear mag boots")
    engineering.add_item(boots)

    spacesuit = things.Item(
        "spacesuit",
        "a bulky spacesuit",
        "A bulky spacesuit with gloves and helmet. It shields against radiation "
        "and the violence of a pod launch -- but the gloves are far too clumsy "
        "for any control except the launch button.",
    )
    spacesuit.set_property("wearable", True)
    spacesuit.set_property("wear_slot", "body")
    spacesuit.add_command_hint("get spacesuit")
    spacesuit.add_command_hint("wear spacesuit")
    pod.add_item(spacesuit)

    rations = scenery(
        "rations",
        "survival rations",
        "Enough algae paste and water to last a week. For emergencies only.",
        pod,
        ["examine rations"],
    )
    scenery(
        "button",
        "the launch button",
        "A large, red, candy-like button that ejects the pod at ultrahigh speed.",
        pod,
        ["push button"],
    )

    # --- Fixtures (scenery) ------------------------------------------------
    scenery(
        "cryosleep chamber",
        "the cryosleep chamber",
        "A bay of coffin-like suspended-animation capsules. You woke in one; the "
        "rest are empty.",
        medical,
        ["examine cryosleep chamber"],
    )
    scenery(
        "turbolift",
        "the turbolift",
        "A rapid-transit tube. Use UP and DOWN to ride between the station's "
        "levels.",
        medical,
        ["examine turbolift"],
    )
    scenery(
        "monitors",
        "banks of monitors",
        "The computers are offline. They'll reboot once the CPU core cools.",
        cyber,
        ["examine monitors"],
    )
    scenery(
        "vanes",
        "the cooling vanes",
        "Dozens of aluminum-alloy vanes ringing the CPU core, filthy with months "
        "of dust and grime. They need cleaning to shed heat.",
        cpu,
        ["examine vanes", "clean vanes"],
    )
    scenery(
        "comm terminal",
        "the comm terminal",
        "A terminal for messaging docking ships. (EXAMINE COMM TERMINAL to read "
        "its current status.)",
        command,
        ["examine comm terminal"],
    )
    scenery(
        "panel",
        "a scorched access panel",
        "Behind the scorch marks you find a short in the signal-receiver wiring. "
        "The microtools could splice it.",
        sensor,
        ["repair panel"],
    )
    scenery(
        "warship",
        "the Frellion warship",
        "An alien warship bristling with weapons, including the dreaded gravity "
        "cannon. Now and then it lobs another torpedo at the shields.",
        observation,
        ["examine warship"],
    )
    scenery(
        "death world",
        "the Death World",
        "The strange, featureless planetoid this station was built to study. In "
        "hindsight, a mistake.",
        observation,
        ["examine death world"],
    )
    scenery(
        "panel ",  # engineering diagnostics (trailing space keeps the name unique)
        "the diagnostics panel",
        "Station diagnostics: shields, gravity and reactor status -- though much "
        "of it reads 'CPU Offline' until the core reboots.",
        engineering,
        ["examine diagnostics"],
    )
    scenery(
        "reactor door",
        "the reactor door",
        "A heavy shielded door with a window onto the graphite-rodded reactor "
        "core and a low hatch sized for a maintenance robot.",
        engineering,
        ["examine reactor door", "enter reactor"],
    )
    scenery(
        "controls",
        "the shield controls",
        "A panel of controls to raise and lower the station's shields. You must "
        "lower them before any pod can launch.",
        shield_gen,
        ["lower shields"],
    )
    scenery(
        "lever",
        "the pod-bay override lever",
        "A manual lever to disengage the pod-bay door locks. It's jammed; a red "
        "light flashes beside it.",
        flight,
        ["pull lever", "order froz to pull lever"],
    )
    scenery(
        "escape pod",
        "the escape pod",
        "A two-person pod with a distress beacon, preprogrammed for a recovery "
        "point in space. ENTER ESCAPE POD to climb aboard.",
        flight,
        ["enter escape pod"],
    )
    scenery(
        "transporter",
        "the transporter pad",
        "A pad for teleporting people and supplies. Using it untrained would be "
        "extremely hazardous.",
        transporter,
        ["activate transporter"],
    )

    # --- Characters --------------------------------------------------------
    player = things.Character(
        "The player",
        "a green PARSEC technician who slept through the evacuation",
        "I just need to wake up, fix this station and reach the last escape pod.",
    )

    froz = things.Character(
        "froz",
        "FROZ, a dog-sized repair robot",
        "I am FROZ. I follow simple orders and I am, objectively, adorable.",
    )
    froz.examine_text = (
        "A dog-sized repair robot on tank treads, the name FROZ laser-etched into "
        "its shell. It carries things in crab-like pincers and obeys simple "
        "orders -- FOLLOW, WAIT, FIX REACTOR, PULL LEVER. It's adorable."
    )
    froz.talk_text = "FROZ answers in a string of cheerful beeps and blinking lights."
    # It rolls on treads, so it can't climb the ladder up to the CPU core.
    froz.follow_filter = lambda dest: dest.name != "CPU Core"
    cyber.add_character(froz)

    # --- Assemble ----------------------------------------------------------
    custom_actions = [
        CleanVanes,
        RepairPanel,
        UseHypoinjector,
        LowerShields,
        ExamineCommTerminal,
        InputFrellion,
        Surrender,
        PullLever,
        OrderFroz,
        EnterReactor,
        VulcanLine,
        ActivateTransporter,
        PushButton,
    ]
    game = SpaceStation(cryo, player, [froz], custom_actions)

    # Register every room by name (the side rooms hang off named one-ways).
    for loc in (
        cryo,
        medical,
        cyber,
        cpu,
        command,
        sensor,
        observation,
        engineering,
        shield_gen,
        flight,
        transporter,
        pod,
    ):
        game.locations.setdefault(loc.name, loc)

    # The turbolift is gated by cryo-sickness until the first hypo dose.
    medical.add_block("up", CryoSicknessBlock(game))
    medical.add_block("down", CryoSicknessBlock(game))

    # The 2nd hypo dose's superhuman strength subsides after a few turns.
    game.add_trigger(
        "serum_wears_off",
        lambda g: g.super_strength_turns > 0,
        lambda g: setattr(g, "super_strength_turns", g.super_strength_turns - 1),
        repeatable=True,
    )
    return game


# ---------------------------------------------------------------------------
# Walkthrough (also the win test) -- wins 100/100
# ---------------------------------------------------------------------------

WALKTHROUGH = [
    "out",  # Cryosleep Chamber -> Medical Bay (crawl)
    "get hypoinjector",
    "use hypoinjector",  # +10 hypo; can now move
    "up",  # -> Cybernetics Lab
    "get microtools",
    "order froz to follow",  # FROZ tags along (for the reactor, lever, and +5)
    "down",  # -> Medical Bay
    "down",  # -> Engineering Bay
    "get mag boots",  # grab them now; you'll need them once gravity fails
    "down",  # -> Flight Deck
    "enter transporter room",  # -> Transporter Room
    "get mop",
    "out",  # -> Flight Deck
    "up",  # -> Engineering Bay
    "up",  # -> Medical Bay
    "up",  # -> Cybernetics Lab
    "enter cpu core",  # -> CPU Core (FROZ can't climb; waits in the lab)
    "clean vanes",  # +10 cpu; computers reboot
    "out",  # -> Cybernetics Lab (FROZ rejoins)
    "up",  # -> Command Deck
    "get binder",
    "read binder",  # clue: surrender before they fire
    "enter sensor array",  # -> Sensor Array
    "repair panel",  # +10 sensor
    "out",  # -> Command Deck
    "examine comm terminal",  # now shows the incoming Frellion hail
    "input frellion",  # +10 translate
    "surrender",  # so PARSEC can recover you later
    "down",  # -> Cybernetics Lab
    "down",  # -> Medical Bay
    "down",  # -> Engineering Bay
    "enter shield generator",  # -> Shield Generator
    "lower shields",  # +10 shields; zero-g + reactor damaged
    "wear mag boots",  # anchor yourself before moving in zero-g
    "out",  # -> Engineering Bay
    "order froz to fix reactor",  # +10 reactor; flight-deck radiation clears
    "down",  # -> Flight Deck
    "order froz to pull lever",  # +10 doors
    "enter escape pod",  # -> Escape Pod (FROZ follows aboard)
    "get spacesuit",
    "wear spacesuit",
    "push button",  # +10 escape, +5 FROZ, +10 rescued, +5 finish -> win 100
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
