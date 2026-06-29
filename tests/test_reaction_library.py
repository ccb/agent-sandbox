"""Phase 3 of the reactions design (docs/design/reactions.md): the reusable
reaction library -- FleesAtNoise / WakesAtNoise (startle on any perceived sound)
and Countdown (a stimulus starts a cancelable timed consequence). Driven with a
small noisy test action; no game wiring yet (that's the migration phase).
"""

from text_adventure_games import games, things, actions, reactions


class _Noise(actions.base.Action):
    """A loud test command: carries one room and reads as 'a loud noise'."""

    ACTION_NAME = "noise"
    AUDIBLE_RADIUS = 1

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)

    def check_preconditions(self):
        return True

    def apply_effects(self):
        self.parser.ok("You make a din.")

    def sound_description(self):
        return "a loud noise"


def _line(*names):
    rooms = [things.Location(n, f"Room {n}.") for n in names]
    for a, b in zip(rooms, rooms[1:]):
        a.add_connection("north", b)
    player = things.Character("you", "the player", "I explore.")
    game = games.Game(rooms[0], player)
    game.parser.add_action(_Noise)
    return game, player, rooms


# --- FleesAtNoise -----------------------------------------------------------


def test_flees_at_noise_relocates_the_owner():
    game, player, (woods, deep) = _line("Woods", "Deep Woods")
    deer = things.Item("deer", "a doe", "A grazing doe.")
    woods.add_item(deer)
    game.add_reaction(deer, reactions.FleesAtNoise(to=deep))

    game.do_command("noise")  # player makes noise in the Woods, where the doe is
    assert "deer" not in woods.items
    assert "deer" in deep.items
    # The flight is logged as a move, so it is a perceivable arrival others react to.
    assert game.entered_this_round(deer, deep)


def test_flees_at_noise_is_one_shot():
    game, player, (woods, deep) = _line("Woods", "Deep Woods")
    deer = things.Item("deer", "a doe", "A grazing doe.")
    woods.add_item(deer)
    game.add_reaction(deer, reactions.FleesAtNoise(to=deep))
    game.do_command("noise")
    game.do_command("noise")  # already fled; a one-shot doesn't re-fire
    assert "deer" in deep.items


def test_flees_only_when_a_noise_is_actually_heard():
    game, player, (woods, deep) = _line("Woods", "Deep Woods")
    deer = things.Item("deer", "a doe", "A grazing doe.")
    woods.add_item(deer)
    game.add_reaction(deer, reactions.FleesAtNoise(to=deep))
    game.do_command("look")  # silent
    assert "deer" in woods.items


# --- WakesAtNoise -----------------------------------------------------------


def test_wakes_at_noise_clears_the_asleep_flag():
    game, player, (cave,) = _line("Cave")
    dragon = things.Character("dragon", "a dragon", "I hoard.")
    cave.add_character(dragon)
    dragon.set_property("asleep", True)
    game.add_reaction(dragon, reactions.WakesAtNoise())

    game.do_command("noise")
    assert dragon.get_property("asleep") is False


def test_does_not_wake_when_already_awake():
    game, player, (cave,) = _line("Cave")
    dragon = things.Character("dragon", "a dragon", "I hoard.")
    cave.add_character(dragon)
    dragon.set_property("asleep", False)  # not sleeping -> nothing to wake
    fired = []

    class _Watch(reactions.WakesAtNoise):
        def wake(self):
            fired.append(True)

    game.add_reaction(dragon, _Watch())
    game.do_command("noise")
    assert fired == []


# --- Countdown --------------------------------------------------------------


class _Boom(reactions.Countdown):
    DELAY = 2

    def __init__(self, trigger_loc):
        super().__init__()
        self.trigger_loc = trigger_loc
        self.boomed = []
        self.disarmed = False

    def stimulus(self):
        return self.game.entered_this_round(self.game.player, self.trigger_loc)

    def cancelled(self):
        return self.disarmed

    def warning(self):
        return "A fuse hisses..."

    def consequence(self, game):
        self.boomed.append(game.turn)


def test_countdown_fires_its_consequence_after_the_delay():
    game, player, (a, b) = _line("A", "B")
    boom = _Boom(trigger_loc=b)
    game.add_reaction(b, boom)

    game.do_command("go north")  # enter B -> countdown starts (turn 1), resolves at turn 3
    assert boom.boomed == []
    game.do_command("look")  # turn 2
    assert boom.boomed == []
    game.do_command("look")  # turn 3 -> boom
    assert boom.boomed == [3]


def test_countdown_can_be_cancelled_before_it_lands():
    game, player, (a, b) = _line("A", "B")
    boom = _Boom(trigger_loc=b)
    game.add_reaction(b, boom)

    game.do_command("go north")  # countdown starts
    boom.disarmed = True  # averted before it lands
    game.do_command("look")
    game.do_command("look")
    assert boom.boomed == []
