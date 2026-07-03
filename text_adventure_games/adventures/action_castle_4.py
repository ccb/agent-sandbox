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
  * Slice 2: the world skeleton -- rooms, exits, items, characters, start state
    (the princess wears a gown + tiara), the vehicle-gated woods exit, and the ending stubs.
  * Slice 3: the full-fidelity tower escape (cut hair -> braid a rope -> climb out the
    window; the front gate is a guard trap that re-locks you, and KILL SELF is a clue).
  * Slice 4: the horse (tame with apple/brush, then ride) + the poacher/deer confrontation.
  * Slice 5: the finale -- the ranch (GIVE HORSE -> a yes/no job offer), the roadhouse
    "Wade sent me" gate, the bar brawl (tray -> table four -> keys), the started motorcycle,
    and the two scored endings (Rancher +40, Highway +50; a full run scores 100/100).

Run interactively:   python action_castle_4.py
"""

from text_adventure_games import games, things, actions, blocks, Recipe, Prompt
from text_adventure_games import reactions
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


def _footwear(name, description, wear_text, examine_text=""):
    """A wearable shoe in the "feet" slot (so only one is worn at a time -- the
    engine Wear action enforces the slot). ``wear_text`` is the flavor on wearing."""
    it = _item(name, description, examine_text)
    it.set_property(Property.WEARABLE, True)
    it.set_property("wear_slot", "feet")
    it.set_property("wear_text", wear_text)
    return it


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
# Tower escape (Slice 3). The one real way out is the window: cut your hair, braid
# it into a rope, tie it to the door's iron ring and climb down (-> Gardens). The
# front gate (Guardroom WEST -> the bridge) is a trap -- the guard marches you back
# and locks the door, and without the dagger that's the "trapped forever" ending.
# MAKE ROPE / BRAID HAIR is a crafting recipe (hair -> rope); CUT HAIR (with the
# dagger) and TIE ROPE are bespoke steps.
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
        # Update the live appearance the mirror reflects (no more "staggeringly long").
        self.player.appearance["hair"] = (
            "Your hair is hacked off in a ragged crop where the dagger sawed through it."
        )
        for store in (self.player.inventory, self.player.worn, self.player.wielded):
            if "dagger" in store:
                store["dagger"].set_property("dull", True)
        # The hair falls to the floor (faithful to the rulebook) -- GET HAIR to
        # pick it up, then MAKE ROPE / BRAID HAIR braids it.
        self.player.location.add_item(
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
        # The rope is now tied to the door and fed out the window -- it leaves
        # your hands.
        _take_held(self.player, "rope")
        self.parser.ok(
            "You tie the rope to the door's iron ring and feed the rest out the "
            "window. Now you can CLIMB DOWN."
        )


class LetGo(actions.Action):
    """Drop from the rope into the gardens (the commit). Only meaningful while
    Outside the Tower; delegates to GO DOWN so the fall reuses the travel text,
    room description, and escape scoring."""

    ACTION_NAME = "let go"
    ACTION_DESCRIPTION = "Let go of the rope and drop into the gardens"
    ACTION_ALIASES = [
        "jump",
        "fall",
        "jump down",
        "let go of the rope",
        "let go of the window",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if (
            self.player.location is None
            or self.player.location.name != "Outside the Tower"
        ):
            self.parser.fail("There's nothing to let go of here.")
            return False
        return True

    def apply_effects(self):
        actions.Go(self.game, "down", actor=self.player)()


# The slippers and boots are ordinary WEARABLE items in the "feet" slot, so the
# engine Wear action handles them: WEAR GLASS/RUBY SLIPPERS deliver their gag
# (wear_text), WEAR BOOTS its line, and the slot rule means only one is worn at a
# time -- "wear boots" while slippers are on is refused until you take them off.
# (No custom wear actions needed -- this is the wear_slot generalization.)


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


class PickWatermelon(actions.Action):
    """Try to pick a watermelon from the vines -- a gag: it's too heavy to carry
    (rulebook)."""

    ACTION_NAME = "pick watermelon"
    ACTION_DESCRIPTION = "Try to pick a watermelon from the vines"
    ACTION_ALIASES = [
        "pick a watermelon",
        "pluck watermelon",
        "pick watermelons",
        "take watermelon",
        "get watermelon",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if self.player.location is None or self.player.location.name != "Gardens":
            self.parser.fail("There are no watermelon vines here.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "It's too heavy. Why would you want to carry a watermelon, anyway?"
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


class BrushHair(actions.Action):
    """Brush your own (absurdly long) hair -- pure flavor, but it nudges you
    toward the idea that all this hair might be good for something."""

    ACTION_NAME = "brush hair"
    ACTION_DESCRIPTION = "Brush your own hair with the hairbrush"
    ACTION_ALIASES = [
        "brush my hair",
        "brush your hair",
        "brush the hair",
        "comb hair",
        "comb my hair",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if not _is_holding(self.player, "hairbrush"):
            self.parser.fail("You'll need a hairbrush for that.")
            return False
        if self.player.get_property("hair_cut"):
            self.parser.fail("What's left of your hair hardly needs brushing now.")
            return False
        return True

    def apply_effects(self):
        self.player.set_property("hair_brushed", True)
        self.parser.ok(
            "You spend about two hours brushing out your impossibly long hair. "
            "Well -- that was productive."
        )


# ---------------------------------------------------------------------------
# The poacher + the deer (Slice 4b). Ride after the deer into the Deep Woods,
# where a poacher has it in his sights. SHOOT POACHER (with the crossbow) saves
# the deer (+5) and he flees, dropping his coin purse (+5 to take) and cloak.
#
# Both threats are programmable reactions (docs/design/reactions.md), owned by
# the things themselves rather than by location triggers:
#   * the doe is a FleesAtNoise startle -- she bolts at ANY noise she hears in
#     the Old Woods (the shack door banging as you step out, or a loud action of
#     your own). What counts as noise is the source's business (an action's
#     AUDIBLE_RADIUS, or emit_sound for the door), so there's no per-scene "loud
#     verbs" list here; quiet things (looking, taking the crossbow, mounting)
#     leave her be, so you can arm yourself first if you move quietly.
#   * the poacher is a Countdown -- the doe's arrival in the Deep Woods puts her
#     in his sights and starts a clock; reach him and SHOOT before it elapses or
#     he looses his arrow. The clock starts the moment she's cornered, whether or
#     not you've followed yet, so a careful approach has to be a fast one.
# ---------------------------------------------------------------------------


class DoeFlees(reactions.FleesAtNoise):
    """The grazing doe bolts to the Deep Woods at the first noise she hears, and
    once she's at bay there the examine text reflects the poacher's crossbow."""

    def apply_effects(self):
        super().apply_effects()  # relocate + narrate
        self.owner.examine_text = (
            "The doe stands at bay, wide-eyed, a poacher's crossbow trained on her."
        )

    def narration(self, dest) -> str:
        cue = (self.cause or {}).get("description", "a noise")
        return (
            f"{cue[:1].upper()}{cue[1:]}, and the doe's head snaps up -- in a flash "
            "she bolts, white tail flashing, off into the Deep Woods."
        )


class PoacherShoots(reactions.Countdown):
    """The poacher's lethal clock. The moment the doe is driven into his clearing
    she's at bay; a few turns later he looses his arrow -- unless you reach him
    and SHOOT POACHER first (which sets ``poacher_dealt`` and calls it off).

    Anchored on the doe's arrival, not yours: the delay covers a prompt ride +
    FOLLOW DEER with one turn to spare to loose your own bolt, so dawdling on the
    way costs the doe her life."""

    DELAY = 4

    def __init__(self, quarry):
        super().__init__()
        self.quarry = quarry  # the doe
        self._clearing = None  # captured when the countdown starts

    def stimulus(self) -> bool:
        return self.game.entered_this_round(self.quarry, self.owner.location)

    def apply_effects(self):
        # Capture the clearing now, while the poacher is still standing in it:
        # SHOOT POACHER removes him (location -> None), but the scheduled shot
        # still resolves and must read the cancel flag off the room, not the
        # vanished poacher.
        self._clearing = self.owner.location
        super().apply_effects()

    def cancelled(self) -> bool:
        return bool(self._clearing.get_property("poacher_dealt"))

    def warning(self) -> str:
        return (
            "Off through the trees the doe is brought to bay -- a poacher's "
            "crossbow rises. There's no time to lose."
        )

    def consequence(self, game):
        _die(
            game,
            "Too slow -- the poacher looses his arrow and the doe drops. With no "
            "guide, you wander the Deep Woods until you are hopelessly lost. THE END.",
        )


class FollowDeer(actions.Action):
    """Ride after the deer (from the Old Woods) into the Deep Woods."""

    ACTION_NAME = "follow deer"
    ACTION_DESCRIPTION = "Ride after the deer"
    ACTION_ALIASES = ["follow the deer", "chase deer", "follow doe", "enter deep woods"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if self.player.location is None or self.player.location.name != "Old Woods":
            self.parser.fail("There's no deer to follow here.")
            return False
        riding = self.player.riding
        if riding is None or riding.name != "horse":
            self.parser.fail("You'd never catch her on foot -- you'll need the horse.")
            return False
        # There's a chase only once she's bolted. While she's still grazing in
        # the Old Woods there's nothing to follow -- hinting at the shack, where
        # emerging spooks her (and where the crossbow is, which you'll want).
        if "deer" in self.player.location.items:
            self.parser.fail(
                "The doe is still grazing, unspooked -- there's nothing to chase "
                "yet. (The game warden's shack might be worth a look first.)"
            )
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "You click your tongue and nudge the white mare down a hidden path into "
            "the Deep Woods."
        )
        _relocate(self.game, self.player, "Deep Woods")


class _WorkWinch(actions.Action):
    """Shared base for the guardroom drawbridge winch. Subclasses set the
    target state (``_target_raised``) and the success line."""

    _target_raised = True
    _already = "The drawbridge is already there."
    _line = ""

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.drawbridge = self.game.locations["Drawbridge"]

    def check_preconditions(self) -> bool:
        if self.player.location is None or self.player.location.name != "Guardroom":
            self.parser.fail(
                "There's no winch here. The drawbridge winch is back in the guardroom."
            )
            return False
        if bool(self.drawbridge.get_property("raised")) == self._target_raised:
            self.parser.fail(self._already)
            return False
        return True

    def apply_effects(self):
        self.drawbridge.set_property("raised", self._target_raised)
        self.parser.ok(self._line)


class LowerDrawbridge(_WorkWinch):
    """Work the guardroom winch to lower the drawbridge across the moat."""

    ACTION_NAME = "lower drawbridge"
    ACTION_DESCRIPTION = "Lower the castle drawbridge"
    ACTION_ALIASES = [
        "lower the drawbridge",
        "lower bridge",
        "lower the bridge",
        "lower drawbridge with winch",
    ]
    _target_raised = False
    _already = "The drawbridge is already down."
    _line = (
        "You throw your weight on the great winch. With a shriek of chains the "
        "drawbridge sinks down across the moat -- the way west lies open."
    )


class RaiseDrawbridge(_WorkWinch):
    """Work the guardroom winch to haul the drawbridge back up."""

    ACTION_NAME = "raise drawbridge"
    ACTION_DESCRIPTION = "Raise the castle drawbridge"
    ACTION_ALIASES = [
        "raise the drawbridge",
        "raise bridge",
        "raise the bridge",
    ]
    _target_raised = True
    _already = "The drawbridge is already up."
    _line = (
        "You crank the winch the other way; the drawbridge groans back up, sealing "
        "the castle gate."
    )


class ShootPoacher(actions.Action):
    """Loose the crossbow at the poacher -- he flees, dropping his purse + cloak,
    and the deer is saved."""

    ACTION_NAME = "shoot poacher"
    ACTION_DESCRIPTION = "Fire the crossbow at the poacher"
    ACTION_ALIASES = [
        "shoot the poacher",
        "fire at poacher",
        "fire crossbow at poacher",
        "shoot crossbow",
        "shoot crossbow at poacher",
        "threaten poacher",
        "show crossbow",
        "show crossbow to poacher",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.deep_woods = self.game.locations["Deep Woods"]

    def check_preconditions(self) -> bool:
        if self.player.location is not self.deep_woods:
            self.parser.fail("There's no poacher here.")
            return False
        if self.deep_woods.get_property("poacher_dealt"):
            self.parser.fail("The poacher is already dealt with.")
            return False
        if not _is_holding(self.player, "crossbow"):
            self.parser.fail("You have nothing to shoot him with.")
            return False
        return True

    def apply_effects(self):
        self.deep_woods.set_property("poacher_dealt", True)
        poacher = self.game.characters.get("poacher")
        if poacher is not None and poacher.location is self.deep_woods:
            self.deep_woods.remove_character(poacher)
        purse = _item(
            "coin purse",
            "a small coin purse",
            "A few silver coins, each stamped with your father's face.",
        ).make_container()
        purse.add_alias("purse")
        purse.add_item(_item("silver coins", "silver coins").make_stackable(3))
        cloak = _item(
            "cloak", "a stained cloak", "The poacher's stained traveling cloak."
        )
        # Wearable, and it layers over the gown (wear_over) -- the wear-slot
        # feature's cloak-over-a-gown case. Pure flavor: a bit of disguise.
        cloak.set_property(Property.WEARABLE, True)
        cloak.set_property("wear_slot", "body")
        cloak.set_property("wear_over", True)
        cloak.set_property(
            "wear_text",
            "You pull the poacher's stained cloak over your gown -- less a princess "
            "now, more a traveler on the road.",
        )
        self.deep_woods.add_item(purse)
        self.deep_woods.add_item(cloak)
        self.game.award(
            "shoot",
            5,
            "You fire, pinning the poacher to a tree with your bolt! He thrashes free "
            "and flees, dropping his coin purse and cloak. The doe, safe, nuzzles your "
            "hand before bounding off -- as if to say thanks.",
        )


# ---------------------------------------------------------------------------
# The finale (Slice 5): the Ranch, the Roadhouse, and the Breakpoint bar.
#
# Two winning routes diverge at the Ranch. GIVE HORSE TO RANCHER pairs your mare
# with Wade's stallion and earns a job offer (a posed yes/no Prompt, #110):
#   * SAY YES -> settle as a Rancher (+40, a good ending).
#   * SAY NO  -> Wade sends you to Dalton at the roadhouse ("tell him Wade sent
#     ya"), which unlocks the bar. Inside, wait tables -> start a brawl -> a ring
#     of motorcycle keys flies loose -> start the bike -> ride onto the Highway
#     (+50, the 100-point best run).
# ---------------------------------------------------------------------------


def _find_horse(game):
    """The mare, whether the player is still mounted or has dismounted here."""
    player = game.player
    if getattr(player, "riding", None) is not None and player.riding.name == "horse":
        return player.riding
    if player.location is not None:
        return player.location.items.get("horse")
    return None


class GiveHorseToRancher(actions.Action):
    ACTION_NAME = "give horse to rancher"
    ACTION_DESCRIPTION = "Give your mare to Wade the rancher"
    ACTION_ALIASES = [
        "give the horse to the rancher",
        "give horse to wade",
        "give the horse to wade",
        "give mare to rancher",
        "give the mare to the rancher",
        "give horse to the rancher",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.rancher = self.game.characters.get("rancher")

    def check_preconditions(self) -> bool:
        if self.rancher is None or self.rancher.location is not self.player.location:
            self.parser.fail("There's no rancher here.")
            return False
        if _find_horse(self.game) is None:
            self.parser.fail("You don't have a horse to give.")
            return False
        return True

    def apply_effects(self):
        horse = _find_horse(self.game)
        if self.player.riding is horse:
            self.player.riding = None
        if self.player.location is not None and "horse" in self.player.location.items:
            self.player.location.remove_item(horse)
        self.rancher.set_property("offered_job", True)
        self.game.award(
            "gift_horse",
            5,
            "The mare and ol' Champ nuzzle like old friends. Wade beams: \"Aww, they "
            "took a shine to each other! Say -- you look like a hard worker. I could "
            'use a hand here on the Double-Deuce. Whaddya say?"',
        )
        self.game.pose_prompt(
            Prompt(
                text="Stay and work the ranch? (yes / no)",
                options={"yes": "say yes", "no": "say no"},
                speaker="rancher",
            )
        )


class SayYes(actions.Action):
    ACTION_NAME = "say yes"
    ACTION_DESCRIPTION = "Accept Wade's offer to work the ranch"
    ACTION_ALIASES = ["accept", "accept the job", "yes please"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.rancher = self.game.characters.get("rancher")

    def check_preconditions(self) -> bool:
        if self.rancher is None or not self.rancher.get_property("offered_job"):
            self.parser.fail("No one's asked you anything.")
            return False
        return True

    def apply_effects(self):
        self.game.award("rancher", 40)
        self.game.award("finish", 5)
        ending = (
            "You hang up your tiara and take up ranching. The work is honest, the "
            "sunsets are long, and ol' Champ and your mare raise a whole herd of foals. "
            "Years later, when Wade retires, the Double-Deuce is yours. THE END."
        )
        self.parser.ok(ending)
        self.game.game_over = True
        self.game.game_over_description = ending


class SayNo(actions.Action):
    ACTION_NAME = "say no"
    ACTION_DESCRIPTION = "Decline Wade's offer to work the ranch"
    ACTION_ALIASES = ["decline", "no thanks", "no thank you"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.rancher = self.game.characters.get("rancher")

    def check_preconditions(self) -> bool:
        if self.rancher is None or not self.rancher.get_property("offered_job"):
            self.parser.fail("No one's asked you anything.")
            return False
        return True

    def apply_effects(self):
        self.player.set_property("knows_wade", True)
        self.parser.ok(
            "\"Well, I understand -- ranchin' ain't for everyone.\" Wade tips his hat. "
            "\"If it's a ride you're after, go see Dalton up at the Breakpoint. Tell him "
            "Wade sent ya, and he'll let you in.\""
        )


class SayWadeSentMe(actions.Action):
    ACTION_NAME = "say wade sent me"
    ACTION_DESCRIPTION = "Tell Dalton that Wade sent you"
    ACTION_ALIASES = [
        "wade sent me",
        "tell dalton wade sent me",
        "tell him wade sent me",
        "say wade sent me to dalton",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if self.player.location is None or self.player.location.name != "Roadhouse":
            self.parser.fail("There's no one here to say that to.")
            return False
        return True

    def apply_effects(self):
        if not self.player.get_property("knows_wade"):
            self.parser.ok(
                'Dalton raises an eyebrow. "Wade who? No I.D., no entry, darlin\'."'
            )
            return
        self.player.location.set_property("admitted", True)
        self.parser.ok(
            "Dalton grins. \"Aw heck, any friend o' Wade's a friend o' mine. Stick to "
            "ginger ale -- and if anyone asks, you're the new waitress.\" He stands aside."
        )


class TalkToBartender(actions.Action):
    ACTION_NAME = "talk to bartender"
    ACTION_DESCRIPTION = "See what the harried bartender wants"
    ACTION_ALIASES = [
        "talk to the bartender",
        "speak to bartender",
        "speak to the bartender",
        "ask bartender",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if (
            self.player.location is None
            or self.player.location.name != "The Breakpoint"
        ):
            self.parser.fail("There's no bartender here.")
            return False
        return True

    def apply_effects(self):
        if _is_holding(self.player, "tray"):
            self.parser.ok("\"Quit dawdlin' -- table four's waitin'!\"")
            return
        tray = _item(
            "tray",
            "a tray of drinks",
            "Three longneck bottles, carefully balanced on the tray.",
        )
        self.player.add_to_inventory(tray)
        self.parser.ok(
            "The bartender shoves a loaded tray into your hands without looking up. "
            '"You the new girl? Good. Table four -- the big fella in the leather. GO."'
        )


class ServeTableFour(actions.Action):
    ACTION_NAME = "take tray to table four"
    ACTION_DESCRIPTION = "Carry the tray of drinks to table four"
    ACTION_ALIASES = [
        "bring tray to table four",
        "take the tray to table four",
        "serve table four",
        "give tray to table four",
        "deliver tray",
        "deliver the tray",
        # "table 4" (the numeral) reads the same as "table four"
        "take tray to table 4",
        "bring tray to table 4",
        "take the tray to table 4",
        "serve table 4",
        "give tray to table 4",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if (
            self.player.location is None
            or self.player.location.name != "The Breakpoint"
        ):
            self.parser.fail("There's no table four here.")
            return False
        if not _is_holding(self.player, "tray"):
            self.parser.fail("You've nothing to serve. (Ask the BARTENDER.)")
            return False
        return True

    def apply_effects(self):
        _take_held(self.player, "tray")
        self.player.location.set_property("provoked", True)
        self.parser.ok(
            "You set the drinks at table four. A mountain of a biker lurches up, beer "
            'sloshing down his vest. "You spill on my colors?! Nobody disrespects the '
            'Steel Vipers!" The whole bar goes quiet, waiting. (Best act first.)'
        )


class StartBrawl(actions.Action):
    ACTION_NAME = "punch biker"
    ACTION_DESCRIPTION = "Throw the first punch and start a bar brawl"
    ACTION_ALIASES = [
        "hit biker",
        "punch the biker",
        "hit the biker",
        "smash biker",
        "smash bottle",
        "smash bottle over his head",
        "throw drink",
        "throw drink in his face",
        "deck the biker",
        "start a fight",
        "start a brawl",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player
        self.command = command

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or loc.name != "The Breakpoint":
            self.parser.fail("There's no one here to fight.")
            return False
        if not loc.get_property("provoked"):
            self.parser.fail("Nobody's looking for a fight just yet.")
            return False
        if loc.get_property("brawled"):
            self.parser.fail("The brawl's already in full swing.")
            return False
        return True

    def _opening_blow(self) -> str:
        """The first move, worded to match how the player threw it."""
        cmd = self.command.lower()
        if "throw" in cmd or "drink" in cmd:
            return "You toss a drink in the biker's face"
        if "smash" in cmd or "bottle" in cmd:
            return "You smash a bottle over the biker's head"
        if "deck" in cmd:
            return "You deck the biker with a roundhouse"
        if "punch" in cmd or "hit" in cmd:
            return "You crack the biker across the jaw"
        return "You throw the first punch"

    def apply_effects(self):
        loc = self.player.location
        loc.set_property("brawled", True)
        # You hit the BIKER, so his skull keyring is what's knocked loose -- CATCH
        # it. The ranchers get dragged into the melee too and their truck keys end
        # up on the floor (a separate GET; see CatchKeys' pointer), so that ring
        # is the brawl's doing, not your punch.
        keys = _item(
            "keys",
            "a ring of motorcycle keys",
            "A heavy skull keyring stamped ROCK HARD, RIDE FREE.",
        )
        loc.add_item(keys)
        rancher_keys = _item(
            "rancher keys",
            "a ring of truck keys",
            "A tooled-leather horseshoe fob, branded with the Double-Deuce mark and "
            "stamped RIDE EASY.",
        )
        rancher_keys.add_alias("truck keys")
        rancher_keys.add_alias("horseshoe keys")
        loc.add_item(rancher_keys)
        self.game.award(
            "brawl",
            5,
            f"{self._opening_blow()} and the Breakpoint ERUPTS -- fists, stools, and "
            "longnecks flying. His skull keyring is knocked loose and skitters across "
            "the floor. (Quick -- CATCH KEYS!)",
        )


class CatchKeys(actions.Action):
    ACTION_NAME = "catch keys"
    ACTION_DESCRIPTION = "Snatch the keys loose in the brawl"
    ACTION_ALIASES = ["catch the keys", "grab keys", "grab the keys", "snatch keys"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or "keys" not in loc.items:
            self.parser.fail("There are no keys here to catch.")
            return False
        return True

    def apply_effects(self):
        # CATCH grabs the biker's airborne skull keyring (what your punch knocked
        # loose). The ranchers' fob is left lying on the floor in the melee -- the
        # room listing shows it; the player can notice and GET it on their own.
        loc = self.player.location
        keys = loc.items["keys"]
        loc.remove_item(keys)
        self.player.add_to_inventory(keys)
        self.parser.ok("You grab the skull keys out of the air, quick as a cat.")


class UseKeyOnMotorcycle(actions.Action):
    ACTION_NAME = "use key on motorcycle"
    ACTION_DESCRIPTION = "Start the chopper with the stolen keys"
    ACTION_ALIASES = [
        "use keys on motorcycle",
        "use key on bike",
        "use keys on bike",
        "start the motorcycle",
        "start motorcycle",
        "start the bike",
        "start the chopper",
        "put key in motorcycle",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or "motorcycle" not in loc.items:
            self.parser.fail("There's no motorcycle here.")
            return False
        if not _is_holding(self.player, "keys"):
            if _is_holding(self.player, "rancher keys"):
                self.parser.fail("The horseshoe-fob key doesn't fit the chopper.")
            else:
                self.parser.fail("You don't have any keys.")
            return False
        if loc.items["motorcycle"].vehicle_ready():
            self.parser.fail("The chopper's already running.")
            return False
        return True

    def apply_effects(self):
        self.player.location.items["motorcycle"].set_property("vehicle_ready", True)
        self.parser.ok(
            "You slot the skull key home and thumb the starter. The chopper coughs, "
            "catches, and ROARS to life. (Now GET ON THE MOTORCYCLE and head EAST or "
            "WEST onto the highway.)"
        )


class UseKeyOnTruck(actions.Action):
    ACTION_NAME = "use key on truck"
    ACTION_DESCRIPTION = "Start the pickup truck with the ranchers' keys"
    ACTION_ALIASES = [
        "use keys on truck",
        "use rancher keys on truck",
        "use truck keys on truck",
        "start the truck",
        "start truck",
        "start the pickup",
        "put key in truck",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or "truck" not in loc.items:
            self.parser.fail("There's no truck here.")
            return False
        if not _is_holding(self.player, "rancher keys"):
            if _is_holding(self.player, "keys"):
                self.parser.fail("That skull key doesn't fit the truck's ignition.")
            else:
                self.parser.fail("You don't have any keys.")
            return False
        if loc.items["truck"].vehicle_ready():
            self.parser.fail("The truck's already idling.")
            return False
        return True

    def apply_effects(self):
        self.player.location.items["truck"].set_property("vehicle_ready", True)
        self.parser.ok(
            "You jam the horseshoe-fob key in and crank it. The old truck shudders, "
            "belches blue smoke, and rumbles to life. (Now GET ON THE TRUCK and head "
            "EAST or WEST onto the highway.)"
        )


# The jukebox + the drinks tray: optional Breakpoint flavor. The jukebox gives the
# poacher's silver coins a use (each song costs a coin); every genre just annoys
# half the crowd. None of it affects the win -- pure color.


def _spend_coin(player):
    """Spend one of the poacher's silver coins (from the carried purse). True if
    one was spent; decrements the stack and discards it when empty."""
    coins = player.carried_items().get("silver coins")
    if coins is None or getattr(coins, "quantity", 1) < 1:
        return False
    coins.quantity = getattr(coins, "quantity", 1) - 1
    if coins.quantity <= 0:
        player.discard_item(coins)
    return True


class DrinkBottle(actions.Action):
    """A gag: sneak a sip off the tray you're carrying."""

    ACTION_NAME = "drink bottle"
    ACTION_DESCRIPTION = "Sneak a sip from the tray"
    ACTION_ALIASES = [
        "drink a bottle",
        "drink from the tray",
        "drink from tray",
        "take a sip",
        "sip drink",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        if not _is_holding(self.player, "tray"):
            self.parser.fail("You've nothing to drink.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "You sneak a sip from one of the bottles. Ow -- it burns! Gross. You set "
            "it back on the tray."
        )


class UseCoinOnJukebox(actions.Action):
    """Drop one of the poacher's silver coins in the jukebox, then pick a genre."""

    ACTION_NAME = "use coin on jukebox"
    ACTION_DESCRIPTION = "Put a coin in the jukebox"
    ACTION_ALIASES = [
        "use coins on jukebox",
        "use silver coins on jukebox",
        "put coin in jukebox",
        "put a coin in the jukebox",
        "insert coin",
        "play jukebox",
        "use the jukebox",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or "jukebox" not in loc.items:
            self.parser.fail("There's no jukebox here.")
            return False
        coins = self.player.carried_items().get("silver coins")
        if coins is None or getattr(coins, "quantity", 1) < 1:
            self.parser.fail("You've no coins for the jukebox.")
            return False
        return True

    def apply_effects(self):
        _spend_coin(self.player)
        self.player.location.items["jukebox"].set_property("credit", True)
        self.parser.ok("You drop a silver coin into the jukebox. What'll it be?")
        self.game.pose_prompt(
            Prompt(
                text="Country, blues, or metal? (country / blues / metal)",
                options={
                    "country": "play country",
                    "blues": "play blues",
                    "metal": "play metal",
                },
                speaker="jukebox",
            )
        )


class _PlaySong(actions.Action):
    """Shared base: play a genre once the jukebox has a coin's credit."""

    GENRE = ""
    FLAVOR = ""

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.player = self.game.player

    def check_preconditions(self) -> bool:
        loc = self.player.location
        if loc is None or "jukebox" not in loc.items:
            self.parser.fail("There's no jukebox here.")
            return False
        if not loc.items["jukebox"].get_property("credit"):
            self.parser.fail("Put a coin in the jukebox first (USE COIN ON JUKEBOX).")
            return False
        return True

    def apply_effects(self):
        self.player.location.items["jukebox"].set_property("credit", False)
        self.parser.ok(self.FLAVOR)


class PlayCountry(_PlaySong):
    ACTION_NAME = "play country"
    ACTION_DESCRIPTION = "Play a country song on the jukebox"
    ACTION_ALIASES = ["play country-and-western", "play country and western"]
    FLAVOR = (
        "A twangy, mid-tempo number about drinkin' and horses fills the room. The "
        "bikers boo and holler at you to put on some metal."
    )


class PlayBlues(_PlaySong):
    ACTION_NAME = "play blues"
    ACTION_DESCRIPTION = "Play a blues song on the jukebox"
    FLAVOR = (
        "A slow, sad blues about drinkin' and trains. The whole bar boos and yells "
        "at you to change the song."
    )


class PlayMetal(_PlaySong):
    ACTION_NAME = "play metal"
    ACTION_DESCRIPTION = "Play a metal song on the jukebox"
    FLAVOR = (
        "A loud, fast anthem about leather, motorcycles, and rock 'n' roll. The "
        "ranchers boo and yell at you to put on some country."
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
    outside_tower = L(
        "Outside the Tower",
        "You're partway down the tower's outer wall, clinging to the hair-rope. The "
        "window is just above you; a large rosebush waits far below. You can CLIMB IN "
        "to go back, or LET GO (or JUMP) to drop into the gardens.",
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
        "You're in the Old Woods. The game warden's shack is here.",
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
    highway = L(
        "Highway",
        "Open road, as far as you can see. The wind takes your hair and the kingdom "
        "shrinks in the chrome mirrors behind you.",
    )

    # --- Connections (geography resolved from each room's exit block) ------
    # Castle
    _one_way(tower, "out", tower_stairs)  # the door (locks after a failed escape)
    # The window escape is two steps: CLIMB DOWN onto the rope (-> Outside the
    # Tower), then LET GO / JUMP / DOWN to drop into the Gardens. You can CLIMB IN
    # to go back up -- but once you've dropped, the rope's out of reach from the
    # ground, so Outside -> Gardens is one-way.
    _one_way(tower, "down", outside_tower)  # climb out the window onto the rope
    tower.move_verbs["down"] = "climbs"  # "Princess climbs to Outside the Tower"
    tower.travel_descriptions["down"] = (
        "Hand over hand, you work down the hair-rope to its frayed end, where you "
        "dangle above a large rosebush."
    )
    _one_way(outside_tower, "in", tower)  # climb back in through the window
    outside_tower.move_verbs["in"] = "climbs"
    outside_tower.travel_descriptions["in"] = (
        "You haul yourself back up and in through the window."
    )
    _one_way(outside_tower, "down", gardens)  # let go / jump -> drop into the gardens
    outside_tower.move_verbs["down"] = "falls"  # "Princess falls to Gardens"

    def _worn_feet(player):
        """The footwear she's wearing as she drops, or None if barefoot."""
        return next(
            (
                it
                for it in player.worn.values()
                if it.get_property("wear_slot") == "feet"
            ),
            None,
        )

    def _describe_fall(g):
        """The drop's narration, generated from what she's wearing: the gown only
        'takes the brunt' if she's in it, and her feet fare differently in glass,
        boots, or bare. Paired with the fall_into_rosebush trigger, which makes
        the state match (tears the gown, shatters the slippers, marks her)."""
        p = g.player
        parts = ["You let go, crashing into the thorny rosebush."]
        if "gown" in p.worn:
            parts.append(
                "It breaks your fall and your voluminous gown takes the brunt -- "
                "torn to ribbons, but you've only a few scratches."
            )
        else:
            parts.append(
                "It breaks your fall, but with no gown to shield you the thorns "
                "rake your arms and shoulders raw."
            )
        feet = _worn_feet(p)
        if feet is None:
            parts.append("Your bare feet land hard, left tender and bruised.")
        elif feet.name == "glass slippers":
            parts.append(
                "The glass slippers shatter on impact, shards slicing your soles."
            )
        elif feet.name == "boots":
            parts.append(
                "Your army boots hit the dirt with a thud and a puff of dust -- "
                "your feet, at least, are fine."
            )
        else:
            parts.append(
                f"Luckily the {feet.name} cushion the landing -- your feet are fine."
            )
        return " ".join(parts)

    outside_tower.travel_descriptions["down"] = _describe_fall
    _one_way(tower_stairs, "enter", tower)
    tower_stairs.add_connection("down", guardroom)  # auto: guardroom up -> stairs
    # The drawbridge is the castle gate, between the Guardroom (inside) and the
    # bridge/outer grounds. It starts RAISED (she's a prisoner, the castle is
    # sealed): WEST out of the guardroom and EAST back in are both barred until
    # the winch lowers it. The front gate is still a trap -- lower the bridge,
    # bolt across, and the guard marches you back (trigger below) and hauls it up
    # again -- so the real way out is the tower window. Once she's out (caught
    # then escaped, or straight out the window) the bridge stays up: "returning
    # to the castle is out of the question" (rulebook p9).
    drawbridge.set_property("raised", True)
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
    # The Old Woods -> Deep Woods link stays connected (so Deep Woods + the rooms
    # beyond it are reachable/indexed), but a bare "north" is always blocked (see
    # FollowDeerBlock below): the only way in is FOLLOW DEER, which leads you down
    # a hidden path (the FollowDeer action relocates directly, bypassing the block).
    _one_way(old_woods, "north", deep_woods)
    _one_way(deep_woods, "south", old_woods)
    _one_way(deep_woods, "north", clearing)  # opens once the poacher is dealt with
    # Clearing / ranch / road (diagonals -> one-way both sides)
    clearing.add_connection("west", dirt_road)  # auto: dirt_road east -> clearing
    _one_way(clearing, "southwest", ranch)
    _one_way(ranch, "northeast", clearing)
    ranch.add_connection("north", dirt_road)  # auto: dirt_road south -> ranch
    dirt_road.add_connection("north", roadhouse)  # auto: roadhouse south -> dirt_road
    # Roadhouse / bar / highway
    _one_way(roadhouse, "enter", breakpoint)  # gated by Dalton until "Wade sent me"
    _one_way(breakpoint, "out", roadhouse)
    # The highway runs east-west: either direction rides out onto the open road
    # (the +50 ending). Both are one-way (no coming back) and gated on actually
    # being astride the started motorcycle. The Rancher ending, by contrast, is
    # pure dialog (SAY YES) -- no travel -- so it stays an action effect.
    _one_way(roadhouse, "east", highway)
    _one_way(roadhouse, "west", highway)

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
    # rope tied off. The door route (OUT -> Tower Stairs) is open until the guard
    # marches you back and locks it (see the guard trigger below); once locked,
    # the only way out is the window -- and only if you grabbed the dagger first.
    class RopeBlock(blocks.Block):
        def __init__(self, tower):
            super().__init__(
                "No way down", "It's a long way down -- you'd need a rope to climb."
            )
            self.tower = tower

        def is_blocked(self) -> bool:
            return not self.tower.get_property("rope_tied")

    tower.add_block("down", RopeBlock(tower))

    class LockedDoorBlock(blocks.Block):
        def __init__(self, tower):
            super().__init__(
                "The door is locked",
                "You grab the iron ring and pull, but the guard has locked the door "
                "from the outside. The window is your only way out now.",
            )
            self.tower = tower

        def is_blocked(self) -> bool:
            return bool(self.tower.get_property("door_locked"))

    tower.add_block("out", LockedDoorBlock(tower))

    # The drawbridge gates the castle gate both ways while it's raised: you can't
    # bolt WEST out of the guardroom, and you can't come back EAST into the castle.
    # (It gates only this crossing -- the outer grounds stay connected, so a raised
    # bridge is never a dead-end.)
    class DrawbridgeRaisedBlock(blocks.Block):
        def __init__(self, drawbridge, message):
            super().__init__("The drawbridge is raised", message)
            self.drawbridge = drawbridge

        def is_blocked(self) -> bool:
            return bool(self.drawbridge.get_property("raised"))

    guardroom.add_block(
        "west",
        DrawbridgeRaisedBlock(
            drawbridge,
            "The drawbridge is hauled up. You'll have to lower it first -- there's "
            "a great winch here in the guardroom.",
        ),
    )
    drawbridge.add_block(
        "east",
        DrawbridgeRaisedBlock(
            drawbridge,
            "The drawbridge is hauled up, sealing the castle gate -- there's no way "
            "back inside.",
        ),
    )

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

    # A bare "north" never walks you into the Deep Woods -- the doe leads you down
    # a hidden path, so FOLLOW DEER (which relocates directly, bypassing this
    # block) is the only way in. Keeps you from blundering into the lethal poacher
    # confrontation unprepared.
    class FollowDeerBlock(blocks.Block):
        def __init__(self):
            super().__init__(
                "A hidden path",
                "The doe bounds off down a hidden path. You'll have to FOLLOW DEER "
                "(you'll need the horse) to chase her into the Deep Woods.",
            )

        def is_blocked(self) -> bool:
            return True

    old_woods.add_block("north", FollowDeerBlock())

    # The Deep Woods north exit (-> Clearing) is barred until the poacher is
    # dealt with (you can't ride past while he stalks the deer).
    class PoacherBlock(blocks.Block):
        def __init__(self, woods):
            super().__init__(
                "The poacher",
                "You can't ride on while the poacher still stalks the deer.",
            )
            self.woods = woods

        def is_blocked(self) -> bool:
            return not self.woods.get_property("poacher_dealt")

    deep_woods.add_block("north", PoacherBlock(deep_woods))

    # Dalton bars the bar until you've said "Wade sent me" (SAY WADE SENT ME,
    # which needs you to have met Wade and turned down the ranch job).
    class DaltonBlock(blocks.Block):
        def __init__(self, roadhouse):
            super().__init__(
                "Dalton",
                "Dalton blocks the door. \"Hold up, darlin' -- the Breakpoint's "
                "twenty-one and over. Let's see some I.D.\" He doesn't budge.",
            )
            self.roadhouse = roadhouse

        def is_blocked(self) -> bool:
            return not self.roadhouse.get_property("admitted")

    roadhouse.add_block("enter", DaltonBlock(roadhouse))

    # You can only ride onto the highway astride the *started* motorcycle -- not
    # on foot, and not on the horse (the rulebook's "you need a motor vehicle").
    class OnMotorcycleBlock(blocks.Block):
        def __init__(self, game_ref):
            super().__init__(
                "No wheels",
                "You'll need a motor vehicle to take the highway. (Start the "
                "MOTORCYCLE or the TRUCK, then GET ON it.)",
            )
            self.game_ref = game_ref

        def is_blocked(self) -> bool:
            player = self.game_ref["game"].player
            riding = getattr(player, "riding", None)
            return riding is None or riding.name not in ("motorcycle", "truck")

    # The Game isn't built yet; hand the block a holder we fill in below.
    _game_ref = {}
    roadhouse.add_block("east", OnMotorcycleBlock(_game_ref))
    roadhouse.add_block("west", OnMotorcycleBlock(_game_ref))

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
    # A reflective mirror: EXAMINE MIRROR composes a live reflection of whoever
    # looks (their appearance + what they're wearing), so it tracks the haircut
    # and the gown/boots instead of going stale. See Character.reflection.
    mirror = _fixture(
        "mirror", "a mirror", "A tall mirror in a tarnished silver frame."
    )
    mirror.set_property("is_mirror", True)
    tower.add_item(mirror)
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
    glass_slippers = _footwear(
        "glass slippers",
        "a pair of glass slippers",
        "You cram your size 9's inside the tortuous footwear. If you step lightly, "
        "it doesn't hurt... much.",
        "Glass? Yes, glass.",
    )
    ruby_slippers = _footwear(
        "ruby slippers",
        "a pair of ruby slippers",
        "You click your heels together. It does not send you back to Kansas.",
        "There's no place like home? I guess.",
    )
    tower.add_item(glass_slippers)
    tower.add_item(ruby_slippers)
    # The cot is an open container concealing the boots: they're not listed in
    # the room ("look"), but EXAMINE ARMY COT reveals them under the mattress
    # (contents_relation), and the listing self-updates once they're taken.
    cot = _fixture(
        "army cot", "an army cot", "A grubby army cot with a stained mattress."
    )
    cot.add_alias("cot")  # so "examine cot" works, not just "examine army cot"
    cot.make_container()
    cot.set_property("contents_relation", "Under the stained mattress you see")
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
    # Named "boots" so GET/WEAR BOOTS work as well as "army boots". They live
    # inside the cot (under the mattress), revealed by examining it.
    boots = _footwear(
        "boots",
        "a pair of old army boots",
        "You lace up the army boots. Now you can actually walk.",
        "A little big, but your feet aren't petite.",
    )
    cot.add_item(boots)
    guardroom.add_item(cot)
    # The drawbridge winch -- LOWER / RAISE DRAWBRIDGE work it (see _WorkWinch).
    winch = _fixture(
        "winch",
        "a great iron winch",
        "A great iron winch wound with chain -- this is what raises and lowers the "
        "castle drawbridge. Try LOWER DRAWBRIDGE.",
    )
    winch.add_alias("crank")
    winch.add_alias("windlass")
    winch.add_alias("drawbridge winch")
    guardroom.add_item(winch)
    rosebushes = _fixture(
        "rosebushes",
        "thorny rosebushes",
        "Thorny and covered with roses of every color.",
    )
    # The roses aren't used for anything (rulebook), but the bush is covered in
    # them -- so PICK ROSE should pluck one (pure flavor + the SMELL ROSE gag),
    # not report the bush "bare". HAS_ROSE enables the built-in Pick_Rose action.
    rosebushes.set_property(Property.HAS_ROSE, True)
    gardens.add_item(rosebushes)
    gardens.add_item(
        _fixture("fruit trees", "apple trees", "Branches heavy with ripe red apples.")
    )
    gardens.add_item(
        _fixture(
            "watermelon vines",
            "watermelon vines",
            "Fat, ripe watermelons swelling on the vine near the tower's base.",
        )
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
    # The river doubles as a mirror -- EXAMINE RIVER (or WATER) gives back a live
    # reflection. It's the only reflective surface past the tower, so it's where
    # she sees what the fall did: shorn hair, scratches, the torn gown, her feet.
    river_water = _fixture(
        "river",
        "the slow-moving river",
        "The slow water gives back a wavering reflection.",
    )
    river_water.add_alias("water")
    river_water.set_property("is_mirror", True)
    river.add_item(river_water)
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
    sign = _fixture(
        "sign",
        "a signpost",
        "North to the Breakpoint Bar & Grill, south to the Double-Deuce Ranch.",
    )
    # READ SIGN shows its lettering (the same directions you'd examine).
    sign.set_property(
        Property.READ_TEXT,
        "North to the Breakpoint Bar & Grill, south to the Double-Deuce Ranch.",
    )
    dirt_road.add_item(sign)
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

    # The ranchers' pickup -- the other way out, started by the horseshoe-fob keys.
    truck = _fixture(
        "truck",
        "a rusty pickup truck",
        "An old rustbucket -- creaky springs, bald tires, a gun rack in the back window.",
    )
    truck.add_alias("pickup")
    truck.add_alias("pickup truck")
    truck.make_vehicle(ready=False)
    truck.set_property("ride_verb", "drives")  # "Princess drives the truck to ..."
    truck.set_property("mount_refusal_message", "The truck won't start without a key.")
    roadhouse.add_item(truck)

    # --- Characters --------------------------------------------------------
    player = things.Character(
        "princess",
        "the Princess of Action Castle, in a sparkly gown and tiara",
        "I am the princess, and I am getting out of this tower.",
    )
    # Physical traits the mirror reflects (CUT HAIR rewrites "hair" live). Clothing
    # isn't listed here -- the mirror reads `worn`, so the gown/tiara/boots track
    # themselves.
    player.appearance = {
        "hair": "Your hair is staggeringly long -- it drags on the floor behind you.",
        "feet": "Your feet are bare.",  # synced to footwear by a trigger below
    }

    prince = things.Character(
        "prince",
        "a well-dressed young prince with a paintbrush",
        "I am a prince on a quest; first, I must paint.",
    )
    prince.talk_text = '"Good day, m\'lady! What a delightful view! So fortunate I packed my art supplies before my quest."'
    _prince_quest_line = '"I\'ve traveled many leagues to rescue the princess from yon tower. But first, I must paint!"'
    prince.talk_topics = {
        "quest": _prince_quest_line,
        "art": _prince_quest_line,  # "talk to prince about art" -> the quest line
        "tower": '"Yon tower is where the princess sleeps for all eternity, cursed by an evil witch\'s spell... or something."',
        "princess": '"I hear she is beautiful -- rose lips, flaxen hair, and delicate feet like an elf maid."',
    }
    # The deer is a passive creature you observe and chase, not someone you talk
    # to -- so it's an Item fixture (gettable=False), like the horse, not a
    # Character. It grazes in the Old Woods and bolts to the Deep Woods when you
    # emerge from the warden's shack (see the deer_flees trigger).
    deer = things.Item(
        "deer",
        "a beautiful doe",
        "The beautiful doe is grazing and doesn't appear to notice you.",
    )
    deer.set_property("gettable", False)
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
    dalton.talk_text = (
        '"Howdy, Princess. Name\'s Dalton." He leans off the doorframe. "The '
        "Breakpoint's twenty-one and over, though -- I'll need to see some I.D.\""
    )
    dalton.talk_topics = {
        # The "wade" hint points at the SAY WADE SENT ME gate.
        "wade": '"Wade, eh? Well now -- if *Wade* sent you, that\'d be a different story. Just say the word."',
        "id": "\"No I.D., no entry, darlin'. Them's the rules.\"",
        "bar": '"The Breakpoint? Rowdiest joint this side of the highway -- bikers, ranchers, and trouble."',
    }
    bartender = things.Character(
        "bartender", "the Breakpoint's bartender", "I tend bar and I am very busy."
    )
    # The crowd the rulebook puts in the bar: bikers and ranchers, the two
    # factions whose feud the brawl sets off. They don't take turns of their own
    # -- they react to the jukebox and the brawl in the scripted narration -- but
    # they're present people you can see, examine, and (fruitlessly) talk to.
    bikers = things.Character(
        "bikers",
        "a pack of leather-clad bikers",
        "We're the Steel Vipers. We ride, we drink, and we don't make small talk.",
    )
    bikers.examine_text = "The Steel Vipers -- all leather, chrome, and attitude, hogging the back tables."
    bikers.talk_text = '"Beat it, princess," one grunts without looking up.'
    ranchers = things.Character(
        "ranchers",
        "a knot of weathered ranchers",
        "We work the land hereabouts, miss. Don't want no trouble.",
    )
    ranchers.examine_text = (
        "Sunburnt ranch hands in dusty hats, nursing their beers along the bar."
    )
    ranchers.talk_text = "The ranchers just tip their hats and go back to their drinks."

    river.add_character(prince)
    old_woods.add_item(deer)
    deep_woods.add_character(poacher)
    ranch.add_character(rancher)
    roadhouse.add_character(dalton)
    breakpoint.add_character(bartender)
    breakpoint.add_character(bikers)
    breakpoint.add_character(ranchers)

    # --- Start state: the princess wears a gown and a tiara ----------------
    gown = _item(
        "gown",
        "a sparkly gown",
        "Much layers. So sparkle. It weighs almost as much as you.",
    )
    gown.set_property(Property.WEARABLE, True)
    gown.set_property("wear_slot", "body")
    tiara = _item("tiara", "a jeweled tiara", "Pretty, but pinchy.")
    tiara.set_property(Property.WEARABLE, True)
    tiara.set_property("wear_slot", "head")
    player.inventory["gown"] = gown
    player.inventory["tiara"] = tiara
    player.wear(gown)
    player.wear(tiara)

    characters = [prince, poacher, rancher, dalton, bartender]  # deer is an Item
    custom_actions = [
        CutHair,
        TieRope,
        LetGo,
        LowerDrawbridge,
        RaiseDrawbridge,
        KillSelf,
        PickApple,
        EatApple,
        PickWatermelon,
        GiveAppleToHorse,
        BrushHorse,
        BrushHair,
        FollowDeer,
        ShootPoacher,
        GiveHorseToRancher,
        SayYes,
        SayNo,
        SayWadeSentMe,
        TalkToBartender,
        ServeTableFour,
        StartBrawl,
        CatchKeys,
        UseKeyOnMotorcycle,
        UseKeyOnTruck,
        DrinkBottle,
        UseCoinOnJukebox,
        PlayCountry,
        PlayBlues,
        PlayMetal,
    ]
    game = ActionCastle4(tower, player, characters, custom_actions)
    _game_ref["game"] = game  # back-fill the OnMotorcycleBlock's Game handle

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
        lambda g: "boots" in g.player.worn and "boots" not in g._scored_keys,
        lambda g: g.award("boots", 5, "Properly shod for the road ahead."),
        repeatable=True,
    )

    # Keep the mirror's "feet" line honest: bare while unshod, silent once she's
    # wearing footwear (the boots/slippers then show up in the "wearing ..."
    # line). Fires only when the line is out of sync with what's on her feet.
    def _feet_line(g):
        shod = any(
            it.get_property("wear_slot") == "feet" for it in g.player.worn.values()
        )
        return "" if shod else "Your feet are bare."

    game.add_trigger(
        "sync_feet_reflection",
        lambda g: g.player.appearance.get("feet") != _feet_line(g),
        lambda g: g.player.appearance.__setitem__("feet", _feet_line(g)),
        repeatable=True,
    )

    # You've genuinely escaped only by climbing out the window into the Gardens
    # (the one room reachable solely via the rope). Marking it here lets the
    # guard trigger tell a real escape from a doomed break for the front gate.
    def _mark_escaped(g):
        g.player.set_property("escaped", True)
        # The castle seals behind her -- if she'd lowered the drawbridge on a
        # front-gate attempt, it goes back up now ("no return", rulebook p9).
        drawbridge.set_property("raised", True)

    game.add_trigger(
        "mark_escaped",
        lambda g: g.player.location is gardens and not g.player.get_property("escaped"),
        _mark_escaped,
        repeatable=True,
    )

    # The drop leaves its mark: make the state match _describe_fall's narration.
    # The gown (if worn) is shredded; the glass slippers shatter and cut her;
    # bare feet bruise; boots spare her. feet_injury is a separate appearance
    # key so the sync_feet_reflection trigger (which owns "feet") can't clobber
    # it. Once, on the first landing.
    def _fall_damage(g):
        p = g.player
        p.set_property("fell", True)
        if "gown" in p.worn:
            gown = p.worn["gown"]
            gown.description = "a gown torn to ribbons"
            gown.examine_text = (
                "Your once-sparkly gown, shredded to ribbons by the rosebush."
            )
            p.appearance["marks"] = "Your arms and shoulders are lightly scratched."
        else:
            p.appearance["marks"] = (
                "Your arms and shoulders are raw and badly scratched."
            )
        feet = _worn_feet(p)
        if feet is None:
            p.appearance["feet_injury"] = (
                "Your soles ache, tender and bruised from the hard landing."
            )
        elif feet.name == "glass slippers":
            p.worn.pop("glass slippers")  # shattered -- gone
            p.appearance["feet_injury"] = (
                "Your soles are cut and bleeding from the broken glass."
            )
            # Cut feet change her gait: she LIMPS on foot from here on (the
            # arrival line reads "Princess limps to ..."). It only shows while
            # walking -- once she's on the horse or motorcycle the riding line
            # takes over. Pure flavor, the gag's just reward for glass footwear.
            p.set_property("move_verb", "limps")
        # boots / other footwear: no lasting injury

    game.add_trigger(
        "fall_into_rosebush",
        lambda g: g.player.location is gardens and not g.player.get_property("fell"),
        _fall_damage,
        repeatable=True,
    )
    game.add_trigger(
        "score_escape",
        lambda g: g.player.get_property("escaped") and "escape" not in g._scored_keys,
        lambda g: g.award("escape", 5, "You're free of that blasted tower!"),
        repeatable=True,
    )

    # The guard is waiting at the bridge. Bolt out the front (Guardroom WEST ->
    # Drawbridge) without having slipped out the window and he marches you back
    # upstairs and locks the door behind you (rulebook p7). If you never grabbed
    # the dagger, that lock is fatal -- see the trapped-forever trigger.
    def _guard_catches(g):
        g.parser.ok(
            "You make a break for it across the bridge -- and run smack into the "
            "tower's guard. \"Hey! What are you doing sneaking around? Back to your "
            "chambers at once!\" You're marched upstairs, the door locks behind you, "
            "and the drawbridge is hauled up with a clatter of chains -- the guards "
            "bar themselves inside."
        )
        tower.set_property("door_locked", True)
        drawbridge.set_property("raised", True)
        _relocate(g, g.player, "Tower")

    game.add_trigger(
        "guard_catches_at_bridge",
        lambda g: g.player.location is drawbridge
        and not g.player.get_property("escaped"),
        _guard_catches,
        repeatable=True,
    )

    # Locked back in the tower with no way to cut your hair = the "nineteen years"
    # ending (rulebook p5): no dagger, no hair, no rope means no window escape.
    def _has_escape_means(g):
        held = _all_held(g.player)
        return (
            _is_holding(g.player, "dagger")
            or g.player.get_property("hair_cut")
            or "hair" in held
            or "rope" in held
        )

    game.add_trigger(
        "trapped_forever",
        lambda g: tower.get_property("door_locked")
        and g.player.location is tower
        and not g.player.get_property("escaped")
        and not _has_escape_means(g),
        lambda g: _die(
            g,
            "The door is locked and you've nothing to cut your hair with. Someday your "
            "prince may come, you tell yourself -- and you spend the next nineteen "
            "years brushing your hair. THE END.",
        ),
        repeatable=True,
    )
    deep_woods = game.locations["Deep Woods"]
    game.add_trigger(
        "score_purse",
        lambda g: _is_holding(g.player, "coin purse") and "purse" not in g._scored_keys,
        lambda g: g.award("purse", 5, "You pocket the poacher's coin purse."),
        repeatable=True,
    )

    # Finale scoring (rulebook page 19): mounting the mare +5, getting inside the
    # Breakpoint +5. (Gifting the horse +5 and starting the brawl +5 are awarded
    # in their actions.)
    game.add_trigger(
        "score_horse",
        lambda g: getattr(g.player, "riding", None) is not None
        and g.player.riding.name == "horse"
        and "horse" not in g._scored_keys,
        lambda g: g.award("horse", 5, "You swing up into the saddle."),
        repeatable=True,
    )
    game.add_trigger(
        "score_roadhouse",
        lambda g: g.player.location is not None
        and g.player.location.name == "The Breakpoint"
        and "roadhouse" not in g._scored_keys,
        lambda g: g.award("roadhouse", 5, "You're inside the Breakpoint."),
        repeatable=True,
    )

    # The Highway ending (+50, the best run): reaching the Highway means you rode
    # out astride the started bike (the exits are gated). Award + finish + end.
    def _ride_off(g):
        g.player.set_property("rode_the_highway", True)
        g.award("highway", 50)
        g.award("finish", 5)
        riding = getattr(g.player, "riding", None)
        if riding is not None and riding.name == "truck":
            lead = (
                "The old truck rattles out onto the blacktop, bald tires singing, and "
                "the Breakpoint shrinks in the cracked mirror"
            )
        else:
            lead = (
                "You open the throttle and the chopper howls; the Breakpoint vanishes "
                "behind you"
            )
        ending = (
            f"{lead}. No tower, no curse, no prince -- just you, the open road, and "
            "the whole wide world. You ride off into your own happily-ever-after. THE END."
        )
        g.parser.ok(ending)
        g.game_over = True
        g.game_over_description = ending

    game.add_trigger(
        "highway_ending",
        lambda g: g.player.location is not None
        and g.player.location.name == "Highway"
        and not g.game_over,
        _ride_off,
        repeatable=True,
    )

    # The grazing doe is skittish: a noise in the Old Woods sends her bolting into
    # the Deep Woods. Two kinds of noise spook her -- the shack door banging shut
    # as you step out (tracked via visited_shack), and any loud action you take in
    # the woods (talking/yelling, smashing -- see _NOISY_ACTIONS). Quiet things
    # leave her be, so a careful player can slip in for the crossbow first; a
    # careless one spooks her early and chases unarmed. No timer on the flee
    # itself -- the poacher's clock only starts when YOU reach the Deep Woods.
    game.add_trigger(
        "note_shack_visit",
        lambda g: g.player.location is old_shack
        and not g.player.get_property("visited_shack"),
        lambda g: g.player.set_property("visited_shack", True),
        repeatable=True,
    )

    # The shack door bangs shut the first time you step back out into the Old
    # Woods -- an ambient noise the door emits (the source owns its volume), which
    # the doe's startle reaction hears. Registered BEFORE the doe's reaction so,
    # in the same react phase, the sound is logged before she listens for it.
    game.add_trigger(
        "shack_door_bang",
        lambda g: g.player.location is old_woods
        and g.player.get_property("visited_shack"),
        lambda g: g.emit_sound(old_woods, 1, "the shack door bangs shut behind you"),
        repeatable=False,  # bangs once
    )

    # The doe bolts at any noise she hears in the Old Woods; the poacher's clock
    # starts the instant she's driven into his clearing. Both are thing-owned
    # reactions (see DoeFlees / PoacherShoots above) evaluated in the react phase.
    game.add_reaction(deer, DoeFlees(to=deep_woods))
    game.add_reaction(poacher, PoacherShoots(quarry=deer))

    # --- Room descriptions that track state -------------------------------------
    # Some rooms would otherwise hardcode transient details -- a crossbow on the
    # wall, a poacher stalking the deer, a horse tethered by the river. Each gets
    # a small function that regenerates its description from the current state,
    # kept in sync by a trigger (the same self-syncing pattern as the mirror's
    # feet line). The transient *objects* are already listed dynamically under
    # "You see:" / "Characters:"; these conditionals keep the prose honest too.
    def _sync_description(name, loc, fn):
        game.add_trigger(
            name,
            lambda g, loc=loc, fn=fn: loc.description != fn(g),
            lambda g, loc=loc, fn=fn: setattr(loc, "description", fn(g)),
            repeatable=True,
        )

    def _shack_desc(g):
        if "crossbow" in old_shack.items:
            return "The game warden's shack. There's a crossbow here."
        return "The game warden's shack -- bare pegs on the wall where a crossbow once hung."

    def _deep_woods_desc(g):
        if deep_woods.get_property("poacher_dealt"):
            return (
                "Primordial forest, the canopy thick overhead. The trees are still "
                "now -- the poacher gone, the doe safe."
            )
        return (
            "Primordial forest, the canopy thick overhead. A cloaked figure stalks "
            "the deer through the trees."
        )

    def _river_desc(g):
        if "horse" in river.items:
            return (
                "Down by the river, a white mare is tethered to a tree and a young "
                "man paints at an easel. The drawbridge is north."
            )
        return "Down by the river, a young man paints at an easel. The drawbridge is north."

    def _drawbridge_desc(g):
        base = (
            "A bridge spans the river. A path heads north to the gardens and south "
            "along the river. The Old Woods lie west."
        )
        # The raised/lowered castle gate (the drawbridge feature). Guarded so this
        # stays the plain base description until that feature wires the east exit.
        if drawbridge.get_property("raised"):
            return (
                base
                + " The drawbridge is hauled up, sealing the castle gate to the east."
            )
        if "east" in drawbridge.connections:
            return base + " The lowered drawbridge leads east into the castle."
        return base

    def _breakpoint_desc(g):
        if breakpoint.get_property("brawled"):
            return (
                "The Breakpoint Bar & Grill -- a full-blown brawl underway, chairs "
                "and bottles flying. A jukebox blares in the corner."
            )
        return (
            "The Breakpoint Bar & Grill -- rowdy and packed with bikers and ranchers. "
            "There's a jukebox here, and a bartender tending bar."
        )

    _sync_description("sync_shack_desc", old_shack, _shack_desc)
    _sync_description("sync_deep_woods_desc", deep_woods, _deep_woods_desc)
    _sync_description("sync_river_desc", river, _river_desc)
    _sync_description("sync_drawbridge_desc", drawbridge, _drawbridge_desc)
    _sync_description("sync_breakpoint_desc", breakpoint, _breakpoint_desc)

    return game


# ---------------------------------------------------------------------------
# Walkthrough: the 100-point winning run (sneak out -> tame the mare -> deal
# with the poacher -> gift the horse, decline the job -> the bar -> ride off).
# ---------------------------------------------------------------------------

WALKTHROUGH_WIN = [
    # Grab the dagger + boots from the guardroom -- but the front gate is a trap
    # (the guard marches you back), so escape out the tower window on a hair rope.
    "out",  # Tower -> Tower Stairs
    "down",  # -> Guardroom              (+5 guardroom)
    "open footlocker",
    "take dagger",  # needed to cut your hair (and to avoid being trapped)
    "examine army cot",  # reveals the boots under the mattress
    "take boots",
    "wear boots",  # (+5 boots)
    "up",  # -> Tower Stairs
    "enter",  # -> Tower
    "cut hair",  # the dagger shears off your hair (it falls to the floor)
    "get hair",  # pick the shorn hair up off the floor
    "make rope",  # crafting: hair -> rope
    "tie rope",  # tie it to the door's iron ring
    "climb down",  # out the window onto the rope -> Outside the Tower
    "let go",  # drop into the Gardens             (+5 escape)
    # Tame the skittish mare with an apple from the gardens.
    "pick apple",
    "south",  # -> Drawbridge (the guard ignores you now -- you're already out)
    "south",  # -> Down by the River
    "give apple to horse",  # tames the mare
    "get on horse",  # (+5 horse)
    # Ride to the woods; the warden's shack has the crossbow.
    "north",  # -> Drawbridge
    "west",  # -> Old Woods (vehicle-gated; ok, mounted)
    "dismount",
    "enter",  # -> Old Shack
    "take crossbow",
    "out",  # -> Old Woods
    "get on horse",
    "follow deer",  # -> Deep Woods (the only way in; the poacher stalks the deer)
    "shoot poacher",  # (+5 shoot) -- drops a coin purse + cloak
    "take coin purse",  # (+5 purse)
    "north",  # -> Clearing
    "southwest",  # -> Ranch
    # Gift the mare; turn down the job so Wade sends you to the roadhouse.
    "give horse to rancher",  # (+5 gift_horse) -- poses the yes/no offer
    "say no",  # learn "Wade sent me"
    "north",  # -> Dirt Road
    "north",  # -> Roadhouse
    "say wade sent me",  # Dalton admits you
    "enter",  # -> The Breakpoint        (+5 roadhouse)
    # Wait a table, start the brawl, grab the keys that fly loose.
    "talk to bartender",  # get a tray
    "take tray to table four",  # provoke the biker
    "punch biker",  # (+5 brawl) -- keys skitter loose
    "catch keys",
    "out",  # -> Roadhouse
    # Start the chopper and ride off down the highway.
    "use key on motorcycle",
    "get on motorcycle",
    "east",  # -> Highway                (+50 highway, +5 finish) -- THE END
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
        _run(WALKTHROUGH_WIN)
    else:
        build_game().game_loop()
