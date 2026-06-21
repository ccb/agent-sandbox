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


def test_give_loaded_container_refreshes_nested_owner():
    game, room, giver, recipient, cap = _capture_two_char_game()
    pack = _backpack(capacity=2)
    giver.add_to_inventory(pack)
    rock = things.Item("rock", "a plain rock")
    pack.add_item(rock)
    assert rock.owner is giver  # the rock rides along with the giver

    thing_actions.Give(game, "give backpack to recipient", actor=giver)()

    assert "backpack" in recipient.inventory
    assert pack.owner is recipient
    assert rock.owner is recipient  # nested content changed hands too


def test_give_food_into_container_is_still_eaten_when_hungry():
    # Recipient's single hand is full of a backpack, so the gifted food is
    # routed into the pack. A hungry recipient must still eat it -- the
    # eat follow-up has to see container contents, not just top-level hands.
    game, room, giver, recipient, cap = _capture_two_char_game(recipient_cap=1)
    pack = _backpack(capacity=2)
    recipient.add_to_inventory(pack)  # the one hand slot is now full
    recipient.set_property("is_hungry", True)
    apple = things.Item("apple", "a crisp apple")
    apple.set_property("edible", True)
    giver.add_to_inventory(apple)

    thing_actions.Give(game, "give apple to recipient", actor=giver)()

    assert recipient.get_property("is_hungry") is False  # they ate it
    assert "apple" not in pack.contents  # consumed, not just stowed
    assert "apple" not in recipient.carried_items()


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


# ---------------------------------------------------------------------------
# Containers sitting in a ROOM: take items out of them, and examine to peek in.
# (A boat holding a blanket; a chest holding a key.)
# ---------------------------------------------------------------------------


def _room_chest(room, *, closed=False, gettable=False):
    """A non-gettable chest container placed in *room*."""
    chest = things.Item("chest", "a wooden chest", "An old oak chest.")
    chest.set_property("gettable", gettable)
    chest.make_container()
    if closed:
        chest.set_property("is_closed", True)
    room.add_item(chest)
    return chest


def test_get_takes_item_from_open_room_container():
    game, room, player, cap = _capture_game(player_capacity=None)
    chest = _room_chest(room)
    key = things.Item("key", "a brass key")
    chest.add_item(key)

    thing_actions.Get(game, "take key", actor=player)()

    assert "key" in player.inventory  # now in hand
    assert "key" not in chest.contents  # removed from the chest
    assert key.container is None
    assert cap.texts(Channel.NARRATION)  # a success message was emitted


def test_get_from_room_container_overflows_into_backpack():
    game, room, player, cap = _capture_game(player_capacity=1)
    pack = _backpack(capacity=2)
    player.add_to_inventory(pack)  # the one hand slot is now full
    chest = _room_chest(room)
    chest.add_item(things.Item("key", "a brass key"))

    thing_actions.Get(game, "take key", actor=player)()

    assert "key" not in player.inventory  # hands were full
    assert "key" in pack.contents  # stowed in the carried pack
    assert "key" not in chest.contents  # left the chest


def test_non_gettable_room_container_itself_cannot_be_taken():
    game, room, player, cap = _capture_game(player_capacity=None)
    _room_chest(room)  # gettable=False
    action = thing_actions.Get(game, "take chest", actor=player)
    assert action.check_preconditions() is False
    assert "chest" in room.items  # the chest stays put


def test_closed_room_container_hides_contents_from_get():
    game, room, player, cap = _capture_game(player_capacity=None)
    chest = _room_chest(room, closed=True)
    chest.add_item(things.Item("key", "a brass key"))

    action = thing_actions.Get(game, "take key", actor=player)
    assert action.check_preconditions() is False  # can't take what you can't see
    assert "key" in chest.contents  # still inside the closed chest


def test_examine_lists_open_container_contents():
    game, room, player, cap = _capture_game(player_capacity=None)
    chest = _room_chest(room)
    chest.add_item(things.Item("key", "a brass key"))

    thing_actions.Examine(game, "examine chest", actor=player)()

    text = "\n".join(cap.texts(Channel.NARRATION))
    assert "An old oak chest." in text
    assert "It contains a brass key." in text


def test_examine_joins_multiple_contents():
    game, room, player, cap = _capture_game(player_capacity=None)
    chest = _room_chest(room)
    chest.add_item(things.Item("key", "a brass key"))
    chest.add_item(things.Item("coin", "a gold coin"))

    thing_actions.Examine(game, "examine chest", actor=player)()

    text = "\n".join(cap.texts(Channel.NARRATION))
    assert "It contains a brass key and a gold coin." in text


def test_examine_empty_container_omits_contents_sentence():
    game, room, player, cap = _capture_game(player_capacity=None)
    _room_chest(room)  # empty

    thing_actions.Examine(game, "examine chest", actor=player)()

    text = "\n".join(cap.texts(Channel.NARRATION))
    assert "An old oak chest." in text
    assert "It contains" not in text  # no contents line, no "It's empty" noise


def test_examine_closed_container_omits_contents_sentence():
    game, room, player, cap = _capture_game(player_capacity=None)
    chest = _room_chest(room, closed=True)
    chest.add_item(things.Item("key", "a brass key"))

    thing_actions.Examine(game, "examine chest", actor=player)()

    text = "\n".join(cap.texts(Channel.NARRATION))
    assert "It contains" not in text


