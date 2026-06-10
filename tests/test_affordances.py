"""Tests for affordance tags, worn/wielded slots, and equipment actions."""

import pytest

from text_adventure_games import games, things
from text_adventure_games.enums import Property


def _one_char_game():
    """A bare room with the player; tests add items as needed."""
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    game = games.Game(room, player, characters=[])
    return game


# ----------------------------------------------------------------------
# Round-trip serialization for the new slots
# ----------------------------------------------------------------------


def test_character_round_trips_worn_and_wielded():
    game = _one_char_game()
    player = game.player

    held = things.Item("ring", "a plain ring")
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)

    player.add_to_inventory(held)
    player.add_to_inventory(cloak)
    player.wear(cloak)
    player.add_to_inventory(sword)
    player.wield(sword)

    restored = things.Character.from_primitive(player.to_primitive())

    assert set(restored.inventory) == {"ring"}
    assert set(restored.worn) == {"cloak"}
    assert set(restored.wielded) == {"sword"}


def test_from_primitive_tolerates_old_data_without_slots():
    """Fixtures saved before the slots existed should still load."""
    legacy = {
        "name": "ghost",
        "description": "a spectre",
        "persona": "I haunt.",
        "inventory": {},
        "properties": {},
        "commands": [],
    }
    restored = things.Character.from_primitive(legacy)
    assert restored.worn == {}
    assert restored.wielded == {}


# ----------------------------------------------------------------------
# Wear / Take_Off
# ----------------------------------------------------------------------


def test_wear_moves_item_from_inventory_to_worn():
    game = _one_char_game()
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    game.player.add_to_inventory(cloak)

    assert game.parser.parse_command("wear cloak")
    assert "cloak" not in game.player.inventory
    assert "cloak" in game.player.worn


def test_wear_rejects_non_wearable_item():
    game = _one_char_game()
    rock = things.Item("rock", "a heavy rock")
    game.player.add_to_inventory(rock)

    assert not game.parser.parse_command("wear rock")
    assert "rock" in game.player.inventory
    assert "rock" not in game.player.worn


def test_take_off_returns_item_to_inventory():
    game = _one_char_game()
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    game.player.add_to_inventory(cloak)
    game.player.wear(cloak)

    assert game.parser.parse_command("take off cloak")
    assert "cloak" in game.player.inventory
    assert "cloak" not in game.player.worn


# ----------------------------------------------------------------------
# Wield / Unwield
# ----------------------------------------------------------------------


def test_wield_moves_item_from_inventory_to_wielded():
    game = _one_char_game()
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)
    game.player.add_to_inventory(sword)

    assert game.parser.parse_command("wield sword")
    assert "sword" not in game.player.inventory
    assert "sword" in game.player.wielded


def test_unwield_returns_item_to_inventory():
    game = _one_char_game()
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)
    game.player.add_to_inventory(sword)
    game.player.wield(sword)

    assert game.parser.parse_command("unwield sword")
    assert "sword" in game.player.inventory
    assert "sword" not in game.player.wielded


# ----------------------------------------------------------------------
# Drop / Give reject equipped items
# ----------------------------------------------------------------------


def test_drop_fails_on_worn_item_then_succeeds_after_take_off():
    game = _one_char_game()
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    game.player.add_to_inventory(cloak)
    game.player.wear(cloak)

    assert not game.parser.parse_command("drop cloak")
    assert "cloak" in game.player.worn

    assert game.parser.parse_command("take off cloak")
    assert game.parser.parse_command("drop cloak")
    assert "cloak" not in game.player.inventory
    assert "cloak" in game.player.location.items


def test_drop_fails_on_wielded_item():
    game = _one_char_game()
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)
    game.player.add_to_inventory(sword)
    game.player.wield(sword)

    assert not game.parser.parse_command("drop sword")
    assert "sword" in game.player.wielded


def test_give_fails_on_worn_item():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    guard = things.Character("guard", "a guard", "I patrol.")
    game = games.Game(room, player, characters=[guard])
    room.add_character(guard)

    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    player.add_to_inventory(cloak)
    player.wear(cloak)

    assert not game.parser.parse_command("give cloak to guard")
    assert "cloak" in player.worn
    assert "cloak" not in guard.inventory


# ----------------------------------------------------------------------
# Wear_Crown composition (bundled Action Castle game)
# ----------------------------------------------------------------------


def test_wear_crown_requires_royalty_and_crowns_on_success():
    from notebooks.hw1_solution.action_castle import Wear_Crown

    game = _one_char_game()
    crown = things.Item("crown", "a golden crown")
    crown.set_property(Property.WEARABLE, True)
    game.player.add_to_inventory(crown)
    game.parser.add_action(Wear_Crown)

    # Not royal -> generic Wear's slot move is gated; crown stays in inventory.
    assert not game.parser.parse_command("wear crown")
    assert game.player.get_property("is_crowned") is False
    assert "crown" in game.player.inventory

    # Make royal -> Wear_Crown succeeds; crown moves into `worn` and the
    # character is crowned.
    game.player.set_property("is_royal", True)
    assert game.parser.parse_command("wear crown")
    assert game.player.get_property("is_crowned") is True
    assert "crown" in game.player.worn
    assert "crown" not in game.player.inventory


# ----------------------------------------------------------------------
# Observation surface
# ----------------------------------------------------------------------


def test_describe_for_lists_affordance_tags_on_items():
    game = _one_char_game()
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)
    game.player.add_to_inventory(sword)

    obs = game.describe_for(game.player)
    assert "[wieldable, gettable]" in obs or "[gettable, wieldable]" in obs


def test_describe_for_shows_worn_and_wielded_sections():
    game = _one_char_game()
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    sword = things.Item("sword", "a short sword")
    sword.set_property(Property.WIELDABLE, True)
    game.player.add_to_inventory(cloak)
    game.player.add_to_inventory(sword)
    game.player.wear(cloak)
    game.player.wield(sword)

    obs = game.describe_for(game.player)
    assert "Worn: cloak" in obs
    assert "Wielded: sword" in obs


def test_describe_for_omits_affordance_brackets_for_plain_scenery():
    game = _one_char_game()
    statue = things.Item("statue", "a marble statue")
    statue.set_property(Property.GETTABLE, False)
    game.player.location.add_item(statue)

    obs = game.describe_for(game.player)
    # Statue line should have no brackets at all.
    [line] = [l for l in obs.splitlines() if "statue" in l]
    assert "[" not in line
