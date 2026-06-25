"""Regression tests for the checked-in Action Castle II game instance.

Locks in the win paths and the playtest fixes (boat container, shoe-size fit
gate, talk-to-NPC, clean map topology, 100-point scoring) so the game can't
silently rot as the engine evolves.
"""

from text_adventure_games.adventures import action_castle_2 as ac2
from text_adventure_games.reporting import CaptureRenderer, Channel


def _game():
    game = ac2.build_game()
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


def _said(cap, substring):
    # player-facing text: world narration AND blocked/refusal messages
    # (parser.fail() emits on Channel.BLOCKED, e.g. "The slippers don't fit.")
    return any(
        substring in t
        for ch in (Channel.NARRATION, Channel.BLOCKED)
        for t in cap.texts(ch)
    )


# --- win paths -------------------------------------------------------------


def test_champion_walkthrough_wins():
    game, _ = _play(ac2.WALKTHROUGH_CHAMPION)
    assert game.is_won()
    assert game.player.get_property("is_champion")
    assert game.max_score == 100
    assert game.score == 71  # the minimal champion walkthrough's score


def test_marriage_walkthrough_wins():
    game, _ = _play(ac2.WALKTHROUGH_MARRIAGE)
    assert game.is_won()
    assert game.player.get_property("is_married")
    assert game.max_score == 100
    assert game.score == 79


# --- boat as a room container (engine container support) -------------------


def test_blanket_starts_in_the_boat_not_loose():
    game, _ = _game()
    old_pond = game.locations["Old Pond"]
    boat = old_pond.items["boat"]
    assert boat.get_property("is_container")
    assert "blanket" in boat.contents
    assert "blanket" not in old_pond.items  # it's in the boat, not on the ground


def test_examine_boat_lists_blanket_then_take_empties_it():
    game, cap = _play(["out", "east", "south"])  # -> Old Pond
    game.do_command("examine boat")
    assert _said(cap, "It contains a warm wool blanket.")
    game.do_command("take blanket")  # reach into the open container
    assert "blanket" in game.player.inventory
    assert "blanket" not in game.locations["Old Pond"].items["boat"].contents
    game.do_command("examine boat")
    assert _said(cap, "fair condition")  # still describable, now empty


# --- shoe-size fit gate (Wear) ---------------------------------------------


def test_slippers_do_not_fit_the_cobbler():
    game, cap = _play(["take slippers", "wear slippers"])
    assert _said(cap, "The slippers don't fit.")
    # the gate is real: only royalty shares the slippers' size
    slippers = game.player.inventory["slippers"]
    assert game.player.get_property("shoe_size") != slippers.get_property("shoe_size")
    assert game.characters["king"].get_property("shoe_size") == slippers.get_property(
        "shoe_size"
    )


# --- talk to an NPC (generic Talk verb) ------------------------------------


def test_talk_to_smith_speaks_his_line():
    game, cap = _play(["out", "south"])  # -> Smithy
    game.do_command("talk to smith")
    assert _said(cap, "Whaddya want? I'm busy!")


def _at_hermit():
    return _play(["out", "east", "south", "south"])  # -> Outside Hermit's Cave


def test_hermit_is_outside_a_blocked_cave():
    game, _ = _game()
    assert "Outside Hermit's Cave" in game.locations
    assert "Cave" in game.locations  # a real (if unenterable) location


def test_cave_is_too_dark_to_enter():
    game, cap = _at_hermit()
    assert game.player.location.name == "Outside Hermit's Cave"
    game.do_command("go in")  # blocked exit
    assert _said(cap, "too dark and scary")
    assert game.player.location.name == "Outside Hermit's Cave"  # didn't enter
    game.do_command("enter cave")  # the rulebook verb
    assert _said(cap, "too dark and scary")
    assert game.player.location.name == "Outside Hermit's Cave"


