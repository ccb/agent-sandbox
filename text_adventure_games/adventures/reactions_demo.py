"""A tiny sandbox for watching the reactions system (docs/design/reactions.md).

Three rooms, one of every reaction shape, and the physical-sound model wiring
them together. Read it top-to-bottom to see how a game attaches reflexes to
things; play it to watch them fire.

    Ledge  --in/out-->  Hollow  --down/up-->  Shrine
     bat                 ogre                  fuse + gem
   (FleesAtNoise)     (WakesAtNoise)         (Countdown)

What each piece demonstrates:

  * The BAT is an Item with a `FleesAtNoise` reaction: it bolts to the Hollow at
    ANY noise it hears -- your shout (SAY), a smash (BREAK), or the gong two rooms
    off (earshot). Quiet actions (LOOK, EXAMINE) leave it be.

  * The OGRE is a Character with a `WakesAtNoise` reaction (subclassed to roar on
    waking): a sleeping creature roused by the first noise it hears.

  * The SHRINE's FUSE is an Item with a `Countdown` reaction: stepping into the
    Shrine lights it, and three turns later the cave comes down -- unless you
    CUT FUSE first. A cancelable timed consequence (the poacher/demon pattern).

  * Sound is the SOURCE's property: SAY/BREAK carry because the actions declare an
    AUDIBLE_RADIUS; the GONG is an ambient noise emitted with `game.emit_sound`.
    Reactions just *hear* -- they own no notion of "what is loud".

Run it:
    python -m text_adventure_games.adventures.reactions_demo            # play
    python -m text_adventure_games.adventures.reactions_demo --walk     # scripted tour

Goal: grab the gem from the Shrine and get back out to the Ledge alive.
"""

from text_adventure_games import games, things, actions, reactions


def _die(game, text):
    """End the game with a parting line (demo helper)."""
    game.parser.ok(text)
    game.game_over = True
    game.game_over_description = text


# ---------------------------------------------------------------------------
# Reactions -- the reflexes we attach to things in build_game() below.
# ---------------------------------------------------------------------------


class OgreWakes(reactions.WakesAtNoise):
    """A sleeping ogre roused by the first noise it hears.

    `WakesAtNoise` already gates on the owner's ``asleep`` property and flips it
    on firing; we only override :meth:`wake` to give the awakening some flavor."""

    def wake(self):
        self.game.parser.ok(
            "The ogre's eyes snap open. It heaves upright with a bone-rattling "
            "ROAR -- wide awake, and not pleased."
        )


class FuseBurns(reactions.Countdown):
    """Stepping into the Shrine lights a fuse in the doorway; DELAY turns later the
    ceiling comes down -- unless you CUT FUSE, which sets ``fuse_cut`` and calls it
    off. The fuse is the reaction's owner, so it reads its own room for the flags."""

    DELAY = 3

    def stimulus(self) -> bool:
        # Arm the moment the player steps into the fuse's room.
        return self.game.entered_this_round(self.game.player, self.owner.location)

    def warning(self) -> str:
        return (
            "A fuse set in the doorway sputters alight, hissing and spitting "
            "sparks. Better CUT FUSE -- fast."
        )

    def cancelled(self) -> bool:
        return bool(self.owner.location.get_property("fuse_cut"))

    def consequence(self, game):
        _die(
            game,
            "The fuse burns down to the rock and the whole ceiling lets go. You "
            "are buried where you stand. THE END.",
        )


# ---------------------------------------------------------------------------
# Two small custom verbs: an ambient-sound source and the Countdown's cancel.
# ---------------------------------------------------------------------------


