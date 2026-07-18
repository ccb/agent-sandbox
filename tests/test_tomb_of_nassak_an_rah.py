"""The Tomb of Nassak An-Rah (Vaults of Vaarn adventure).

The game opens at the Caravan Wreck (the onboarding sandbox, design doc §16.2);
the tomb interior holds the puzzles, threats, scoring, and deaths (see
docs/design/tomb-of-nassak-an-rah.md).
"""

from text_adventure_games.adventures import tomb_of_nassak_an_rah as tomb
from text_adventure_games.reporting import CaptureRenderer, Channel


def _game():
    # Seed per game so no test depends on the RNG state its neighbors left
    # behind (the climb test once failed only in full-file runs because a new
    # test upstream shifted the stream before its wound-displacement draw).
    return tomb.build_game(seed=0)


def _goes(game, room, direction, dest):
    return game.locations[room].connections.get(direction) is game.locations[dest]


def _embark(game, *, glowstone=True):
    """Play the wreck's opening beats and walk to the Tomb Exterior -- the
    common preamble for tests of the tomb proper. With ``glowstone=False``,
    leave the stone in the pack (some tests want an empty-handed scavenger)."""
    if glowstone:
        game.do_command("search merchant")
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
    assert _goes(game, "Hall of Hounds", "up", "Hall of the Canopic Jars")
    # Two stairways down from the pentagon (source, room 5): left to Memory,
    # right to Hounds.
    assert _goes(game, "Hall of the Canopic Jars", "left stairs", "Hall of Memory")
    assert _goes(game, "Hall of the Canopic Jars", "right stairs", "Hall of Hounds")
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
    game.do_command("search merchant")
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
    game.do_command("search merchant")
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


def test_the_hall_of_warriors_reads_its_own_wreckage():
    """CCB: the room description updates as cylinders break -- remaining
    colours named, the fungus note gone with the orange one, and a final
    all-burst state ("one darkening lake")."""
    game = _game()
    warriors = game.locations["Hall of Warriors"]
    game.relocate(game.player, warriors)
    assert "Four plexiglas cylinders stand" in warriors.description
    game.do_command("break cerulean cylinder")
    game.do_command("break orange cylinder")
    assert "amber and viridian still stand" in warriors.description
    assert "Fungus" not in warriors.description  # gone with the orange
    cylinders = warriors.items["cylinders"]
    assert "Only the amber and viridian" in cylinders.examine_text()
    game.do_command("break amber cylinder")
    game.do_command("break viridian cylinder")
    assert "one darkening lake" in warriors.description
    assert "All four cylinders lie burst" in cylinders.examine_text()


def test_the_pack_takes_three_blows():
    """The vigor system (CCB): a PACK does not drop to one swing."""
    game = _game()
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    pack = game.characters["jackal pack"]
    game.relocate(game.player, game.locations["Hall of Memory"])
    game.relocate(pack, game.player.location)
    cap = _texts(game)
    game.do_command("attack jackal pack with blade")
    game.do_command("attack jackal pack with blade")
    assert not pack.get_property("is_unconscious")
    assert any("thinner by one" in t for t in cap.texts(Channel.NARRATION))
    game.do_command("attack jackal pack with blade")
    assert pack.get_property("is_unconscious")


def test_silas_takes_two_blows():
    game = _game()
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.relocate(game.player, game.locations["Hall of Memory"])
    silas = game.characters["Silas"]
    game.do_command("attack silas with blade")
    assert not silas.get_property("is_unconscious")
    game.do_command("attack silas with blade")
    assert silas.get_property("is_unconscious")


def test_unstatted_creatures_still_drop_in_one():
    """vigor unset = the classic one-hit knockout: the engine default
    leaves every existing NPC untouched."""
    game = _game()
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.relocate(game.player, game.locations["The Summit"])
    game.do_command("in")  # the centipede springs
    game.do_command("attack centipede with blade")
    assert game.characters["glass centipede"].get_property("is_unconscious")


def test_the_teamster_tells_the_story_and_decamps():
    """CCB's pick: the teamster is CRITCH, the golden new-hyena, every
    expedition -- and once she has said her piece she decamps south along
    the trail, out of the game."""
    game = _game()
    wreck = game.locations["The Caravan Wreck"]
    teamster = next(c for c in wreck.characters.values() if "teamster" in c.description)
    assert teamster.name == "Critch"  # chosen, not rolled
    assert "cracked clean across the smile" in teamster.examine_text
    cap = _texts(game)
    game.do_command("talk to teamster")
    said = " ".join(cap.texts(Channel.NARRATION)).lower()
    assert "they came at moonset" in said
    assert "tomb pays better than the road" in said
    # She has already decided to be elsewhere.
    assert teamster.name not in wreck.characters
    assert "sets off south along the trail" in " ".join(cap.texts(Channel.NARRATION))


def test_every_seed_meets_critch():
    names = set()
    for seed in range(4):
        game = tomb.build_game(seed=seed)
        wreck = game.locations["The Caravan Wreck"]
        t = next(c for c in wreck.characters.values() if "teamster" in c.description)
        names.add(t.name)
    assert names == {"Critch"}  # one face for the caravan, every time


def test_examine_self_is_the_chargen_easter_egg():
    """EXAMINE SELF (CCB): once per expedition the scavenger discovers who
    they have been all along; every later look finds the same self, and a
    (seed, journal) replay remembers the face."""
    game = _game()
    cap = _texts(game)
    game.do_command("x self")
    first = " ".join(cap.texts(Channel.NARRATION))
    assert "You take stock of yourself" in first
    assert "You are" in first  # one of the hundred selves
    i = game.player.get_property("_self_index")
    assert i is not False and i is not None
    cap2 = _texts(game)
    game.do_command("examine self")
    again = " ".join(cap2.texts(Channel.NARRATION))
    assert "You remain, on inspection, yourself." in again
    assert game.player.get_property("_self_index") == i  # rolled once only
    # the roll survives the save replay
    game2 = tomb.build_game(seed=0)
    game2.parser.set_renderer(CaptureRenderer())
    game2.replay(list(game.journal))
    assert game2.player.get_property("_self_index") == i
    # and the aliases do not hijack other examines
    cap3 = _texts(game)
    game.do_command("examine merchant")
    assert "composed" in " ".join(cap3.texts(Channel.NARRATION))


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
    assert "lattice remembers his father's embalming" in said
    assert "Step softly" in said


def test_memory_crystals_give_the_head_to_organ_clue():
    """The clue is now one facet among many (CCB: random memory per look):
    whoever troubles to keep looking still finds the embalming."""
    game = _game()
    _embark(game)
    tomb._RNG.seed(1)
    cap = _texts(game)
    game.do_command("sneak north")
    game.do_command("sneak north")
    for _ in range(30):  # sift the king's days for the useful one
        game.do_command("examine crystal lattice")
        if "the jackal -- strangely -- his brain" in " ".join(
            cap.texts(Channel.NARRATION)
        ):
            break
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
    for cmd in [
        "sneak east",
        "break cerulean cylinder",
        "take prismatic blade",
        "sneak east",
        "sneak up",
    ]:
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


def _no_spawn(game):
    """KO both Spawn so a test can isolate the jackal pack (the Spawn are
    drawn to the same noises and would interleave attacks)."""
    for name in ("spawn of guts", "spawn of brain"):
        game.characters[name].set_property("is_unconscious", True)


def test_sustained_noise_brings_the_pack_who_growl_then_maul():
    """Two warnings, then the pack ENTERS and growls (one round of grace);
    unfed and unfled, they maul (a d20 wound-table roll) round after round."""
    tomb._RNG.seed(0)  # first roll: 13, Cracked Skull (2 slots)
    game = _game()
    cap = _texts(game)
    _no_spawn(game)
    _embark(game, glowstone=False)
    game.do_command("sneak north")  # -> Hall of Youth (dark, quiet)
    game.do_command("sneak north")  # -> Hall of Memory (no Spawn here)
    game.do_command("say hey")  # a shout AND the song it wakes: +2
    assert not game.player.wounds
    game.do_command("say hey")  # +2 again: the pack enters
    hall = game.locations["Hall of Memory"]
    assert "jackal pack" in hall.characters
    assert not game.player.wounds  # the entry round is grace
    game.do_command("wait")  # neither fed nor fled -> mauled
    assert game.player.wound_slots() == 2  # Cracked Skull
    assert not game.is_game_over()
    assert "jackal pack" in hall.characters  # they wait for more


def test_feeding_the_pack_buys_them_off():
    game = _game()
    cap = _texts(game)
    _no_spawn(game)
    # Bring the dates from the wreck, then make a racket in Memory.
    for cmd in (
        "in",
        "open crates",
        "take dates",
        "out",
        "north",
        "north",
        "north",
        "say hey",
        "say hey",
    ):
        game.do_command(cmd)
    hall = game.locations["Hall of Memory"]
    assert "jackal pack" in hall.characters
    wounds_before = game.player.wound_slots()
    game.do_command("give dates to jackals")
    assert "jackal pack" not in hall.characters  # gone with the goods
    game.do_command("wait")
    assert game.player.wound_slots() == wounds_before  # sated: no more mauls
    out = " ".join(cap.texts(Channel.NARRATION)).lower()
    assert "terrible courtesy" in out
    game.do_command("say hey")  # the fed pack forgets you a while
    assert "jackal pack" not in hall.characters


def test_the_pack_refuses_what_it_cannot_eat():
    game = _game()
    cap = _texts(game)
    _no_spawn(game)
    for cmd in (
        "in",
        "open crates",
        "take bale",
        "out",
        "north",
        "north",
        "north",
        "say hey",
        "say hey",
        "say hey",
        "say hey",
    ):
        game.do_command(cmd)
    hall = game.locations["Hall of Memory"]
    tomb._RNG.seed(0)
    game.do_command("give saffron to jackals")  # not that kind of hunger
    assert "bale of saffron" in hall.items  # dropped at your feet
    assert "jackal pack" in hall.characters  # and they are still here
    assert "not that kind of hunger" in " ".join(cap.texts(Channel.NARRATION)).lower()


