"""Tests for the Tier 2 perception verbs: READ and SEARCH + hidden items.

READ prints an item's ``read_text``. SEARCH reveals items flagged ``is_hidden``
-- which until found are invisible: not in the room description, not in scope
(can't be examined), and not gettable.
"""

from text_adventure_games import games, things
from text_adventure_games.reporting import CaptureRenderer, Channel


def _world():
    """A room holding a readable sign, a plain rock, a hidden pendant lying in
    the room, and a closed desk concealing a hidden key."""
    room = things.Location("Cell", "A damp dungeon cell.")
    player = things.Character("player", "the player", "I explore.")

    sign = things.Item("sign", "a scratched sign", "")
    sign.set_property("gettable", False)
    sign.set_property("read_text", "Beware the troll on the drawbridge.")
    room.add_item(sign)

    rock = things.Item("rock", "an ordinary rock")
    rock.set_property("gettable", False)
    room.add_item(rock)

    pendant = things.Item("pendant", "a pewter holy symbol")
    pendant.set_property("is_hidden", True)
    room.add_item(pendant)

    desk = things.Item("desk", "a battered writing desk")
    desk.set_property("gettable", False)
    desk.make_container()
    desk.set_property("is_closed", True)
    key = things.Item("key", "a small brass key")
    key.set_property("is_hidden", True)
    desk.add_item(key)
    room.add_item(desk)

    game = games.Game(room, player)
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, cap


def _said(cap, substring):
    return any(
        substring in t
        for ch in (Channel.NARRATION, Channel.BLOCKED)
        for t in cap.texts(ch)
    )


# --- READ ------------------------------------------------------------------


def test_read_prints_read_text():
    game, cap = _world()
    game.do_command("read sign")
    assert _said(cap, "Beware the troll on the drawbridge.")


def test_read_non_readable_item_fails():
    game, cap = _world()
    game.do_command("read rock")
    assert _said(cap, "nothing to read on the rock")


def test_read_missing_item_fails():
    game, cap = _world()
    game.do_command("read diary")
    assert _said(cap, "I don't see it.")


def test_read_works_on_a_carried_item():
    game, cap = _world()
    note = things.Item("note", "a crumpled note")
    note.set_property("read_text", "Meet me at midnight.")
    game.player.add_to_inventory(note)
    game.do_command("read note")
    assert _said(cap, "Meet me at midnight.")


# --- hidden items are concealed until found --------------------------------


def test_hidden_item_not_in_room_description():
    game, _ = _world()
    assert "pendant" not in game.describe_items()


def test_hidden_item_not_examinable():
    game, cap = _world()
    game.do_command("examine pendant")
    assert not _said(cap, "pewter holy symbol")
    assert _said(cap, "don't see anything special")


def test_hidden_item_not_gettable():
    game, cap = _world()
    game.do_command("take pendant")
    assert "pendant" not in game.player.inventory


# --- SEARCH reveals -------------------------------------------------------


def test_search_room_reveals_hidden_item():
    game, cap = _world()
    game.do_command("search")
    assert _said(cap, "pewter holy symbol")
    # Now it's a normal item: described, examinable, gettable.
    assert not game.start_at.items["pendant"].get_property("is_hidden")
    assert "pendant" in game.describe_items()
    game.do_command("take pendant")
    assert "pendant" in game.player.inventory


def test_search_named_holder_reveals_its_hidden_contents_even_when_closed():
    game, cap = _world()
    game.do_command("search desk")
    assert _said(cap, "small brass key")
    key = game.start_at.items["desk"].contents["key"]
    assert not key.get_property("is_hidden")


def test_search_finds_nothing_when_already_revealed():
    game, cap = _world()
    game.do_command("search")  # reveals pendant
    cap2 = CaptureRenderer()
    game.parser.set_renderer(cap2)
    game.do_command("search")  # nothing hidden left in the room
    assert any("nothing of interest" in t for t in cap2.texts(Channel.NARRATION))
