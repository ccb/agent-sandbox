"""Tests for the Godot backend's Buy/Sell commerce actions (#931).

Unlike the engine-level ``Buy``/``Sell`` scaffold in
``text_adventure_games/actions/base.py`` (see ``tests/test_commerce_scaffold.py``),
``backend.actions.Sell``/``backend.actions.Buy`` are a two-step, dibs-based
trade gated on a world-tagged "marketplace" affordance:

    1. The owner calls ``sell <item> to <buyer>``. This only stamps the item
       with ``Property.BUYER`` -- a dibs marker (mirrors
       ``CheckOutBook.checked_out_by``) -- it does not move the item or money.
    2. The named buyer then calls ``buy <item>`` to actually complete the
       trade: the item moves seller -> buyer and its ``Property.PRICE`` moves
       buyer's ``Property.MONEY`` -> seller's.

Both verbs require a "marketplace"-tagged ``Location`` (or item) in scope --
the same affordance-gate pattern ``Sleep`` uses for "sleepable".

Run with: uv run pytest tests/commerce_system_test.py -v
"""

import pytest

from backend.actions import Buy, Sell
from text_adventure_games import games, things
from text_adventure_games.enums import Property

STARTING_MONEY = 20
TEAPOT_PRICE = 10


def _teapot(price=TEAPOT_PRICE, owner="Merchant"):
    item = things.Item("teapot", "a chipped teapot", "Blue china, a little chipped.")
    item.set_property(Property.IS_FOR_SALE, True)
    item.set_property(Property.PRICE, price)
    item.set_property(Property.OWNER, owner)
    return item


@pytest.fixture
def market():
    """(game, buyer, merchant): a buyer and a merchant standing in the same
    marketplace-tagged Market, the merchant carrying one for-sale teapot.
    Fresh fixture per test, not shared."""
    market_loc = things.Location("Market", "A row of stalls under an awning.")
    market_loc.set_property("marketplace", True)
    elsewhere = things.Location("Elsewhere", "Somewhere else entirely, not a market.")
    market_loc.add_connection("out", elsewhere)

    buyer = things.Character("player", "a shopper", "I'm here to buy something.")
    buyer.set_property(Property.MONEY, STARTING_MONEY)

    merchant = things.Character("Merchant", "a market trader", "Wares for sale.")
    merchant.set_property(Property.MONEY, 0)
    merchant.add_to_inventory(_teapot())

    game = games.Game(market_loc, buyer, [merchant], [Sell, Buy])
    market_loc.add_character(merchant)
    return game, buyer, merchant


def _sell(game, merchant, item="teapot", buyer="player"):
    return game.parser.parse_command(f"sell {item} to {buyer}", actor=merchant)


def test_sell_and_buy_are_registered(market):
    game, _buyer, _merchant = market
    assert game.parser.actions["sell"] is Sell
    assert game.parser.actions["buy"] is Buy


def test_sell_stamps_dibs_without_moving_item_or_money(market):
    game, buyer, merchant = market
    assert _sell(game, merchant) is True
    teapot = merchant.carried_items()["teapot"]
    assert teapot.get_property(Property.BUYER) == buyer.name
    # Selling only offers the trade -- nothing has moved yet.
    assert "teapot" in merchant.inventory
    assert "teapot" not in buyer.inventory
    assert buyer.get_property(Property.MONEY) == STARTING_MONEY
    assert merchant.get_property(Property.MONEY) == 0


def test_sell_fails_without_the_marketplace_affordance(market):
    game, _buyer, merchant = market
    game.locations["Elsewhere"].add_character(merchant)
    assert _sell(game, merchant) is False
    assert not merchant.carried_items()["teapot"].get_property(Property.BUYER)


def test_sell_fails_when_seller_is_asleep(market):
    game, _buyer, merchant = market
    merchant.set_property(Property.IS_SLEEPING, True)
    assert _sell(game, merchant) is False
    assert not merchant.carried_items()["teapot"].get_property(Property.BUYER)


def test_sell_fails_when_seller_is_not_the_owner(market):
    game, _buyer, merchant = market
    merchant.carried_items()["teapot"].set_property(Property.OWNER, "Someone Else")
    assert _sell(game, merchant) is False
    assert not merchant.carried_items()["teapot"].get_property(Property.BUYER)


def test_sell_fails_when_item_is_not_for_sale(market):
    game, _buyer, merchant = market
    merchant.carried_items()["teapot"].set_property(Property.IS_FOR_SALE, False)
    assert _sell(game, merchant) is False
    assert not merchant.carried_items()["teapot"].get_property(Property.BUYER)


def test_sell_fails_without_a_named_buyer(market):
    game, _buyer, merchant = market
    assert game.parser.parse_command("sell teapot", actor=merchant) is False
    assert not merchant.carried_items()["teapot"].get_property(Property.BUYER)


