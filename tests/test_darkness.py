"""The engine Darkness block (promoted from the Action Castle adventure).

A dark room blocks an exit until someone present carries a lit light source --
in hand, worn, wielded, or inside an open carried container (a lit lantern in
an open backpack still lights the way; a closed pack does not).
"""

from text_adventure_games import games, things
from text_adventure_games.blocks import Darkness
from text_adventure_games.enums import Property
from text_adventure_games.reporting import CaptureRenderer, Channel


def _lantern(lit=False):
    lamp = things.Item("lantern", "a brass lantern", "A brass lantern.")
    lamp.set_property(Property.FLAMMABLE, True)
    lamp.set_property(Property.IS_LIT, lit)
    return lamp


def _build(player_items=()):
    """A lit entrance with a dark 'in' exit to a cave."""
    entrance = things.Location("Entrance", "A rocky entrance. A gap leads in.")
    cave = things.Location("Cave", "A pitch-black cave.")
    entrance.add_connection("in", cave)
    cave.add_connection("out", entrance)
    entrance.add_block("in", Darkness(entrance))
    player = things.Character("you", "the player", "I am here.")
    for it in player_items:
        player.add_to_inventory(it)
    game = games.Game(entrance, player, characters=[])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, cap


def _said(cap, substring):
    return any(
        substring in t
        for ch in (Channel.NARRATION, Channel.BLOCKED)
        for t in cap.texts(ch)
    )


# --- the block in isolation ------------------------------------------------


def test_dark_exit_is_blocked_with_no_light():
    game, _ = _build()
    assert game.start_at.get_property(Property.IS_DARK)
    assert game.start_at.is_blocked("in")


def test_a_lit_item_in_hand_clears_the_darkness():
    game, _ = _build(player_items=[_lantern(lit=True)])
    assert not game.start_at.is_blocked("in")


def test_an_unlit_item_does_not_clear_the_darkness():
    game, _ = _build(player_items=[_lantern(lit=False)])
    assert game.start_at.is_blocked("in")


def test_a_lit_lantern_in_an_open_backpack_lights_the_way():
    pack = things.Item("backpack", "a backpack").make_container()
    pack.add_item(_lantern(lit=True))
    game, _ = _build(player_items=[pack])
    assert not game.start_at.is_blocked("in")


def test_a_lit_lantern_in_a_closed_backpack_does_not():
    pack = things.Item("backpack", "a backpack").make_container()
    pack.add_item(_lantern(lit=True))
    pack.set_property("is_closed", True)
    game, _ = _build(player_items=[pack])
    assert game.start_at.is_blocked("in")


def test_light_leaves_with_the_only_lit_character():
    # The block reads live state: nobody present with light -> blocked again.
    lamp = _lantern(lit=True)
    game, _ = _build(player_items=[lamp])
    assert not game.start_at.is_blocked("in")
    lamp.set_property(Property.IS_LIT, False)
    assert game.start_at.is_blocked("in")


# --- end to end: light the lantern, then the exit opens --------------------


def test_cannot_enter_the_dark_until_the_lantern_is_lit():
    game, cap = _build(player_items=[_lantern(lit=False)])
    game.do_command("go in")
    assert _said(cap, "too dark")
    assert game.player.location.name == "Entrance"  # didn't move

    game.do_command("light lantern")
    game.do_command("go in")
    assert game.player.location.name == "Cave"  # now it's passable
