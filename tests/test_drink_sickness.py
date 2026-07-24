"""The engine Drink's sickness arc (#464): bad drinks sicken, safe water cures.

Lifted from the Penn boil-water port (#300): an ``is_contaminated`` liquid
sets ``is_sick`` on the drinker (and logs a ``sickness`` GameEvent); drinking
*boiled* water while sick clears it (and logs a ``recovery``) -- a bare safe
drink does not (aking526's #464 review: boiled-only is the one cure rule, so
the library never ships "any beverage cures dysentery"). The Penn backend
keeps its narrower *sicken* gate by subclassing the same seam (see
backend/actions.py's DrinkPenn).
"""

from text_adventure_games import games, things
from text_adventure_games.enums import Property


def drinker_game():
    """A one-room world with just the player."""
    spring = things.Location("Spring", "A clearing around a spring.")
    player = things.Character("player", "the player", "I explore.")
    return games.Game(spring, player, characters=[])


def _cup(name="cup of water", **props):
    cup = things.Item(name, f"a {name}", "Water in a tin cup.")
    cup.set_property(Property.DRINKABLE, True)
    for key, value in props.items():
        cup.set_property(key, value)
    return cup


def _events(game, kind):
    return [e for e in game.events if e.action == kind]


def test_contaminated_drink_sickens_and_logs_a_sickness_event():
    game = drinker_game()
    cup = _cup("cup of pond water")
    cup.set_property(Property.IS_CONTAMINATED, True)
    game.player.add_to_inventory(cup)
    assert game.parser.parse_command("drink cup of pond water")
    assert game.player.get_property(Property.IS_SICK) is True
    sick = _events(game, "sickness")
    assert len(sick) == 1
    assert sick[0].payload["item"] == "cup of pond water"
    assert sick[0].payload["location"] == "Spring"


def test_clean_drink_neither_sickens_nor_logs():
    game = drinker_game()
    game.player.add_to_inventory(_cup())
    assert game.parser.parse_command("drink cup of water")
    assert not game.player.get_property(Property.IS_SICK)
    assert not _events(game, "sickness")
    # Not sick, so the safe drink logs no recovery either.
    assert not _events(game, "recovery")


def test_boiled_water_cures_a_sick_drinker_and_logs_a_recovery_event():
    game = drinker_game()
    game.player.set_property(Property.IS_SICK, True)
    cup = _cup("cup of boiled water")
    cup.set_property(Property.REQUIRES_BOILING, True)
    cup.set_property(Property.IS_BOILED, True)
    game.player.add_to_inventory(cup)
    assert game.parser.parse_command("drink cup of boiled water")
    assert game.player.get_property(Property.IS_SICK) is False
    rec = _events(game, "recovery")
    assert len(rec) == 1
    assert rec[0].payload["item"] == "cup of boiled water"
    assert rec[0].payload["location"] == "Spring"


def test_a_bare_safe_drink_does_not_cure():
    # Engine mirror of Penn's pin (aking526's #464 review): only *boiled* water
    # cures. A plain drink that never needed boiling (juice, a bare cup of
    # water) does NOT clear sickness -- otherwise any beverage would cure
    # dysentery, erasing the #301 "did it learn to boil?" signal.
    game = drinker_game()
    game.player.set_property(Property.IS_SICK, True)
    game.player.add_to_inventory(_cup())  # plain water: never needed boiling
    assert game.parser.parse_command("drink cup of water")
    assert game.player.get_property(Property.IS_SICK) is True
    assert not _events(game, "recovery")


def test_raw_water_that_requires_boiling_does_not_cure():
    game = drinker_game()
    game.player.set_property(Property.IS_SICK, True)
    cup = _cup("cup of river water")
    cup.set_property(Property.REQUIRES_BOILING, True)
    game.player.add_to_inventory(cup)
    assert game.parser.parse_command("drink cup of river water")
    assert game.player.get_property(Property.IS_SICK) is True
    assert not _events(game, "recovery")


def test_a_fatal_poison_skips_the_sickness_arc():
    # A poisonous drink kills; don't also sicken (or "recover") the corpse.
    game = drinker_game()
    cup = _cup("cup of hemlock")
    cup.set_property(Property.IS_POISONOUS, True)
    cup.set_property(Property.IS_CONTAMINATED, True)
    game.player.add_to_inventory(cup)
    game.parser.parse_command("drink cup of hemlock")
    assert game.player.get_property(Property.IS_DEAD) is True
    assert not game.player.get_property(Property.IS_SICK)
    assert not _events(game, "sickness")
