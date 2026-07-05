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
    game.do_command("say hey")  # yipping, distant
    game.do_command("say hey")  # yipping, nearer
    game.do_command("say hey")  # yellow eyes
    assert not game.player.wounds
    game.do_command("say hey")  # the pack enters and growls
    hall = game.locations["Hall of Memory"]
    assert "jackal pack" in hall.characters
    assert "growls" in " ".join(cap.texts(Channel.NARRATION)).lower()
    assert not game.player.wounds  # the growl round is grace
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
        "take dates",
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
    assert "jackal pack" in hall.characters
    game.do_command("give dates to jackals")
    assert "jackal pack" not in hall.characters  # gone with the goods
    assert not game.player.wounds
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
        "compartment three times larger"
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
    assert "swings toward your footfalls" in " ".join(cap.texts(Channel.NARRATION))
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
        "open pack",
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

    game.do_command("open pack")
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
    """Two warnings, then a Seared Lungs wound per round of lingering -- death
    only when the wounds fill your slots."""
    game = _game()
    _embark(game)
    game.characters["glass centipede"].set_property("is_unconscious", True)
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


def test_the_spider_silk_tether_is_the_bootless_anchor():
    game = _game()
    sphere = game.locations["Burial Sphere of Nassak An-Rah"]
    sphere.set_property("horror_dead", True)
    _hand(game, "Hall of Warriors", "cerulean cylinder", "prismatic blade")
    game.do_command("in")
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
    """Anchor, blade, gel, and spark -- straight to the sphere."""
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
    assert "unwinds from the Autarch's bones" in out


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
    assert "cannot knit itself" in " ".join(cap.texts(Channel.NARRATION))
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
    assert "What is cut can knit again" in out


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


def _summon_pack(game):
    """Quietly reach Memory, then shout the pack into the room."""
    _no_spawn(game)
    _embark(game, glowstone=False)
    for cmd in (
        "sneak north",
        "sneak north",
        "say hey",
        "say hey",
        "say hey",
        "say hey",
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
    for cmd in ("open pack", "take glowstone", "light glowstone"):
        game.do_command(cmd)
    game.relocate(game.player, game.locations["Hall of Warriors"])
    game.do_command("attack spawn of guts with blade")
    cap = _texts(game)
    game.do_command("look")
    out = " ".join(cap.texts(Channel.NARRATION))
    assert "collapsed in a heap" in out
    assert "swaying toward every sound" not in out


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
    assert game.locations["The Fungal Chimney"].get_property("burned")
    for _ in range(4):  # linger unmasked: the spores are gone
        game.do_command("look")
    assert not any(w.name == "Seared Lungs" for w in game.player.wounds)


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
    assert game.score == 100 == game.max_score
    assert game.player.location.name == "Tomb Exterior"
