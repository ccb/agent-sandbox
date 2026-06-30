"""The Tomb of Nassak An-Rah (Vaults of Vaarn adventure).

PHASE 1: map + atmosphere scaffold only -- the world is navigable and examinable,
the scavenger starts with a glowstone. Puzzles, threats, scoring, and deaths land
in later phases (see docs/design/tomb-of-nassak-an-rah.md).
"""

from text_adventure_games.adventures import tomb_of_nassak_an_rah as tomb
from text_adventure_games.reporting import CaptureRenderer, Channel


def _game():
    return tomb.build_game()


def _goes(game, room, direction, dest):
    return game.locations[room].connections.get(direction) is game.locations[dest]


# --- the map -----------------------------------------------------------------


def test_all_eight_locations_exist():
    game = _game()
    expected = {
        "Tomb Exterior",
        "Hall of Youth",
        "Hall of Memory",
        "Hall of Hounds",
        "Hall of Warriors",
        "Hall of the Canopic Jars",
        "Burial Sphere of Nassak An-Rah",
        "The Summit",
    }
    assert expected <= set(game.locations)


def test_three_entrances_off_the_exterior():
    game = _game()
    assert _goes(game, "Tomb Exterior", "north", "Hall of Youth")        # child's mouth
    assert _goes(game, "Tomb Exterior", "east", "Hall of Warriors")      # warrior's mouth
    assert _goes(game, "Tomb Exterior", "up", "The Summit")              # the climb
    assert _goes(game, "The Summit", "down", "Tomb Exterior")            # ...and back down


def test_lower_diamond_is_a_four_cycle():
    game = _game()
    # spec edges 1-2, 1-3, 4-2, 4-3
    assert _goes(game, "Hall of Youth", "north", "Hall of Memory")       # 1-2
    assert _goes(game, "Hall of Youth", "west", "Hall of Hounds")        # 1-3
    assert _goes(game, "Hall of Memory", "north", "Hall of Warriors")    # 2-4
    assert _goes(game, "Hall of Warriors", "east", "Hall of Hounds")     # 4-3


def test_the_stairs_seal_and_chimney():
    game = _game()
    assert _goes(game, "Hall of Memory", "up", "Hall of the Canopic Jars")
    assert _goes(game, "Hall of the Canopic Jars", "down", "Hall of Memory")
    assert _goes(game, "Hall of the Canopic Jars", "up", "Burial Sphere of Nassak An-Rah")
    assert _goes(game, "Burial Sphere of Nassak An-Rah", "down", "Hall of the Canopic Jars")
    # the fungal chimney (in/out) joins the sphere's crown to the summit
    assert _goes(game, "The Summit", "in", "Burial Sphere of Nassak An-Rah")
    assert _goes(game, "Burial Sphere of Nassak An-Rah", "out", "The Summit")


# --- start state + atmosphere ------------------------------------------------


def test_scavenger_starts_in_the_sands_with_a_glowstone():
    game = _game()
    assert game.player.location.name == "Tomb Exterior"
    assert "glowstone" in game.player.inventory


def test_smoke_tour_traverses_every_room_cleanly():
    game = _game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    visited = {game.player.location.name}
    for cmd in tomb.WALK:
        game.do_command(cmd)
        visited.add(game.player.location.name)
    # the tour reaches all eight rooms...
    assert len(visited) == 8
    # ...with no failed move or unparsed/missing command along the way
    texts = " ".join(cap.texts(Channel.NARRATION)).lower()
    assert "i'm not sure what you want to do" not in texts
    assert "does not have an exit" not in texts
    assert "you don't see anything special" not in texts
    assert not game.is_game_over()  # nothing lethal in the scaffold
