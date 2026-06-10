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


def test_container_round_trips_through_primitive():
    pack = _backpack(capacity=4)
    pack.add_item(things.Item("rock", "a plain rock"))
    pack.add_item(things.Item("gem", "a shiny gem"))

    restored = things.Item.from_primitive(pack.to_primitive())

    assert restored.get_property("is_container") is True
    assert restored.capacity == 4
    assert set(restored.contents.keys()) == {"rock", "gem"}
    assert restored.contents["rock"].description == "a plain rock"
    assert restored.contents["rock"].container is None  # back-ref by name only


def test_unlimited_hands_always_have_space():
    player = things.Character("player", "the player", "I explore.")
    assert player.carry_capacity is None
    assert player.has_hand_space() is True


def test_finite_hands_fill_up():
    player = things.Character("player", "the player", "I explore.")
    player.carry_capacity = 1
    assert player.has_hand_space() is True
    player.add_to_inventory(things.Item("rock", "a plain rock"))
    assert player.has_hand_space() is False


def test_accept_item_routes_overflow_into_container():
    player = things.Character("player", "the player", "I explore.")
    player.carry_capacity = 1
    pack = _backpack(capacity=2)
    player.add_to_inventory(pack)  # fills the single hand slot
    assert player.has_hand_space() is False

    rock = things.Item("rock", "a plain rock")
    placed = player.accept_item(rock)
    assert placed is True
    assert rock.container is pack
    assert "rock" in pack.contents


def test_accept_item_fails_when_hands_and_containers_full():
    player = things.Character("player", "the player", "I explore.")
    player.carry_capacity = 1
    pack = _backpack(capacity=1)
    player.add_to_inventory(pack)
    player.accept_item(things.Item("rock", "a plain rock"))  # fills the pack
    assert player.accept_item(things.Item("gem", "a gem")) is False


def test_carried_items_flattens_hands_and_containers():
    player = things.Character("player", "the player", "I explore.")
    pack = _backpack(capacity=3)
    player.add_to_inventory(pack)
    pack.add_item(things.Item("rock", "a plain rock"))
    carried = player.carried_items()
    assert set(carried.keys()) == {"backpack", "rock"}


def test_discard_item_removes_from_container_or_hands():
    player = things.Character("player", "the player", "I explore.")
    pack = _backpack(capacity=3)
    player.add_to_inventory(pack)
    rock = things.Item("rock", "a plain rock")
    pack.add_item(rock)
    player.discard_item(rock)
    assert "rock" not in pack.contents
    assert rock.container is None
    player.discard_item(pack)
    assert "backpack" not in player.inventory


def test_carry_capacity_round_trips():
    player = things.Character("player", "the player", "I explore.")
    player.carry_capacity = 2
    restored = things.Character.from_primitive(player.to_primitive())
    assert restored.carry_capacity == 2


def test_get_with_unlimited_hands_is_unchanged():
    game, room, player, cap = _capture_game(player_capacity=None)
    rock = things.Item("rock", "a plain rock")
    room.add_item(rock)
    thing_actions.Get(game, "get rock", actor=player)()
    assert "rock" in player.inventory
    assert cap.texts(Channel.NARRATION)  # a success message was emitted


def test_get_overflows_into_backpack():
    game, room, player, cap = _capture_game(player_capacity=1)
    pack = _backpack(capacity=2)
    player.add_to_inventory(pack)  # the one hand slot is now full
    rock = things.Item("rock", "a plain rock")
    room.add_item(rock)

    thing_actions.Get(game, "get rock", actor=player)()

    assert "rock" not in player.inventory  # not in hands
    assert "rock" in pack.contents  # stowed in the pack
    assert "rock" not in room.items  # left the room


