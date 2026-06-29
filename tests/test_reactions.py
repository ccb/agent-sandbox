"""Phase 1 of the reactions design (docs/design/reactions.md): the engine
plumbing only -- GatedEffect / Reaction, Thing.reactions, game.add_reaction, and
react-phase evaluation via the trigger driver. No game behavior or sound model
yet (those are later phases); these pin down the mechanism.
"""

from text_adventure_games import games, things, actions
from text_adventure_games.reactions import GatedEffect, Reaction


def _room_with_player():
    room = things.Location("Clearing", "A quiet clearing.")
    player = things.Character("you", "the player", "I explore.")
    game = games.Game(room, player)
    return game, player, room


class _FlagReaction(Reaction):
    """Fires whenever its owner has the ``armed`` property set, recording the
    cause it stashed so a test can see gate->effect ran with state passed across."""

    def __init__(self):
        super().__init__()
        self.fired = []

    def check_preconditions(self):
        if self.owner.get_property("armed"):
            self.cause = "the owner is armed"
            return True
        return False

    def apply_effects(self):
        self.fired.append(self.cause)


class _RepeatingFlagReaction(_FlagReaction):
    REPEATABLE = True


def test_action_is_a_gated_effect():
    # Factoring __call__ out of Action must not change Action's identity contract.
    assert issubclass(actions.Action, GatedEffect)


def test_add_reaction_binds_owner_and_game_and_registers():
    game, player, room = _room_with_player()
    reaction = _FlagReaction()
    game.add_reaction(room, reaction)
    assert reaction.owner is room
    assert reaction.game is game
    assert reaction in room.reactions
    # Registered as a react-phase trigger under its stable name.
    assert any(t.name == "reaction:_FlagReaction:Clearing" for t in game.triggers)


def test_reaction_fires_in_react_phase_with_its_cause():
    game, player, room = _room_with_player()
    reaction = _FlagReaction()
    game.add_reaction(room, reaction)

    game.do_command("look")  # not armed -> no fire
    assert reaction.fired == []

    room.set_property("armed", True)
    game.do_command("look")  # armed -> fires in the react phase, cause carried over
    assert reaction.fired == ["the owner is armed"]


def test_one_shot_is_the_default():
    game, player, room = _room_with_player()
    reaction = _FlagReaction()  # REPEATABLE defaults False
    game.add_reaction(room, reaction)
    room.set_property("armed", True)
    game.do_command("look")
    game.do_command("look")  # stimulus still present, but a one-shot won't re-fire
    assert reaction.fired == ["the owner is armed"]


def test_repeatable_reaction_refires_each_round():
    game, player, room = _room_with_player()
    reaction = _RepeatingFlagReaction()
    game.add_reaction(room, reaction)
    room.set_property("armed", True)
    game.do_command("look")
    game.do_command("look")
    assert reaction.fired == ["the owner is armed", "the owner is armed"]


def test_reactions_are_not_serialized():
    # Runtime-only, like behavior: the reflex must not leak into to_primitive.
    game, player, room = _room_with_player()
    game.add_reaction(room, _FlagReaction())
    assert "reactions" not in room.to_primitive()
