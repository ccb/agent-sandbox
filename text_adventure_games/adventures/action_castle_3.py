"""Action Castle III -- "Beneath Action Castle" -- on the text_adventure_games engine.

A faithful port of the Parsely game (Action Castle III), authored the same way as its
siblings ``action_castle.py`` / ``action_castle_2.py``: a ``build_game()`` that assembles
locations / items / characters, a small ``ActionCastle3`` Game subclass holding the score
and ending logic, custom ``Action`` subclasses for the novel verbs, follower behaviors for
the party, and reaction *triggers* for the world's set-pieces.

WHAT MAKES AC3 DIFFERENT:  it's a party-based dungeon crawl. You recruit four companions
-- an elf, a dwarf, a cleric and a wizard -- each of whom unlocks an ability-verb (SHOOT
SPIDER, USE HATCHET, TURN UNDEAD, CAST SLEEP, USE WAND), and almost every obstacle is
gated on having the right companion present with the right item. It's not a single win:
the game ends when you GO NORTH home, and one of several EPILOGUES is chosen by your
progress (max 100 points). The best ending banishes the Chaos demon AND kills the cultist.

PORTED IN PHASES (this file grows over several PRs, like AC2 did):
  * Phase 1 (engine): a reusable Darkness block (text_adventure_games.blocks.Darkness).
  * Phase 2 (THIS): the world skeleton -- all rooms, exits, the three regions off the
    Crossroads hub, start inventory (a backpack container), the darkness-gated cave and
    dungeon descents, populated rooms, and the GO-NORTH-home ending stub.
  * Phases 3-5 (TODO): companions + ability-verbs; the puzzle chain (bow/sleep, spider,
    webs, baby + stew, goblin queen, pendant/crypt, ooze/lockbox/crown, slide trap); the
    endgame (javelin summons + banishes the demon, push the cultist) and scored epilogues.

Run interactively:   python action_castle_3.py
"""

from text_adventure_games import games, things, actions, blocks
from text_adventure_games.enums import Property

# ---------------------------------------------------------------------------
# Helpers (shared with the patterns used in action_castle_2.py)
# ---------------------------------------------------------------------------


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s canonical auto-reverse, so a
    pair of non-opposite exits (ENTER CAVERN in, UP out) doesn't wire a phantom
    reverse and leave two exits pointing at the same room."""
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


def _die(game, text):
    """End the game with a death/THE END message."""
    game.parser.ok(text)
    game.game_over = True
    game.game_over_description = text


def _relocate(game, character, dest_name):
    """Move *character* to the named location, dragging any followers along
    (the party travels together). Routes through the engine chokepoint."""
    dest = game.locations[dest_name]
    game.relocate(character, dest)
    game.drag_followers(character)
    return dest


def _all_held(character):
    """inventory + worn + wielded -- everything the character is holding."""
    return {**character.inventory, **character.worn, **character.wielded}


def _is_holding(character, name):
    """True if the character is carrying/wearing/wielding an item by name, or
    has it inside an open carried container (the backpack)."""
    if name in _all_held(character):
        return True
    for item in character.inventory.values():
        if name in item.accessible_contents():
            return True
    return False


def _fixture(name, description, examine_text=""):
    """A scenery item -- examinable but not gettable (springs, statues, pits)."""
    it = things.Item(name, description, examine_text or description)
    it.set_property(Property.GETTABLE, False)
    return it


def _item(name, description, examine_text=""):
    """A gettable item."""
    return things.Item(name, description, examine_text or description)


# ---------------------------------------------------------------------------
# Game subclass: scoring + ending
# ---------------------------------------------------------------------------


class ActionCastle3(games.Game):
    """The adventure ends by GOing NORTH home; an epilogue is chosen by progress.
    The best ending banishes the demon AND kills the Chaos cultist."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        self.score = 0
        # Scoring is event-based (rulebook page 28), not per-location; total 100.
        self.max_score = 100
        self._scored_keys = set()

    def award(self, key, points, msg=None):
        """Add *points* once per *key* (idempotent), optionally announcing *msg*."""
        if key in self._scored_keys:
            return
        self._scored_keys.add(key)
        self.score += points
        if msg:
            self.parser.ok(msg)

    def is_won(self) -> bool:
        # The "TO BE CONTINUED!" ending: the demon banished and the cultist dead.
        p = self.player
        return bool(
            p.get_property("banished_demon") and p.get_property("killed_cultist")
        )


