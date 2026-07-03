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

from text_adventure_games import games, things, actions, blocks, reactions, perception
from text_adventure_games.enums import Property


def _die(game, message):
    """End the game with a death line (the tomb is deadly)."""
    game.parser.ok(message)
    game.game_over = True
    game.game_over_description = message


# "Loud" actions are everything NOT in a hazard's quiet set. Movement (go/sneak)
# and looking are always quiet -- you may walk the tomb freely. What kills is
# LIGHT (the bats), sustained NOISE (the jackals), SPORES (the chimney), or
# disturbing the coffin (the Horror) -- and every hazard warns before it kills.
_QUIET = {"go", "sneak", "look", "examine", "describe", "inventory", "wait",
          "get", "drop", "put", "talk", "open", "wear", "light", "douse",
          "feel", "listen", "smell"}
# To the Fungal Horror, even rummaging is a disturbance: only moving, looking,
# quietly sensing, and working your own light are safe (so you can enter, see it,
# and back out -- but not loot it alive).
_QUIET_SPHERE = {"go", "sneak", "look", "examine", "describe", "inventory",
                 "light", "douse", "feel", "listen", "smell"}


def _is_holding(character, name):
    return name in character.inventory


def _player_was_loud_in(g, room, quiet):
    """True if the player did a loud (non-quiet) action located in *room* this
    round. Movement and looking never count -- only acts like say / break / attack
    / pry. (Creatures' own actions don't count -- it's the player giving themselves
    away.)"""
    for e in g.events[g._round_event_start :]:
        if (
            e.actor == g.player.name
            and e.action not in quiet
            and (e.payload or {}).get("location") == room.name
        ):
            return True
    return False


def _hazard(game, room, *, danger, warns, kill, limit=3, gate=None):
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
        active = (
            g.player.location is room
            and (gate is None or gate(g))
            and danger(g)
        )
        if not active:
            room.set_property(key, 0)
            return
        n = (room.get_property(key) or 0) + 1
        room.set_property(key, n)
        if n >= limit:
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
    ACTION_ALIASES = [
        f"{verb} {direction}"
        for verb in ("sneak", "creep", "tiptoe")
        for direction in ("north", "south", "east", "west", "up", "down", "in", "out")
    ]

    def __init__(self, game, command, actor=None):
        cl = command.lower()
        for verb in ("sneak to", "creep to", "tiptoe to", "sneak", "creep", "tiptoe"):
            if cl.startswith(verb):
                command = "go " + command[len(verb) :].strip()
                break
        super().__init__(game, command, actor=actor)


class FungalSong(reactions.Startle):
    """The Canopic hall's mantis-headed jar -- split and fungal -- SINGS whenever it
    hears a noise, and the wail carries across the whole tomb, luring the Spawn
    (which are :class:`DrawnToSound`) to the singer. Re-arms each round."""

    REPEATABLE = True

    def apply_effects(self):
        self.game.parser.ok(
            "The mantis-headed jar splits wider and SINGS -- a tuneless, carrying "
            "wail that fills the tomb."
        )
        self.game.emit_sound(self.owner.location, 6, "a tuneless fungal song")


