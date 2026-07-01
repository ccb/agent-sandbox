"""Worn and wielded items are in scope (engine): you can EXAMINE the gown you
have on or the sword in your hand, not just things on the ground or in a pack."""

from text_adventure_games import games, things
from text_adventure_games.actions import things as thing_actions
from text_adventure_games.reporting import CaptureRenderer, Channel


def _world():
    room = things.Location("Hall", "A plain hall.")
    player = things.Character("you", "the looker", "I look.")
    game = games.Game(room, player, characters=[])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, room, player, cap


def _said(cap, sub):
    return any(
        sub in t for ch in (Channel.NARRATION, Channel.BLOCKED) for t in cap.texts(ch)
    )


def test_scope_includes_worn_and_wielded():
    game, room, player, cap = _world()
    gown = things.Item("gown", "a fine gown", "Layers of silk.")
    sword = things.Item("sword", "a steel sword", "Notched but sharp.")
    player.inventory["gown"] = gown
    player.inventory["sword"] = sword
    player.wear(gown)
    player.wield(sword)
    scope = game.parser.get_items_in_scope(player)
    assert scope.get("gown") is gown
    assert scope.get("sword") is sword


def test_examine_a_worn_item():
    game, room, player, cap = _world()
    gown = things.Item("gown", "a fine gown", "Layers of silk.")
    player.inventory["gown"] = gown
    player.wear(gown)
    thing_actions.Examine(game, "examine gown", actor=player)()
    assert _said(cap, "Layers of silk.")


def test_examine_a_wielded_item():
    game, room, player, cap = _world()
    sword = things.Item("sword", "a steel sword", "Notched but sharp.")
    player.inventory["sword"] = sword
    player.wield(sword)
    thing_actions.Examine(game, "examine sword", actor=player)()
    assert _said(cap, "Notched but sharp.")
