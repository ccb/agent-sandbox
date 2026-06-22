"""Wearable equipment slots + layering (engine feature).

An item may declare a ``wear_slot`` (a body location); only one item occupies a
slot at a time, unless the item being put on declares ``wear_over`` (it layers
atop). ``wear_text`` gives an item its own flavor line on wearing.
"""

from text_adventure_games import games, things
from text_adventure_games.actions import equipment
from text_adventure_games.enums import Property
from text_adventure_games.reporting import CaptureRenderer, Channel


def _capture_game():
    room = things.Location("Room", "A plain room.")
    player = things.Character("you", "the player", "I dress.")
    game = games.Game(room, player, characters=[])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, player, cap


def _wearable(name, slot=None, over=False, wear_text=None):
    it = things.Item(name, f"a {name}")
    it.set_property(Property.WEARABLE, True)
    if slot:
        it.set_property("wear_slot", slot)
    if over:
        it.set_property("wear_over", True)
    if wear_text:
        it.set_property("wear_text", wear_text)
    return it


def _said(cap, sub):
    return any(
        sub in t for ch in (Channel.NARRATION, Channel.BLOCKED) for t in cap.texts(ch)
    )


def _wear(game, player, name):
    equipment.Wear(game, f"wear {name}", actor=player)()


def test_one_item_per_slot_blocks_the_second():
    game, player, cap = _capture_game()
    player.add_to_inventory(_wearable("boots", slot="feet"))
    player.add_to_inventory(_wearable("sandals", slot="feet"))
    _wear(game, player, "boots")
    assert "boots" in player.worn
    _wear(game, player, "sandals")  # same slot, not over -> refused
    assert _said(cap, "take off the boots")
    assert "sandals" not in player.worn and "boots" in player.worn


def test_taking_off_frees_the_slot():
    game, player, _ = _capture_game()
    player.add_to_inventory(_wearable("boots", slot="feet"))
    player.add_to_inventory(_wearable("sandals", slot="feet"))
    _wear(game, player, "boots")
    equipment.Take_Off(game, "take off boots", actor=player)()
    _wear(game, player, "sandals")
    assert "sandals" in player.worn and "boots" not in player.worn


def test_wear_over_layers_on_top():
    game, player, _ = _capture_game()
    player.add_to_inventory(_wearable("gown", slot="body"))
    player.add_to_inventory(_wearable("cloak", slot="body", over=True))
    _wear(game, player, "gown")
    _wear(game, player, "cloak")  # wear_over -> layers atop the gown
    assert "gown" in player.worn and "cloak" in player.worn


def test_different_slots_coexist():
    game, player, _ = _capture_game()
    player.add_to_inventory(_wearable("boots", slot="feet"))
    player.add_to_inventory(_wearable("tiara", slot="head"))
    _wear(game, player, "boots")
    _wear(game, player, "tiara")
    assert "boots" in player.worn and "tiara" in player.worn


def test_wear_text_flavor():
    game, player, cap = _capture_game()
    player.add_to_inventory(
        _wearable("boots", slot="feet", wear_text="You lace up the boots. Sturdy!")
    )
    _wear(game, player, "boots")
    assert _said(cap, "Sturdy!")


def test_unslotted_wearables_are_unaffected():
    # No wear_slot -> no exclusivity (legacy behavior): two such items coexist.
    game, player, _ = _capture_game()
    player.add_to_inventory(_wearable("ring"))
    player.add_to_inventory(_wearable("amulet"))
    _wear(game, player, "ring")
    _wear(game, player, "amulet")
    assert "ring" in player.worn and "amulet" in player.worn