def test_get_fails_gracefully_when_full():
    game, room, player, cap = _capture_game(player_capacity=1)
    pack = _backpack(capacity=1)
    player.add_to_inventory(pack)
    player.accept_item(things.Item("gem", "a gem"))  # fills the pack
    rock = things.Item("rock", "a plain rock")
    room.add_item(rock)

    action = thing_actions.Get(game, "get rock", actor=player)
    assert action.check_preconditions() is False
    assert "rock" in room.items  # world state unchanged
    assert "full" in (game.parser.last_fail_message or "").lower()


def test_drop_item_stowed_in_backpack():
    game, room, player, cap = _capture_game(player_capacity=1)
    pack = _backpack(capacity=2)
    player.add_to_inventory(pack)
    rock = things.Item("rock", "a plain rock")
    pack.add_item(rock)

    thing_actions.Drop(game, "drop rock", actor=player)()

    assert "rock" not in pack.contents
    assert rock.container is None
    assert "rock" in room.items


def test_drop_item_held_in_hand():
    game, room, player, cap = _capture_game(player_capacity=None)
    rock = things.Item("rock", "a plain rock")
    player.add_to_inventory(rock)

    thing_actions.Drop(game, "drop rock", actor=player)()

    assert "rock" not in player.inventory
    assert "rock" in room.items
    assert rock.location is room


def _capture_two_char_game(giver_cap=None, recipient_cap=None):
    room = things.Location("Room", "A plain room.")
    giver = things.Character("giver", "the giver", "I give.")
    giver.carry_capacity = giver_cap
    recipient = things.Character("recipient", "the recipient", "I receive.")
    recipient.carry_capacity = recipient_cap
    game = games.Game(room, giver, characters=[recipient])
    room.add_character(recipient)
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, room, giver, recipient, cap


def test_give_stowed_item_routes_into_recipient():
    game, room, giver, recipient, cap = _capture_two_char_game()
    pack = _backpack(capacity=2)
    giver.add_to_inventory(pack)
    rock = things.Item("rock", "a plain rock")
    pack.add_item(rock)

    thing_actions.Give(game, "give rock to recipient", actor=giver)()

    assert "rock" not in pack.contents
    assert "rock" in recipient.inventory


def test_give_fails_gracefully_when_recipient_full():
    game, room, giver, recipient, cap = _capture_two_char_game(recipient_cap=0)
    rock = things.Item("rock", "a plain rock")
    giver.add_to_inventory(rock)

    action = thing_actions.Give(game, "give rock to recipient", actor=giver)
    assert action.check_preconditions() is False
    assert "rock" in giver.inventory  # still with the giver
    assert "rock" not in recipient.inventory


def test_inventory_shows_container_contents_and_capacity():
    game, room, player, cap = _capture_game(player_capacity=None)
    pack = _backpack(capacity=5)
    player.add_to_inventory(pack)
    pack.add_item(things.Item("rock", "a plain rock"))
    pack.add_item(things.Item("gem", "a shiny gem"))

    thing_actions.Inventory(game, "inventory", actor=player)()

    text = "\n".join(cap.texts(Channel.NARRATION))
    assert "backpack" in text
    assert "(2/5)" in text  # count / capacity
    assert "a plain rock" in text  # nested content shown
    assert "a shiny gem" in text


def test_inventory_unlimited_container_shows_count_only():
    game, room, player, cap = _capture_game(player_capacity=None)
    pack = _backpack(capacity=None)
    player.add_to_inventory(pack)
    pack.add_item(things.Item("rock", "a plain rock"))

    thing_actions.Inventory(game, "inventory", actor=player)()

    text = "\n".join(cap.texts(Channel.NARRATION))
    assert "(1)" in text  # count only, no slash
    assert "/" not in text.split("backpack")[1].split("\n")[0]


def test_inventory_empty_is_unchanged():
    game, room, player, cap = _capture_game(player_capacity=None)
    thing_actions.Inventory(game, "inventory", actor=player)()
    text = "\n".join(cap.texts(Channel.NARRATION))
    assert "empty" in text