class RingGong(actions.Action):
    """Strike the gong -- an ambient noise emitted with ``game.emit_sound`` (radius
    2, so it carries clear across the cave) rather than the sound of a verb."""

    ACTION_NAME = "ring gong"
    ACTION_DESCRIPTION = "Strike the bronze gong"
    ACTION_ALIASES = ["strike gong", "bang gong", "hit gong"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        if "gong" not in self.game.player.location.items:
            self.parser.fail("There's no gong here.")
            return False
        return True

    def apply_effects(self):
        loc = self.game.player.location
        self.parser.ok("You strike the gong. A deep CLANG rolls through the cave.")
        # The source owns its volume: this noise is heard here and two rooms out,
        # and any reaction within earshot answers it.
        self.game.emit_sound(loc, 2, "the clang of a gong")


class CutFuse(actions.Action):
    """Cancel the FuseBurns countdown by snuffing the fuse."""

    ACTION_NAME = "cut fuse"
    ACTION_DESCRIPTION = "Snuff out the burning fuse"
    ACTION_ALIASES = ["douse fuse", "pinch fuse", "put out fuse", "snuff fuse"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self) -> bool:
        loc = self.game.player.location
        if "fuse" not in loc.items:
            self.parser.fail("There's no fuse here.")
            return False
        if loc.get_property("fuse_cut"):
            self.parser.fail("The fuse is already out.")
            return False
        return True

    def apply_effects(self):
        loc = self.game.player.location
        loc.set_property("fuse_cut", True)  # FuseBurns.cancelled() reads this
        self.parser.ok("You pinch the hissing fuse dead. Silence floods back in.")


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


class ReactionsDemo(games.Game):
    """The base engine leaves :meth:`is_won` to the game; ours is "got out with
    the gem" (the ``escaped`` flag the win trigger sets below)."""

    def is_won(self) -> bool:
        return bool(self.player.get_property("escaped"))


def build_game():
    ledge = things.Location(
        "Ledge",
        "A narrow ledge at the cave mouth, daylight at your back. A passage leads "
        "in to the north.",
    )
    hollow = things.Location(
        "Hollow",
        "A wide hollow, deep in shadow. A bronze gong hangs from a beam, and a "
        "passage drops away downward.",
    )
    shrine = things.Location(
        "Shrine",
        "A cramped shrine. A gemstone glints on the altar -- and the only way out "
        "is back up.",
    )
    ledge.add_connection("in", hollow)  # auto-wires hollow --out--> ledge
    hollow.add_connection("down", shrine)  # auto-wires shrine --up--> hollow

    # The skittish bat (Item): bolts to the Hollow at any noise it hears.
    bat = things.Item(
        "bat", "a nervous bat", "A nervous little bat clings to the rock."
    )
    bat.set_property("gettable", False)
    ledge.add_item(bat)

    # Something to smash for noise -- BREAK declares an AUDIBLE_RADIUS, so it spooks
    # the bat without any per-game "loud verbs" list.
    icicle = things.Item("icicle", "a brittle icicle", "A long, brittle icicle.")
    icicle.set_property("gettable", False)
    icicle.set_property("is_breakable", True)
    ledge.add_item(icicle)

    # The sleeping ogre (Character): wakes at the first noise it hears.
    ogre = things.Character("ogre", "a snoring ogre", "I was having such a nice nap.")
    ogre.set_property("asleep", True)
    ogre.examine_text = "A huge ogre, fast asleep and snoring like a sawmill."
    hollow.add_character(ogre)

    gong = things.Item(
        "gong", "a bronze gong", "A bronze gong on a beam. (Try RING GONG.)"
    )
    gong.set_property("gettable", False)
    hollow.add_item(gong)

    # The Shrine's fuse (Item, owns the Countdown) and the prize.
    fuse = things.Item(
        "fuse", "a fuse in the doorway", "A fuse threaded through the doorway."
    )
    fuse.set_property("gettable", False)
    shrine.add_item(fuse)
    gem = things.Item(
        "gem", "a glittering gem", "A fat gemstone, yours for the taking."
    )
    gem.set_property("gettable", True)
    shrine.add_item(gem)

    player = things.Character("you", "a curious spelunker", "I explore the cave.")

    game = ReactionsDemo(
        ledge, player, characters=[ogre], custom_actions=[RingGong, CutFuse]
    )

    # Attach the reflexes to the things that own them (the heart of the demo).
    game.add_reaction(bat, reactions.FleesAtNoise(to=hollow))
    game.add_reaction(ogre, OgreWakes())
    game.add_reaction(fuse, FuseBurns())

    # Win: get back to the Ledge holding the gem.
    def _escape(g):
        g.parser.ok("You scramble up and out into the daylight, gem in hand. You win!")
        g.player.set_property("escaped", True)  # ReactionsDemo.is_won() reads this
        g.game_over = True
        g.game_over_description = "Escaped with the gem!"

    game.add_trigger(
        "escape",
        lambda g: g.player.location is ledge
        and "gem" in g.player.inventory
        and not g.game_over,
        _escape,
        repeatable=False,
    )
    return game


# ---------------------------------------------------------------------------
# A scripted tour (--walk) that fires every reaction, then a play loop.
# ---------------------------------------------------------------------------

WALKTHROUGH = [
    "examine bat",  # quiet: the bat stays put
    "in",  # -> Hollow (bat still on the Ledge)
    "examine ogre",  # fast asleep
    "ring gong",  # emit_sound carries 2 rooms: wakes the ogre AND spooks the bat
    "down",  # -> Shrine: the fuse lights (Countdown starts)
    "take gem",
    "cut fuse",  # cancel the countdown before it lands
    "up",  # -> Hollow
    "out",  # -> Ledge with the gem -> win
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
    print(f"WON: {game.is_won()}   GAME_OVER: {game.is_game_over()}")
    return game


if __name__ == "__main__":
    import sys

    if "--walk" in sys.argv:
        _run(WALKTHROUGH)
    else:
        build_game().game_loop()
