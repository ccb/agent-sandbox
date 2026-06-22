"""Regression tests for the Action Castle IV skeleton (Slice 2).

Locks in the world topology, the start state (the princess wears a gown + tiara),
and the vehicle-gated woods exit. Puzzles + endings land in later slices.
"""

from text_adventure_games.adventures import action_castle_4 as ac4
from text_adventure_games.reporting import CaptureRenderer, Channel


def _game():
    game = ac4.build_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, cap


def _play(cmds):
    game, cap = _game()
    for c in cmds:
        game.do_command(c)
        if game.is_game_over():
            break
    return game, cap


def _said(cap, sub):
    return any(
        sub in t for ch in (Channel.NARRATION, Channel.BLOCKED) for t in cap.texts(ch)
    )


EXPECTED_ROOMS = {
    "Tower",
    "Tower Stairs",
    "Guardroom",
    "Gardens",
    "Drawbridge",
    "Down by the River",
    "Old Woods",
    "Old Shack",
    "Deep Woods",
    "Clearing",
    "Ranch",
    "Dirt Road",
    "Roadhouse",
    "The Breakpoint",
}


def test_all_rooms_present():
    game, _ = _game()
    assert set(game.locations) == EXPECTED_ROOMS


def test_every_exit_resolves():
    game, _ = _game()
    for name, loc in game.locations.items():
        for direction, dest in loc.connections.items():
            assert dest.name in game.locations, f"{name} '{direction}' -> dangling"


def test_no_duplicate_destination_exits():
    game, _ = _game()
    for name, loc in game.locations.items():
        dests = [d.name for d in loc.connections.values()]
        assert len(dests) == len(set(dests)), f"{name} has a duplicate-destination exit"


def test_key_connections():
    game, _ = _game()
    loc = game.locations

    def goes(room, direction, dest):
        return loc[room].connections.get(direction) is loc[dest]

    assert goes("Tower", "out", "Tower Stairs")
    assert goes("Tower", "down", "Gardens")
    assert goes("Tower Stairs", "down", "Guardroom")
    assert goes("Guardroom", "west", "Drawbridge")
    assert goes("Gardens", "south", "Drawbridge")
    assert goes("Drawbridge", "south", "Down by the River")
    assert goes("Drawbridge", "west", "Old Woods")
    assert goes("Old Woods", "enter", "Old Shack")
    assert goes("Old Woods", "north", "Deep Woods")
    assert goes("Deep Woods", "north", "Clearing")
    assert goes("Clearing", "west", "Dirt Road")
    assert goes("Clearing", "southwest", "Ranch")
    assert goes("Dirt Road", "north", "Roadhouse")
    assert goes("Roadhouse", "enter", "The Breakpoint")


def test_princess_starts_wearing_gown_and_tiara():
    game, _ = _game()
    assert "gown" in game.player.worn
    assert "tiara" in game.player.worn


def test_the_mare_and_motorcycle_are_vehicles_that_start_unready():
    game, _ = _game()
    mare = game.locations["Down by the River"].items["horse"]
    bike = game.locations["Roadhouse"].items["motorcycle"]
    assert mare.is_vehicle() and not mare.vehicle_ready()
    assert bike.is_vehicle() and not bike.vehicle_ready()


def test_cannot_cross_to_the_woods_on_foot():
    # Drawbridge -> Old Woods is vehicle-gated.
    game, cap = _play(
        ["out", "down", "west", "west"]
    )  # Tower->Stairs->Guardroom->Drawbridge->(try)Woods
    assert game.player.location.name == "Drawbridge"
    assert _said(cap, "too far")


def test_skeleton_smoke_path_navigates():
    game, _ = _play(ac4.WALKTHROUGH_SKELETON)
    assert game.player.location.name == "Drawbridge"
    assert not game.is_game_over()
