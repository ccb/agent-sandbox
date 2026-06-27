"""Regression tests for Action Castle IV ("Escape from Action Castle").

Locks in the world topology and start state (Slice 2), the tower escape (Slice 3),
the horse + poacher (Slice 4), and the finale -- ranch, roadhouse, bar brawl, and
the two scored endings (Slice 5), including the full 100-point winning run.
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
    "Outside the Tower",
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
    "Highway",
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
        # The Roadhouse deliberately has two roads (east + west) onto the one
        # Highway ending -- that's faithful, not a copy-paste bug, so allow it.
        dests = [d.name for d in loc.connections.values() if d.name != "Highway"]
        assert len(dests) == len(set(dests)), f"{name} has a duplicate-destination exit"


def test_key_connections():
    game, _ = _game()
    loc = game.locations

    def goes(room, direction, dest):
        return loc[room].connections.get(direction) is loc[dest]

    assert goes("Tower", "out", "Tower Stairs")
    assert goes("Tower", "down", "Outside the Tower")
    assert goes("Outside the Tower", "down", "Gardens")
    assert goes("Outside the Tower", "in", "Tower")
    assert goes("Tower Stairs", "down", "Guardroom")
    assert goes("Guardroom", "west", "Drawbridge")
    assert goes("Gardens", "south", "Drawbridge")
    assert goes("Drawbridge", "south", "Down by the River")
    assert goes("Drawbridge", "west", "Old Woods")
    assert goes("Old Woods", "enter", "Old Shack")
    # The Old Woods -> Deep Woods link exists (keeps Deep Woods reachable/indexed)
    # but is always blocked -- you must FOLLOW DEER to get in (see below).
    assert goes("Old Woods", "north", "Deep Woods")
    assert loc["Old Woods"].is_blocked("north")
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
    # Drawbridge -> Old Woods is vehicle-gated (reach the bridge via the window).
    game, cap = _play(ESCAPE_TO_GARDENS + ["south", "west"])
    assert game.player.location.name == "Drawbridge"
    assert _said(cap, "too far")


def test_window_escape_reaches_the_gardens():
    game, _ = _play(ESCAPE_TO_GARDENS)
    assert game.player.location.name == "Gardens"
    assert not game.is_game_over()
    assert game.player.get_property("escaped")


# --- Slice 3: the tower escape --------------------------------------------


def test_escape_scores_guardroom_boots_and_escape():
    game, cap = _play(
        [
            "out",
            "down",  # -> Guardroom (+5)
            "open footlocker",
            "take dagger",
            "take army boots",
            "wear army boots",  # +5
            "up",
            "enter",
            "cut hair",
            "get hair",
            "make rope",
            "tie rope",
            "climb down",  # -> Outside the Tower
            "let go",  # drop -> Gardens (escape, +5)
        ]
    )
    assert game.player.location.name == "Gardens"
    assert {"guardroom", "boots", "escape"} <= game._scored_keys
    assert game.score >= 15


def test_window_rope_route_escape_via_crafting():
    game, cap = _play(
        [
            "out",
            "down",  # -> Guardroom
            "open footlocker",
            "take dagger",
            "up",
            "enter",  # back up into the Tower
            "cut hair",  # yields the hair (on the floor)
            "get hair",  # pick it up off the floor
            "make rope",  # crafting recipe: hair -> rope
            "tie rope",
            "climb down",  # -> Outside the Tower (on the rope)
            "let go",  # drop -> Gardens (escape +5)
        ]
    )
    assert game.player.location.name == "Gardens"  # climbed out the window
    assert game.player.get_property("hair_cut")
    assert "escape" in game._scored_keys


def test_cannot_climb_down_without_a_tied_rope():
    game, cap = _play(["look"])  # start in the Tower
    game.do_command("down")
    assert _said(cap, "rope")
    assert game.player.location.name == "Tower"


def test_braid_hair_reaches_the_same_rope_recipe():
    game, cap = _play(
        [
            "out",
            "down",
            "open footlocker",
            "take dagger",
            "up",
            "enter",
            "cut hair",
            "get hair",
            "braid hair",
        ]
    )
    assert "rope" in game.player.inventory


def test_cut_hair_needs_the_dagger():
    game, cap = _play(["cut hair"])  # in the Tower, no dagger
    assert _said(cap, "nothing sharp")
    assert not game.player.get_property("hair_cut")


def test_make_rope_needs_hair():
    game, cap = _play(["make rope"])  # no hair yet
    assert _said(cap, "You need")
    assert "rope" not in game.player.inventory


def test_wearing_glass_slippers_is_a_gag_not_a_death():
    game, cap = _play(["take glass slippers", "wear glass slippers"])
    assert not game.is_game_over()
    assert _said(cap, "doesn't hurt")
    assert "glass slippers" in game.player.worn


def test_wearing_ruby_slippers_is_a_gag_not_a_death():
    game, cap = _play(["take ruby slippers", "wear ruby slippers"])
    assert not game.is_game_over()
    assert _said(cap, "Kansas")


def test_kill_self_is_a_clue_not_a_death():
    game, cap = _play(
        ["out", "down", "open footlocker", "take dagger", "up", "enter", "kill self"]
    )
    assert not game.is_game_over()
    assert _said(cap, "Hmm")


def test_tower_stairs_has_only_two_exits():
    # Per the rulebook: DOWN to the Guardroom and ENTER back into the Tower.
    game, _ = _game()
    assert set(game.locations["Tower Stairs"].connections) == {"down", "enter"}


def test_bolting_out_the_front_gate_without_the_dagger_is_doom():
    # Guardroom WEST -> the guard catches you at the bridge, marches you back and
    # locks the door; with no dagger to cut your hair, you're trapped forever.
    game, cap = _play(["out", "down", "west"])
    assert _said(cap, "guard")
    assert game.is_game_over()
    assert _said(cap, "nineteen years")


def test_caught_with_the_dagger_can_still_escape_by_window():
    game, cap = _play(["out", "down", "open footlocker", "take dagger", "west"])
    assert _said(cap, "guard")
    assert game.player.location.name == "Tower"  # marched back upstairs
    assert game.locations["Tower"].get_property("door_locked")
    assert not game.is_game_over()  # the dagger means the window is still open
    # the door is locked now, but the window still works
    game, cap = _play(
        ["out", "down", "open footlocker", "take dagger", "west"]
        + ["cut hair", "get hair", "make rope", "tie rope", "climb down", "let go"]
    )
    assert game.player.location.name == "Gardens"


def test_the_locked_door_blocks_the_stairs():
    game, cap = _play(["out", "down", "open footlocker", "take dagger", "west", "out"])
    assert game.player.location.name == "Tower"
    assert _said(cap, "locked")


# --- Slice 4a: the horse ---------------------------------------------------

# The only real escape: grab the dagger, cut your hair, rope out the window into
# the Gardens. (Bolting out the front gate is a trap -- see the guard tests.)
ESCAPE_TO_GARDENS = [
    "out",
    "down",  # -> Guardroom
    "open footlocker",
    "take dagger",
    "up",
    "enter",  # back into the Tower
    "cut hair",
    "get hair",  # the shorn hair lands on the floor -- pick it up
    "make rope",
    "tie rope",
    "climb down",  # out the window onto the rope -> Outside the Tower
    "let go",  # drop into the gardens
]

# ...then on to the river with an apple in hand.
TO_RIVER_WITH_APPLE = ESCAPE_TO_GARDENS + [
    "pick apple",
    "south",  # Gardens -> Drawbridge
    "south",  # Drawbridge -> Down by the River
]


def test_pick_apple_in_the_gardens():
    game, _ = _play(ESCAPE_TO_GARDENS + ["pick apple"])
    assert "apple" in game.player.inventory


def test_cannot_ride_the_untamed_mare():
    game, cap = _play(TO_RIVER_WITH_APPLE + ["ride horse"])
    assert _said(cap, "whinnies")
    assert game.player.riding is None


def test_apple_tames_the_mare():
    game, _ = _play(TO_RIVER_WITH_APPLE + ["give apple to horse", "ride horse"])
    assert game.player.riding is not None and game.player.riding.name == "horse"
    assert "apple" not in game.player.inventory  # consumed


def test_brushing_also_tames_the_mare():
    game, _ = _play(
        ["open dresser", "take hairbrush"]  # the hairbrush is in the tower dresser
        + ESCAPE_TO_GARDENS
        + ["south", "south", "brush horse", "ride horse"]  # -> Down by the River
    )
    assert game.player.riding is not None


def test_must_dismount_to_enter_the_shack():
    game, cap = _play(
        TO_RIVER_WITH_APPLE
        + [
            "give apple to horse",
            "ride horse",
            "north",
            "west",
        ]  # -> Old Woods, mounted
    )
    assert game.player.location.name == "Old Woods"
    game.do_command("enter")  # can't enter the shack on horseback
    assert _said(cap, "get off the horse")
    assert game.player.location.name == "Old Woods"
    game.do_command("dismount")
    game.do_command("enter")
    assert game.player.location.name == "Old Shack"


def test_ride_to_the_woods_and_get_the_crossbow():
    game, _ = _play(
        TO_RIVER_WITH_APPLE
        + [
            "give apple to horse",
            "ride horse",
            "north",
            "west",  # -> Old Woods (mounted; the gate opens)
            "dismount",
            "enter",
            "take crossbow",
        ]
    )
    assert game.player.location.name == "Old Shack"
    assert "crossbow" in game.player.inventory


def test_eat_apple_is_a_gag_that_spends_it():
    game, cap = _play(ESCAPE_TO_GARDENS + ["pick apple", "eat apple"])
    assert _said(cap, "CRUNCH")
    assert "apple" not in game.player.inventory


# --- Slice 4b: the poacher + the deer --------------------------------------

# Tame the mare, ride to the Old Woods, get the crossbow, and ride into the Deep
# Woods after the deer.
TO_DEEP_WOODS = TO_RIVER_WITH_APPLE + [
    "give apple to horse",
    "ride horse",
    "north",
    "west",  # -> Old Woods (mounted)
    "dismount",
    "enter",
    "take crossbow",
    "out",  # crossbow in hand
    "ride horse",
    "follow deer",  # -> Deep Woods
]


def test_follow_deer_needs_the_horse():
    game, cap = _play(
        TO_RIVER_WITH_APPLE
        + [
            "give apple to horse",
            "ride horse",
            "north",
            "west",
            "dismount",
            "follow deer",
        ]
    )
    assert _said(cap, "on foot")
    assert game.player.location.name == "Old Woods"


def test_shoot_poacher_saves_the_deer_and_drops_the_purse():
    game, cap = _play(TO_DEEP_WOODS + ["shoot poacher"])
    assert game.player.location.name == "Deep Woods"
    assert game.locations["Deep Woods"].get_property("poacher_dealt")
    assert "shoot" in game._scored_keys
    assert "coin purse" in game.locations["Deep Woods"].items  # dropped


def test_shooting_needs_the_crossbow():
    # Ride in without the crossbow (skip the shack), then it's the wrong tool.
    game, cap = _play(
        TO_RIVER_WITH_APPLE
        + [
            "give apple to horse",
            "ride horse",
            "north",
            "west",
            "follow deer",
            "shoot poacher",
        ]
    )
    assert _said(cap, "nothing to shoot")


def test_taking_the_purse_scores_and_north_opens():
    game, _ = _play(TO_DEEP_WOODS + ["shoot poacher", "take coin purse", "north"])
    assert "purse" in game._scored_keys
    assert game.player.location.name == "Clearing"


def test_north_is_barred_until_the_poacher_is_dealt_with():
    game, cap = _play(TO_DEEP_WOODS + ["north"])
    assert _said(cap, "stalks the deer")
    assert game.player.location.name == "Deep Woods"


def test_hesitating_lets_the_poacher_kill_the_deer():
    game, cap = _play(TO_DEEP_WOODS + ["south"])  # flee instead of shooting
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "doe drops")


def test_examining_in_the_deep_woods_is_safe():
    game, cap = _play(TO_DEEP_WOODS + ["examine poacher"])  # a look isn't fatal
    assert not game.is_game_over()
    game.do_command("shoot poacher")
    assert game.locations["Deep Woods"].get_property("poacher_dealt")


# --- boots playtest fixes (get/wear "boots"; one footwear at a time) -------


def test_boots_can_be_taken_by_short_or_full_name():
    game, _ = _play(["out", "down", "get boots"])
    assert "boots" in game.player.inventory
    game2, _ = _play(["out", "down", "get army boots"])  # the descriptive name too
    assert "boots" in game2.player.inventory


def test_wearing_boots_scores_and_works_by_either_name():
    game, cap = _play(["out", "down", "get boots", "wear boots"])
    assert "boots" in game.player.worn and "boots" in game._scored_keys
    game2, _ = _play(["out", "down", "get boots", "wear army boots"])
    assert "boots" in game2.player.worn


def test_only_one_footwear_at_a_time():
    game, cap = _play(
        [
            "out",
            "down",
            "get boots",
            "up",
            "enter",
            "take glass slippers",
            "wear glass slippers",
        ]
    )
    assert "glass slippers" in game.player.worn
    game.do_command("wear boots")  # blocked: slippers occupy the feet slot
    assert _said(cap, "take off")
    assert "boots" not in game.player.worn
    game.do_command("take off glass slippers")
    game.do_command("wear boots")
    assert "boots" in game.player.worn and "glass slippers" not in game.player.worn


def test_slipper_gags_run_through_the_engine_wear():
    game, cap = _play(["take glass slippers", "wear glass slippers"])
    assert not game.is_game_over()  # a gag, not a death
    assert _said(cap, "doesn't hurt")


def test_boots_are_hidden_under_the_cot_until_examined():
    game, cap = _play(["out", "down"])  # -> Guardroom
    # The boots aren't advertised in the room listing...
    assert not _said(cap, "army boots") or not any(
        "You see" in t and "boots" in t for t in cap.texts(Channel.NARRATION)
    )
    assert "boots" not in game.locations["Guardroom"].items  # they're in the cot
    fresh = CaptureRenderer()
    game.parser.set_renderer(fresh)
    game.do_command("examine army cot")  # ...revealed by looking under the mattress
    assert _said(fresh, "Under the stained mattress you see a pair of old army boots")
    game.do_command("take boots")
    assert "boots" in game.player.inventory
    after = CaptureRenderer()
    game.parser.set_renderer(after)
    game.do_command("examine army cot")  # self-updates: no stale mention
    assert not _said(after, "Under the stained mattress")


# --- Slice 5: the finale (ranch, roadhouse, bar, endings) ------------------


def test_winning_run_scores_100_and_wins():
    game, _ = _play(ac4.WALKTHROUGH_WIN)
    assert game.is_game_over()
    assert game.is_won()
    assert game.score == 100
    assert game.player.get_property("rode_the_highway")


def test_rancher_ending_is_a_good_finish_not_the_win():
    # Same run, but accept Wade's job instead of declining it.
    cmds = ac4.WALKTHROUGH_WIN[: ac4.WALKTHROUGH_WIN.index("say no")] + ["say yes"]
    game, _ = _play(cmds)
    assert game.is_game_over()
    assert not game.is_won()  # the Rancher ending isn't the 100-point run
    assert game.score == 80


def test_dalton_bars_the_bar_without_wade():
    # Drive to the roadhouse on the bike-less path and try to enter cold.
    cmds = ac4.WALKTHROUGH_WIN[: ac4.WALKTHROUGH_WIN.index("give horse to rancher")]
    cmds += ["northeast", "west", "north", "enter"]  # Clearing -> road -> roadhouse
    game, cap = _play(cmds)
    assert game.player.location.name == "Roadhouse"  # blocked at the door
    assert _said(cap, "I.D.")


def test_say_wade_sent_me_needs_having_met_wade():
    cmds = ac4.WALKTHROUGH_WIN[: ac4.WALKTHROUGH_WIN.index("give horse to rancher")]
    cmds += ["northeast", "west", "north", "say wade sent me"]
    game, cap = _play(cmds)
    assert _said(cap, "Wade who?")
    assert not game.locations["Roadhouse"].get_property("admitted")


def test_brawl_requires_provoking_the_biker_first():
    cmds = ac4.WALKTHROUGH_WIN[: ac4.WALKTHROUGH_WIN.index("talk to bartender") + 1]
    cmds += ["punch biker"]  # before serving table four
    game, cap = _play(cmds)
    assert _said(cap, "Nobody's looking for a fight")
    assert "keys" not in game.player.location.items


def test_cannot_ride_the_horse_onto_the_highway():
    # Skip the ranch entirely and arrive at the roadhouse still mounted; the
    # highway exits demand the motorcycle specifically.
    cmds = ac4.WALKTHROUGH_WIN[: ac4.WALKTHROUGH_WIN.index("give horse to rancher")]
    cmds += ["northeast", "west", "north", "east"]
    game, cap = _play(cmds)
    assert game.player.location.name == "Roadhouse"
    assert _said(cap, "motor vehicle")


def test_brush_hair_is_flavor_with_the_hairbrush():
    game, cap = _play(["open dresser", "take hairbrush", "brush hair"])
    assert _said(cap, "two hours")
    assert game.player.get_property("hair_brushed")
    assert not game.is_game_over()


def test_brush_hair_needs_the_hairbrush():
    game, cap = _play(["brush hair"])  # in the Tower, no hairbrush yet
    assert _said(cap, "need a hairbrush")


def test_cut_hair_drops_it_on_the_floor_and_climb_has_narration():
    # Hair lands in the room (faithful), not the inventory; you GET it to craft.
    game, cap = _play(
        ["out", "down", "open footlocker", "take dagger", "up", "enter", "cut hair"]
    )
    tower = game.locations["Tower"]
    assert "hair" in tower.items and "hair" not in game.player.inventory
    # Climbing out the window has the rope/rosebush descent flavor.
    game2, cap2 = _play(ESCAPE_TO_GARDENS)
    assert game2.player.location.name == "Gardens"
    assert _said(cap2, "down the rope") and _said(cap2, "rosebush")


def test_climb_down_puts_you_on_the_rope_not_yet_escaped():
    game, _ = _play(ESCAPE_TO_GARDENS[:-1])  # everything up to "climb down"
    assert game.player.location.name == "Outside the Tower"
    assert not game.player.get_property("escaped")  # you haven't let go yet


def test_can_climb_back_in_from_the_rope():
    game, _ = _play(ESCAPE_TO_GARDENS[:-1] + ["climb in"])
    assert game.player.location.name == "Tower"


def test_jump_from_the_rope_drops_into_the_gardens():
    game, cap = _play(ESCAPE_TO_GARDENS[:-1] + ["jump"])  # "jump" alias of let go
    assert game.player.location.name == "Gardens"
    assert game.player.get_property("escaped")
    assert _said(cap, "rosebush")


def test_no_climbing_back_up_from_the_gardens():
    # The rope dangles out of reach once you're on the ground -- one-way drop.
    game, _ = _play(ESCAPE_TO_GARDENS + ["up"])
    assert game.player.location.name == "Gardens"
    assert "up" not in game.locations["Gardens"].connections


def test_pick_rose_is_flavor_not_a_bare_bush():
    # The bush is covered in roses (rulebook: "not used for anything") -- picking
    # one is harmless flavor + the SMELL ROSE gag, not a "bare bush" refusal.
    game, cap = _play(ESCAPE_TO_GARDENS + ["pick rose", "smell rose"])
    assert _said(cap, "picked the lone rose")
    assert "rose" in game.player.inventory
    assert not _said(cap, "bare")


def test_pick_watermelon_is_a_too_heavy_gag():
    # Parallel to roses/apples, but the rulebook makes watermelon a gag: too
    # heavy to carry, so it's never added to the inventory.
    game, cap = _play(
        ESCAPE_TO_GARDENS + ["examine watermelon vines", "pick watermelon"]
    )
    assert _said(cap, "watermelons swelling on the vine")  # the fixture examines
    assert _said(cap, "too heavy")
    assert "watermelon" not in game.player.inventory


def test_cannot_walk_north_into_the_deep_woods():
    # The only way in is FOLLOW DEER -- a bare "north" must not blunder you into
    # the lethal poacher confrontation.
    setup = TO_RIVER_WITH_APPLE + [
        "give apple to horse",
        "ride horse",
        "north",
        "west",  # -> Old Woods, mounted
    ]
    game, cap = _play(setup + ["north"])
    assert game.player.location.name == "Old Woods"  # didn't move; no such exit
    assert not game.is_game_over()
    # FOLLOW DEER is the way in.
    game.do_command("follow deer")
    assert game.player.location.name == "Deep Woods"


def test_tying_the_rope_removes_it_from_inventory():
    # The rope is tied to the door + fed out the window -- it leaves your hands.
    game, _ = _play(ESCAPE_TO_GARDENS[: ESCAPE_TO_GARDENS.index("tie rope") + 1])
    assert game.locations["Tower"].get_property("rope_tied")
    assert "rope" not in game.player.inventory


def test_talk_to_prince_about_art_gives_the_quest_line():
    # "art" is aliased to the same response as "quest" (he packed art supplies).
    game, cap = _play(
        ESCAPE_TO_GARDENS + ["south", "south", "talk to prince about art"]
    )
    assert _said(cap, "rescue the princess from yon tower")


def test_mirror_reflects_the_haircut_live():
    # Before: "staggeringly long"; after CUT HAIR: the ragged crop -- same command.
    before, cap_b = _play(["examine mirror"])
    assert _said(cap_b, "staggeringly long")
    after, cap_a = _play(
        [
            "out",
            "down",
            "open footlocker",
            "take dagger",
            "up",
            "enter",
            "cut hair",
            "examine mirror",
        ]
    )
    assert _said(cap_a, "ragged crop")
    assert not _said(cap_a, "staggeringly long")


def test_mirror_feet_line_tracks_footwear():
    # "Your feet are bare" while unshod; once she dons the boots the feet line
    # clears (the boots show in the "wearing ..." line instead -- no contradiction).
    bare, cap_b = _play(["examine mirror"])
    assert _said(cap_b, "Your feet are bare")
    shod, cap_s = _play(
        ["out", "down", "take boots", "wear boots", "up", "enter", "examine mirror"]
    )
    assert not _said(cap_s, "feet are bare")
    assert _said(cap_s, "old army boots")  # now reflected as worn


def test_poacher_cloak_is_wearable_over_the_gown():
    # The cloak is wearable and layers over the gown (wear_over), not displacing it.
    game, cap = _play(TO_DEEP_WOODS + ["shoot poacher", "take cloak", "wear cloak"])
    assert "cloak" in game.player.worn and "gown" in game.player.worn
    assert _said(cap, "over your gown")


def test_read_sign_shows_its_directions():
    game, cap = _play(TO_DEEP_WOODS + ["shoot poacher", "north", "west", "read sign"])
    assert _said(cap, "Breakpoint Bar & Grill")
    assert not _said(cap, "nothing to read")


def test_talk_to_dalton_greets_and_hints_at_wade():
    game, cap = _play(
        ac4.WALKTHROUGH_WIN[: ac4.WALKTHROUGH_WIN.index("say wade sent me")]
        + ["talk to dalton", "talk to dalton about wade"]
    )
    assert _said(cap, "Name's Dalton")
    assert _said(cap, "if *Wade* sent you")


# --- Breakpoint flavor: jukebox + drink bottle (optional, coin-driven) -------


def _to_breakpoint():
    # ... say wade sent me, enter -> The Breakpoint (carrying the poacher's purse).
    W = ac4.WALKTHROUGH_WIN
    return W[: W.index("say wade sent me") + 2]


def test_jukebox_plays_for_a_coin_and_annoys_the_crowd():
    game, cap = _play(_to_breakpoint() + ["use coin on jukebox", "play metal"])
    assert _said(cap, "ranchers boo")  # metal annoys the ranchers
    coins = game.player.carried_items().get("silver coins")
    assert coins is not None and coins.quantity == 2  # one of three spent


def test_play_without_a_coin_is_refused():
    game, cap = _play(_to_breakpoint() + ["play metal"])
    assert _said(cap, "Put a coin in the jukebox first")


def test_drink_bottle_is_a_gag():
    game, cap = _play(_to_breakpoint() + ["talk to bartender", "drink bottle"])
    assert _said(cap, "it burns")
