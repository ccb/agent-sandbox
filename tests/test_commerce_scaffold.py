"""TDD scaffold (#932): Buy/Sell, a minimal money/commerce system.

Money is a plain numerical property (``Property.MONEY``) any character can
carry. An item becomes purchasable once it carries ``Property.IS_FOR_SALE``,
a ``Property.PRICE``, and a ``Property.OWNER`` naming who's authorized to
sell it -- NOT the same thing as the engine's ``item.owner`` attribute (see
the comment on ``Property.OWNER`` in ``enums.py``). ``Buy`` (buyer-initiated)
and ``Sell`` (owner-initiated) are the two verbs for the same trade; both
live in ``text_adventure_games/actions/base.py``, right next to the engine's
other universal actions, and ``Sell`` is meant to mirror ``Give``'s
location/capacity-check pattern (``actions/things.py``) rather than
reinvent it.

A purchase needs ALL of:
    1. The item is actually ``Property.IS_FOR_SALE``.
    2. The buyer's ``Property.MONEY`` covers the item's ``Property.PRICE``.
    3. The buyer is not asleep (``Property.IS_SLEEPING``).
    4. The buyer and the seller (named by the item's ``Property.OWNER``) are
       at the same ``Location``.
    5. The seller ``Property.OWNER`` names is a real, present character.

``Buy.check_preconditions``/``Buy.apply_effects`` (and ``Sell``'s) currently
``raise NotImplementedError`` -- that's the TODO. Each test below should go
from an error to a clean pass once you fill them in; none of the assertions
here should need to change.

Run with: uv run pytest tests/test_commerce_scaffold.py -v
"""

import pytest

from text_adventure_games import games, things
from text_adventure_games.actions.base import Buy, Sell
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
    Market, the merchant carrying one for-sale teapot. Each test starts from
    this same clean state -- a fresh fixture call per test, not shared."""
    market_loc = things.Location("Market", "A row of stalls under an awning.")
    elsewhere = things.Location("Elsewhere", "Somewhere else entirely.")
    market_loc.add_connection("out", elsewhere)

    buyer = things.Character("player", "a shopper", "I'm here to buy something.")
    buyer.set_property(Property.MONEY, STARTING_MONEY)

    merchant = things.Character("Merchant", "a market trader", "Wares for sale.")
    merchant.set_property(Property.MONEY, 0)
    merchant.add_to_inventory(_teapot())

    game = games.Game(market_loc, buyer, [merchant], [Buy, Sell])
    market_loc.add_character(merchant)
    return game, buyer, merchant


def test_buy_and_sell_are_registered(market):
    game, _buyer, _merchant = market
    assert game.parser.actions["buy"] is Buy
    assert game.parser.actions["sell"] is Sell


def test_buy_fails_when_item_is_not_for_sale(market):
    game, buyer, merchant = market
    merchant.carried_items()["teapot"].set_property(Property.IS_FOR_SALE, False)
    assert game.do_command("buy teapot") is False
    assert "teapot" not in buyer.inventory


def test_buy_fails_when_money_is_insufficient(market):
    game, buyer, _merchant = market
    buyer.set_property(Property.MONEY, TEAPOT_PRICE - 1)
    assert game.do_command("buy teapot") is False
    assert "teapot" not in buyer.inventory
    assert buyer.get_property(Property.MONEY) == TEAPOT_PRICE - 1


def test_buy_fails_when_buyer_is_asleep(market):
    game, buyer, _merchant = market
    buyer.set_property(Property.IS_SLEEPING, True)
    assert game.do_command("buy teapot") is False
    assert "teapot" not in buyer.inventory


def test_buy_fails_when_locations_dont_match(market):
    game, buyer, merchant = market
    game.locations["Elsewhere"].add_character(merchant)  # merchant walks off
    assert game.do_command("buy teapot") is False
    assert "teapot" not in buyer.inventory


def test_buy_fails_without_a_present_owner(market):
    game, buyer, merchant = market
    merchant.carried_items()["teapot"].set_property(Property.OWNER, "Nobody")
    assert game.do_command("buy teapot") is False
    assert "teapot" not in buyer.inventory


def test_buy_succeeds_and_transfers_money_and_item(market):
    game, buyer, merchant = market
    assert game.do_command("buy teapot") is True
    assert "teapot" in buyer.inventory
    assert "teapot" not in merchant.inventory
    assert buyer.get_property(Property.MONEY) == STARTING_MONEY - TEAPOT_PRICE
    assert merchant.get_property(Property.MONEY) == TEAPOT_PRICE
    # A sold item shouldn't stay listed, or stay claimed by a stale buyer.
    assert not buyer.inventory["teapot"].get_property(Property.IS_FOR_SALE)
    assert not buyer.inventory["teapot"].get_property(Property.BUYER)


def test_sell_is_the_owners_side_of_the_same_trade(market):
    game, buyer, merchant = market
    assert game.parser.parse_command("sell teapot to player", actor=merchant) is True
    assert "teapot" in buyer.inventory
    assert buyer.get_property(Property.MONEY) == STARTING_MONEY - TEAPOT_PRICE
    assert merchant.get_property(Property.MONEY) == TEAPOT_PRICE
