"""The Tomb of Nassak An-Rah (Vaults of Vaarn adventure).

The game opens at the Caravan Wreck (the onboarding sandbox, design doc §16.2);
the tomb interior holds the puzzles, threats, scoring, and deaths (see
docs/design/tomb-of-nassak-an-rah.md).
"""

from text_adventure_games.adventures import tomb_of_nassak_an_rah as tomb
from text_adventure_games.reporting import CaptureRenderer, Channel


def _game():
    return tomb.build_game()


def _goes(game, room, direction, dest):
    return game.locations[room].connections.get(direction) is game.locations[dest]


def _embark(game, *, glowstone=True):
    """Play the wreck's opening beats and walk to the Tomb Exterior -- the
    common preamble for tests of the tomb proper. With ``glowstone=False``,
    leave the stone in the pack (some tests want an empty-handed scavenger)."""
    if glowstone:
        game.do_command("open pack")
        game.do_command("take glowstone")
    game.do_command("north")


# --- the map -----------------------------------------------------------------


def test_all_eleven_locations_exist():
    game = _game()
    expected = {
        "The Caravan Wreck",
        "The Wagon's Hold",
        "Tomb Exterior",
        "Hall of Youth",
        "Hall of Memory",
        "Hall of Hounds",
        "Hall of Warriors",
        "Hall of the Canopic Jars",
        "Burial Sphere of Nassak An-Rah",
        "The Summit",
        "The Fungal Chimney",
    }
    assert expected <= set(game.locations)


def test_three_entrances_off_the_exterior():
    game = _game()
    assert _goes(game, "Tomb Exterior", "north", "Hall of Youth")  # child's mouth
    assert _goes(game, "Tomb Exterior", "east", "Hall of Warriors")  # warrior's mouth
    assert _goes(game, "Tomb Exterior", "up", "The Summit")  # the climb
    assert _goes(game, "The Summit", "down", "Tomb Exterior")  # ...and back down


def test_lower_diamond_is_a_four_cycle():
    game = _game()
    # spec edges 1-2, 1-3, 4-2, 4-3
    assert _goes(game, "Hall of Youth", "north", "Hall of Memory")  # 1-2
    assert _goes(game, "Hall of Youth", "west", "Hall of Hounds")  # 1-3
    assert _goes(game, "Hall of Memory", "north", "Hall of Warriors")  # 2-4
    assert _goes(game, "Hall of Warriors", "east", "Hall of Hounds")  # 4-3


def test_the_stairs_seal_and_chimney():
    game = _game()
    assert _goes(game, "Hall of Memory", "up", "Hall of the Canopic Jars")
    assert _goes(game, "Hall of the Canopic Jars", "down", "Hall of Memory")
    assert _goes(
        game, "Hall of the Canopic Jars", "up", "Burial Sphere of Nassak An-Rah"
    )
    assert _goes(
        game, "Burial Sphere of Nassak An-Rah", "down", "Hall of the Canopic Jars"
    )
    # the fungal chimney is a room between the summit and the sphere's crown
    assert _goes(game, "The Summit", "in", "The Fungal Chimney")
    assert _goes(game, "The Fungal Chimney", "down", "Burial Sphere of Nassak An-Rah")
    assert _goes(game, "The Fungal Chimney", "out", "The Summit")
    assert _goes(game, "Burial Sphere of Nassak An-Rah", "up", "The Fungal Chimney")


# --- start state + atmosphere ------------------------------------------------


def test_scavenger_starts_at_the_wreck_and_finds_the_glowstone():
    game = _game()
    assert game.player.location.name == "The Caravan Wreck"
    assert "glowstone" not in game.player.inventory  # found, not given
    game.do_command("open pack")
    game.do_command("take glowstone")
    assert "glowstone" in game.player.inventory


def test_go_north_skips_the_tutorial():
    """The wreck is optional exploration, not a gate."""
    game = _game()
    game.do_command("north")
    assert game.player.location.name == "Tomb Exterior"
    assert not game.is_game_over()


def test_the_wrecks_hold_teaches_light_in_safety():
    """The hold is pitch dark (the ledger unlisted) until the glowstone is lit;
    reading, lighting, and dousing there is harmless -- the safe rehearsal for
    the Hall of Youth's deadly version of the same lesson."""
    game = _game()
    cap = _texts(game)
    game.do_command("open pack")
    game.do_command("take glowstone")
    game.do_command("in")
    dark = " ".join(cap.texts(Channel.NARRATION)).lower()
    assert "bruise-dark" in dark
    assert "ledger" not in dark  # contents hidden until lit
    cap2 = _texts(game)
    game.do_command("light glowstone")
    game.do_command("look")
    game.do_command("read ledger")
    lit = " ".join(cap2.texts(Channel.NARRATION)).lower()
    assert "ledger" in lit  # revealed by the light
    assert "three mouths" in lit  # the merchant's last entries (the lore)
    game.do_command("douse glowstone")
    game.do_command("out")
    assert not game.is_game_over()
    assert game.player.location.name == "The Caravan Wreck"


