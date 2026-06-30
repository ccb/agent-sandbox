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
    # the safe tour reaches the seven survivable rooms (it avoids the lethal Sphere)
    assert len(visited) == 7
    # ...with no failed move or unparsed/missing command, and survives (it creeps)
    texts = " ".join(cap.texts(Channel.NARRATION)).lower()
    assert "i'm not sure what you want to do" not in texts
    assert "does not have an exit" not in texts
    assert "you don't see anything special" not in texts
    assert not game.is_game_over()  # the safe tour creeps, so nothing kills you


# --- Phase 2: the canopic seal puzzle + Silas --------------------------------


def _texts(game):
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return cap


def _bring_jars_to_canopic(game):
    """Test shortcut for the seal-mechanic tests: hand the player both jars and
    stand them in the Canopic hall, skipping the lure-and-fight (covered in the
    Phase 3 section). The jars are otherwise worn by the Spawn."""
    canopic = game.locations["Hall of the Canopic Jars"]
    for sp in ("spawn of guts", "spawn of brain"):
        spawn = game.characters[sp]
        for jar in list(spawn.inventory.values()):
            spawn.remove_from_inventory(jar)
            game.player.add_to_inventory(jar)
    game.relocate(game.player, canopic)


def test_silas_warns_about_the_spawn_and_the_seal():
    game = _game()
    cap = _texts(game)
    game.do_command("sneak north")  # -> Hall of Youth (creep past the bats)
    game.do_command("sneak north")  # -> Hall of Memory (Silas)
    game.do_command("talk to silas")
    assert "plinth of its kind" in " ".join(cap.texts(Channel.NARRATION))


def test_memory_crystals_give_the_head_to_organ_clue():
    game = _game()
    cap = _texts(game)
    game.do_command("sneak north")
    game.do_command("sneak north")
    game.do_command("examine crystal lattice")
    assert "the jackal -- strangely -- his brain" in " ".join(cap.texts(Channel.NARRATION))


def test_a_sealed_jar_reveals_its_organ_only_when_opened():
    game = _game()
    cap = _texts(game)
    _bring_jars_to_canopic(game)              # hands the player the falcon jar
    game.do_command("examine falcon jar")     # sealed -> says nothing of the organ
    game.do_command("open falcon jar")        # now it reveals the intestines
    texts = " ".join(cap.texts(Channel.NARRATION))
    assert "in it you see: a coil of cured intestines" in texts.lower()


def test_the_seal_bars_the_stair_until_both_jars_are_placed():
    game = _game()
    _bring_jars_to_canopic(game)
    assert game.player.location.name == "Hall of the Canopic Jars"
    game.do_command("up")  # the crystal seal blocks the stair
    assert game.player.location.name == "Hall of the Canopic Jars"
    assert not game.locations["Hall of the Canopic Jars"].get_property("seal_open")


def test_wrong_plinth_does_not_open_the_seal():
    game = _game()
    _bring_jars_to_canopic(game)
    game.do_command("put falcon jar on jackal plinth")  # mismatch
    game.do_command("put jackal jar on falcon plinth")  # mismatch
    assert not game.locations["Hall of the Canopic Jars"].get_property("seal_open")


def test_matching_both_jars_opens_the_seal():
    game = _game()
    _bring_jars_to_canopic(game)
    game.do_command("put falcon jar on falcon plinth")
    game.do_command("put jackal jar on jackal plinth")
    assert game.locations["Hall of the Canopic Jars"].get_property("seal_open")


# --- Phase 3: the tomb listens (noise, Spawn lure, deaths) -------------------


def _arm_and_reach_canopic(game):
    """Sneak in, take the prismatic blade from the Hall of Warriors, and creep up
    to the Canopic hall -- armed and safe."""
    for cmd in ["sneak east", "take prismatic blade", "sneak east", "sneak up"]:
        game.do_command(cmd)