# ---------------------------------------------------------------------------
# Custom actions
# ---------------------------------------------------------------------------


class GoHome(actions.Action):
    """Return home up the northern road, ending the adventure. The rulebook asks
    "Are you sure?"; we pose that as a yes/no prompt (engine #110), and on YES we
    relocate to Home, where an arrival trigger reads the epilogue."""

    ACTION_NAME = "go home"
    ACTION_DESCRIPTION = "Return home up the northern road (ends the adventure)"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.game.player

    def check_preconditions(self) -> bool:
        if (
            self.character.location is None
            or self.character.location.name != "Crossroads"
        ):
            self.parser.fail("The road home lies north of the Crossroads.")
            return False
        return True

    def apply_effects(self):
        from text_adventure_games import Prompt

        self.parser.ok("Are you sure you want to return home and end your adventure?")
        self.game.pose_prompt(
            Prompt(
                text="Return home and end your adventure?",
                options={"yes": "confirm home", "no": "stay"},
                speaker="narrator",
            )
        )


class ConfirmHome(actions.Action):
    """The YES branch of GoHome's prompt: go home for good."""

    ACTION_NAME = "confirm home"
    ACTION_DESCRIPTION = "Confirm returning home"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.game.player

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        self.parser.ok("You set off up the northern road toward home.")
        _relocate(self.game, self.character, "Home")  # arrival trigger -> epilogue