def test_the_merchants_body_can_be_searched_for_his_tokens():
    """The wreck's safe rehearsal of the corpse-searching habit the Summit pays
    off: search (or examine) the merchant, find his water-debt tokens."""
    game = _game()
    cap = _texts(game)
    game.do_command("search merchant")
    assert "water-debt tokens" in " ".join(cap.texts(Channel.NARRATION)).lower()
    game.do_command("take purse")
    assert "purse of water-debt tokens" in game.player.inventory


def test_worry_the_mule_tells_the_story():
    game = _game()
    cap = _texts(game)
    game.do_command("talk to worry")
    said = " ".join(cap.texts(Channel.NARRATION)).lower()
    assert "they came at moonset" in said
    assert "caravan is seldom wrong twice" in said


def test_smoke_tour_traverses_every_room_cleanly():
    game = _game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    visited = {game.player.location.name}
    for cmd in tomb.WALK:
        game.do_command(cmd)
        visited.add(game.player.location.name)
    # the safe tour reaches the nine survivable rooms (it avoids the lethal Sphere)
    assert len(visited) == 9
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
    _embark(game)
    cap = _texts(game)
    game.do_command("sneak north")  # -> Hall of Youth (creep past the bats)
    game.do_command("sneak north")  # -> Hall of Memory (Silas)
    game.do_command("talk to silas")
    # Silas is oblique now (design doc §16.1): he points at the lattice and the
    # plinths rather than reciting the seal solution.
    said = " ".join(cap.texts(Channel.NARRATION))
    assert "lattice remembers his embalming" in said
    assert "Step softly" in said


def test_memory_crystals_give_the_head_to_organ_clue():
    game = _game()
    _embark(game)
    cap = _texts(game)
    game.do_command("sneak north")
    game.do_command("sneak north")
    game.do_command("examine crystal lattice")
    assert "the jackal -- strangely -- his brain" in " ".join(
        cap.texts(Channel.NARRATION)
    )


def test_a_sealed_jar_reveals_its_organ_only_when_opened():
    game = _game()
    cap = _texts(game)
    _bring_jars_to_canopic(game)  # hands the player the falcon jar
    game.do_command("examine falcon jar")  # sealed -> says nothing of the organ
    game.do_command("open falcon jar")  # now it reveals the intestines
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
    _embark(game)
    for cmd in ["sneak east", "take prismatic blade", "sneak east", "sneak up"]:
        game.do_command(cmd)


def test_the_hall_of_youth_is_pitch_dark_until_you_light_the_glowstone():
    game = _game()
    _embark(game)
    cap = _texts(game)
    game.do_command("north")  # into the Youth carrying the UNLIT glowstone
    dark = " ".join(cap.texts(Channel.NARRATION)).lower()
    assert "dark as the inside of a sealed jar" in dark
    assert "statues" not in dark  # the veil hides the room's contents...
    assert "exits:" not in dark  # ...and its exits
    cap2 = _texts(game)
    game.do_command("light glowstone")  # a light reveals the room
    game.do_command("look")
    lit = " ".join(cap2.texts(Channel.NARRATION)).lower()
    assert "statues" in lit
    assert "hall of memory" in lit  # exits now visible


def test_the_ceiling_is_heard_in_the_dark_and_seen_once_lit():
    game = _game()
    _embark(game)
    cap = _texts(game)
    game.do_command("north")  # dark Youth
    game.do_command("examine ceiling")  # can't see -> hear the bats (the clue)
    dark = " ".join(cap.texts(Channel.NARRATION)).lower()
    assert "leathery wings" in dark
    assert "roosting bats" not in dark  # the visual detail is withheld in the dark
    cap2 = _texts(game)
    game.do_command("light glowstone")  # now lit -> the visual ceiling
    game.do_command("examine ceiling")
    lit = " ".join(cap2.texts(Channel.NARRATION)).lower()
    assert "seethes with roosting bats" in lit


def test_you_can_feel_and_listen_in_the_dark_without_waking_the_bats():
    game = _game()
    _embark(game)
    game.do_command("north")  # dark Youth, glowstone unlit
    for probe in ("feel", "listen", "examine ceiling", "feel statues"):
        game.do_command(probe)
    assert not game.is_game_over()  # quiet senses don't rouse them
    assert game.player.location.name == "Hall of Youth"