def test_examine_item_inside_open_room_container():
    game, room, player, cap = _capture_game(player_capacity=None)
    chest = _room_chest(room)
    chest.add_item(things.Item("key", "a brass key", "A small brass key, worn smooth."))

    thing_actions.Examine(game, "examine key", actor=player)()

    text = "\n".join(cap.texts(Channel.NARRATION))
    assert "worn smooth" in text  # reachable by name even though it's in the chest


def test_take_from_container_then_drop_to_room():
    game, room, player, cap = _capture_game(player_capacity=None)
    chest = _room_chest(room)
    chest.add_item(things.Item("key", "a brass key"))

    thing_actions.Get(game, "take key", actor=player)()
    thing_actions.Drop(game, "drop key", actor=player)()

    assert "key" in room.items  # back in the room, loose
    assert "key" not in chest.contents
    assert "key" not in player.inventory


# ---------------------------------------------------------------------------
# Surfaces (surfaces): things rest ON them and are always in view. PUT to
# place, GET to take, OPEN/CLOSE for containers. (A candle on a table.)
# ---------------------------------------------------------------------------


def _room_surface(room, *, capacity=None):
    table = things.Item("table", "a sturdy table", "An oak table.")
    table.set_property("gettable", False)
    table.make_surface(capacity=capacity)
    room.add_item(table)
    return table


def test_make_surface_sets_holder_properties():
    table = things.Item("table", "a table")
    table.make_surface()
    assert table.get_property("is_surface")
    assert table.is_holder() and table.is_open()  # surfaces are always open
    assert table.preposition() == "on"


def test_get_takes_item_off_a_room_surface():
    game, room, player, cap = _capture_game(player_capacity=None)
    table = _room_surface(room)
    table.add_item(things.Item("candle", "a wax candle"))

    thing_actions.Get(game, "take candle", actor=player)()

    assert "candle" in player.inventory
    assert "candle" not in table.contents


def test_examine_surface_lists_what_is_on_it():
    game, room, player, cap = _capture_game(player_capacity=None)
    table = _room_surface(room)
    table.add_item(things.Item("candle", "a wax candle"))

    thing_actions.Examine(game, "examine table", actor=player)()

    text = "\n".join(cap.texts(Channel.NARRATION))
    assert "An oak table." in text
    assert "On it you see a wax candle." in text


def test_room_description_shows_items_on_a_surface():
    game, room, player, cap = _capture_game(player_capacity=None)
    table = _room_surface(room)
    table.add_item(things.Item("candle", "a wax candle"))

    desc = game.describe_items()
    assert "table" in desc
    assert "on it: a wax candle" in desc


def test_put_item_on_a_surface():
    game, room, player, cap = _capture_game(player_capacity=None)
    table = _room_surface(room)
    player.add_to_inventory(things.Item("candle", "a wax candle"))

    game.do_command("put candle on table")

    assert "candle" in table.contents
    assert "candle" not in player.inventory


def test_put_item_in_a_container():
    game, room, player, cap = _capture_game(player_capacity=None)
    chest = _room_chest(room)  # an open container in the room
    player.add_to_inventory(things.Item("coin", "a gold coin"))

    game.do_command("put coin in chest")

    assert "coin" in chest.contents
    assert "coin" not in player.inventory


def test_put_wrong_relation_is_refused():
    game, room, player, cap = _capture_game(player_capacity=None)
    table = _room_surface(room)  # a surface wants "on", not "in"
    player.add_to_inventory(things.Item("coin", "a gold coin"))

    game.do_command("put coin in table")

    assert "coin" not in table.contents
    assert "coin" in player.inventory
    assert "can't put things in the table" in (game.parser.last_fail_message or "")


def test_put_into_closed_container_is_refused():
    game, room, player, cap = _capture_game(player_capacity=None)
    _room_chest(room, closed=True)
    player.add_to_inventory(things.Item("coin", "a gold coin"))

    game.do_command("put coin in chest")

    assert "closed" in (game.parser.last_fail_message or "").lower()


def test_put_respects_capacity():
    game, room, player, cap = _capture_game(player_capacity=None)
    table = _room_surface(room, capacity=1)
    table.add_item(things.Item("vase", "a vase"))  # fills the surface
    player.add_to_inventory(things.Item("candle", "a wax candle"))

    game.do_command("put candle on table")

    assert "candle" not in table.contents
    assert "full" in (game.parser.last_fail_message or "").lower()


def test_open_makes_container_contents_takeable():
    game, room, player, cap = _capture_game(player_capacity=None)
    chest = _room_chest(room, closed=True)
    chest.add_item(things.Item("key", "a brass key"))

    # closed -> can't take what you can't see
    assert (
        thing_actions.Get(game, "take key", actor=player).check_preconditions() is False
    )
    game.do_command("open chest")
    assert chest.get_property("is_closed") is False
    game.do_command("take key")
    assert "key" in player.inventory


def test_close_hides_container_contents_from_examine():
    game, room, player, cap = _capture_game(player_capacity=None)
    chest = _room_chest(room)  # open
    chest.add_item(things.Item("key", "a brass key"))

    game.do_command("close chest")
    assert chest.get_property("is_closed") is True

    fresh = CaptureRenderer()
    game.parser.set_renderer(fresh)
    game.do_command("examine chest")
    assert "It contains" not in "\n".join(fresh.texts(Channel.NARRATION))


def test_open_non_container_is_refused():
    game, room, player, cap = _capture_game(player_capacity=None)
    _room_surface(room)  # a table can't be opened

    game.do_command("open table")

    assert "can't open the table" in (game.parser.last_fail_message or "")
