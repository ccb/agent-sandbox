"""Save/load round-trips blocks (issue #744).

Game.from_primitive used to leave each location's blocks as the raw primitive
dicts, so a loaded game crashed with AttributeError the first time anything
checked a formerly-blocked direction. These tests pin the fix: blocks come
back as real Block instances, still block movement, unblock when their
condition is met, and keep any state that changed before the save.
"""

import pytest

from text_adventure_games import blocks, games, things
from text_adventure_games.adventures import action_castle
from text_adventure_games.enums import Property
from text_adventure_games.reporting import CaptureRenderer, Channel


def _restore(game):
    """Round-trip a game through the JSON save path, like a real save file."""
    return games.Game.from_json(game.to_json(), custom_actions=game.custom_actions)


def _blocked_map(game):
    """{location: {direction: is_blocked}} for every location with blocks."""
    return {
        loc.name: {d: loc.is_blocked(d) for d in loc.blocks}
        for loc in game.locations.values()
        if loc.blocks
    }


def _teleport(character, location):
    """Drop a character at a location directly (tests skip the long walk)."""
    character.location.remove_character(character)
    location.add_character(character)


# --- the issue's crash repro -------------------------------------------------


def test_issue_744_repro_blocks_survive_from_json():
    # Action Castle -> to_json -> from_json -> is_blocked() used to raise
    # AttributeError: 'dict' object has no attribute 'is_blocked'.
    game = action_castle.build_game()
    before = _blocked_map(game)
    assert before  # sanity: Action Castle really ships with blocks

    restored = _restore(game)
    for loc in restored.locations.values():
        for block in loc.blocks.values():
            assert isinstance(block, blocks.Block)
    assert _blocked_map(restored) == before


def test_loaded_block_still_blocks_movement_and_narrates():
    restored = _restore(action_castle.build_game())
    cap = CaptureRenderer()
    restored.parser.set_renderer(cap)

    player = restored.player
    drawbridge = restored.locations["Drawbridge"]
    _teleport(player, drawbridge)

    restored.do_command("go east")
    assert player.location is drawbridge  # the troll still stops the player
    assert any("troll" in t.lower() for t in cap.texts(Channel.BLOCKED))


def test_loaded_block_unblocks_when_condition_met():
    restored = _restore(action_castle.build_game())
    restored.parser.set_renderer(CaptureRenderer())

    player = restored.player
    drawbridge = restored.locations["Drawbridge"]
    _teleport(player, drawbridge)

    # A fed troll no longer blocks; the loaded block reads the loaded troll.
    # (Fetched from the location: after a load, Game.characters only lists
    # the player -- a separate, pre-existing save/load gap.)
    drawbridge.characters["troll"].set_property("is_hungry", False)
    restored.do_command("go east")
    assert player.location.name == "Courtyard"


def test_block_state_changed_before_the_save_survives():
    # Fidelity: the load must reproduce the *saved* state, not a fresh build.
    game = action_castle.build_game()
    game.characters["troll"].set_property("is_hungry", False)
    assert not game.locations["Drawbridge"].is_blocked("east")

    restored = _restore(game)
    assert not restored.locations["Drawbridge"].is_blocked("east")


def test_save_file_round_trip_keeps_blocks(tmp_path):
    # The on-disk path students actually use: save_game -> load_game.
    game = action_castle.build_game()
    save_file = tmp_path / "castle.json"
    game.save_game(save_file)
    restored = games.Game.load_game(save_file, custom_actions=game.custom_actions)
    assert _blocked_map(restored) == _blocked_map(game)


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