def test_the_sphere_is_safe_until_you_pry():
    """The sphere has no noise hazard (design doc §17.3): enter, look, even
    shout. Only the deliberate act -- prying the live coffin -- wakes the boss."""
    game = _game()
    _bring_jars_to_canopic(game)
    game.do_command("put falcon jar on falcon plinth")
    game.do_command("put jackal jar on jackal plinth")
    game.do_command("up")
    game.do_command("look")
    game.do_command("say boo")
    game.do_command("say boo")
    assert not game.is_game_over()
    assert "fungal horror" not in game.player.location.characters


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
        "a direction the tomb does not otherwise have"
        in " ".join(cap.texts(Channel.NARRATION)).lower()
    )


def test_the_spawn_ignores_a_sneaking_scavenger():
    """The Spawn are blind -- they hunt footfalls. Creep and they never know."""
    game = _game()
    game.do_command("north")
    game.do_command("sneak east")  # into the spawn's dark hall, silently
    game.do_command("sneak west")  # and out again
    assert not game.player.wounds


def test_striding_in_earns_a_warning_then_a_lash():
    game = _game()
    cap = _texts(game)
    game.do_command("north")
    game.do_command("east")  # footfalls: it swings toward you
    assert "swings toward your noise" in " ".join(cap.texts(Channel.NARRATION))
    assert not game.player.wounds  # the swing is the warning
    game.do_command("say hello")  # loud again while it listens -> the lash
    assert any(w.name == "Acid-Lashed" for w in game.player.wounds)
    assert not game.is_game_over()


def test_the_brain_spawn_opens_your_hands():
    """Psychic domination: it makes you drop your wielded weapon."""
    game = _game()
    blade = things_blade = None
    # arm the player directly and walk into the brain's hall wielding steel
    cyl = game.locations["Hall of Warriors"].items["cerulean cylinder"]
    blade = cyl.contents["prismatic blade"]
    cyl.remove_item(blade)
    game.player.add_to_inventory(blade)
    game.do_command("wield blade")
    game.relocate(game.player, game.locations["Hall of Hounds"])
    game.do_command("say hello")  # warn
    game.do_command("say hello")  # dominate: hands open
    assert "prismatic blade" not in game.player.wielded
    assert "prismatic blade" in game.locations["Hall of Hounds"].items


def test_the_kit_is_sealed_until_the_glass_breaks():
    game = _game()
    cap = _texts(game)
    game.do_command("north")
    game.do_command("sneak east")  # Hall of Warriors -- creep: the Spawn hears
    game.do_command("take blade")  # sealed under glass -> unreachable
    assert "prismatic blade" not in game.player.inventory
    game.do_command("break cerulean cylinder")  # loud: the crash carries
    game.do_command("take blade")
    assert "prismatic blade" in game.player.inventory
    assert "rings on the stone" in " ".join(cap.texts(Channel.NARRATION)).lower()


def test_venting_the_orange_cylinder_sears_unmasked_lungs():
    game = _game()
    game.do_command("north")
    game.do_command("sneak east")
    game.do_command("break orange cylinder")  # no respirator -> the bloom bites
    assert any(w.name == "Seared Lungs" for w in game.player.wounds)
    assert not game.is_game_over()


def test_a_respirator_makes_the_orange_cylinder_safe():
    game = _game()
    _sate_pack(game)  # this test is about spores, not jackals
    cap = _texts(game)
    for cmd in (
        "north",
        "sneak east",
        "break amber cylinder",
        "take respirator",
        "wear respirator",
        "break orange cylinder",
    ):
        game.do_command(cmd)
    # The mask's job is the spores (the spawn may still have opinions).
    assert not any(w.name == "Seared Lungs" for w in game.player.wounds)
    assert "disappointed" in " ".join(cap.texts(Channel.NARRATION)).lower()
    game.do_command("take igniter")
    assert "plasma-igniter" in game.player.inventory


