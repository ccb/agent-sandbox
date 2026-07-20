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
    from text_adventure_games.adventures.action_castle import Wear_Crown

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


def test_describe_for_omits_sick_line_when_healthy_634():
    # Byte-identical for games that never sicken a character: no is_sick, no line.
    game = _one_char_game()
    assert "You feel ill." not in game.describe_for(game.player)


def test_describe_for_shows_and_hides_self_sick_line_634():
    game = _one_char_game()
    game.player.set_property("is_sick", True)
    assert "You feel ill." in game.describe_for(game.player)
    # Authorable wording overrides the neutral default.
    game.player.set_property("sick_self_description", "Your stomach is cramping.")
    obs = game.describe_for(game.player)
    assert "Your stomach is cramping." in obs
    assert "You feel ill." not in obs
    # Recovery: the line simply disappears once is_sick clears.
    game.player.set_property("is_sick", False)
    assert "cramping" not in game.describe_for(game.player)


def test_visible_description_shows_sickness_to_a_bystander_634():
    room = things.Location("Room", "A plain room.")
    player = things.Character("player", "the player", "I explore.")
    other = things.Character("Nadia", "a student", "I study.")
    game = games.Game(room, player, characters=[other])
    room.add_character(other)
    other.set_property("is_sick", True)
    obs = game.describe_for(player)
    assert "Nadia - Nadia, looking ill" in obs
    # Authorable, and dead/unconscious still take priority over sick.
    other.set_property("sick_description", "Nadia, pale and sweating")
    assert "Nadia, pale and sweating" in game.describe_for(player)
    other.set_property("is_dead", True)
    assert "looking ill" not in game.describe_for(player)
    assert "pale and sweating" not in game.describe_for(player)


def test_describe_for_omits_affordance_brackets_for_plain_scenery():
    game = _one_char_game()
    statue = things.Item("statue", "a marble statue")
    statue.set_property(Property.GETTABLE, False)
    game.player.location.add_item(statue)

    obs = game.describe_for(game.player)
    # Statue line should have no brackets at all.
    [line] = [l for l in obs.splitlines() if "statue" in l]
    assert "[" not in line


# ----------------------------------------------------------------------
# Inventory listing: carried, then worn, then wielded
# ----------------------------------------------------------------------


def _inventory_text(game):
    from text_adventure_games.reporting import CaptureRenderer, Channel

    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.parser.parse_command("inventory")
    return cap.texts(Channel.NARRATION)[-1]


def test_inventory_lists_carried_then_worn_then_wielded():
    game = _one_char_game()
    p = game.player
    for it, wearable, wieldable in [
        (things.Item("ring", "a plain ring"), False, False),
        (things.Item("cloak", "a wool cloak"), True, False),
        (things.Item("sword", "a short sword"), False, True),
    ]:
        if wearable:
            it.set_property(Property.WEARABLE, True)
        if wieldable:
            it.set_property(Property.WIELDABLE, True)
        p.add_to_inventory(it)
    p.wear(p.inventory["cloak"])
    p.wield(p.inventory["sword"])

    text = _inventory_text(game)
    assert "inventory contains:" in text and "a plain ring" in text
    assert "Wearing:" in text and "a wool cloak" in text
    assert "Wielding:" in text and "a short sword" in text
    # Order: carried section, then Wearing, then Wielding.
    assert text.index("contains:") < text.index("Wearing:") < text.index("Wielding:")
    # The cloak/sword moved out of inventory, so they don't double-list there.
    assert text.index("Wearing:") < text.index("a wool cloak")


def test_inventory_shows_worn_even_with_empty_hands():
    game = _one_char_game()
    cloak = things.Item("cloak", "a wool cloak")
    cloak.set_property(Property.WEARABLE, True)
    game.player.add_to_inventory(cloak)
    game.player.wear(cloak)

    text = _inventory_text(game)
    assert "is empty." in text  # nothing in hand
    assert "Wearing:" in text and "a wool cloak" in text


def test_inventory_truly_empty():
    game = _one_char_game()
    text = _inventory_text(game)
    assert "is empty." in text
    assert "Wearing:" not in text and "Wielding:" not in text
