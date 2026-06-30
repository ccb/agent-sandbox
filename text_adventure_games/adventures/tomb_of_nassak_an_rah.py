"""The Tomb of Nassak An-Rah -- a Vaults of Vaarn parser adventure.

A Zork / Action Castle homage set in the Blue Ruins of Vaarn. See the design spec
at docs/design/tomb-of-nassak-an-rah.md.

PHASE 1 (this file): the map + atmosphere only -- eight navigable, examinable
locations, the nameless scavenger, a glowstone to see by. No puzzles, threats,
reactions, scoring, or deaths yet; those arrive in later phases. The goal here is
a world you can walk and read.

    Run:  python -m text_adventure_games.adventures.tomb_of_nassak_an_rah [--walk]
"""

from text_adventure_games import games, things, actions, blocks, reactions
from text_adventure_games.enums import Property


def _die(game, message):
    """End the game with a death line (the tomb is deadly)."""
    game.parser.ok(message)
    game.game_over = True
    game.game_over_description = message


# Actions a deadly room's listeners treat as silent -- everything else is "noise".
_QUIET = {"sneak", "examine", "describe", "inventory", "wait", "get", "drop", "put", "talk"}
# In the zero-g Burial Sphere even sneaking stirs the fungus; only looking is safe.
_QUIET_SPHERE = {"examine", "describe", "inventory"}


def _is_holding(character, name):
    return name in character.inventory


def _deadly_room(game, room, message, quiet=_QUIET, gate=None):
    """Register a death: while the player stands in *room*, any noisy act associated
    with it this round is fatal -- a noisy arrival (a plain ``go``, not a ``sneak``)
    or a loud action done there (``say``/``break``/``attack``). Quiet acts are safe.
    Only the *player's* own actions count, so a creature lured through the room
    doesn't set it off. ``gate`` (a predicate) can switch the danger off -- e.g. the
    Burial Sphere stops being lethal once the Fungal Horror is dead."""

    def condition(g):
        if g.player.location is not room:
            return False
        if gate is not None and not gate(g):
            return False
        for e in g.events[g._round_event_start :]:
            if e.actor != g.player.name or e.action in quiet:
                continue
            payload = e.payload or {}
            if payload.get("dest") == room.name or payload.get("location") == room.name:
                return True
        return False

    game.add_trigger(
        f"deadly:{room.name}", condition, lambda g: _die(g, message), repeatable=True
    )


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
                "You'd need something that burns and a flame to light it -- gel, and an igniter."
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
                "The coffin floats in the dead centre, out of reach -- you flail in "
                "the zero gravity and get nowhere. You need purchase. (Magnetic boots?)"
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
            "The stair up is barred by a lattice of red crystal -- it will yield "
            "only to the Autarch's missing jars, each on the plinth of its kind.",
        )
        self.canopic = canopic

    def is_blocked(self) -> bool:
        return not self.canopic.get_property("seal_open")


