"""The Tomb of Nassak An-Rah -- a Vaults of Vaarn parser adventure.

A Zork / Action Castle homage set in the Blue Ruins of Vaarn. See the design spec
at docs/design/tomb-of-nassak-an-rah.md.

PHASE 1 (this file): the map + atmosphere only -- eight navigable, examinable
locations, the nameless scavenger, a glowstone to see by. No puzzles, threats,
reactions, scoring, or deaths yet; those arrive in later phases. The goal here is
a world you can walk and read.

    Run:  python -m text_adventure_games.adventures.tomb_of_nassak_an_rah [--walk]
"""

from text_adventure_games import games, things, actions, blocks


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

    # The fungal chimney joins the Sphere's crown to the Summit: go "in" the
    # chimney from the summit to descend, "out" to climb back up.
    summit.add_connection("in", sphere)           # auto: sphere out -> summit

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
    # The three present jars sit on their plinths -- examinable clues to which
    # organ each head holds (the empty plinths name the two that are missing).
    _scenery(canopic, "baboon jar", "a baboon-headed canopic jar",
             "The baboon-headed jar holds the Autarch's lungs, sealed on its plinth.")
    _scenery(canopic, "human jar", "a human-headed canopic jar",
             "The human-headed jar holds the Autarch's liver, sealed on its plinth.")
    _scenery(canopic, "mantis jar", "a mantis-headed canopic jar",
             "The mantis holds the eyes -- but this jar is split and fungal, a "
             "misshapen orange head budding from the crack. It is unnervingly still.")

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
    _scenery(sphere, "coffin", "the Autarch's anti-entropy coffin",
             "A clouded glass sphere at the chamber's heart, its preserving field "
             "failing, its interior a slow orange churn. An-Rah's bones hang within.")
    _scenery(summit, "ossified corpse", "an ossified mystic",
             "A corpse turned to stone mid-meditation, orange fungus weeping from its "
             "eyes and mouth -- the wellspring, it seems, of all the rot below.")

    # The two MISSING jars. In the finished game the Spawn wear these (Phase 3
    # relocates them onto the creatures and gates them behind a fight); for now
    # they lie loose in the lower halls so the seal puzzle is solvable on its own.
    falcon_jar = things.Item(
        "falcon jar", "a falcon-headed canopic jar",
        "A sealed jar with a falcon's head -- it holds the Autarch's intestines.",
    )
    jackal_jar = things.Item(
        "jackal jar", "a jackal-headed canopic jar",
        "A sealed jar with a jackal's head -- it holds the Autarch's brain.",
    )
    warriors.add_item(falcon_jar)   # TODO P3: worn by the Spawn of An-Rah's Guts
    hounds.add_item(jackal_jar)     # TODO P3: worn by the Spawn of An-Rah's Brain

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

    game = TombGame(exterior, player, characters=[silas])

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

    game.add_trigger("canopic_seal", _seal_solved, _open_seal, repeatable=False)
    return game


# ---------------------------------------------------------------------------
# A smoke tour (--walk): traverse every room and read it. No win yet.
# ---------------------------------------------------------------------------

WALK = [
    "examine tomb", "up", "examine ossified corpse",   # -> Summit
    "in",                                              # -> Burial Sphere (down the chimney)
    "examine coffin", "down",                          # -> Canopic (the aperture)
    "examine falcon plinth", "examine baboon jar", "down",  # -> Memory
    "examine crystal lattice", "south",                # -> Youth
    "examine statues", "west",                         # -> Hounds
    "examine tank", "west",                            # -> Warriors
    "examine cylinders",
]


def _run(commands):
    game = build_game()
    game.parser.parse_command("look")
    for cmd in commands:
        print(f"\n>>> {cmd}")
        game.do_command(cmd)
    print("\n" + "=" * 60)
    print(f"Scaffold tour complete. Rooms reachable; nothing lethal yet.")
    return game


if __name__ == "__main__":
    import sys

    if "--walk" in sys.argv:
        _run(WALK)
    else:
        build_game().game_loop()