def test_talk_to_hermit_mumbles_about_a_prophecy():
    game, cap = _at_hermit()
    game.do_command("talk to hermit")
    assert _said(cap, "mumbles something about a prophecy")
    assert not _said(cap, "A champion will arise")  # the topic line isn't given yet


def test_talk_to_hermit_about_prophecy_evokes_it():
    game, cap = _at_hermit()
    game.do_command("talk to hermit about prophecy")
    assert _said(cap, "A champion will arise from humble beginnings")


def test_ask_hermit_about_the_prophecy_also_works():
    game, cap = _at_hermit()
    game.do_command("ask hermit about the prophecy")  # the "ask ... about" form
    assert _said(cap, "A champion will arise from humble beginnings")


def test_ask_hermit_about_unknown_topic_is_declined():
    game, cap = _at_hermit()
    game.do_command("ask hermit about the weather")
    assert _said(cap, "has nothing to say about that")
    assert not _said(cap, "A champion will arise")


# --- map topology (one-way connection fixes) -------------------------------


def test_no_room_has_duplicate_destination_exits():
    game, _ = _game()
    for name, loc in game.locations.items():
        dests = [d.name for d in loc.connections.values()]
        assert len(dests) == len(set(dests)), f"{name} has a duplicate-destination exit"


def test_workshop_is_reachable_from_town_square():
    game, _ = _play(["out"])  # -> Town Square
    assert game.player.location.name == "Town Square"
    game.do_command("north")  # the rulebook's NORTH back into the shop
    assert game.player.location.name == "Cobbler's Workshop"


# --- a couple of signature interactions ------------------------------------


def _smithy_with_axe(give_command):
    """Reach the smithy holding the axe, then issue *give_command*."""
    return _play(
        ["out", "east", "north", "take axe", "south", "west", "south", give_command]
    )


def test_give_axe_to_smith_sharpens_it():
    game, _ = _smithy_with_axe("give axe to smith")
    axe = game.player.inventory.get("axe")
    assert axe is not None and axe.get_property("is_sharp")


def test_give_smith_the_axe_also_sharpens_it():
    # The word-order variant routes through the built-in Give; a trigger reacts
    # to the smith holding the axe and sharpens it regardless of phrasing (#113).
    game, _ = _smithy_with_axe("give smith the axe")
    axe = game.player.inventory.get("axe")
    assert axe is not None and axe.get_property("is_sharp")
    assert "axe" not in game.characters["smith"].inventory  # handed back


def test_axe_is_embedded_in_the_stump_surface():
    game, cap = _play(["out", "east", "north"])  # -> Bend in the Road
    stump = game.player.location.items["stump"]
    assert stump.get_property("is_surface") and "axe" in stump.contents
    assert "axe" not in game.player.location.items  # in the stump, not loose
    game.do_command("examine stump")
    assert _said(cap, "On it you see an axe.")
    game.do_command("take axe")
    assert "axe" in game.player.inventory and "axe" not in stump.contents
    # The listing is generated from live contents, so once the axe is gone the
    # examine text no longer claims it's there (no stale, baked-in mention).
    fresh = CaptureRenderer()
    game.parser.set_renderer(fresh)
    game.do_command("examine stump")
    assert not _said(fresh, "axe")


def test_row_back_from_the_middle_of_the_pond():
    # At the middle, the room tells you how to leave, and natural "row back" /
    # "row to shore" / "exit boat" phrasings all return you to shore.
    for back_cmd in ("row boat", "row back", "row to shore", "exit boat"):
        game, cap = _play(["out", "east", "south", "row boat"])  # -> Middle of Pond
        assert game.player.location.name == "Middle of Pond"
        assert _said(cap, "Row the boat to head back to shore")  # the hint is shown
        game.do_command(back_cmd)
        assert game.player.location.name == "Old Pond", back_cmd


def _at_trove():
    return _play(
        [
            "out",
            "east",
            "north",
            "take axe",
            "south",
            "west",
            "south",
            "give axe to smith",
            "out",
            "east",
            "north",
            "east",
            "enter moat",
            "move stone",
            "enter tunnel",
            "south",
        ]
    )


