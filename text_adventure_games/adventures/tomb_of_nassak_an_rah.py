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

from text_adventure_games import (
    games,
    things,
    actions,
    blocks,
    reactions,
    perception,
)
from text_adventure_games.enums import Property
from text_adventure_games.adventures import vaarn_selves
from text_adventure_games.hints import Hint
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


# The lattice holds the Autarch's DAYS (CCB: deeper now). Each facet has a
# NAME the REMEMBER verb answers to, and a continuation that notices what the
# expedition has since done -- the lattice is the tomb's commentary track.
# EXAMINE draws unseen facets first; once every remembered day has been
# consulted, a hidden bank wakes: the keep-list, the day he chose. The
# embalming replay (the jar-puzzle clue) stays findable by name the moment
# Silas points at it.
_LATTICE_FACETS = (
    {
        "key": "embalming",
        "name": "THE EMBALMING",
        "words": ("embalming", "embalm", "funeral", "organs"),
        "text": (
            "the Autarch's embalming: the baboon took his lungs, the human his "
            "liver, the mantis his eyes; the falcon was given his intestines, and "
            "the jackal -- strangely -- his brain."
        ),
        "more": lambda g: (
            " The jars stand answered on their plinths now; the stair took "
            "the lattice at its word."
            if g.locations["Hall of the Canopic Jars"].get_property("seal_open")
            else (
                " The hall of plinths below wears the same five faces. The "
                "lattice has been telling you where things go."
                if g.locations["Hall of the Canopic Jars"].has_been_visited
                else ""
            )
        ),
    },
    {
        "key": "bath",
        "name": "THE BATH",
        "words": ("bath", "water", "weeping", "immersion"),
        "text": (
            "a bath: full immersion, water to the chin and warm -- a luxury no one "
            "now living has tasted. He weeps in it, quietly, where no court can "
            "see, and the crystal keeps the weeping with the warmth."
        ),
        "more": lambda g: (
            " Water still mends, in Vaarn. You have felt what he wept for."
            if g.scored("healed")
            else ""
        ),
    },
    {
        "key": "mother",
        "name": "HIS MOTHER",
        "words": ("mother", "neck", "his mother"),
        "text": (
            "his mother's hand on the back of his neck, from before either crown "
            "or name. The facet is brief. It is the most consulted bank in the "
            "lattice; the wear on the crystal says so."
        ),
        "more": lambda g: (
            " Silas says there is a daughter counting to a hundred in the "
            "ego-core. The hand he kept HERE, at hand-height, where hands "
            "could reach it."
            if g.characters["Silas"].get_property("core_traded")
            else ""
        ),
    },
    {
        "key": "first blood",
        "name": "FIRST BLOOD",
        "words": ("first blood", "blood", "cousin", "training yard"),
        "text": (
            "the first time he drew blood: a training yard, a cousin's forearm "
            "opened by accident, and the long second in which he understands that "
            "no one is going to punish him. The facet ends on that second."
        ),
        "more": lambda g: (
            " No one has punished you, either."
            if g.scored("spawn_guts")
            or g.scored("spawn_brain")
            or g.scored("jackals_settled")
            else ""
        ),
    },
    {
        "key": "the raising",
        "name": "THE RAISING",
        "words": ("raising", "banners", "vice", "staff", "crown"),
        "text": (
            "the day they raised him: ten thousand banners the colour of this sand, "
            "and his own hands shaking too hard to take the staff, so that he grips "
            "his wrist to steady it -- the gesture his historians would later call "
            "the Vice."
        ),
        "more": lambda g: (
            " The guards in the western hall were buried gripping their "
            "wrists the same way. The Vice outlived his historians."
            if g.locations["Hall of Warriors"].has_been_visited
            else ""
        ),
    },
    {
        "key": "physician",
        "name": "THE PHYSICIAN'S CHAMBER",
        "words": ("physician", "sample", "chamber", "orange"),
        "text": (
            "a physician's chamber. Something orange in a sample-jar, small as a "
            "coin, and An-Rah watching it move against the glass with an expression "
            "the facet preserves exactly. It is not fear."
        ),
        "more": lambda g: (
            " The sample outlived him by four thousand years. You have "
            "since corrected that."
            if g.locations["Burial Sphere of Nassak An-Rah"].get_property("horror_dead")
            else (
                " You have seen that expression since -- on the thing "
                "wearing his bones."
                if g.characters["fungal horror"].location
                is g.locations["Burial Sphere of Nassak An-Rah"]
                else ""
            )
        ),
    },
    {
        "key": "seeds",
        "name": "THE EIGHT-JOINTED HANDS",
        "words": ("seeds", "starlight", "eight", "eight-jointed"),
        "text": (
            "a memory that is not his: eight-jointed hands sorting seeds by "
            "starlight, patient as arithmetic. The lattice does not say whose day "
            "this was, or how it got in among the king's."
        ),
        "more": lambda g: (
            " Something in the jar-hall below sorts SOUND the way these "
            "hands sort seeds. The lattice keeps its counsel."
            if g.locations["Hall of the Canopic Jars"].has_been_visited
            else ""
        ),
    },
    {
        "key": "kestrel",
        "name": "THE KESTREL",
        "words": ("kestrel", "bird", "falconry", "wrist"),
        "text": (
            "an old man's hands -- his own, by then -- teaching a kestrel to stand "
            "on a wrist, over and over, with the patience of a man who has outlived "
            "everyone who would have laughed at him."
        ),
        "more": lambda g: (
            " That wrist lies composed now among its wrappings. You "
            "arranged it yourself."
            if g.locations["Burial Sphere of Nassak An-Rah"]
            .items["coffin"]
            .get_property("fixed")
            else (
                " That wrist is adrift in the sphere below, gold wire "
                "loose at the joints."
                if g.locations["Burial Sphere of Nassak An-Rah"].get_property(
                    "horror_dead"
                )
                else ""
            )
        ),
    },
    {
        "key": "tombwrights",
        "name": "THE TOMBWRIGHTS",
        "words": ("tombwrights", "measurements", "smile", "faces", "sky"),
        "text": (
            "the tombwrights taking his measurements while he still lived; his own "
            "voice, bored, asking whether the sky-facing face might be made to "
            "smile. It was not."
        ),
        "more": lambda g: (
            " You have since taught the face's owner to smile after all "
            "-- from the inside."
            if g.locations["Burial Sphere of Nassak An-Rah"]
            .items["prayers"]
            .get_property("slumber_spent")
            else ""
        ),
    },
    {
        "key": "the choosing",
        "name": "THE CHOOSING",
        "words": ("choosing", "keep-list", "chose", "kept", "the day he chose"),
        "hidden": True,  # wakes only once every other day has been consulted
        "text": (
            "the day he chose: a table of wax tablets, the tombwrights' "
            "ledger of what a lattice can hold, and An-Rah, old, striking "
            "lines from it. The decrees go. The conquests go. The ten "
            "thousand banners go. What stays: the bath. The hand on the "
            "neck. The kestrel, the weeping, the seeds that were never his. "
            "And at the bottom, in the king's own unpracticed hand, one "
            "entry the wrights did not offer: THE DAY I CHOSE. KEEP THIS "
            "TOO, SO THAT WHOEVER READS ME KNOWS I KNEW."
        ),
    },
)

#: Compatibility view (tests and prose tooling read the raw day-texts).
_LATTICE_MEMORIES = tuple(f["text"] for f in _LATTICE_FACETS if not f.get("hidden"))


def _facet_text(g, lattice, i):
    """Show facet *i*: mark it consulted, pay the first-look award (and the
    completion award if this is the hidden keep-list), and return the text
    with any continuation the expedition has earned."""
    mask = int(lattice.get_property("_seen") or 0)
    first = not mask & (1 << i)
    lattice.set_property("_seen", mask | (1 << i))
    g.award("lattice", 5, "[+5 -- a dead king's days]")
    facet = _LATTICE_FACETS[i]
    if facet.get("hidden") and first:
        g.award("remembered", 5, "[+5 -- every remembered day, in its order]")
    extra = facet["more"](g) if facet.get("more") else ""
    return facet["text"] + (extra or "")


def _lattice_look(g=None):
    """A facet per look (callable examine_text): UNSEEN days first, so the
    sifting converges; when every remembered day has been consulted, the
    hidden bank -- the keep-list -- wakes exactly once, then the lattice
    returns to replaying at its own whim."""
    intro = (
        "Lazulite crystals knit across the walls, worn smooth at "
        "hand-height. A bank wakes at your attention and replays "
    )
    if g is None:
        return intro + _RNG.choice(_LATTICE_MEMORIES)
    lattice = g.locations["Hall of Memory"].items["crystal lattice"]
    mask = int(lattice.get_property("_seen") or 0)
    unseen = [
        i
        for i, f in enumerate(_LATTICE_FACETS)
        if not f.get("hidden") and not mask & (1 << i)
    ]
    if unseen:
        return intro + _facet_text(g, lattice, _RNG.choice(unseen))
    hidden_i = next(i for i, f in enumerate(_LATTICE_FACETS) if f.get("hidden"))
    if not mask & (1 << hidden_i):
        return (
            "The banks go quiet at your attention -- all of them, at once: "
            "every remembered day consulted, and the lattice knows it. Deep "
            "in the wall a bank you have never seen wakes, unworn, and "
            "replays " + _facet_text(g, lattice, hidden_i)
        )
    return intro + _facet_text(g, lattice, _RNG.choice(range(len(_LATTICE_FACETS))))


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

    def check_preconditions(self) -> bool:
        # Engine sounds (say, breaks, the clatter of an overloaded pack) --
        # the Startle base -- OR the Spawn's ear (CCB: walking in unsneakily
        # must start the song; footfalls carry, and the jar listens exactly
        # like the jar-headed Spawn it calls to).
        if super().check_preconditions():
            return True
        loc = self.owner.location
        if loc is None:
            holder = getattr(self.owner, "owner", None)
            loc = getattr(holder, "location", None)
        if loc is None:
            return False
        return _player_was_loud_in(self.game, loc, _QUIET_SPAWN)

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
            if horror is not None and horror.get_property("is_dead"):
                self.parser.fail("It is already still, and past burning's help.")
                return False
            if horror is None or horror.location is not self.player.location:
                self.parser.fail(
                    "The mass is sealed behind the glass; burn what feeds it, or open its door."
                )
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
            # held since the eruption drift free in the sphere, its remains
            # hang there as ash, and the room's descriptions follow (CCB).
            horror = self.game.characters.get("fungal horror")
            if horror is not None and not horror.get_property("is_dead"):
                horror.set_property("is_dead", True)
                sphere_loc = self.game.locations["Burial Sphere of Nassak An-Rah"]
                if horror.location is sphere_loc:
                    message += (
                        " Far below, its coil collapses mid-motion, every "
                        "thread of it gone slack at once."
                    )
                    coffin_item = sphere_loc.items.get("coffin")
                    if coffin_item is not None:
                        for it in list(coffin_item.contents.values()):
                            coffin_item.remove_item(it)
                            sphere_loc.add_item(it)
                    sphere_loc.remove_character(horror)
                    _sphere_aftermath(self.game, ash=True)
                else:
                    # Never erupted: the thing in the coffin dies unseen, and
                    # the slow churn behind the glass goes still.
                    _sphere_quieted(self.game)
            self.parser.ok(message)
            self.game.award("horror", 25, "[+25 -- the Horror is ended]")
        elif target == "chimney":
            chimney_loc = self.game.locations["The Fungal Chimney"]
            chimney_loc.set_property("burned", True)
            _chimney_burned_out(self.game)
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
            self.game.show_figure("autarch-e")
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


