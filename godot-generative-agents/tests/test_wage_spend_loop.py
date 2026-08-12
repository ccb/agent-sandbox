"""Integration test for the wage -> spend loop (#931 follow-up): a job
persona earns money on an authored work stop (backend.drives.accrue_wage),
then spends it on food at the Houston Hall sandwich shop
(backend.actions.Sell/Buy) and eats it (backend.actions.EatPenn), restoring
Property.ENERGY. Nothing else in the suite crosses wage and commerce --
test_wage_drive.py only tests accrual conditions in isolation on a bare
Character with a fake schedule, and test_sandwich_shop.py never sets
wage_rate at all.

Debra starts broke (Property.MONEY == 0) and already hungry
(Property.ENERGY below the low-energy threshold), and her wage_rate is
hand-set to exactly SANDWICH_PRICE so a single accrue_wage() call funds
the whole purchase -- no multi-tick simulation needed to keep this test
concise and deterministic.

Run with: uv run pytest godot-generative-agents/tests/test_wage_spend_loop.py -v
"""

from types import SimpleNamespace

from backend.drives import accrue_wage
from backend.penn.penn_world import SANDWICH_PRICE, build_penn_world
from text_adventure_games.enums import Property


def _live_world(cast):
    """(game, characters) for the real Penn world, built with just `cast`."""
    world = build_penn_world(cast=cast)
    return world.build_world_fn(world.world_map)


def test_persona_earns_a_wage_then_spends_it_on_food_and_eats():
    game, characters = _live_world(["rosa", "debra"])
    rosa = characters["Rosa Delgado"]
    debra = characters["Debra Hollis"]

    # Debra starts broke and already hungry -- the loop must go from "no
    # money, needs food now" all the way to "ate, no longer hungry."
    debra.set_property(Property.MONEY, 0)
    debra.set_property(Property.ENERGY, 10)  # below the 20 low-energy threshold
    debra.set_property("is_low_energy", True)

    # Earn: stand her on her authored work stop (College Hall) with a wage
    # exactly equal to one sandwich's price, so a single accrue_wage() call
    # funds the whole purchase.
    debra.set_property("wage_rate", SANDWICH_PRICE)
    game.locations["College Hall"].add_character(debra)
    debra.set_property("activity", "grading")
    debra.agent = SimpleNamespace(
        schedule=SimpleNamespace(
            _stop={"place": "College Hall", "activity": "grading", "is_work": True}
        )
    )
    accrue_wage(debra)
    assert debra.get_property(Property.MONEY) == SANDWICH_PRICE

    # Spend: walk to the Houston Hall counter and buy a sandwich from Rosa.
    game.locations["Houston Hall"].add_character(debra)
    game.locations["Houston Hall"].add_character(rosa)
    assert game.parser.parse_command("sell turkey sandwich to Debra Hollis", actor=rosa)
    assert game.parser.parse_command("buy turkey sandwich", actor=debra)
    assert debra.get_property(Property.MONEY) == 0
    assert "turkey sandwich" in debra.inventory

    # Eat: the sandwich's energy_value (20) clears the hunger she started with.
    assert game.parser.parse_command("eat turkey sandwich", actor=debra)
    assert debra.get_property(Property.ENERGY) == 30
    assert not debra.get_property("is_low_energy")