def test_treasure_holds_examinable_loot():
    game, cap = _at_trove()
    treasure = game.player.location.items["treasure"]
    assert treasure.get_property("is_container")
    assert set(treasure.contents) == {"gold", "sword", "ring"}
    game.do_command("examine treasure")
    assert _said(cap, "It contains")  # the hoard lists its loot on examine
    game.do_command("examine sword")
    assert _said(cap, "it's glowing")  # the rulebook's sword flavor
    game.do_command("examine ring")
    assert _said(cap, "The gem is enormous")


def test_stealing_from_the_hoard_wakes_the_dragon_and_kills_you():
    game, cap = _at_trove()
    game.do_command("take gold")  # try to steal
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "THIEF")
    assert game.characters["dragon"].get_property("awake")


def test_choosing_the_reward_takes_it_from_the_hoard_without_dying():
    game, cap = _at_trove()
    for c in ["wake dragon", "choose wits", "answer riddle a wise man", "choose sword"]:
        game.do_command(c)
    assert not game.is_game_over()
    assert "sword" in game.player.inventory  # the actual hoard sword, handed over
    assert "sword" not in game.player.location.items["treasure"].contents


def test_attacking_the_dragon_is_fatal():
    game, cap = _at_trove()
    game.do_command("attack dragon")
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "incinerates you") or _said(cap, "burns you alive")
    assert game.characters["dragon"].get_property("awake")


def test_lingering_wakes_the_dragon_but_leaving_is_safe():
    # Arrival is a grace turn -- the dragon only stirs; a second action wakes it.
    game, cap = _at_trove()
    assert not game.characters["dragon"].get_property("awake")  # just arrived
    assert _said(cap, "stirs in its sleep")
    game.do_command("look")  # lingering
    assert game.characters["dragon"].get_property("awake")
    # But you can enter and leave without waking it.
    game2, _ = _at_trove()
    game2.do_command("north")  # exit to the Underground
    assert game2.player.location.name == "Underground"
    assert not game2.characters["dragon"].get_property("awake")


def test_addressing_the_dragon_is_not_mistaken_for_a_move():
    # "dragon"/"tell dragon wits" used to route to GO (the action name "go" is a
    # substring of "dra-go-n"), producing "Treasure trove does not have an exit
    # 'None'". The fallback now matches action names on word boundaries.
    game, cap = _at_trove()
    for bad in ("dragon", "tell dragon", "tell dragon wits"):
        fresh = CaptureRenderer()
        game.parser.set_renderer(fresh)
        game.do_command(bad)
        assert not _said(fresh, "does not have an exit"), bad


# --- posed-prompt dialogue (#110): bare answers to the game's questions ----


def test_bare_answers_drive_the_whole_champion_dialogue():
    # Every dialogue fork now poses a prompt, so the player can answer in plain
    # words instead of the CHOOSE/ANSWER/SAY verbs: "wits" (choice), "a wise
    # man" (free-text riddle), "sword" (choice), "yes" (choice). The champion
    # walkthrough still wins with all four replaced by their bare answers.
    swap = {
        "choose wits": "wits",
        "answer riddle a wise man": "a wise man",
        "choose sword": "sword",
        "say yes": "yes",
    }
    cmds = [swap.get(c, c) for c in ac2.WALKTHROUGH_CHAMPION]
    game, _ = _play(cmds)
    assert game.is_won() and game.player.get_property("is_champion")


def test_lingering_wake_also_poses_the_wits_or_steel_prompt():
    # The dragon can wake two ways -- the WAKE DRAGON verb and lingering (the
    # dragon_stirs trigger). Both must pose the choice, or a bare "wits" after a
    # linger-wake fails ("I'm not sure what you want to do").
    game, cap = _at_trove()  # arrival: the dragon stirs
    game.do_command("look")  # lingering rouses it via the trigger
    assert game.characters["dragon"].get_property("awake")
    assert game.pending_prompt() is not None
    game.do_command("wits")  # the bare answer must work on this path too
    assert _said(cap, "Answer my riddle")  # routed to choose wits -> riddle posed


