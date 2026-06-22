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

from text_adventure_games import games, things, actions, blocks, Recipe
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


def _take_held(character, name):
    """Remove and return a held item by name -- from hands/worn/wielded or an
    open carried container -- else None."""
    for store in (character.inventory, character.worn, character.wielded):
        if name in store:
            return store.pop(name)
    for item in character.inventory.values():
        if name in item.accessible_contents():
            held = item.contents[name]
            item.remove_item(held)
            return held
    return None


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
# Tower escape (Slice 3). Two winning routes: sneak down through the Guardroom
# (-> Drawbridge), or cut your hair, braid it into a rope, tie it off and climb
# out the window (-> Gardens). MAKE ROPE / BRAID HAIR is a crafting recipe
# (hair -> rope); CUT HAIR (with the dagger) and TIE ROPE are bespoke steps.
# ---------------------------------------------------------------------------


class CutHair(actions.Action):
    """Saw off the absurdly long hair with the dagger -- yields a heap of hair
    (the rope's raw material) and dulls the blade."""

    ACTION_NAME = "cut hair"
    ACTION_DESCRIPTION = "Cut off your hair with the dagger"
    ACTION_ALIASES = [
        "cut hair with dagger",
        "cut my hair",
        "cut off my hair",
        "saw hair",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if not _is_holding(self.player, "dagger"):
            self.parser.fail("You have nothing sharp enough to cut it with.")
            return False
        if self.player.get_property("hair_cut"):
            self.parser.fail("Your hair is already cropped short.")
            return False
        return True

    def apply_effects(self):
        self.player.set_property("hair_cut", True)
        for store in (self.player.inventory, self.player.worn, self.player.wielded):
            if "dagger" in store:
                store["dagger"].set_property("dull", True)
        self.player.add_to_inventory(
            _item("hair", "10 lbs of silky hair", "A coiled heap of your shorn hair.")
        )
        self.parser.ok(
            "You saw away close to your scalp and remove about ten pounds of silky "
            "hair. It falls to the floor in a coiled heap. You feel so much lighter! "
            "(The dagger is now dull.)"
        )


class TieRope(actions.Action):
    """Tie the braided rope to the door's iron ring so you can climb out."""

    ACTION_NAME = "tie rope"
    ACTION_DESCRIPTION = "Tie the rope to the door's iron ring"
    ACTION_ALIASES = [
        "tie rope to ring",
        "tie rope to door",
        "tie hair to door",
        "tie the rope",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if self.player.location is None or self.player.location.name != "Tower":
            self.parser.fail("There's nothing here to tie it to.")
            return False
        if not _is_holding(self.player, "rope"):
            self.parser.fail("You have no rope.")
            return False
        return True

    def apply_effects(self):
        self.player.location.set_property("rope_tied", True)
        self.parser.ok(
            "You tie the rope to the door's iron ring and feed the rest out the "
            "window. Now you can CLIMB DOWN."
        )


class _WearSlippers(actions.Action):
    """Shared base for the two slipper gags (rulebook: neither is a death)."""

    SLIPPERS = ""
    GAG = ""

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if not _is_holding(self.player, self.SLIPPERS):
            self.parser.fail(f"You don't have the {self.SLIPPERS}.")
            return False
        return True

    def apply_effects(self):
        # Move them into `worn` (from inventory), then deliver the gag. Not fatal.
        if self.SLIPPERS in self.player.inventory:
            self.player.wear(self.player.inventory[self.SLIPPERS])
        self.parser.ok(self.GAG)


class WearGlassSlippers(_WearSlippers):
    ACTION_NAME = "wear glass slippers"
    ACTION_DESCRIPTION = "Wear the glass slippers"
    ACTION_ALIASES = ["put on glass slippers", "put on the glass slippers"]
    SLIPPERS = "glass slippers"
    GAG = (
        "You cram your size 9's inside the tortuous footwear. If you step lightly, "
        "it doesn't hurt... much."
    )


class WearRubySlippers(_WearSlippers):
    ACTION_NAME = "wear ruby slippers"
    ACTION_DESCRIPTION = "Wear the ruby slippers"
    ACTION_ALIASES = ["put on ruby slippers", "put on the ruby slippers"]
    SLIPPERS = "ruby slippers"
    GAG = "You click your heels together. It does not send you back to Kansas."


class KillSelf(actions.Action):
    """A clue, not a death: she goes to stab herself, a falling hair slices the
    dagger, and she realizes her hair can be cut."""

    ACTION_NAME = "kill self"
    ACTION_DESCRIPTION = "Despair (a clue)"
    ACTION_ALIASES = [
        "kill myself",
        "stab self",
        "stab myself",
        "commit suicide",
        "end it all",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if not _is_holding(self.player, "dagger"):
            self.parser.fail("You have no way to do anything so dramatic.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "Tragic, but dramatic -- you can't bear this meaningless existence any "
            "longer. As you prepare to plunge the dagger into your chest, a single "
            "hair falls from your head and lands on the razor-sharp edge, cutting it "
            "in half. Hmm..."
        )


# ---------------------------------------------------------------------------
# The horse (Slice 4a). The white mare is a vehicle (engine #vehicles) but
# skittish until tamed -- GIVE APPLE TO HORSE or BRUSH HORSE makes it rideable.
# Then ride west into the Old Woods; dismount to enter the shack for the crossbow.
# ---------------------------------------------------------------------------


class PickApple(actions.Action):
    """Pluck a ripe apple from the gardens' fruit trees (taming the mare)."""

    ACTION_NAME = "pick apple"
    ACTION_DESCRIPTION = "Pick an apple from the fruit trees"
    ACTION_ALIASES = ["pick an apple", "pluck apple", "pick apples", "take apple"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if self.player.location is None or self.player.location.name != "Gardens":
            self.parser.fail("There are no apple trees here.")
            return False
        return True

    def apply_effects(self):
        self.player.add_to_inventory(
            _item("apple", "a shiny red apple", "A shiny red apple, plucked yourself.")
        )
        self.parser.ok(
            "You pluck a shiny red apple from the tree. Doing it yourself is rather "
            "satisfying!"
        )


class EatApple(actions.Action):
    """Eat the apple (a gag -- and it spends your horse-taming treat)."""

    ACTION_NAME = "eat apple"
    ACTION_DESCRIPTION = "Eat the apple"
    ACTION_ALIASES = ["eat the apple"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if not _is_holding(self.player, "apple"):
            self.parser.fail("You have no apple.")
            return False
        return True

    def apply_effects(self):
        _take_held(self.player, "apple")
        self.parser.ok(
            "*CRUNCH* You can't help but feel there's some symbolism at play here."
        )


class _TameHorse(actions.Action):
    """Shared base: make the skittish mare rideable, at Down by the River."""

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.mare = self.game.locations["Down by the River"].items.get("horse")

    def _tame(self, message):
        self.mare.set_property("vehicle_ready", True)
        self.parser.ok(message)


class GiveAppleToHorse(_TameHorse):
    ACTION_NAME = "give apple to horse"
    ACTION_DESCRIPTION = "Offer the mare an apple"
    ACTION_ALIASES = [
        "feed apple to horse",
        "feed horse apple",
        "feed the horse an apple",
        "give horse apple",
        "give horse an apple",
        "give the horse an apple",
    ]

    def check_preconditions(self) -> bool:
        if (
            self.player.location is None
            or self.player.location.name != "Down by the River"
        ):
            self.parser.fail("There's no horse here.")
            return False
        if not _is_holding(self.player, "apple"):
            self.parser.fail("You have no apple to offer.")
            return False
        return True

    def apply_effects(self):
        _take_held(self.player, "apple")
        self._tame(
            "The mare lips the apple from your palm, then nuzzles you. She'll let you "
            "ride her now."
        )


class BrushHorse(_TameHorse):
    ACTION_NAME = "brush horse"
    ACTION_DESCRIPTION = "Brush the mare's mane"
    ACTION_ALIASES = [
        "brush the horse",
        "brush mare",
        "brush the mare",
        "brush the mare's mane",
        "groom horse",
        "groom the horse",
    ]

    def check_preconditions(self) -> bool:
        if (
            self.player.location is None
            or self.player.location.name != "Down by the River"
        ):
            self.parser.fail("There's no horse here.")
            return False
        if not _is_holding(self.player, "hairbrush"):
            self.parser.fail("You have nothing to brush her with.")
            return False
        return True

    def apply_effects(self):
        self._tame(
            "You brush the mare's silver mane until it gleams. She calms and lets you "
            "approach. She'll let you ride her now."
        )


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

    # Tower escape gates. The window route (Tower down -> Gardens) needs the hair
    # rope tied off; trying to bolt west off the stairs runs you into the guard
    # (avoidable -- just don't go that way).
    class RopeBlock(blocks.Block):
        def __init__(self, tower):
            super().__init__(
                "No way down", "It's a long way down -- you'd need a rope to climb."
            )
            self.tower = tower

        def is_blocked(self) -> bool:
            return not self.tower.get_property("rope_tied")

    tower.add_block("down", RopeBlock(tower))

    class GuardBlock(blocks.Block):
        def __init__(self):
            super().__init__(
                "The guard",
                "You make a break for it, but run smack into the tower's guard. "
                '"Back to your chambers!" He turns you around. (Best not go this way.)',
            )

        def is_blocked(self) -> bool:
            return True

    _one_way(tower_stairs, "west", drawbridge)  # the "break for it" the guard foils
    tower_stairs.add_block("west", GuardBlock())

    # You must get off the horse to squeeze into the warden's shack.
    class DismountBlock(blocks.Block):
        def __init__(self, loc):
            super().__init__(
                "Not on horseback",
                "You'll have to get off the horse first. (Try DISMOUNT.)",
            )
            self.loc = loc

        def is_blocked(self) -> bool:
            return any(
                getattr(c, "riding", None) is not None
                for c in self.loc.characters.values()
            )

    old_woods.add_block("enter", DismountBlock(old_woods))

    # --- Items (fixtures + key objects; puzzle wiring comes in later slices) ---
    tower.add_item(
        _fixture(
            "armoire",
            "a dazzling armoire of dresses and footwear",
            "Sparkly dresses, ill-fitting undergarments, and fiendish footwear.",
        )
    )
    dresser = _fixture(
        "dresser",
        "a dresser with a mirror",
        "A built-in mirror above a chest of drawers.",
    )
    dresser.make_container()
    dresser.set_property("is_closed", True)  # OPEN DRESSER -> a hairbrush
    dresser.add_item(
        _item(
            "hairbrush", "a green hairbrush", "A green hairbrush with white bristles."
        )
    )
    tower.add_item(dresser)
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
    footlocker = _fixture("footlocker", "a footlocker", "The guard's footlocker.")
    footlocker.make_container()
    footlocker.set_property("is_closed", True)  # OPEN FOOTLOCKER -> a dagger
    footlocker.add_item(
        _item(
            "dagger",
            "a wicked-sharp dagger",
            "It's wicked sharp -- good for cutting, not for hurting.",
        )
    )
    guardroom.add_item(footlocker)
    boots = _item(
        "army boots",
        "a pair of army boots",
        "A little big, but your feet aren't petite.",
    )
    boots.set_property(Property.WEARABLE, True)
    guardroom.add_item(boots)
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
        _item(
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
    custom_actions = [
        CutHair,
        TieRope,
        WearGlassSlippers,
        WearRubySlippers,
        KillSelf,
        PickApple,
        EatApple,
        GiveAppleToHorse,
        BrushHorse,
    ]
    game = ActionCastle4(tower, player, characters, custom_actions)

    # MAKE ROPE / BRAID HAIR: a one-input crafting recipe (hair -> rope), reusing
    # the crafting system. The surrounding steps (CUT HAIR, TIE ROPE) are custom.
    game.add_recipe(
        Recipe(
            name="rope",
            aliases=["hair rope", "braided rope"],
            inputs=["hair"],
            output=lambda g: _item(
                "rope",
                "a rope of braided hair",
                "A long, sturdy rope braided from your own hair.",
            ),
            result_text="You braid the heap of hair into a long, sturdy rope.",
        )
    )

    # Tower-escape scoring (rulebook page 19): sneak to the guardroom +5, wear the
    # army boots +5, and escape the tower +5 (reaching the Gardens or Drawbridge).
    game.add_trigger(
        "score_guardroom",
        lambda g: g.player.location is guardroom and "guardroom" not in g._scored_keys,
        lambda g: g.award("guardroom", 5, "You sneak down into the guardroom."),
        repeatable=True,
    )
    game.add_trigger(
        "score_boots",
        lambda g: "army boots" in g.player.worn and "boots" not in g._scored_keys,
        lambda g: g.award(
            "boots", 5, "Laced into the army boots, you can actually walk."
        ),
        repeatable=True,
    )
    game.add_trigger(
        "score_escape",
        lambda g: g.player.location is not None
        and g.player.location.name in ("Gardens", "Drawbridge")
        and "escape" not in g._scored_keys,
        lambda g: g.award("escape", 5, "You're free of that blasted tower!"),
        repeatable=True,
    )

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