def test_burning_the_corpse_consumes_an_unclaimed_fungus():
    game = _game()
    _embark(game)
    for cmd in [
        "sneak east",
        "break orange cylinder",  # unmasked: costs a Seared Lungs wound
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


# --- Throw, the thrown-light gambit, and appetites ----------------------------


def test_throw_lands_next_door_and_lures_the_sound_hunters():
    game = _game()
    cap = _texts(game)
    for cmd in ("search merchant", "take purse", "north"):
        game.do_command(cmd)
    game.do_command("throw purse north")
    assert "purse of water-debt tokens" in game.locations["Hall of Youth"].items
    assert "a clatter from" in " ".join(cap.texts(Channel.NARRATION))
    game.do_command("wait")
    game.do_command("wait")
    # A spawn heard it land and went to see (whichever was closer).
    assert any(
        game.characters[n].location is game.locations["Hall of Youth"]
        for n in ("spawn of guts", "spawn of brain")
    )


def test_the_thrown_light_gambit_kills_a_spawn_by_bats():
    """CCB's puzzle: lure a spawn into the Youth with a thrown clatter, then
    throw the LIT glowstone in after it -- the swarm mobs the light and rakes
    the spawn dead, leaving its jar and a motionless body."""
    game = _game()
    for cmd in (
        "search merchant",
        "take glowstone",
        "search merchant",
        "take purse",
        "north",
        "throw purse north",
        "wait",
        "wait",
        "light glowstone",
        "throw glowstone north",
        "wait",
        "wait",
    ):
        game.do_command(cmd)
    youth = game.locations["Hall of Youth"]
    dead = [
        n
        for n in ("spawn of guts", "spawn of brain")
        if game.characters[n].get_property("is_dead")
    ]
    assert dead  # the swarm got one
    assert any(j in youth.items for j in ("falcon jar", "jackal jar"))
    assert "dead and motionless" in game.characters[dead[0]].description
    assert not game.is_game_over()  # the player never entered


def test_throwing_the_fungus_at_a_spawn_doses_it():
    game = _game()
    cap = _texts(game)
    # Fetch the fungus, then find the spawn of guts and dose it.
    game.relocate(game.player, game.locations["The Summit"])
    game.do_command("search corpse")
    game.do_command("take fungus")
    guts = game.characters["spawn of guts"]
    game.relocate(game.player, guts.location)
    game.do_command("throw fungus at spawn of guts")
    assert guts.get_property("dosed")
    assert "extremely agreeable" in " ".join(cap.texts(Channel.NARRATION))
    # Dosed, it no longer minds your noise.
    game.do_command("say hello")
    game.do_command("say hello")
    game.do_command("say hello")
    assert not any(w.name == "Acid-Lashed" for w in game.player.wounds)


def test_silas_whispers_while_a_spawn_is_in_the_room():
    game = _game()
    cap = _texts(game)
    silas = game.characters["Silas"]
    game.relocate(game.characters["spawn of guts"], silas.location)
    game.relocate(game.player, silas.location)
    game.do_command("talk to silas")
    assert "be silent, you fool" in " ".join(cap.texts(Channel.NARRATION)).lower()


def test_the_waterskin_holds_three_healing_rations():
    game = _game()
    from text_adventure_games.slots import Wound

    game.do_command("search merchant")
    game.do_command("take waterskin")
    game.player.add_wound(Wound("Bloody Gash", 1, "..."))
    for expected in ("2 rations", "1 ration", "an empty waterskin"):
        game.do_command("drink water")
        assert expected in game.player.inventory["waterskin"].description
    assert not game.player.wounds  # the first drink healed it
    cap = _texts(game)
    game.do_command("drink water")  # a fourth: refused
    assert "is empty" in " ".join(cap.texts(Channel.BLOCKED)).lower()


def test_organs_are_gettable_edible_and_regrettable():
    game = _game()
    game.relocate(game.player, game.locations["Hall of the Canopic Jars"])
    game.do_command("open baboon jar")
    game.do_command("take lungs")
    assert "lungs" in game.player.inventory
    game.do_command("eat lungs")
    assert any(w.name == "Grave-Sick" for w in game.player.wounds)


def test_breaking_the_hound_tank_spills_the_cyborg_hounds():
    game = _game()
    cap = _texts(game)
    game.relocate(game.player, game.locations["Hall of Hounds"])
    game.do_command("break tank")
    hall = game.locations["Hall of Hounds"]
    assert "cyborg hound" in hall.items
    assert "flood" in " ".join(cap.texts(Channel.NARRATION)).lower()


# --- Phase 4: fire, the zero-g coffin, and the win ---------------------------


def test_the_chimney_is_passable_but_the_spores_scar_your_lungs():
    """No grace: EVERY unmasked round in the throat is a Seared Lungs wound
    (CCB) -- death only when the wounds fill your slots."""
    game = _game()
    _embark(game)
    game.characters["glass centipede"].set_property("is_unconscious", True)
    game.do_command("up")  # -> Summit
    game.do_command("in")  # into the fungal chimney -- passable, not blocked
    assert game.player.location.name == "The Fungal Chimney"
    assert not game.is_game_over()
    wounds = lambda g: sum(1 for w in g.player.wounds if w.name == "Seared Lungs")
    assert wounds(game) == 1  # the first breath already burns
    game.do_command("look")  # linger a round: another wound
    assert wounds(game) == 2 and not game.is_game_over()
    game.do_command("out")  # leaving stops the harm
    n = wounds(game)
    game.do_command("look")  # a round on the summit: no new searing
    assert wounds(game) == n
    assert not game.is_game_over()


def test_a_held_respirator_does_not_seal_lungs():
    """The mask works WORN, not carried (CCB: 'if I am not wearing a
    respirator') -- and worn, it holds for as long as you care to linger."""
    game = _game()
    _embark(game)
    game.characters["glass centipede"].set_property("is_unconscious", True)
    _hand(game, "Hall of Warriors", "amber cylinder", "respirator")
    game.do_command("up")
    game.do_command("in")  # holding the mask in a hand: the spores don't care
    assert any(w.name == "Seared Lungs" for w in game.player.wounds)
    game.do_command("out")
    game.do_command("wear respirator")
    game.do_command("in")
    game.do_command("look")
    game.do_command("look")  # three masked rounds: the seal holds
    assert sum(1 for w in game.player.wounds if w.name == "Seared Lungs") == 1


def test_the_prayers_read_and_the_balm_answers_once():
    """The sphere's carvings hold three prayers (CCB): READ lists them, an
    unnamed SAY asks which, BALM refuses whole flesh, heals a wound once,
    and the answered line goes smooth."""
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    sphere.set_property("horror_dead", True)
    game.relocate(game.player, sphere)
    cap = _texts(game)
    game.do_command("read prayers")
    text = " ".join(cap.texts(Channel.NARRATION))
    assert "PRAYER OF BALM" in text
    assert "PRAYER OF WRATH" in text
    assert "PRAYER OF MENDING" in text
    game.do_command("say prayers")  # unnamed: the carvings list the choices
    assert "SAY PRAYER OF BALM" in " ".join(cap.texts(Channel.BLOCKED))
    game.do_command("say prayer of balm")  # unhurt: refused, not spent
    assert "whole flesh" in " ".join(cap.texts(Channel.BLOCKED))
    from text_adventure_games.slots import Wound

    game.player.add_wound(Wound("Bloody Gash", 1, "..."))
    game.do_command("say prayer of balm")
    assert not game.player.wounds  # the chamber closes the wound
    game.do_command("say prayer of balm")  # answered once, never again
    assert "smooth and unlettered" in " ".join(cap.texts(Channel.BLOCKED))
    cap2 = _texts(game)
    game.do_command("read prayers")
    assert "BALM" in " ".join(cap2.texts(Channel.NARRATION))  # named as spent


def test_the_wrath_prayer_strikes_the_horror():
    """WRATH is a blow: it chips the Horror's vigor mid-fight, and as the
    final blow it kills through the engine's KO contract. Without a target
    it is refused, unspent."""
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    game.relocate(game.player, sphere)
    cap = _texts(game)
    game.do_command("say prayer of wrath")  # nothing to smite: refused
    assert "nothing before you" in " ".join(cap.texts(Channel.BLOCKED))
    horror = game.characters["fungal horror"]
    game.relocate(horror, sphere)
    horror.set_property("vigor", 3)
    game.do_command("say prayer of wrath")
    # one blow landed (the Horror knits +1 on its own turn, acid answers)
    assert "smaller than it was" in " ".join(cap.texts(Channel.NARRATION))
    assert not horror.get_property("is_dead")
    game.do_command("say prayer of wrath")  # once only
    assert "smooth and unlettered" in " ".join(cap.texts(Channel.BLOCKED))


def test_the_wrath_prayer_can_land_the_final_blow():
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    game.relocate(game.player, sphere)
    horror = game.characters["fungal horror"]
    game.relocate(horror, sphere)
    horror.set_property("vigor", 1)
    game.do_command("say prayer of wrath")
    assert horror.get_property("is_dead")  # horror_struck converts the KO
    assert sphere.get_property("horror_dead")
    assert game.score >= 25  # the Horror bounty pays either way


def test_the_mending_prayer_restores_the_coffin():
    """MENDING re-seals the burst coffin (CCB): pried becomes whole, the
    descriptions follow, and an unbroken coffin refuses the prayer."""
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    game.relocate(game.player, sphere)
    cap = _texts(game)
    game.do_command("say prayer of mending")  # nothing broken yet
    assert "The coffin is whole" in " ".join(cap.texts(Channel.BLOCKED))
    sphere.set_property("horror_dead", True)
    coffin = sphere.items["coffin"]
    coffin.set_property("pried", True)
    game.do_command("say prayer of mending")
    assert coffin.get_property("pried") is False
    assert "whole" in coffin.examine_text
    assert "whole again" in sphere.description
    assert "hangs whole" in " ".join(cap.texts(Channel.NARRATION))


def test_prayers_listen_only_in_the_sphere():
    game = _game()
    cap = _texts(game)
    game.do_command("say prayer of balm")  # at the wreck: nothing carved
    assert "Burial Sphere" in " ".join(cap.texts(Channel.BLOCKED))


def test_open_grammar_agrees_in_number():
    """'The crates ARE open' (CCB) -- and heads of 'of' phrases stay
    singular ('crate of dates')."""
    game = _game()
    for cmd in ("search merchant", "take glowstone", "light glowstone", "in"):
        game.do_command(cmd)
    cap = _texts(game)
    game.do_command("open crates")
    assert "The crates are open." in " ".join(cap.texts(Channel.NARRATION))
    game.do_command("open crates")
    assert "The crates are already open." in " ".join(cap.texts(Channel.BLOCKED))
    crates = game.locations["The Wagon's Hold"].items["crates"]
    assert crates.to_be() == "are"
    assert crates.contents["crate of dates"].to_be() == "is"


def test_death_closes_the_parser_to_all_but_the_meta_verbs():
    """The dead do not walk (CCB): once the game is over, every world
    command is refused with the RESTORE/RESTART hint; only the meta verbs
    that leave the ended story intact still answer."""
    game = _game()
    game.do_command("north")
    from text_adventure_games.slots import Wound

    game.player.add_wound(Wound("Bloody Gash", 1, "..."))
    game.player.set_property("is_dead", True)
    assert game.is_game_over()
    cap = _texts(game)
    here = game.player.location.name
    turn = game.turn
    game.do_command("go south")
    assert game.player.location.name == here  # the corpse stays put
    assert game.turn == turn  # and time does not pass for it
    blocked = " ".join(cap.texts(Channel.BLOCKED))
    assert "Death has this expedition now" in blocked
    assert "RESTORE" in blocked and "RESTART" in blocked
    game.do_command("look")  # the living's verbs are refused
    assert game.player.location.name == here
    cap_inv = _texts(game)
    game.do_command("inventory")  # ...but the final ledger stays readable
    assert "Wounds" in " ".join(cap_inv.texts(Channel.NARRATION))
    cap2 = _texts(game)
    game.do_command("script")  # the record survives the death
    assert "north" in " ".join(cap2.texts(Channel.NARRATION))


def test_minor_threats_pay_when_quelled_by_any_means():
    """+5 per spawn down and +5 for the pack settled (CCB) -- and the
    tribute route earns the jackal points just as surely as steel."""
    game = _game()
    _sate_pack(game)  # the tribute path: ledgers at deep peace
    game.do_command("look")  # a round for the score trigger
    assert game.scored("jackals_settled")
    guts = game.characters["spawn of guts"]
    guts.set_property("is_unconscious", True)  # a blade's KO counts
    brain = game.characters["spawn of brain"]
    brain.set_property("is_dead", True)  # so does the bat-swarm's kill
    before = game.score
    game.do_command("look")
    assert game.scored("spawn_guts") and game.scored("spawn_brain")
    assert game.score == before + 10
    assert game.max_score == 170


def test_the_pack_answers_to_pack():
    """'give dates to pack' (CCB's transcript) must find the jackals -- the
    tribute changes hands and buys the deep peace."""
    game = _game()
    for cmd in (
        "search merchant",
        "take glowstone",
        "light glowstone",
        "in",
        "open crates",
        "take crate of dates",
        "out",
        "north",
    ):
        game.do_command(cmd)
    pack = game.characters["jackal pack"]
    game.relocate(pack, game.player.location)
    game.do_command("give dates to pack")
    assert "crate of dates" not in game.player.carried_items()
    assert "crate of dates" in pack.inventory or not pack.inventory.get(
        "crate of dates"
    )  # taken (and possibly already devoured by the tribute trigger)


def test_taste_is_the_cautious_cousin_of_eat():
    """TASTE/LICK (CCB): reads flavor and function, verdicts edibility, and
    never consumes -- and 'taste crate of dates' must not be swallowed by
    the EAT keyword ('ate ' lives inside 'crate')."""
    game = _game()
    for cmd in (
        "search merchant",
        "take waterskin",
        "take glowstone",
        "light glowstone",
        "in",
        "open crates",
        "take crate of dates",
    ):
        game.do_command(cmd)
    cap = _texts(game)
    game.do_command("taste crate of dates")
    text = " ".join(cap.texts(Channel.NARRATION))
    assert "honey and sun" in text  # the flavor
    assert "But you could eat it." in text  # the edibility verdict
    assert "crate of dates" in game.player.carried_items()  # NOT eaten
    game.do_command("lick glowstone")  # the alias -- and CCB's battery
    assert "nine-volt battery" in " ".join(cap.texts(Channel.NARRATION))
    cap2 = _texts(game)
    game.do_command("taste waterskin")
    assert "wealth goes" in " ".join(cap2.texts(Channel.NARRATION))
    game.do_command("out")
    teamster = next(  # the newbeast's name is rolled per seed
        c for c in game.player.location.characters.values() if c is not game.player
    )
    cap3 = _texts(game)
    game.do_command(f"lick {teamster.name}")
    assert "not going to lick" in " ".join(cap3.texts(Channel.NARRATION))


def test_every_organ_keeps_its_own_taste():
    """Each canopic organ tastes distinct (CCB) -- the intestines taste of
    OFFAL -- and an open jar standing on a plinth is still within reach of
    the tongue (parser scope recurses through nested open holders)."""
    game = _game()
    canopic = game.locations["Hall of the Canopic Jars"]
    brain_spawn = game.characters["spawn of brain"]
    jar = brain_spawn.inventory["jackal jar"]
    brain_spawn.remove_from_inventory(jar)
    plinth = canopic.items["jackal plinth"]
    plinth.add_item(jar)  # jar ON plinth, brain IN jar: two holders deep
    game.relocate(game.player, canopic)
    game.do_command("open jackal jar")  # reachable through the plinth too
    cap = _texts(game)
    game.do_command("taste brain")
    assert "resin and long memory" in " ".join(cap.texts(Channel.NARRATION))
    # and the coil (CCB: 'the intestines should taste offal')
    falcon = next(
        it
        for c in game.characters.values()
        for it in list(c.inventory.values()) + list(c.worn.values())
        if it.name == "falcon jar"
    )
    assert "of offal" in falcon.contents["intestines"].get_property("taste")


def test_fix_coffin_rehouses_the_king_and_renews_the_prayers():
    """FIX COFFIN (CCB): shards + bones + silk + the anti-entropy field =
    a whole coffin with the Autarch home in it; the chamber re-cuts every
    spent prayer and adds the Prayer of Peaceful Slumber."""
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    coffin = sphere.items["coffin"]
    coffin.set_property("pried", True)
    game.relocate(game.player, sphere)
    cap = _texts(game)
    game.do_command("fix coffin")  # the Horror still lives: refused
    assert "starts with the Horror's ending" in " ".join(cap.texts(Channel.BLOCKED))
    sphere.set_property("horror_dead", True)
    tomb._sphere_aftermath(game, ash=True)  # bones adrift, ash hanging
    game.do_command("fix coffin")  # no silk, no lashing: refused
    assert "Silk" in " ".join(cap.texts(Channel.BLOCKED))
    hold = game.locations["The Wagon's Hold"]
    silk = hold.items["crates"].contents["bolt of spider-silk"]
    hold.items["crates"].remove_item(silk)
    game.player.add_to_inventory(silk)
    prayers = sphere.items["prayers"]
    prayers.set_property("balm_spent", True)
    prayers.set_property("wrath_spent", True)
    cap2 = _texts(game)
    game.do_command("fix coffin")
    text = " ".join(cap2.texts(Channel.NARRATION))
    assert "glass eggshell" in text and "PRAYER OF PEACEFUL SLUMBER" in text
    assert coffin.get_property("pried") is False and coffin.get_property("fixed")
    assert "Autarch's bones" not in sphere.items  # re-housed
    assert "bolt of spider-silk" not in game.player.carried_items()  # spent
    assert not prayers.get_property("balm_spent")  # the chamber re-cut them
    assert not prayers.get_property("wrath_spent")
    assert prayers.get_property("slumber_known")
    cap3 = _texts(game)
    game.do_command("read prayers")
    assert "PEACEFUL SLUMBER" in " ".join(cap3.texts(Channel.NARRATION))


def test_the_slumber_prayer_wants_a_housed_king():
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    game.relocate(game.player, sphere)
    cap = _texts(game)
    game.do_command("say prayer of peaceful slumber")  # not carved yet
    assert "No such line is carved here" in " ".join(cap.texts(Channel.BLOCKED))
    # fix via the OLD LASHING (no silk in hand): the tie serves twice
    coffin = sphere.items["coffin"]
    coffin.set_property("pried", True)
    coffin.set_property("tethered", True)
    sphere.set_property("horror_dead", True)
    tomb._sphere_aftermath(game, ash=False)
    cap2 = _texts(game)
    game.do_command("fix coffin")
    assert "gentler purpose" in " ".join(cap2.texts(Channel.NARRATION))
    game.do_command("say prayer of slumber")
    assert "dreaming something kind" in coffin.examine_text  # beatific
    game.do_command("say prayer of slumber")  # answered once
    assert "smooth and unlettered" in " ".join(cap2.texts(Channel.BLOCKED))


def test_the_core_buys_the_robes():
    """GIVE CORE TO SILAS (CCB): the item's own tease honored -- the robes
    change hands, the archivist gets his ending, and +5 marks it."""
    game = _game()
    _sate_pack(game)
    silas = game.characters["Silas"]
    memory = game.locations["Hall of Memory"]
    game.relocate(game.player, memory)
    # run the whole chain by hand: fungus -> lantern -> core -> trade
    corpse = game.locations["The Summit"].items["ossified corpse"]
    fungus = corpse.contents["friend's fungus"]
    corpse.remove_item(fungus)
    game.player.add_to_inventory(fungus)
    game.do_command("give fungus to silas")
    assert "ulfire lantern" in game.player.inventory  # the mellowed gift
    box = (
        game.locations["Burial Sphere of Nassak An-Rah"]
        .items["coffin"]
        .contents["manifold box"]
    )
    game.player.add_to_inventory(box)
    cap = _texts(game)
    game.do_command("light ulfire lantern")
    reveal = " ".join(cap.texts(Channel.NARRATION))
    assert "ego-core" in game.player.inventory
    assert "hall" in reveal and "television static" in reveal  # hypergeometry
    before = game.score
    cap2 = _texts(game)
    game.do_command("give core to silas")
    text = " ".join(cap2.texts(Channel.NARRATION))
    assert "handed me the author" in text
    assert "yellow monk's robes" in game.player.carried_items()
    assert game.score == before + 5 and game.scored("archivist")
    game.do_command("wear robes")
    assert "yellow monk's robes" in game.player.worn
    cap3 = _texts(game)
    game.do_command("talk to silas")
    assert "practicing goodbye" in " ".join(cap3.texts(Channel.NARRATION))


def test_a_lick_of_friends_fungus_is_a_microdose():
    """The fungus's taste rehearses its whole function (CCB): the agreeable
    warmth in miniature, a nudge toward giving it away -- and the pouch
    survives the tasting."""
    game = _game()
    corpse = game.locations["The Summit"].items["ossified corpse"]
    fungus = corpse.contents["friend's fungus"]
    corpse.remove_item(fungus)
    game.player.add_to_inventory(fungus)
    cap = _texts(game)
    game.do_command("lick fungus")
    text = " ".join(cap.texts(Channel.NARRATION))
    assert "mean well" in text  # the effect, in miniature
    assert "someone lonelier" in text  # the hint at what it is FOR
    assert "friend's fungus" in game.player.carried_items()  # not consumed


def test_drinking_water_mends_a_wound():
    game = _game()
    game.do_command("search merchant")
    game.do_command("take glowstone")
    game.do_command("take waterskin")
    from text_adventure_games.slots import Wound

    game.player.add_wound(Wound("Bloody Gash", 1, "..."))
    cap = _texts(game)
    game.do_command("drink water")
    assert not game.player.wounds  # the glug of water mends
    assert "a wound heals" in " ".join(cap.texts(Channel.NARRATION)).lower()


def test_overloaded_scavenger_cannot_make_the_climb():
    game = _game()
    _sate_pack(game)  # this test is about slots, not jackals
    cap = _texts(game)
    # Greed: haul all the cargo out of the hold, then try the tomb face.
    for cmd in (
        "in",
        "open crates",
        "take bale of saffron",
        "take crate of dates",
        "take bolt of spider-silk",
        "out",
    ):
        game.do_command(cmd)
    game.do_command("search merchant")
    game.do_command("take glowstone")
    game.do_command("take waterskin")
    # blade would be next, but the cargo alone is 5 slots -- go check the climb
    game.do_command("north")
    # load up past 10: smash out the blade and boots (takes between breaks
    # keep the pack's suspicion at one)
    game.do_command("sneak east")
    for cmd in (
        "break cerulean cylinder",
        "take blade",
        "break viridian cylinder",
        "take boots",
    ):
        game.do_command(cmd)
    assert game.player.is_encumbered()
    game.do_command("west")
    game.do_command("up")  # the climb to the Summit
    assert game.player.location.name == "Tomb Exterior"
    assert (
        "climb is out of the question"
        in " ".join(cap.texts(Channel.NARRATION) + cap.texts(Channel.BLOCKED)).lower()
    )


def test_the_climb_out_of_the_sphere_refuses_a_full_pack():
    """CCB playtest: an encumbered player floated freely from the sphere UP
    into the chimney, only to be refused at the chimney's own climb. The
    hauling starts at the sphere's crown -- the gate belongs there too."""
    from text_adventure_games.slots import Wound

    game = _game()
    sphere = _boss_setup(game)  # boots worn; blade, igniter, gel carried
    assert not game.player.is_encumbered()
    game.do_command("up")  # unencumbered: the climb is fine
    assert game.player.location.name == "The Fungal Chimney"
    game.do_command("down")
    while not game.player.is_encumbered():
        game.player.add_wound(Wound("Test-Weight", 2, "ballast"), rng=None)
    cap = _texts(game)
    game.do_command("up")
    assert game.player.location is sphere  # refused at the crown
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
        "break orange cylinder",  # unmasked: costs a Seared Lungs wound
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


def _hand(game, room, cylinder, item_name):
    cyl = game.locations[room].items[cylinder]
    it = cyl.contents[item_name]
    cyl.remove_item(it)
    game.player.add_to_inventory(it)
    return it


def test_prying_the_coffin_needs_an_anchor_and_a_blade_it_will_lose():
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    sphere.set_property("horror_dead", True)  # pretend it's cleansed
    game.relocate(game.player, sphere)
    game.do_command("pry coffin")  # no anchor -> you drift
    assert sphere.items["coffin"].get_property("pried") in (False, None)
    _hand(game, "Hall of Warriors", "viridian cylinder", "magnetic boots")
    game.do_command("wear boots")
    game.do_command("pry coffin")  # anchored but no lever -> refused
    assert sphere.items["coffin"].get_property("pried") in (False, None)
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.do_command("pry coffin")  # anchored + blade -> it gives; the blade snaps
    assert sphere.items["coffin"].get_property("pried")
    assert "synth-hunting dagger" in sphere.items
    assert "prismatic blade" not in game.player.carried_items()


def test_any_honest_edge_pries_the_coffin():
    """The seam wants an edge, not a pedigree (CCB): the centipede's
    crystal shard -- a knife by any honest measure -- opens the coffin,
    and it is the shard that snaps, not some other carried blade."""
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    sphere.set_property("horror_dead", True)
    game.relocate(game.player, sphere)
    _hand(game, "Hall of Warriors", "viridian cylinder", "magnetic boots")
    game.do_command("wear boots")
    shard = game.locations["Tomb Exterior"]  # forge the knife by hand
    from text_adventure_games import things
    edge = things.Item("crystal shard", "a shard", "A knife by any honest measure.")
    edge.set_property("gettable", True)
    edge.set_property("edged", True)
    edge.add_alias("shard")
    game.player.add_to_inventory(edge)
    game.do_command("pry open coffin with shard")
    assert sphere.items["coffin"].get_property("pried")
    assert "crystal shard" not in game.player.carried_items()
    assert "synth-hunting dagger" in sphere.items


def test_the_named_lever_is_the_one_that_snaps():
    """Carrying both, 'pry coffin with shard' spends the shard and the
    prismatic blade survives; bare 'pry coffin' also prefers the shard
    (the cheapest edge goes first, the Exotica dagger last of all)."""
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    sphere.set_property("horror_dead", True)
    game.relocate(game.player, sphere)
    _hand(game, "Hall of Warriors", "viridian cylinder", "magnetic boots")
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.do_command("wear boots")
    from text_adventure_games import things
    edge = things.Item("crystal shard", "a shard", "A knife by any honest measure.")
    edge.set_property("gettable", True)
    edge.set_property("edged", True)
    edge.add_alias("shard")
    game.player.add_to_inventory(edge)
    game.do_command("pry coffin with shard")
    assert sphere.items["coffin"].get_property("pried")
    assert "crystal shard" not in game.player.carried_items()
    assert "prismatic blade" in game.player.carried_items()


def test_the_spider_silk_tether_is_the_bootless_anchor():
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    sphere.set_property("horror_dead", True)
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.do_command("in")
    game.do_command("open crates")
    game.do_command("take silk")
    game.do_command("out")
    game.relocate(game.player, sphere)
    cap = _texts(game)
    game.do_command("tie silk to coffin")
    assert sphere.items["coffin"].get_property("tethered")
    assert "holds like law" in " ".join(cap.texts(Channel.NARRATION))
    game.do_command("pry coffin")  # tethered, no boots
    assert sphere.items["coffin"].get_property("pried")


def _boss_setup(game):
    """Anchor, blade, gel, and spark -- straight to the sphere. The jar
    puzzle is treated as solved (the seal now bars BOTH directions, and a
    fleeing fighter needs the stair)."""
    game.locations["Hall of the Canopic Jars"].set_property("seal_open", True)
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    _hand(game, "Hall of Warriors", "viridian cylinder", "magnetic boots")
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    _hand(game, "Hall of Warriors", "orange cylinder", "plasma-igniter")
    gel = game.locations["Hall of Hounds"].items["flask of gel"]
    game.locations["Hall of Hounds"].remove_item(gel)
    game.player.add_to_inventory(gel)
    game.relocate(game.player, sphere)
    game.do_command("wear boots")
    return sphere


def test_checking_inventory_is_a_free_action():
    """The list is for the player, not the character: INVENTORY reports
    without advancing the round -- no boss turn, no acid, no turn tick."""
    game = _game()
    _boss_setup(game)
    game.do_command("pry coffin")  # the fight is on
    wounds, turn = game.player.wound_slots(), game.turn
    for _ in range(5):
        game.do_command("i")  # read your own ledger freely
    assert game.player.wound_slots() == wounds
    assert game.turn == turn
    game.do_command("wait")  # but a real action still bleeds
    assert game.player.wound_slots() == wounds + 1


def test_prying_the_live_coffin_wakes_the_boss():
    game = _game()
    sphere = _boss_setup(game)
    cap = _texts(game)
    game.do_command("pry coffin")  # the eruption -- not a death
    assert not game.is_game_over()
    assert "fungal horror" in sphere.characters
    assert "prismatic blade" in game.player.carried_items()  # the blade survives
    assert "synth-hunting dagger" not in sphere.items  # kept in its coil
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "From among the shattered glass" in out  # glass fractures; no bulging


def test_steel_alone_is_a_stalemate_and_fire_breaks_it():
    """The boss lesson (design doc §17.3): a hit costs 1 vigor, its turn knits
    1 back -- until it burns."""
    game = _game()
    sphere = _boss_setup(game)
    game.do_command("pry coffin")
    horror = game.characters["fungal horror"]
    game.do_command("attack horror with blade")
    assert horror.get_property("vigor") == 5  # -1 hit, +1 knit: nowhere
    cap = _texts(game)
    game.do_command("burn horror")  # ablaze: nothing knits
    out = " ".join(cap.texts(Channel.NARRATION))
    # Concrete narration: the liquid, the target, the tool in hand (CCB).
    assert "embalming gel" in out
    assert "plasma-igniter" in out
    # The player watched it mend, so the fire's meaning is earned knowledge.
    assert "the mending stops" in out
    game.do_command("attack horror with blade")  # -1 hit, -1 burn
    game.do_command("attack horror with blade")  # -1 hit, -1 burn -> 0
    assert horror.get_property("is_dead")
    assert "synth-hunting dagger" in sphere.items  # the coil unclenches
    assert not game.is_game_over()  # hurt, but standing
    assert game.player.wound_slots() >= 3  # the acid kept the ledger


def test_thrown_gel_douses_the_horror_for_a_spark_alone():
    """CCB's instinctive sequence, legitimized: throw gel at horror (it has no
    hands -- the flask bursts and drifts free), then burn with the spark alone."""
    game = _game()
    sphere = _boss_setup(game)
    game.do_command("pry coffin")
    horror = game.characters["fungal horror"]
    game.do_command("throw gel at horror")  # the short alias works too
    assert horror.get_property("gel_doused")
    assert "flask of gel" in sphere.items  # deflected, not caught
    game.do_command("light gel")  # the dose is ON it: identical to burn horror
    assert int(horror.get_property("ablaze") or 0) > 0
    game.do_command("attack horror with blade")
    game.do_command("attack horror with blade")
    assert horror.get_property("is_dead")


def test_the_fire_burns_whether_or_not_you_watch():
    """CCB's playtest: he lit the Horror, then spent the window shuttling gear
    two rooms away -- and the fire politely waited for him. It must not: douse,
    light, and RUN is a legitimate tactic. And when the window closes, it
    closes audibly, never silently back to knitting."""
    game = _game()
    _boss_setup(game)
    game.do_command("pry coffin")
    horror = game.characters["fungal horror"]
    game.do_command("burn horror")  # lit: one burn tick already taken
    burned_to = horror.get_property("vigor")
    game.do_command("down")  # flee -- the fire keeps working
    assert horror.get_property("vigor") == burned_to - 1
    cap = _texts(game)
    game.do_command("wait")  # the last ablaze round, spent elsewhere
    assert horror.get_property("vigor") == burned_to - 2
    assert int(horror.get_property("ablaze") or 0) == 0
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "roar of fire dies away" in out  # the window closes audibly
    game.do_command("wait")  # and with the fire out, the knitting resumes
    assert horror.get_property("vigor") == burned_to - 1


def test_the_fire_guttering_out_is_announced_to_your_face():
    """Standing in the sphere when ablaze expires, you are told plainly that
    the window has shut -- the knit/burn state change is never silent."""
    game = _game()
    _boss_setup(game)
    game.do_command("pry coffin")
    game.do_command("burn horror")
    cap = _texts(game)
    game.do_command("attack horror with blade")
    game.do_command("wait")  # third and last ablaze round
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "fire gutters out" in out
    assert "What is cut can mend again" in out


def test_the_sphere_becomes_the_fights_record():
    """CCB: after the boss dies, the room should hold the story -- dropped
    gear, the Autarch's bones, the released grave-goods, the shattered
    coffin, the Horror's ash -- and the description must stop lighting the
    room with a churn that no longer exists."""
    game = _game()
    sphere = _boss_setup(game)
    game.do_command("pry coffin")
    # The eruption already re-writes the room: the coffin is shards, and the
    # light is the Horror itself.
    assert "burst coffin" in sphere.description
    assert "orange churn" not in (sphere.dim_description or "")
    game.do_command("burn horror")
    game.do_command("drop flask")  # gear dropped mid-fight stays put
    game.do_command("attack horror with blade")
    game.do_command("attack horror with blade")
    assert game.characters["fungal horror"].get_property("is_dead")
    # The remains are an OBJECT, not a listed combatant.
    assert "fungal horror" not in sphere.characters
    assert "drift of ash" in sphere.items
    assert "Autarch's bones" in sphere.items
    assert "synth-hunting dagger" in sphere.items  # the released goods
    assert "flask of gel" in sphere.items  # the dropped gear
    assert "shattered" in sphere.items["coffin"].description
    assert "quiet in a way it has not been" in sphere.description
    # And the wreckage is scenery, not loot for the slot ledger.
    game.do_command("get bones")
    assert "Autarch's bones" in sphere.items


def test_the_quiet_coffin_when_the_root_dies_first():
    """Burn the corpse at the Summit before ever prying: the churn behind
    the glass goes still, and the sphere's description follows (CCB: no
    stale light sources)."""
    game = _game()
    _hand(game, "Hall of Warriors", "orange cylinder", "plasma-igniter")
    gel = game.locations["Hall of Hounds"].items["flask of gel"]
    game.locations["Hall of Hounds"].remove_item(gel)
    game.player.add_to_inventory(gel)
    game.relocate(game.player, game.locations["The Summit"])
    game.do_command("burn corpse")
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    assert "still now" in sphere.description
    assert "slow orange churn" not in sphere.dim_description


def test_the_fires_meaning_is_only_told_to_those_who_saw_it_mend():
    """Burn the Horror before ever watching it knit and the narration keeps
    its counsel -- no unearned "the mending stops" (CCB: no hints like that).
    The regeneration lesson must be learned by watching, not from the fire."""
    game = _game()
    _boss_setup(game)
    game.do_command("pry coffin")
    cap = _texts(game)
    game.do_command("burn horror")  # first act: it has never knit in view
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "embalming gel" in out and "plasma-igniter" in out
    assert "the mending stops" not in out


def test_burning_the_root_mid_fight_fells_the_horror():
    game = _game()
    sphere = _boss_setup(game)
    game.do_command("pry coffin")
    # Flee the fight and burn the corpse at the Summit instead.
    game.relocate(game.player, game.locations["The Summit"])
    cap = _texts(game)
    game.do_command("burn corpse")
    assert game.characters["fungal horror"].get_property("is_dead")
    assert "collapses mid-motion" in " ".join(cap.texts(Channel.NARRATION))
    # The coil's keeping ends with it: the loot it held since the eruption
    # is in the sphere, not sealed forever inside the coffin item.
    assert "synth-hunting dagger" in sphere.items
    assert "manifold box" in sphere.items


def _sate_pack(game):
    """Deep post-feed grace: for tests about other mechanics entirely, whose
    noise would now ring the song and summon the pack mid-setup."""
    for hall in ("Hall of Memory", "Hall of Hounds", "Hall of Warriors"):
        game.locations[hall].set_property(f"_jk:{hall}", -99)


def _summon_pack(game):
    """Quietly reach Memory, then shout the pack into the room."""
    _no_spawn(game)
    _embark(game, glowstone=False)
    for cmd in (
        "sneak north",
        "sneak north",
        "say hey",  # the shout AND the song it wakes: +2
        "say hey",  # +2 again -- the pack enters (and grants its grace round)
    ):
        game.do_command(cmd)
    assert game.characters["jackal pack"].location.name == "Hall of Memory"


def test_the_pack_pursues_by_sight_and_scent():
    """Sneaking means nothing to scent: once out, the pack tracks you through
    its territory at a lope-and-rest rhythm -- keep moving and you hold your
    lead; stop, and they collect."""
    tomb._RNG.seed(0)
    game = _game()
    _summon_pack(game)
    pack = game.characters["jackal pack"]
    game.do_command("sneak north")  # flee (silently!) to Warriors
    assert pack.location.name == "Hall of Memory"  # first beat: hang back
    game.do_command("sneak east")  # keep moving to Hounds
    assert pack.location.name == "Hall of Warriors"  # one room behind
    wounds = game.player.wound_slots()
    game.do_command("wait")  # stop: they rest...
    game.do_command("wait")  # ...close...
    game.do_command("wait")  # ...and collect
    assert pack.location.name == "Hall of Hounds"
    assert game.player.wound_slots() > wounds


def test_the_youth_is_a_refuge_from_the_pack():
    game = _game()
    _summon_pack(game)
    cap = _texts(game)
    game.do_command("south")  # into the Hall of Youth
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "comes no further" in out
    assert game.characters["jackal pack"].location.name == "Shallow Dens"


def test_the_dead_dont_sway_in_the_listings():
    """A felled creature's one-liner goes still (CCB): state-aware
    visible_description replaces the lively text."""
    game = _game()
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    for cmd in ("search merchant", "take glowstone", "light glowstone"):
        game.do_command(cmd)
    game.relocate(game.player, game.locations["Hall of Warriors"])
    game.do_command("attack spawn of guts with blade")
    cap = _texts(game)
    game.do_command("look")
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "collapsed in a heap" in out
    assert "swaying toward every sound" not in out


def test_remember_asks_the_lattice_by_name():
    """REMEMBER <day> (CCB): directed recall -- the jar clue is findable by
    name the moment Silas points at it, no dice required."""
    game = _game()
    game.relocate(game.player, game.locations["Hall of Memory"])
    cap = _texts(game)
    game.do_command("remember the embalming")
    text = " ".join(cap.texts(Channel.NARRATION))
    assert "the jackal -- strangely -- his brain" in text  # the clue, on demand
    assert game.scored("lattice")  # the first-look award pays either way
    game.do_command("remember")  # bare: the consulted banks, by name
    assert "THE EMBALMING" in " ".join(cap.texts(Channel.BLOCKED))
    game.do_command("remember the choosing")  # hidden until earned
    assert "has not shown it to you" in " ".join(cap.texts(Channel.BLOCKED))
    game.relocate(game.player, game.locations["The Caravan Wreck"])
    cap2 = _texts(game)
    game.do_command("remember his mother")  # no lattice here
    assert "Hall of Memory" in " ".join(cap2.texts(Channel.BLOCKED))


def test_every_day_consulted_wakes_the_keep_list():
    """Unseen facets draw first, so nine looks cover the nine -- and the
    tenth wakes the hidden keep-list exactly once (+5)."""
    game = _game()
    game.relocate(game.player, game.locations["Hall of Memory"])
    cap = _texts(game)
    for _ in range(9):
        game.do_command("x lattice")
    seen = " ".join(cap.texts(Channel.NARRATION))
    for marker in ("embalming", "kestrel", "tombwrights", "starlight"):
        assert marker in seen  # coverage, not luck
    before = game.score
    cap2 = _texts(game)
    game.do_command("x lattice")  # the tenth
    tenth = " ".join(cap2.texts(Channel.NARRATION))
    assert "KEEP THIS TOO" in tenth and "KNOWS I KNEW" in tenth
    assert game.scored("remembered") and game.score == before + 5
    game.do_command("x lattice")  # afterwards: the lattice's own whim again
    assert game.score == before + 5  # paid once
    cap3 = _texts(game)
    game.do_command("remember the choosing")  # now it answers by name
    assert "THE DAY I CHOSE" in " ".join(cap3.texts(Channel.NARRATION))


def test_the_facets_notice_what_the_expedition_has_done():
    """The continuations (CCB): a facet re-read after events gains its
    postscript -- the lattice is the tomb's commentary track."""
    game = _game()
    game.relocate(game.player, game.locations["Hall of Memory"])
    cap = _texts(game)
    game.do_command("remember the physician")
    assert "corrected" not in " ".join(cap.texts(Channel.NARRATION))
    game.locations["Burial Sphere of Nassak An-Rah"].set_property("horror_dead", True)
    cap2 = _texts(game)
    game.do_command("remember the physician")
    assert "You have since corrected that." in " ".join(cap2.texts(Channel.NARRATION))
    game.locations["Hall of the Canopic Jars"].has_been_visited = True
    cap3 = _texts(game)
    game.do_command("remember the embalming")
    assert "telling you where things go" in " ".join(cap3.texts(Channel.NARRATION))


def test_the_lattice_shows_a_different_memory_each_look():
    """CCB: looking into the lattice draws a random facet of the Autarch's
    days, not always the embalming -- but the embalming (the jar-puzzle clue)
    stays in the pool, findable by whoever troubles to look."""
    game = _game()
    tomb._RNG.seed(4)
    game.relocate(game.player, game.locations["Hall of Memory"])
    cap = _texts(game)
    for _ in range(8):
        game.do_command("x lattice")
    looks = [t for t in cap.texts(Channel.NARRATION) if "Lazulite" in t]
    assert len(set(looks)) >= 3  # variety across looks
    assert any("embalming" in m for m in tomb._LATTICE_MEMORIES)  # clue kept


def test_breaking_the_lattice_yields_a_shard_and_silass_wrath():
    """CCB: BREAK LATTICE -> a memory shard, and an archivist who attacks
    and keeps attacking -- through every hall, every round."""
    game = _game()
    memory = game.locations["Hall of Memory"]
    game.relocate(game.player, memory)
    cap = _texts(game)
    game.do_command("break lattice")
    assert "memory shard" in memory.items
    assert game.characters["Silas"].get_property("wrathful")
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "EVERYONE'S" in out
    game.do_command("take shard")
    game.do_command("x shard")  # while there's light to read it by
    assert "One facet still plays" in " ".join(cap.texts(Channel.NARRATION))
    game.do_command("go south")  # flee: he honors no territory
    game.do_command("wait")
    assert game.characters["Silas"].location is game.player.location
    assert any(w.name == "Bore-Struck" for w in game.player.wounds)


def test_a_dead_archivist_holds_no_grudge():
    game = _game()
    memory = game.locations["Hall of Memory"]
    game.relocate(game.player, memory)
    game.characters["Silas"].set_property("is_dead", True)
    game.do_command("break lattice")
    assert "memory shard" in memory.items
    assert not game.characters["Silas"].get_property("wrathful")


def test_silas_answers_on_his_subjects():
    """CCB: ASK SILAS ABOUT memories/lattice/crystal explains what the
    memories are; about himself/robes, why he is there (a mendicant of the
    Seekers, in yellow monk's robes)."""
    game = _game()
    game.relocate(game.player, game.locations["Hall of Memory"])
    cap = _texts(game)
    game.do_command("ask silas about the memories")
    game.do_command("ask silas about his robes")
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "memory-crystal" in out and "could not buy or take by conquest" in out
    assert "Seekers of Eyeless Wisdom" in out and "yellow" in out
    game.do_command("x silas")
    assert "yellow monk's robes" in " ".join(cap.texts(Channel.NARRATION))


def test_the_whole_tomb_is_dark_without_a_light():
    """CCB: every interior hall wants a carried light. The ground halls'
    own glows (tank, plinths, lattice) make them GLOOM -- dim description,
    contents unlisted -- until a lit glowstone changes everything."""
    game = _game()
    cap = _texts(game)
    for hall, tell in (
        ("Hall of Memory", "each point a day someone else lived"),
        ("Hall of Hounds", "lit only by the tank"),
        ("Hall of the Canopic Jars", "like coals in a cold room"),
    ):
        game.relocate(game.player, game.locations[hall])
        game.do_command("look")
        out = " ".join(cap.texts(Channel.NARRATION))
        assert tell in out, hall
    # Contents are shapes, not listings: the jars are not itemized unlit.
    assert "baboon-headed canopic jar" not in " ".join(cap.texts(Channel.NARRATION))
    # A lit glowstone restores the full hall.
    merchant = game.locations["The Caravan Wreck"].items["dead merchant"]
    stone = merchant.contents["glowstone"]
    merchant.remove_item(stone)
    game.player.add_to_inventory(stone)
    game.do_command("light glowstone")
    game.do_command("look")
    assert "baboon-headed canopic jar" in " ".join(cap.texts(Channel.NARRATION))


def test_the_canopic_hall_reads_its_own_progress():
    """CCB: 'two stand empty' must not outlive the truth. The room tracks
    occupancy, the per-plinth verdict, and the seal -- in the same round."""
    game = _game()
    canopic = game.locations["Hall of the Canopic Jars"]
    game.relocate(game.player, canopic)
    assert "two stand empty" in canopic.description
    for spawn, jar in (
        ("spawn of guts", "falcon jar"),
        ("spawn of brain", "jackal jar"),
    ):
        it = game.characters[spawn].inventory[jar]
        game.characters[spawn].remove_from_inventory(it)
        game.player.add_to_inventory(it)
    game.do_command("put falcon jar on falcon plinth")
    assert "the fifth stands empty" in canopic.description
    assert "One of the restored lights has turned white" in canopic.description
    game.do_command("put jackal jar on jackal plinth")
    assert "none stands empty" in canopic.description
    assert "a red glitter remains on the treads" in canopic.description
    assert "barred" not in canopic.description
    # The listener leaves with the mantis jar.
    game.do_command("take mantis jar")
    game.do_command("wait")
    assert "listening" not in canopic.description


def test_the_plinths_read_true():
    """CCB: 'empty' only while empty -- and a plinth knows its own jar:
    the wrong jar reads crimson-unconvinced, the right one goes white."""
    game = _game()
    canopic = game.locations["Hall of the Canopic Jars"]
    game.relocate(game.player, canopic)
    fp = canopic.items["falcon plinth"]
    assert fp.description == "an empty plinth carved with a falcon"
    game.do_command("take baboon jar")
    game.do_command("put baboon jar on falcon plinth")  # the wrong jar
    assert fp.description == "a falcon-carved plinth, its jar seated"
    assert "wrong mouth" in fp.examine_text()
    game.do_command("take baboon jar")
    # Hand the true jar over directly (in play it rides on a spawn).
    jar = game.characters["spawn of guts"].inventory["falcon jar"]
    game.characters["spawn of guts"].remove_from_inventory(jar)
    game.player.add_to_inventory(jar)
    game.do_command("put falcon jar on falcon plinth")
    game.do_command("wait")
    assert "reads as finished" in fp.examine_text()


def test_the_crystal_seal_bars_the_stair_from_both_ends():
    """CCB fix: the seal was one-directional. A scavenger who came down the
    chimney into the sphere must not walk down an unsolved stair; once the
    jars sit on their plinths, BOTH directions clear together."""
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    canopic = game.locations["Hall of the Canopic Jars"]
    game.relocate(game.player, sphere)
    game.do_command("down")
    assert game.player.location is sphere  # barred from above too
    canopic.set_property("seal_open", True)  # the jar puzzle, solved
    game.do_command("down")
    assert game.player.location is canopic
    game.do_command("up")  # and the other direction stays clear
    assert game.player.location is sphere


def test_the_mantis_jar_bites_per_violation():
    """CCB: one bite per VIOLATION -- opening the jar, and again for the
    hand that reaches in for the eyes. Not per attempt: re-opening after
    both draws nothing more."""
    game = _game()
    game.relocate(game.player, game.locations["Hall of the Canopic Jars"])
    cap = _texts(game)
    game.do_command("open mantis jar")
    assert sum(1 for w in game.player.wounds if w.name == "Mantis-Bitten") == 1
    assert "mantis head STRIKES" in " ".join(cap.texts(Channel.NARRATION))
    game.do_command("take fungal eyes")  # the reach is bitten too
    assert sum(1 for w in game.player.wounds if w.name == "Mantis-Bitten") == 2
    game.do_command("close mantis jar")
    game.do_command("open mantis jar")  # both prices paid: no third
    assert sum(1 for w in game.player.wounds if w.name == "Mantis-Bitten") == 2


def test_the_jar_sings_at_loud_entry_but_not_sneaking():
    """CCB playtest: entering the canopic hall didn't start the song. The
    jar now hears exactly what the Spawn hear -- footfalls carry; sneak
    exists for a reason."""
    game = _game()
    game.relocate(game.player, game.locations["Hall of Hounds"])
    cap = _texts(game)
    game.do_command("go up")
    assert any("SINGS" in t for t in cap.texts(Channel.NARRATION))
    quiet_game = _game()
    quiet_game.relocate(quiet_game.player, quiet_game.locations["Hall of Hounds"])
    quiet_cap = _texts(quiet_game)
    quiet_game.do_command("sneak up")
    assert not any("SINGS" in t for t in quiet_cap.texts(Channel.NARRATION))


def test_the_glass_centipede_ambushes_in_the_chimney():
    game = _game()
    game.relocate(game.player, game.locations["The Summit"])
    cap = _texts(game)
    game.do_command("in")  # the ambush springs
    assert any(w.name == "Centipede Venom" for w in game.player.wounds)
    assert "glass centipede" in game.locations["The Fungal Chimney"].characters
    assert "uncoils" in " ".join(cap.texts(Channel.NARRATION))
    game.do_command("out")  # fleeing works
    assert game.player.location.name == "The Summit"


def test_a_blade_answers_the_centipede():
    game = _game()
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.relocate(game.player, game.locations["The Summit"])
    game.do_command("in")  # bitten on entry
    game.do_command("attack centipede with blade")
    assert game.characters["glass centipede"].get_property("is_unconscious")
    game.do_command("look")  # no further bites
    assert sum(1 for w in game.player.wounds if w.name == "Centipede Venom") == 1


def test_fire_scours_the_centipede_with_the_growth():
    game = _game()
    _hand(game, "Hall of Warriors", "orange cylinder", "plasma-igniter")
    gel = game.locations["Hall of Hounds"].items["flask of gel"]
    game.locations["Hall of Hounds"].remove_item(gel)
    game.player.add_to_inventory(gel)
    game.relocate(game.player, game.locations["The Fungal Chimney"])
    game.do_command("burn growth")
    assert game.characters["glass centipede"].get_property("is_dead")


def test_the_bats_follow_the_dates_and_roost_indoors():
    """CCB: toss the dates in an interior room and the colony streams there,
    eats, and roosts -- sated; the Hall of Youth becomes just a room (safe
    to light)."""
    game = _game()
    game.do_command("in")
    game.do_command("open crates")
    game.do_command("take dates")
    game.do_command("out")
    game.relocate(game.player, game.locations["Hall of Hounds"])
    cap = _texts(game)
    game.do_command("drop dates")
    youth = game.locations["Hall of Youth"]
    assert youth.get_property("bats_flown")
    assert "roost of bats" in game.locations["Hall of Hounds"].items
    assert "crate of dates" not in game.locations["Hall of Hounds"].items
    assert "only a room now" in " ".join(cap.texts(Channel.NARRATION))
    # The vault is safe to light.
    merchant = game.locations["The Caravan Wreck"].items["dead merchant"]
    stone = merchant.contents["glowstone"]
    merchant.remove_item(stone)
    game.player.add_to_inventory(stone)
    game.relocate(game.player, youth)
    game.do_command("light glowstone")
    for _ in range(3):
        game.do_command("wait")
    assert not any(w.name == "Bat-Mauled" for w in game.player.wounds)


def test_dates_in_the_bat_room_buy_five_safe_rounds():
    """CCB: dropped in the Hall of Youth itself, the colony swarms the dates
    -- five rounds of feeding during which nothing attacks, light or no
    light. Then the dates are gone and the ceiling resumes its opinions."""
    game = _game()
    game.do_command("in")
    game.do_command("open crates")
    game.do_command("take dates")
    game.do_command("out")
    merchant = game.locations["The Caravan Wreck"].items["dead merchant"]
    stone = merchant.contents["glowstone"]
    merchant.remove_item(stone)
    game.player.add_to_inventory(stone)
    youth = game.locations["Hall of Youth"]
    game.relocate(game.player, youth)
    game.do_command("light glowstone")
    cap = _texts(game)
    game.do_command("drop dates")
    assert "boiling carpet" in " ".join(cap.texts(Channel.NARRATION))
    wounds = len(game.player.wounds)
    for _ in range(5):
        game.do_command("look")  # lit, loud-adjacent, and untouched
    assert len(game.player.wounds) == wounds
    assert not youth.get_property("bats_flown")  # fed at home, not gone
    game.do_command("look")
    game.do_command("look")  # the vault has refilled: warn, then maul
    assert any(w.name == "Bat-Mauled" for w in game.player.wounds)
    assert "resumes its opinion" in " ".join(cap.texts(Channel.NARRATION))


def test_the_bats_disperse_after_ten_turns_outdoors():
    """CCB: tossed under open sky, the colony strips the dates, circles the
    tomb for ten turns, and disperses for good."""
    game = _game()
    game.do_command("in")
    game.do_command("open crates")
    game.do_command("take dates")
    game.do_command("out")
    cap = _texts(game)
    game.do_command("drop dates")  # at the wreck: open sky
    wreck = game.player.location
    assert "wheel of bats" in wreck.items
    assert game.locations["Hall of Youth"].get_property("bats_flown")
    for _ in range(9):
        game.do_command("wait")
    assert "wheel of bats" in wreck.items  # still turning at nine
    game.do_command("wait")
    assert "wheel of bats" not in wreck.items
    assert "scatters toward the horizon" in " ".join(cap.texts(Channel.NARRATION))


def test_carried_food_draws_the_denned_pack_by_scent():
    """CCB: anything edible carried within two rooms of the pack's ground
    pulls them out -- no noise required; salt meat is its own summons."""
    game = _game()
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.do_command("butcher zoxen")
    game.do_command("take zox haunch")
    pack = game.characters["jackal pack"]
    game.relocate(game.player, game.locations["Hall of Warriors"])
    game.do_command("wait")  # noses lift: they emerge
    assert pack.location.name == "Hall of Memory"
    game.do_command("wait")  # and close
    assert pack.location is game.player.location


def test_no_food_no_scent():
    game = _game()
    game.relocate(game.player, game.locations["Hall of Warriors"])
    game.do_command("wait")
    assert game.characters["jackal pack"].location.name == "Shallow Dens"


def test_a_sated_pack_ignores_the_scent():
    """Post-feed grace holds even against fresh meat."""
    game = _game()
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.do_command("butcher zoxen")
    game.do_command("take zox haunch")
    for hall in ("Hall of Memory", "Hall of Hounds", "Hall of Warriors"):
        loc = game.locations[hall]
        loc.set_property(f"_jk:{hall}", -4)  # just fed
    game.relocate(game.player, game.locations["Hall of Warriors"])
    game.do_command("wait")
    assert game.characters["jackal pack"].location.name == "Shallow Dens"


def test_scent_has_a_two_room_range():
    game = _game()
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.do_command("butcher zoxen")
    game.do_command("take zox haunch")
    game.do_command("wait")  # at the wreck: 3+ hops from the den mouth
    assert game.characters["jackal pack"].location.name == "Shallow Dens"


def test_butchering_the_zoxen_wants_a_blade_and_yields_two_cuts():
    """CCB: the zoxen earn their keep -- BUTCHER with a blade in hand gives
    edible trail meat, twice, and then the sand has the rest."""
    game = _game()
    cap = _texts(game)
    game.do_command("butcher zoxen")
    assert any("wants an edge" in t for t in cap.texts(Channel.BLOCKED))
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.do_command("butcher zoxen")
    game.do_command("butcher zoxen")
    game.do_command("butcher zoxen")  # the sand has the rest
    wreck = game.player.location
    assert "zox haunch" in wreck.items and "lean zox haunch" in wreck.items
    assert any("sand has the rest" in t for t in cap.texts(Channel.BLOCKED))
    game.do_command("take zox haunch")
    game.do_command("eat zox haunch")  # it is real food
    assert "zox haunch" not in game.player.carried_items()


def test_zox_meat_serves_as_jackal_tribute():
    """The scent draws them, and the same meat buys them off: GIVE the haunch
    and the pack carries it to the den, sated a long while."""
    game = _game()
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.do_command("butcher zoxen")
    game.do_command("take zox haunch")
    game.relocate(game.player, game.locations["Hall of Warriors"])
    game.do_command("wait")  # noses lift
    game.do_command("wait")  # they arrive
    pack = game.characters["jackal pack"]
    assert pack.location is game.player.location
    game.do_command("give zox haunch to jackal pack")
    assert pack.location.name == "Shallow Dens"  # gone with their tribute
    game.do_command("wait")  # and the grace holds against nothing at all
    assert pack.location.name == "Shallow Dens"


def test_the_centipede_hunts_once_sprung():
    """CCB: after its ambush the centipede follows the player anywhere, a
    room a round, and bites every round it shares one -- with one arrival
    round of grace, so running works and stopping doesn't."""
    game = _game()
    game.relocate(game.player, game.locations["The Summit"])
    game.do_command("in")  # the ambush: sprung + first bite
    cent = game.characters["glass centipede"]
    assert cent.get_property("sprung")
    bites = sum(1 for w in game.player.wounds if w.name == "Centipede Venom")
    assert bites == 1
    game.do_command("out")  # flee: it follows to the Summit
    game.do_command("wait")  # it arrives (grace round) or bites
    game.do_command("wait")  # co-located: bitten
    assert cent.location is game.player.location
    assert sum(1 for w in game.player.wounds if w.name == "Centipede Venom") > bites


def test_kick_the_centipede_off_the_roof():
    """CCB: on the Summit, KICK sends it over the edge -- it shatters at the
    tomb's base, leaving remains there. A boot pays no venom."""
    game = _game()
    game.relocate(game.player, game.locations["The Summit"])
    game.do_command("in")
    game.do_command("out")
    game.do_command("wait")  # let it arrive
    wounds = len(game.player.wounds)
    cap = _texts(game)
    game.do_command("kick centipede")
    cent = game.characters["glass centipede"]
    assert cent.get_property("is_dead")
    exterior = game.locations["Tomb Exterior"]
    assert "centipede remains" in exterior.items
    assert len(game.player.wounds) == wounds  # the boot pays nothing
    assert "dropped chandelier" in " ".join(cap.texts(Channel.NARRATION))
    # The fall forges a knife (CCB): one carapace splinter, edged, a real
    # weapon -- and butchery accepts it.
    shard = exterior.items["crystal shard"]
    assert shard.get_property("is_weapon") and shard.get_property("edged")
    game.relocate(game.player, exterior)
    game.do_command("take crystal shard")
    game.relocate(game.player, game.locations["The Caravan Wreck"])
    game.do_command("butcher zoxen")
    assert "zox haunch" in game.player.location.items


def test_throwing_it_by_hand_draws_a_parting_bite():
    game = _game()
    game.relocate(game.player, game.locations["The Summit"])
    game.do_command("in")
    game.do_command("out")
    game.do_command("wait")
    wounds = len(game.player.wounds)
    game.do_command("throw centipede off the roof")
    assert game.characters["glass centipede"].get_property("is_dead")
    assert len(game.player.wounds) == wounds + 1  # hands pay for live glass


def test_no_edge_no_toss():
    game = _game()
    game.relocate(game.player, game.locations["The Summit"])
    game.do_command("in")  # sprung, co-located in the chimney
    cap = _texts(game)
    game.do_command("kick centipede")
    assert not game.characters["glass centipede"].get_property("is_dead")
    assert any("no edge here" in t for t in cap.texts(Channel.BLOCKED))


def test_fire_finds_a_senseless_centipede_where_it_lies():
    """CCB playtest: a KO'd centipede ("cracked and still") seemed to die
    twice -- the scour line had it "boil out" of the growth. A senseless
    thing does not boil out of anything; the fire finds it where it lies."""
    game = _game()
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    _hand(game, "Hall of Warriors", "orange cylinder", "plasma-igniter")
    gel = game.locations["Hall of Hounds"].items["flask of gel"]
    game.locations["Hall of Hounds"].remove_item(gel)
    game.player.add_to_inventory(gel)
    game.relocate(game.player, game.locations["The Summit"])
    game.do_command("in")  # bitten on entry
    game.do_command("attack centipede with blade")  # cracked and still
    cap = _texts(game)
    game.do_command("burn growth")
    assert game.characters["glass centipede"].get_property("is_dead")
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "finds the cracked thing where it lies" in out
    assert "boils out" not in out


def test_burning_the_shaft_from_inside_costs_a_scorched_wound():
    """You can light the chimney while standing in its throat -- it works,
    and the flue you just made takes its due (CCB: a wound, not a death)."""
    game = _game()
    _hand(game, "Hall of Warriors", "orange cylinder", "plasma-igniter")
    gel = game.locations["Hall of Hounds"].items["flask of gel"]
    game.locations["Hall of Hounds"].remove_item(gel)
    game.player.add_to_inventory(gel)
    game.relocate(game.player, game.locations["The Fungal Chimney"])
    game.do_command("burn growth")
    assert game.locations["The Fungal Chimney"].get_property("burned")
    assert any(w.name == "Scorched" for w in game.player.wounds)


def test_burning_the_shaft_from_the_summit_is_free():
    """The smart play: light a chimney the way chimneys are lit -- from the
    mouth, standing in open air. Same cleanse, no wound."""
    game = _game()
    _hand(game, "Hall of Warriors", "orange cylinder", "plasma-igniter")
    gel = game.locations["Hall of Hounds"].items["flask of gel"]
    game.locations["Hall of Hounds"].remove_item(gel)
    game.player.add_to_inventory(gel)
    game.relocate(game.player, game.locations["The Summit"])
    cap = _texts(game)
    game.do_command("burn growth")
    assert game.locations["The Fungal Chimney"].get_property("burned")
    assert not any(w.name == "Scorched" for w in game.player.wounds)
    assert "from open air" in " ".join(cap.texts(Channel.NARRATION))
    # And the bare verbs at the Summit still mean the corpse, not the shaft.
    assert not game.locations["The Summit"].get_property("cleansed")


def test_burning_the_chimney_growth_clears_the_spores():
    game = _game()
    _hand(game, "Hall of Warriors", "orange cylinder", "plasma-igniter")
    gel = game.locations["Hall of Hounds"].items["flask of gel"]
    game.locations["Hall of Hounds"].remove_item(gel)
    game.player.add_to_inventory(gel)
    game.relocate(game.player, game.locations["The Fungal Chimney"])
    game.do_command("burn growth")
    chimney = game.locations["The Fungal Chimney"]
    assert chimney.get_property("burned")
    for _ in range(4):  # linger unmasked: the spores are gone
        game.do_command("look")
    assert not any(w.name == "Seared Lungs" for w in game.player.wounds)
    # ...and the burn is PERMANENT (CCB): the growth does not return.
    assert "orange growth" not in chimney.items
    assert "charred growth" in chimney.items
    assert "scoured black" in chimney.description
    assert "spores" not in chimney.description
    assert "char" in chimney.dim_description


def test_the_gel_economy_refills_and_regrets():
    game = _game()
    gel = game.locations["Hall of Hounds"].items["flask of gel"]
    game.locations["Hall of Hounds"].remove_item(gel)
    game.player.add_to_inventory(gel)
    game.relocate(game.player, game.locations["Hall of Hounds"])
    game.do_command("drink gel")  # legal, inadvisable
    assert any(w.name == "Gel-Gut" for w in game.player.wounds)
    assert "2 doses" in gel.description
    game.do_command("fill flask")  # topped back up at the tank
    assert "3 doses" in gel.description


def test_the_hound_gives_up_a_sparking_servo():
    game = _game()
    game.relocate(game.player, game.locations["Hall of Hounds"])
    game.do_command("break tank")
    game.do_command("search hound")
    game.do_command("take servo")
    assert "sparking servo" in game.player.inventory
    assert game.player.inventory["sparking servo"].get_property("ignition_source")


def test_the_full_winning_run_scores_100():
    game = _game()
    for cmd in tomb.WIN_WALKTHROUGH:
        if game.is_game_over():
            break
        game.do_command(cmd)
    assert game.is_won()
    assert game.score == 170 == game.max_score
    assert game.player.location.name == "Tomb Exterior"


def test_butchery_catches_the_blood_and_the_blood_mends():
    """The first cut yields the haunch AND two doses of zox blood (CCB);
    each dose drinks like water -- the most recent wound heals -- and the
    doses can be decanted into the waterskin to keep."""
    from text_adventure_games import things as _things
    from text_adventure_games.slots import Wound

    game = _game()
    cap = _texts(game)
    edge = _things.Item("test knife", "a test knife", "a test knife")
    edge.set_property("edged", True)
    game.player.add_to_inventory(edge)
    game.do_command("butcher zoxen")
    loc = game.player.location
    assert "zox haunch" in loc.items
    assert "zox blood" in loc.items
    blood = loc.items["zox blood"]
    assert int(blood.get_property("portions")) == 2
    # a dose heals the freshest wound
    game.player.add_wound(Wound("Bloody Gash", 1, "It will scar."))
    game.do_command("take blood")
    game.do_command("drink blood")
    assert not game.player.wounds
    assert int(blood.get_property("portions")) == 1
    # the last dose keeps in the waterskin as a ration
    game.do_command("search merchant")
    game.do_command("take waterskin")
    skin = game.player.carried_items()["waterskin"]
    before = int(skin.get_property("portions"))
    game.do_command("pour blood into waterskin")
    assert int(skin.get_property("portions")) == before + 1
    assert "zox blood" not in game.player.carried_items()


def test_location_direction_aliases_answer_the_playtesters():
    """'enter tomb' / 'climb stone' / 'enter wagon' parse as movement at the
    rooms where players actually type them -- without the synonyms showing up
    as extra entries in Exits: (which lists real connections only)."""
    game = _game()
    game.do_command("north")
    assert game.player.location.name == "Tomb Exterior"
    game.do_command("enter tomb")
    assert game.player.location.name == "Hall of Youth"
    game.do_command("leave tomb")
    assert game.player.location.name == "Tomb Exterior"
    game.do_command("climb stone")
    assert game.player.location.name == "The Summit"
    # the synonyms are parser-only: Exits stays the real connections
    exterior = game.locations["Tomb Exterior"]
    assert set(exterior.direction_aliases) & {"enter tomb", "climb stone"}
    assert "enter tomb" not in exterior.connections
    # and a non-movement command with the same noun is not hijacked
    game.do_command("climb down")
    cap = _texts(game)
    game.do_command("examine tomb")
    assert game.player.location.name == "Tomb Exterior"  # didn't move
