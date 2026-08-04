"""Save/load round-trips blocks (issue #744).

Game.from_primitive used to leave each location's blocks as the raw primitive
dicts, so a loaded game crashed with AttributeError the first time anything
checked a formerly-blocked direction. These tests pin the fix: blocks come
back as real Block instances, still block movement, unblock when their
condition is met, and keep any state that changed before the save.
"""

import pytest

from text_adventure_games import blocks, games, things
from text_adventure_games.enums import Property


def _restore(game):
    """Round-trip a game through the JSON save path, like a real save file."""
    return games.Game.from_json(game.to_json(), custom_actions=game.custom_actions)


# --- engine Locked_Door: shared blocks and constructor side effects ----------


def _door_game():
    """A hall and a vault joined by an (engine) Locked_Door."""
    hall = things.Location("Hall", "A hall.")
    vault = things.Location("Vault", "A vault.")
    hall.add_connection("north", vault)
    door = things.Item("door", "a heavy door", "A HEAVY DOOR.")
    blocks.Locked_Door(hall, door, vault)
    player = things.Character("player", "the player", "I test doors.")
    return games.Game(hall, player), door


def test_locked_door_round_trips_as_one_shared_instance():
    game, _door = _door_game()
    restored = games.Game.from_json(game.to_json())

    hall_block = restored.locations["Hall"].blocks["north"]
    vault_block = restored.locations["Vault"].blocks["south"]
    assert isinstance(hall_block, blocks.Locked_Door)
    # Locked_Door installs itself on both sides; the loader must not build two.
    assert hall_block is vault_block
    # The block guards the same door item that sits in the room.
    assert hall_block.door is restored.locations["Hall"].items["door"]
    assert restored.locations["Hall"].is_blocked("north")


def test_unlocking_before_the_save_is_not_undone_by_the_load():
    # Locked_Door.__init__ re-locks its door. The loader snapshots and
    # restores thing properties around block construction, so a door
    # unlocked before the save must still be unlocked after the load.
    game, door = _door_game()
    door.set_property(Property.IS_LOCKED, False)

    restored = games.Game.from_json(game.to_json())
    assert not restored.locations["Hall"].items["door"].get_property(Property.IS_LOCKED)
    assert not restored.locations["Hall"].is_blocked("north")


# --- loader edge cases --------------------------------------------------------


def _first_block_prim(data):
    for loc in data["locations"]:
        for prim in loc["blocks"].values():
            return prim
    raise AssertionError("no blocks in primitive data")


def test_unmapped_block_type_raises_a_clear_error():
    game, _door = _door_game()
    data = game.to_primitive()
    for loc in data["locations"]:
        for prim in loc["blocks"].values():
            prim["_type"] = "Vanished_Block"  # a class the loader can't find
            prim.pop("_module", None)
    with pytest.raises(Exception, match="unmapped block"):
        games.Game.from_primitive(data)


def test_old_save_without_module_still_loads_engine_blocks():
    # Saves written before #744 recorded no _module; engine blocks still
    # resolve through the default block map.
    game, _door = _door_game()
    data = game.to_primitive()
    for loc in data["locations"]:
        for prim in loc["blocks"].values():
            prim.pop("_module", None)
    restored = games.Game.from_primitive(data)
    assert isinstance(restored.locations["Hall"].blocks["north"], blocks.Locked_Door)


def test_loading_leaves_the_callers_block_prims_intact():
    # The block loop works on copies, so the caller's primitive data still
    # holds serializable dicts (not Block instances) after a load.
    game, _door = _door_game()
    data = game.to_primitive()
    games.Game.from_primitive(data)
    prim = _first_block_prim(data)
    assert isinstance(prim, dict)
    assert prim["_type"] == "Locked_Door"