def test_walking_into_a_dark_hall_is_safe():
    game = _game()
    _embark(game, glowstone=False)  # leave the stone in the pack
    game.do_command("north")  # STRIDE into the Hall of Youth -- no longer fatal
    assert not game.is_game_over()
    assert game.player.location.name == "Hall of Youth"


def test_light_in_the_hall_of_youth_wounds_after_one_warning():
    """The bats' patience is short (one warning), and their dive-bombing deals
    a non-lethal wound per round -- death only when wounds fill your slots."""
    game = _game()
    _embark(game)  # carrying the UNLIT glowstone
    game.do_command("north")  # into the pitch-dark Youth -- carrying it unlit is safe
    assert not game.is_game_over()
    game.do_command("light glowstone")  # raising a light rouses the bats -- ONE warning
    assert not game.is_game_over() and not game.player.wounds
    game.do_command("look")  # keep the light burning -> mauled, not killed
    assert not game.is_game_over()
    assert any(w.name == "Bat-Mauled" for w in game.player.wounds)
    game.do_command("douse glowstone")  # go dark -> they settle; the wound remains
    game.do_command("look")
    assert not game.is_game_over()
    assert len(game.player.wounds) == 1


def test_enough_bat_wounds_kill():
    game = _game()
    _embark(game)
    game.do_command("north")
    game.do_command("light glowstone")
    for _ in range(12):  # stubbornly keep the light up
        if game.is_game_over():
            break
        game.do_command("look")
    assert game.is_game_over() and not game.is_won()  # slots filled with wounds


def test_sustained_noise_brings_the_jackals_who_take_their_due():
    """Two warnings, then the pack savages you (a d20 wound-table roll) and
    withdraws -- death comes from a fatal roll or wounds filling your slots."""
    tomb._RNG.seed(0)  # first roll: 13, Cracked Skull (2 slots)
    game = _game()
    _embark(game, glowstone=False)
    game.do_command("sneak east")  # -> Hall of Warriors (safe to enter)
    game.do_command("say hey")  # one shout: a warning
    assert not game.is_game_over()
    game.do_command("say hey")  # the second warning
    assert not game.is_game_over() and not game.player.wounds
    game.do_command("say hey")  # the pack takes its due
    assert not game.is_game_over()
    assert game.player.wound_slots() == 2  # Cracked Skull
    game.do_command("wait")  # quiet again -> the pack stays away
    assert not game.is_game_over()


def test_the_live_sphere_kills_only_when_you_disturb_it():
    game = _game()
    _bring_jars_to_canopic(game)
    game.do_command("put falcon jar on falcon plinth")
    game.do_command("put jackal jar on jackal plinth")
    game.do_command("up")  # entering and looking is safe
    assert not game.is_game_over()
    game.do_command("look")
    assert not game.is_game_over()
    game.do_command("say boo")  # but any racket disturbs the live Horror...
    game.do_command("say boo")  # ...and it erupts (limit 2)
    assert game.is_game_over() and not game.is_won()


def test_the_mantis_song_lures_the_spawn_to_the_canopic_hall():
    game = _game()
    _embark(game)
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


# --- The Friend's Fungus chain (optional; design doc §13) --------------------


def test_search_and_examine_both_reveal_the_friends_fungus():
    # SEARCH the corpse (the source adventure's route)...
    game = _game()
    cap = _texts(game)
    game.relocate(game.player, game.locations["The Summit"])
    game.do_command("search corpse")
    assert "pink fungus" in " ".join(cap.texts(Channel.NARRATION)).lower()
    game.do_command("take fungus")
    assert "friend's fungus" in game.player.inventory
    # ...and EXAMINE works too (reveals_on_examine).
    game2 = _game()
    cap2 = _texts(game2)
    game2.relocate(game2.player, game2.locations["The Summit"])
    game2.do_command("x corpse")  # the short alias must match
    out = " ".join(cap2.texts(Channel.NARRATION)).lower()
    assert "clasped hands" in out and "pink fungus" in out


def test_feeding_silas_the_fungus_earns_the_ulfire_lantern():
    game = _game()
    cap = _texts(game)
    fungus = (
        game.locations["The Summit"]
        .items["ossified corpse"]
        .contents["friend's fungus"]
    )
    fungus.set_property("is_hidden", False)
    game.locations["The Summit"].items["ossified corpse"].remove_item(fungus)
    game.player.add_to_inventory(fungus)
    game.relocate(game.player, game.locations["Hall of Memory"])
    game.do_command("give fungus to silas")
    assert "ulfire lantern" in game.player.inventory
    assert "a friend" in " ".join(cap.texts(Channel.NARRATION)).lower()


