"""Event-based disturbance triggers (issue #25 readiness).

A disturbance is read from the *round's events* -- per actor, location-aware --
not from a single global ``parser.last_action`` that the next actor to move
would overwrite. These tests pin that down with a second character acting in
the same round, which is exactly what broke the old global-field approach.
"""

from text_adventure_games import games, things


def _two_actor_room():
    room = things.Location("Clearing", "A quiet clearing.")
    player = things.Character("you", "the player", "I explore.")
    ranger = things.Character("ranger", "a forest ranger", "I patrol.")
    game = games.Game(room, player, characters=[ranger])
    room.add_character(ranger)
    return game, player, ranger, room


def _quiet_behavior(c, g):
    g.parser.parse_command("look", actor=c)  # a quiet action every turn
    return None  # one action, done


def test_players_noise_registers_despite_an_npc_acting_after():
    game, player, ranger, room = _two_actor_room()
    fired = []
    game.add_disturbance_trigger(
        room, lambda g, cause: fired.append(cause), loud={"say"}
    )
    ranger.set_behavior(_quiet_behavior)  # the NPC moves after the player each round
    game.do_command("say boo")  # the PLAYER makes the noise
    # Old code read the global last_action at react time -- by then the ranger's
    # quiet "look" had clobbered it, so the player's "say" was missed. The event
    # log preserves it.
    assert fired == ["your sudden racket"]


def test_a_fully_quiet_round_does_not_fire():
    game, player, ranger, room = _two_actor_room()
    fired = []
    game.add_disturbance_trigger(
        room, lambda g, cause: fired.append(cause), loud={"say"}
    )
    ranger.set_behavior(_quiet_behavior)
    game.do_command("look")  # everyone quiet
    assert not fired


def test_an_npcs_noise_is_attributed_to_the_npc():
    game, player, ranger, room = _two_actor_room()
    causes = []
    game.add_disturbance_trigger(
        room, lambda g, cause: causes.append(cause), loud={"say"}
    )
    ranger.set_behavior(
        lambda c, g: (g.parser.parse_command("say oi", actor=c), None)[1]
    )
    game.do_command("look")  # the player is quiet; the ranger yells
    assert causes == ["the ranger's racket"]


def test_safe_set_framing_fires_on_anything_but_the_safe_actions():
    game, player, ranger, room = _two_actor_room()
    devoured = []
    game.add_disturbance_trigger(
        room, lambda g, cause: devoured.append(True), safe={"examine", "describe"}
    )
    game.do_command("look")  # describe -> safe, no fire
    assert not devoured
    game.do_command("say anything")  # not safe -> fires
    assert devoured
