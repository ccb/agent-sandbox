"""Action Castle II — "Return to Action Castle" — on the text_adventure_games engine.

A faithful port of the Parsely game (Action Castle II) to our engine, authored the
same way as ``action_castle.py`` (its sibling in this package): a ``build_game()`` that
assembles locations / items / characters, a small ``ActionCastle2`` Game subclass
holding the win condition + score, a handful of custom ``Action`` subclasses for the
genuinely novel verbs (including the multi-word gift verbs ``GIVE X TO Y`` /
``DROP PENNY IN WELL``, which the specific-first parser routes ahead of the
built-in ``give``/``drop``), one following-NPC behavior (Rosemary), and a few
reaction *triggers* (smith sharpens the axe, the dragon stirs/kills, scoring).

DIALOGUE FORKS use posed prompts (engine #110, ``prompts.py``): where the game
asks a question -- the dragon's "wits or steel?", its riddle, the reward choice,
the king's "do you accept?" -- it poses a Prompt so a bare ``wits`` / ``a wise
man`` / ``sword`` / ``yes`` answers it. The explicit verbs (``CHOOSE WITS``,
``ANSWER RIDDLE ...``, ``SAY YES``) still work; the prompt just spares the player
from having to know them, which is why the parenthetical syntax hints are gone.

Run interactively:   python action_castle_2.py
Run the walkthrough:  python action_castle_2.py --walk        (champion ending)
                      python action_castle_2.py --walk-marry  (marriage ending)
"""

