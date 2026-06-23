"""Tests for the BREAK action.

Breaking a breakable item destroys it (spilling any contents into the room);
an item flagged ``break_keep`` is instead snapped free and kept -- Action
Castle's dead branch, which you BREAK off the tree to wield as a club.
"""

from text_adventure_games import games, things
from text_adventure_games.actions.things import Break
from text_adventure_games.reporting import CaptureRenderer, Channel


def _world():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I look around.")
    game = games.Game(room, player)
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, room, player, cap


def test_break_destroys_a_fragile_item():
    game, room, player, cap = _world()
    vase = things.Item("vase", "a delicate vase", "It looks fragile.")
    vase.set_property("is_fragile", True)
    room.add_item(vase)

    game.parser.parse_command("break vase")

    assert "vase" not in room.items
    assert "vase" not in player.inventory
    assert any("pieces" in t for t in cap.texts(Channel.NARRATION))


def test_break_refuses_unbreakable_items():
    game, room, player, cap = _world()
    anvil = things.Item("anvil", "a solid iron anvil", "Heavy and immovable.")
    room.add_item(anvil)

    game.parser.parse_command("break anvil")

    assert "anvil" in room.items  # still there
    assert any("can't break" in t for t in cap.texts(Channel.BLOCKED))


def test_break_keep_snaps_it_free_into_inventory():
    game, room, player, cap = _world()
    branch = things.Item("branch", "a stout dead branch", "A good club.")
    branch.set_property("is_fragile", True)
    branch.set_property("break_keep", True)
    branch.set_property("break_text", "You snap the branch free and take it.")
    room.add_item(branch)

    game.parser.parse_command("break branch")

    assert "branch" not in room.items
    assert "branch" in player.inventory  # kept, not destroyed
    assert any("snap" in t for t in cap.texts(Channel.NARRATION))


def test_breaking_a_container_spills_its_contents():
    game, room, player, cap = _world()
    crate = things.Item("crate", "a flimsy crate", "It could be smashed open.")
    crate.set_property("is_breakable", True)
    crate.set_property("is_container", True)
    coin = things.Item("coin", "a gold coin", "It glints.")
    crate.add_item(coin)
    room.add_item(crate)

    game.parser.parse_command("smash crate")  # alias routes too

    assert "crate" not in room.items
    assert "coin" in room.items  # spilled onto the floor, not vanished


def test_break_is_a_player_visible_action():
    # Sanity: BREAK should advertise itself (so HELP lists it).
    assert Break.PLAYER_VISIBLE is True
    assert "smash" in Break.ACTION_ALIASES