def test_buy_fails_without_dibs(market):
    game, buyer, _merchant = market
    assert game.do_command("buy teapot") is False
    assert "teapot" not in buyer.inventory
    assert buyer.get_property(Property.MONEY) == STARTING_MONEY


def test_buy_fails_for_a_buyer_without_dibs(market):
    game, buyer, merchant = market
    rival = things.Character("Rival", "another shopper", "I also want that teapot.")
    rival.set_property(Property.MONEY, STARTING_MONEY)
    game.add_character(rival)
    game.locations["Market"].add_character(rival)

    assert _sell(game, merchant, buyer="player") is True
    assert game.parser.parse_command("buy teapot", actor=rival) is False
    assert "teapot" not in rival.inventory
    assert "teapot" not in buyer.inventory
    assert rival.get_property(Property.MONEY) == STARTING_MONEY


def test_buy_fails_when_buyer_is_asleep(market):
    game, buyer, merchant = market
    assert _sell(game, merchant) is True
    buyer.set_property(Property.IS_SLEEPING, True)
    assert game.do_command("buy teapot") is False
    assert "teapot" not in buyer.inventory


def test_buy_fails_when_money_is_insufficient(market):
    game, buyer, merchant = market
    assert _sell(game, merchant) is True
    buyer.set_property(Property.MONEY, TEAPOT_PRICE - 1)
    assert game.do_command("buy teapot") is False
    assert "teapot" not in buyer.inventory
    assert buyer.get_property(Property.MONEY) == TEAPOT_PRICE - 1


def test_buy_fails_without_the_marketplace_affordance(market):
    game, buyer, merchant = market
    assert _sell(game, merchant) is True
    game.locations["Elsewhere"].add_character(buyer)
    assert game.do_command("buy teapot") is False
    assert "teapot" not in buyer.inventory


def test_buy_fails_when_seller_walks_away_after_offering(market):
    game, buyer, merchant = market
    assert _sell(game, merchant) is True
    game.locations["Elsewhere"].add_character(merchant)
    assert game.do_command("buy teapot") is False
    assert "teapot" not in buyer.inventory


def test_buy_succeeds_and_completes_the_trade(market):
    game, buyer, merchant = market
    assert _sell(game, merchant) is True
    assert game.do_command("buy teapot") is True

    assert "teapot" in buyer.inventory
    assert "teapot" not in merchant.inventory
    assert buyer.get_property(Property.MONEY) == STARTING_MONEY - TEAPOT_PRICE
    assert merchant.get_property(Property.MONEY) == TEAPOT_PRICE
    # A sold item shouldn't stay listed, or stay claimed by a stale buyer.
    assert not buyer.inventory["teapot"].get_property(Property.IS_FOR_SALE)
    assert not buyer.inventory["teapot"].get_property(Property.BUYER)


def test_buy_matches_the_dibbed_item_even_when_a_second_seller_carries_the_same_name():
    # Regression (code review, 2026-08-13): two co-located sellers can carry
    # identically-named items (e.g. Rosa and Walt both stock "turkey
    # sandwich" at Houston Hall). _match_for_sale_item pooled same-named
    # items with a plain dict.update(), so whichever seller was iterated
    # last silently overwrote the dict entry -- even when the buyer already
    # had dibs on the OTHER seller's item.
    market_loc = things.Location("Houston Hall", "a food court")
    market_loc.set_property("marketplace", True)

    buyer = things.Character("Diego", "a hungry student", "")
    buyer.set_property(Property.MONEY, 20)

    def _sandwich(owner):
        item = things.Item("turkey sandwich", "a turkey sandwich", "On rye.")
        item.set_property(Property.IS_FOR_SALE, True)
        item.set_property(Property.PRICE, 5)
        item.set_property(Property.OWNER, owner)
        return item

    rosa = things.Character("Rosa", "a counter worker", "")
    rosa.set_property(Property.MONEY, 0)
    rosa.add_to_inventory(_sandwich("Rosa"))

    walt = things.Character("Walt", "another counter worker", "")
    walt.set_property(Property.MONEY, 0)
    walt.add_to_inventory(_sandwich("Walt"))

    game = games.Game(market_loc, buyer, [rosa, walt], [Sell, Buy])
    market_loc.add_character(rosa)
    market_loc.add_character(walt)

    assert (
        game.parser.parse_command("sell turkey sandwich to Diego", actor=rosa) is True
    )
    assert game.do_command("buy turkey sandwich") is True

    assert "turkey sandwich" in buyer.inventory
    assert "turkey sandwich" in walt.inventory  # Walt's own stock is untouched
    assert rosa.get_property(Property.MONEY) == 5  # Rosa was paid
    assert walt.get_property(Property.MONEY) == 0  # not Walt