class ExamineSelf(actions.Action):
    """EXAMINE SELF (CCB's easter egg): once per expedition, the scavenger
    discovers who they have been all along -- one of a hundred pregenerated
    Vaarnish selves (vaarn_selves.py). The draw happens at action time and
    the command journals, so a save remembers your face; every later look
    finds the same one."""

    ACTION_NAME = "examine self"
    ACTION_DESCRIPTION = "Take stock of yourself"
    ACTION_ALIASES = [
        "examine myself",
        "x self",
        "x myself",
        "look at self",
        "look at myself",
        "inspect self",
        "who am i",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        i = self.player.get_property("_self_index")
        if i is False or i is None:  # never rolled (index 0 is a real self)
            i = _RNG.randrange(len(vaarn_selves.SELVES))
            self.player.set_property("_self_index", i)
            intro = (
                "You take stock of yourself, perhaps for the first time "
                "since the Cacklemaw. "
            )
        else:
            intro = "You remain, on inspection, yourself. "
        self.parser.ok(intro + vaarn_selves.SELVES[int(i)])


class Remember(actions.Action):
    """REMEMBER <day> (CCB): directed recall at the lattice. A bank answers
    to its NAME -- the embalming, his mother, the kestrel -- for whoever
    knows what to ask for (Silas names several; the rest are earned by
    looking). EXAMINE stays the lattice choosing; REMEMBER is you asking."""

    ACTION_NAME = "remember"
    ACTION_DESCRIPTION = "Ask the lattice for one of the Autarch's days by name"
    ACTION_ALIASES = ["recall"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.command = command.lower()
        loc = self.player.location
        self.lattice = loc.items.get("crystal lattice") if loc else None
        self.facet_i = None
        for i, f in enumerate(_LATTICE_FACETS):
            if any(w in self.command for w in f["words"]):
                self.facet_i = i
                break

    def check_preconditions(self) -> bool:
        if self.lattice is None:
            self.parser.fail(
                "Nothing here holds a dead man's days. The memory-crystal "
                "is in the Hall of Memory."
            )
            return False
        mask = int(self.lattice.get_property("_seen") or 0)
        if self.facet_i is None:
            consulted = [
                f["name"] for i, f in enumerate(_LATTICE_FACETS) if mask & (1 << i)
            ]
            if consulted:
                self.parser.fail(
                    "Which day? The banks you have consulted answer to: "
                    + "; ".join(consulted)
                    + ". (REMEMBER THE EMBALMING -- and Silas may name "
                    "others.)"
                )
            else:
                self.parser.fail(
                    "The lattice shows what it chooses (EXAMINE LATTICE) -- "
                    "but a bank answers to its NAME, for whoever knows what "
                    "to ask for. Silas has named a few."
                )
            return False
        facet = _LATTICE_FACETS[self.facet_i]
        if facet.get("hidden") and not mask & (1 << self.facet_i):
            self.parser.fail(
                "If the lattice keeps such a day, it has not shown it to "
                "you. Some banks wake only for a finished reader."
            )
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "You lay your fingers where the wear is deepest and ask. The "
            "bank wakes under them and replays "
            + _facet_text(self.game, self.lattice, self.facet_i)
        )


class FixCoffin(actions.Action):
    """FIX COFFIN (CCB): once the Fungal Horror is destroyed, gather the
    orbiting shards around the Autarch's drifting bones, wrap the whole in
    spider-silk, and let the sphere's anti-entropy field fuse the cracks.
    The chamber answers the kindness: every spoken prayer is re-cut into
    the walls, and a NEW line rises -- the Prayer of Peaceful Slumber."""

    ACTION_NAME = "fix coffin"
    ACTION_DESCRIPTION = (
        "Re-house the Autarch: gather the shards, wrap them in silk, let "
        "the field fuse them"
    )
    ACTION_ALIASES = [
        "fix the coffin",
        "repair coffin",
        "repair the coffin",
        "rebuild coffin",
        "rebuild the coffin",
        "restore coffin",
        "restore the coffin",
        "reassemble coffin",
        "gather shards",
        "gather the shards",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or "coffin" not in loc.items:
            self.parser.fail("There's no coffin here to fix.")
            return False
        coffin = loc.items["coffin"]
        bones_adrift = "Autarch's bones" in loc.items
        if not coffin.get_property("pried") and not bones_adrift:
            self.parser.fail("The coffin is whole, and its tenant housed.")
            return False
        if not loc.get_property("horror_dead"):
            self.parser.fail(
                "Not while the thing that wore him still lives. The fixing "
                "of this room starts with the Horror's ending."
            )
            return False
        if (
            "bolt of spider-silk" not in self.player.carried_items()
            and not coffin.get_property("tethered")
        ):
            self.parser.fail(
                "The pieces want holding while the field thinks -- "
                "something long, light, and stronger than it looks. Silk."
            )
            return False
        return True

    def apply_effects(self):
        loc = self.player.location
        coffin = loc.items["coffin"]
        silk = self.player.carried_items().get("bolt of spider-silk")
        if silk is not None:
            self.player.discard_item(silk)
            wrap = (
                "A wrap of spider-silk, paid out arm over arm, holds the "
                "puzzle closed."
            )
        else:  # the old lashing, re-purposed
            coffin.set_property("tethered", False)
            wrap = (
                "The lashing you tied for the prying serves a gentler "
                "purpose now, drawn tight around the whole."
            )
        pried = coffin.get_property("pried")
        gather = (
            "You gather the orbiting shards out of the air one by one and "
            "fit them around the Autarch's drifting bones -- a glass "
            "eggshell reassembled in zero gravity around its king. "
            if pried
            else "You open the seam the field left soft, gather the "
            "Autarch's drifting bones, and settle them home among their "
            "wrappings. "
        )
        bones = loc.items.get("Autarch's bones")
        if bones is not None:
            loc.remove_item(bones)
        coffin.set_property("pried", False)
        coffin.set_property("is_closed", True)
        coffin.set_property("fixed", True)
        coffin.description = "the Autarch's anti-entropy coffin, made whole"
        coffin.examine_text = (
            "The glass sphere hangs whole at the chamber's heart, its "
            "equator seamless -- you know where the cracks were, and cannot "
            "find them. Past the clearing cloud, Nassak An-Rah lies "
            "re-housed among his wrappings, composed, the gold wire at his "
            "joints at rest."
        )
        desc = (
            "A spherical chamber carved over every inch with funeral "
            "prayers, and nothing in it obeys the ground. The coffin hangs "
            "whole at the dead centre, seam sealed, the Autarch re-housed "
            "within; the chamber is quiet in the way of a made bed."
        )
        if "drift of ash" in loc.items:
            desc += " The ash of the Horror turns in its slow orbit, out of respect."
        loc.description = desc
        loc.dim_description = (
            "A spherical chamber, weightless and quiet. A whole dark shape "
            "hangs at the centre, and nothing in the room is broken."
        )
        prayers = loc.items.get("prayers")
        if prayers is not None:
            for key in ("balm", "wrath", "mending"):
                prayers.set_property(key + "_spent", False)
            prayers.set_property("slumber_known", True)
            prayers.set_property("read_text", _prayers_text(prayers))
        self.parser.ok(
            gather + wrap + " Then the chamber does what it was built to "
            "do: the anti-entropy field leans on the cracks until they "
            "remember being whole, seams closing like water under the "
            "silk, and the coffin hangs at the centre of its sphere as if "
            "nothing had ever presumed to open it. Along the walls, the "
            "answered prayers rise again out of the smooth stone, re-cut "
            "-- and beneath them a NEW line, deeper than the rest: the "
            "PRAYER OF PEACEFUL SLUMBER."
        )
        self.game.show_figure("autarch")


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
                "all at once. From among the shattered glass the Fungal "
                "Horror emerges: a mass of animate orange fungus coiled "
                "around the bones of the Autarch, moving his dead limbs like "
                "its own. It strikes at you with a speed no gravity "
                "encumbers, sending the coffin shards spinning outward."
            )
            _sphere_erupted(self.game)
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
        _sphere_aftermath(self.game, ash=False)


def _prayers_text(prayers):
    """The carvings' READ text, kept current as the chamber answers each
    prayer: a spoken prayer's line goes smooth and unlettered."""
    entries = [
        ("balm", "the PRAYER OF BALM, for the mourner's hurts"),
        (
            "wrath",
            "the PRAYER OF WRATH, a word the Autarchs kept for what would not die",
        ),
        (
            "mending",
            "the PRAYER OF MENDING, for vessels broken before their time",
        ),
    ]
    if prayers.get_property("slumber_known"):
        entries.append(
            (
                "slumber",
                "the PRAYER OF PEACEFUL SLUMBER, new-cut and deepest, for a "
                "king put properly to bed",
            )
        )
    live = [text for key, text in entries if not prayers.get_property(key + "_spent")]
    spent = [key.upper() for key, _ in entries if prayers.get_property(key + "_spent")]
    parts = [
        "Line over line, wall over wall -- most of it is names, titles, and "
        "grief in the old liturgical hand."
    ]
    if live:
        parts.append(
            "Three lines are cut deeper than the rest, ringed to be spoken "
            "aloud, and the chamber answers each ONCE: "
            + "; ".join(live)
            + ". To speak one: SAY PRAYER OF BALM."
            if len(live) == 3
            else "Of the three ringed prayers, these still wait to be spoken: "
            + "; ".join(live)
            + "."
        )
    if spent:
        parts.append(
            "Where the "
            + " and the ".join("PRAYER OF " + k for k in spent)
            + " stood, the stone is smooth and unlettered now; the chamber "
            "has answered."
        )
    if not live:
        parts.append("The chamber owes nothing more.")
    return " ".join(parts)


class SayPrayer(actions.Action):
    """SAY one of the Burial Sphere's carved funeral prayers (CCB): the
    chamber was carved to be read aloud from every direction at once, and it
    answers each of its three prayers exactly once. BALM closes a wound;
    WRATH strikes the Fungal Horror like a blow; MENDING calls the shattered
    coffin's glass back into one piece."""

    ACTION_NAME = "say prayer"
    ACTION_DESCRIPTION = "Say one of the carved funeral prayers aloud"
    ACTION_ALIASES = [
        "say prayers",
        "say the prayers",
        "recite prayer",
        "recite prayers",
        "pray",
        "say prayer of balm",
        "say balm prayer",
        "say healing prayer",
        "say prayer of wrath",
        "say wrath prayer",
        "say attack prayer",
        "say prayer of mending",
        "say mending prayer",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.command = command.lower()
        loc = self.player.location
        self.prayers = loc.items.get("prayers") if loc else None
        if "balm" in self.command or "heal" in self.command:
            self.which = "balm"
        elif "wrath" in self.command or "attack" in self.command:
            self.which = "wrath"
        elif "mend" in self.command:
            self.which = "mending"
        elif any(w in self.command for w in ("slumber", "sleep", "peaceful")):
            self.which = "slumber"
        else:
            self.which = None

    def check_preconditions(self) -> bool:
        if self.prayers is None:
            self.parser.fail(
                "Nothing here is carved to be answered. The funeral prayers "
                "are cut into the Burial Sphere, and they listen only there."
            )
            return False
        if self.which is None:
            self.parser.fail(
                "The carvings ring three prayers to be spoken (READ PRAYERS "
                "to study them): SAY PRAYER OF BALM, SAY PRAYER OF WRATH, or "
                "SAY PRAYER OF MENDING."
            )
            return False
        if self.prayers.get_property(self.which + "_spent"):
            self.parser.fail(
                f"Where the Prayer of {self.which.capitalize()} was carved, "
                "the stone is smooth and unlettered. The chamber has "
                "answered it once, and owes nothing more."
            )
            return False
        if self.which == "balm" and not self.player.wounds:
            self.parser.fail(
                "You shape the first syllable of the Prayer of Balm and the "
                "carvings do not warm to it. You are unhurt; the chamber "
                "will not spend its grace on whole flesh."
            )
            return False
        if self.which == "wrath":
            horror = self.game.characters.get("fungal horror")
            if (
                horror is None
                or horror.get_property("is_dead")
                or horror.location is not self.player.location
            ):
                self.parser.fail(
                    "The Prayer of Wrath wants a target the Autarchs feared, "
                    "and nothing before you answers that description."
                )
                return False
        if self.which == "mending":
            coffin = self.player.location.items.get("coffin")
            if coffin is None or not coffin.get_property("pried"):
                self.parser.fail(
                    "The Prayer of Mending finds no broken vessel to close. "
                    "The coffin is whole."
                )
                return False
        if self.which == "slumber":
            if not self.prayers.get_property("slumber_known"):
                self.parser.fail(
                    "No such line is carved here -- not yet. The chamber "
                    "cuts new prayers only for new kindnesses."
                )
                return False
            coffin = self.player.location.items.get("coffin")
            if coffin is None or not coffin.get_property("fixed"):
                self.parser.fail(
                    "The Prayer of Peaceful Slumber wants a king properly "
                    "housed to say it over."
                )
                return False
        return True

    def apply_effects(self):
        loc = self.player.location
        if self.which == "balm":
            healed = self.player.heal_wound()
            self.parser.ok(
                "You say the Prayer of Balm, and the chamber says it back "
                "from every direction at once, a round of carved voices "
                "closing over you like warm water. The "
                f"{healed.name.lower()} troubles you no more."
            )
        elif self.which == "wrath":
            horror = self.game.characters["fungal horror"]
            vigor = int(horror.get_property("vigor") or 0) - 1
            if vigor <= 0:
                horror.set_property("vigor", 0)
                # The engine's KO contract: the horror_struck trigger converts
                # this to the death it really is at the end of the round.
                horror.set_property("is_unconscious", True)
                self.parser.ok(
                    "You say the Prayer of Wrath and the whole chamber says "
                    "it with you -- a word with an edge on it, kept a "
                    "thousand years for exactly this. It goes through the "
                    "Fungal Horror like heat through frost: the coil lets go "
                    "of everything it holds, all at once."
                )
            else:
                horror.set_property("vigor", vigor)
                self.parser.ok(
                    "You say the Prayer of Wrath and the chamber says it "
                    "with you, a word with an edge on it. Ropes of fungus "
                    "char and drop away where it lands; the Fungal Horror "
                    "is smaller than it was."
                )
        elif self.which == "slumber":
            coffin = loc.items["coffin"]
            coffin.examine_text = (
                "The glass sphere hangs whole at the chamber's heart. Past "
                "the clearing cloud, Nassak An-Rah lies among his "
                "wrappings, and his face -- you would swear it -- has "
                "untightened: the look of a man dreaming something kind, "
                "four thousand years into a good night's sleep."
            )
            self.parser.ok(
                "You say the Prayer of Peaceful Slumber, and the chamber "
                "says it back so softly it is almost a hum. Through the "
                "clouded glass the Autarch's face lets go of some ancient "
                "argument; what settles over it is beatific, the rest he "
                "built this whole blue mountain hoping for. The prayers on "
                "the walls seem, briefly, less like grief."
            )
        else:  # mending
            coffin = loc.items["coffin"]
            coffin.set_property("pried", False)
            coffin.set_property("is_closed", True)
            coffin.description = "the Autarch's anti-entropy coffin, made whole again"
            coffin.examine_text = (
                "The glass sphere hangs whole at the chamber's heart again, "
                "its equator seamless -- the shards remembered their places "
                "and the places closed. The keeping is over; it is a "
                "reliquary now, clouded and quiet."
            )
            dead = loc.get_property("horror_dead")
            desc = (
                "A spherical chamber carved over every inch with funeral "
                "prayers, and nothing in it obeys the ground. The coffin "
                "hangs whole again at the dead centre, seam sealed, glass "
                "clouded and still."
            )
            if "Autarch's bones" in loc.items:
                desc += (
                    " The Autarch's bones drift around it in slow orbits, "
                    "gold wire glinting at the joints."
                )
            if "drift of ash" in loc.items:
                desc += " The ash of the Horror hangs in the air like a held breath."
            if not dead:
                desc += (
                    " The light in the chamber is the Fungal Horror itself, "
                    "coiled and moving."
                )
            loc.description = desc
            loc.dim_description = (
                "A spherical chamber, weightless and quiet. A whole dark "
                "shape hangs at the centre; pale shapes drift around it in "
                "the half-dark."
            )
            self.parser.ok(
                "You say the Prayer of Mending, and the chamber takes it up "
                "in a thousand carved voices. The orbiting glass remembers "
                "its places: shard streams home to shard along old "
                "symmetries, seams closing like water, until the coffin "
                "hangs whole at the heart of the chamber."
            )
        self.prayers.set_property(self.which + "_spent", True)
        self.prayers.set_property("read_text", _prayers_text(self.prayers))


class Butcher(actions.Action):
    """BUTCHER ZOXEN (CCB): with a blade in hand, the dead draught-beasts at
    the wreck become trail food -- two cuts before the sand claims the rest.
    Zox meat is EDIBLE, which makes it lunch, jackal tribute... and scent."""

    ACTION_NAME = "butcher"
    ACTION_DESCRIPTION = "Butcher a dead animal for meat (needs a blade)"
    ACTION_ALIASES = [
        "butcher zoxen",
        "butcher the zoxen",
        "butcher zox",
        "carve zoxen",
        "carve the zoxen",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def _zoxen(self):
        loc = self.player.location
        return loc.items.get("zoxen") if loc else None

    def check_preconditions(self) -> bool:
        zoxen = self._zoxen()
        if zoxen is None:
            self.parser.fail("There is nothing here to butcher.")
            return False
        if not any(
            "blade" in n or "dagger" in n or it.get_property("edged")
            for n, it in self.player.carried_items().items()
        ):
            self.parser.fail(
                "Butchery wants an edge. Your hands alone won't part zox hide."
            )
            return False
        if int(zoxen.get_property("butchered") or 0) >= 2:
            self.parser.fail(
                "Nothing left on them worth the knife; the sand has the rest."
            )
            return False
        return True

    def apply_effects(self):
        zoxen = self._zoxen()
        cut = int(zoxen.get_property("butchered") or 0) + 1
        zoxen.set_property("butchered", cut)
        meat = things.Item(
            "zox haunch" if cut == 1 else "lean zox haunch",
            "a briny haunch of zox meat",
            "A dense, briny haunch, dark as jerky already -- zoxen are half "
            "salt by weight. It will keep. In these halls, meat has "
            "listeners.",
        )
        meat.set_property(Property.EDIBLE, True)
        meat.set_property("smells_edible", True)  # the pack's nose (jackal scent)
        meat.set_property(
            Property.TASTE,
            "of iron and brine -- zoxen are half salt by weight. Food, "
            "honestly, and better bait: you are not the hungriest thing "
            "down here.",
        )
        meat.add_alias("meat")
        meat.add_alias("zox meat")
        meat.add_alias("haunch")
        self.player.location.add_item(meat)
        self.parser.ok(
            "You open the nearer zox along the flank the sand hasn't "
            "claimed and carve loose a haunch. Road-butchery: quick, "
            "ungentle, honest."
            if cut == 1
            else "You take a second haunch, leaner than the first. The road "
            "will have what's left by morning."
        )


class TossCentipede(actions.Action):
    """KICK or THROW the glass centipede off the Summit (CCB): it falls the
    height of the tomb and shatters on the stones at the base, leaving its
    remains there. The verb matters -- KICK uses a boot; THROW means picking a
    venomous glass centipede up with your hands, and the hands pay for it."""

    ACTION_NAME = "kick centipede"
    ACTION_DESCRIPTION = "Kick (or throw) the glass centipede off the roof"
    ACTION_ALIASES = [
        "kick the centipede",
        "throw centipede",
        "throw the centipede",
        "toss centipede",
        "toss the centipede",
        "kick centipede off",
        "throw centipede off",
        "kick centipede off the roof",
        "throw centipede off the roof",
        "kick glass centipede",
        "throw glass centipede",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.command = command.lower()

    def check_preconditions(self) -> bool:
        centipede = self.game.characters.get("glass centipede")
        if centipede is None or centipede.location is not self.player.location:
            self.parser.fail("The centipede isn't here to kick.")
            return False
        if centipede.get_property("is_dead"):
            self.parser.fail("It is past kicking.")
            return False
        if self.player.location.name != "The Summit":
            self.parser.fail(
                "There is no edge here worth the trouble -- it would only "
                "come back. The Summit has a drop that means it."
            )
            return False
        return True

    def apply_effects(self):
        centipede = self.game.characters["glass centipede"]
        by_hand = "throw" in self.command or "toss" in self.command
        if by_hand and not centipede.get_property("is_unconscious"):
            # Picking up four feet of live venomous glass: the hands pay.
            fatal = _wound_player(
                self.game,
                "Centipede Venom",
                1,
                (
                    "It hits you once across the palm as you heave it -- a "
                    "parting gift, going in cold.",
                ),
            )
            if fatal:
                _die(
                    self.game,
                    "The venom finishes its work at the very edge of the "
                    "sky. THE END.",
                )
                return
        verb = "heave" if by_hand else "kick"
        self.parser.ok(
            f"You {verb} the glass centipede over the Summit's edge. It "
            "falls the height of all three carved faces, turning, catching "
            "the red light -- and comes apart on the stones below with a "
            "sound like a dropped chandelier."
        )
        centipede.set_property("is_dead", True)
        if centipede.location is not None:
            centipede.location.remove_character(centipede)
        exterior = self.game.locations["Tomb Exterior"]
        remains = things.Item(
            "centipede remains",
            "the shattered remains of the glass centipede",
            "A spray of translucent chitin across the stones, glittering "
            "like a burst chandelier. The venom dries to nothing in the "
            "open air. One long splinter of carapace survived the fall "
            "whole -- edged like a surgeon's regret.",
        )
        remains.set_property("gettable", False)
        remains.add_alias("remains")
        remains.add_alias("shattered centipede")
        exterior.add_item(remains)
        # The fall that kills it forges a knife (CCB): one splinter of
        # carapace survives whole, and it takes an edge nothing metal does.
        shard = things.Item(
            "crystal shard",
            "a long shard of glass carapace, edged like a knife",
            "A hand-length splinter of the centipede's carapace, clear as "
            "water and edged on both sides. It cuts the light just holding "
            "it. A knife by any honest measure.",
        )
        shard.set_property("gettable", True)
        shard.set_property("is_weapon", True)
        shard.set_property(Property.WIELDABLE, True)
        shard.set_property("edged", True)  # butchery accepts it
        shard.add_alias("shard")
        shard.add_alias("carapace shard")
        shard.add_alias("glass knife")
        exterior.add_item(shard)


class CrystalSeal(blocks.Block):
    """The red-crystal seal on the stair between the Canopic hall and the
    Burial Sphere. A physical seal bars a stair from BOTH ends (CCB fix: it
    was one-directional), so one instance sits on the hall's "up" and another
    on the sphere's "down"; both key on the same ``seal_open`` property, set
    by the jar-placement trigger, so they clear together."""

    def __init__(self, canopic, from_above: bool = False):
        description = (
            "A seal of red crystal closes the stair below, cut and fitted to "
            "the treads so exactly that the joins read as one stone -- "
            "tombwright work, made to open for one thing only. The crystal "
            "hums at a pitch just under hearing, with the patience of a lock."
            if from_above
            else "A seal of red crystal bars the stair, cut and fitted to the "
            "treads so exactly that the joins read as one stone -- tombwright "
            "work, made to open for one thing only. Five beast-sigils are set "
            "in the arch above it; two of them are dark. The crystal hums at "
            "a pitch just under hearing, with the patience of a lock."
        )
        super().__init__("A seal of red crystal", description)
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


def _sphere_gloom_blurb(g, text):
    """Re-voice the Burial Sphere's half-light to match its current state."""
    sphere = g.locations["Burial Sphere of Nassak An-Rah"]
    for veil in sphere.veils:
        if isinstance(veil, perception.Gloom):
            veil._blurb = text


def _sphere_erupted(g):
    """The eruption's mark on the room (CCB: the description must keep up):
    the coffin is a drift of shards now, and the light is the Horror itself."""
    sphere = g.locations["Burial Sphere of Nassak An-Rah"]
    coffin = sphere.items.get("coffin")
    if coffin is not None:
        coffin.description = "the burst remains of the anti-entropy coffin"
        coffin.examine_text = (
            "A slow orbit of glass shards around the point where the coffin "
            "hung, edges catching the orange light. The field is dead; "
            "whatever it kept, the Horror keeps now."
        )
    sphere.description = (
        "A spherical chamber carved over every inch with funeral prayers, and "
        "nothing in it obeys the ground: glass shards from the burst coffin "
        "drift in slow orbits around the empty centre where it hung. The "
        "chamber's light is the Fungal Horror itself, orange and luminous. "
        "The prayers were carved to be read from every direction at once."
    )
    sphere.dim_description = (
        "A spherical chamber, weightless, lit by the Fungal Horror's own "
        "orange glow. Glass shards turn slowly through it."
    )
    _sphere_gloom_blurb(
        g,
        "A rotten half-light: the Fungal Horror's glow fills the chamber, "
        "and the carved prayers read as texture, not words.",
    )


def _sphere_aftermath(g, ash):
    """After the keeping ends -- the Horror dead in the sphere, or the coffin
    pried once nothing lives to mind it. The room becomes the fight's record
    (CCB): shattered glass, the Autarch's bones adrift, and (if it died here)
    the ash of the thing that held them."""
    sphere = g.locations["Burial Sphere of Nassak An-Rah"]
    coffin = sphere.items.get("coffin")
    if coffin is not None:
        coffin.description = "the shattered remains of the anti-entropy coffin"
        coffin.examine_text = (
            "A slow orbit of glass shards around empty air. The field is "
            "dead, and the keeping is over."
        )
    if "Autarch's bones" not in sphere.items:
        bones = _scenery(
            sphere,
            "Autarch's bones",
            "the bones of Nassak An-Rah, drifting free of their keeping",
            "The Autarch, at last: a king reduced to drifting articulation, "
            "gold wire at the joints, the skull tipped as if listening. "
            "Vaarn has taken everything else.",
        )
        bones.add_alias("bones")
        bones.add_alias("skeleton")
        bones.add_alias("autarch")
        bones.set_property("figure", "autarch-c")
    if ash and "drift of ash" not in sphere.items:
        ash_item = _scenery(
            sphere,
            "drift of ash",
            "the ash of the Fungal Horror, hanging weightless in the air",
            "Fine grey ash shot through with dull orange, still faintly warm, "
            "hanging where the Horror burned. Nothing in it mends.",
        )
        ash_item.add_alias("ash")
    sphere.description = (
        "A spherical chamber carved over every inch with funeral prayers, and "
        "nothing in it obeys the ground: glass shards from the shattered "
        "coffin turn in slow orbits, and the chamber is quiet in a way it has "
        "not been for a thousand years. The prayers were carved to be read "
        "from every direction at once."
    )
    sphere.dim_description = (
        "A spherical chamber, weightless and quiet. Glass and pale bone "
        "drift in the half-dark; the prayers are texture only."
    )
    _sphere_gloom_blurb(
        g,
        "A settling half-light: drifting shapes, and nothing in the chamber "
        "moves on its own.",
    )


def _sphere_quieted(g):
    """The root burned before the coffin was ever opened: the churn inside
    the glass goes still, and every description that leaned on it follows."""
    sphere = g.locations["Burial Sphere of Nassak An-Rah"]
    coffin = sphere.items.get("coffin")
    if coffin is not None and not coffin.get_property("pried"):
        coffin.examine_text = (
            "A clouded glass sphere at the chamber's heart, its field "
            "failing. Past the cloud, nothing moves any more; the slow "
            "churn has stopped. No handle or latch, but there is a seam "
            "at its equator, fine as a hair -- it could be pried, with the "
            "right tool."
        )
        sphere.description = (
            "A spherical chamber carved over every inch with funeral "
            "prayers, and nothing in it obeys the ground: dust and "
            "bone-chips drift in the still air, and your own weight forgot "
            "you at the threshold. In the dead centre floats the Autarch's "
            "coffin, a glass anti-entropy sphere, clouded and still now -- "
            "whatever moved inside it moves no more. The prayers were "
            "carved to be read from every direction at once."
        )
        sphere.dim_description = (
            "A spherical chamber, weightless, lit only by the fading orange "
            "glow of the coffin at its heart -- still now. Dust and "
            "bone-chips drift through it."
        )
        _sphere_gloom_blurb(
            g,
            "A rotten half-light, dimming: the coffin's glow no longer "
            "stirs, and the carved prayers read as texture, not words.",
        )


def _chimney_burned_out(g):
    """The burn is PERMANENT (CCB: the growth must not return): the room, its
    half-light, and the growth itself all read as aftermath from now on. The
    shaft keeps a faint glow -- the carved prayers far below -- so the gloom
    stays gloom, not blindness."""
    chimney = g.locations["The Fungal Chimney"]
    chimney.description = (
        "A vertical throat scoured black, bare rock and crumbling char from "
        "throat to crown, dropping from the summit toward a glow of carved "
        "prayers far below. The air is only air now, and cool."
    )
    chimney.dim_description = (
        "A black, bare shaft; char flakes away under your hands. The air is "
        "only air, and cool."
    )
    for veil in chimney.veils:
        if isinstance(veil, perception.Gloom):
            veil._blurb = (
                "The shaft is dark and quiet, rimmed faintly from below by "
                "the glow of carved prayers. Char, and cool air."
            )
    growth = chimney.items.get("orange growth")
    if growth is not None:
        chimney.remove_item(growth)
    if "charred growth" not in chimney.items:
        stub = _scenery(
            chimney,
            "charred growth",
            "the charred stubble of the burned growth",
            "Black wisps and crumbling char, packed in the seams where the "
            "growth was. Nothing left to burn, and nothing left breathing.",
        )
        stub.add_alias("growth")
        stub.add_alias("char")
        stub.add_alias("stubble")
        stub.perceptible_by(
            perception.Sense.TASTE,
            "Char. It tastes of a fire that has finished its work.",
        )


def _canopic_jar(name, description, examine_text, organ_name, organ_desc):
    """A sealed canopic jar: a closed container holding the Autarch's preserved
    organ. The organ is revealed only when the jar is OPENED (examining the sealed
    jar tells you nothing of what's inside). Jar and organ are both gettable --
    and the organ is edible, God help you, or feedable to things that eat."""
    jar = things.Item(name, description, examine_text).make_container()
    jar.set_property("is_closed", True)
    fig = {
        "mantis jar": "jar-mantis",
        "jackal jar": "jar-jackal",
        "falcon jar": "jar-falcon",
    }.get(name)
    if fig:
        jar.set_property("figure", fig)
    organ = things.Item(organ_name, organ_desc, organ_desc)
    organ.set_property("gettable", True)
    organ.set_property(Property.EDIBLE, True)
    # (Deliberately NOT smells_edible: the win route carries the cured
    # intestines openly, and making loose organs draw the pack wrecks the
    # pacifist path. If we ever want that, the route must first learn to
    # seal them back in their jar.)
    organ.set_property(
        Property.TASTE,
        "of four thousand years of preservative, and beneath that, of exactly "
        "what it is.",
    )
    organ.set_property("is_organ", True)  # the grave-sick trigger keys on this
    jar.add_item(organ)
    return jar


def build_game(seed=None):
    """Build the Tomb. With *seed*, the module RNG is seeded first, making the
    whole game deterministic -- (seed, game.journal) is then a complete save
    file, restored by ``build_game(seed).replay(journal)`` (the iOS app design,
    docs/design/ios-tomb-app.md §2). The seed is kept on ``game.rng_seed``."""
    if seed is not None:
        _RNG.seed(seed)
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
    # The crates are the OPEN rehearsal now (CCB) -- lashed tight until opened.
    crates.set_property("is_closed", True)
    crates.add_command_hint("open crates")
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
            _good.set_property(
                Property.TASTE,
                "of honey and sun under the road-dust. Proper trail food -- "
                "and anything in these halls with a nose will know you "
                "carry it.",
            )
        if "saffron" in _name:
            _good.set_property(
                Property.TASTE,
                "of bitter gold. A spice worth more than the wagon that "
                "hauled it -- seasoning, not supper.",
            )
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
        "The hand is neat. '...ninth day. Camped in the lee "
        "of the tomb the road-folk call the Three Mouths. Of it, Gnomon "
        "tells three things: that the boy's mouth is lightless within, and "
        "what roosts there hates a lamp worse than a shout; that the halls "
        "remember every footfall; and that no one, drunk or paid, will "
        "speak of the old man's mouth, which weeps orange. Rumor -- but the "
        "road teaches a certain respect for rumor. Tomorrow, Gnomon.' The "
        "entry is the last.",
    )
    ledger.set_property("gettable", True)  # take it along; it reads anywhere
    ledger.add_command_hint("read ledger")

    # (CCB: no separate pack -- everything the merchant carried is ON the
    # merchant, found the way the tokens are: by searching the dead. The
    # corpse-searching habit is rehearsed harder for it.)
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
    waterskin.set_property(Property.IS_HIDDEN, True)
    merchant.add_item(waterskin)

    # The TEAMSTER is CRITCH (CCB's pick from the rolled slate; the chargen
    # slate lives in docs/design/teamster-candidates.md): a golden new-hyena
    # of Vaarn's mask-wearing newbeasts -- except Critch declines. Won't
    # wear clothes, either; the brass pin rides a cord. The RANDOM chargen
    # survives as the EXAMINE SELF easter egg (vaarn_selves.py).
    teamster = things.Character(
        "Critch",
        "a golden new-hyena teamster",
        "I am Critch. I drove the wagon; now there is no wagon.",
    )
    teamster.examine_text = (
        "A golden-coated new-hyena, upright, unhurt, and bare of any stitch "
        "-- newbeasts dress to reassure, and Critch has declined. A carved "
        "mask in imitation of a human face, cracked clean across the smile, "
        "hangs at her neck on a cord beside a brass pin that reads CRITCH. "
        "She laughs, softly and steadily, at nothing you can see; with "
        "new-hyenas it is a manner of breathing, not an opinion."
    )

    def _teamster_talk(g):
        teamster.set_property("has_spoken", True)
        return (
            '"They came at moonset, laughing," Critch says, and laughs '
            'herself, without pleasure. "I ran, and the merchant could not, '
            "and that is the whole story. The Cacklemaw make no secret of "
            'their coming." She looks north, to the faces in the azure '
            'stone. "Take what he no longer needs -- better you than the '
            "sand. He carried water, three rations of it, and a glowstone; "
            "search him, he is past minding. The hold is yours too, "
            "whatever you can carry. But mind the tomb, scavenger. The "
            "caravans give its mouths a wide berth, and a caravan is seldom "
            'wrong twice." She settles her pack straps as she speaks, the '
            "way people do who have already decided to be elsewhere."
        )

    teamster.talk_text = _teamster_talk
    teamster.add_alias("teamster")
    teamster.add_alias("new-hyena")
    teamster.add_alias("hyena")
    wreck.add_character(teamster)

    # --- The eight locations -------------------------------------------------
    exterior = things.Location(
        "Tomb Exterior",
        "A thirty-foot slab of azure stone rises from the phthalo sands, webbed "
        "over every seam with creeping orange fungus. Three faces are carved in "
        "it: westward, the dead Autarch as a young boy; eastward, a helmed "
        "warrior; far up, an old man turned to the sky, orange tendrils weeping "
        "from his open mouth. Each mouth is a door. Wind and sand have been "
        "scoring these faces for ages, and yet they remain intact somehow.",
    )
    # The approach (card 17-C): a title plate above the first arrival's
    # description (the Go hook) -- and EXAMINE TOMB, whichever comes first.
    exterior.set_property("figure", "ext1c")
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
        "A blue slab of stone, thirty feet high, carved as three likenesses "
        "of Nassak An-Rah: a boy on the western face, a helmed warrior on "
        "the eastern, and at the summit an old man with his face to the sky. "
        "The two lower mouths gape as doorways. From the elder's mouth -- a "
        "chimney -- bright orange tendrils and fungal vines sprout, webbing "
        "down over the stone, shifting drowsily in the red light of the sun.",
    ).set_property("figure", "ext1c")
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
    ceiling.set_property("figure", "bats-c")  # RESIDENTS (THOUSANDS)
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
        _lattice_look,  # a different facet each look (CCB)
    )
    lattice.add_alias("lattice")
    lattice.add_alias("crystals")
    # BREAKABLE (CCB): smashing it yields a MEMORY SHARD -- and an archivist's
    # undying wrath (the trigger below the jackal block).
    lattice.set_property("is_breakable", True)
    lattice.set_property(
        "break_text",
        "The bank gives with a sound like a struck bell-field: facet after "
        "facet cascades dark, a thousand remembered days going out at once. "
        "A hand-sized shard skitters to your feet, one memory still alive "
        "inside it.",
    )
    # The shard's one surviving memory is drawn at BREAK time (inside the
    # trigger), not at build: a build-time draw would shift the RNG stream
    # for every game, seeded or not.
    memory_shard = things.Item(
        "memory shard",
        "a shard of memory-crystal, one facet still lit",
        "A splinter of lazulite, warm-edged where it broke.",
    )
    memory_shard.add_alias("shard")
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
    hound_pile.set_property("figure", "hound")
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
    _CYLINDER_NAMES = (
        "cerulean cylinder",
        "amber cylinder",
        "viridian cylinder",
        "orange cylinder",
    )

    def _standing_cylinders():
        return [n.split()[0] for n in _CYLINDER_NAMES if n in warriors.items]

    def _colour_list(colours):
        if len(colours) <= 1:
            return colours[0] if colours else ""
        if len(colours) == 2:
            return f"{colours[0]} and {colours[1]}"
        return ", ".join(colours[:-1]) + f", and {colours[-1]}"

    def _cylinders_examine(g=None):
        standing = _standing_cylinders()
        if len(standing) == 4:
            return (
                "Four guard-mummies at an attention no order will ever "
                "relieve, each sealed under its own gel -- cerulean, amber, "
                "viridian, orange -- and each armed as in life. Whatever "
                "they carried went under the glass with them. The plexiglas "
                "is crazed to milk at the corners; a firm blow would finish "
                "what the centuries started."
            )
        if not standing:
            return (
                "All four cylinders lie burst. The guard-mummies sprawl "
                "where their gel let them down, at attention from the waist "
                "up, relieved of everything but posture."
            )
        kept = _colour_list(standing)
        return (
            f"Only the {kept} still {'stands' if len(standing) == 1 else 'stand'} "
            "sealed, its dead still armed as in life. The broken ones gape, "
            "their guard-mummies slumped in drying gel, glass crazed to milk "
            "where the blows landed."
        )

    _scenery(
        warriors,
        "cylinders",
        "four plexiglas burial cylinders",
        _cylinders_examine,
    ).set_property(
        "figure",
        lambda g: "cylinders-b" if len(_standing_cylinders()) == 4 else "cylinders",
    )
    # ...and the same card as a title plate on ARRIVAL, light permitting
    # (the hall is pitch dark; a blind arrival keeps the card unburned).
    warriors.set_property(
        "figure",
        lambda g: (
            ("cylinders-b" if len(_standing_cylinders()) == 4 else "cylinders")
            if perception.sight_for(g.player, warriors)[0] >= perception.Sight.CLEAR
            else None
        ),
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
    # Each organ keeps its own taste (CCB) -- the shared preservative note
    # in _canopic_jar is only the fallback.
    baboon_jar.contents["lungs"].set_property(
        Property.TASTE,
        "of dust and cedar; they crackle faintly, like old paper. Whatever "
        "they last breathed is four thousand years gone.",
    )
    human_jar.contents["liver"].set_property(
        Property.TASTE,
        "of bitter iron and resin -- the organ that kept the Autarch's "
        "score. It is, God help you, edible.",
    )
    mantis_jar.contents["fungal eyes"].set_property(
        Property.TASTE,
        "of orange rot and salt, and your tongue itches where it touched. "
        "You would swear, briefly, that the eyes taste you back.",
    )
    for j in (baboon_jar, human_jar, mantis_jar):
        j.set_property("gettable", True)
        canopic.add_item(j)

    # The two empty plinths are surfaces you set the missing jars ON; each is
    # carved with the head that belongs there.
    falcon_plinth = things.Item(
        "falcon plinth",
        "an empty plinth carved with a falcon",
        lambda g=None: (
            "A plinth carved as a falcon, lit crimson and empty. The "
            "carving's talons are cupped, curled around the shape of "
            "something it has lost."
            if not falcon_plinth.contents
            else (
                "A plinth carved as a falcon, the crimson gone white. The "
                "talons cup their jar again, and the carving reads as "
                "finished."
                if "falcon jar" in falcon_plinth.contents
                else "A plinth carved as a falcon, still burning crimson. "
                "The talons hold the jar awkwardly, like a word in the "
                "wrong mouth."
            )
        ),
    ).make_surface(capacity=1)
    falcon_plinth.set_property("gettable", False)
    falcon_plinth.set_property("figure", "canopic-c")
    jackal_plinth = things.Item(
        "jackal plinth",
        "an empty plinth carved with a jackal",
        lambda g=None: (
            "A plinth carved as a jackal, lit crimson and empty. The stone "
            "jaws are parted, holding their grip on an absence."
            if not jackal_plinth.contents
            else (
                "A plinth carved as a jackal, the crimson gone white. The "
                "stone jaws close true around their jar, grip answered at "
                "last."
                if "jackal jar" in jackal_plinth.contents
                else "A plinth carved as a jackal, still burning crimson. "
                "The stone jaws hold the jar without conviction; this is "
                "not what they were parted for."
            )
        ),
    ).make_surface(capacity=1)
    jackal_plinth.set_property("gettable", False)
    jackal_plinth.set_property("figure", "canopic-c")
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
    manifold_box.set_property("figure", "tesseract")
    coffin = _scenery(
        sphere,
        "coffin",
        "the Autarch's anti-entropy coffin",
        "A clouded glass sphere at the chamber's heart, its field failing, its "
        "interior a slow orange churn. Past the cloud, shapes drift and turn "
        "like fish under ice: bone, and things that were buried to be kept. No "
        "handle or latch, but there is a seam at its equator, fine as a hair "
        "-- it could be pried, with the right tool.",
    )
    prayers = _scenery(
        sphere,
        "prayers",
        "the funeral prayers, carved over every inch of the chamber",
        "Carved to be read from every direction at once. READ them to study "
        "the lines; three of them are rung to be SAID aloud.",
    )
    prayers.add_alias("prayer")
    prayers.add_alias("funeral prayers")
    prayers.add_alias("carvings")
    prayers.add_alias("carved prayers")
    prayers.set_property("read_text", _prayers_text(prayers))
    prayers.add_command_hint("read prayers")

    coffin.make_container()
    coffin.set_property("is_closed", True)
    coffin.set_property(
        "figure", "sphere-b"
    )  # PryCoffin (boots-gated) is the only way in
    # ...and as a title plate on ARRIVAL (the chamber is gloom: a dark entry
    # keeps the card). After the mend, arrivals show the Autarch at rest.
    sphere.set_property(
        "figure",
        lambda g: (
            ("autarch" if coffin.get_property("fixed") else "sphere-b")
            if perception.sight_for(g.player, sphere)[0] >= perception.Sight.CLEAR
            else None
        ),
    )
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
    corpse.set_property("figure", "mystic-b")
    # ...and the same card as a title plate on first ARRIVING at the Summit
    # (open sky at sunset: no sight gate needed).
    summit.set_property("figure", "mystic-b")
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
    fungus.set_property("figure", "fungus")
    fungus.set_property("gettable", True)
    fungus.set_property(Property.EDIBLE, True)
    # A LICK is a microdose (CCB): the taste rehearses the fungus's whole
    # function -- and points, gently, at giving it away rather than eating it.
    fungus.perceptible_by(
        perception.Sense.TASTE,
        "A crumb on the tongue, no more -- and warmth spreads outward from "
        "it, and for one held breath everything in Vaarn seems to mean "
        "well: the tomb, the dark, even you. Then it passes, and you miss "
        "it. A whole dose would make fast friends of whoever ate it -- it "
        "feels meant for someone lonelier than you.",
    )
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
    falcon_jar.contents["intestines"].set_property(
        Property.TASTE,
        "of offal -- cured, ancient, and unmistakably what it is. Food, "
        "technically. Tribute, ideally: you are not the hungriest thing "
        "in these halls.",
    )
    jackal_jar.contents["brain"].set_property(
        Property.TASTE,
        "of resin and long memory. Somewhere behind your teeth, for one "
        "beat, a thought that is not yours: blue sand, and a mother's "
        "voice. Swallowing more would be somebody's biography.",
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
    spawn_guts.set_property("figure", "guts-a")
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
    spawn_brain.set_property("figure", "spawn-a")
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
    for _a in ("jackals", "jackal", "pack", "pack of jackals", "pthalo-jackals"):
        jackal_pack.add_alias(_a)
    jackal_pack.set_property("figure", "jackal")
    # A PACK does not drop to one swing (the vigor system, CCB): three blows
    # thin it to nothing.
    jackal_pack.set_property("vigor", 3)
    jackal_pack.set_property(
        "struck_text",
        "The blow lands; the pack gives ground snarling, thinner by one.",
    )
    den.add_character(jackal_pack)

    # The Fungal Horror -- the boss (design doc §17.3). It lives coiled in the
    # coffin (narrative) until an alive-pry brings it out as a real Character.
    horror = things.Character(
        "fungal horror",
        "the Fungal Horror, a mass of animate orange fungus coiled around "
        "the Autarch's bones",
        "We keep him. We are keeping him still.",
    )
    horror.examine_text = (
        "A single muscle of orange fungus the size of a river-snake, coiled "
        "around what is left of Nassak An-Rah and moving his dead limbs like "
        "its own. Where you cut it, it remembers; where it burns, it does not."
    )
    for _a in ("horror", "the horror", "mass", "fungal mass"):
        horror.add_alias(_a)
    horror.set_property("no_catch", True)  # a coil has no hands
    # Its card follows its state: the coil in the coffin, or the bust ablaze.
    horror.set_property(
        "figure",
        lambda g: (
            "autarch-e"
            if g.characters["fungal horror"].get_property("ablaze")
            else "sphere-b"
        ),
    )
    horror.set_property("vigor", 5)
    horror.set_property(
        "struck_text",
        "The blade opens a rent in the orange mass; it seethes, and does " "not fall.",
    )
    # The engine prints ko_text on the FINAL blow, just before the death
    # trigger converts the knockout into the end it really is.
    horror.set_property("ko_text", "The last rent does not close.")
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
    centipede.set_property("figure", "centipede")
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
    blade.set_property("figure", "blade")

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
        "a synthetic archivist in yellow monk's robes",
        "I am Silas, of the Seekers of Eyeless Wisdom. I read the dead.",
    )
    silas.examine_text = (
        "A gaunt synth in yellow monk's robes, plain-woven and dust-hemmed, "
        "fingertips tipped with cranial bores, drawing memory from the "
        "lattice in slow bright threads. Patient, courteous, elsewhere. Now "
        "and then his lips move -- circular glyphs, no sound."
    )
    silas.set_property("figure", "silas")
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
        g.show_figure("silas")  # his card, if the arrival or a look hasn't
        g.award("silas", 5, "[+5 -- the archivist's acquaintance]")
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
    # ASK SILAS ABOUT ... (CCB): the archivist answers on his subjects.
    # Several keywords share an answer; parser.match_topic picks by keyword
    # (longest match wins), the LLM parser by meaning.
    _about_lattice = (
        "Silas's fingertips still. \"The lattice is a memory-crystal -- "
        "New-Pangean work, grown rather than cut. The tombwrights fed it "
        "the Autarch's chosen memories as they embalmed him, and it holds "
        "them yet, set down in facets: a reader with the right fingertips "
        "can walk them like halls. Not his decrees -- crystal is too dear "
        "for decrees. What it keeps is what he could not buy or take by "
        "conquest: his "
        "mother's hand on the back of his neck. A bath, full immersion, "
        "water to the chin -- a luxury this world no longer imagines. The "
        'first time he drew blood, and what it taught him." He turns back '
        'to the light. "Look into it yourself, if you are gentle. It shows '
        'what it chooses."'
    )
    _about_himself = (
        '"Why am I here?" Silas considers the question as if reading it. '
        '"I am of the Seekers of Eyeless Wisdom -- a mendicant order; the '
        "robes are the rule, yellow so the dust of the road shows on them. "
        "We read the dead where they kept their own records. When I have "
        "the Autarch whole -- every remembered day in its order -- my "
        "order will speak him aloud once, in a hall built for the purpose, "
        "and then let him go. A man is not done dying until he is done "
        'being remembered. I am here to finish Nassak An-Rah properly."'
    )
    silas.talk_topics = {
        "memories": _about_lattice,
        "memory": _about_lattice,
        "lattice": _about_lattice,
        "crystal": _about_lattice,
        "himself": _about_himself,
        "why he is here": _about_himself,
        "seekers": _about_himself,
        "his order": _about_himself,
        "robes": _about_himself,
        "autarch": (
            '"Nassak An-Rah. A nobleman of the Fallen Autarchy, buried in '
            "state above us -- and not, I should say, entirely at rest. His "
            "appetites and his thoughts were jarred separately, as the rite "
            "requires, and both have got up. I do not fight them; I read. "
            'But keep your voice low and your blade closer."'
        ),
        "lantern": (
            '"The lantern burns ulfire -- the ninth colour. Its light passes '
            "through solid things; only lead stops it. An archivist's tool: "
            'one reads a sealed page by it. It is not for sale." A pause. '
            '"Though I am, in one matter, corruptible. The order forbids us '
            'nothing that grows."'
        ),
    }
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
    # A synth takes some breaking (vigor 2).
    silas.set_property("vigor", 2)
    silas.set_property(
        "struck_text",
        "Silas takes the blow with synthetic patience; something inside him "
        "ticks, recalibrates, and holds.",
    )
    memory.add_character(silas)

    # The crystal seal bars the stair up from the Canopic hall until both jars are
    # placed (registered before the game so the parser picks up the block).
    # A physical seal bars the stair from BOTH ends (CCB fix): whoever drops
    # into the sphere from the chimney meets the same crystal from above, and
    # the jar puzzle clears both at once.
    canopic.add_block("up", CrystalSeal(canopic))
    sphere.add_block("down", CrystalSeal(canopic, from_above=True))

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
    glowstone.set_property(
        Property.TASTE,
        "like a nine-volt battery: a flat electric fizz that finds every "
        "filling you own. Not food. Possibly not polite.",
    )
    glowstone.add_alias(
        "stone"
    )  # no "lantern" alias: the Ulfire Lantern owns that word
    glowstone.set_property("figure", "glowstone")
    glowstone.add_command_hint("light glowstone")
    glowstone.add_command_hint("douse glowstone")
    glowstone.set_property(Property.IS_HIDDEN, True)
    merchant.add_item(glowstone)

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
    # Weightless or not, hauling yourself up into the chimney's throat is a
    # climb (CCB) -- the way DOWN is a drift, and stays free.
    sphere.set_property("climb_exits", {"up"})

    game = TombGame(
        wreck,
        player,
        characters=[
            silas,
            spawn_guts,
            spawn_brain,
            teamster,
            jackal_pack,
            horror,
            centipede,
        ],
        custom_actions=[
            Sneak,
            Burn,
            ExamineSelf,
            FixCoffin,
            PryCoffin,
            Remember,
            SayPrayer,
            TieSilk,
            Refill,
            TossCentipede,
            Butcher,
        ],
    )
    game.max_score = 145
    game.rng_seed = seed  # the save blob records this alongside game.journal
    # Turn on the feel / listen / smell probes: the Hall of Youth's dark clue
    # (the unseen bats overhead) is meant to be heard and felt, not just seen.
    game.enable_senses()
    # Register purity by default: no command-hint training wheels in the prose
    # (design doc §16 -- danger telegraphs through fiction). Flip give_hints on
    # for a hand-held demo/classroom run; the wreck's tutorial items carry
    # their hints ("open pack", "light glowstone", "read ledger") for that mode.
    game.give_hints = False

    # --- The hint booklet (InvisiClues style; engine hints.py) --------------
    # Question-based, met-before-listed, one level deeper per ask: level 1
    # restates what the fiction already said, level 2 names the thing, level
    # 3 is walkthrough-grade. Solved puzzles leave the menu; HINT costs no
    # turn but is journaled, and the final score owns up to hints taken.
    for _h in (
        Hint(
            "light",
            "How am I supposed to see anything in there?",
            [
                "The caravan did not die carrying nothing.",
                "SEARCH the dead merchant. Traders of the Tomblands carry "
                "their own light.",
                "TAKE GLOWSTONE, then LIGHT GLOWSTONE -- and DOUSE it when "
                "the dark is the safer company.",
            ],
            resolved=lambda g: g.scored("first_light"),
        ),
        Hint(
            "bats",
            "What do I do about the bats?",
            [
                "They hate your light. They love something else more.",
                "The caravan's crates hold what a starving colony wants far "
                "more than your scalp.",
                "THROW DATES (or drop the crate). In the Hall of Youth the "
                "colony feasts -- five quiet rounds. Carried to another "
                "room, it follows and ROOSTS there for good. Under open "
                "sky, it wheels and scatters.",
            ],
            available=lambda g: youth.has_been_visited,
            resolved=lambda g: bool(youth.get_property("bats_flown")),
        ),
        Hint(
            "jackals",
            "How do I get past the pthalo-jackals?",
            [
                "They are scavengers, not sentries. Scavengers can be paid.",
                "Think about what a jackal wants, and what this expedition "
                "is carrying (or could butcher) that smells like it.",
                "Carry the CRATE OF DATES (or BUTCHER ZOXEN at the wreck for "
                "haunches) and let the pack take its tribute; a real toll "
                "buys a long peace. Steel works too, three blows' worth.",
            ],
            available=lambda g: youth.has_been_visited,
            resolved=lambda g: jackal_pack.get_property("is_dead")
            or any((h.get_property(f"_jk:{h.name}") or 0) < 0 for h in _halls),
        ),
        Hint(
            "spawn",
            "The things in the jars keep finding me.",
            [
                "They have no eyes. Ask yourself what they are using instead.",
                "Walking SOUNDS like something in these halls -- the arrival "
                "line says so. There is a quieter way to move.",
                "SNEAK <direction> to move silently. If you must fight them, "
                "make your racket in the Canopic hall, where the mantis jar "
                "sings them to you on your own terms.",
            ],
            available=lambda g: youth.has_been_visited,
            resolved=lambda g: spawn_guts.get_property("is_dead")
            and spawn_brain.get_property("is_dead"),
        ),
        Hint(
            "seal",
            "How do I open the crimson seal on the stair?",
            [
                "Five plinths, three jars. The room is telling you its own "
                "inventory.",
                "The falcon and jackal jars were carried off. One walks the "
                "halls on a spawn's shoulders; one waits among the dead "
                "guards.",
                "Take the FALCON JAR from the fallen spawn and the JACKAL "
                "JAR from the Hall of Warriors, then PUT each ON its "
                "matching plinth. The seal answers the jars.",
            ],
            available=lambda g: canopic.has_been_visited,
            resolved=lambda g: bool(canopic.get_property("seal_open")),
        ),
        Hint(
            "cylinders",
            "What is in the burial cylinders?",
            [
                "Kit outlasts its owners. These owners were guards.",
                "BREAK them -- but read the colors first: one holds a mask, "
                "one holds boots, and the orange one holds a bloom you do "
                "not want in your lungs.",
                "BREAK AMBER CYLINDER for the respirator (WEAR IT FIRST), "
                "then BREAK ORANGE CYLINDER for the plasma-igniter, and "
                "BREAK VIRIDIAN CYLINDER for the magnetic boots.",
            ],
            available=lambda g: warriors.has_been_visited,
            resolved=lambda g: all(
                c not in warriors.items
                for c in ("amber cylinder", "viridian cylinder", "orange cylinder")
            ),
        ),
        Hint(
            "spores",
            "The orange spores are searing my lungs.",
            [
                "The fungus is the air itself. You need to change one of " "the two.",
                "An Autarchy respirator was buried with the guards -- WORN, "
                "not held. Or remember that everything the gel has touched "
                "is ready to burn.",
                "WEAR RESPIRATOR (amber cylinder, Hall of Warriors) -- or "
                "douse the growth with gel and BURN GROWTH to clear the "
                "chimney for good. Standing outside it first is wise.",
            ],
            available=lambda g: chimney.has_been_visited
            or bool(warriors.get_property("spores_vented")),
            resolved=lambda g: bool(chimney.get_property("burned"))
            or "respirator" in game.player.worn,
        ),
        Hint(
            "coffin",
            "How do I open the Autarch's coffin?",
            [
                "Nothing in the sphere holds you down. Prying wants bracing, "
                "and the seam wants an edge.",
                "A guard was buried with boots that grip, and the merchant "
                "carried silk strong enough to lash a coffin still.",
                "WEAR MAGNETIC BOOTS (or TIE SILK TO COFFIN), then PRY "
                "COFFIN with the prismatic blade in hand. The blade will "
                "not survive the coffin -- and what sleeps inside will "
                "mind the knock.",
            ],
            available=lambda g: sphere.has_been_visited,
            resolved=lambda g: bool(coffin.get_property("pried"))
            or bool(sphere.get_property("horror_dead")),
        ),
        Hint(
            "horror",
            "How do I kill the Fungal Horror?",
            [
                "Watch it for one round doing nothing. What you see it do "
                "is the whole problem.",
                "Steel is a treadmill: it knits faster than you cut. "
                "Everything the embalming gel touches is ready to burn -- "
                "and the chamber itself was carved to take your side.",
                "THROW GEL AT HORROR, then BURN HORROR with the igniter or "
                "glowstone spark -- ablaze, it cannot mend, so keep "
                "cutting. The carved PRAYER OF WRATH is a free blow, and "
                "the PRAYER OF BALM will close a wound mid-fight.",
            ],
            available=lambda g: horror.location is sphere,
            resolved=lambda g: bool(horror.get_property("is_dead")),
        ),
        Hint(
            "score",
            "What am I still missing?",
            [
                "The score pays for light, water, wisdom spent, both jars, "
                "the seal, the tomb's lesser hosts quelled, the Horror -- "
                "and leaving alive.",
                "READ LEDGER at the wreck; DRINK WATER on a wound; the "
                "lattice remembers a dead king's days; Silas rewards a "
                "civil TALK.",
                "The full 145: threshold 5, first light 5, water 5, a "
                "healed wound 5, the lattice memory 5, every remembered day "
                "in its order 5, Silas's acquaintance "
                "5, falcon jar 5, jackal jar 5, the dagger 5, the manifold "
                "box 5, the Friend's Fungus 5, the archivist made whole 5, "
                "each spawn quelled 5, the "
                "pack settled (paid or put down) 5, the seal 20, the Horror "
                "25, and out alive 20.",
            ],
            resolved=lambda g: g.score >= g.max_score,
        ),
    ):
        game.add_hint(_h)

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

    # THE WHOLE TOMB IS DARK (CCB): every interior hall wants a carried
    # light. The three ground halls have their own faint canonical glows
    # (the luminous tank, the crimson plinths, the glimmering lattice), so
    # they are GLOOM -- shape and exits show, contents don't, and the dim
    # description carries the room until a light does.
    memory.obscure(
        perception.Gloom(
            blurb="The lattice's glimmer is light the way frost is water: "
            "walls of faint constellations, and nothing else legible."
        )
    )
    # Silas at his reading (card 09): a title plate on ARRIVING in the Hall
    # of Memory -- but only when you can actually see him (the hall is gloom;
    # a dark arrival doesn't burn the card, and EXAMINE SILAS remains the
    # backstop cue once a light is raised).
    memory.set_property(
        "figure",
        lambda g: (
            "silas"
            if "Silas" in memory.characters
            and not g.characters["Silas"].get_property("is_dead")
            and perception.sight_for(g.player, memory)[0] >= perception.Sight.CLEAR
            else None
        ),
    )
    memory.dim_description = (
        "A hall lit only by the lattice itself -- drifts of pale glimmer "
        "crawling the walls, each point a day someone else lived. Between "
        "their constellations, the dark keeps its own counsel."
    )
    hounds.obscure(
        perception.Gloom(
            blurb="A wall of green-gold light: the tank glows like old honey "
            "held to a lamp, and everything before it is silhouette."
        )
    )
    hounds.dim_description = (
        "The hall is lit only by the tank -- a wall of green-gold, luminous "
        "and slow, ten hound-shapes hanging in it like thoughts. Everything "
        "on your side of the plexiglas is shadow and floor-grit."
    )
    canopic.obscure(
        perception.Gloom(
            blurb="Two points of crimson burn at knee height and light "
            "nothing but themselves. The stair climbs into black."
        )
    )
    canopic.dim_description = (
        "A pentagon of dressed stone, dark except where two empty plinths "
        "burn crimson from within -- light that reaches nothing, like coals "
        "in a cold room. Something in this room is listening; you can tell, "
        "the way one can."
    )

    youth.obscure(
        perception.Darkness(
            blurb="Dark as the inside of a sealed jar. The air is chill and smells "
            "of old guano; somewhere far above, leather rustles against leather, "
            "patient and vast. The road-folk's word for the boy's mouth is "
            "'lightless', and they mean it as advice."
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
            g.show_figure("bats-c")  # the residents, eyes opening
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
        danger=lambda g: not youth.get_property("bats_flown")
        and (youth.get_property("bats_feeding") or 0) <= 0
        and (
            perception.carries_light(g.player) or _player_was_loud_in(g, youth, _QUIET)
        ),
        warns=(
            "The rustle overhead deepens. Grit sifts down through your light; "
            "the whole vault has begun, gently, to move.",
        ),
        limit=2,  # one warning -- the bats' patience is short
        harm=_bat_maul,
    )

    # --- Getting rid of the bats (CCB): THROW THE DATES ----------------------
    # Fruit on the air empties the vault. Thrown in an interior room, the
    # colony streams there, eats, and ROOSTS -- sated and harmless, and the
    # Hall of Youth is only a room now. Thrown under open sky, they strip the
    # dates, circle the tomb for ten turns, and disperse for good. Either way
    # the dates are spent -- the same dates the jackals would take as tribute.
    _outdoors = (wreck, exterior, summit)

    def _dates_thrown(g):
        # Thrown OR set down: food on the floor is food on the floor. The
        # colony answers wherever the dates come to rest -- including one
        # room over, for a scavenger who throws them through a doorway.
        return not youth.get_property("bats_flown") and any(
            e.actor == g.player.name
            and e.action in ("throw", "drop")
            and "date" in (e.summary or "").lower()
            for e in g.events[g._round_event_start :]
        )

    def _bats_follow(g):
        here = next(
            (room for room in g.locations.values() if "crate of dates" in room.items),
            None,
        )
        if here is None:
            return  # still in hand (a failed throw); the colony stays
        dates = here.items["crate of dates"]
        if here is youth:
            # Fed at home (CCB): the colony falls on the dates and cares
            # about nothing else for five rounds -- a bought window to
            # cross the vault, light and all. Then the dates are gone,
            # and the ceiling resumes its opinions.
            here.remove_item(dates)
            youth.set_property("bats_feeding", 6)  # spawn round burns one
            g.parser.ok(
                "The ceiling DETACHES. The whole colony falls on the dates "
                "in a boiling carpet of wings, and for the moment nothing "
                "in this room cares about you at all."
            )
            return
        youth.set_property("bats_flown", True)
        here.remove_item(dates)  # stripped to the palm-fibre
        ceiling.examine_text = (
            "The vault overhead hangs bare, guano-scarred, and silent. "
            "Whatever roosted here has followed its stomach elsewhere."
        )
        ceiling.perceptible_by(
            perception.Sense.HEARING,
            "Silence overhead -- true silence, the first this room has "
            "held in centuries.",
        )
        if here in _outdoors:
            # 11: the trigger pass on the toss round itself burns one tick,
            # so the wheel turns ten full turns AFTER the dates land.
            here.set_property("_bat_wheel", 11)
            wheel = _scenery(
                here,
                "wheel of bats",
                "a wheel of bats, circling overhead",
                "Thousands of bats turn overhead in a slow black gyre, "
                "drunk on dates and daylight, unsure what to do with "
                "either.",
            )
            wheel.add_alias("bats")
            wheel.set_property("figure", "bats")
            g.parser.ok(
                "The mouths of the tomb EXHALE -- a river of leather "
                "pouring into the open air. The colony strips the dates in "
                "one boiling knot, and then rises, and circles, a slow "
                "black wheel over the tomb."
            )
        else:
            roost = _scenery(
                here,
                "roost of bats",
                "a fresh roost of bats, folded and sated",
                "The ceiling here seethes gently now: the colony, moved in "
                "and fed, packed wing to wing and fast asleep. They have "
                "no further opinions about your light.",
            )
            roost.add_alias("bats")
            roost.set_property("figure", "bats-c")
            g.parser.ok(
                "A sound like a tide through the halls -- and the colony "
                "arrives, a river of leather that breaks over the dates "
                "and strips them to the palm-fibre. Then, gorged, they "
                "climb the walls and fold themselves to sleep. The Hall "
                "of Youth is only a room now."
            )

    game.add_trigger("bats_follow_dates", _dates_thrown, _bats_follow)

    def _wheel_turning(g):
        loc = next(
            (r for r in _outdoors if (r.get_property("_bat_wheel") or 0) > 0),
            None,
        )
        return loc is not None

    def _wheel_tick(g):
        for room in _outdoors:
            n = room.get_property("_bat_wheel") or 0
            if n <= 0:
                continue
            n -= 1
            room.set_property("_bat_wheel", n)
            if n == 0:
                if "wheel of bats" in room.items:
                    room.remove_item(room.items["wheel of bats"])
                g.parser.ok(
                    "Overhead, the wheel of bats thins, breaks, and "
                    "scatters toward the horizon's molten line. The tomb "
                    "has one tenant fewer."
                    if g.player.location in _outdoors
                    else "Somewhere above the stone, a long dry rustle "
                    "fades to nothing."
                )

    game.add_trigger("bat_wheel", _wheel_turning, _wheel_tick, repeatable=True)

    def _feeding(g):
        return (youth.get_property("bats_feeding") or 0) > 0

    def _feeding_tick(g):
        n = (youth.get_property("bats_feeding") or 0) - 1
        youth.set_property("bats_feeding", n)
        if n == 0 and g.player.location is youth:
            g.parser.ok(
                "The last of the dates is gone. Gorged, the colony climbs "
                "back into the vault, wing over wing -- and resumes its "
                "opinion of light."
            )
        elif n == 0:
            g.parser.ok(
                "From the boy's mouth of the tomb, a long rustle: the "
                "feast below is over, and the vault refills."
            )

    game.add_trigger("bats_feeding", _feeding, _feeding_tick, repeatable=True)

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
            # A real tribute buys real peace: deep enough that even a
            # cylinder-looting spree won't burn back through it.
            h.set_property(f"_jk:{h.name}", -6)

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
                    # the card first, then the warning (CCB): the sway is
                    # what you SEE as it swings toward your noise -- forced,
                    # so a spent examine key cannot mute the beat
                    g.show_figure(
                        "guts-a" if spawn is spawn_guts else "spawn-a", force=True
                    )
                    g.parser.ok(warn_text)
                else:
                    # the close-up plays FIRST, then the blow lands (CCB);
                    # forced on the FIRST blow only (later blows do not spam)
                    g.show_figure(
                        "guts-b" if spawn is spawn_guts else "spawn-b",
                        force=(n == 2),
                    )
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
        "The spawn of guts swings toward your noise, arms rising from the "
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
        if g.player.location in (youth, exterior, memory, hounds):
            g.show_figure("bats-c")  # the card plays first, then the swarm
            g.parser.ok(
                "In the Hall of Youth, the swarm pours down onto the light where "
                "it lies, a screaming wheel around a still point."
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
        g.show_figure("jackal", force=True)  # a story beat: always plays
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
        # The mantis song is the tomb's dinner bell: every round the jar
        # sings, every ground hall's ledger climbs. Noise begets the song;
        # the song begets the pack.
        song_round = any(
            "insect song" in ((e.payload or {}).get("sound") or "")
            for e in g.events[g._round_event_start :]
        )
        for hall in _halls:
            key = f"_jk:{hall.name}"
            streak_key = f"_jkq:{hall.name}"
            n = hall.get_property(key) or 0
            if song_round and n >= 0:
                hall.set_property(streak_key, 0)  # the song IS noise
                n += 1
                hall.set_property(key, n)
                if n >= 4 and jackal_pack.location is den:
                    g.relocate(jackal_pack, hall)
                    jackal_pack.set_property("_stride", True)
                    g.show_figure(
                        "jackal", force=True
                    )  # the prowl, then the arithmetic
                    g.parser.ok(
                        "They come in low and unhurried, cerulean-coated, "
                        "filling the doorways -- the song called, and the "
                        "pack answers what it summons."
                        if here is hall
                        else "Somewhere below, a yipping rises to meet the "
                        "song, gathers, and goes quiet. Purposeful."
                    )
                    continue
            if here is not hall:
                # The trail cools toward calm from either side (suspicion
                # drains, post-feed grace wears off) -- but only after THREE
                # consecutive quiet rounds (CCB: the jackals were MIA in real
                # play; a -1 per quiet round cancelled almost every +1, so
                # only back-to-back crashes ever summoned them). Suspicion
                # outlasts a pause to read a ledger.
                streak = (hall.get_property(streak_key) or 0) + 1
                if streak >= 3 and n != 0:
                    hall.set_property(key, n - 1 if n > 0 else n + 1)
                    streak = 0
                hall.set_property(streak_key, streak)
                continue
            if jackal_pack.location is hall:
                _jackal_maul(g)  # unfed, unfled: they collect
                continue
            if _player_was_loud_in(g, hall, _QUIET):
                hall.set_property(streak_key, 0)
                # A crash carries: breaking things counts double on the ledger.
                crashed = any(
                    e.actor == g.player.name
                    and e.action == "break"
                    and (e.payload or {}).get("location") == hall.name
                    for e in g.events[g._round_event_start :]
                )
                n += 2 if crashed else 1
                hall.set_property(key, n)
                if n <= 0:
                    pass  # sated (or long-calmed): the noise only burns patience
                elif n <= 2:
                    g.parser.ok(
                        "Somewhere off in the halls, a yipping answers your "
                        "noise -- once, and then again, nearer."
                    )
                elif n == 3:
                    g.show_figure("jackal", force=True)
                    g.parser.ok(
                        "Yellow eyes ring the doorways, unhurried. "
                        "Pthalo-jackals: cautious, clever, and done being "
                        "cautious."
                    )
                elif n >= 4:
                    g.relocate(jackal_pack, hall)
                    jackal_pack.set_property("_stride", True)  # first beat: hang back
                    g.show_figure("jackal", force=True)  # the prowl, first
                    g.parser.ok(
                        "They come in low and unhurried, cerulean-coated, "
                        "filling the doorways. The nearest growls -- a sound "
                        "with arithmetic in it -- and the pack looks from you "
                        "to your bag, and back."
                    )
                # n <= 0: a fed (or long-calmed) pack lets it go -- the noise
                # only burns through their patience.
            else:
                streak = (hall.get_property(streak_key) or 0) + 1
                if streak >= 3 and n != 0:
                    hall.set_property(key, n - 1 if n > 0 else n + 1)
                    streak = 0
                hall.set_property(streak_key, streak)

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
                    g.show_figure("jackal")  # the card plays first
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

    # THE SCENT (CCB): jackals smell food. A player carrying anything edible
    # within two rooms of the den mouth (the Hall of Memory, heart of their
    # ground) draws the denned pack OUT -- no noise required; salt meat is
    # its own summons. Once out, the existing pursuit closes the distance.
    # A freshly fed pack (post-feed grace: negative ledgers) stays sated.
    def _hops(start, goal, cap=2):
        if start is goal:
            return 0
        from collections import deque

        seen = {start}
        queue = deque([(start, 0)])
        while queue:
            room, d = queue.popleft()
            if d >= cap:
                continue
            for nxt in room.connections.values():
                if nxt is goal:
                    return d + 1
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, d + 1))
        return cap + 1

    def _smells_of_food(g):
        # What the pack can SMELL: exposed meat (zox haunches, loose organs)
        # -- not everything technically edible. The friend's fungus rides in
        # a sealed plastic pouch; organs inside their sealed jars are mute.
        return any(
            it.get_property("smells_edible") for it in g.player.carried_items().values()
        )

    def _scent_check(g):
        if jackal_pack.location is not den or not _smells_of_food(g):
            return False
        if jackal_pack.get_property("is_dead") or jackal_pack.get_property(
            "is_unconscious"
        ):
            return False
        # Sated is sated: post-feed grace holds even against fresh meat.
        if any((h.get_property(f"_jk:{h.name}") or 0) < 0 for h in _halls):
            return False
        return _hops(memory, g.player.location) <= 2

    def _scent_pull(g):
        g.relocate(jackal_pack, memory)
        # Keep the pack's lope-and-rest rhythm: emergence is its own beat, so
        # the pursuit's first move is the hang-back yip, not the doorway.
        jackal_pack.set_property("_stride", True)
        g.parser.ok(
            "Down in the halls, noses lift. Something has smelled the salt "
            "on what you carry -- a yipping starts, low and purposeful, and "
            "begins to close."
        )

    game.add_trigger("jackal_scent", _scent_check, _scent_pull, repeatable=True)

    # The teamster DECAMPS once she has said her piece (CCB): she survived
    # the night by knowing when to be elsewhere, and she still knows.
    def _teamster_spoken(g):
        return teamster.get_property("has_spoken") and teamster.location is wreck

    def _teamster_decamps(g):
        wreck.remove_character(teamster)
        g.parser.ok(
            f"{teamster.name} settles the mask over her face, takes up her "
            "stick, and sets off south along the trail on foot -- a small "
            "figure keeping to the wind-shadow of the dunes, smaller, then "
            "gone. The road is yours, and the tomb is the road's."
        )

    game.add_trigger("teamster_decamps", _teamster_spoken, _teamster_decamps)

    # --- The point table's progress beats (CCB): the score is a progress
    # bar, not a diploma -- small awards mark the expedition's firsts, and
    # both victory routes reach the same 115.
    _interior = (youth, memory, hounds, warriors, canopic, sphere, chimney)

    def _score_beats(g):
        inv = g.player.inventory
        if g.player.location in _interior:
            g.award("threshold", 5, "[+5 -- the threshold]")
        if "waterskin" in inv:
            g.award("water", 5, "[+5 -- an inheritance of water]")
        if "falcon jar" in inv:
            g.award("falcon_jar", 5, "[+5 -- the falcon jar]")
        if "jackal jar" in inv:
            g.award("jackal_jar", 5, "[+5 -- the jackal jar]")
        # Each Exotica pays on ITS OWN find (CCB: no waiting for the pair),
        # and the Friend's Fungus pays when claimed from the mystic's hands.
        if "synth-hunting dagger" in inv:
            g.award("dagger", 5, "[+5 -- the synth-hunting dagger]")
        if "manifold box" in inv:
            g.award("box", 5, "[+5 -- the manifold box]")
        if "friend's fungus" in inv:
            g.award("fungus", 5, "[+5 -- the Friend's Fungus, claimed]")
        stone = inv.get("glowstone")
        if stone is not None and stone.get_property(Property.IS_LIT):
            g.award("first_light", 5, "[+5 -- light, learned]")
        # The minor threats pay when QUELLED, by any means (CCB): a spawn
        # dropped by blade or raked down by the bat-swarm, the pack paid
        # its tribute or put down. The clever route and the bloody one
        # score the same.
        for sp, key, card in (
            (spawn_guts, "spawn_guts", "guts-c"),
            (spawn_brain, "spawn_brain", "spawn-c"),
        ):
            if sp.get_property("is_dead") or sp.get_property("is_unconscious"):
                g.award(key, 5, f"[+5 -- the {sp.name} is quelled]")
                g.show_figure(card)  # the felled beat; the jar, claimable
        if jackal_pack.get_property("is_dead") or any(
            (h.get_property(f"_jk:{h.name}") or 0) <= -6 for h in _halls
        ):
            g.award("jackals_settled", 5, "[+5 -- the pack is settled]")

    game.add_trigger("score_beats", lambda g: True, _score_beats, repeatable=True)

    # The Hall of Warriors reads its own wreckage (CCB): the room description
    # recomputes whenever the set of standing cylinders changes.
    warriors.set_property("_cyl_state", ",".join(_standing_cylinders()))

    def _warriors_desc_stale(g):
        return warriors.get_property("_cyl_state") != ",".join(_standing_cylinders())

    def _warriors_desc_update(g):
        standing = _standing_cylinders()
        warriors.set_property("_cyl_state", ",".join(standing))
        fungus = (
            " Fungus has found the orange one; veins fan out under its "
            "glass like pressed flowers."
            if "orange" in standing
            else ""
        )
        if not standing:
            warriors.description = (
                "The four cylinders lie burst on the uneven floor, their "
                "gels run together into one darkening lake. The guard-"
                "mummies sprawl at attention from the waist up, and their "
                "scattered kit outlasts them still, as kit does."
            )
            return
        kept = _colour_list(standing)
        verb = "stands" if len(standing) == 1 else "stand"
        warriors.description = (
            f"Of the four plexiglas cylinders, only the {kept} still {verb} "
            "sealed, the guard-mummy within at an attention no order will "
            "relieve. The rest lie burst, their dead slumped in drifts of "
            f"drying gel, kit scattered where the flood carried it.{fungus} "
            "What kit remains has outlasted its owners, as kit does."
        )

    game.add_trigger(
        "warriors_desc", _warriors_desc_stale, _warriors_desc_update, repeatable=True
    )

    # The plinths' one-line descriptions read true (CCB): "empty" only while
    # they are.
    def _plinth_descs(g):
        for plinth, beast in ((falcon_plinth, "falcon"), (jackal_plinth, "jackal")):
            plinth.description = (
                f"an empty plinth carved with a {beast}"
                if not plinth.contents
                else f"a {beast}-carved plinth, its jar seated"
            )

    game.add_trigger("plinth_descs", lambda g: True, _plinth_descs, repeatable=True)

    # The Canopic hall reads its own progress too (CCB: "two stand empty" is
    # out of date the moment it isn't): plinth occupancy, per-plinth verdicts,
    # the seal, and whether the listener is even still in the room.
    def _canopic_state():
        occupied = sum(1 for pl in (falcon_plinth, jackal_plinth) if pl.contents)
        right = sum(
            1
            for pl, jar in (
                (falcon_plinth, "falcon jar"),
                (jackal_plinth, "jackal jar"),
            )
            if jar in pl.contents
        )
        return (
            occupied,
            right,
            bool(canopic.get_property("seal_open")),
            "mantis jar" in canopic.items,
        )

    def _canopic_desc_stale(g):
        return canopic.get_property("_desc_state") != str(_canopic_state())

    def _canopic_desc_update(g):
        occupied, right, seal_open, listener = _canopic_state()
        canopic.set_property("_desc_state", str(_canopic_state()))
        parts = ["Five plinths ring a central stair in a pentagon of dressed stone."]
        if occupied == 0:
            parts.append(
                "Three still bear their canopic jars; two stand empty, lit "
                "from within by a crimson light that does not flicker."
            )
        elif occupied == 1:
            parts.append(
                "Four bear jars now; the fifth stands empty, lit from within "
                "by a crimson light that does not flicker."
            )
        else:
            parts.append("For the first time in an age, none stands empty.")
        if not seal_open and right == 1 and occupied >= 1:
            parts.append(
                "One of the restored lights has turned white; the crimson "
                "of the rest is unconvinced."
            )
        elif not seal_open and occupied == 2 and right == 0:
            parts.append(
                "The crimson has not gone out of either restored plinth; "
                "the stone is not persuaded."
            )
        parts.append(
            "The stair climbs open into the dark above; of the seal, only "
            "a red glitter remains on the treads."
            if seal_open
            else "The stair climbs into shadow, barred by a seal of red " "crystal."
        )
        if listener:
            parts.append(
                "Something in this room is listening; you can tell, the way " "one can."
            )
        canopic.description = " ".join(parts)

    game.add_trigger(
        "canopic_desc", _canopic_desc_stale, _canopic_desc_update, repeatable=True
    )

    # --- Breaking the lattice: a shard, and Silas's wrath (CCB) --------------
    def _lattice_broken(g):
        return (
            any(
                e.actor == g.player.name
                and e.action == "break"
                and any(w in (e.summary or "").lower() for w in ("lattice", "crystal"))
                for e in g.events[g._round_event_start :]
            )
            and "crystal lattice" not in memory.items
        )

    def _lattice_shatters(g):
        memory_shard.examine_text = (
            "A splinter of lazulite, warm-edged where it broke. One facet "
            "still plays, over and over, "
            + _RNG.choice(_LATTICE_MEMORIES)
            + " The rest of the bank it came from is dark now, and will "
            "stay so."
        )
        memory.add_item(memory_shard)
        memory.description = (
            "Dead lattices climb every wall, dark where they were lit -- a "
            "library burned in a language no one else could read. Splinters "
            "of lazulite grit underfoot."
        )
        _scenery(
            memory,
            "shattered lattice",
            "the dead memory-crystal, dark and fractured",
            "The facets are ash-grey and silent. Whatever days the Autarch "
            "kept here are gone from the universe now, except the one in "
            "the shard.",
        )
        if not silas.get_property("is_dead") and not silas.get_property(
            "is_unconscious"
        ):
            silas.set_property("wrathful", True)
            silas.set_property("mellowed", False)
            g.parser.ok(
                'Silas turns all the way around for the first time. "Those '
                "were EVERYONE'S,\" he says, very quietly, and the cranial "
                'bores slide from his fingertips like claws. "Every day he '
                "ever kept. You have made me the last reader of a burned "
                'book." He comes for you, and he does not stop coming.'
            )

    game.add_trigger("lattice_break", _lattice_broken, _lattice_shatters)

    def _hop_anywhere(start, goal):
        """One step from *start* toward *goal*, any route (Silas knows every
        hall; unlike the pack he honors no territory)."""
        from collections import deque

        seen = {start}
        queue = deque([(start, None)])
        while queue:
            room, first = queue.popleft()
            for nxt in room.connections.values():
                if nxt is goal:
                    return first or nxt
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, first or nxt))
        return None

    def _silas_wrathful(g):
        return (
            silas.get_property("wrathful")
            and not silas.get_property("is_dead")
            and not silas.get_property("is_unconscious")
        )

    def _silas_hunts(g):
        here = g.player.location
        if silas.location is here:
            fatal = _wound_player(
                g,
                "Bore-Struck",
                1,
                (
                    "A cranial bore skips off your skull, taking skin.",
                    "His fingertips find the base of your neck; a white "
                    "spark of someone else's morning blinds you.",
                    "The archivist's hand closes on your jaw; the bore "
                    "sings against bone.",
                ),
            )
            if fatal:
                _die(
                    g,
                    "Silas reads you to the last page, and closes it. THE END.",
                )
            return
        step = _hop_anywhere(silas.location, here)
        if step is not None:
            g.relocate(silas, step)
            g.parser.ok(
                "Soft, unhurried footsteps keep coming -- the archivist, "
                "reading your trail."
                if step is not here
                else "Silas comes through the doorway, yellow robes without "
                "haste, bores out."
            )

    game.add_trigger("silas_wrath", _silas_wrathful, _silas_hunts, repeatable=True)

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
    chimney.items["orange growth"].perceptible_by(
        perception.Sense.TASTE,
        "You touch your tongue to the growth, briefly, like a fool. Orange "
        "rot blooms across it and your throat itches for a long minute. "
        "Whatever this fungus wants with a body, do not volunteer more of "
        "yours.",
    )

    # No grace rounds and no credit for a mask in your HAND (CCB): the air
    # itself is the hazard, so every round unmasked in the throat is a wound
    # -- WEAR the respirator, or burn the growth out, or don't linger.
    _hazard(
        game,
        chimney,
        danger=lambda g: "respirator" not in g.player.worn,
        gate=lambda g: not chimney.get_property("burned"),
        limit=1,
        warns=(),  # unreachable at limit=1: the first breath IS the harm
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
        g.show_figure("seal")
        g.parser.ok(
            "As the last jar settles onto its plinth, the crimson light steadies to "
            "white. The crystal seal sighs apart into motes, unblocking the "
            "stair: the way up stands open."
        )
        g.award("seal", 20, "[+20 -- the seal answers the jars]")
        _canopic_desc_update(g)  # the room reads open THIS round, not next

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

    # GIVE CORE TO SILAS (CCB): the item's own tease -- 'Silas would trade
    # his robes for it' -- honored. The Seeker's reading is finished; the
    # stated price is paid; the chain finally has an ending.
    monk_robes = things.Item(
        "yellow monk's robes",
        "the yellow robes of a Seeker of Eyeless Wisdom",
        "Plain-woven and dust-hemmed, yellow so the road shows on them: the "
        "rule of a mendicant order that reads the dead where they kept "
        "their own records. Given freely exactly once -- when a Seeker's "
        "reading is done.",
    )
    monk_robes.set_property(Property.WEARABLE, True)
    monk_robes.set_property("wear_slot", "body")
    monk_robes.add_alias("robes")
    monk_robes.add_alias("yellow robes")
    monk_robes.add_alias("monk's robes")

    def _core_given(g):
        return "ego-core" in silas.inventory and not silas.get_property("core_traded")

    def _core_trade(g):
        silas.set_property("core_traded", True)
        g.player.add_to_inventory(monk_robes)
        silas.description = (
            "a gaunt synthetic archivist, bare-chassised, wholly given to "
            "his reading"
        )
        silas.examine_text = (
            "The synth without his robes: a lattice of dust-dulled alloy, "
            "unbothered by the cold, the ego-core held to his chest the way "
            "a man holds water in the desert. The bright threads of the "
            "lattice spool around him in patterns like thought."
        )
        silas.talk_text = (
            '"He was afraid," Silas says, not looking up from the core. '
            '"Under the jars and the seal and all this keeping -- afraid '
            "that to be forgotten was to have never been. Most of what he "
            "chose to keep is ordinary: bread, an argument, rain on a fig "
            "tree, a daughter counting to a hundred. Four centuries of a "
            'man practicing goodbye. I will finish it for him."'
        )
        g.parser.ok(
            "Silas goes still the way only a machine can, every thread of "
            "the lattice hanging mid-spool. He takes the ego-core in both "
            'hands, the way a man takes water in the desert. "A thousand '
            'years I have read this tomb from its margins," he says. "You '
            'have just handed me the author." He unknots the yellow robes '
            "and folds them over your arm, unasked -- the rule of his "
            'order, and the stated price, paid in full. "When he is whole, '
            "we will speak him aloud once, and let him go. You will have "
            "finished a king, scavenger. Wear the yellow; you have earned "
            'the dust it shows."'
        )
        g.award("archivist", 5, "[+5 -- the archivist made whole]")

    game.add_trigger("silas_core", _core_given, _core_trade, repeatable=False)

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
                "troubles you less; a wound heals."
            )
            g.award("healed", 5, "[+5 -- water, spent wisely]")
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
        g.award("horror", 25, "[+25 -- the Horror is ended]")
        # The coil unclenches: the coffin's keeping is over.
        coffin_item = sphere.items.get("coffin")
        released = []
        if coffin_item is not None:
            for it in list(coffin_item.contents.values()):
                coffin_item.remove_item(it)
                sphere.add_item(it)
                released.append(it.name)
        sphere.set_property("horror_dead", True)
        # Every death here is a burning one (steel alone is a treadmill): the
        # remains are ASH, an object in the room, not a listed combatant --
        # and the room itself becomes the fight's record (CCB).
        if horror.location is sphere:
            sphere.remove_character(horror)
        _sphere_aftermath(g, ash=True)
        if g.player.location is not sphere:
            # Burned to death with no one watching: heard, not seen.
            g.parser.ok(
                "From the Burial Sphere, a long wet shriek, and then nothing "
                "at all -- not even the sound of something mending."
            )
            return
        msg = (
            "The Horror comes apart and does not close again -- what the fire "
            "leaves of it hangs in the air as a drift of ash."
        )
        if released:
            msg += (
                " Its coil unclenches from the Autarch's bones, and what he "
                "was buried with drifts free: " + ", ".join(released) + "."
            )
        g.parser.ok(msg)

    # Striking the Horror: the ENGINE's vigor system (actions/fight.py) does
    # the arithmetic now -- vigor 5, struck_text per blow. This trigger only
    # converts the FINAL blow's knockout into the death it really is, before
    # _horror_turn could let a "senseless" Horror knit.
    def _struck_horror(g):
        return horror.get_property("is_unconscious") and not horror.get_property(
            "is_dead"
        )

    def _horror_struck(g):
        _horror_dies(g)

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

    # --- The glass centipede: ambush, then a HUNT (CCB) ----------------------
    # It springs in the chimney as before -- but once sprung it follows the
    # player anywhere, a room a round, and bites every round it shares one.
    # The outs: keep moving (it closes but grants an arrival round), one solid
    # blade hit, fire in the chimney -- or the Summit's edge (the toss, below).
    def _centipede_venom(g):
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
                "The venom finishes what the tomb began; the tomb keeps you. "
                "THE END.",
            )

    def _centipede_active(g):
        return (
            not centipede.get_property("is_dead")
            and not centipede.get_property("is_unconscious")
            and (centipede.get_property("sprung") or g.player.location is chimney)
        )

    def _centipede_hunts(g):
        here = g.player.location
        if not centipede.get_property("sprung"):
            if chimney.get_property("burned"):
                return  # scoured out before it ever sprang
            centipede.set_property("sprung", True)
            if centipede.location is not chimney:
                g.relocate(centipede, chimney)
            g.show_figure("centipede", force=True)  # a story beat: always plays
            g.parser.ok(
                "The growth beside you bends wrong -- and four feet of glass "
                "uncoils out of it, faster than the eye wants to allow."
            )
            _centipede_venom(g)
            return
        if centipede.location is here:
            _centipede_venom(g)
            return
        step = _hop_anywhere(centipede.location, here)
        if step is not None:
            g.relocate(centipede, step)
            g.parser.ok(
                "Glass pours through the doorway after you, unhurried as "
                "water finding a level."
                if step is here
                else "Somewhere behind you, glass ticks over stone, keeping "
                "your pace."
            )

    game.add_trigger(
        "centipede_hunt", _centipede_active, _centipede_hunts, repeatable=True
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
        "A spindle of smoke-grey memory-crystal that has not fully agreed "
        "to be in this room: look away and back and it hangs at a slightly "
        "different angle than you left it, and its faint shadow falls "
        "against the light. Heavier than it looks, warmer than it should "
        "be. Nassak An-Rah -- or what he chose to keep of himself, stored "
        "where geometry could not evict him. Silas would trade his robes "
        "for it.",
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
            "Under the ninth colour, the manifold box stops pretending. Its "
            "gilded walls go glassy, then merely ADVISORY -- and the "
            "interior opens away from you: not a compartment but a hall, "
            "receding along a direction the tomb does not otherwise have. "
            "The geometry in there has stopped agreeing with the geometry "
            "out here. Corners count wrong. Parallel edges meet, twice, "
            "somewhere behind you. The vanishing point sits over your own "
            "shoulder, and the far end of that unlit hall is a pace away "
            "and a province away, in the manner of stars. There, hanging "
            "where every wrong angle converges, a spindle of smoke-grey "
            "crystal turns without turning, its shadow falling UP the "
            "light. You reach in. Your arm bends along an angle that has "
            "no name; your hand goes cold as television static, in a place "
            "your eyes decline to file. Your fingers close on it anyway. "
            "You draw out An-Rah's ego-core, your arm comes back honest, "
            "and the hall folds itself away like a sentence ending -- "
            "leaving the box merely gilded, merely small, and very "
            "slightly heavier than the room it keeps."
        )

    game.add_trigger("ulfire_box", _box_viewed, _reveal_core, repeatable=False)

    # The mantis jar has teeth (CCB): a ONE-TIME defensive snap at the first
    # hand that opens it. It stays an alarm, not a combatant -- the bite
    # teaches respect; the song it sings at noise delivers the sentence.
    def _jar_violated(g):
        opened = any(
            e.actor == g.player.name
            and e.action == "open"
            and "mantis" in (e.summary or "").lower()
            for e in g.events[g._round_event_start :]
        )
        open_due = opened and not mantis_jar.get_property("bit_for_open")
        # The eyes leave the jar only by a hand reaching in (CCB: that hand
        # is bitten too) -- one bite per violation, not per carry.
        reach_due = "fungal eyes" in g.player.inventory and not mantis_jar.get_property(
            "bit_for_eyes"
        )
        return open_due or reach_due

    def _mantis_snaps(g):
        if any(
            e.actor == g.player.name
            and e.action == "open"
            and "mantis" in (e.summary or "").lower()
            for e in g.events[g._round_event_start :]
        ):
            mantis_jar.set_property("bit_for_open", True)
        if "fungal eyes" in g.player.inventory:
            mantis_jar.set_property("bit_for_eyes", True)
        g.parser.ok(
            "The split in the jar widens and the mantis head STRIKES -- one "
            "motion, out and back, quicker than the eye. The jar settles "
            "again, as if it had never moved."
        )
        fatal = _wound_player(
            g,
            "Mantis-Bitten",
            1,
            (
                "Mandibles close on your wrist and are gone before your "
                "eyes catch up.",
                "Something arched and chitinous snaps across your knuckles; "
                "the cut is clean as scissors.",
                "The mantis head snips the web of your hand and lets go "
                "-- a warning, not a meal.",
            ),
        )
        if fatal:
            _die(g, "The jar sings on over what it has done. THE END.")

    game.add_trigger("mantis_snap", _jar_violated, _mantis_snaps, repeatable=True)

    # Win: escape to the surface carrying both Exotica (the Dagger + the Box).
    def _escape(g):
        g.player.set_property("escaped", True)
        g.award("escape", 20, "[+20 -- out alive]")
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
    "take glowstone",
    "talk to teamster",
    "in",
    "open crates",
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
    # Loot the wreck (water heals; the glowstone lights the dark Warriors)
    # -- and bring the dates: the crashes ahead ring the mantis song, the
    # song calls the jackals, and the pack is BOUGHT, not fought.
    "search merchant",
    "take glowstone",
    "take waterskin",
    "in",
    "open crates",
    "take crate of dates",
    "out",
    "north",
    "sneak east",  # Warriors: pitch dark; the kit is sealed in the cylinders
    "light glowstone",  # safe here -- no bats -- and the colours matter
    "break amber cylinder",  # the eyeless spawn swings toward the crash --
    "take respirator",  # -- and the crashes call its brother from next door
    "wear respirator",
    "break cerulean cylinder",  # second crash: the song has the pack's ear now
    "give dates to jackal pack",  # -- so pay the toll the moment they fill the doorways
    "take blade",
    "attack spawn of guts with blade",  # answer it: the falcon jar drops
    "take falcon jar",
    "attack spawn of brain with blade",  # its brother came to the noise: fell it too
    "take jackal jar",
    "drink water",  # a glug; a wound heals (keep the blade: the coffin wants it)
    "drink water",  # another -- the brain got its thoughts in
    "drink water",  # the last ration; the skin runs dry
    "drop waterskin",  # travel light; the climbs refuse a full pack
    "break orange cylinder",  # the bloom vents against the mask, disappointed
    "take igniter",
    "break viridian cylinder",
    "take boots",
    "douse glowstone",
    "drop glowstone",  # the halls ahead light themselves
    # The archivist's acquaintance and the dead king's days (the full-score
    # detour: Memory is one quiet hall south, and the lattice lights itself).
    "sneak south",
    "talk to silas",
    "x lattice",
    "sneak north",
    "sneak east",
    "take gel",  # Hounds: gel
    "sneak up",  # -> Canopic (no luring needed -- the jars came off the dead)
    "put falcon jar on falcon plinth",
    "put jackal jar on jackal plinth",  # seal opens
    "sneak left stairs",  # the left stairs descend to Memory
    "sneak south",
    "sneak south",  # Canopic -> Exterior (dark and quiet through the Youth)
    "up",
    "search corpse",  # the mystic's hands hold the Friend's Fungus...
    "take fungus",  # ...claimed BEFORE the burn consumes it (+5)
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
    "give fungus to silas",  # the lonely archivist hands over the lantern
    "light ulfire lantern",  # ...which opens the manifold box's true interior
    "give core to silas",  # the stated price: his robes, and an ending (+5)
    # Consult every remembered day (unseen facets draw first, so nine looks
    # cover the nine) -- and the tenth look wakes the keep-list (+5).
    "x lattice",
    "x lattice",
    "x lattice",
    "x lattice",
    "x lattice",
    "x lattice",
    "x lattice",
    "x lattice",
    "x lattice",
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
        # Interactive play gets the Infocom trio: SAVE/RESTORE slots persist
        # to a JSON file beside your home dir, via the loop that can actually
        # rebuild the world on RESTORE (saves.run_with_saves).
        from ..saves import FileSaveStore, run_with_saves

        run_with_saves(build_game, FileSaveStore("~/.tomb_of_nassak_saves.json"))
