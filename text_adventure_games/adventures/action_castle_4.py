"""Action Castle IV -- "Escape from Action Castle" -- on the text_adventure_games engine.

A port of the Parsely game (Action Castle IV), authored like its siblings
``action_castle{,_2,_3}.py``: a ``build_game()`` assembling locations / items /
characters, a small ``ActionCastle4`` Game subclass with the score + endings, custom
``Action`` subclasses for the novel verbs, and reaction *triggers* for set-pieces.

THE STORY: the Princess escapes her tower and rides off into a road-trip. A mostly
linear chain -- Tower -> Guardroom -> Gardens/Drawbridge -> Down by the River (get a
horse) -> Old Woods/Deep Woods (a poacher + a deer) -> Clearing -> Ranch / Roadhouse
-> a biker bar. Two winning endings: settle as a Rancher (+40) or ride off down the
Highway (+50, the 100-point best run); plus several dead-ends.

PORTED IN SLICES (this is the worked example in docs/converting-parsely-games.md):
  * Slice 1 (engine): a reusable vehicle/mount feature (the horse + motorcycle ride on it).
  * Slice 2 (THIS): the world skeleton -- rooms, exits, items, characters, start state
    (the princess wears a gown + tiara), the vehicle-gated woods exit, and the ending stubs.
  * Slices 3-5 (TODO): the full-fidelity tower escape (dagger -> cut hair -> rope -> climb
    out, the guard-catch soft-lock, slipper dead-ends); the horse (tame with apple/brush)
    + poacher/deer; the ranch + roadhouse "Wade sent me" gate + bar brawl -> keys; the two
    scored endings + epilogue.

Run interactively:   python action_castle_4.py
"""

from text_adventure_games import games, things, actions, blocks
from text_adventure_games.enums import Property

# ---------------------------------------------------------------------------
# Helpers (same kit as the other ports)
# ---------------------------------------------------------------------------


def _one_way(frm, direction, to):
    """A connection with no auto-reverse (for diagonals / non-opposite pairs)."""
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


def _die(game, text):
    game.parser.ok(text)
    game.game_over = True
    game.game_over_description = text


def _relocate(game, character, dest_name):
    dest = game.locations[dest_name]
    game.relocate(character, dest)
    game.drag_followers(character)
    return dest


def _all_held(character):
    return {**character.inventory, **character.worn, **character.wielded}


def _is_holding(character, name):
    if name in _all_held(character):
        return True
    for item in character.inventory.values():
        if name in item.accessible_contents():
            return True
    return False


def _fixture(name, description, examine_text=""):
    it = things.Item(name, description, examine_text or description)
    it.set_property(Property.GETTABLE, False)
    return it


def _item(name, description, examine_text=""):
    return things.Item(name, description, examine_text or description)


# ---------------------------------------------------------------------------
# Game subclass: scoring + endings
# ---------------------------------------------------------------------------