def test_striding_into_a_hall_is_deadly_but_creeping_is_safe():
    loud = _game()
    loud.do_command("north")  # STRIDE into the Hall of Youth -> the bats
    assert loud.is_game_over() and not loud.is_won()

    quiet = _game()
    quiet.do_command("sneak north")  # creep in -> safe
    assert not quiet.is_game_over()
    assert quiet.player.location.name == "Hall of Youth"


def test_a_loud_action_in_a_hall_is_deadly():
    game = _game()
    game.do_command("sneak north")  # -> Hall of Youth (safe)
    game.do_command("say anyone there?")  # but shouting wakes the bats
    assert game.is_game_over() and not game.is_won()


def test_the_burial_sphere_is_lethal_to_enter():
    game = _game()
    _bring_jars_to_canopic(game)
    game.do_command("put falcon jar on falcon plinth")
    game.do_command("put jackal jar on jackal plinth")
    game.do_command("up")  # step into the Sphere -> the Fungal Horror
    assert game.is_game_over() and not game.is_won()


def test_the_mantis_song_lures_the_spawn_to_the_canopic_hall():
    game = _game()
    for cmd in ["sneak north", "sneak north", "sneak up"]:  # -> Canopic, silently
        game.do_command(cmd)
    canopic = game.player.location
    assert "spawn of brain" not in canopic.characters  # they start in the lower halls
    for _ in range(5):
        game.do_command("say come to me")  # the mantis-head sings; the Spawn home in
    assert "spawn of guts" in canopic.characters
    assert "spawn of brain" in canopic.characters


def test_felling_a_lured_spawn_drops_its_canopic_jar():
    game = _game()
    _arm_and_reach_canopic(game)
    canopic = game.player.location
    for _ in range(5):
        game.do_command("say come to me")  # lure both up
    assert "spawn of guts" in canopic.characters
    game.do_command("attack spawn of guts with blade")
    assert "falcon jar" in canopic.items  # the felled Spawn dropped its jar
    assert not game.is_game_over()  # fighting in the (safe) Canopic hall is fine


# --- Phase 4: fire, the zero-g coffin, and the win ---------------------------


def test_the_choked_chimney_cannot_be_passed():
    game = _game()
    game.do_command("up")          # -> Summit (safe)
    game.do_command("in")          # try the fungal chimney down to the Sphere
    assert game.player.location.name == "The Summit"  # blocked by spores


def test_burning_the_corpse_kills_the_horror_and_makes_the_sphere_safe():
    game = _game()
    # Arm with gel + igniter, creep out to the Exterior, climb up, burn the root.
    for cmd in ["sneak east", "take igniter", "sneak east", "take gel",
                "sneak east", "sneak south", "up", "burn corpse"]:
        game.do_command(cmd)
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    assert sphere.get_property("horror_dead")
    assert game.locations["The Summit"].get_property("cleansed")


def test_prying_the_coffin_needs_the_magnetic_boots():
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    sphere.set_property("horror_dead", True)         # pretend it's cleansed
    game.relocate(game.player, sphere)
    game.do_command("pry coffin")                    # no boots -> refused
    assert sphere.items["coffin"].get_property("pried") in (False, None)
    assert "synth-hunting dagger" not in sphere.items
    # with the boots worn, it works
    boots = game.locations["Hall of Warriors"].items["magnetic boots"]
    game.locations["Hall of Warriors"].remove_item(boots)
    game.player.add_to_inventory(boots)
    game.do_command("wear boots")
    game.do_command("pry coffin")
    assert sphere.items["coffin"].get_property("pried")
    assert "synth-hunting dagger" in sphere.items


def test_the_full_winning_run_scores_100():
    game = _game()
    for cmd in tomb.WIN_WALKTHROUGH:
        if game.is_game_over():
            break
        game.do_command(cmd)
    assert game.is_won()
    assert game.score == 100 == game.max_score
    assert game.player.location.name == "Tomb Exterior"