class BurnCorpse(actions.Action):
    """Burn the ossified corpse at the Summit -- the root of the fungus. With the
    gel and the igniter it goes up in flame, and the whole network (the Fungal
    Horror included, far below) dies with it. The elegant boss solution: it makes
    the Burial Sphere safe to enter without ever fighting the Horror."""

    ACTION_NAME = "burn corpse"
    ACTION_DESCRIPTION = "Set the ossified corpse alight (needs gel and a flame)"
    ACTION_ALIASES = [
        "burn ossified corpse", "burn the corpse", "ignite corpse",
        "torch corpse", "burn mystic", "burn the ossified corpse",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if self.player.location is None or self.player.location.name != "The Summit":
            self.parser.fail("There's nothing here to burn.")
            return False
        if self.player.location.get_property("cleansed"):
            self.parser.fail("The corpse is already ash; the fungus is dead.")
            return False
        if not (_is_holding(self.player, "flask of gel") and _is_holding(self.player, "plasma-igniter")):
            self.parser.fail(
                "Bone gone to stone does not take bare flame. It would want "
                "dousing in something that burns, and a spark hot enough to "
                "mean it."
            )
            return False
        return True

    def apply_effects(self):
        gel = self.player.inventory.get("flask of gel")
        if gel is not None:
            self.player.remove_from_inventory(gel)
        self.player.location.set_property("cleansed", True)
        self.game.locations["Burial Sphere of Nassak An-Rah"].set_property("horror_dead", True)
        self.parser.ok(
            "You splash the embalming gel over the ossified mystic and strike the "
            "igniter. Orange flame roars down the fungal chimney -- and far below, the "
            "whole rotten network shudders and dies. The Fungal Horror sloughs into "
            "ash. The tomb falls silent at last."
        )
        self.game.award("cleanse", 30, None)


class PryCoffin(actions.Action):
    """Pry open the Autarch's anti-entropy coffin in the zero-g Burial Sphere to
    claim the Exotica. The coffin floats off the wall; you can only get the
    purchase to force it open while anchored by the magnetic boots."""

    ACTION_NAME = "pry coffin"
    ACTION_DESCRIPTION = "Pry open the floating coffin (needs the magnetic boots)"
    ACTION_ALIASES = [
        "open coffin", "open the coffin", "pry open coffin", "pry the coffin",
        "loot coffin", "loot the coffin", "pry open the coffin",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or "coffin" not in loc.items:
            self.parser.fail("There's no coffin here.")
            return False
        if loc.items["coffin"].get_property("pried"):
            self.parser.fail("The coffin is already open.")
            return False
        if "magnetic boots" not in self.player.worn:
            self.parser.fail(
                "You reach the coffin and shove -- and it is you who drifts "
                "away, slow as sediment. Nothing here holds you down, and "
                "prying wants something to brace against."
            )
            return False
        return True

    def apply_effects(self):
        loc = self.player.location
        coffin = loc.items["coffin"]
        coffin.set_property("pried", True)
        taken = []
        for item in list(coffin.contents.values()):
            coffin.remove_item(item)
            loc.add_item(item)
            taken.append(item.name)
        self.parser.ok(
            "Anchored by the magnetic boots, you brace against the coffin and force "
            "the glass apart. Among the Autarch's drifting bones you find: "
            + ", ".join(taken) + "."
        )
        self.game.award("exotica", 30, None)


class CrystalSeal(blocks.Block):
    """The red-crystal seal barring the stair from the Canopic hall up to the
    Burial Sphere. It clears once both missing canopic jars sit on their matching
    plinths (the placement trigger sets ``seal_open`` on the Canopic hall)."""

    def __init__(self, canopic):
        super().__init__(
            "A seal of red crystal",
            "A seal of red crystal bars the stair, grown through the treads like "
            "frost through cloth. Five beast-sigils are set in the arch above "
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
    jar tells you nothing of what's inside)."""
    jar = things.Item(name, description, examine_text).make_container()
    jar.set_property("is_closed", True)
    organ = things.Item(organ_name, organ_desc, organ_desc)
    organ.set_property("gettable", False)
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

    hold.obscure(perception.Darkness(
        blurb="Bruise-dark. The hold smells of saffron, lamp-oil, and the dry "
        "sweetness of dates; you can make out crate-shapes, and on a desk "
        "somewhere, a pale square of paper. The daylight is a grey rectangle "
        "behind you."))

    _scenery(wreck, "wreck", "the heeled-over wind-wagon",
             "Pale ribs and torn sailcloth. Wind-wagons are built to outrun "
             "anything on the Tomblands road, and this one nearly did.")
    _scenery(wreck, "zoxen", "two dead zoxen, half-sanded",
             "The caravan's draught-zoxen, patient in death as in life, already "
             "sanded to the shoulder. By morning the road will have them wholly.")
    _scenery(hold, "crates", "lashed crates of saffron and dates",
             "Trade goods bound for the souks of Gnomon, worth a season's water. "
             "Too much to carry, and the Cacklemaw do not trade.")
    ledger = _scenery(hold, "ledger", "the merchant's ledger",
             "A trade ledger bound in lizard-skin, closed around a ribbon "
             "marker at its final page.")
    # FEEL finds the ledger in the dark hold -- so an empty-handed player who
    # gropes around is rewarded, and the probe is rehearsed before the Hall of
    # Youth needs it.
    ledger.perceptible_by(perception.Sense.TOUCH,
             "Your hands find a folding desk, and on it a book bound in "
             "lizard-skin, closed around a ribbon. Too dark to read a word of it.")
    ledger.set_property("read_text",
             "The hand is neat until it is not. '...ninth day. Camped in the lee "
             "of the tomb the guards call the Three Mouths. They will not pass "
             "it after dark, and I have stopped teasing them for it. Kotesh "
             "swears the boy's mouth is lightless within, and that what roosts "
             "there hates a lamp worse than a shout. The halls, he says, "
             "remember every footfall. And none of them, drunk or paid, will "
             "speak of the old man's mouth, which weeps orange. Superstition -- "
             "but I observe that my guards are paid to be brave, and are not. "
             "Tomorrow, Gnomon.' The entry is the last.")
    ledger.add_command_hint("read ledger")

    pack = things.Item(
        "pack", "the merchant's half-buried pack",
        "Boiled leather, half-buried, the straps still buckled. Whatever the "
        "Cacklemaw came for, it was not this.",
    ).make_container()
    pack.set_property("is_closed", True)
    pack.add_command_hint("open pack")
    waterskin = things.Item(
        "waterskin", "a half-full waterskin",
        "Half of the merchant's water survived the night. In Vaarn this is "
        "called an inheritance.",
    )
    wreck.add_item(pack)

    # Worry is a NEWBEAST -- a humanoid animal-person (Issue 1: they "speak and
    # walk like men", wear masks in imitation of the human face). She was the
    # caravan's TEAMSTER, driving the zoxen; the zoxen pulled. Newbeasts are
    # never beasts of burden -- canon reserves that for zoxen and iron mules.
    worry = things.Character(
        "Worry", "a new-mule teamster",
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
        '"They came at moonset," Worry says. "Laughing. I ran, and the merchant '
        "could not, and that is the whole story. The Cacklemaw make no secret "
        'of their coming; the secret is what good knowing does you." She looks '
        'north, to the faces in the azure stone. "Take what he no longer needs '
        "-- better you than the sand. His ledger is in the hold, and the dark "
        "in there is ordinary; he kept a glowstone in his pack, and it is the "
        "only light left on this road. But "
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
        "of the Autarch set in lazulite. The light inside them is not reflection; "
        "it moves while you are still, slow and cold, like thought at the bottom "
        "of a lake. One bank of crystal is worn smooth at hand-height, as if "
        "often consulted.",
    )
    hounds = things.Location(
        "Hall of Hounds",
        "A wall of plexiglas holds back a tank of embalming gel, luminous, the "
        "green-gold of old honey. Ten of An-Rah's hunting hounds hang suspended "
        "in it, black and spindly, threaded through with chrome, forever "
        "mid-stride. They are perfectly preserved. Their eyes are open.",
    )
    warriors = things.Location(
        "Hall of Warriors",
        "Four plexiglas cylinders stand on an uneven floor, each holding a "
        "guard-mummy at attention in Autarchy armour. The fungus has found all "
        "four; orange veins fan out under the glass like pressed flowers. Their "
        "kit has outlasted them, as kit does.",
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
    wreck.add_connection("north", exterior)       # the Tomblands road (auto: exterior south -> wreck)
    exterior.add_connection("north", youth)       # child's mouth (west face) -> Youth
    exterior.add_connection("east", warriors)     # warrior's mouth (east face) -> Warriors
    exterior.add_connection("up", summit)         # climb the exterior (auto: summit down -> exterior)

    # The lower diamond: Youth-Memory-Warriors-Hounds form a 4-cycle (spec §3:
    # edges 1-2, 1-3, 4-2, 4-3).
    youth.add_connection("north", memory)         # 1-2
    youth.add_connection("west", hounds)          # 1-3
    memory.add_connection("north", warriors)      # 2-4
    warriors.add_connection("east", hounds)       # 4-3

    # Stairs up to the Canopic hall from both Memory and Hounds. memory's "up"
    # auto-wires canopic "down" -> memory; hounds' up is set manually so it does
    # not clobber that single "down".
    memory.add_connection("up", canopic)          # canopic.down -> memory
    # Hounds also has a stair up; set it by hand (with its travel description) so it
    # doesn't clobber canopic's single "down" (-> memory). The halls interconnect,
    # so from the Canopic hall you descend to Memory and reach the rest from there.
    hounds.connections["up"] = canopic
    hounds.travel_descriptions["up"] = ""

    # Canopic stair up to the Burial Sphere (Phase 2 bars this with the crystal
    # seal Block; open for now so the scaffold is fully walkable).
    canopic.add_connection("up", sphere)          # sphere.down -> canopic (the aperture)

    # The fungal chimney is a real, passable, spore-choked ROOM between the Summit
    # and the Sphere's crown. You CAN go "in" -- but the spores choke you worse each
    # round you linger (the hazard, below); dash through, or wear a respirator.
    summit.add_connection("in", chimney)          # auto: chimney out -> summit
    chimney.add_connection("down", sphere)        # auto: sphere up -> chimney

    # --- Atmosphere: examinable scenery (hooks for later phases) -------------
    _scenery(exterior, "tomb", "the Tomb of Nassak An-Rah",
             "Three faces in azure stone -- boy, warrior, and sky-gazing elder -- "
             "their mouths gaping as doors. Orange fungus mortars every seam.")
    # The statues can be felt in the dark (TOUCH); the ceiling of bats can be
    # heard (HEARING) -- so EXAMINE-in-the-dark and the feel/listen probes reveal
    # them without a light (perception Layer 2). The ceiling's *visual* text is
    # what you see once lit; its heard text is the dark clue.
    statues = _scenery(youth, "statues", "blue statues of the boy-Autarch",
             "Nassak An-Rah as an infant, a child, a youth -- each rendered with "
             "unsettling tenderness in cold blue stone.")
    statues.perceptible_by(perception.Sense.TOUCH,
             "Your hands find cold, smooth stone -- a swaddled infant, then a "
             "standing boy, larger than life. The boy-Autarch, unmistakably.")
    ceiling = _scenery(youth, "ceiling", "the vaulted ceiling",
             "Your light picks out the vault overhead: the whole ceiling seethes "
             "with roosting bats, packed wing to wing, thousands of them -- and "
             "the nearest have already let go of the stone.")
    ceiling.perceptible_by(perception.Sense.HEARING,
             "You can't see a thing, but the vault overhead seethes -- a dry, "
             "restless storm of leathery wings. A great many, and close. They "
             "shift when you shift.")
    _scenery(memory, "crystal lattice", "lattices of memory-crystal",
             "Lazulite crystals knit across the walls, worn smooth at hand-height. "
             "One bank replays the Autarch's embalming for no one: the baboon took "
             "his lungs, the human his liver, the mantis his eyes; the falcon was "
             "given his intestines, and the jackal -- strangely -- his brain.")
    _scenery(hounds, "tank", "a plexiglas tank of embalming gel",
             "Ten hounds hang in the luminous gel, chrome-threaded, forever "
             "mid-stride. Even through the seam the gel smells of lamp-oil and "
             "honey. Collectors would pay in salt and water for any of this.")
    _scenery(warriors, "cylinders", "four plexiglas burial cylinders",
             "Each holds a guard-mummy in Autarchy armour, at an attention no "
             "order will ever relieve, the glass fogged from within by threads "
             "of orange fungus.")
    # The three present jars sit on their plinths -- sealed containers. OPEN one to
    # learn which organ it holds (a second route to the head->organ matching, on
    # top of the plinth carvings and the memory crystals).
    baboon_jar = _canopic_jar(
        "baboon jar", "a baboon-headed canopic jar",
        "A sealed jar with a baboon's head. Something shifts dryly inside.",
        "lungs", "a pair of withered lungs")
    human_jar = _canopic_jar(
        "human jar", "a human-headed canopic jar",
        "A sealed jar with a man's face. Something shifts inside.",
        "liver", "a leathery liver")
    mantis_jar = _canopic_jar(
        "mantis jar", "a mantis-headed canopic jar",
        "A split, fungal jar with a mantis's head, a misshapen orange growth budding "
        "from the crack. It stirs at the faintest sound, as if listening.",
        "fungal eyes", "a clutch of fungus-clotted eyes")
    for j in (baboon_jar, human_jar, mantis_jar):
        j.set_property("gettable", False)
        canopic.add_item(j)

    # The two empty plinths are surfaces you set the missing jars ON; each is
    # carved with the head that belongs there.
    falcon_plinth = things.Item(
        "falcon plinth", "an empty plinth carved with a falcon",
        "A plinth carved as a falcon, lit crimson and empty. The carving's "
        "talons are cupped, curled around the shape of something it has lost.",
    ).make_surface(capacity=1)
    falcon_plinth.set_property("gettable", False)
    jackal_plinth = things.Item(
        "jackal plinth", "an empty plinth carved with a jackal",
        "A plinth carved as a jackal, lit crimson and empty. The stone jaws are "
        "parted, holding their grip on an absence.",
    ).make_surface(capacity=1)
    jackal_plinth.set_property("gettable", False)
    canopic.add_item(falcon_plinth)
    canopic.add_item(jackal_plinth)
    dagger = things.Item(
        "synth-hunting dagger", "An-Rah's synth-hunting dagger",
        "A dagger that flashes coded LogLang as you grip it -- synthetics flinch "
        "from its wielder.")
    dagger.set_property("is_weapon", True)
    dagger.add_alias("dagger")
    manifold_box = things.Item(
        "manifold box", "An-Rah's manifold box",
        "A small gilded box that doesn't quite fit the space it sits in -- "
        "hypergeometric, and heavier inside than out.")
    manifold_box.add_alias("box")
    coffin = _scenery(
        sphere, "coffin", "the Autarch's anti-entropy coffin",
        "A clouded glass sphere at the chamber's heart, its field failing, its "
        "interior a slow orange churn. Past the cloud, shapes drift and turn "
        "like fish under ice: bone, and things that were buried to be kept. The "
        "seam at its equator is fine as a hair -- made to be pried, never opened.")
    coffin.make_container()
    coffin.set_property("is_closed", True)  # PryCoffin (boots-gated) is the only way in
    coffin.add_item(dagger)
    coffin.add_item(manifold_box)
    _scenery(summit, "ossified corpse", "an ossified mystic",
             "A corpse turned to stone mid-meditation, orange fungus weeping from its "
             "eyes and mouth -- the wellspring, it seems, of all the rot below.")

    # The two missing jars are WORN by the Spawn (each as a hat). Knock a Spawn out
    # (it needs a weapon -- the prismatic blade below) and it drops the jar.
    falcon_jar = _canopic_jar(
        "falcon jar", "a falcon-headed canopic jar",
        "A sealed jar with a falcon's head. Something coils inside.",
        "intestines", "a coil of cured intestines")
    jackal_jar = _canopic_jar(
        "jackal jar", "a jackal-headed canopic jar",
        "A sealed jar with a jackal's head. Something heavy rolls inside.",
        "brain", "the Autarch's shrivelled brain")

    spawn_guts = things.Character(
        "spawn of guts", "a fungal spawn wearing a falcon-headed jar",
        "I am what is left of the Autarch's appetites.",
    )
    spawn_guts.examine_text = (
        "What could be described as an octopus of orange fungus and grave-cured "
        "intestine -- though even that doesn't quite get it -- wearing the "
        "falcon canopic jar on top like a hat. It sways toward any sound."
    )
    spawn_guts.add_to_inventory(falcon_jar)
    spawn_brain = things.Character(
        "spawn of brain", "a fungal spawn wearing a jackal-headed jar",
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

    # The prismatic blade -- a weapon, pried from a guard's cylinder. (The full
    # guard-mummy gear and spore hazard arrive in Phase 4; for now the blade lets
    # you fight the Spawn.)
    blade = things.Item(
        "prismatic blade", "a guard's prismatic blade",
        "An Autarchy guard's blade, its edge fracturing the light into colours.",
    )
    blade.set_property("is_weapon", True)  # Property.IS_WEAPON == "is_weapon"
    blade.add_alias("blade")
    warriors.add_item(blade)

    # Endgame gear: a plasma-igniter and magnetic boots (more guard kit), and a
    # flask of flammable embalming gel from the hound tank.
    igniter = things.Item(
        "plasma-igniter", "an Autarchy plasma-igniter",
        "A guard's plasma-igniter -- a thumb-flame hot enough to light anything.",
    )
    igniter.add_alias("igniter")
    boots = things.Item(
        "magnetic boots", "a pair of magnetic boots",
        "Heavy Autarchy guard-boots, soled in dull magnet-metal. They clamp to "
        "anything ferrous with a click that means it, and let go grudgingly.",
    )
    boots.set_property(Property.WEARABLE, True)
    boots.set_property("wear_slot", "feet")
    boots.add_alias("boots")
    respirator = things.Item(
        "respirator", "an Autarchy respirator",
        "A guard's filter-mask -- clean air in a spore-choked place.",
    )
    respirator.set_property(Property.WEARABLE, True)
    respirator.set_property("wear_slot", "face")
    respirator.add_alias("mask")
    warriors.add_item(igniter)
    warriors.add_item(boots)
    warriors.add_item(respirator)
    gel = things.Item(
        "flask of gel", "a flask of embalming gel",
        "A flask of luminous embalming gel scooped from the hound tank. It reeks, "
        "and it burns.",
    )
    gel.add_alias("gel")
    hounds.add_item(gel)

    # Silas -- the synthetic archivist (the hint NPC). His combat / pacify / rob
    # outcomes arrive with later phases (the dagger, Friend's Fungus); for now he
    # warns you about the Spawn and the seal if you talk to him.
    silas = things.Character(
        "Silas", "a yellow-robed synthetic archivist",
        "I am Silas, of the Seekers of Eyeless Wisdom. I read the dead.",
    )
    silas.examine_text = (
        "A gaunt synth in fuligin-yellow robes, fingertips tipped with cranial "
        "bores, drawing memory from the lattice in slow bright threads. Patient, "
        "courteous, elsewhere. Now and then his lips move -- circular glyphs, "
        "no sound."
    )
    silas.talk_text = (
        'Silas speaks without turning. "Scavenger. You walk in a house of '
        "memory; mind what you wake. Two of the Autarch's organs have got up and "
        "walk these halls wearing their own jars -- his appetites and his "
        "thoughts, if you follow me. I do not fight them; I read. The lattice "
        "remembers his embalming, for those who trouble to look, and the plinths "
        'above remember what they held." A pause; a brief run of clipped, '
        'circular syllables, like a quotation. "The dead here listen. Step '
        'softly."'
    )
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
        "glowstone", "a dim glowstone",
        "A shard of cold lazulite, dark until woken. Scavengers carry them "
        "dark: light is dear, and attention dearer.",
    )
    glowstone.set_property(Property.FLAMMABLE, True)
    glowstone.add_alias("stone")
    glowstone.add_alias("lantern")
    glowstone.add_command_hint("light glowstone")
    glowstone.add_command_hint("douse glowstone")
    pack.add_item(glowstone)
    pack.add_item(waterskin)

    game = TombGame(
        wreck, player, characters=[silas, spawn_guts, spawn_brain, worry],
        custom_actions=[Sneak, BurnCorpse, PryCoffin],
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
    game.add_reaction(mantis_jar, FungalSong())
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
    youth.obscure(perception.Darkness(
        blurb="Dark as the inside of a sealed jar. The air is chill and smells "
        "of old guano; somewhere far above, leather rustles against leather, "
        "patient and vast. The caravan-guards' word for the boy's mouth was "
        "'lightless', and they meant it as advice."))

    # The bats: roused by carrying a LIT light into the Youth, or by a loud noise
    # there. Patient -- the escalation is the clock. Douse the light (or fall
    # quiet) and they settle.
    _hazard(game, youth,
            danger=lambda g: perception.carries_light(g.player) or _player_was_loud_in(g, youth, _QUIET),
            warns=(
                "The rustle overhead deepens. Grit sifts down through your light; "
                "the whole vault has begun, gently, to move.",
                "The first bats drop -- wheeling through the glow, shrieking, near "
                "enough to feel the wind off their wings. The vault above is one "
                "turning wheel.",
            ),
            kill="The vault empties all at once. The swarm takes the light, and then everything else. THE END.")

    # The Pthalo-jackals: drawn by sustained loud NOISE in the lower halls (walking
    # and rummaging are fine; shouting and smashing are not).
    for hall in (memory, hounds, warriors):
        _hazard(game, hall,
                danger=lambda g, h=hall: _player_was_loud_in(g, h, _QUIET),
                warns=(
                    "Somewhere off in the halls, a yipping answers your noise -- "
                    "once, and then again, nearer.",
                    "Yellow eyes ring the doorways, unhurried. Pthalo-jackals: "
                    "cautious, clever, and done being cautious.",
                ),
                kill="The pack pours from the dark, and afterwards the tomb goes back to listening. THE END.")

    # The chimney's spores: choke you each round you're in it without a respirator.
    _hazard(game, chimney,
            danger=lambda g: not (_is_holding(g.player, "respirator") or "respirator" in g.player.worn),
            warns=(
                "Each breath comes back smaller than it went out. The spores "
                "settle on your lips and taste of orange rot.",
                "Your lungs sear; the glow below swims and doubles. The chimney's "
                "warmth has begun to feel like a mouth.",
            ),
            kill="You breathe the tomb in, and it keeps you. THE END.")

    # The Fungal Horror: while it lives, disturbing the coffin (taking, prying,
    # wearing, any racket) makes it erupt. Looking is safe -- enter, see it, and
    # back out. Cleansing the corpse (Summit) kills it and lifts this.
    _hazard(game, sphere,
            danger=lambda g: _player_was_loud_in(g, sphere, _QUIET_SPHERE),
            warns=(
                "The orange mass in the coffin turns -- all of it, at once -- "
                "toward the sound. Against the inside of the glass, something "
                "like a palm.",
            ),
            kill="The coffin does not so much open as give up. The Horror takes you in a single fold. THE END.",
            limit=2,
            gate=lambda g: not sphere.get_property("horror_dead"))

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
    "examine wreck", "talk to worry",
    "open pack", "take glowstone",
    "in", "light glowstone", "read ledger", "douse glowstone", "out",
    "north",                                                 # -> Tomb Exterior
    "examine tomb", "up", "examine ossified corpse", "down",  # Summit and back (safe)
    "north", "examine ceiling",                              # -> Hall of Youth (pitch dark; hear the bats)
    "light glowstone", "examine statues", "douse glowstone",  # light to see (bats stir), then go dark again
    "north", "talk to silas", "examine crystal lattice",     # -> Hall of Memory
    "north", "take prismatic blade", "examine cylinders",    # -> Hall of Warriors
    "east", "examine tank",                                  # -> Hall of Hounds
    "up", "open baboon jar", "examine falcon plinth",        # -> Canopic hall
]


# The full 100/100 winning run: arm up (creeping the deadly halls), lure and fell
# the Spawn to claim the jars, open the seal, climb out and burn the corpse to
# kill the Horror, then loot the now-safe Sphere with the boots and escape.
WIN_WALKTHROUGH = [
    # Loot the wreck, walk to the tomb. (The glowstone starts unlit, so it's
    # safe to carry -- never light it in the Hall of Youth. This route never
    # needs to see in the dark.)
    "open pack", "take glowstone", "north",
    "sneak east", "take blade", "take igniter", "take boots",       # Warriors: arm
    "sneak east", "take gel",                                       # Hounds: gel
    "sneak up",                                                     # -> Canopic
    "say come", "say come", "say come", "say come", "say come",     # the mantis lures the Spawn
    "attack spawn of guts with blade", "attack spawn of brain with blade",
    "take falcon jar", "take jackal jar",
    "put falcon jar on falcon plinth", "put jackal jar on jackal plinth",  # seal opens
    "sneak down", "sneak south", "sneak south",                     # Canopic -> Exterior
    "up", "burn corpse",                                            # Summit: cleanse the root
    "down", "sneak north", "sneak north", "sneak up",               # back to Canopic
    "up", "wear boots", "pry coffin",                               # Sphere: loot
    "take dagger", "take manifold box",
    "sneak down", "sneak down", "sneak south", "sneak south",       # escape -> WIN
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
    print(f"WON: {game.is_won()}   GAME_OVER: {game.is_game_over()}   "
          f"SCORE: {game.score}/{game.max_score}")
    return game


if __name__ == "__main__":
    import sys

    if "--win" in sys.argv:
        _run(WIN_WALKTHROUGH)
    elif "--walk" in sys.argv:
        _run(WALK)
    else:
        build_game().game_loop()
