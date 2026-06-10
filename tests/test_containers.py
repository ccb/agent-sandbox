from text_adventure_games import games, things
from text_adventure_games.actions import things as thing_actions
from text_adventure_games.reporting import CaptureRenderer, Channel


def _capture_game(player_capacity=None):
    """A one-room world with a player. Returns (game, room, player, cap)
    where cap is a CaptureRenderer recording all parser output."""
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    player.carry_capacity = player_capacity
    game = games.Game(room, player, characters=[])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, room, player, cap


def _backpack(capacity=5):
    pack = things.Item("backpack", "a sturdy backpack")
    pack.make_container(capacity=capacity)
    return pack


def test_make_container_sets_properties():
    pack = _backpack(capacity=3)
    assert pack.get_property("is_container") is True
    assert pack.capacity == 3
    assert pack.contents == {}
    assert pack.current_count() == 0


def test_plain_item_is_not_a_container():
    rock = things.Item("rock", "a plain rock")
    assert rock.get_property("is_container") is False
    assert rock.capacity is None
    assert rock.contents == {}


def test_add_item_tracks_contents_and_backref():
    pack = _backpack(capacity=2)
    rock = things.Item("rock", "a plain rock")
    pack.add_item(rock)
    assert pack.contents["rock"] is rock
    assert rock.container is pack
    assert pack.current_count() == 1


def test_has_space_and_is_full_respect_capacity():
    pack = _backpack(capacity=1)
    assert pack.has_space() is True
    pack.add_item(things.Item("rock", "a plain rock"))
    assert pack.has_space() is False
    assert pack.is_full() is True


def test_unlimited_capacity_never_full():
    pack = _backpack(capacity=None)
    for i in range(10):
        pack.add_item(things.Item(f"thing{i}", "a thing"))
    assert pack.has_space() is True
    assert pack.is_full() is False


def test_remove_item_clears_backref():
    pack = _backpack(capacity=2)
    rock = things.Item("rock", "a plain rock")
    pack.add_item(rock)
    pack.remove_item(rock)
    assert "rock" not in pack.contents
    assert rock.container is None
