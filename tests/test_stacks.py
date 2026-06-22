"""Opt-in item stacks / quantities (#134).

A stackable item represents N identical units in one holder entry; same-named
stackable items merge on add. Default (non-stackable) items are unaffected --
they never merge and never show a count.
"""

from text_adventure_games import games, things, Recipe, Ingredient
from text_adventure_games.actions import things as thing_actions
from text_adventure_games.reporting import CaptureRenderer, Channel


def _stick(n=1):
    return things.Item("stick", "a wooden stick").make_stackable(n)


def _capture_game():
    room = things.Location("Room", "A plain room.")
    player = things.Character("you", "the player", "I explore.")
    game = games.Game(room, player, characters=[])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, room, player, cap


def _said(cap, sub):
    return any(
        sub in t for ch in (Channel.NARRATION, Channel.BLOCKED) for t in cap.texts(ch)
    )


# --- the model -------------------------------------------------------------


def test_stackable_items_merge_in_inventory():
    _, _, player, _ = _capture_game()
    player.add_to_inventory(_stick(1))
    player.add_to_inventory(_stick(2))
    assert list(player.inventory) == ["stick"]  # one entry
    assert player.inventory["stick"].quantity == 3


def test_stackable_items_merge_in_a_container():
    pack = things.Item("backpack", "a pack").make_container()
    pack.add_item(_stick(2))
    pack.add_item(_stick(1))
    assert pack.contents["stick"].quantity == 3
    assert pack.current_count() == 1  # a stack is one slot


def test_stackable_items_merge_in_a_location():
    room = things.Location("Room", "A room.")
    room.add_item(_stick(2))
    room.add_item(_stick(5))
    assert room.items["stick"].quantity == 7


def test_non_stackable_items_do_not_merge():
    _, _, player, _ = _capture_game()
    # Two same-named NON-stackable items: the engine keys by name, so the second
    # replaces the first (existing behavior) -- they do not merge into a stack.
    player.add_to_inventory(things.Item("lamp", "a lamp"))
    assert player.inventory["lamp"].quantity == 1
    player.add_to_inventory(things.Item("lamp", "a lamp"))
    assert player.inventory["lamp"].quantity == 1  # still 1, no stacking


def test_get_a_stack_from_the_room_merges_into_a_held_stack():
    game, room, player, _ = _capture_game()
    player.add_to_inventory(_stick(1))
    room.add_item(_stick(2))
    thing_actions.Get(game, "get stick", actor=player)()
    assert "stick" not in room.items
    assert player.inventory["stick"].quantity == 3


def test_quantity_round_trips_through_primitive():
    s = _stick(4)
    again = things.Item.from_primitive(s.to_primitive())
    assert again.quantity == 4 and again.is_stackable()
    # a plain item defaults to quantity 1 (and old saves with no field, too)
    plain = things.Item.from_primitive(things.Item("rock", "a rock").to_primitive())
    assert plain.quantity == 1


def test_inventory_shows_a_stack_count():
    game, _, player, cap = _capture_game()
    player.add_to_inventory(_stick(3))
    thing_actions.Inventory(game, "inventory", actor=player)()
    assert _said(cap, "(x3)")


# --- crafting with count>1 (the #134 motivation) ---------------------------


def test_recipe_requires_two_of_a_stacked_named_ingredient():
    room = things.Location("Shop", "A shop.")
    player = things.Character("you", "the player", "I craft.")
    game = games.Game(room, player, characters=[])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.add_recipe(
        Recipe(
            name="raft",
            inputs=[Ingredient(name="stick", count=2)],
            output=lambda g: things.Item("raft", "a flimsy raft"),
        )
    )
    # one stick: not enough
    player.add_to_inventory(_stick(1))
    game.do_command("make raft")
    assert "raft" not in player.inventory
    assert any("need" in t for t in cap.texts(Channel.BLOCKED))
    # top up to two: now it crafts and consumes both
    player.add_to_inventory(_stick(1))
    assert player.inventory["stick"].quantity == 2
    game.do_command("make raft")
    assert "raft" in player.inventory
    assert "stick" not in player.inventory  # both units consumed