class ChokedChimney(blocks.Block):
    """The fungal chimney between the Summit and the Burial Sphere is too choked
    with spores to pass without breathing protection -- so the only way into the
    Sphere is the front stair (the canopic seal). (A respirator route is a future
    extension.)"""

    def __init__(self):
        super().__init__(
            "The fungal chimney",
            "The chimney is packed with orange spores -- you'd choke before you were "
            "halfway. You'd need breathing protection to brave it.",
        )

    def is_blocked(self) -> bool:
        return True


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
    # --- The eight locations -------------------------------------------------
    exterior = things.Location(
        "Tomb Exterior",
        "You stand in the phthalo sands beneath a dying red sun. Before you rises "
        "the Tomb of Nassak An-Rah: a thirty-foot slab of azure stone, three carved "
        "faces staring across the wastes, the whole edifice webbed in creeping "
        "orange fungus. The western face is the dead Autarch as a young boy; the "
        "eastern, a helmed warrior. Far up, a third face -- an old man -- turns to "
        "the sky, orange tendrils weeping from its open mouth. Each mouth is a door.",
    )
    youth = things.Location(
        "Hall of Youth",
        "Sand-scoured walls glow a faint blue. Statues crowd the chamber, depicting "
        "the birth and boyhood of Nassak An-Rah, swaddled and adored. Something "
        "rustles, unseen, in the dark of the high ceiling.",
    )
    memory = things.Location(
        "Hall of Memory",
        "Glinting lattices of crystal climb the walls -- the favoured memories of "
        "the Autarch, frozen in lazulite. The light they throw is cold and slow.",
    )
    hounds = things.Location(
        "Hall of Hounds",
        "A wall of thick plexiglas holds back a tank of luminous embalming gel. "
        "Suspended in it: ten of An-Rah's hunting hounds, black and spindly, threaded "
        "with cyborg augmentations, perfectly preserved.",
    )
    warriors = things.Location(
        "Hall of Warriors",
        "A dim, uneven floor. Four tall plexiglas cylinders stand here, each holding "
        "a mummified guard in Autarchy armour -- and each laced through with veins of "
        "orange fungus.",
    )
    canopic = things.Location(
        "Hall of the Canopic Jars",
        "Pentagonal walls of dressed stone. Five plinths ring a central staircase "
        "that climbs into shadow -- but the stair is barred by a seal of red crystal. "
        "Two of the plinths stand empty, lit from within by a crimson light.",
    )
    sphere = things.Location(
        "Burial Sphere of Nassak An-Rah",
        "A great spherical chamber, its walls carved with funeral prayers. In the "
        "dead centre floats the Autarch's coffin -- a glass anti-entropy sphere, now "
        "clouded and invaded by a roiling orange mass. There is no gravity here; dust "
        "and bone-chips drift in the still air.",
    )
    summit = things.Location(
        "The Summit",
        "Windy and high, the desert spread out blue and endless below. An ossified "
        "corpse sits here in the lotus position, mummified mid-meditation, orange "
        "fungus fronding from its eyes and open mouth and down into the chimney that "
        "drops through the tomb's crown.",
    )

    # --- Connections (see spec §3) ------------------------------------------
    # Three entrances off the Exterior: the western (child) mouth, the eastern
    # (warrior) mouth, and a climb to the summit. Cardinal links auto-wire their
    # reverse; non-cardinal ones (climb, chimney) are set both ways by hand.
    # (Only canonical directions -- n/s/e/w/up/down/in/out -- auto-route from a
    # bare word; the flavor verbs "climb"/"chimney" arrive with custom actions in a
    # later phase. The room prose names which mouth lies which way.)
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

    # The fungal chimney joins the Sphere's crown to the Summit -- but it's choked
    # with spores (impassable in v1), so the Sphere is reached only by the front
    # stair (the canopic seal). Both directions are blocked.
    summit.add_connection("in", sphere)           # auto: sphere out -> summit
    summit.add_block("in", ChokedChimney())
    sphere.add_block("out", ChokedChimney())

    # --- Atmosphere: examinable scenery (hooks for later phases) -------------
    _scenery(exterior, "tomb", "the Tomb of Nassak An-Rah",
             "Three faces in azure stone -- boy, warrior, and sky-gazing elder -- "
             "their mouths gaping as doors. Orange fungus mortars every seam.")
    _scenery(youth, "statues", "blue statues of the boy-Autarch",
             "Nassak An-Rah as an infant, a child, a youth -- each rendered with "
             "unsettling tenderness in cold blue stone.")
    _scenery(memory, "crystal lattice", "lattices of memory-crystal",
             "Lazulite crystals knit across the walls. One holds the Autarch's "
             "embalming: the baboon took his lungs, the human his liver, the mantis "
             "his eyes; the falcon was given his intestines, and the jackal -- "
             "strangely -- his brain.")
    _scenery(hounds, "tank", "a plexiglas tank of embalming gel",
             "Ten cyborg hounds hang in luminous, flammable gel behind thick "
             "plexiglas. Collectors would pay in salt and water for these.")
    _scenery(warriors, "cylinders", "four plexiglas burial cylinders",
             "Each holds a guard-mummy in Autarchy armour, prismatic blade at rest, "
             "the glass fogged from within by threads of orange fungus.")
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
        "A plinth carved with a falcon's likeness, lit crimson and empty -- it waits "
        "for the jar that holds the Autarch's intestines.",
    ).make_surface(capacity=1)
    falcon_plinth.set_property("gettable", False)
    jackal_plinth = things.Item(
        "jackal plinth", "an empty plinth carved with a jackal",
        "A plinth carved with a jackal's likeness, lit crimson and empty -- it waits "
        "for the jar that holds the Autarch's brain.",
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
        "interior a slow orange churn. The Autarch's bones -- and his Exotica -- "
        "drift sealed within. You'd have to PRY it open.")
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
        "An octopus of orange fungus and grave-cured intestine, the falcon canopic "
        "jar worn on top like a hat. It sways toward any sound."
    )
    spawn_guts.add_to_inventory(falcon_jar)
    spawn_brain = things.Character(
        "spawn of brain", "a fungal spawn wearing a jackal-headed jar",
        "I am what is left of the Autarch's thoughts.",
    )
    spawn_brain.examine_text = (
        "A fungal brain that walks on two tiny legs, the jackal canopic jar worn as "
        "a hat. It twitches toward every noise."
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
        "Heavy Autarchy boots that clamp to metal -- the way to keep your footing "
        "in a zero-gravity chamber.",
    )
    boots.set_property(Property.WEARABLE, True)
    boots.set_property("wear_slot", "feet")
    boots.add_alias("boots")
    warriors.add_item(igniter)
    warriors.add_item(boots)
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
        "A gaunt synthetic in fuligin-yellow robes, fingertips tipped with cranial "
        "bores, drawing memory from the lattice in slow bright threads. He does not "
        "look up."
    )
    silas.talk_text = (
        'Silas speaks without turning. "Scavenger. Two of the Autarch\'s organs walk '
        "these halls -- his guts and his brain, sprouted on fungus and each wearing "
        "the canopic jar it was sealed in. Take the jars; set each on the plinth of "
        'its kind; the seal will yield. And step softly -- the dead here listen."'
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
    glowstone = things.Item(
        "glowstone", "a dim glowstone",
        "A shard of cold blue glowstone, just bright enough to see by.",
    )
    player.add_to_inventory(glowstone)

    game = TombGame(
        exterior, player, characters=[silas, spawn_guts, spawn_brain],
        custom_actions=[Sneak, BurnCorpse, PryCoffin],
    )
    game.max_score = 100

    # The Spawn home in on noise (DrawnToSound); the mantis-headed jar amplifies
    # any noise in the Canopic hall into a luring song. Make a racket there and the
    # Spawn come to you -- the safe place to fight them (the halls are deadly).
    game.add_reaction(mantis_jar, FungalSong())
    game.add_reaction(spawn_guts, reactions.DrawnToSound())
    game.add_reaction(spawn_brain, reactions.DrawnToSound())

    # The tomb listens. A noisy move (a plain `go`) or a loud act (`say`/`break`/
    # `attack`) is fatal in the lower halls and the Burial Sphere; creep, and act
    # quietly. (Lethality is a playtest dial.)
    _deadly_room(game, youth,
                 "Your noise wakes the roosting bats; they boil down in a shrieking "
                 "cloud and tear you apart in the dark. THE END.")
    for hall in (memory, hounds, warriors):
        _deadly_room(game, hall,
                     "Your noise carries. Pthalo-jackals pour from the shadows, drag "
                     "you down, and feed. THE END.")
    _deadly_room(game, sphere,
                 "At the first stir of movement the orange mass erupts from the "
                 "coffin -- the Fungal Horror -- and drowns you in acid. THE END.",
                 quiet=_QUIET_SPHERE,
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
    "examine tomb", "up", "examine ossified corpse", "down",  # Summit and back (safe)
    "sneak north", "examine statues",                        # -> Hall of Youth (creep past the bats)
    "sneak north", "talk to silas", "examine crystal lattice",  # -> Hall of Memory
    "sneak north", "take prismatic blade", "examine cylinders",  # -> Hall of Warriors
    "sneak east", "examine tank",                            # -> Hall of Hounds
    "sneak up", "open baboon jar", "examine falcon plinth",  # -> Canopic hall
]


# The full 100/100 winning run: arm up (creeping the deadly halls), lure and fell
# the Spawn to claim the jars, open the seal, climb out and burn the corpse to
# kill the Horror, then loot the now-safe Sphere with the boots and escape.
WIN_WALKTHROUGH = [
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
