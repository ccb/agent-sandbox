"""Posed-prompt mechanism (issue #110).

Builds a tiny two-room game with one custom verb and exercises the engine
plumbing: a choice prompt resolves a bare keyword to its command, a free-text
prompt forwards the whole reply, prompts are a non-modal fallback (real verbs
still win), and a prompt expires when the player walks away.
"""

from text_adventure_games import games, things, actions, Prompt
from text_adventure_games.reporting import CaptureRenderer, Channel

# --- a minimal world with one custom "press <color>" verb ------------------


class PressButton(actions.Action):
    """A stand-in choice target: `press red` / `press blue`, recorded on the
    game so tests can assert which command actually ran."""

    ACTION_NAME = "press"
    ACTION_DESCRIPTION = "Press a colored button"
    ACTION_ALIASES = ["press red", "press blue"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.command = command.lower()

    def check_preconditions(self):
        return True

    def apply_effects(self):
        color = "red" if "red" in self.command else "blue"
        self.game.pressed = color
        self.parser.ok(f"You press the {color} button.")


class Answer(actions.Action):
    """A free-text target: stores whatever was said after the verb."""

    ACTION_NAME = "answer"
    ACTION_DESCRIPTION = "Answer aloud"
    ACTION_ALIASES = []

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.command = command.lower()

    def check_preconditions(self):
        return True

    def apply_effects(self):
        # everything after the verb "answer"
        self.game.answered = self.command.split("answer", 1)[1].strip()
        self.parser.ok(f"You say: {self.game.answered}")


def _build():
    hall = things.Location("Hall", "A bare hall. An exit leads north.")
    yard = things.Location("Yard", "An open yard. An exit leads south.")
    hall.add_connection("north", yard)
    yard.add_connection("south", hall)
    player = things.Character("you", "the player", "I am here.")
    game = games.Game(hall, player, characters=[], custom_actions=[PressButton, Answer])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, cap


def _said(cap, substring):
    return any(
        substring in t
        for ch in (Channel.NARRATION, Channel.BLOCKED)
        for t in cap.texts(ch)
    )


# --- choice prompts --------------------------------------------------------


def test_choice_prompt_resolves_bare_keyword_to_its_command():
    game, cap = _build()
    game.pose_prompt(
        Prompt(text="Red or blue?", options={"red": "press red", "blue": "press blue"})
    )
    game.do_command("blue")  # a bare keyword, not a recognized verb on its own
    assert game.pressed == "blue"
    assert _said(cap, "You press the blue button.")
    assert game.pending_prompt() is None  # answered -> cleared


def test_unmatched_reply_to_a_choice_prompt_is_still_not_understood():
    game, cap = _build()
    game.pose_prompt(Prompt(options={"red": "press red", "blue": "press blue"}))
    game.do_command("green")  # answers nothing
    assert _said(cap, "I'm not sure what you want to do.")
    assert game.pending_prompt() is not None  # not consumed by a non-answer


def test_prompt_is_a_fallback_real_verbs_still_win():
    game, cap = _build()
    game.pose_prompt(Prompt(options={"red": "press red", "blue": "press blue"}))
    game.do_command("look")  # a real action -- not swallowed as an answer
    assert _said(cap, "bare hall")
    assert game.pending_prompt() is not None  # look didn't answer the question
    assert getattr(game, "pressed", None) is None


# --- free-text prompts -----------------------------------------------------


def test_free_text_prompt_forwards_the_whole_reply():
    game, cap = _build()
    game.pose_prompt(Prompt(text="What is the password?", forward_as="answer"))
    game.do_command("a wise man")  # not a verb; forwarded to "answer ..."
    assert game.answered == "a wise man"
    assert _said(cap, "You say: a wise man")
    assert game.pending_prompt() is None


# --- lifecycle -------------------------------------------------------------


def test_prompt_expires_when_the_player_leaves_the_room():
    game, cap = _build()
    game.pose_prompt(Prompt(options={"red": "press red"}))
    game.do_command("north")  # walk away from where it was asked
    assert game.player.location.name == "Yard"
    assert game.pending_prompt() is None
    game.do_command("red")  # no longer an answer to anything
    assert _said(cap, "I'm not sure what you want to do.")
    assert getattr(game, "pressed", None) is None


def test_sticky_prompt_survives_a_move():
    game, cap = _build()
    game.pose_prompt(Prompt(options={"red": "press red"}, sticky=True))
    game.do_command("north")
    assert game.pending_prompt() is not None
    game.do_command("red")
    assert game.pressed == "red"


def test_posing_a_prompt_replaces_the_previous_one():
    game, _ = _build()
    game.pose_prompt(Prompt(options={"red": "press red"}))
    game.pose_prompt(Prompt(options={"blue": "press blue"}))
    game.do_command("red")  # the first prompt's keyword no longer applies
    assert getattr(game, "pressed", None) is None
    game.do_command("blue")
    assert game.pressed == "blue"


def test_choice_keywords_match_on_word_boundaries():
    # "no" must not fire inside an unrecognized word that merely contains it.
    game, cap = _build()
    game.pose_prompt(Prompt(options={"yes": "press red", "no": "press blue"}))
    game.do_command("snowing")  # not a verb; contains "no" only as a substring
    assert _said(cap, "I'm not sure what you want to do.")
    assert getattr(game, "pressed", None) is None
    assert game.pending_prompt() is not None  # still awaiting a real answer