from text_adventure_games import games, things, actions, reactions, Prompt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Locations Rosemary/Sage refuses to enter while following (south of the Old
# Pond, and anywhere inside the castle east of the Bend) -- see ACII pages 35/37.
ROSEMARY_NO_FOLLOW = {
    "Outside Hermit's Cave",
    "Cave",
    "Action Castle",
    "Moat",
    "Underground",
    "Treasure Trove",
    "Dungeon",
    "Dungeon Stairs",
    "Courtyard",
    "Throne Room",
}

# The cave is never enterable (rulebook). Shared by the CaveBlock (on "go in")
# and the EnterCave action (the literal "enter cave" verb).
CAVE_TOO_DARK = "It's too dark and scary in there. Also: It smells."


def _relocate(game, character, dest_name):
    """Move *character* to the location named *dest_name*, dragging any followers
    along (so rowing out to the pond carries Rosemary with you). Routes through
    the engine's relocate/drag_followers chokepoint."""
    dest = game.locations[dest_name]
    game.relocate(character, dest)
    game.drag_followers(character)
    return dest


def _die(game, text):
    """End the game with a death/THE END message (the conditional-death path).
    Thin wrapper over the engine's ``Game.end_in_death`` so existing call sites
    keep their short local name."""
    game.end_in_death(text)


def _all_held(character):
    """Everything the character is holding: inventory + worn + wielded.

    The engine's WEAR/WIELD actions *move* an item out of ``inventory`` into
    ``worn``/``wielded``, so a quest check that only inspects ``inventory`` would
    wrongly conclude the player no longer has it (e.g. WIELD SWORD then get
    arrested in the courtyard, or WEAR SLIPPERS then be unable to gift them). We
    treat "held" as the union of all three everywhere the game asks "do you have
    X?".
    """
    return {**character.inventory, **character.worn, **character.wielded}


def _is_holding(character, name):
    """True if the character is carrying/wearing/wielding an item by name."""
    return name in _all_held(character)


def _take_held(character, name):
    """Remove and return a held item by name from wherever it lives, else None."""
    for store in (character.inventory, character.worn, character.wielded):
        if name in store:
            return store.pop(name)
    return None


def _has_item_with(character, prop):
    """True if the character holds any item with the given property set."""
    return any(item.get_property(prop) for item in _all_held(character).values())


def _one_way(frm, direction, to):
    """Add a connection WITHOUT add_connection()'s canonical auto-reverse.

    add_connection() always wires the opposite direction back on the far side
    (out<->in, north<->south, ...). For the town's convenience "out" verbs that
    is a footgun: the workshop, smithy, and town hall all leave via "out" to the
    Town Square, so each would try to claim ``town_square["in"]`` as its reverse
    -- they collide, the last one wins, and the others' return paths vanish (the
    old "In to Smithy" junk + the unreachable workshop). Writing the exit
    directly keeps it one-way, so only the workshop owns ``town_square["in"]``.
    """
    frm.connections[direction] = to
    frm.travel_descriptions[direction] = ""


# ---------------------------------------------------------------------------
# Game subclass: win condition + scoring
# ---------------------------------------------------------------------------


class ActionCastle2(games.Game):
    """Won by becoming the king's champion OR by marrying Rosemary/Sage."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        # Scoring per the ACII rulebook (page 18): 16 locations x2 = 32, + wish 3
        # + blanket 10 + slippers 10 + catfish 10 + riddle 10 + (champion OR
        # propose) 20 + finishing-without-saving 5 = 100. Champion and propose are
        # mutually exclusive endings, so the full-score path is the champion run.
        # score / _scored_keys / award() come from the base Game.
        self.max_score = 100
        self.visited = set()
        # +2 for each newly-visited location (ACII scoring), via the trigger system.
        self.add_trigger(
            "score_locations",
            lambda g: g.player.location is not None
            and g.player.location.name not in g.visited,
            lambda g: g._note_visit(g.player.location.name),
            repeatable=True,
        )
        # Score the starting room (the trigger only sees rooms entered after t0).
        self._note_visit(self.player.location.name)

    def _note_visit(self, name):
        if name not in self.visited:
            self.visited.add(name)
            # "Middle of Pond" is our own sub-room of the Old Pond boat ride; the
            # rulebook counts 16 locations (32 pts), so it scores no visit points.
            if name != "Middle of Pond":
                self.score += 2

    def is_won(self) -> bool:
        p = self.player
        won = bool(p.get_property("is_champion") or p.get_property("is_married"))
        # is_won() is polled repeatedly by is_game_over(); announce_ending only
        # prints once and appends the score line.
        if won:
            # +5 for finishing without saving (rulebook page 18). This game has
            # no save mechanic, so reaching a winning end always earns it.
            self.award("finish", 5)
            if p.get_property("is_champion"):
                msg = "You are the new champion of ACTION CASTLE! THE END."
            else:
                msg = "The two of you return to town and live happily ever after. THE END."
            self.announce_ending(msg, show_score=True)
        return won


# ---------------------------------------------------------------------------
# Custom actions (verbs with no built-in-keyword collision)
# ---------------------------------------------------------------------------


class MoveStone(actions.Action):
    ACTION_NAME = "move stone"
    ACTION_DESCRIPTION = "Move the loose stone in the moat wall, revealing a tunnel"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)

    def check_preconditions(self) -> bool:
        loc = self.character.location
        if loc is None or loc.name != "Moat":
            self.parser.fail("There's no loose stone here.")
            return False
        return True

    def apply_effects(self):
        self.game.locations["Moat"].set_property("stone_moved", True)
        self.parser.ok(
            "Pulling with all your might, you move the stone away, revealing a tunnel."
        )


class EnterMoat(actions.Action):
    """Entering the moat is the catfish gate: survive only with a SHARP axe."""

    ACTION_NAME = "enter moat"
    ACTION_DESCRIPTION = "Enter the dark water of the castle moat"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)

    def check_preconditions(self) -> bool:
        loc = self.character.location
        if loc is None or loc.name != "Action Castle":
            self.parser.fail("There's no moat here.")
            return False
        return True

    def apply_effects(self):
        if _has_item_with(self.character, "is_sharp"):
            self.parser.ok(
                "As you enter the water, a monstrous catfish as big as a horse rears "
                "up, but you fend it off with your sharp axe. Wounded, it sinks below "
                "the murky water."
            )
            self.game.award("catfish", 10)
            _relocate(self.game, self.character, "Moat")
            self.parser.ok(self.game.locations["Moat"].description)
        else:
            _die(
                self.game,
                "As you enter the water, a monstrous catfish as big as a horse rears "
                "up and drags you away in its jaws. THE END.",
            )


# --- the dragon's dialogue, as a small property state machine ---------------


def _wake_and_challenge(game, dragon, roar):
    """Wake the dragon, deliver its *roar*, and pose the wits/steel choice so a
    bare "wits" / "steel" answers it (#110). Shared by every path that rouses
    the dragon -- the WAKE DRAGON verb and the linger trigger -- so the prompt
    is posed no matter how it woke (the explicit CHOOSE WITS / CHOOSE STEEL
    verbs still work too)."""
    dragon.set_property("awake", True)
    game.parser.ok(roar)
    game.pose_prompt(
        Prompt(
            text="Choose a weapon: wits or steel.",
            options={"wits": "choose wits", "steel": "choose steel"},
            speaker="dragon",
        )
    )


class DragonLingers(reactions.Countdown):
    """The sleeping dragon's menace is *presence*, not noise (Parsely: "any move
    besides exiting the room will wake the dragon"). Stepping into the trove starts
    a one-turn clock: it stirs as you arrive, and if you're still there next turn
    it rears into the wits/steel challenge. Leave -- or never dawdle -- and you're
    safe.

    A thing-owned Countdown like the poacher and demon; its clock simply starts on
    *your* arrival rather than a fleeing creature's, and "leaving" is the cancel.
    Re-arming (``REPEATABLE``) so a later return is risky too. Deliberately rousing
    it with WAKE DRAGON, or robbing the hoard, are handled by their own
    action/trigger."""

    DELAY = 1
    REPEATABLE = True  # re-arm each time you step back in

    def stimulus(self) -> bool:
        # Arm the moment you enter the trove, while the dragon still sleeps.
        return not self.owner.get_property("awake") and self.game.entered_this_round(
            self.game.player, self.owner.location
        )

    def warning(self) -> str:
        return "The dragon stirs in its sleep, one claw twitching. Best not linger."

    def cancelled(self) -> bool:
        # Safe if you've stepped back out (or it's already roused another way).
        return bool(self.owner.get_property("awake")) or (
            self.game.player.location is not self.owner.location
        )

    def consequence(self, game):
        _wake_and_challenge(
            game,
            self.owner,
            'The dragon wakes, eyes you hungrily and roars, "Another mortal dares '
            'challenge me? Choose a weapon: wits or steel."',
        )


class WakeDragon(actions.Action):
    ACTION_NAME = "wake dragon"
    ACTION_DESCRIPTION = "Wake the sleeping dragon"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)
        self.dragon = self.parser.get_character("dragon")

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.dragon, "There's no dragon here."):
            return False
        if not self.at(self.dragon, self.character.location, "There's no dragon here."):
            return False
        return True

    def apply_effects(self):
        _wake_and_challenge(
            self.game,
            self.dragon,
            'The dragon wakes up, eyes you hungrily and roars, "Another mortal dares '
            'challenge me? Choose a weapon: wits or steel."',
        )


class ChooseSteel(actions.Action):
    ACTION_NAME = "choose steel"
    ACTION_DESCRIPTION = "Fight the dragon with steel"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)
        self.dragon = self.parser.get_character("dragon")

    def check_preconditions(self) -> bool:
        if self.dragon is None or not self.dragon.get_property("awake"):
            self.parser.fail("The dragon is asleep.")
            return False
        return True

    def apply_effects(self):
        _die(
            self.game,
            "The dragon knocks your shield aside, then breathes fire on you. THE END.",
        )


class AttackDragon(actions.Action):
    """Attacking the dragon is fatal -- with or without the sword (rulebook).
    Multi-word name/aliases so the parser routes here before the generic ATTACK."""

    ACTION_NAME = "attack dragon"
    ACTION_DESCRIPTION = "Attack the dragon (ill-advised)"
    ACTION_ALIASES = [
        "attack the dragon",
        "kill dragon",
        "kill the dragon",
        "fight dragon",
        "fight the dragon",
        "slay dragon",
        "slay the dragon",
        "hit dragon",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)
        self.dragon = self.parser.get_character("dragon")

    def check_preconditions(self) -> bool:
        if not self.was_matched(self.dragon, "There's no dragon here."):
            return False
        if not self.at(self.dragon, self.character.location, "There's no dragon here."):
            return False
        return True

    def apply_effects(self):
        self.dragon.set_property("awake", True)
        if _is_holding(self.character, "sword"):
            _die(
                self.game,
                "The creature bats the sword aside and burns you alive with dragon "
                "fire. THE END.",
            )
        else:
            _die(
                self.game,
                "You strike the dragon; it doesn't so much as flinch, then "
                "incinerates you with a blast of fire. THE END.",
            )


class ChooseWits(actions.Action):
    ACTION_NAME = "choose wits"
    ACTION_DESCRIPTION = "Match wits with the dragon"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)
        self.dragon = self.parser.get_character("dragon")

    def check_preconditions(self) -> bool:
        if self.dragon is None or not self.dragon.get_property("awake"):
            self.parser.fail("The dragon is asleep.")
            return False
        return True

    def apply_effects(self):
        self.dragon.set_property("riddle_posed", True)
        self.parser.ok(
            '"Excellent! Answer my riddle correctly or be burned alive and eaten!  '
            'Who owns nothing yet has everything?"'
        )
        # Free-text: whatever the player says next is taken as their answer and
        # forwarded to ANSWER RIDDLE (#110), so "a wise man" works directly.
        self.game.pose_prompt(
            Prompt(
                text="Who owns nothing yet has everything?",
                forward_as="answer riddle",
                speaker="dragon",
            )
        )


class AnswerRiddle(actions.Action):
    ACTION_NAME = "answer riddle"
    ACTION_DESCRIPTION = "Answer the dragon's riddle"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)
        self.dragon = self.parser.get_character("dragon")
        self.command = command

    def check_preconditions(self) -> bool:
        if self.dragon is None or not self.dragon.get_property("riddle_posed"):
            self.parser.fail("There is no riddle to answer.")
            return False
        return True

    def apply_effects(self):
        # The hermit's advice telegraphs this: "only a fool desires wealth and
        # power; the wise person has everything they need."
        if "wise" in self.command.lower():
            self.dragon.set_property("riddle_solved", True)
            self.game.award("riddle", 10)
            self.parser.ok(
                'The dragon laughs. "Well done! You succeeded where all others '
                'failed. Now, choose your reward: gold, the sword, or the ring!"'
            )
            self.game.pose_prompt(
                Prompt(
                    text="Choose your reward: gold, the sword, or the ring.",
                    options={
                        "gold": "choose gold",
                        "sword": "choose sword",
                        "ring": "choose ring",
                    },
                    speaker="dragon",
                )
            )
        else:
            _die(
                self.game,
                'The dragon roars, "Wrong!" and breathes fire at you. THE END.',
            )


class _ChooseReward(actions.Action):
    """Base for the three reward choices; each requires the riddle solved and
    that no reward has been taken yet."""

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)
        self.dragon = self.parser.get_character("dragon")

    def check_preconditions(self) -> bool:
        if self.dragon is None or not self.dragon.get_property("riddle_solved"):
            self.parser.fail("The dragon has offered you no reward.")
            return False
        if self.dragon.get_property("reward_taken"):
            self.parser.fail("You have already chosen your reward.")
            return False
        return True


def _take_from_hoard(game, character, name):
    """Move the named loot item out of the treasure hoard into the character's
    hands (the legitimate reward path -- the steal trigger is keyed on having a
    hoard item *without* reward_taken, which CHOOSE sets first)."""
    treasure = game.locations["Treasure Trove"].items.get("treasure")
    item = treasure.contents.get(name) if treasure else None
    if item is not None:
        item.set_property("gettable", True)
        treasure.remove_item(item)
        character.add_to_inventory(item)
    return item


class ChooseGold(_ChooseReward):
    ACTION_NAME = "choose gold"
    ACTION_DESCRIPTION = "Take the dragon's gold"
    ACTION_ALIASES = []

    def apply_effects(self):
        self.dragon.set_property("reward_taken", True)
        _take_from_hoard(self.game, self.character, "gold")
        self.parser.ok(
            'The dragon laughs evilly. "Well, take as much as you can carry!" '
            "You grab a large sack of gold."
        )


class ChooseSword(_ChooseReward):
    ACTION_NAME = "choose sword"
    ACTION_DESCRIPTION = "Take the fallen champion's sword"
    ACTION_ALIASES = []

    def apply_effects(self):
        self.dragon.set_property("reward_taken", True)
        _take_from_hoard(self.game, self.character, "sword")
        self.parser.ok(
            '"The sword of the fallen champion? A bold choice!" roars the dragon. '
            "You strap the sword to your waist, and the dragon goes back to sleep."
        )


class ChooseRing(_ChooseReward):
    ACTION_NAME = "choose ring"
    ACTION_DESCRIPTION = "Take the diamond ring"
    ACTION_ALIASES = []

    def apply_effects(self):
        self.dragon.set_property("reward_taken", True)
        _take_from_hoard(self.game, self.character, "ring")
        self.parser.ok(
            '"A human who loves pretty rocks? Typical!" With a sweep of its tail, the '
            "dragon opens a chute beneath your feet, and you tumble down into the darkness..."
        )
        # The chute drops you out outside the Hermit's Cave; the hermit is gone.
        hermit = self.game.characters.get("hermit")
        outside_cave = self.game.locations["Outside Hermit's Cave"]
        if hermit is not None and hermit.location is outside_cave:
            outside_cave.remove_character(hermit)
            hermit.location = None
        _relocate(self.game, self.character, "Outside Hermit's Cave")
        self.parser.ok(outside_cave.description)


# --- castle endgame ---------------------------------------------------------


# --- gift interactions, now as first-class custom actions ------------------
# (Previously these were triggers reacting to the built-in Give/Drop, because
# the keyword parser hijacked "give"/"drop". Under SpecificFirstParser they are
# ordinary custom actions: local, gateable, single-narration.)


class DropPennyInWell(actions.Action):
    ACTION_NAME = "drop penny in well"
    ACTION_DESCRIPTION = "Drop your penny into the wishing well to make a wish"
    ACTION_ALIASES = ["make a wish", "toss penny in well"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.game.player

    def check_preconditions(self) -> bool:
        if (
            self.character.location is None
            or self.character.location.name != "Town Square"
        ):
            self.parser.fail("There's no wishing well here.")
            return False
        if not _is_holding(self.character, "penny"):
            self.parser.fail("You have no penny to drop.")
            return False
        return True

    def apply_effects(self):
        _take_held(self.character, "penny")
        self.game.award(
            "wish",
            3,
            "You drop the penny into the well and hear a faint *plink*. There goes your last cent.",
        )


# NOTE: sharpening the axe is handled by a TRIGGER (see build_game), not a custom
# action. The built-in Give already moves the axe into the smith's hands for any
# phrasing -- "give axe to smith", "give smith the axe", "hand the smith my axe" --
# so a trigger that reacts to "the smith holds the unsharpened axe" sharpens it and
# hands it back, independent of how the give was worded (issue #113).


# These three gifts are two-object interactions -- hold X, recipient present,
# then transfer + side effects -- so they're built with the engine's
# ``use_item_on`` factory (actions/use.py) instead of a hand-written Action
# subclass. The effect closures reuse ``_take_held`` so the item moves exactly
# as before; ``award=`` carries the scoring + narration unchanged.


def _give_blanket_to_rosemary(action):
    blanket = _take_held(action.character, "blanket")
    action.target.add_to_inventory(blanket)
    action.target.wear(blanket)  # she drapes it over her shoulders
    # Now warm enough to come along: she follows the player, and a later
    # "ask rosemary to follow" is accepted too (clear the cold-feet refusal).
    action.target.following = action.game.player
    action.target.set_property("refuses_follow", False)
    action.target.set_property("emotional_state", "happy")


GiveBlanketToRosemary = actions.use_item_on(
    "give blanket to rosemary",
    item="blanket",
    target="rosemary",
    verb="give",
    preposition="to",
    description="Give the warm blanket to Rosemary",
    aliases=["give blanket to sage", "offer rosemary the blanket"],
    effect=_give_blanket_to_rosemary,
    award=(
        "blanket",
        10,
        "Rosemary kisses you on the cheek and drapes the blanket over her shoulders. She'll follow you now.",
    ),
    item_missing="You have no blanket to give.",
    target_missing="She isn't here.",
)


def _give_slippers_to_hermit(action):
    action.target.add_to_inventory(_take_held(action.character, "slippers"))
    king = action.game.characters.get("king")
    if king is not None:
        king.set_property("wears_slippers", True)


GiveSlippersToHermit = actions.use_item_on(
    "give slippers to hermit",
    item="slippers",
    target="hermit",
    verb="give",
    preposition="to",
    description="Give the velvet slippers to the hermit",
    aliases=["give slippers to old man"],
    effect=_give_slippers_to_hermit,
    award=(
        "slippers",
        10,
        'The hermit accepts your gift: "Only a fool desires wealth and power. '
        'The wise person has everything they need." He taps his head and winks.',
    ),
    item_missing="You have no slippers to give.",
    target_missing="There's no one here to give them to.",
)


def _give_sword_to_king(action):
    action.target.add_to_inventory(_take_held(action.character, "sword"))
    action.target.set_property("offered_championship", True)
    action.parser.ok(
        "\"This kingdom needs a clever mind as much as a keen blade. And as I'm "
        'in need of a new champion, I offer you the position! Do you accept?"'
    )
    # A bare "yes" / "no" now answers the king (#110).
    action.game.pose_prompt(
        Prompt(
            text="The king offers you the championship. Do you accept?",
            options={"yes": "say yes", "no": "say no"},
            speaker="king",
        )
    )


GiveSwordToKing = actions.use_item_on(
    "give sword to king",
    item="sword",
    target="king",
    verb="give",
    preposition="to",
    description="Present the gleaming sword to the king",
    aliases=["offer the sword to the king"],
    effect=_give_sword_to_king,
    item_missing="You have no sword to give.",
    target_missing="The king isn't here.",
)


class SayYes(actions.Action):
    ACTION_NAME = "say yes"
    ACTION_DESCRIPTION = "Say yes -- accept the offer that's been made to you"
    ACTION_ALIASES = ["i accept", "accept the offer"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.game.player
        self.king = self.parser.get_character("king")

    def check_preconditions(self) -> bool:
        if self.king is None or not self.king.get_property("offered_championship"):
            self.parser.fail("No one has asked you anything.")
            return False
        if self.king.location is not self.character.location:
            self.parser.fail("The king isn't here.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            "The king touches your shoulder with the flat of the sword's blade and "
            "pronounces you the new champion of Action Castle!"
        )
        self.game.award("champion", 20)
        self.character.set_property("is_champion", True)


class SayNo(actions.Action):
    ACTION_NAME = "say no"
    ACTION_DESCRIPTION = "Say no -- decline the offer that's been made to you"
    ACTION_ALIASES = ["i decline", "decline the offer"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.game.player
        self.king = self.parser.get_character("king")

    def check_preconditions(self) -> bool:
        if self.king is None or not self.king.get_property("offered_championship"):
            self.parser.fail("No one has asked you anything.")
            return False
        return True

    def apply_effects(self):
        _die(
            self.game,
            'The king sighs. "Ah, then perhaps you are not the One." You return to '
            "your simple life as a cobbler. THE END.",
        )


# --- the boat + marriage ----------------------------------------------------


class RowBoat(actions.Action):
    ACTION_NAME = "row boat"
    ACTION_DESCRIPTION = "Row the boat out onto the pond, or back to shore"
    # Natural phrasings for getting back/out, so the player isn't stuck at the
    # middle hunting for the magic words. (All multi-word, so they route via the
    # parser's specific-first pass.)
    ACTION_ALIASES = [
        "row to shore",
        "row back",
        "row back to shore",
        "row to the shore",
        "exit boat",
        "leave the boat",
        "get out of the boat",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)
        self.command = command.lower()

    def check_preconditions(self) -> bool:
        loc = self.character.location
        if loc is None or loc.name not in ("Old Pond", "Middle of Pond"):
            self.parser.fail("There's no boat here.")
            return False
        return True

    def apply_effects(self):
        here = self.character.location.name
        wants_shore = any(
            w in self.command for w in ("shore", "back", "exit", "leave", "get out")
        )
        if here == "Middle of Pond":
            # Any row/exit from the middle takes you back to shore.
            self.parser.ok("You row back to the shore.")
            _relocate(self.game, self.character, "Old Pond")
        elif wants_shore:
            # "row back" / "exit boat" while already ashore.
            self.parser.ok("You're already on the shore.")
            return
        else:
            self.parser.ok("Row, row, row your boat. Life is but a dream.")
            _relocate(self.game, self.character, "Middle of Pond")
        # Describe the place we arrived (exits + hints), the way walking does --
        # so the player at the middle sees how to get back without having to look.
        actions.Describe(self.game, command="look")()


class EnterBoat(actions.Action):
    """Climb into the rowboat. Flavor (rulebook page 35: 'You're now in the
    boat.') -- rowing works from the shore regardless; this just answers the
    natural ENTER BOAT command."""

    ACTION_NAME = "enter boat"
    ACTION_DESCRIPTION = "Climb into the rowboat"
    ACTION_ALIASES = ["get in boat", "board boat", "get in the boat"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)

    def check_preconditions(self) -> bool:
        loc = self.character.location
        if loc is None or loc.name not in ("Old Pond", "Middle of Pond"):
            self.parser.fail("There's no boat here.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok("You're now in the boat.")


class EnterCave(actions.Action):
    """The literal ENTER CAVE verb (rulebook). The cave is also a blocked "in"
    exit (CaveBlock), so "go in" works too; this answers "enter cave" with the
    same refusal -- it's too dark and scary in there."""

    ACTION_NAME = "enter cave"
    ACTION_DESCRIPTION = "Try to enter the dark cave"
    ACTION_ALIASES = ["enter the cave", "go into the cave", "go in the cave"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)

    def check_preconditions(self) -> bool:
        loc = self.character.location
        if loc is None or loc.name != "Outside Hermit's Cave":
            self.parser.fail("There's no cave here.")
            return False
        return True

    def apply_effects(self):
        self.parser.ok(CAVE_TOO_DARK)


class Propose(actions.Action):
    ACTION_NAME = "propose"
    ACTION_DESCRIPTION = "Propose marriage to your beloved"
    # "give ring to rosemary" IS the proposal -- route it here (multi-word, so
    # it wins specific-first over the built-in Give, which would otherwise hand
    # the ring away and strand the marriage ending). Outside the Middle of the
    # Pond it fails the location gate below WITHOUT transferring the ring.
    ACTION_ALIASES = [
        "give ring to rosemary",
        "give the ring to rosemary",
        "give ring to sage",
        "give rosemary the ring",
        "give rosemary ring",
        "offer ring to rosemary",
        "offer the ring to rosemary",
        "hand rosemary the ring",
    ]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        # The proposer is the actor (the player for a typed command). Don't scan
        # the command for a name -- "give ring to rosemary" names Rosemary, who
        # is the beloved, not the one doing the proposing.
        self.character = self.actor if self.actor is not None else self.game.player
        self.beloved = self.parser.get_character("rosemary")

    def check_preconditions(self) -> bool:
        if not _is_holding(self.character, "ring") and not _has_item_with(
            self.character, "is_ring"
        ):
            self.parser.fail("You have nothing to offer as a token of your love.")
            return False
        if self.beloved is None or self.beloved.location is not self.character.location:
            self.parser.fail("Your beloved isn't here.")
            return False
        if self.character.location.name != "Middle of Pond":
            self.parser.fail(
                "You want to propose here? Maybe a more romantic location is in order?"
            )
            return False
        return True

    def apply_effects(self):
        self.parser.ok(
            'Your beloved kisses you on the cheek, exclaiming, "Of course I do!"'
        )
        self.game.award("propose", 20)
        self.character.set_property("is_married", True)
        self.beloved.set_property("is_married", True)


# NOTE: the hermit's dialogue is handled by the engine's generic Talk verb via
# his talk_text (the mumble) + talk_topics ("prophecy" -> the prophecy line),
# set in build_game -- not a custom action. So "talk to hermit" mumbles, and
# "talk to hermit about prophecy" / "ask hermit about the prophecy" evokes it.


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game() -> ActionCastle2:
    L = things.Location

    # --- Locations ---------------------------------------------------------
    workshop = L(
        "Cobbler's Workshop", "You are in your workshop. A door leads outside."
    )
    town_square = L(
        "Town Square",
        "It's a dark, cold night. You see a wishing well here. Exits lead north, south, east and west.",
    )
    town_hall = L("Town Hall", "You are in the town hall.")
    smithy = L(
        "Smithy",
        "You are in the smithy. The blacksmith is at the forge, hammering on red-hot iron.",
    )
    pond_road = L(
        "Old Pond Road",
        "You're walking down Old Pond Road, a wide cobblestone road. There is a sign here.",
    )
    old_pond = L(
        "Old Pond",
        "You stand at the edge of the old pond. The clear night sky above is full "
        "of stars. You see a rowboat here. A path runs alongside the pond to the "
        "north and south.",
    )
    middle_pond = L(
        "Middle of Pond",
        "You are in a rowboat in the middle of the old pond. It's quiet, peaceful "
        "and romantic here. Row the boat to head back to shore.",
    )
    hermit_cave = L(
        "Outside Hermit's Cave",
        "An old man sits by a fire outside a dark cave. The cave mouth gapes "
        "darkly before you.",
    )
    cave = L(
        "Cave",
        "Pitch black. You can't see a thing -- and the smell is unspeakable.",
    )
    bend = L(
        "Bend in the Road",
        "You arrive at a bend in the road. There is an old tree stump here.",
    )
    castle = L(
        "Action Castle",
        "You stand outside the walls of Action Castle! There's a deep moat here. The drawbridge is up.",
    )
    moat = L(
        "Moat",
        "You are treading water in the moat, just within reach of the castle's stone walls.",
    )
    underground = L(
        "Underground", "You are somewhere underneath the castle. A skeleton lies here."
    )
    trove = L(
        "Treasure Trove",
        "A huge dragon slumbers here atop a mountain of glittering treasure.",
    )
    dungeon = L(
        "Dungeon",
        "You are in the dungeon. A twisting staircase leads up; there are cells here.",
    )
    dungeon_stairs = L(
        "Dungeon Stairs",
        "You are on the dungeon stairs. You can hear the king's guards talking above.",
    )
    courtyard = L(
        "Courtyard", "You are in the castle courtyard. A pair of guards stands here."
    )
    throne_room = L(
        "Throne Room",
        "You are in the throne room of Action Castle. The king sits upon an ornate gold throne.",
    )

    # --- Connections (canonical dirs auto-reverse; named exits are one-way) -
    # Per the rulebook the three buildings ring the Town Square (workshop NORTH,
    # smithy SOUTH, town hall WEST) and each returns via a one-way "out". We wire
    # BOTH directions one-way (see _one_way): the canonical auto-reverse would
    # otherwise (a) collide on town_square["in"] and strand the workshop, and
    # (b) give each building a second, redundant exit home (e.g. the Smithy
    # showing both "North" and "Out" to the Town Square). The road is the one
    # canonical pair -- east<->west auto-reverses cleanly with no duplicate.
    _one_way(town_square, "north", workshop)  # rulebook: NORTH -> Cobbler's Workshop
    _one_way(workshop, "out", town_square)  # "A door leads outside"
    _one_way(town_square, "south", smithy)
    _one_way(smithy, "out", town_square)
    _one_way(town_square, "west", town_hall)
    _one_way(town_hall, "out", town_square)
    town_square.add_connection("east", pond_road)  # pairs with pond_road WEST
    pond_road.add_connection("north", bend)
    pond_road.add_connection("south", old_pond)
    old_pond.add_connection("south", hermit_cave)
    hermit_cave.add_connection("in", cave)  # "go in" -- but blocked (see CaveBlock)
    bend.add_connection("east", castle)
    # Moat is reached ONLY via the EnterMoat action (the catfish gate) -- we
    # deliberately give it no connection back to Action Castle, because a
    # canonical "out" would auto-create a castle->"in"->moat reverse exit that
    # bypasses the catfish. For the same reason the moat<->underground link uses
    # non-canonical exit names (no auto-reverse), so the tunnel block can't be
    # sidestepped by walking "south".
    moat.add_connection("enter tunnel", underground)
    underground.add_connection("tunnel", moat)
    underground.add_connection("south", trove)
    # Underground -> EAST -> Dungeon, but the Dungeon returns via HOLE only
    # (rulebook). One-way so the east auto-reverse doesn't add a redundant
    # "west" exit alongside the explicit "hole" back to the Underground.
    _one_way(underground, "east", dungeon)
    dungeon.add_connection("up", dungeon_stairs)
    dungeon.add_connection("hole", underground)
    dungeon_stairs.add_connection("up", courtyard)
    # Action Castle -> Moat -> Courtyard -> Throne Room transitions are all
    # handled by the EnterMoat action and the courtyard trigger below.

    # --- Items: gettable ---------------------------------------------------
    # The slippers ARE wearable -- they just don't fit the cobbler. We model that
    # with the engine's fit gate: the slippers declare fit_property="shoe_size"
    # and carry shoe_size="imperial_foot", so only a wearer whose own shoe_size is
    # "imperial_foot" can put them on. The cobbler (and everyone but the
    # king/hermit) has it unset, so WEAR SLIPPERS yields "The slippers don't fit."
    # Their real use remains GIVE SLIPPERS TO HERMIT.
    slippers = things.Item(
        "slippers",
        "a pair of fine purple velvet slippers",
        "A pair of fine purple velvet slippers, fit for a king.",
    )
    slippers.set_property("wearable", True)
    slippers.set_property("fit_property", "shoe_size")
    slippers.set_property("shoe_size", "imperial_foot")
    slippers.set_property("misfit_message", "The slippers don't fit.")
    workshop.add_item(slippers)

    # Wearable: the player can bundle up, and Rosemary drapes it over her
    # shoulders when gifted (GiveBlanketToRosemary wears it on her).
    # The rowboat is a container holding the blanket (rulebook page 35: EXAMINE
    # BOAT -> "It contains a blanket"). The blanket is takeable from the shore --
    # the engine's Get reaches into an open container sitting in the room, and
    # Examine lists its contents.
    boat = things.Item(
        "boat", "a rowboat", "You see that the boat is in fair condition."
    )
    boat.set_property("gettable", False)
    boat.make_container()  # unlimited capacity, always open
    # You can see into the open rowboat from shore, so the blanket it holds is
    # listed in the room (and GET reaches it) rather than hidden until EXAMINE.
    boat.set_property("contents_visible", True)
    boat.add_command_hint("enter boat")
    boat.add_command_hint("row boat")

    blanket = things.Item(
        "blanket",
        "a warm wool blanket",
        "You see the blanket is made of fine wool. It looks warm.",
    )
    blanket.set_property("wearable", True)
    boat.add_item(blanket)  # in the boat, not loose at the pond
    old_pond.add_item(boat)

    # The axe is embedded in the tree stump (rulebook), so the stump is a
    # surface holding it -- TAKE AXE pulls it from the stump, and EXAMINE STUMP
    # lists it. (A surface, per the engine's supporter feature.)
    stump = things.Item(
        "stump",
        "an old tree stump",
        "Judging by the size of its stump, this tree must have been enormous.",
    )
    stump.set_property("gettable", False)
    stump.make_surface()
    axe = things.Item("axe", "an axe", "The axe is dulled from frequent use.")
    axe.set_property("is_weapon", True)
    stump.add_item(axe)
    bend.add_item(stump)

    armor = things.Item(
        "armor", "fire-scorched armor", "It bears the heraldry of Action Castle."
    )
    armor.set_property("wearable", True)
    shield = things.Item(
        "shield", "a battered shield", "It bears the heraldry of Action Castle."
    )
    shield.set_property("wieldable", True)
    underground.add_item(armor)
    underground.add_item(shield)

    # --- Items: scenery (examine flavor / command hints) -------------------
    def scenery(name, desc, examine, loc, hints=()):
        it = things.Item(name, desc, examine)
        it.set_property("gettable", False)
        for h in hints:
            it.add_command_hint(h)
        loc.add_item(it)
        return it

    scenery(
        "well",
        "a stone wishing well",
        "Well, well. A well!",
        town_square,
        ["drop penny in well"],
    )
    scenery(
        "grindstone",
        "a grindstone",
        "If you put your nose to it, you might make something of yourself.",
        smithy,
    )
    sign = scenery(
        "sign",
        "a weather-beaten sign",
        'It reads, "Please don\'t pick the roses."',
        pond_road,
        ["read sign"],
    )
    # READ SIGN surfaces its writing (the generic Read verb reads read_text).
    sign.set_property("read_text", 'It reads, "Please don\'t pick the roses."')
    scenery(
        "moat",
        "the castle moat",
        "The black, murky water ripples as something moves below.",
        castle,
        ["enter moat"],
    )
    scenery(
        "stone",
        "a loose stone in the wall",
        "Peering closely, you notice a loose stone.",
        moat,
        ["move stone"],
    )
    # EXAMINE WALL(S) points at the loose stone too (matches "examine walls").
    scenery(
        "wall",
        "the castle's stone wall",
        "Peering closely, you notice a loose stone in the wall.",
        moat,
        ["move stone"],
    )
    scenery(
        "skeleton",
        "the skeletal remains of an adventurer",
        "Clad in fire-scorched armor and a battered shield.",
        underground,
    )
    # The hoard is a container: you can EXAMINE the gold / sword / ring it holds
    # (rulebook flavor), and you *can* try to grab them -- but stealing wakes the
    # dragon (the steal trigger below). CHOOSE GOLD/SWORD/RING hands you the same
    # item legitimately. Contents show on EXAMINE TREASURE, not in the room list.
    treasure = things.Item(
        "treasure",
        "a mountain of treasure",
        "Burlap sacks bursting with coins, a king's ransom of gems and jewelry, "
        "and a glint of steel.",
    )
    treasure.set_property("gettable", False)
    treasure.make_container()
    hoard_gold = things.Item(
        "gold",
        "a heavy sack of gold coins",
        "Stolen from the king's treasury, no doubt -- you recognize the royal seal.",
    )
    hoard_sword = things.Item(
        "sword", "a gleaming sword", "The sword isn't just gleaming... it's glowing!"
    )
    hoard_sword.set_property("is_weapon", True)
    hoard_sword.set_property("wieldable", True)
    hoard_ring = things.Item(
        "ring",
        "a beautiful diamond ring",
        "An especially beautiful diamond ring. The gem is enormous!",
    )
    for loot in (hoard_gold, hoard_sword, hoard_ring):
        treasure.add_item(loot)
    trove.add_item(treasure)
    # A surface (engine supporter): the old lamp rests ON a stone ledge. Demos
    # the surface verbs in a live game -- EXAMINE LEDGE lists what's on it, and
    # you can TAKE LAMP off it / PUT LAMP ON LEDGE. (The lamp is a useless
    # souvenir per the rulebook, but it's takeable so the demo has something to
    # move.)
    ledge = things.Item(
        "ledge", "a stone ledge", "A worn stone ledge runs along the stairs."
    )
    ledge.set_property("gettable", False)
    ledge.make_surface()
    lamp = things.Item(
        "lamp", "an old lamp", "It ran out of oil ages ago. It cannot be lit."
    )
    ledge.add_item(lamp)
    dungeon_stairs.add_item(ledge)

    # --- Characters --------------------------------------------------------
    player = things.Character(
        "The player",
        "You are a humble cobbler seeking fortune and glory.",
        "I am on a grand adventure.",
    )
    penny = things.Item("penny", "a shiny copper penny", "Your last cent.")
    player.add_to_inventory(penny)

    # Characters carry an optional examine_text (richer than the one-line
    # description the room listing shows) -- the engine's EXAMINE action prefers
    # it, so "examine rosemary" reads like the original Parsely flavor.
    rosemary = things.Character(
        "rosemary",
        "the mayor's daughter, your sweetheart",
        "I am sweet but painfully shy.",
    )
    rosemary.examine_text = (
        "Hey, it's your sweetheart! She's a sweet girl, but painfully shy. "
        "Rosemary blushes as she catches you looking at her."
    )
    # talk_text is the spoken line the generic Talk action surfaces (nicer than
    # her first-person persona, which would read oddly quoted aloud).
    rosemary.talk_text = (
        "Rosemary blushes and looks at her feet. \"Oh! H-hello... it's good to "
        'see you."'
    )
    rosemary.set_property("emotional_state", "happy")
    # Following (engine #112): she declines until she has the blanket ("too
    # chilly"), and even once following she won't leave the town for the castle
    # or the hermit's cave (ACII pages 35/37). GiveBlanketToRosemary sets
    # `following` and clears the refusal.
    rosemary.set_property("refuses_follow", True)
    rosemary.set_property(
        "follow_refusal_message", "Rosemary says it's too chilly to go outside."
    )
    rosemary.follow_filter = lambda loc: loc.name not in ROSEMARY_NO_FOLLOW
    town_hall.add_character(rosemary)

    smith = things.Character(
        "smith", "a burly, bearded blacksmith", "Whaddya want? I'm busy!"
    )
    smith.examine_text = (
        "A burly, bearded blacksmith, sleeves rolled up, hammering red-hot iron "
        "at the forge. He doesn't look up."
    )
    smith.talk_text = 'The smith barely glances up. "Whaddya want? I\'m busy!"'
    smithy.add_character(smith)

    hermit = things.Character(
        "hermit",
        "a crazy old hermit in a burlap sack",
        "Only a fool desires wealth and power.",
    )
    hermit.examine_text = (
        "A wild-eyed old man in a burlap sack, warming his hands by a small fire. "
        "He mutters about fools, wealth, and the wisdom of wanting nothing."
    )
    # TALK TO HERMIT mumbles (and teases the topic); TALK TO HERMIT ABOUT
    # PROPHECY / ASK HERMIT ABOUT THE PROPHECY evokes the prophecy (rulebook).
    hermit.talk_text = (
        "The hermit mumbles something about a prophecy, then goes back to "
        "staring into the fire."
    )
    hermit.talk_topics = {
        "prophecy": (
            'The hermit turns from the fire and intones, "A champion will arise '
            'from humble beginnings to bring peace to the land."'
        )
    }
    # The hermit takes the same shoe size as the king (he is more than he seems)
    # -- the velvet slippers fit him, which is why gifting them ends with the
    # king wearing them.
    hermit.set_property("shoe_size", "imperial_foot")
    hermit_cave.add_character(hermit)

    dragon = things.Character(
        "dragon",
        "a huge dragon with razor-sharp claws",
        "Another mortal dares challenge me?",
    )
    dragon.examine_text = (
        "A huge dragon with razor-sharp claws, coiled atop a hoard of gold. Smoke "
        "curls from its nostrils with every slow breath."
    )
    trove.add_character(dragon)

    guards = things.Character(
        "guards", "a pair of royal guards", "Halt! Who goes there?"
    )
    guards.examine_text = (
        "A pair of royal guards in the king's livery, halberds crossed. They eye "
        "you -- and whatever you're carrying -- with suspicion."
    )
    guards.talk_text = 'The guards level their halberds. "Halt! Who goes there?"'
    courtyard.add_character(guards)

    king = things.Character(
        "king",
        "the king of Action Castle, with a long beard and gold crown",
        "I am in need of a new champion.",
    )
    king.examine_text = (
        "The king of Action Castle, long-bearded and gold-crowned, slumped on his "
        "throne. He looks every inch a monarch in want of a champion."
    )
    king.talk_text = (
        'The king studies you from his throne. "Speak, then -- what brings you '
        'before the throne?"'
    )
    king.set_property("shoe_size", "imperial_foot")  # the velvet slippers fit him
    throne_room.add_character(king)

    # --- Reaction triggers: only genuinely emergent / on-arrival checks ------
    # The gift & wish interactions that used to live here as triggers are now
    # plain custom actions (DropPennyInWell, GiveAxeToSmith, ...), routed by
    # SpecificFirstParser. Triggers are kept only for conditions that aren't
    # tied to a single verb.
    game_triggers = []

    # SMITH sharpens the axe (issue #113). The built-in Give moves the axe into
    # the smith's hands for ANY phrasing; this trigger then reacts to "the smith
    # holds the unsharpened axe" -- sharpening it and handing it back -- so it
    # works whether you typed "give axe to smith" or "give smith the axe".
    def sharpen_axe(g):
        axe = smith.inventory.get("axe")
        if axe is None:
            return
        axe.set_property("is_sharp", True)
        axe.description = "a sharp axe"
        smith.remove_from_inventory(axe)
        g.player.add_to_inventory(axe)
        g.parser.ok(
            "The smith mutters under his breath and sharpens the axe for you. "
            "You now have a sharp axe."
        )

    game_triggers.append(
        (
            "smith_sharpens_axe",
            lambda g: "axe" in smith.inventory
            and not smith.inventory["axe"].get_property("is_sharp"),
            sharpen_axe,
            True,
        )
    )

    # Stealing from the hoard wakes the dragon -- and it kills the thief
    # (rulebook). Keyed on holding a loot item you did NOT earn: CHOOSE sets
    # reward_taken first, so the legitimate reward never trips this; a bare
    # "take gold/sword/ring" does.
    def dragon_kills_thief(g):
        dragon.set_property("awake", True)
        _die(
            g,
            'The dragon\'s eye snaps open. "THIEF!" it roars, and a gout of '
            "flame engulfs you. THE END.",
        )

    game_triggers.append(
        (
            "dragon_kills_thief",
            lambda g: dragon is not None
            and not dragon.get_property("reward_taken")
            and any(_is_holding(g.player, n) for n in ("gold", "sword", "ring")),
            dragon_kills_thief,
            False,
        )
    )

    # Lingering wakes the dragon (rulebook: "any other move besides exiting the
    # room will wake the dragon"). It's a DragonLingers Countdown reaction attached
    # after the game is built: one grace turn (it stirs as you arrive), then the
    # challenge if you're still there. (Deliberate WAKE DRAGON and the theft-kill
    # above are unchanged.)

    # Returning to the Moat carrying the gold is fatal (you sink and drown).
    def gold_drown(g):
        _die(
            g,
            "Weighed down by the gold coins, you swiftly sink to the bottom of the moat and drown. THE END.",
        )

    game_triggers.append(
        (
            "gold_drown",
            lambda g: g.player.location is moat and _is_holding(g.player, "gold"),
            gold_drown,
            False,
        )
    )

    # COURTYARD checkpoint: the guards arrest you unless you carry the sword,
    # in which case they escort you to the Throne Room.
    def courtyard_check(g):
        if _is_holding(g.player, "sword"):
            g.parser.ok(
                'A guard notices your sword. "Wait! The king will want to see this. Come with us." They escort you to the throne room.'
            )
            _relocate(g, g.player, "Throne Room")
        else:
            _die(
                g,
                "The guards grab you by the arms. You are arrested for trespassing and locked in the dungeon. THE END.",
            )

    game_triggers.append(
        ("courtyard", lambda g: g.player.location is courtyard, courtyard_check, False)
    )

    # --- Assemble the game -------------------------------------------------
    custom_actions = [
        MoveStone,
        EnterMoat,
        WakeDragon,
        AttackDragon,
        ChooseWits,
        ChooseSteel,
        AnswerRiddle,
        ChooseGold,
        ChooseSword,
        ChooseRing,
        DropPennyInWell,
        GiveBlanketToRosemary,
        GiveSlippersToHermit,
        GiveSwordToKing,
        SayYes,
        SayNo,
        RowBoat,
        EnterBoat,
        EnterCave,
        Propose,
    ]
    characters = [rosemary, smith, hermit, dragon, guards, king]
    game = ActionCastle2(workshop, player, characters, custom_actions)

    # The engine indexes game.locations by walking the connection graph from the
    # start. Locations reached only via an action/trigger relocation (the whole
    # castle interior, the Middle of the Pond, the Throne Room) aren't on that
    # graph, so register every location explicitly -- _relocate() looks them up
    # by name.
    for loc in (
        workshop,
        town_square,
        town_hall,
        smithy,
        pond_road,
        old_pond,
        middle_pond,
        hermit_cave,
        cave,
        bend,
        castle,
        moat,
        underground,
        trove,
        dungeon,
        dungeon_stairs,
        courtyard,
        throne_room,
    ):
        game.locations.setdefault(loc.name, loc)

    for name, cond, act, repeat in game_triggers:
        game.add_trigger(name, cond, act, repeatable=repeat)

    # The dragon's linger reflex (thing-owned reaction, evaluated in the react
    # phase): dawdle in the trove and it rouses into the challenge.
    game.add_reaction(dragon, DragonLingers())

    # A block so the moat tunnel only opens after MOVE STONE.
    from text_adventure_games import blocks

    class TunnelBlock(blocks.Block):
        def __init__(self, moat_loc):
            super().__init__(
                "A wall blocks your way",
                "There's no way through until you move the loose stone.",
            )
            self.moat = moat_loc

        def is_blocked(self) -> bool:
            return not self.moat.get_property("stone_moved")

    moat.add_block("enter tunnel", TunnelBlock(moat))

    # The cave is never enterable -- "go in" is permanently blocked (rulebook:
    # ENTER CAVE -> "It's too dark and scary in there. Also: It smells."). The
    # EnterCave action answers the literal "enter cave" verb with the same line.
    class CaveBlock(blocks.Block):
        def __init__(self):
            super().__init__("The cave is impassable", CAVE_TOO_DARK)

        def is_blocked(self) -> bool:
            return True

    hermit_cave.add_block("in", CaveBlock())

    # The king's guards bar the throne room's west door -- GO WEST gets a flavor
    # refusal rather than the bare "no exit" error. A permanently-blocked
    # one-way exit (the connection exists so Go reaches the block, which never
    # opens), mirroring the CaveBlock pattern above.
    class ThroneGuardBlock(blocks.Block):
        def __init__(self):
            super().__init__(
                "The guards bar the way",
                "The king's guards step into your path. \"No one leaves the "
                "king's presence unbidden.\"",
            )

        def is_blocked(self) -> bool:
            return True

    _one_way(throne_room, "west", courtyard)
    throne_room.add_block("west", ThroneGuardBlock())
    # NOTE: build_game is parser-agnostic. It returns the game with the engine's
    # default parser; the caller chooses a parser via game.set_parser(...).
    return game


# ---------------------------------------------------------------------------
# Walkthroughs (also serve as automated win tests)
# ---------------------------------------------------------------------------

WALKTHROUGH_CHAMPION = [
    "out",
    "east",
    "north",  # -> Bend in the Road
    "take axe",
    "south",
    "west",
    "south",  # -> Smithy
    "give axe to smith",  # custom action: sharpens the axe in place
    "out",
    "east",
    "north",
    "east",  # -> Action Castle
    "enter moat",  # survive catfish (sharp axe)
    "move stone",
    "enter tunnel",  # -> Underground
    "south",  # -> Treasure Trove
    "wake dragon",
    "choose wits",
    "answer riddle a wise man",
    "choose sword",
    "north",
    "east",
    "up",
    "up",  # Underground -> Dungeon -> Stairs -> Courtyard (escort to Throne Room)
    "give sword to king",
    "say yes",  # become champion  (custom GiveSwordToKing + SayYes)
]

WALKTHROUGH_MARRIAGE = [
    # Get the ring from the dragon first (drops you at the Hermit's Cave).
    "out",
    "east",
    "north",  # Bend
    "take axe",
    "south",
    "west",
    "south",  # Smithy
    "give axe to smith",
    "out",
    "east",
    "north",
    "east",  # Action Castle
    "enter moat",
    "move stone",
    "enter tunnel",
    "south",  # Treasure Trove
    "wake dragon",
    "choose wits",
    "answer riddle a wise man",
    "choose ring",  # -> Hermit's Cave
    # Now go court Rosemary.
    "north",  # Hermit's Cave -> Old Pond
    "take blanket",
    "north",
    "west",  # Old Pond Road -> Town Square ... to Town Hall
    "west",  # Town Square -> Town Hall
    "give blanket to rosemary",  # she follows
    "out",
    "east",
    "south",  # Town Hall -> Town Square -> Old Pond Road -> Old Pond
    "row boat",  # -> Middle of Pond (Rosemary follows)
    "propose",
]


def _run(commands):
    """Run a command list against a fresh game on the engine's default parser
    (which now ranks multi-word custom verbs specific-first)."""
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
        _run(WALKTHROUGH_CHAMPION)
    elif "--walk-marry" in sys.argv:
        _run(WALKTHROUGH_MARRIAGE)
    else:
        build_game().game_loop()