class Stay(actions.Action):
    """The NO branch: think better of it and stay."""

    ACTION_NAME = "stay"
    ACTION_DESCRIPTION = "Decide not to go home yet"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        return True

    def apply_effects(self):
        self.parser.ok("You decide your adventure isn't over yet.")


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> ActionCastle3:
    L = things.Location

    # --- Locations ---------------------------------------------------------
    # Surface
    crossroads = L(
        "Crossroads",
        "You stand at a crossroads. The ruins of the once-glorious Action Castle lie to "
        "the east. A dark forest looms to the west. The road north will take you home.",
    )
    dark_forest = L(
        "Dark Forest",
        "You stand at the edge of a dark forest. Smoke rises to the west. A trail leads "
        "south. Through the trees you spy a shadowy figure watching your every move.",
    )
    bandit_camp = L(
        "Bandit Camp",
        "Through the trees you spy a clearing where a group of bandits has made camp. A "
        "stew pot hangs over their campfire.",
    )
    cavern_entrance = L(
        "Cavern Entrance",
        "You come across an outcrop of mossy boulders. A gap between the rocks leads down "
        "into darkness. A natural spring bubbles up from the ground nearby.",
    )
    # Caves
    dark_cavern = L(
        "Dark Cavern",
        "You emerge into a large cavern. A steep slope leads back to the surface. To the "
        "east is a cramped passage. You hear soft mewling cries from a crack in the wall.",
    )
    fissure = L(
        "Fissure",
        "You're barely able to squeeze in. Wedged deep inside is a bundle wrapped in rags.",
    )
    mushroom_garden = L(
        "Mushroom Garden",
        "You are in a wide chamber carpeted with purple-spotted cave mushrooms. To the "
        "south is a tunnel choked with cobwebs. A cramped passage leads west.",
    )
    spider_lair = L(
        "Spider Lair",
        "The tunnel ends in a large web that spans the western exit, beyond which is a "
        "sheer drop-off. A narrow tunnel leads north. A pair of bodies hangs from the ceiling.",
    )
    deep_ravine = L(
        "Deep Ravine",
        "Steps carved into the rock lead down from the eastern tunnel into a deep ravine. "
        "A flock of leathery-winged creatures feeds on the body of a large spider.",
    )
    goblin_caves = L(
        "Goblin Caves",
        "A maze of twisting passages, switchbacks and flooded grottoes. The air smells of "
        "goblins.",
    )
    throne_room = L(
        "Throne Room",
        "Balanced atop a pile of treasure is an ornate gold throne. On it sits a diminutive "
        "goblin dressed in furs, feathers and looted jewelry.",
    )
    # Castle / temple
    castle_ruins = L(
        "Castle Ruins",
        "All that's left of Action Castle is this courtyard, a lonely tower and a few "
        "crumbling walls. A rickety stairway leads up to the tower; a dark stairwell "
        "descends to the dungeon.",
    )
    wizard_tower = L(
        "Wizard's Tower",
        "The tower is cluttered with old books. A wizard is here, peering through a telescope.",
    )
    dungeon = L(
        "Dungeon",
        "You enter the dungeon. A dark corridor runs east to west. A stone stair leads up. "
        "There are a few dark and dingy cells here.",
    )
    vault = L(
        "Vault",
        "A vaulted chamber filled with broken crates and empty shelves, looted long ago. "
        "A large stone statue stands here.",
    )
    dark_corridor = L(
        "Dark Corridor",
        "A long, dark corridor. At the far end is an iron door covered in spikes. There "
        "are some human remains here.",
    )
    torture_chamber = L(
        "Torture Chamber",
        "A blood-spattered chamber. An iron maiden stands in the corner. A man is tied "
        "down, stretched across a wooden table.",
    )
    sanctum = L(
        "Sanctum",
        "The inner sanctum of a hidden temple. A large tome rests on a lectern. A spiral "
        "staircase leads up. You smell burning incense to the west.",
    )
    chaos_chapel = L(
        "Chaos Chapel",
        "The chapel is lit by flickering oil lamps, thick with incense. In the center is a "
        "large pit ringed with spikes. To the south is the crypt.",
    )
    crypt = L(
        "Crypt",
        "A long, narrow chamber adorned with skulls and bones. Many skeletal bodies are "
        "entombed here, still clad in mouldering armor.",
    )
    # The road home -- arriving here ends the game (see the epilogue trigger).
    home = L(
        "Home", "The road winds north, back toward your village and the life you knew."
    )

    # --- Connections -------------------------------------------------------
    # Surface hub
    crossroads.add_connection(
        "east", castle_ruins
    )  # auto: castle_ruins west -> crossroads
    crossroads.add_connection(
        "west", dark_forest
    )  # auto: dark_forest east -> crossroads
    _one_way(
        crossroads, "north", home
    )  # GoHome confirms first; this is the literal road
    dark_forest.add_connection("south", cavern_entrance)
    dark_forest.add_connection("west", bandit_camp)
    # Caves (enter cavern / enter fissure are custom one-way exits; UP/OUT lead back)
    _one_way(cavern_entrance, "enter cavern", dark_cavern)
    _one_way(dark_cavern, "up", cavern_entrance)
    dark_cavern.add_connection("east", mushroom_garden)
    _one_way(dark_cavern, "enter fissure", fissure)
    _one_way(fissure, "out", dark_cavern)
    mushroom_garden.add_connection("south", spider_lair)
    spider_lair.add_connection("west", deep_ravine)  # web-blocked (TODO Phase 4)
    _one_way(deep_ravine, "down", goblin_caves)
    _one_way(goblin_caves, "north", deep_ravine)
    goblin_caves.add_connection("east", throne_room)
    # Castle / temple
    castle_ruins.add_connection("up", wizard_tower)
    castle_ruins.add_connection("down", dungeon)  # darkness-gated
    dungeon.add_connection("west", vault)
    dungeon.add_connection("east", dark_corridor)
    dark_corridor.add_connection("east", torture_chamber)  # door-gated (TODO Phase 4)
    torture_chamber.add_connection("down", sanctum)  # iron-maiden-gated (TODO Phase 4)
    sanctum.add_connection("west", chaos_chapel)
    chaos_chapel.add_connection("south", crypt)

    # --- Darkness gates (engine Darkness block) ----------------------------
    # You can't enter the caverns or descend to the dungeon without a lit lantern.
    cavern_entrance.add_block("enter cavern", blocks.Darkness(cavern_entrance))
    castle_ruins.add_block("down", blocks.Darkness(castle_ruins))

    # --- World items -------------------------------------------------------
    bandit_camp.add_item(
        _fixture(
            "pot",
            "a stew pot",
            "It's empty now, but you could cook a meal if you had ingredients.",
        )
    )
    bandit_camp.add_item(
        _fixture(
            "bow",
            "a fine elvish bow",
            "A fine elvish bow -- strong, supple and light as a feather. A bandit is admiring it.",
        )
    )
    cavern_entrance.add_item(
        _fixture(
            "spring",
            "a natural spring",
            "The water looks clean and clear, but looks can be deceiving.",
        )
    )
    fissure.add_item(
        _item(
            "bundle",
            "a bundle wrapped in rags",
            "A wrinkly green face with yellow catlike eyes and a tuft of red hair. It's a baby goblin, probably abandoned.",
        )
    )
    mushroom_garden.add_item(
        _fixture(
            "mushrooms",
            "purple-spotted cave mushrooms",
            "The purple-spotted mushrooms are carefully laid out in rows.",
        )
    )
    spider_lair.add_item(
        _fixture(
            "web",
            "a thick spiderweb",
            "A spiderweb blocks the passage west. A large wolf spider sits in the center, venom dripping from its fangs.",
        )
    )
    spider_lair.add_item(
        _fixture(
            "bodies",
            "two cocooned bodies",
            "A desiccated goblin corpse and a freshly caught dwarf wrapped in spider silk. The dwarf struggles weakly.",
        )
    )
    wizard_tower.add_item(
        _fixture(
            "telescope", "a brass telescope", "A telescope pointed at the night sky."
        )
    )
    wizard_tower.add_item(
        _fixture(
            "books",
            "shelves of occult tomes",
            "A dizzying array of occult tomes. One you can read is a journal: Ecology of the Ooze.",
        )
    )
    wizard_tower.add_item(
        _item(
            "wand",
            "an icy wand",
            "Carved from a piece of ice and covered in runes. One rune still glows with dim blue light.",
        )
    )
    dungeon.add_item(
        _fixture(
            "cells",
            "dingy cells",
            "The dirty cells are empty save for straw bedding strewn about.",
        )
    )
    vault.add_item(
        _fixture(
            "statue",
            "a large stone statue",
            "A stern figure clad in armor, its fist raised to the heavens. Some fingers are broken off, as if something was pried loose.",
        )
    )
    dark_corridor.add_item(
        _fixture(
            "remains",
            "grisly human remains",
            "A pair of severed arms clutching a small metal lockbox. The stone underneath is stained and corroded.",
        )
    )
    torture_chamber.add_item(
        _fixture(
            "iron maiden",
            "a rusting iron maiden",
            "A rusting metal sarcophagus cast in the shape of a young woman.",
        )
    )
    sanctum.add_item(
        _fixture(
            "tome",
            "a large leather-bound tome",
            "Opened to an illustration of an armored man throwing a lightning bolt at a massive horned demon.",
        )
    )
    chaos_chapel.add_item(
        _fixture(
            "pit", "a spiked pit", "It's deep and dark; you cannot see the bottom."
        )
    )
    crypt.add_item(
        _fixture(
            "skeletal bodies",
            "armored skeletons",
            "One of the skeletons grips a spell book in its bony hands.",
        )
    )

    # --- Characters --------------------------------------------------------
    player = things.Character(
        name="adventurer",
        description="a brave adventurer delving beneath Action Castle",
        persona="I am an adventurer seeking glory beneath the ruins of Action Castle.",
    )

    # The four would-be companions (recruitment is Phase 3). Placed with their
    # canned lines so EXAMINE/TALK already work.
    elf = things.Character(
        "elf",
        "a green-cloaked elf with pointed ears",
        "I am an elf who fled bandits in the ruins.",
    )
    elf.talk_text = '"A group of bandits ambushed me in the ruins. I dropped my bow during my escape."'
    elf.location = None

    wizard = things.Character(
        "wizard",
        "an old wizard in star-spangled blue robes",
        "I am a wizard who has misplaced his spell book.",
    )
    wizard.talk_text = '"Have you come across a spell book in your travels? I seem to have misplaced mine!"'

    dwarf = things.Character(
        "dwarf",
        "a stout, red-bearded dwarf, wounded and poisoned",
        "I am a dwarf who was searching for gold when the spider ambushed me.",
    )
    dwarf.talk_text = '"I was searching for gold and gems when the spider ambushed me!"'

    cleric = things.Character(
        "man",
        "a tortured man with a lightning-bolt sigil on his tabard",
        "I am a cleric of the Lord of Law, taken and tortured by the cultists.",
    )
    cleric.talk_text = '"Water..."'

    spider = things.Character(
        "spider",
        "a wolf spider the size of a small horse",
        "I am a great wolf spider, nearly camouflaged against the rock.",
    )
    queen = things.Character(
        "goblin queen",
        "the goblin queen, in looted finery",
        "I am the goblin queen. Tribute!",
    )
    queen.talk_text = 'The goblin queen shrieks, "Tribute!"'

    dark_forest.add_character(elf)
    wizard_tower.add_character(wizard)
    spider_lair.add_character(dwarf)
    spider_lair.add_character(spider)
    torture_chamber.add_character(cleric)
    throne_room.add_character(queen)

    # --- Player start inventory --------------------------------------------
    # The rulebook starts you with a backpack containing a lantern, dagger,
    # lockpicks and a waterskin. The lantern is carried in hand so it can be lit
    # immediately; the rest ride in the pack.
    #
    # TODO (engine, Phase 3 prelude): GET only reaches holders sitting in the
    # room, not the player's own carried containers, so you can't yet pull the
    # dagger/lockpicks/waterskin out of the pack. AC3 leans on that ("the party
    # carries a pack and pulls gear out"), so the next reusable engine feature is
    # letting GET/scope reach into carried open containers -- then the lantern
    # can live in the pack too and DROP BACKPACK (the fissure puzzle) bites.
    backpack = _item("backpack", "a sturdy leather backpack").make_container()
    lantern = _item("lantern", "a brass lantern", "A brass lantern, currently unlit.")
    lantern.set_property(Property.FLAMMABLE, True)
    lantern.set_property(Property.IS_LIT, False)
    backpack.add_item(
        _item("dagger", "a simple dagger", "A plain but serviceable dagger.")
    )
    backpack.add_item(
        _item("lockpicks", "a set of lockpicks", "A slim set of lockpicks.")
    )
    backpack.add_item(
        _item("waterskin", "a waterskin", "A leather waterskin. It's empty.")
    )

    # --- Assemble ----------------------------------------------------------
    characters = [elf, wizard, dwarf, cleric, spider, queen]
    custom_actions = [GoHome, ConfirmHome, Stay]
    game = ActionCastle3(crossroads, player, characters, custom_actions)
    player.add_to_inventory(backpack)
    player.add_to_inventory(lantern)

    # Going north ends the adventure: arriving Home reads the epilogue.
    def epilogue(g):
        # Phase 5 will branch this by score/flags; for now, one stub ending.
        g.award("home", 10)
        g.parser.ok(
            "You return to your village. (Scored epilogues arrive in a later phase.)  "
            f"THE END.  (Score: {g.score}/{g.max_score})"
        )
        g.game_over = True
        g.game_over_description = "You returned home."

    game.add_trigger(
        "epilogue_home",
        lambda g: g.player.location is not None and g.player.location.name == "Home",
        epilogue,
        repeatable=False,
    )

    return game


# ---------------------------------------------------------------------------
# Skeleton navigation smoke-path (a real walkthrough comes with the puzzles)
# ---------------------------------------------------------------------------

WALKTHROUGH_SKELETON = [
    "light lantern",  # carried in hand from the start
    "west",  # Crossroads -> Dark Forest
    "south",  # -> Cavern Entrance
    "enter cavern",  # darkness gate: passable now the lantern is lit
    "east",  # Dark Cavern -> Mushroom Garden
    "west",  # back to Dark Cavern
    "up",  # -> Cavern Entrance
    "north",  # -> Dark Forest
    "east",  # -> Crossroads
    "east",  # -> Castle Ruins
    "down",  # darkness gate -> Dungeon
    "up",  # -> Castle Ruins
    "up",  # -> Wizard's Tower
    "down",  # -> Castle Ruins
    "west",  # -> Crossroads
    "go home",
    "yes",  # confirm -> Home -> epilogue
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
        _run(WALKTHROUGH_SKELETON)
    else:
        build_game().game_loop()