def test_ulfire_light_reveals_the_ego_core_in_the_manifold_box():
    game = _game()
    cap = _texts(game)
    # Shortcut: hand the player the lantern and the box directly.
    silas = game.characters["Silas"]
    lamp = silas.inventory["ulfire lantern"]
    silas.remove_from_inventory(lamp)
    game.player.add_to_inventory(lamp)
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    box = sphere.items["coffin"].contents["manifold box"]
    sphere.items["coffin"].remove_item(box)
    game.player.add_to_inventory(box)
    assert "ego-core" not in game.player.inventory
    game.do_command("light lantern")  # the very specific angle
    assert "ego-core" in game.player.inventory
    assert (
        "compartment three times larger"
        in " ".join(cap.texts(Channel.NARRATION)).lower()
    )


def test_burning_the_corpse_consumes_an_unclaimed_fungus():
    game = _game()
    _embark(game)
    for cmd in [
        "sneak east",
        "take igniter",
        "sneak east",
        "take gel",
        "sneak east",
        "sneak south",
        "up",
        "burn corpse",
    ]:
        game.do_command(cmd)
    corpse = game.locations["The Summit"].items["ossified corpse"]
    assert "friend's fungus" not in corpse.contents  # went up with him


# --- Phase 4: fire, the zero-g coffin, and the win ---------------------------


def test_the_chimney_is_passable_but_the_spores_scar_your_lungs():
    """Two warnings, then a Seared Lungs wound per round of lingering -- death
    only when the wounds fill your slots."""
    game = _game()
    _embark(game)
    game.do_command("up")  # -> Summit
    game.do_command("in")  # into the fungal chimney -- passable, not blocked
    assert game.player.location.name == "The Fungal Chimney"
    assert not game.is_game_over()  # first breath: a warning
    game.do_command("look")  # second warning
    assert not game.is_game_over() and not game.player.wounds
    game.do_command("look")  # now the spores wound
    assert not game.is_game_over()
    assert any(w.name == "Seared Lungs" for w in game.player.wounds)
    game.do_command("out")  # leaving stops the harm
    assert not game.is_game_over()


def test_drinking_water_mends_a_wound():
    game = _game()
    game.do_command("open pack")
    game.do_command("take glowstone")
    game.do_command("take waterskin")
    from text_adventure_games.slots import Wound

    game.player.add_wound(Wound("Bloody Gash", 1, "..."))
    cap = _texts(game)
    game.do_command("drink water")
    assert not game.player.wounds  # the glug of water mends
    assert "something knits" in " ".join(cap.texts(Channel.NARRATION)).lower()


def test_overloaded_scavenger_cannot_make_the_climb():
    game = _game()
    cap = _texts(game)
    # Greed: haul all the cargo out of the hold, then try the tomb face.
    for cmd in (
        "in",
        "take bale of saffron",
        "take crate of dates",
        "take bolt of spider-silk",
        "out",
    ):
        game.do_command(cmd)
    game.do_command("open pack")
    game.do_command("take glowstone")
    game.do_command("take waterskin")
    # blade would be next, but the cargo alone is 5 slots -- go check the climb
    game.do_command("north")
    # load up past 10: add the blade and kit from the Hall of Warriors
    game.do_command("east")
    for cmd in ("take blade", "take igniter", "take boots", "take respirator"):
        game.do_command(cmd)
    assert game.player.is_encumbered()
    game.do_command("west")
    game.do_command("up")  # the climb to the Summit
    assert game.player.location.name == "Tomb Exterior"
    assert (
        "climb is out of the question"
        in " ".join(cap.texts(Channel.NARRATION) + cap.texts(Channel.BLOCKED)).lower()
    )


def test_burning_the_corpse_kills_the_horror_and_makes_the_sphere_safe():
    game = _game()
    _embark(game)
    # Arm with gel + igniter, creep out to the Exterior, climb up, burn the root.
    for cmd in [
        "sneak east",
        "take igniter",
        "sneak east",
        "take gel",
        "sneak east",
        "sneak south",
        "up",
        "burn corpse",
    ]:
        game.do_command(cmd)
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    assert sphere.get_property("horror_dead")
    assert game.locations["The Summit"].get_property("cleansed")


def test_prying_the_coffin_needs_the_magnetic_boots():
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    sphere.set_property("horror_dead", True)  # pretend it's cleansed
    game.relocate(game.player, sphere)
    game.do_command("pry coffin")  # no boots -> refused
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
