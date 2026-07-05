"""The Tomb of Nassak An-Rah -- a Vaults of Vaarn parser adventure.

A Zork / Action Castle homage set in the Blue Ruins of Vaarn. See the design spec
at docs/design/tomb-of-nassak-an-rah.md.

The game opens at the Caravan Wreck -- a safe onboarding room on the Tomblands
road that teaches the old-school verb+object language (EXAMINE / OPEN / TAKE /
LIGHT / DOUSE / READ / TALK) before the tomb can kill you (design doc §16.2).
The glowstone is found in the merchant's pack, not given. GO NORTH skips the
tutorial entirely.

    Run:  python -m text_adventure_games.adventures.tomb_of_nassak_an_rah [--walk]
"""

import random

from text_adventure_games import games, things, actions, blocks, reactions, perception
from text_adventure_games.enums import Property
from text_adventure_games.slots import Wound, roll_wound

# Wound rolls draw from a module RNG so tests can seed it.
_RNG = random.Random()


def _die(game, message):
    """End the game with a death line (the tomb is deadly)."""
    game.parser.ok(message)
    game.game_over = True
    game.game_over_description = message


# "Loud" actions are everything NOT in a hazard's quiet set. Movement (go/sneak)
# and looking are always quiet -- you may walk the tomb freely. What kills is
# LIGHT (the bats), sustained NOISE (the jackals), SPORES (the chimney), or
# disturbing the coffin (the Horror) -- and every hazard warns before it kills.
_QUIET = {
    "go",
    "sneak",
    "look",
    "examine",
    "describe",
    "inventory",
    "wait",
    "get",
    "drop",
    "put",
    "talk",
    "open",
    "wear",
    "light",
    "douse",
    "feel",
    "listen",
    "smell",
    "drink",
    "eat",
    "read",
    "search",
    "give",
    "throw",
    "close",
    "take off",
    "wield",
    "unwield",
    "help",
    "quit",
}
# The Spawn hunt by SOUND alone (they wear jars for heads): everything quiet
# to the halls is quiet to them EXCEPT plain walking -- footfalls carry, and
# sneak exists for a reason. Light means nothing to them.
_QUIET_SPAWN = _QUIET - {"go", "talk"}

# The sphere has NO noise hazard (CCB: noise reactions are covered
# elsewhere) -- enter, look, even shout. The Horror wakes on the deliberate
# act alone: prying its coffin (the boss fight, below).


def _wound_player(g, name, slots_n, desc):
    """Wound the player: the standard [damage] line, any displaced-gear spill,
    and the fatal verdict back to the caller. *desc* may be a tuple of
    variants -- one is drawn, so a body hurt eight times reads eight ways."""
    if isinstance(desc, (list, tuple)):
        desc = _RNG.choice(desc)
    fatal, dropped = g.player.add_wound(Wound(name, slots_n, desc), rng=_RNG)
    g.parser.damage(f"{name} - {desc}")
    for it in dropped:
        g.parser.ok(f"The {it.name} spills from your pack.")
    return fatal


def _is_holding(character, name):
    return name in character.inventory


def _player_was_loud_in(g, room, quiet):
    """True if the player did a loud (non-quiet) action located in *room* this
    round. Movement and looking never count -- only acts like say / break / attack
    / pry. (Creatures' own actions don't count -- it's the player giving themselves
    away.)"""
    for e in g.events[g._round_event_start :]:
        payload = e.payload or {}
        if (
            e.actor == g.player.name
            and e.action not in quiet
            and (
                payload.get("location") == room.name
                # A movement event logs its origin; its footfalls land in the
                # DESTINATION too (matters only where "go" itself is loud --
                # the Spawn's rooms).
                or payload.get("dest") == room.name
            )
        ):
            return True
        # An encumbered player's movement clatters (slots.py): the engine
        # emits a real sound, and the tomb's listeners treat it as one.
        if (
            "overloaded pack" in (payload.get("sound") or "")
            and payload.get("location") == room.name
        ):
            return True
    return False


def _hazard(
    game,
    room,
    *,
    danger,
    warns,
    kill=None,
    limit=3,
    gate=None,
    harm=None,
    harm_resets=False,
):
    """A patient room hazard. Each round the player is in *room* and ``danger(g)``
    holds (and ``gate`` allows), a counter escalates and the next line of *warns*
    is narrated; at ``limit`` it ``kill``s. The counter resets the instant the
    danger lifts -- douse the light, fall quiet, mask up, step out -- so a hazard
    always warns first and there is always a way clear.

    *warns* is a tuple of escalating lines: **the fiction is the clock** (design
    doc §16.1). The first warning is ambient; the last is unmistakably terminal.
    No mechanics leak into the prose -- unless ``give_hints`` is on, in which
    case a counter is appended as training wheels."""
    key = f"_hz:{room.name}"

    def tick(g):
        active = g.player.location is room and (gate is None or gate(g)) and danger(g)
        if not active:
            # Decay rather than reset: one quiet round steps the count back by
            # one, so spaced-out noises still accumulate -- the second warning
            # ("nearer") is reachable by intermittent racket, not only by
            # sustained racket. Full calm still drains to zero.
            room.set_property(key, max(0, (room.get_property(key) or 0) - 1))
            return
        n = (room.get_property(key) or 0) + 1
        room.set_property(key, n)
        if n >= limit:
            if harm is not None:
                # Wound-then-kill (design: slots share the harm gauge): the
                # hazard maims rather than executes; death arrives when wounds
                # fill the player's slots (or the wound roll is itself fatal).
                if harm(g) and harm_resets:
                    room.set_property(key, 0)
            else:
                _die(g, kill)
        else:
            line = warns[min(n, len(warns)) - 1]
            if g.give_hints:
                line += f" ({n}/{limit})"
            g.parser.ok(line)

    game.add_trigger(f"hazard:{room.name}", lambda g: True, tick, repeatable=True)


class Sneak(actions.Go):
    """Move quietly -- a silent ``Go``. Creeping is the only safe way through the
    lower halls and past their listeners; striding (``go``) gives you away.

    Aliases are the multi-word ``sneak <dir>`` / ``creep <dir>`` forms so the
    parser's specific-first pass routes them here rather than letting the bare
    direction (a ``Go`` alias of the same length, e.g. "north") pre-empt them."""

    ACTION_NAME = "sneak"
    ACTION_DESCRIPTION = "Move quietly in a direction (don't wake the tomb)"
    MOVE_VERB = "slip silently"  # "You slip silently to Hall of Memory."
    ACTION_ALIASES = [
        f"{verb} {direction}"
        for verb in ("sneak", "creep", "tiptoe")
        for direction in (
            "north",
            "south",
            "east",
            "west",
            "up",
            "down",
            "in",
            "out",
            "left stairs",
            "right stairs",
        )
    ]

    def __init__(self, game, command, actor=None):
        cl = command.lower()
        for verb in ("sneak to", "creep to", "tiptoe to", "sneak", "creep", "tiptoe"):
            if cl.startswith(verb):
                command = "go " + command[len(verb) :].strip()
                break
        super().__init__(game, command, actor=actor)


class MantisSong(reactions.Startle):
    """The Canopic hall's mantis-headed jar -- split and fungal -- SINGS whenever
    it hears a noise, in an INSECT'S voice (CCB): a stridulation, wing-cases and
    rubbed legs, carrying across the whole tomb and luring the Spawn (which are
    :class:`DrawnToSound`) to the singer. Re-arms each round."""

    REPEATABLE = True

    def apply_effects(self):
        # The jar may be carried (it is gettable, at the carrier's peril): sing
        # from wherever it is -- its own location, or its holder's.
        loc = self.owner.location
        if loc is None:
            holder = getattr(self.owner, "owner", None)
            loc = getattr(holder, "location", None)
        if loc is None:
            return
        # The close-up is only for someone in the room; everyone else gets the
        # heard version via the sound system ("From the south you hear...").
        if self.game.player.location is loc:
            self.game.parser.ok(
                "The mantis-headed jar splits wider and SINGS -- a tuneless, "
                "carrying stridulation, as of a thousand wing-cases rubbed "
                "to one note, and it fills the tomb."
            )
        self.game.emit_sound(loc, 6, "a tuneless insect song")


def _has_spark(player):
    """Any carried ignition source (the plasma-igniter, or a hound's servo)."""
    return any(
        it.get_property("ignition_source") for it in player.carried_items().values()
    )


def _spark_name(player):
    """The NAME of the carried thing that makes the spark, so the burn
    narrations can be concrete about the tool in hand (CCB)."""
    for it in player.carried_items().values():
        if it.get_property("ignition_source"):
            return it.name
    return "spark"


def _gel_dose(g):
    """Consume one dose of gel from the player's flask (relabelling it);
    returns False if they carry no dose."""
    flask = g.player.carried_items().get("flask of gel")
    if flask is None:
        return False
    n = int(flask.get_property("portions") or 0)
    if n <= 0:
        return False
    flask.set_property("portions", n - 1)
    n -= 1
    flask.description = (
        f"a flask of gel with {n} dose{'s' if n != 1 else ''}"
        if n
        else "an empty flask"
    )
    return True