def test_bare_steel_answers_the_dragon_and_is_fatal():
    game, cap = _at_trove()
    game.do_command("wake dragon")
    game.do_command("steel")  # the choice prompt routes this to "choose steel"
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "breathes fire on you")


def test_a_wrong_free_text_riddle_answer_is_fatal():
    # The riddle is a free-text prompt: whatever you say is taken as the answer.
    game, cap = _at_trove()
    game.do_command("wake dragon")
    game.do_command("wits")
    game.do_command("a fool")  # forwarded to "answer riddle a fool" -> wrong
    assert game.is_game_over() and not game.is_won()
    assert _said(cap, "Wrong!")


def test_dialogue_prompt_is_not_modal_and_expires_on_leaving():
    game, cap = _at_trove()
    game.do_command("wake dragon")
    assert game.pending_prompt() is not None  # "wits or steel?" is posed
    game.do_command("look")  # a real verb still works mid-conversation
    assert not game.is_game_over()
    assert game.pending_prompt() is not None  # look didn't answer it
    game.do_command("north")  # walk away -> the question is moot
    assert game.player.location.name == "Underground"
    assert game.pending_prompt() is None


def test_drop_penny_in_well_scores_the_wish():
    game, _ = _play(["out", "drop penny in well"])
    assert "penny" not in game.player.inventory
    assert "wish" in game._scored_keys


# --- a surface in the world: the lamp on the dungeon-stairs ledge -----------


def test_lamp_rests_on_a_surface_and_is_takeable():
    game, cap = _play(
        [
            "out",
            "east",
            "north",
            "take axe",
            "south",
            "west",
            "south",
            "give axe to smith",
            "out",
            "east",
            "north",
            "east",
            "enter moat",
            "move stone",
            "enter tunnel",
            "south",
            "wake dragon",
            "choose wits",
            "answer riddle a wise man",
            "choose sword",
            "north",
            "east",
            "up",
        ]
    )
    assert game.player.location.name == "Dungeon Stairs"
    ledge = game.player.location.items["ledge"]
    assert ledge.get_property("is_surface") and "lamp" in ledge.contents

    game.do_command("examine ledge")
    assert _said(cap, "On it you see an old lamp.")
    game.do_command("take lamp")
    assert "lamp" in game.player.inventory and "lamp" not in ledge.contents
    game.do_command("put lamp on ledge")
    assert "lamp" in ledge.contents and "lamp" not in game.player.inventory


# --- issue #113: give word-order variants must still fire custom give-effects -
# "give <recipient> the <item>" (recipient-first) used to route to the built-in
# Give, which moves the item but skips the game's special effect. These lock in
# that the recipient-first phrasing produces the same outcome as the canonical
# "give <item> to <recipient>".


def test_champion_walkthrough_wins_with_reversed_give_to_king():
    cmds = list(ac2.WALKTHROUGH_CHAMPION)
    cmds[cmds.index("give sword to king")] = "give king the sword"
    game, _ = _play(cmds)
    assert game.is_won()
    assert game.player.get_property("is_champion")


def test_marriage_walkthrough_wins_with_reversed_give_to_rosemary():
    cmds = list(ac2.WALKTHROUGH_MARRIAGE)
    cmds[cmds.index("give blanket to rosemary")] = "give rosemary the blanket"
    game, _ = _play(cmds)
    assert game.is_won()
    assert game.player.get_property("is_married")


def test_reversed_give_slippers_to_hermit_still_rewards():
    # The built-in Give moves the slippers regardless of word order; the custom
    # effect (the king ends up shod) is what the recipient-first phrasing dropped.
    game, _ = _play(
        ["take slippers", "out", "east", "south", "south", "give hermit the slippers"]
    )
    assert "slippers" in game.characters["hermit"].inventory
    assert game.characters["king"].get_property("wears_slippers")