class ActionCastle4(games.Game):
    """Ends by settling as a Rancher (+40) or riding off down the Highway (+50,
    the best run). `is_won` reports the Highway ending once it's reached."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        self.score = 0
        self.max_score = 100  # rulebook page 19 scoring table
        self._scored_keys = set()

    def award(self, key, points, msg=None):
        if key in self._scored_keys:
            return
        self._scored_keys.add(key)
        self.score += points
        if msg:
            self.parser.ok(msg)

    def is_won(self) -> bool:
        # The best ending: out on the Highway. Gated on game_over so it reports
        # the final state rather than ending the game early (is_game_over reads
        # is_won). The Rancher ending is a "good" finish but not the max run.
        return bool(self.game_over and self.player.get_property("rode_the_highway"))


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> ActionCastle4:
    L = things.Location

    # --- Locations ---------------------------------------------------------
    tower = L(
        "Tower",
        "You're all alone in your tower. A window overlooks the gardens. An armoire "
        "and a dresser stand by your bed. A heavy door leads out.",
    )
    tower_stairs = L(
        "Tower Stairs",
        "You're on the tower steps. A wooden door leads to your chambers.",
    )
    guardroom = L(
        "Guardroom",
        "The castle guardroom. A doorway leads west out of the castle; stairs lead up "
        "to the tower. There's an army cot and a footlocker here.",
    )
    gardens = L(
        "Gardens",
        "The air is fresh and the sun is shining -- rosebushes and fruit trees, and "
        "watermelon vines near the tower's base. A braid of hair hangs from the window. "
        "The drawbridge is south.",
    )
    drawbridge = L(
        "Drawbridge",
        "A bridge spans the river. A path heads north to the gardens and south along "
        "the river. The Old Woods lie west.",
    )
    river = L(
        "Down by the River",
        "Down by the river, a horse is tethered to a tree and a young man paints at an "
        "easel. The drawbridge is north.",
    )
    old_woods = L(
        "Old Woods",
        "You're in the Old Woods. The game warden's shack is here. You see a deer!",
    )
    old_shack = L("Old Shack", "The game warden's shack. There's a crossbow here.")
    deep_woods = L(
        "Deep Woods",
        "Primordial forest. The deer is here, alert -- and a cloaked figure stalks it "
        "through the trees.",
    )
    clearing = L(
        "Clearing",
        "A clearing beyond the kingdom's borders, cleared for grazing. A dirt road runs "
        "west; an old ranch lies to the southwest.",
    )
    ranch = L(
        "Ranch",
        "The Double-Deuce Ranch: fenced pasture, an old farmhouse, a melon patch. An "
        "old rancher sits here on horseback.",
    )
    dirt_road = L(
        "Dirt Road",
        "A long dirt road running north to south. There's a signpost here.",
    )
    roadhouse = L(
        "Roadhouse",
        "Outside a building with a flashing neon sign. A lanky man lounges by the door. "
        "Motorcycles and pickup trucks are parked out front. A highway runs east-west; a "
        "dirt road leads south.",
    )
    breakpoint = L(
        "The Breakpoint",
        "The Breakpoint Bar & Grill -- rowdy and packed with bikers and ranchers. There's "
        "a jukebox here, and a bartender tending bar.",
    )

    # --- Connections (geography resolved from each room's exit block) ------
    # Castle
    _one_way(tower, "out", tower_stairs)  # the door (locks after a failed escape)
    _one_way(tower, "down", gardens)  # climbing out the window on the hair rope
    _one_way(tower_stairs, "enter", tower)
    tower_stairs.add_connection("down", guardroom)  # auto: guardroom up -> stairs
    guardroom.add_connection("west", drawbridge)  # auto: drawbridge east -> guardroom
    # Gardens / river
    gardens.add_connection("south", drawbridge)  # auto: drawbridge north -> gardens
    drawbridge.add_connection("south", river)  # auto: river north -> drawbridge
    drawbridge.add_connection(
        "west", old_woods
    )  # vehicle-gated (RequiresVehicle, below)
    # Woods
    _one_way(old_woods, "enter", old_shack)
    _one_way(old_shack, "out", old_woods)
    _one_way(old_woods, "north", deep_woods)  # follow the deer (mounted)
    _one_way(deep_woods, "south", old_woods)
    _one_way(deep_woods, "north", clearing)  # opens once the poacher is dealt with
    # Clearing / ranch / road (diagonals -> one-way both sides)
    clearing.add_connection("west", dirt_road)  # auto: dirt_road east -> clearing
    _one_way(clearing, "southwest", ranch)
    _one_way(ranch, "northeast", clearing)
    ranch.add_connection("north", dirt_road)  # auto: dirt_road south -> ranch
    dirt_road.add_connection("north", roadhouse)  # auto: roadhouse south -> dirt_road
    # Roadhouse / bar / highway
    _one_way(roadhouse, "enter", breakpoint)
    _one_way(breakpoint, "out", roadhouse)
    # The two endings (ride onto the Highway; settle as a Rancher) are action
    # *effects*, not rooms -- they land as custom actions in Slice 5, not as
    # exits here. ("ride east"/"ride west" off the bike, "say yes" at the ranch.)

    # --- Vehicle gate: the woods are too far on foot -----------------------
    drawbridge.add_block(
        "west",
        blocks.RequiresVehicle(
            drawbridge,
            "It's too far to travel on foot, and you're not used to all this walking. "
            "Perhaps if you had a horse...",
        ),
    )

    # --- Items (fixtures + key objects; puzzle wiring comes in later slices) ---
    tower.add_item(
        _fixture(
            "armoire",
            "a dazzling armoire of dresses and footwear",
            "Sparkly dresses, ill-fitting undergarments, and fiendish footwear.",
        )
    )
    tower.add_item(
        _fixture(
            "dresser",
            "a dresser with a mirror",
            "A built-in mirror above a chest of drawers.",
        )
    )
    tower.add_item(
        _fixture(
            "mirror",
            "a mirror",
            "Your hair is staggeringly long -- it drags on the floor behind you.",
        )
    )
    tower.add_item(
        _fixture(
            "window",
            "a tower window",
            "A long way down to the gardens' rosebushes and orchards.",
        )
    )
    tower.add_item(
        _fixture(
            "door",
            "a heavy wooden door",
            "A heavy door with a large iron ring for a handle.",
        )
    )
    glass_slippers = _item(
        "glass slippers", "a pair of glass slippers", "Glass? Yes, glass."
    )
    ruby_slippers = _item(
        "ruby slippers",
        "a pair of ruby slippers",
        "There's no place like home? I guess.",
    )
    tower.add_item(glass_slippers)
    tower.add_item(ruby_slippers)
    guardroom.add_item(
        _fixture(
            "army cot",
            "an army cot",
            "Under the stained mattress is a pair of old army boots.",
        )
    )
    guardroom.add_item(
        _fixture(
            "footlocker", "a closed footlocker", "The guard's footlocker. It's closed."
        )
    )
    guardroom.add_item(
        _item(
            "army boots",
            "a pair of army boots",
            "A little big, but your feet aren't petite.",
        )
    )
    gardens.add_item(
        _fixture(
            "rosebushes",
            "thorny rosebushes",
            "Thorny and covered with roses of every color.",
        )
    )
    gardens.add_item(
        _fixture("fruit trees", "apple trees", "Branches heavy with ripe red apples.")
    )

    # The white mare: a vehicle, but skittish until tamed (apple or brushing).
    mare = _fixture(
        "horse", "a white mare", "A beautiful white mare with a flowing silver mane."
    )
    mare.make_vehicle(ready=False)
    mare.set_property(
        "mount_refusal_message", "The mare steps away and whinnies, shaking its mane."
    )
    river.add_item(mare)
    old_shack.add_item(
        _fixture(
            "crossbow",
            "a loaded crossbow",
            "Drawn back and ready -- for scaring poachers, not killing.",
        )
    )
    ranch.add_item(
        _fixture(
            "melon patch",
            "a melon patch",
            "Watermelons on the vine. Too heavy to carry.",
        )
    )
    dirt_road.add_item(
        _fixture(
            "sign",
            "a signpost",
            "North to the Breakpoint Bar & Grill, south to the Double-Deuce Ranch.",
        )
    )
    breakpoint.add_item(
        _fixture(
            "jukebox",
            "a jukebox",
            "Country, blues, and a little classic metal. Each song costs a coin.",
        )
    )

    # The motorcycle: a vehicle, but needs a key (from the bar brawl) to start.
    bike = _fixture(
        "motorcycle",
        "a custom chopper",
        "All black and chrome, with ape-hanger bars and airbrushed skulls.",
    )
    bike.make_vehicle(ready=False)
    bike.set_property("mount_refusal_message", "The bike won't start without a key.")
    roadhouse.add_item(bike)

    # --- Characters --------------------------------------------------------
    player = things.Character(
        "princess",
        "the Princess of Action Castle, in a sparkly gown and tiara",
        "I am the princess, and I am getting out of this tower.",
    )

    prince = things.Character(
        "prince",
        "a well-dressed young prince with a paintbrush",
        "I am a prince on a quest; first, I must paint.",
    )
    prince.talk_text = '"Good day, m\'lady! What a delightful view! So fortunate I packed my art supplies before my quest."'
    prince.talk_topics = {
        "quest": '"I\'ve traveled many leagues to rescue the princess from yon tower. But first, I must paint!"',
        "tower": '"Yon tower is where the princess sleeps for all eternity, cursed by an evil witch\'s spell... or something."',
        "princess": '"I hear she is beautiful -- rose lips, flaxen hair, and delicate feet like an elf maid."',
    }
    deer = things.Character(
        "deer", "a beautiful doe", "A grazing doe, alert to any sign of danger."
    )
    poacher = things.Character(
        "poacher",
        "a grizzled poacher in a stained cloak",
        "I poach the king's deer; mind your business.",
    )
    rancher = things.Character(
        "rancher",
        "an old rancher (Wade) on a black stallion",
        "I am Wade; I run the Double-Deuce and could use a hand.",
    )
    rancher.talk_text = "\"Beautiful horse you've got there! Ol' Champ here could use a companion. Mornin', miss!\""
    dalton = things.Character(
        "dalton",
        "Dalton, a good-looking man by the roadhouse door",
        "I am Dalton; I keep the underage out of the bar.",
    )
    bartender = things.Character(
        "bartender", "the Breakpoint's bartender", "I tend bar and I am very busy."
    )

    river.add_character(prince)
    old_woods.add_character(deer)
    deep_woods.add_character(poacher)
    ranch.add_character(rancher)
    roadhouse.add_character(dalton)
    breakpoint.add_character(bartender)

    # --- Start state: the princess wears a gown and a tiara ----------------
    gown = _item(
        "gown",
        "a sparkly gown",
        "Much layers. So sparkle. It weighs almost as much as you.",
    )
    tiara = _item("tiara", "a jeweled tiara", "Pretty, but pinchy.")
    player.inventory["gown"] = gown
    player.inventory["tiara"] = tiara
    player.wear(gown)
    player.wear(tiara)

    characters = [prince, deer, poacher, rancher, dalton, bartender]
    custom_actions = []  # the novel verbs land in Slices 3-5
    game = ActionCastle4(tower, player, characters, custom_actions)
    return game


# ---------------------------------------------------------------------------
# Walkthrough (a skeleton smoke path for now; the winning run lands in Slice 5)
# ---------------------------------------------------------------------------

WALKTHROUGH_SKELETON = [
    "out",  # Tower -> Tower Stairs
    "down",  # -> Guardroom
    "west",  # -> Drawbridge
    "south",  # -> Down by the River
    "north",  # -> Drawbridge
    "north",  # -> Gardens
    "south",  # -> Drawbridge
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
        f"WON: {game.is_won()}  GAME_OVER: {game.is_game_over()}  SCORE: {game.score}/{game.max_score}"
    )
    return game


if __name__ == "__main__":
    import sys

    if "--walk" in sys.argv:
        _run(WALKTHROUGH_SKELETON)
    else:
        build_game().game_loop()