class Burn(actions.Action):
    """BURN, generalized (design doc §17.2): one gel dose + any spark, aimed at
    what the fungus holds. The ossified corpse (the cleanse -- kills the whole
    network); the chimney growth (burns the shaft clean, a local fix); or the
    Fungal Horror itself (sets it ABLAZE: no regrowth while it burns)."""

    ACTION_NAME = "burn"
    ACTION_DESCRIPTION = "Set something alight (a gel dose, and a spark)"
    ACTION_ALIASES = [
        "burn corpse",
        "burn ossified corpse",
        "burn the corpse",
        "ignite corpse",
        "torch corpse",
        "burn mystic",
        "burn the ossified corpse",
        "burn growth",
        "burn fungus",
        "burn the fungus",
        "burn chimney",
        "ignite fungus",
        "burn horror",
        "burn the horror",
        "ignite horror",
        "torch horror",
        "set horror ablaze",
        "ignite",
        "torch",
        "set ablaze",
        "burn gel",
        "light gel",
        "ignite gel",
        "burn flask",
        "light flask",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.command = command.lower()

    def _target(self):
        loc = self.player.location
        if loc is None:
            return None
        if loc.name == "The Summit" and (
            "corpse" in self.command
            or "mystic" in self.command
            or self.command.strip() in ("burn", "ignite", "torch", "set ablaze")
        ):
            return "corpse"
        chimney_loc = self.game.locations.get("The Fungal Chimney")
        if (
            chimney_loc is not None
            and not chimney_loc.get_property("burned")
            and (
                loc is chimney_loc
                # From the Summit you stand at the chimney's mouth: light it
                # like a chimney is lit -- from open air, not from inside.
                or (
                    loc.name == "The Summit"
                    and any(w in self.command for w in ("growth", "fungus", "chimney"))
                )
            )
        ):
            return "chimney"
        if loc.name == "Burial Sphere of Nassak An-Rah" and (
            "horror" in self.command
            or "mass" in self.command
            or "gel" in self.command
            and self._doused_horror_here()
            or self.command.strip() in ("burn", "ignite", "torch", "set ablaze")
        ):
            return "horror"
        return None

    def _doused_horror_here(self):
        horror = self.game.characters.get("fungal horror")
        return (
            horror is not None
            and horror.location is self.player.location
            and horror.get_property("gel_doused")
            and not horror.get_property("is_dead")
        )

    def check_preconditions(self) -> bool:
        if "gel" in self.command.split() or "flask" in self.command.split():
            # Once the dose is ON something, lighting "the gel" IS lighting
            # that something (CCB: throw gel at horror, then light gel).
            if not self._doused_horror_here():
                self.parser.fail(
                    "The gel burns where you pour it, not in your hand. Douse "
                    "a thing, and burn THAT."
                )
                return False
        target = self._target()
        if target is None:
            self.parser.fail("There's nothing here that wants burning.")
            return False
        if target == "corpse" and self.player.location.get_property("cleansed"):
            self.parser.fail("The corpse is already ash; the fungus is dead.")
            return False
        if target == "horror":
            horror = self.game.characters.get("fungal horror")
            if horror is None or horror.location is not self.player.location:
                self.parser.fail(
                    "The mass is sealed behind the glass; burn what feeds it, or open its door."
                )
                return False
            if horror.get_property("is_dead"):
                self.parser.fail("It is already still, and past burning's help.")
                return False
        if not _has_spark(self.player):
            self.parser.fail(
                "You have nothing that makes a spark hot enough to mean it."
            )
            return False
        if target == "horror" and self.game.characters["fungal horror"].get_property(
            "gel_doused"
        ):
            return True  # already dripping with a thrown dose: spark alone
        flask = self.player.carried_items().get("flask of gel")
        if flask is None or int(flask.get_property("portions") or 0) <= 0:
            self.parser.fail(
                "Bare flame won't take here. It would want dousing in "
                "something that burns -- a dose of the embalming gel."
            )
            return False
        return True

    def apply_effects(self):
        target = self._target()
        if not (
            target == "horror"
            and self.game.characters["fungal horror"].get_property("gel_doused")
        ):
            _gel_dose(self.game)
        loc = self.player.location
        if target == "corpse":
            loc.set_property("cleansed", True)
            self.game.locations["Burial Sphere of Nassak An-Rah"].set_property(
                "horror_dead", True
            )
            message = (
                "You splash a dose of embalming gel over the ossified mystic "
                f"and put a spark from the {_spark_name(self.player)} to it. Orange "
                "flame roars down the fungal chimney -- and far below, the "
                "whole rotten network shudders and dies. The Fungal Horror "
                "sloughs into ash. The tomb falls silent at last."
            )
            corpse_item = loc.items.get("ossified corpse")
            if corpse_item is not None and "friend's fungus" in corpse_item.contents:
                corpse_item.remove_item(corpse_item.contents["friend's fungus"])
                message += (
                    " The pouch nested in his clasped hands goes up with him, "
                    "sweet on the wind for a moment."
                )
            # If the Horror is out and fighting, the root's death is its death
            # -- and the coil's keeping ends with it: the coffin's contents it
            # held since the eruption drift free in the sphere.
            horror = self.game.characters.get("fungal horror")
            if horror is not None and not horror.get_property("is_dead"):
                horror.set_property("is_dead", True)
                message += (
                    " Far below, the coil collapses mid-motion, every thread of "
                    "it gone slack at once."
                )
                sphere_loc = self.game.locations["Burial Sphere of Nassak An-Rah"]
                if horror.location is sphere_loc:
                    horror.description = "the Fungal Horror, charred and still"
                    horror.examine_text = (
                        "Still at last. The coil lies slack around nothing; "
                        "the bones it kept drift free."
                    )
                    coffin_item = sphere_loc.items.get("coffin")
                    if coffin_item is not None:
                        for it in list(coffin_item.contents.values()):
                            coffin_item.remove_item(it)
                            sphere_loc.add_item(it)
            self.parser.ok(message)
            self.game.award("cleanse", 30, None)
        elif target == "chimney":
            chimney_loc = self.game.locations["The Fungal Chimney"]
            chimney_loc.set_property("burned", True)
            if loc is chimney_loc:
                # Lit from INSIDE the shaft: it works, and it costs you --
                # you are standing in the thing you just made a flue.
                self.parser.ok(
                    "You sling a dose of embalming gel across the orange "
                    f"growth and put a spark from the {_spark_name(self.player)} "
                    "to it. The shaft goes up like a struck match, flame "
                    "crawling the growth from throat to crown -- with you in "
                    "its throat. When it gutters out, the chimney is black, "
                    "bare, and breathable -- a local victory. Somewhere below, "
                    "the root of it all is untouched."
                )
                fatal = _wound_player(
                    self.game,
                    "Scorched",
                    1,
                    (
                        "The fire takes your eyebrows and the hair on the back "
                        "of your neck as you scramble clear.",
                        "A sheet of flame runs up your sleeve; the skin beneath "
                        "keeps the shape of it.",
                        "The first breath of the blaze crisps your cheek before "
                        "you can turn from it.",
                    ),
                )
                if fatal:
                    _die(
                        self.game,
                        "The shaft becomes a flue, and you are what it burns. "
                        "THE END.",
                    )
            else:
                # Lit from the Summit's lip: the smart way to light a chimney.
                self.parser.ok(
                    "You douse a knot of the growth at the chimney's mouth "
                    "with a dose of embalming gel, strike the "
                    f"{_spark_name(self.player)} over it, and step back. The "
                    "shaft takes it like a struck match, flame crawling the "
                    "growth from throat to crown while you watch from open "
                    "air. When it gutters out, the chimney is black, bare, "
                    "and breathable. Somewhere below, the root of it all is "
                    "untouched."
                )
        else:  # the Horror
            horror = self.game.characters["fungal horror"]
            was_doused = horror.get_property("gel_doused")
            horror.set_property("ablaze", 3)
            horror.set_property("gel_doused", False)
            tool = _spark_name(self.player)
            if was_doused:
                message = (
                    f"You strike a spark from the {tool}, and the dose of "
                    "embalming gel already sheeting the Fungal Horror takes "
                    "all at once. It goes up with a sound like a held breath "
                    "released."
                )
            else:
                message = (
                    "You sling a dose of embalming gel from your flask across "
                    f"the Fungal Horror and put a spark from the {tool} to it. It "
                    "goes up with a sound like a held breath released."
                )
            # Say what the fire MEANS only to someone who has watched the
            # thing mend (CCB: no unearned hints) -- and say it as a fact of
            # the body, not a rule of the game.
            if horror.get_property("knit_seen"):
                message += (
                    " And in the flames, the mending stops: the rents you "
                    "cut gape, and go on gaping."
                )
            self.parser.ok(message)


class Refill(actions.Action):
    """Refill the gel flask wherever embalming gel pools: the Hall of Hounds
    (the tank, intact or flooded), or the Hall of Warriors once any cylinder
    has been broken open."""

    ACTION_NAME = "fill flask"
    ACTION_DESCRIPTION = "Refill the gel flask from a tank or a spill"
    ACTION_ALIASES = [
        "refill flask",
        "fill the flask",
        "refill the flask",
        "fill flask with gel",
        "refill gel",
        "fill gel",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def _source_here(self):
        loc = self.player.location
        if loc is None:
            return False
        if loc.name == "Hall of Hounds":
            return True  # the tank holds it, broken or whole
        if loc.name == "Hall of Warriors":
            # any shattered cylinder has spilled its gel
            return any(
                f"{c} cylinder" not in loc.items
                for c in ("cerulean", "amber", "viridian", "orange")
            )
        return False

    def check_preconditions(self) -> bool:
        flask = self.player.carried_items().get("flask of gel")
        if flask is None:
            self.parser.fail("You have nothing to fill.")
            return False
        if int(flask.get_property("portions") or 0) >= 3:
            self.parser.fail("The flask is full.")
            return False
        if not self._source_here():
            self.parser.fail("There's no gel pooled here to draw from.")
            return False
        return True

    def apply_effects(self):
        flask = self.player.carried_items()["flask of gel"]
        flask.set_property("portions", 3)
        flask.description = "a flask of gel with 3 doses"
        self.parser.ok(
            "You draw the flask through the gel until it runs over -- luminous, "
            "green-gold, reeking faithfully of lamp-oil. Three doses."
        )


class TieSilk(actions.Action):
    """Lash the drifting coffin fast with the merchant's spider-silk (CCB
    design) -- the bootless anchor. Cobweb-thin, and it holds like law."""

    ACTION_NAME = "tie coffin"
    ACTION_DESCRIPTION = "Tie the coffin down with spider-silk"
    ACTION_ALIASES = [
        "tie spider-silk to coffin",
        "tie silk to coffin",
        "tie coffin with spider-silk",
        "tie coffin with silk",
        "tether coffin",
        "lash coffin",
        "tie spider-silk",
        "tie silk",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or "coffin" not in loc.items:
            self.parser.fail("There's no coffin here to tie.")
            return False
        if loc.items["coffin"].get_property("tethered"):
            self.parser.fail("The coffin is already lashed fast.")
            return False
        if "bolt of spider-silk" not in self.player.carried_items():
            self.parser.fail(
                "You'd want something long, light, and stronger than it looks."
            )
            return False
        return True

    def apply_effects(self):
        loc = self.player.location
        silk = self.player.carried_items()["bolt of spider-silk"]
        self.player.discard_item(silk)
        loc.items["coffin"].set_property("tethered", True)
        self.parser.ok(
            "You pay the spider-silk out through the wall-rings and lash the "
            "coffin fast -- cobweb-thin, and it holds like law. The coffin "
            "stops its slow turning."
        )


class PryCoffin(actions.Action):
    """Pry open the Autarch's anti-entropy coffin in the zero-g Burial Sphere to
    claim the Exotica. Prying wants two things: an ANCHOR (the magnetic boots
    worn, or the coffin lashed down with spider-silk) and a LEVER -- the
    prismatic blade, which snaps at the hilt as the coffin gives (CCB design).
    """

    ACTION_NAME = "pry coffin"
    ACTION_DESCRIPTION = "Pry open the floating coffin (an anchor, and a blade to lose)"
    ACTION_ALIASES = [
        "open coffin",
        "open the coffin",
        "pry open coffin",
        "pry the coffin",
        "loot coffin",
        "loot the coffin",
        "pry open the coffin",
        "pry coffin open with blade",
        "pry coffin with blade",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or "coffin" not in loc.items:
            self.parser.fail("There's no coffin here.")
            return False
        coffin = loc.items["coffin"]
        if coffin.get_property("pried"):
            self.parser.fail("The coffin is already open.")
            return False
        anchored = "magnetic boots" in self.player.worn or coffin.get_property(
            "tethered"
        )
        if not anchored:
            self.parser.fail(
                "You reach the coffin and shove -- and it is you who drifts "
                "away, floating and unmoored from gravity. Nothing here holds "
                "you down, and prying wants something to brace against."
            )
            return False
        if "prismatic blade" not in self.player.carried_items():
            self.parser.fail(
                "The seam is fine as a hair; fingers will not part it. It "
                "wants a blade's edge -- and a fool willing to lose one."
            )
            return False
        return True

    def apply_effects(self):
        loc = self.player.location
        coffin = loc.items["coffin"]
        if not loc.get_property("horror_dead"):
            # The coffin is the thing's HOUSE. Opening it while it lives wakes
            # the boss (design doc §17.3) -- the eruption interrupts the pry,
            # so the blade survives for the fight it just started.
            horror = self.game.characters["fungal horror"]
            if horror.location is not loc:
                self.game.relocate(horror, loc)
            coffin.set_property("pried", True)
            self.parser.ok(
                "You work the blade into the seam and the glass FRACTURES -- "
                "cracks racing from the blade's edge until the coffin gives "
                "all at once, shards drifting slow and glittering in the "
                "weightless air. From among the shattered glass the Fungal "
                "Horror emerges, unwinding from the Autarch's bones -- orange "
                "and vast and patient -- and it keeps the bones in its coil."
            )
            return
        coffin.set_property("pried", True)
        blade = self.player.carried_items()["prismatic blade"]
        self.player.discard_item(blade)
        anchor = (
            "Anchored by the magnetic boots"
            if "magnetic boots" in self.player.worn
            else "Braced against the silk-lashed coffin"
        )
        taken = []
        for item in list(coffin.contents.values()):
            coffin.remove_item(item)
            loc.add_item(item)
            taken.append(item.name)
        self.parser.ok(
            f"{anchor}, you work the prismatic blade into the hairline seam. "
            "The edge bends light, bends -- and snaps at the hilt as the "
            "coffin gives. Among the Autarch's drifting bones you find: "
            + ", ".join(taken)
            + ". The blade is done."
        )
        self.game.award("exotica", 30, None)


class CrystalSeal(blocks.Block):
    """The red-crystal seal barring the stair from the Canopic hall up to the
    Burial Sphere. It clears once both missing canopic jars sit on their matching
    plinths (the placement trigger sets ``seal_open`` on the Canopic hall)."""

    def __init__(self, canopic):
        super().__init__(
            "A seal of red crystal",
            "A seal of red crystal bars the stair, cut and fitted to the "
            "treads so exactly that the joins read as one stone -- tombwright "
            "work, made to open for one thing only. Five beast-sigils are set in the arch above "
            "it; two of them are dark. The crystal hums at a pitch just under "
            "hearing, with the patience of a lock.",
        )
        self.canopic = canopic

    def is_blocked(self) -> bool:
        return not self.canopic.get_property("seal_open")


class TombGame(games.Game):
    """The adventure's Game. Winning (later) is "got out of the tomb alive with the
    Exotica" -- the ``escaped`` flag a future escape trigger will set. For now it
    is always unwon; Phase 1 is a sandbox to walk."""

    def is_won(self) -> bool:
        return bool(self.player.get_property("escaped"))


def _scenery(location, name, description, examine_text):
    """Place a fixed, un-takeable prop in a room (atmosphere + a hook for later
    phases). Returns the Item so callers can tag it further."""
    it = things.Item(name, description, examine_text)
    it.set_property("gettable", False)
    location.add_item(it)
    return it


def _canopic_jar(name, description, examine_text, organ_name, organ_desc):
    """A sealed canopic jar: a closed container holding the Autarch's preserved
    organ. The organ is revealed only when the jar is OPENED (examining the sealed
    jar tells you nothing of what's inside). Jar and organ are both gettable --
    and the organ is edible, God help you, or feedable to things that eat."""
    jar = things.Item(name, description, examine_text).make_container()
    jar.set_property("is_closed", True)
    organ = things.Item(organ_name, organ_desc, organ_desc)
    organ.set_property("gettable", True)
    organ.set_property(Property.EDIBLE, True)
    organ.set_property(
        Property.TASTE,
        "of four thousand years of preservative, and beneath that, of exactly "
        "what it is.",
    )
    organ.set_property("is_organ", True)  # the grave-sick trigger keys on this
    jar.add_item(organ)
    return jar


def build_game():
    # --- The onboarding: the Caravan Wreck (start) ---------------------------
    # A safe sandbox one room south of the tomb that teaches the old-school
    # verb+object language (EXAMINE / OPEN / TAKE / LIGHT / DOUSE / READ / TALK)
    # before anything can kill you. GO NORTH works from turn one -- the tutorial
    # is optional exploration, not a gate. (Design: tomb doc §16.2; register:
    # docs/design/vaarn-style-guide.md.)
    wreck = things.Location(
        "The Caravan Wreck",
        "The Tomblands road, at the hour after the Cacklemaw. A trade caravan lies "
        "heeled over in the blue sand -- wind-wagon ribs of pale wood, cargo "
        "strewn and already sanding under -- and the dead have been arranged by "
        "the wind into attitudes of sleep. It is said the road to Gnomon is "
        "walked only by the desperate; last night this was proven again. "
        "Northward, three carved faces watch from a slab of azure stone.",
    )
    hold = things.Location(
        "The Wagon's Hold",
        # The LIT view; the Darkness veil below supplies the dark blurb. This is
        # where LIGHT/DOUSE get learned in safety -- so the Hall of Youth can
        # later subvert the lesson.
        "Your light finds the hold intact where the wagon is not: crates of "
        "saffron and dates still lashed tight, a folding desk, and the "
        "merchant's ledger, closed around its ribbon marker.",
    )
    wreck.add_connection("in", hold)  # auto: hold out -> wreck

    hold.obscure(
        perception.Darkness(
            blurb="Bruise-dark. The hold smells of saffron, lamp-oil, and the dry "
            "sweetness of dates; you can make out crate-shapes, and on a desk "
            "somewhere, a pale square of paper. The daylight is a grey rectangle "
            "behind you."
        )
    )

    _scenery(
        wreck,
        "wreck",
        "the heeled-over wind-wagon",
        "Pale ribs and torn sailcloth. Wind-wagons are built to outrun "
        "anything on the Tomblands road, and this one nearly did.",
    )
    _scenery(
        wreck,
        "zoxen",
        "two dead zoxen, half-sanded",
        "The caravan's draught-zoxen, patient in death as in life, already "
        "sanded to the shoulder. By morning the road will have them wholly.",
    )
    # The merchant himself -- Worry's "the merchant could not". Searching (or
    # examining) him is the wreck's safe rehearsal of the corpse-searching habit
    # that pays off at the Summit.
    merchant = _scenery(
        wreck,
        "dead merchant",
        "the merchant, dead where the road put him",
        "He lies composed, as if the wind had tidied him for visitors. The "
        "Cacklemaw did not linger over him; the sand has been more "
        "attentive, already drifting into the folds of his coat.",
    )
    merchant.add_alias("merchant")
    merchant.add_alias("body")
    merchant.add_alias("corpse")
    merchant.make_surface()
    merchant.set_property("reveals_on_examine", True)
    merchant.set_property(
        "contents_relation", "In the sand-drifted folds of his coat you find"
    )
    tokens = things.Item(
        "purse of water-debt tokens",
        "a purse of water-debt tokens",
        "Stamped brass tokens on a ring, each good for a measure of water in "
        "Gnomon. The city's truest currency, and the desert's most honest joke.",
    )
    tokens.set_property("gettable", True)
    tokens.add_alias("purse")
    tokens.add_alias("tokens")
    tokens.set_property(Property.IS_HIDDEN, True)
    merchant.add_item(tokens)
    crates = _scenery(
        hold,
        "crates",
        "lashed crates of saffron and dates",
        "Trade goods bound for the souks of Gnomon, worth a season's water "
        "-- far too much to carry, though a bale or two might ride home "
        "with somebody. The Cacklemaw do not trade.",
    )
    crates.make_container()
    for _name, _desc, _ex, _slots in (
        (
            "bale of saffron",
            "a bale of saffron",
            "Crimson threads pressed into a bale, worth more than its weight in "
            "water at the souks of Gnomon. Heavy, and it knows it.",
            2,
        ),
        (
            "crate of dates",
            "a crate of dates",
            "Dates from the southern oases, packed in palm fibre. Food for a "
            "month, or a small fortune for whoever hauls it.",
            2,
        ),
        (
            "bolt of spider-silk",
            "a bolt of spider-silk",
            "Grey spider-silk, cool as water over the hands. Light -- the "
            "merchant knew what was worth the wagon-space.",
            1,
        ),
    ):
        _good = things.Item(_name, _desc, _ex)
        _good.set_property("gettable", True)
        _good.set_property("slots", _slots)
        _good.add_alias(_name.split()[0])  # bale / crate / bolt
        if "dates" in _name:
            _good.set_property(Property.EDIBLE, True)
        _good.add_alias(_name.split()[-1].strip())  # saffron / dates / spider-silk
        if "silk" in _name:
            _good.add_alias("silk")
        crates.add_item(_good)
    ledger = _scenery(
        hold,
        "ledger",
        "the merchant's ledger",
        "A trade ledger bound in lizard-skin, closed around a ribbon "
        "marker at its final page.",
    )
    # FEEL finds the ledger in the dark hold -- so an empty-handed player who
    # gropes around is rewarded, and the probe is rehearsed before the Hall of
    # Youth needs it.
    ledger.perceptible_by(
        perception.Sense.TOUCH,
        "Your hands find a folding desk, and on it a book bound in "
        "lizard-skin, closed around a ribbon. Too dark to read a word of it.",
    )
    ledger.set_property(
        "read_text",
        "The hand is neat until it is not. '...ninth day. Camped in the lee "
        "of the tomb the guards call the Three Mouths. They will not pass "
        "it after dark, and I have stopped teasing them for it. Kotesh "
        "swears the boy's mouth is lightless within, and that what roosts "
        "there hates a lamp worse than a shout. The halls, he says, "
        "remember every footfall. And none of them, drunk or paid, will "
        "speak of the old man's mouth, which weeps orange. Superstition -- "
        "but I observe that my guards are paid to be brave, and are not. "
        "Tomorrow, Gnomon.' The entry is the last.",
    )
    ledger.set_property("gettable", True)  # take it along; it reads anywhere
    ledger.add_command_hint("read ledger")

    pack = things.Item(
        "pack",
        "the merchant's half-buried pack",
        "Boiled leather, half-buried, the straps still buckled. Whatever the "
        "Cacklemaw came for, it was not this.",
    ).make_container()
    pack.set_property("is_closed", True)
    pack.add_command_hint("open pack")
    waterskin = things.Item(
        "waterskin",
        "a waterskin with 3 rations",
        "Three rations of the merchant's water survived the night. In Vaarn "
        "this is called an inheritance. Each swallow mends what it can.",
    )
    # Water is Vaarn's scarcest resource -- of course you can drink it. Three
    # rations (CCB design): each drink heals a wound and takes a ration; the
    # empty skin stays with you, honestly labelled.
    waterskin.set_property("portions", 3)
    waterskin.set_property(Property.DRINKABLE, True)
    waterskin.set_property(
        Property.TASTE,
        "of warm leather and of luck. In Vaarn, wealth goes " "down the throat.",
    )
    waterskin.add_alias("water")
    waterskin.add_alias("skin")
    wreck.add_item(pack)

    # Worry is a NEWBEAST -- a humanoid animal-person (Issue 1: they "speak and
    # walk like men", wear masks in imitation of the human face). She was the
    # caravan's TEAMSTER, driving the zoxen; the zoxen pulled. Newbeasts are
    # never beasts of burden -- canon reserves that for zoxen and iron mules.
    worry = things.Character(
        "Worry",
        "a new-mule teamster",
        "I am Worry. I drove the wagon; now there is no wagon.",
    )
    worry.examine_text = (
        "A grey new-mule in a drover's long coat, upright on her hind hooves, "
        "dressed in the road's dust. Patient, mournful, unhurt. A carved mask "
        "in imitation of a human face hangs at her neck on a cord; there is no "
        "one left on the road to wear it for. A brass pin on the coat reads "
        "WORRY."
    )
    worry.talk_text = (
        '"They came at moonset, laughing," Worry says. "I ran, and the merchant '
        "could not, and that is the whole story. The Cacklemaw make no secret "
        'of their coming." She looks '
        'north, to the faces in the azure stone. "Take what he no longer needs '
        "-- better you than the sand. There is water in his pack, three rations "
        "of it, and a glowstone besides. You can take whatever you can carry "
        "from the hold. But "
        "mind the tomb, scavenger. The caravans give its mouths a wide berth, "
        'and a caravan is seldom wrong twice."'
    )
    wreck.add_character(worry)

    # --- The eight locations -------------------------------------------------
    exterior = things.Location(
        "Tomb Exterior",
        "A thirty-foot slab of azure stone rises from the phthalo sands, webbed "
        "over every seam with creeping orange fungus. Three faces are carved in "
        "it: westward, the dead Autarch as a young boy; eastward, a helmed "
        "warrior; far up, an old man turned to the sky, orange tendrils weeping "
        "from his open mouth. Each mouth is a door. The wind has been reading "
        "these faces for aeons and keeps its findings to itself.",
    )
    youth = things.Location(
        "Hall of Youth",
        # The LIT view -- what you see once a light is raised. Pitch dark until
        # then: the Darkness veil (set in build_game) supplies the dark blurb.
        "Your light wakes the blue in the sand-scoured walls: statues of the "
        "boy-Autarch crowd the chamber, swaddled and adored, rendered with an "
        "unsettling tenderness. Overhead, the whole vault answers the glow -- it "
        "seethes. Thousands of bats, wheeling lower with every pass.",
    )
    memory = things.Location(
        "Hall of Memory",
        "Lattices of memory-crystal climb every wall, the favoured recollections "
        "of the Autarch set in lazulite. The glimmering moving on them is not "
        "your reflection; it moves while you are still. One bank of crystal is "
        "worn smooth at hand-height, as if often consulted.",
    )
    hounds = things.Location(
        "Hall of Hounds",
        "A wall of plexiglas holds back a tank of embalming gel, luminous, the "
        "green-gold of old honey. Ten of An-Rah's hunting hounds hang suspended "
        "in it, black and spindly, more machine than dog below the shoulder -- "
        "servo-hocks, chrome ribs, lenses where a dog keeps its eyes. They are "
        "perfectly preserved. The lenses are open.",
    )
    warriors = things.Location(
        "Hall of Warriors",
        "Four plexiglas cylinders stand on an uneven floor, each holding a "
        "guard-mummy at attention in Autarchy armour, each steeped in its own "
        "embalming gel: cerulean, amber, viridian, orange. Fungus has found "
        "one of the four; orange veins fan out under its glass like pressed "
        "flowers. Their kit was sealed in with them, as if the dead might be "
        "recalled to duty. It has outlasted them, as kit does.",
    )
    canopic = things.Location(
        "Hall of the Canopic Jars",
        "Five plinths ring a central stair in a pentagon of dressed stone. Three "
        "still bear their canopic jars; two stand empty, lit from within by a "
        "crimson light that does not flicker. The stair climbs into shadow, "
        "barred by a seal of red crystal. Something in this room is listening; "
        "you can tell, the way one can.",
    )
    sphere = things.Location(
        "Burial Sphere of Nassak An-Rah",
        "A spherical chamber carved over every inch with funeral prayers, and "
        "nothing in it obeys the ground: dust and bone-chips drift in the still "
        "air, and your own weight forgot you at the threshold. In the dead "
        "centre floats the Autarch's coffin, a glass anti-entropy sphere, "
        "clouded now, and tenanted -- something orange coils inside it at the "
        "pace of a slow breath. The prayers were carved to be read from every "
        "direction at once.",
    )
    summit = things.Location(
        "The Summit",
        "High and wind-scoured, the blue desolation unrolled below to the "
        "horizon's molten line. An ossified mystic sits here in the lotus "
        "position, stone where he was flesh, orange fungus fronding from his "
        "eyes and open mouth and down into the chimney that drops through the "
        "tomb's crown. He has the look of a man interrupted mid-sentence, whose "
        "sentence continues underground.",
    )
    chimney = things.Location(
        "The Fungal Chimney",
        "A vertical throat choked with orange growth, dropping from the summit "
        "toward a glow of carved prayers far below. The spores hang so thick the "
        "air has texture. Down in the dark of it, the fungus is warm.",
    )

    # --- Connections (see spec §3) ------------------------------------------
    # Three entrances off the Exterior: the western (child) mouth, the eastern
    # (warrior) mouth, and a climb to the summit. Cardinal links auto-wire their
    # reverse; non-cardinal ones (climb, chimney) are set both ways by hand.
    # (Only canonical directions -- n/s/e/w/up/down/in/out -- auto-route from a
    # bare word; the flavor verbs "climb"/"chimney" arrive with custom actions in a
    # later phase. The room prose names which mouth lies which way.)
    wreck.add_connection(
        "north", exterior
    )  # the Tomblands road (auto: exterior south -> wreck)
    exterior.add_connection("north", youth)  # child's mouth (west face) -> Youth
    exterior.add_connection("east", warriors)  # warrior's mouth (east face) -> Warriors
    exterior.add_connection(
        "up", summit
    )  # climb the exterior (auto: summit down -> exterior)

    # The lower diamond: Youth-Memory-Warriors-Hounds form a 4-cycle (spec §3:
    # edges 1-2, 1-3, 4-2, 4-3).
    youth.add_connection("north", memory)  # 1-2
    youth.add_connection("west", hounds)  # 1-3
    memory.add_connection("north", warriors)  # 2-4
    warriors.add_connection("east", hounds)  # 4-3

    # Stairs up to the Canopic hall from both Memory and Hounds; from above,
    # the pentagon offers TWO stairways down (source, room 5): the left stairs
    # descend to Memory, the right stairs to Hounds.
    memory.add_connection("up", canopic)  # canopic.down -> memory (renamed below)
    # Hounds also has a stair up; set it by hand (with its travel description) so it
    # doesn't clobber canopic's single "down" (-> memory). The halls interconnect,
    # so from the Canopic hall you descend to Memory and reach the rest from there.
    hounds.connections["up"] = canopic
    hounds.travel_descriptions["up"] = ""
    # Rename the auto-wired "down" into the two named stairways.
    del canopic.connections["down"]
    canopic.travel_descriptions.pop("down", None)
    for _stairs, _dest in (("left stairs", memory), ("right stairs", hounds)):
        canopic.connections[_stairs] = _dest
        canopic.travel_descriptions[_stairs] = ""

    # Canopic stair up to the Burial Sphere (Phase 2 bars this with the crystal
    # seal Block; open for now so the scaffold is fully walkable).
    canopic.add_connection("up", sphere)  # sphere.down -> canopic (the aperture)

    # The fungal chimney is a real, passable, spore-choked ROOM between the Summit
    # and the Sphere's crown. You CAN go "in" -- but the spores choke you worse each
    # round you linger (the hazard, below); dash through, or wear a respirator.
    summit.add_connection("in", chimney)  # auto: chimney out -> summit
    chimney.add_connection("down", sphere)  # auto: sphere up -> chimney

    # Inside the tomb, plain walking SOUNDS like something: the arrival line
    # says so ("You walk, footfalls carrying, to ...") -- the standing hint
    # that sneak exists. The Sphere drifts (zero-g); the climbs climb.
    for _room, _verb in (
        (youth, "walk, footfalls carrying,"),
        (memory, "walk, footfalls carrying,"),
        (hounds, "walk, footfalls carrying,"),
        (warriors, "walk, footfalls carrying,"),
        (canopic, "walk, footfalls carrying,"),
        (sphere, "drift, weightless,"),
        (chimney, "climb, spores swirling,"),
    ):
        for _d in _room.connections:
            _room.move_verbs.setdefault(_d, _verb)
    exterior.move_verbs.setdefault("north", "walk, footfalls carrying,")
    exterior.move_verbs.setdefault("east", "walk, footfalls carrying,")
    exterior.move_verbs.setdefault("up", "climb")
    summit.move_verbs.setdefault("down", "climb down")

    # --- Atmosphere: examinable scenery (hooks for later phases) -------------
    _scenery(
        exterior,
        "tomb",
        "the Tomb of Nassak An-Rah",
        "Three faces in azure stone -- boy, warrior, and sky-gazing elder -- "
        "their mouths gaping as doors. Orange fungus mortars every seam.",
    )
    # The statues can be felt in the dark (TOUCH); the ceiling of bats can be
    # heard (HEARING) -- so EXAMINE-in-the-dark and the feel/listen probes reveal
    # them without a light (perception Layer 2). The ceiling's *visual* text is
    # what you see once lit; its heard text is the dark clue.
    statues = _scenery(
        youth,
        "statues",
        "blue statues of the boy-Autarch",
        "Nassak An-Rah as an infant, a child, a youth -- each rendered with "
        "unsettling tenderness in cold blue stone.",
    )
    statues.perceptible_by(
        perception.Sense.TOUCH,
        "Your hands find cold, smooth stone -- a swaddled infant, then a "
        "standing boy, larger than life. The boy-Autarch, unmistakably.",
    )
    ceiling = _scenery(
        youth,
        "ceiling",
        "the vaulted ceiling",
        "Your light picks out the vault overhead: the whole ceiling seethes "
        "with roosting bats, packed wing to wing, thousands of them -- and "
        "the nearest have already let go of the stone.",
    )
    ceiling.perceptible_by(
        perception.Sense.HEARING,
        "You can't see a thing, but the vault overhead seethes -- a dry, "
        "restless storm of leathery wings. A great many, and close. They "
        "shift when you shift.",
    )
    lattice = _scenery(
        memory,
        "crystal lattice",
        "lattices of memory-crystal",
        "Lazulite crystals knit across the walls, worn smooth at hand-height. "
        "One bank replays the Autarch's embalming for no one: the baboon took "
        "his lungs, the human his liver, the mantis his eyes; the falcon was "
        "given his intestines, and the jackal -- strangely -- his brain.",
    )
    lattice.add_alias("lattice")
    lattice.add_alias("crystals")
    tank = _scenery(
        hounds,
        "tank",
        "a plexiglas tank of embalming gel",
        "Ten hounds hang in the luminous gel, forever mid-stride: cyborg "
        "coursers of the old Autarchy, servo-hocked and chrome-ribbed, bred "
        "half in a kennel and half on a bench. Even through the seam the gel "
        "smells of lamp-oil and honey. Collectors would pay in salt and water "
        "for any of this -- and the plexiglas is one good blow from agreeing.",
    )
    tank.make_container()
    tank.set_property("is_closed", True)
    tank.set_property("is_breakable", True)
    tank.set_property(
        "break_text",
        "The plexiglas gives all at once and the wall of gel comes with it -- "
        "a luminous green-gold flood, reeking of lamp-oil, that carries the "
        "hounds out across the floor in a clatter of chrome and bone.",
    )
    hound_pile = things.Item(
        "cyborg hound",
        "a cyborg hound, gel-slick and perfectly preserved",
        "One of An-Rah's coursers: servo-hocks, chrome ribs, glass lenses, "
        "the rest of it dog. Heavy as a rolled carpet, and worth a season of "
        "water to the right collector in Gnomon.",
    )
    hound_pile.make_container()
    hound_pile.set_property("gettable", True)
    hound_pile.set_property("slots", 3)
    hound_pile.add_alias("hound")
    hound_pile.add_alias("dog")
    # SEARCH the hound and its chest gives up a second fire-starter (design
    # doc §17.1) -- the corpse-searching habit pays out a third time.
    servo = things.Item(
        "sparking servo",
        "a sparking servo",
        "A fist-sized actuator out of the hound's chest, still holding charge. "
        "Strike its leads together and it spits fat blue sparks.",
    )
    servo.set_property("gettable", True)
    servo.set_property("ignition_source", True)
    servo.set_property(Property.IS_HIDDEN, True)
    servo.add_alias("servo")
    hound_pile.add_item(servo)
    tank.add_item(hound_pile)
    _scenery(
        warriors,
        "cylinders",
        "four plexiglas burial cylinders",
        "Four guard-mummies at an attention no order will ever relieve, each "
        "sealed under its own gel -- cerulean, amber, viridian, orange -- and "
        "each armed as in life. Whatever they carried went under the glass "
        "with them. The plexiglas is crazed to milk at the corners; a firm "
        "blow would finish what the centuries started.",
    )
    # The three present jars sit on their plinths -- sealed containers. OPEN one to
    # learn which organ it holds (a second route to the head->organ matching, on
    # top of the plinth carvings and the memory crystals).
    baboon_jar = _canopic_jar(
        "baboon jar",
        "a baboon-headed canopic jar",
        "A sealed jar with a baboon's head. Something shifts dryly inside.",
        "lungs",
        "a pair of withered lungs",
    )
    human_jar = _canopic_jar(
        "human jar",
        "a human-headed canopic jar",
        "A sealed jar with a man's face. Something shifts inside.",
        "liver",
        "a leathery liver",
    )
    mantis_jar = _canopic_jar(
        "mantis jar",
        "a mantis-headed canopic jar",
        "A split, fungal jar with a mantis's head, a misshapen orange growth budding "
        "from the crack. It stirs at the faintest sound with a dry, chitinous "
        "rasp, as if listening.",
        "fungal eyes",
        "a clutch of fungus-clotted eyes",
    )
    mantis_jar.contents["fungal eyes"].add_alias("eyes")
    baboon_jar.contents["lungs"].add_alias("lung")
    for j in (baboon_jar, human_jar, mantis_jar):
        j.set_property("gettable", True)
        canopic.add_item(j)

    # The two empty plinths are surfaces you set the missing jars ON; each is
    # carved with the head that belongs there.
    falcon_plinth = things.Item(
        "falcon plinth",
        "an empty plinth carved with a falcon",
        "A plinth carved as a falcon, lit crimson and empty. The carving's "
        "talons are cupped, curled around the shape of something it has lost.",
    ).make_surface(capacity=1)
    falcon_plinth.set_property("gettable", False)
    jackal_plinth = things.Item(
        "jackal plinth",
        "an empty plinth carved with a jackal",
        "A plinth carved as a jackal, lit crimson and empty. The stone jaws are "
        "parted, holding their grip on an absence.",
    ).make_surface(capacity=1)
    jackal_plinth.set_property("gettable", False)
    canopic.add_item(falcon_plinth)
    canopic.add_item(jackal_plinth)
    dagger = things.Item(
        "synth-hunting dagger",
        "An-Rah's synth-hunting dagger",
        "A dagger that flashes coded LogLang as you grip it -- synthetics flinch "
        "from its wielder.",
    )
    dagger.set_property("is_weapon", True)
    dagger.set_property(Property.WIELDABLE, True)
    dagger.add_alias("dagger")
    manifold_box = things.Item(
        "manifold box",
        "An-Rah's manifold box",
        "A small gilded box that doesn't quite fit the space it sits in -- "
        "hypergeometric, and heavier inside than out.",
    )
    manifold_box.add_alias("box")
    coffin = _scenery(
        sphere,
        "coffin",
        "the Autarch's anti-entropy coffin",
        "A clouded glass sphere at the chamber's heart, its field failing, its "
        "interior a slow orange churn. Past the cloud, shapes drift and turn "
        "like fish under ice: bone, and things that were buried to be kept. The "
        "seam at its equator is fine as a hair -- made to be pried, never opened.",
    )
    coffin.make_container()
    coffin.set_property("is_closed", True)  # PryCoffin (boots-gated) is the only way in
    # The failing anti-entropy field still counts as a lock: SEARCH (which
    # rummages open ordinary closed containers) must not bypass the pry puzzle.
    coffin.set_property(Property.IS_LOCKED, True)
    coffin.add_item(dagger)
    coffin.add_item(manifold_box)
    # The ossified corpse carries the source adventure's find: "Searching the
    # corpse yields a pouch of Friend's Fungus." It's a surface (the pouch nests
    # in its hands), the pouch hidden until SEARCH -- or EXAMINE, which opts in
    # via reveals_on_examine (a close look at the hands is enough).
    corpse = _scenery(
        summit,
        "ossified corpse",
        "an ossified mystic",
        "A corpse turned to stone mid-meditation, orange fungus weeping from its "
        "eyes and mouth -- the wellspring, it seems, of all the rot below.",
    )
    corpse.add_alias("corpse")
    corpse.add_alias("mystic")
    corpse.make_surface()
    corpse.set_property("reveals_on_examine", True)
    corpse.set_property(
        "contents_relation", "Nested in the hollow of its clasped hands you find"
    )
    fungus = things.Item(
        "friend's fungus",
        "a plastic pouch of pink fungus",
        "A plastic pouch of pink fungus, soft and faintly warm. The Autarchy fed "
        "it to guests of state: whoever ingests it becomes extremely agreeable, "
        "and stays that way for hours. The mystic was holding it when he turned "
        "to stone -- for himself, or for whatever came up the mountain.",
    )
    fungus.set_property("gettable", True)
    fungus.set_property(Property.EDIBLE, True)
    fungus.set_property(
        Property.TASTE,
        "sweet, chemical, and companionable. For the next while "
        "you find yourself agreeing with everything -- the "
        "tomb, the dark, the distant rustling. All quite "
        "reasonable, really.",
    )
    fungus.add_alias("fungus")
    fungus.add_alias("pouch")
    fungus.set_property(Property.IS_HIDDEN, True)
    corpse.add_item(fungus)

    # The two missing jars are WORN by the Spawn (each as a hat). Knock a Spawn out
    # (it needs a weapon -- the prismatic blade below) and it drops the jar.
    falcon_jar = _canopic_jar(
        "falcon jar",
        "a falcon-headed canopic jar",
        "A sealed jar with a falcon's head. Something coils inside.",
        "intestines",
        "a coil of cured intestines",
    )
    jackal_jar = _canopic_jar(
        "jackal jar",
        "a jackal-headed canopic jar",
        "A sealed jar with a jackal's head. Something heavy rolls inside.",
        "brain",
        "the Autarch's shrivelled brain",
    )

    spawn_guts = things.Character(
        "spawn of guts",
        "a fungal spawn, eyeless under its falcon-headed jar, swaying toward every sound",
        "I am what is left of the Autarch's appetites.",
    )
    spawn_guts.examine_text = (
        "What could be described as an octopus of orange fungus and grave-cured "
        "intestine -- though even that doesn't quite get it -- wearing the "
        "falcon canopic jar on top like a hat. It sways toward any sound."
    )
    spawn_guts.add_to_inventory(falcon_jar)
    spawn_brain = things.Character(
        "spawn of brain",
        "a fungal brain on two small legs, jackal jar for a head, listening",
        "I am what is left of the Autarch's thoughts.",
    )
    spawn_brain.examine_text = (
        "A fungal brain that walks on two small legs, the jackal canopic jar "
        "worn as a hat. It has no eyes and does not appear to want any; it "
        "twitches toward every noise, precise as a metronome."
    )
    spawn_brain.add_to_inventory(jackal_jar)
    warriors.add_character(spawn_guts)
    hounds.add_character(spawn_brain)

    # The pthalo-jackals are an embodied pack (one Character), denned off-map
    # (canon: "Pthalo-Jackals -- Shallow Dens -- Hear Howling on the Wind").
    # Noise draws them in; food or water buys them off; nothing does not.
    den = things.Location(
        "Shallow Dens",
        "Low scrapes in the blue sand, ripe with old bones and jackal-musk.",
    )
    jackal_pack = things.Character(
        "jackal pack",
        "a pack of pthalo-jackals",
        "We are cautious. We are clever. We are owed.",
    )
    jackal_pack.examine_text = (
        "Pthalo-jackals: cautious, clever, cerulean-coated pack hunters. Their "
        "eyes do sums -- you, minus what you carry, minus what you bleed. It "
        "is not you they want."
    )
    for _a in ("jackals", "jackal", "pack of jackals", "pthalo-jackals"):
        jackal_pack.add_alias(_a)
    den.add_character(jackal_pack)

    # The Fungal Horror -- the boss (design doc §17.3). It lives coiled in the
    # coffin (narrative) until an alive-pry brings it out as a real Character.
    horror = things.Character(
        "fungal horror",
        "the Fungal Horror, a coil of orange around a king's bones",
        "We keep him. We are keeping him still.",
    )
    horror.examine_text = (
        "A single muscle of fungus the size of a river-snake, wound around "
        "what is left of Nassak An-Rah. Where you cut it, it remembers; "
        "where it burns, it does not."
    )
    for _a in ("horror", "the horror", "mass", "fungal mass"):
        horror.add_alias(_a)
    horror.set_property("vigor", 5)
    horror.set_property("no_catch", True)  # a coil has no hands
    horror.set_property(
        "ko_text",
        "The blow lands true, and the mass folds around the blade's path "
        "without falling.",
    )
    den.add_character(horror)

    # The glass centipede (source: "lying in ambush in the fungal chimney" --
    # "four-foot centipede with translucent carapace"). Unseen until it
    # strikes; one solid blow answers it; fire scours it out with the growth.
    centipede = things.Character(
        "glass centipede",
        "a glass centipede, four feet of translucent patience",
        "I wait. Everything comes down the chimney eventually.",
    )
    centipede.examine_text = (
        "Four feet of centipede in a carapace like poured glass -- you see it "
        "mostly by what bends behind it. It does not move while you watch."
    )
    for _a in ("centipede", "glass"):
        centipede.add_alias(_a)
    den.add_character(centipede)

    # The prismatic blade -- a weapon, pried from a guard's cylinder. (The full
    # guard-mummy gear and spore hazard arrive in Phase 4; for now the blade lets
    # you fight the Spawn.)
    blade = things.Item(
        "prismatic blade",
        "a guard's prismatic blade",
        "An Autarchy guard's blade, its edge fracturing the light into colours.",
    )
    blade.set_property("is_weapon", True)  # Property.IS_WEAPON == "is_weapon"
    blade.set_property(Property.WIELDABLE, True)
    blade.set_property("slots", 2)  # a medium weapon (source: "d8, 2 slots")
    blade.add_alias("blade")

    # Endgame gear: a plasma-igniter and magnetic boots (more guard kit), and a
    # flask of flammable embalming gel from the hound tank.
    igniter = things.Item(
        "plasma-igniter",
        "an Autarchy plasma-igniter",
        "A guard's plasma-igniter -- a thumb-flame hot enough to light anything.",
    )
    igniter.add_alias("igniter")
    igniter.set_property("ignition_source", True)
    boots = things.Item(
        "magnetic boots",
        "a pair of magnetic boots",
        "Heavy Autarchy guard-boots, soled in dull magnet-metal. They clamp to "
        "anything ferrous with a click that means it, and let go grudgingly.",
    )
    boots.set_property(Property.WEARABLE, True)
    boots.set_property("wear_slot", "feet")
    boots.add_alias("boots")
    respirator = things.Item(
        "respirator",
        "an Autarchy respirator",
        "A guard's filter-mask -- clean air in a spore-choked place.",
    )
    respirator.set_property(Property.WEARABLE, True)
    respirator.set_property("wear_slot", "face")
    respirator.add_alias("mask")

    # The four cylinders (CCB design): each guard's kit is sealed IN with him,
    # gettable only once the glass is broken -- and breaking glass is LOUD
    # (Break carries two rooms; the jackals keep the ledger). Each cylinder
    # holds a different gel; the orange one is choked with fungus, and venting
    # it sears unmasked lungs. The respirator sits in the AMBER one, so the
    # careful order is: amber first, mask up, then the rest.
    def _cylinder(colour, kit, examine, break_text):
        cyl = things.Item(
            f"{colour} cylinder",
            f"the {colour} burial cylinder",
            examine,
        ).make_container()
        cyl.set_property("gettable", False)
        cyl.set_property("is_closed", True)  # sealed: no reaching through glass
        cyl.set_property("is_breakable", True)  # the only way in
        cyl.set_property("break_text", break_text)
        cyl.add_alias(colour)
        cyl.add_item(kit)
        warriors.add_item(cyl)
        return cyl

    _cylinder(
        "cerulean",
        blade,
        "A guard-mummy floats in gel the blue of deep sky, prismatic blade at "
        "rest against its shoulder. The edge splits your light into colours, "
        "even through the glass.",
        "The glass gives all at once; cerulean gel sluices across the floor "
        "and the guard folds out with it, weightless as kelp. Its blade rings "
        "on the stone.",
    )
    _cylinder(
        "amber",
        respirator,
        "A guard-mummy floats in gel like old honey, an Autarchy respirator "
        "still strapped to its face. It did the guard no lasting good, but it "
        "has kept its seal.",
        "Amber gel bursts over your boots, sweet-smelling and old as the "
        "walls. The guard settles into the spill, and the respirator comes "
        "loose in the flood.",
    )
    _cylinder(
        "viridian",
        boots,
        "A guard-mummy in green-glass gel, still at its post by no will of "
        "its own. The boots' soles have kept their grip on the plinth.",
        "The viridian gel goes everywhere. The guard stays standing a moment "
        "longer -- boots anchored -- then tips.",
    )
    orange_cyl = _cylinder(
        "orange",
        igniter,
        "Less a cylinder than a column of fungus now; the guard inside is a "
        "shadow in the bloom. At its hip, the outline of a plasma-igniter. The "
        "growth stirs against the glass, very slightly, in time with nothing.",
        "The orange cylinder does not so much shatter as exhale.",
    )
    gel = things.Item(
        "flask of gel",
        "a flask of gel with 3 doses",
        "A flask of luminous embalming gel scooped from the hound tank. It "
        "reeks, and it burns -- three doses' worth, and refillable wherever "
        "the gel pools. Do not drink it.",
    )
    gel.set_property("portions", 3)
    gel.set_property(Property.DRINKABLE, True)  # regrettably (see the trigger)
    gel.set_property(
        Property.TASTE,
        "of lamp-oil, honey, and four thousand years. It was never water.",
    )
    gel.add_alias("gel")
    gel.add_alias("flask")
    hounds.add_item(gel)

    # Silas -- the synthetic archivist (the hint NPC). His combat / pacify / rob
    # outcomes arrive with later phases (the dagger, Friend's Fungus); for now he
    # warns you about the Spawn and the seal if you talk to him.
    silas = things.Character(
        "Silas",
        "a yellow-robed synthetic archivist",
        "I am Silas, of the Seekers of Eyeless Wisdom. I read the dead.",
    )
    silas.examine_text = (
        "A gaunt synth in fuligin-yellow robes, fingertips tipped with cranial "
        "bores, drawing memory from the lattice in slow bright threads. Patient, "
        "courteous, elsewhere. Now and then his lips move -- circular glyphs, "
        "no sound."
    )
    _silas_speech = (
        'Silas speaks without turning. "Scavenger. You walk in a house of '
        "memory; mind what you wake. Two of the Autarch's organs have got up and "
        "walk these halls wearing their own jars -- his appetites and his "
        "thoughts, if you follow me. I do not fight them; I read. The lattice "
        "remembers his embalming, for those who trouble to look, and the plinths "
        'above remember what they held." A pause; a brief run of clipped, '
        'circular syllables, like a quotation. "The dead here listen. Step '
        'softly."'
    )

    def _silas_talk(g):
        # With a living spawn in earshot, Silas will not perform the lecture.
        for name in ("spawn of guts", "spawn of brain"):
            sp = g.characters.get(name)
            if (
                sp is not None
                and sp.location is silas.location
                and not sp.get_property(Property.IS_DEAD)
                and not sp.get_property(Property.IS_UNCONSCIOUS)
                and not sp.get_property("dosed")
            ):
                return (
                    '"Be silent, you fool," Silas whispers, without turning, '
                    "and one bare finger indicates the thing swaying in the "
                    "doorway."
                )
        return _silas_speech

    silas.talk_text = _silas_talk
    # Silas keeps the Ulfire Lantern (Exotica; design doc §13). Ulfire is the
    # ninth colour: its light shines THROUGH solid objects -- the "very specific
    # angle" from which the Manifold Box's hypergeometric compartment can be
    # seen. He parts with it only for the Friend's Fungus (the give-trigger
    # below); prying it from him otherwise means fighting an INT-drinker.
    ulfire_lantern = things.Item(
        "ulfire lantern",
        "a lantern of the ninth colour",
        "A lantern worked in lead and glass, cold until lit. Ulfire is the "
        "ninth colour; its light has the unusual property of shining through "
        "solid objects, and is stopped only by lead.",
    )
    ulfire_lantern.set_property(Property.FLAMMABLE, True)
    ulfire_lantern.add_alias("lantern")
    silas.add_to_inventory(ulfire_lantern)
    memory.add_character(silas)

    # The crystal seal bars the stair up from the Canopic hall until both jars are
    # placed (registered before the game so the parser picks up the block).
    canopic.add_block("up", CrystalSeal(canopic))

    # --- The player ----------------------------------------------------------
    player = things.Character(
        "you",
        "a lone scavenger",
        "I comb the Blue Ruins for what the dead no longer need.",
    )
    # The glowstone is a lantern: dark until you LIGHT it, DOUSE to go dark
    # again. FLAMMABLE is the engine's "can be lit" flag (see actions.Light). It
    # starts UNLIT -- carrying it is safe; *lighting* it in the Hall of Youth is
    # what wakes the bats. It is FOUND (in the merchant's pack at the wreck),
    # not given: taking it is the tutorial's OPEN/TAKE beat.
    glowstone = things.Item(
        "glowstone",
        "a dim glowstone",
        "A shard of cold lazulite, dark until woken. Scavengers carry them "
        "dark: light is dear, and attention dearer.",
    )
    glowstone.set_property(Property.FLAMMABLE, True)
    glowstone.add_alias(
        "stone"
    )  # no "lantern" alias: the Ulfire Lantern owns that word
    glowstone.add_command_hint("light glowstone")
    glowstone.add_command_hint("douse glowstone")
    pack.add_item(glowstone)
    pack.add_item(waterskin)

    # The dead don't sway (CCB): state-aware one-liners for the creatures.
    spawn_guts.set_property(
        "unconscious_description",
        "the spawn of guts, collapsed in a heap, its falcon jar askew",
    )
    spawn_guts.set_property(
        "dead_description", "the spawn of guts, dead and motionless"
    )
    spawn_brain.set_property(
        "unconscious_description",
        "the spawn of brain, felled mid-step, jar rolled to its side",
    )
    spawn_brain.set_property(
        "dead_description", "the spawn of brain, dead and motionless"
    )
    jackal_pack.set_property(
        "unconscious_description", "the jackal pack, sprawled senseless where they fell"
    )
    centipede.set_property(
        "unconscious_description", "the glass centipede, cracked and still"
    )
    centipede.set_property(
        "dead_description", "the glass centipede, shattered along its length"
    )

    # Vaarn item slots (slots.py): ten -- gear and wounds share the gauge.
    player.slot_capacity = 10
    # The tomb's climbs: an encumbered scavenger cannot make them.
    exterior.set_property("climb_exits", {"up"})
    summit.set_property("climb_exits", {"down"})
    chimney.set_property("climb_exits", {"out"})

    game = TombGame(
        wreck,
        player,
        characters=[
            silas,
            spawn_guts,
            spawn_brain,
            worry,
            jackal_pack,
            horror,
            centipede,
        ],
        custom_actions=[Sneak, Burn, PryCoffin, TieSilk, Refill],
    )
    game.max_score = 100
    # Turn on the feel / listen / smell probes: the Hall of Youth's dark clue
    # (the unseen bats overhead) is meant to be heard and felt, not just seen.
    game.enable_senses()
    # Register purity by default: no command-hint training wheels in the prose
    # (design doc §16 -- danger telegraphs through fiction). Flip give_hints on
    # for a hand-held demo/classroom run; the wreck's tutorial items carry
    # their hints ("open pack", "light glowstone", "read ledger") for that mode.
    game.give_hints = False

    # The Spawn home in on noise (DrawnToSound); the mantis-headed jar amplifies
    # any noise in the Canopic hall into a luring song. Make a racket there and the
    # Spawn come to you -- the safe place to fight them (the halls are deadly).
    game.add_reaction(mantis_jar, MantisSong())
    game.add_reaction(spawn_guts, reactions.DrawnToSound())
    game.add_reaction(spawn_brain, reactions.DrawnToSound())

    # The tomb's hazards: each is patient (warns, then kills after a few rounds) and
    # has a clear out. You may WALK anywhere freely -- only light, noise, spores, or
    # disturbing the dead are dangerous.

    # The Hall of Youth is pitch dark: the Darkness veil hides the room (its exits,
    # its statues) until you raise a light, so a newcomer's instinct is to LIGHT
    # the glowstone to find the way -- which is exactly what rouses the bats. A
    # player who knows the layout can still creep through blind. (The perception
    # veil only gates what's *seen*; movement stays free -- design/perception.md.)
    # The tomb is dark wherever it doesn't light itself (CCB): Memory glows
    # crystal-cold, Hounds by its tank, Canopic by its plinths -- but the Hall
    # of Warriors is dark as duty, and the Sphere and Chimney live in the
    # bloom's own rotten half-light.
    warriors.obscure(
        perception.Darkness(
            blurb="Dark as a pocket. Your footsteps come back off plexiglas "
            "somewhere close; the air smells of old gel and older duty. And "
            "low down, near the floor, something breathes wetly, in no hurry."
        )
    )
    sphere.obscure(
        perception.Gloom(
            blurb="A rotten half-light: the coffin's orange churn glows at the "
            "chamber's heart, and the carved prayers read as texture, not words."
        )
    )
    sphere.dim_description = (
        "A spherical chamber, weightless, lit only by the slow orange churn of "
        "the coffin at its heart. Dust and bone-chips drift through the glow. "
        "The prayers on the walls are legible only as texture."
    )
    chimney.obscure(
        perception.Gloom(
            blurb="The shaft is lit by the bloom itself, a dull orange "
            "breathing; the way down is a deeper orange, the way up a paler one."
        )
    )
    chimney.dim_description = (
        "A vertical throat choked with orange growth, glowing faintly with its "
        "own rot. The spores hang so thick the air has texture. Down in the "
        "dark of it, the fungus is warm."
    )

    youth.obscure(
        perception.Darkness(
            blurb="Dark as the inside of a sealed jar. The air is chill and smells "
            "of old guano; somewhere far above, leather rustles against leather, "
            "patient and vast. The caravan-guards' word for the boy's mouth was "
            "'lightless', and they meant it as advice."
        )
    )

    # The bats: roused by carrying a LIT light into the Youth, or by a loud noise
    # there. Patient -- the escalation is the clock. Douse the light (or fall
    # quiet) and they settle.
    def _bat_maul(g):
        """Dive-bombing bats deal a non-lethal wound each round the light (or
        din) persists; death comes only if wounds fill the scavenger's slots."""
        fatal = _wound_player(
            g,
            "Bat-Mauled",
            1,
            (
                "Claw-rakes across your scalp and hands.",
                "A wing's elbow takes your ear; claws find the nape of your neck.",
                "They come through your raised arms; your knuckles come away gloved in blood.",
            ),
        )
        if fatal:
            _die(
                g,
                "The swarm takes you down among the statues, and the dark "
                "closes over the light. THE END.",
            )
        else:
            g.parser.ok(
                "The bats drop in a wheeling rake of claws -- your scalp and "
                "hands pay for the light. (You are mauled; douse it, or feed "
                "them more of yourself.)"
                if g.give_hints
                else "The bats drop in a wheeling rake of claws; your scalp and "
                "hands pay for the light."
            )
        return True

    _hazard(
        game,
        youth,
        danger=lambda g: perception.carries_light(g.player)
        or _player_was_loud_in(g, youth, _QUIET),
        warns=(
            "The rustle overhead deepens. Grit sifts down through your light; "
            "the whole vault has begun, gently, to move.",
        ),
        limit=2,  # one warning -- the bats' patience is short
        harm=_bat_maul,
    )

    # The Pthalo-jackals: drawn by sustained loud NOISE in the lower halls (walking
    # and rummaging are fine; shouting and smashing are not).
    # The pthalo-jackals, embodied (CCB design): noise draws the pack IN. Two
    # warnings, then they enter and growl -- one round of grace. GIVE them food
    # or water and they leave with it; otherwise they maul you, round after
    # round, until you feed them, flee, or fall. A blade also answers (they can
    # be knocked out), and their examine text says what they want.
    _halls = (memory, hounds, warriors)

    def _pack_out(g):
        return jackal_pack.get_property(
            Property.IS_UNCONSCIOUS
        ) or jackal_pack.get_property(Property.IS_DEAD)

    def _jackal_feed_check(g):
        return jackal_pack.inventory and not _pack_out(g)

    def _jackal_feed(g):
        fed = [
            it
            for it in jackal_pack.inventory.values()
            if it.get_property(Property.EDIBLE) or it.get_property(Property.DRINKABLE)
        ]
        refused = [it for it in jackal_pack.inventory.values() if it not in fed]
        for it in refused:
            jackal_pack.remove_from_inventory(it)
            if jackal_pack.location is not None:
                jackal_pack.location.add_item(it)
            g.parser.ok(
                f"The pack noses the {it.name} and lets it fall. It is not "
                "that kind of hunger."
            )
        if not fed:
            return
        for it in fed:
            jackal_pack.remove_from_inventory(it)  # consumed
        names = " and ".join(f"the {it.name}" for it in fed)
        g.parser.ok(
            f"The pack closes over {names} with terrible courtesy and is gone "
            "into the dark with it. The halls stay quiet a long while after."
        )
        g.relocate(jackal_pack, den)
        for h in _halls:
            h.set_property(f"_jk:{h.name}", -4)  # a fed pack forgets you a while

    game.add_trigger("jackal_feed", _jackal_feed_check, _jackal_feed, repeatable=True)

    # Venting the orange cylinder (CCB design): breaking it exhales the bloom.
    # Masked, you watch it settle; unmasked, it sears your lungs -- the same
    # wound the chimney deals, because it is the same fungus.
    def _orange_vented_check(g):
        return "orange cylinder" not in warriors.items and not warriors.get_property(
            "spores_vented"
        )

    def _orange_vent(g):
        warriors.set_property("spores_vented", True)
        if "respirator" in g.player.worn:
            g.parser.ok(
                "The bloom bursts outward in a dry orange cloud. The "
                "respirator's seal holds; the spores settle over your "
                "shoulders like ash, disappointed."
            )
            return
        fatal = _wound_player(
            g,
            "Seared Lungs",
            1,
            (
                "Every breath is smaller than the last.",
                "A cough you cannot finish, and something orange in what comes up.",
                "Your chest works like a bellows with a hole in it.",
            ),
        )
        if fatal:
            _die(g, "You breathe the bloom in, and it keeps you. THE END.")
        else:
            g.parser.ok(
                "The bloom bursts outward in a dry orange cloud and you take a "
                "breath of it before you can help it. It burns going down; "
                "something in your chest will remember this."
            )

    game.add_trigger(
        "orange_vent", _orange_vented_check, _orange_vent, repeatable=False
    )

    # The Spawn are blind, sound-hunting monsters (CCB: "shouldn't it attack?").
    # Share a room with one and be HEARD -- stride in, shout, smash -- and it
    # swings toward you (one warning), then attacks each loud round after.
    # Creep and it never knows you were there.
    def _spawn_menace(spawn, warn_text, attack):
        key = f"_sp:{spawn.name}"

        def tick(g):
            if (
                spawn.get_property(Property.IS_DEAD)
                or spawn.get_property(Property.IS_UNCONSCIOUS)
                or spawn.get_property("dosed")
            ):
                return
            loc = spawn.location
            n = spawn.get_property(key) or 0
            if loc is None or g.player.location is not loc:
                spawn.set_property(key, max(0, n - 1))
                return
            if _player_was_loud_in(g, loc, _QUIET_SPAWN):
                n += 1
                spawn.set_property(key, n)
                if n == 1:
                    g.parser.ok(warn_text)
                else:
                    attack(g)
            # No decay while you share its room: it heard you once, and it is
            # still listening. Only distance (handled above) lets it settle.

        game.add_trigger(f"menace:{spawn.name}", lambda g: True, tick, repeatable=True)

    def _guts_lash(g):
        fatal = _wound_player(
            g,
            "Acid-Lashed",
            1,
            (
                "A welt across your back, acid where it touched.",
                "The lash takes your calf; the acid keeps its own count.",
                "A wet arm cracks across your ribs and leaves its burn behind.",
            ),
        )
        if fatal:
            _die(g, "The spawn folds you into itself, patiently. THE END.")
        else:
            g.parser.ok(
                "The spawn of guts lashes out at the sound of you -- a wet arm "
                "of grave-cured muscle, acid where it touches."
            )

    def _brain_dominate(g):
        # Psychic, not physical: it opens your hands, or handles your thoughts.
        wielded = list(g.player.wielded.values())
        if wielded:
            it = wielded[0]
            g.player.wielded.pop(it.name)
            if g.player.location is not None:
                g.player.location.add_item(it)
            g.parser.ok(
                f"The spawn of brain turns its jar toward your noise, and your "
                f"hands open without your leave. The {it.name} clatters away."
            )
            return
        fatal = _wound_player(
            g,
            "Mind-Handled",
            1,
            (
                "Your thoughts arrive with someone else's fingerprints.",
                "A minute goes missing; you are somewhere in it.",
                "Your own name takes a moment too long to answer.",
            ),
        )
        if fatal:
            _die(g, "Your mind is folded shut from the outside. THE END.")
        else:
            g.parser.ok(
                "The spawn of brain turns its jar toward your noise, and "
                "something walks through your thoughts on small, precise feet."
            )

    _spawn_menace(
        spawn_guts,
        "The spawn of guts swings toward your footfalls, arms rising from the "
        "floor like kelp in a current.",
        _guts_lash,
    )
    _spawn_menace(
        spawn_brain,
        "The spawn of brain goes very still, jar cocked toward the sound of you.",
        _brain_dominate,
    )

    # The Spawn are HUNGRY (CCB): throw (or give) something edible and they eat
    # it. Friend's Fungus doses them agreeable -- a pacifist answer to both.
    def _spawn_eats_check(g):
        return any(
            sp.inventory
            and not sp.get_property(Property.IS_DEAD)
            and not sp.get_property(Property.IS_UNCONSCIOUS)
            for sp in (spawn_guts, spawn_brain)
        )

    def _spawn_eats(g):
        for sp in (spawn_guts, spawn_brain):
            if sp.get_property(Property.IS_DEAD) or sp.get_property(
                Property.IS_UNCONSCIOUS
            ):
                continue
            for it in list(sp.inventory.values()):
                # It keeps its own jar; anything ELSE edible goes down.
                if it.name in ("falcon jar", "jackal jar"):
                    continue
                if it.get_property(Property.EDIBLE):
                    sp.remove_from_inventory(it)
                    if it.name == "friend's fungus":
                        sp.set_property("dosed", True)
                        sp.description = f"{sp.name}, swaying dreamily, at peace"
                        g.parser.ok(
                            f"The {sp.name} folds the pouch into itself, and "
                            "the change is immediate: the swaying softens, the "
                            "menace drains out of it. It is extremely agreeable "
                            "now, and will be for hours."
                        )
                    else:
                        g.parser.ok(
                            f"The {sp.name} folds the {it.name} into itself, "
                            "unhurried."
                        )

    game.add_trigger("spawn_eats", _spawn_eats_check, _spawn_eats, repeatable=True)

    # The thrown-light gambit (CCB's puzzle): a LIT light lying on the Youth's
    # floor draws the swarm down onto it -- and onto anything on the floor
    # beside it. Two rounds of mobbing kill a spawn, leaving its jar and a
    # dead, motionless body. (Lure the spawn in with one thrown clatter, then
    # throw the lit glowstone in after it.)
    def _floor_light(g):
        return any(it.get_property(Property.IS_LIT) for it in youth.items.values())

    def _bat_mobbing(g):
        if not _floor_light(g):
            youth.set_property("_mob", 0)
            return
        (
            g.parser.ok(
                "In the Hall of Youth, the swarm pours down onto the light where "
                "it lies, a screaming wheel around a still point."
            )
            if g.player.location in (youth, exterior, memory, hounds)
            else None
        )
        youth.set_property("_mob", (youth.get_property("_mob") or 0) + 1)
        # Anything on the floor beside the light takes the swarm.
        for sp in (spawn_guts, spawn_brain):
            if sp.location is youth and not sp.get_property(Property.IS_DEAD):
                hits = (sp.get_property("_bat_hits") or 0) + 1
                sp.set_property("_bat_hits", hits)
                if hits >= 2:
                    sp.set_property(Property.IS_DEAD, True)
                    for it in list(sp.inventory.values()):
                        sp.remove_from_inventory(it)
                        youth.add_item(it)
                    sp.description = f"the {sp.name}, dead and motionless"
                    sp.examine_text = (
                        "Raked to stillness by the swarm. The fungus no longer "
                        "sways; whatever was listening in it has stopped."
                    )
                    g.parser.ok(
                        f"The swarm finds the {sp.name} beside the light and "
                        "rakes it, pass after pass, until it stops moving. "
                        "Something rolls free of the body."
                    )
        # The player, if fool enough to stand in the mobbing, is raked too.
        if g.player.location is youth:
            fatal = _wound_player(
                g,
                "Bat-Mauled",
                1,
                (
                    "Claw-rakes across your scalp and hands.",
                    "A wing's elbow takes your ear; claws find the nape of your neck.",
                    "They come through your raised arms; your knuckles come away gloved in blood.",
                ),
            )
            if fatal:
                _die(g, "The swarm takes you down beside the light. THE END.")

    game.add_trigger("bat_mobbing", lambda g: True, _bat_mobbing, repeatable=True)

    def _jackal_maul(g):
        g.parser.ok("The pack takes its due before you can raise an arm.")
        _, messages, fatal = roll_wound(g.player, rng=_RNG, game=g)
        for m in messages:
            g.parser.ok(m)
        if fatal or g.player.get_property(Property.IS_DEAD):
            _die(
                g,
                "The pthalo-jackals drag you down, and afterwards the tomb "
                "goes back to listening. THE END.",
            )
        else:
            g.parser.ok(
                "They do not leave. They are waiting to see what else you have."
            )

    def _jackal_tick(g):
        if _pack_out(g):
            return
        here = g.player.location
        for hall in _halls:
            key = f"_jk:{hall.name}"
            n = hall.get_property(key) or 0
            if here is not hall:
                # The trail cools toward calm from either side (suspicion
                # drains, post-feed grace wears off). The pack itself, once
                # out, PURSUES -- handled below, not here.
                hall.set_property(key, n - 1 if n > 0 else min(0, n + 1))
                continue
            if jackal_pack.location is hall:
                _jackal_maul(g)  # unfed, unfled: they collect
                continue
            if _player_was_loud_in(g, hall, _QUIET):
                # A crash carries: breaking things counts double on the ledger.
                crashed = any(
                    e.actor == g.player.name
                    and e.action == "break"
                    and (e.payload or {}).get("location") == hall.name
                    for e in g.events[g._round_event_start :]
                )
                n += 2 if crashed else 1
                hall.set_property(key, n)
                if n <= 2:
                    g.parser.ok(
                        "Somewhere off in the halls, a yipping answers your "
                        "noise -- once, and then again, nearer."
                    )
                elif n == 3:
                    g.parser.ok(
                        "Yellow eyes ring the doorways, unhurried. "
                        "Pthalo-jackals: cautious, clever, and done being "
                        "cautious."
                    )
                elif n >= 4:
                    g.relocate(jackal_pack, hall)
                    jackal_pack.set_property("_stride", True)  # first beat: hang back
                    g.parser.ok(
                        "They come in low and unhurried, cerulean-coated, "
                        "filling the doorways. The nearest growls -- a sound "
                        "with arithmetic in it -- and the pack looks from you "
                        "to your bag, and back."
                    )
                # n <= 0: a fed (or long-calmed) pack lets it go -- the noise
                # only burns through their patience.
            else:
                hall.set_property(key, n - 1 if n > 0 else min(0, n + 1))

    game.add_trigger("jackal_pack", lambda g: True, _jackal_tick, repeatable=True)

    # THE PACK PURSUES (CCB design): unlike the blind Spawn, jackals see and
    # smell -- once out, they track you through their territory (the three
    # ground halls), one hall per round. Sneaking means nothing to scent. The
    # answers are distance (keep moving), the Youth (they will not follow into
    # the bat vault), the stairs and the open sand (leave their ground long
    # enough and they give you up), tribute, or steel.
    _territory = (memory, hounds, warriors)

    def _hop_toward(start, goal):
        """One step from *start* toward *goal* through territory rooms."""
        from collections import deque

        seen = {start}
        queue = deque([(start, None)])
        while queue:
            room, first = queue.popleft()
            for nxt in room.connections.values():
                if nxt is goal:
                    return first or nxt
                if nxt in _territory and nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, first or nxt))
        return None

    def _pack_pursues(g):
        return jackal_pack.location in _territory and not _pack_out(g)

    def _pursue(g):
        here = g.player.location
        if here is jackal_pack.location:
            return  # co-located: the main tick handles the mauling
        if here in _territory:
            jackal_pack.set_property("_lost", 0)
            # A lope-and-rest rhythm: the pack closes every OTHER round, so a
            # player who keeps moving holds their lead -- and one who stops to
            # rummage is caught. Cautious, clever, patient.
            if jackal_pack.get_property("_stride"):
                jackal_pack.set_property("_stride", False)
                g.parser.ok("The yipping hangs back a room, in no hurry at all.")
                return
            jackal_pack.set_property("_stride", True)
            step = _hop_toward(jackal_pack.location, here)
            if step is not None:
                g.relocate(jackal_pack, step)
                if step is here:
                    g.parser.ok(
                        "The pack comes through the doorway at a lope, "
                        "unhurried, sure of you."
                    )
                else:
                    g.parser.ok(
                        "Behind you, the yipping keeps your pace. They are "
                        "not following your noise. They are following you."
                    )
        elif here is youth:
            g.parser.ok(
                "The yipping stops at the lightless mouth of the Hall of "
                "Youth and comes no further. Something about the dark above "
                "is theirs to respect."
            )
            g.relocate(jackal_pack, den)
        else:
            lost = int(jackal_pack.get_property("_lost") or 0) + 1
            jackal_pack.set_property("_lost", lost)
            if lost >= 3:
                jackal_pack.set_property("_lost", 0)
                g.relocate(jackal_pack, den)
                for h in _halls:
                    h.set_property(f"_jk:{h.name}", 0)
                g.parser.ok(
                    "Somewhere below, the yipping circles twice, and gives " "you up."
                )

    game.add_trigger("jackal_pursuit", _pack_pursues, _pursue, repeatable=True)

    # The chimney's spores: choke you each round you're in it without a respirator.
    def _spore_sear(g):
        fatal = _wound_player(
            g,
            "Seared Lungs",
            1,
            (
                "Every breath is smaller than the last.",
                "A cough you cannot finish, and something orange in what comes up.",
                "Your chest works like a bellows with a hole in it.",
            ),
        )
        if fatal:
            _die(g, "You breathe the tomb in, and it keeps you. THE END.")
        else:
            g.parser.ok(
                "The spores get past your clenched teeth and burn going "
                "down. Something in your chest will remember this."
            )
        return True

    _scenery(
        chimney,
        "orange growth",
        "the orange growth choking the shaft",
        "The fungus fills the chimney the way a wick fills a lamp: packed, "
        "fibrous, faintly warm, and -- like everything the gel has ever "
        "touched -- ready to burn.",
    ).add_alias("growth")

    _hazard(
        game,
        chimney,
        danger=lambda g: not (
            _is_holding(g.player, "respirator") or "respirator" in g.player.worn
        ),
        gate=lambda g: not chimney.get_property("burned"),
        warns=(
            "Each breath comes back smaller than it went out. The spores "
            "settle on your lips and taste of orange rot.",
            "Your lungs sear; the glow below swims and doubles. The chimney's "
            "warmth has begun to feel like a mouth.",
        ),
        harm=_spore_sear,
    )

    # The sphere has NO noise hazard (CCB: noise reactions are covered
    # elsewhere) -- enter, look, even shout. The Horror wakes on the deliberate
    # act alone: prying its coffin (the boss fight, below).

    # Placement trigger: both missing jars on their matching plinths -> the seal
    # opens. Fires once.
    def _seal_solved(g):
        return (
            "falcon jar" in falcon_plinth.contents
            and "jackal jar" in jackal_plinth.contents
            and not canopic.get_property("seal_open")
        )

    def _open_seal(g):
        canopic.set_property("seal_open", True)
        g.parser.ok(
            "As the last jar settles onto its plinth, the crimson light steadies to "
            "white. The crystal seal sighs apart into motes, baring the stair up."
        )
        g.award("seal", 20, None)

    game.add_trigger("canopic_seal", _seal_solved, _open_seal, repeatable=False)

    # --- The Friend's Fungus chain (design doc §13; optional, no score) ------
    # fungus (corpse) -> GIVE to Silas -> the Ulfire Lantern -> LIGHT it while
    # carrying the Manifold Box -> the hypergeometric compartment -> ego-core.

    def _silas_dosed(g):
        return "friend's fungus" in silas.inventory and not silas.get_property(
            "mellowed"
        )

    def _silas_mellows(g):
        silas.set_property("mellowed", True)
        fun = silas.inventory.get("friend's fungus")
        if fun is not None:
            silas.remove_from_inventory(fun)
        lamp = silas.inventory.get("ulfire lantern")
        if lamp is not None:
            silas.remove_from_inventory(lamp)
            g.player.add_to_inventory(lamp)
        silas.talk_text = (
            '"A friend," Silas says, warmly and a little vaguely, and returns '
            "to the lattice. The bright threads spool on."
        )
        g.parser.ok(
            "Silas takes the pouch with unexpected delicacy and presses a pinch "
            "of the pink fungus into a port beneath his jaw. The hum of his "
            'work softens by a third. "You are," he decides, "a friend. Take '
            "the lantern -- I have read it twice already, and light should be "
            'for the unread." He hands you the ulfire lantern.'
        )

    game.add_trigger("silas_fungus", _silas_dosed, _silas_mellows, repeatable=False)

    # Water mends (the canon short rest is "a quick sit-down, with a glug of
    # water"): drinking the waterskin heals the most recent wound.
    def _drank_water(g):
        return any(
            e.actor == g.player.name
            and e.action == "drink"
            and "water" in (e.summary or "").lower()
            for e in g.events[g._round_event_start :]
        )

    def _water_mends(g):
        if g.player.wounds:
            healed = g.player.heal_wound()
            g.parser.ok(
                f"The water does what water does in Vaarn. The {healed.name.lower()} "
                "troubles you less; something knits."
            )
        n = int(waterskin.get_property("portions") or 0)
        if n <= 0:
            waterskin.description = "an empty waterskin"
        else:
            waterskin.description = (
                f"a waterskin with {n} ration{'s' if n != 1 else ''}"
            )

    game.add_trigger("water_mends", _drank_water, _water_mends, repeatable=True)

    # Drinking the GEL is legal and inadvisable (design doc §17.1).
    def _drank_gel(g):
        return any(
            e.actor == g.player.name
            and e.action == "drink"
            and "gel" in (e.summary or "").lower()
            for e in g.events[g._round_event_start :]
        )

    def _gel_gut(g):
        n = int(gel.get_property("portions") or 0)
        gel.description = (
            f"a flask of gel with {n} dose{'s' if n != 1 else ''}"
            if n
            else "an empty flask"
        )
        fatal = _wound_player(
            g, "Gel-Gut", 1, "Embalming fluid, doing what it was made to do."
        )
        if fatal:
            _die(g, "You are preserved from the inside out. THE END.")
        else:
            g.parser.ok("It is not water. It was never water.")

    game.add_trigger("gel_gut", _drank_gel, _gel_gut, repeatable=True)

    # --- The boss loop (design doc §17.3) ------------------------------------
    # Each round the Horror is out, alive, and facing you: it regenerates
    # (visibly) unless ablaze, burns down if it IS ablaze, and sprays acid.
    def _horror_fighting(g):
        # The Horror's turn runs whenever it is out and alive: FIRE does not
        # care whether you are watching (CCB: douse, light, and run is a
        # legitimate tactic), and it knits while you are away too. Only the
        # acid needs you present.
        return horror.location is sphere and not horror.get_property("is_dead")

    def _horror_turn(g):
        watching = g.player.location is sphere
        vigor = int(horror.get_property("vigor") or 0)
        ablaze = int(horror.get_property("ablaze") or 0)
        if ablaze > 0:
            horror.set_property("ablaze", ablaze - 1)
            vigor -= 1
            horror.set_property("vigor", vigor)
            if vigor <= 0:
                _horror_dies(g, burned=True)
                return
            if watching:
                g.parser.ok(
                    "The fire walks the length of the Fungal Horror and it "
                    "thrashes; charred ropes of fungus drift loose. Nothing "
                    "mends. It is smaller than it was."
                )
            if ablaze - 1 == 0:
                # The window closes AUDIBLY -- never silently back to knitting.
                g.parser.ok(
                    "The fire gutters out against the wet of the Fungal "
                    "Horror's flesh. What is cut can mend again."
                    if watching
                    else "From the Burial Sphere, the roar of fire dies away "
                    "to nothing."
                )
        elif vigor < 5:
            horror.set_property("vigor", vigor + 1)
            if watching:
                # The player has now SEEN the mending -- the burn narration
                # may speak of stopping it without giving an unearned hint.
                horror.set_property("knit_seen", True)
                g.parser.ok(
                    "The rents you have cut in the Fungal Horror knit closed "
                    "before your eyes, new threads lacing across them, pale "
                    "and then orange. It is mending faster than you are."
                )
        if not watching:
            return  # the acid needs a target
        # And its answer: acid, flung weightless.
        fatal = _wound_player(
            g,
            "Acid-Burned",
            1,
            (
                "A rope of acid caught you across the shoulder.",
                "A rope of acid took the forearm you raised in time.",
                "Acid spatters your scalp and goes on burning after you wipe it.",
                "A whip of acid opens the back of your hand to the tendons.",
                "Acid across the hip; the cloth of your coat gives up first.",
            ),
        )
        if fatal:
            _die(
                g,
                "The acid takes the last of you, and the Fungal Horror folds "
                "you in among the bones it keeps. THE END.",
            )

    def _horror_dies(g, burned=False):
        horror.set_property("is_dead", True)
        horror.description = (
            "the Fungal Horror, charred and still"
            if burned
            else ("the Fungal Horror, cut apart and still")
        )
        horror.examine_text = (
            "Still at last. The coil lies slack around nothing; the bones it "
            "kept drift free."
        )
        # The coil unclenches: the coffin's keeping is over.
        coffin_item = sphere.items.get("coffin")
        released = []
        if coffin_item is not None:
            for it in list(coffin_item.contents.values()):
                coffin_item.remove_item(it)
                sphere.add_item(it)
                released.append(it.name)
        sphere.set_property("horror_dead", True)
        if g.player.location is not sphere:
            # Burned to death with no one watching: heard, not seen.
            g.parser.ok(
                "From the Burial Sphere, a long wet shriek, and then nothing "
                "at all -- not even the sound of something mending."
            )
            return
        msg = "The Horror comes apart and does not close again."
        if released:
            msg += (
                " The coil unclenches from the Autarch's bones, and what he "
                "was buried with drifts free: " + ", ".join(released) + "."
            )
        g.parser.ok(msg)

    # Striking the Horror: a weapon hit costs it one vigor, visibly.
    def _struck_horror(g):
        # The event summary is the raw command ("attack horror with blade"),
        # so match any of the thing's names.
        return any(
            e.actor == g.player.name
            and e.action == "attack"
            and any(
                a in (e.summary or "").lower()
                for a in ("fungal horror", "horror", "mass")
            )
            for e in g.events[g._round_event_start :]
        ) and not horror.get_property("is_dead")

    def _horror_struck(g):
        # Undo the engine's one-hit KO; convert it into a point of vigor.
        horror.set_property("is_unconscious", False)
        vigor = int(horror.get_property("vigor") or 0) - 1
        horror.set_property("vigor", vigor)
        if vigor <= 0:
            _horror_dies(g)
            return
        g.parser.ok(
            "The blade opens a rent in the orange mass; it seethes, and does "
            "not fall."
        )

    game.add_trigger("horror_struck", _struck_horror, _horror_struck, repeatable=True)

    # Throwing the gel AT the Horror douses it (CCB's instinctive sequence):
    # the flask bursts a dose across the coil, and the next spark needs no
    # pour of its own.
    def _gel_thrown_at_horror(g):
        return (
            not horror.get_property("is_dead")
            and not horror.get_property("gel_doused")
            and any(
                e.actor == g.player.name
                and e.action == "throw"
                and "gel" in (e.summary or "").lower()
                and any(
                    a in (e.summary or "").lower() for a in ("horror", "mass", "fungal")
                )
                for e in g.events[g._round_event_start :]
            )
        )

    def _gel_splash(g):
        flask = None
        for holder in (g.player.carried_items(), sphere.items):
            if "flask of gel" in holder:
                flask = holder["flask of gel"]
                break
        if flask is None or int(flask.get_property("portions") or 0) <= 0:
            return
        n = int(flask.get_property("portions")) - 1
        flask.set_property("portions", n)
        flask.description = (
            f"a flask of gel with {n} dose{'s' if n != 1 else ''}"
            if n
            else "an empty flask"
        )
        horror.set_property("gel_doused", True)
        g.parser.ok(
            "The flask bursts against the Fungal Horror and a dose of "
            "embalming gel sheets across the orange, luminous, clinging. "
            "It wants only a spark."
        )

    game.add_trigger("gel_splash", _gel_thrown_at_horror, _gel_splash, repeatable=True)

    # --- The glass centipede's ambush -----------------------------------------
    def _centipede_lurks(g):
        return (
            not centipede.get_property("is_dead")
            and not centipede.get_property("is_unconscious")
            and g.player.location is chimney
        )

    def _centipede_bites(g):
        if chimney.get_property("burned") and centipede.location is not chimney:
            return  # scoured out before it ever sprang
        if centipede.location is not chimney:
            g.relocate(centipede, chimney)
            g.parser.ok(
                "The growth beside you bends wrong -- and four feet of glass "
                "uncoils out of it, faster than the eye wants to allow."
            )
        fatal = _wound_player(
            g,
            "Centipede Venom",
            1,
            (
                "Twin punctures in the calf; the venom goes in cold.",
                "It takes you through the boot-seam; the leg answers slowly after.",
                "A bite at the wrist as you shield your face; the arm hums.",
            ),
        )
        if fatal:
            _die(
                g,
                "The venom finishes what the tomb began; the shaft keeps you. "
                "THE END.",
            )

    game.add_trigger(
        "centipede_ambush", _centipede_lurks, _centipede_bites, repeatable=True
    )

    # Fire scours the shaft: the centipede goes with the growth.
    def _centipede_scoured(g):
        return chimney.get_property("burned") and not centipede.get_property("is_dead")

    def _scour(g):
        was_senseless = centipede.get_property("is_unconscious")
        centipede.set_property("is_dead", True)
        if centipede.location is chimney:
            # A senseless thing does not boil out of anything (CCB playtest:
            # the "cracked and still" centipede seemed to die twice).
            g.parser.ok(
                "The fire finds the cracked thing where it lies; it seizes "
                "once in the flame, and is still."
                if was_senseless
                else "Something four feet long and glassy boils out of the "
                "burning growth, seizes once, and is still."
            )
        else:
            g.relocate(centipede, chimney)
            centipede.set_property("is_hidden", True)
            g.parser.ok(
                "In the flames, something glassy spasms out of the growth and "
                "drops away down the shaft."
            )

    game.add_trigger("centipede_scoured", _centipede_scoured, _scour, repeatable=False)
    game.add_trigger("horror_turn", _horror_fighting, _horror_turn, repeatable=True)

    # Eating the Autarch's preserved organs (CCB: "gross, but should be
    # gettable... edible, with horrible effects"). Four thousand years of
    # preservative disagree with the living; the fungal eyes disagree worse.
    _ORGANS = {"lungs", "liver", "intestines", "brain", "fungal eyes"}

    def _ate_organ(g):
        return any(
            e.actor == g.player.name
            and e.action == "eat"
            and any(o in (e.summary or "").lower() for o in _ORGANS)
            for e in g.events[g._round_event_start :]
        )

    def _grave_sick(g):
        ate_eyes = any(
            e.actor == g.player.name
            and e.action == "eat"
            and "eyes" in (e.summary or "").lower()
            for e in g.events[g._round_event_start :]
        )
        if ate_eyes:
            fatal = _wound_player(
                g, "Spore-Gut", 2, "Something has taken root where food goes."
            )
            msg = (
                "The eyes go down like oysters and begin, at once, to garden. "
                "Something has taken root where food goes."
            )
        else:
            fatal = _wound_player(
                g, "Grave-Sick", 1, "The Autarch's preservatives at work in you."
            )
            msg = (
                "It goes down. The Autarchy embalmed to last, and the "
                "preservatives set to work at once on the living."
            )
        if fatal:
            _die(g, "You are preserved from the inside out. THE END.")
        else:
            g.parser.ok(msg)

    game.add_trigger("grave_sick", _ate_organ, _grave_sick, repeatable=True)

    ego_core = things.Item(
        "ego-core",
        "An-Rah's ego-core",
        "A spindle of smoke-grey memory-crystal, heavier than it looks and "
        "warmer than it should be: Nassak An-Rah, or what he chose to keep of "
        "himself. Silas would trade his robes for it.",
    )
    ego_core.add_alias("core")

    def _box_viewed(g):
        return (
            ulfire_lantern.get_property(Property.IS_LIT)
            and "ulfire lantern" in g.player.inventory
            and "manifold box" in g.player.inventory
            and not manifold_box.get_property("compartment_found")
        )

    def _reveal_core(g):
        manifold_box.set_property("compartment_found", True)
        g.player.add_to_inventory(ego_core)
        g.parser.ok(
            "The ulfire light soaks through the manifold box's gilded walls, "
            "and its true interior opens to your eye: a compartment three "
            "times larger than the box that holds it, empty except for a "
            "spindle of grey crystal hanging in the middle of that impossible "
            "room. You reach in along the angle of the light and draw out "
            "An-Rah's ego-core."
        )

    game.add_trigger("ulfire_box", _box_viewed, _reveal_core, repeatable=False)

    # Win: escape to the surface carrying both Exotica (the Dagger + the Box).
    def _escape(g):
        g.player.set_property("escaped", True)
        g.award("escape", 20, None)
        g.parser.ok(
            "You climb out into the phthalo sands. The dying sun stains the dunes "
            "red, the Autarch's Exotica heavy in your pack. You have plundered the "
            f"Tomb of Nassak An-Rah and lived. (Score {g.score}/{g.max_score}.) THE END."
        )
        g.game_over = True
        g.game_over_description = "Escaped the Blue Ruins with the Autarch's Exotica."

    game.add_trigger(
        "escape",
        lambda g: g.player.location is exterior
        and "synth-hunting dagger" in g.player.inventory
        and "manifold box" in g.player.inventory
        and not g.game_over,
        _escape,
        repeatable=False,
    )
    return game


# ---------------------------------------------------------------------------
# A smoke tour (--walk): traverse every room and read it. No win yet.
# ---------------------------------------------------------------------------

# A SAFE tour: the tomb is deadly now, so creep (sneak) through the halls and
# don't enter the lethal Burial Sphere. Visits the seven survivable rooms.
WALK = [
    # The onboarding beats at the Caravan Wreck (the start): examine, talk,
    # open/take, then light/douse/read in the safe dark of the hold.
    "examine wreck",
    "search merchant",
    "talk to worry",
    "open pack",
    "take glowstone",
    "in",
    "light glowstone",
    "read ledger",
    "douse glowstone",
    "out",
    "north",  # -> Tomb Exterior
    "examine tomb",
    "up",
    "examine ossified corpse",
    "down",  # Summit and back (safe)
    "north",
    "examine ceiling",
    "feel statues",  # -> Hall of Youth: dark-craft (hear, touch)
    "light glowstone",
    "douse glowstone",  # one stolen glance -- the bats stir, then settle
    "north",
    "talk to silas",
    "examine crystal lattice",  # -> Hall of Memory
    "sneak north",  # -> Hall of Warriors: dark, and something breathes in it
    "light glowstone",  # no bats here -- light is safe, and the colours matter
    "examine cylinders",
    "break cerulean cylinder",
    "take blade",  # loud -- a yip, a swaying spawn; then quiet again
    "east",
    "examine tank",  # -> Hall of Hounds
    "up",
    "open baboon jar",
    "examine falcon plinth",  # -> Canopic hall
]


# The full 100/100 winning run: arm up (creeping the deadly halls), lure and fell
# the Spawn to claim the jars, open the seal, climb out and burn the corpse to
# kill the Horror, then loot the now-safe Sphere with the boots and escape.
WIN_WALKTHROUGH = [
    # Loot the wreck (water heals; the glowstone lights the dark Warriors).
    "open pack",
    "take glowstone",
    "take waterskin",
    "north",
    "sneak east",  # Warriors: pitch dark; the kit is sealed in the cylinders
    "light glowstone",  # safe here -- no bats -- and the colours matter
    "break amber cylinder",  # the eyeless spawn swings toward the crash --
    "take respirator",  # -- and the crashes call its brother from next door
    "wear respirator",
    "break cerulean cylinder",  # second crash: the lash lands; take the blade
    "take blade",
    "attack spawn of guts with blade",  # answer it: the falcon jar drops
    "take falcon jar",
    "attack spawn of brain with blade",  # its brother came to the noise: fell it too
    "take jackal jar",
    "drink water",  # a glug; something knits (keep the blade: the coffin wants it)
    "drink water",  # another -- the brain got its thoughts in
    "drink water",  # the last ration; the skin runs dry
    "drop waterskin",  # travel light; the climbs refuse a full pack
    "break orange cylinder",  # the bloom vents against the mask, disappointed
    "take igniter",
    "break viridian cylinder",
    "take boots",
    "douse glowstone",
    "drop glowstone",  # the halls ahead light themselves
    "sneak east",
    "take gel",  # Hounds: gel
    "sneak up",  # -> Canopic (no luring needed -- the jars came off the dead)
    "put falcon jar on falcon plinth",
    "put jackal jar on jackal plinth",  # seal opens
    "sneak left stairs",  # the left stairs descend to Memory
    "sneak south",
    "sneak south",  # Canopic -> Exterior (dark and quiet through the Youth)
    "up",
    "burn corpse",  # Summit: cleanse the root
    "down",
    "sneak north",
    "sneak north",
    "sneak up",  # back to Canopic
    "up",
    "wear boots",
    "pry coffin",  # Sphere: loot
    "take dagger",
    "take manifold box",
    "sneak down",  # Sphere -> Canopic
    "sneak left stairs",  # -> Memory
    "sneak south",
    "sneak south",  # escape -> WIN
]


def _run(commands):
    game = build_game()
    game.parser.parse_command("look")
    for cmd in commands:
        if game.is_game_over():
            break
        print(f"\n>>> {cmd}")
        game.do_command(cmd)
    print("\n" + "=" * 60)
    print(
        f"WON: {game.is_won()}   GAME_OVER: {game.is_game_over()}   "
        f"SCORE: {game.score}/{game.max_score}"
    )
    return game


if __name__ == "__main__":
    import sys

    if "--win" in sys.argv:
        _run(WIN_WALKTHROUGH)
    elif "--walk" in sys.argv:
        _run(WALK)
    else:
        build_game().game_loop()
