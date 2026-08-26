"""Tests for the Houston Hall sandwich shop (#931): worker/customer commerce
in the live Penn world, built on top of the engine's Sell/Buy trade
(backend.actions) and Property.MONEY/PRICE/OWNER/IS_FOR_SALE/BUYER.

Two personas -- `rosa` (Rosa Delgado) and `walt` (Walt Higgins), both
Houston Hall dining staff in the library, `godot-generative-agents/backend/
penn/personas/` -- are opted into selling via `penn_world._furnish_sandwich_shop`
(a `sells_sandwiches` marker + a starting stock carried in their own
inventory). Neither is in the default 3-person cast (see `personas/README.md`),
so every test here builds an explicit `cast=` including at least one worker,
mirroring `test_sleep_action.py`'s live-world wiring checks.

Run with: uv run pytest godot-generative-agents/tests/test_sandwich_shop.py -v
"""

from backend.penn.penn_world import (
    DEFAULT_STARTING_MONEY,
    SANDWICH_PRICE,
    SANDWICH_VARIETIES,
    _furnish_starting_money,
    build_penn_world,
    restock_sandwiches,
)
from text_adventure_games.enums import Property


def _live_world(cast):
    """(game, characters) for the real Penn world, built with just `cast`."""
    world = build_penn_world(cast=cast)
    return world.build_world_fn(world.world_map)


def test_houston_hall_is_a_marketplace_and_sell_buy_are_registered():
    game, _characters = _live_world(["diego"])
    hall = game.locations["Houston Hall"]
    assert hall.get_property("marketplace")
    assert "sell" in game.parser.actions
    assert "buy" in game.parser.actions


def test_worker_starts_with_carried_for_sale_stock():
    _game, characters = _live_world(["rosa"])
    rosa = characters["Rosa Delgado"]
    assert rosa.get_property("sells_sandwiches")
    carried = rosa.carried_items()
    for variety_name, _description, _examine in SANDWICH_VARIETIES:
        item = carried[variety_name]
        assert item.get_property(Property.IS_FOR_SALE)
        assert item.get_property(Property.PRICE) == SANDWICH_PRICE
        assert item.get_property(Property.OWNER) == "Rosa Delgado"


def test_worker_sells_and_customer_buys_a_sandwich_end_to_end():
    game, characters = _live_world(["rosa", "diego"])
    rosa = characters["Rosa Delgado"]
    diego = characters["Diego Torres"]
    # Diego's authored schedule never visits Houston Hall -- put the customer
    # at the counter directly, the same way commerce_system_test.py's fixture
    # co-locates a buyer and merchant.
    game.locations["Houston Hall"].add_character(diego)
    game.locations["Houston Hall"].add_character(rosa)

    starting_diego_money = diego.get_property(Property.MONEY)
    starting_rosa_money = rosa.get_property(Property.MONEY)

    assert (
        game.parser.parse_command("sell turkey sandwich to Diego Torres", actor=rosa)
        is True
    )
    assert game.parser.parse_command("buy turkey sandwich", actor=diego) is True

    assert "turkey sandwich" in diego.inventory
    assert "turkey sandwich" not in rosa.carried_items()
    assert diego.get_property(Property.MONEY) == starting_diego_money - SANDWICH_PRICE
    assert rosa.get_property(Property.MONEY) == starting_rosa_money + SANDWICH_PRICE
    assert not diego.inventory["turkey sandwich"].get_property(Property.IS_FOR_SALE)
    assert not diego.inventory["turkey sandwich"].get_property(Property.BUYER)


def test_restock_tops_up_a_depleted_worker_at_the_counter():
    game, characters = _live_world(["rosa"])
    rosa = characters["Rosa Delgado"]
    game.locations["Houston Hall"].add_character(rosa)  # at the counter

    sold = rosa.carried_items()["turkey sandwich"]
    rosa.discard_item(sold)
    assert "turkey sandwich" not in rosa.carried_items()

    restock_sandwiches(rosa)

    restocked = rosa.carried_items()["turkey sandwich"]
    assert restocked.get_property(Property.IS_FOR_SALE)
    assert restocked.get_property(Property.OWNER) == "Rosa Delgado"


def test_restock_is_a_noop_off_shift_or_not_opted_in():
    game, characters = _live_world(["rosa", "diego"])
    rosa = characters["Rosa Delgado"]
    diego = characters["Diego Torres"]

    # Off the marketplace-tagged counter (still Rosa's home tile, "Penn campus").
    sold = rosa.carried_items()["turkey sandwich"]
    rosa.discard_item(sold)
    restock_sandwiches(rosa)
    assert "turkey sandwich" not in rosa.carried_items()

    # Not opted in at all, even standing at the counter.
    game.locations["Houston Hall"].add_character(diego)
    restock_sandwiches(diego)
    assert "turkey sandwich" not in diego.carried_items()


def test_default_starting_money_is_seeded_but_never_overwrites():
    game, characters = _live_world(["diego"])
    diego = characters["Diego Torres"]
    assert diego.get_property(Property.MONEY) == DEFAULT_STARTING_MONEY

    diego.set_property(Property.MONEY, 999)
    _furnish_starting_money(game)  # re-running must not clobber an existing value
    assert diego.get_property(Property.MONEY) == 999
