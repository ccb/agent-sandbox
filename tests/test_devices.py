"""Engine Activate/Deactivate (#464): switch a fixed device on and off.

Lifted from the Penn backend's boil-water verbs (#300). These tests pin the
engine copies: the device gate and ``is_on`` toggle, the fixture-need-not-be-
held behavior, the #612 affordance curation, and the parser routing -- both
that "activate stove" survives the old "ate " misroute (#536) and that the
alias split leaves "turn off" with Douse (fire) while Deactivate owns
"switch off" (devices).
"""

from text_adventure_games import games, things
from text_adventure_games.actions.base import offered_action_names
from text_adventure_games.enums import ActionName, Property


def device_game():
    """A one-room kitchen with the player and a stove fixture (a device)."""
    kitchen = things.Location("Kitchen", "A small kitchen.")
    player = things.Character("player", "the player", "I explore.")
    game = games.Game(kitchen, player, characters=[])
    stove = things.Item("stove", "a camp stove", "A one-burner camp stove.")
    stove.set_property(Property.IS_DEVICE, True)
    kitchen.add_item(stove)
    return game, stove


def test_activate_and_deactivate_toggle_a_device():
    game, stove = device_game()
    # The stove sits in the room, not in the player's inventory -- a device is
    # a fixture, so being in scope is enough (no "you don't have it" gate).
    assert game.parser.parse_command("activate stove")
    assert stove.get_property(Property.IS_ON) is True
    assert game.parser.parse_command("deactivate stove")
    assert stove.get_property(Property.IS_ON) is False


def test_activate_when_already_on_fails_at_the_gate():
    game, stove = device_game()
    assert game.parser.parse_command("activate stove")
    assert not game.parser.parse_command("activate stove")
    assert stove.get_property(Property.IS_ON) is True


def test_deactivate_when_already_off_fails_at_the_gate():
    game, stove = device_game()
    assert not game.parser.parse_command("deactivate stove")
    assert stove.get_property(Property.IS_ON) is False


def test_activate_rejects_a_non_device():
    game, _ = device_game()
    pot = things.Item("pot", "a cooking pot", "An empty steel pot.")
    game.locations["Kitchen"].add_item(pot)
    assert not game.parser.parse_command("activate pot")
    assert not pot.get_property(Property.IS_ON)


def test_device_verbs_are_curated_by_the_affordance():
    # Offered exactly where a device is in scope (#612): the kitchen's stove
    # affords both verbs; a bare field affords neither.
    game, _ = device_game()
    offered = offered_action_names(game.parser, game.player)
    assert ActionName.ACTIVATE in offered
    assert ActionName.DEACTIVATE in offered

    field = things.Location("Field", "An open grassy field.")
    walker = things.Character("player", "the player", "I explore.")
    bare = games.Game(field, walker, characters=[])
    offered = offered_action_names(bare.parser, bare.player)
    assert ActionName.ACTIVATE not in offered
    assert ActionName.DEACTIVATE not in offered


def test_activate_routes_past_the_old_ate_misroute():
    # "activate" contains the letters "ate": before #536's word-boundary
    # matching this misrouted to EAT (the reason PennParser existed).
    game, _ = device_game()
    assert game.parser.determine_intent("activate stove") == ActionName.ACTIVATE
    assert game.parser.determine_intent("deactivate stove") == ActionName.DEACTIVATE


def test_alias_split_douse_keeps_turn_off_deactivate_owns_switch_off():
    # The #464 alias resolution: "turn off"/"turn on" stay with Douse/Light
    # (fire, the pre-existing phrasing), while the device pair owns
    # "switch off"/"switch on".
    game, _ = device_game()
    assert game.parser.determine_intent("switch on stove") == ActionName.ACTIVATE
    assert game.parser.determine_intent("switch off stove") == ActionName.DEACTIVATE
    assert game.parser.determine_intent("turn on lamp") == ActionName.LIGHT
    assert game.parser.determine_intent("turn off lamp") == ActionName.DOUSE
