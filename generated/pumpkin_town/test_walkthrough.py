"""Tests for the Pumpkin Town port -- the spec of its supported commands.

Loads the sibling module by file path (so the test runs regardless of how
``test_gen`` is importable) and drives it through a CaptureRenderer, the house
pattern from docs/converting-parsely-games.md section 11.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from text_adventure_games import things
from text_adventure_games.reporting import CaptureRenderer, Channel


def _load_module():
    path = Path(__file__).resolve().parent / "pumpkin_town.py"
    spec = importlib.util.spec_from_file_location("pt_port", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pt = _load_module()


def _fresh():
    game = pt.build_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, cap


def _play(cmds, game=None):
    if game is None:
        game, cap = _fresh()
    else:
        cap = game.parser.renderer
    for c in cmds:
        game.do_command(c)
        if game.is_game_over():
            break
    return game, cap


def _said(cap, sub):
    """True if any player-facing text (narration or a blocked/failed message)
    contained *sub*."""
    return any(
        sub in t for ch in (Channel.NARRATION, Channel.BLOCKED) for t in cap.texts(ch)
    )


def _upto(cmd, inclusive=True):
    idx = pt.WALKTHROUGH.index(cmd)
    return pt.WALKTHROUGH[: idx + 1] if inclusive else pt.WALKTHROUGH[:idx]


# --- the happy path --------------------------------------------------------


def test_walkthrough_wins_at_full_score():
    game, _ = _play(pt.WALKTHROUGH)
    assert game.is_won()
    assert game.score == game.max_score == 100


def test_all_sixteen_treats_and_every_bonus_score():
    game, _ = _play(pt.WALKTHROUGH)
    expected = set(pt.TREATS.values()) | {
        "return",
        "bonus_train",
        "bonus_hell",
        "bonus_graveyard",
    }
    assert game._scored_keys == expected
    assert len(pt.TREATS) == 16  # 16 treats x5 + return 5 + 3 bonuses x5 = 100


# --- topology --------------------------------------------------------------


def test_every_exit_resolves_and_no_duplicate_destinations():
    game = pt.build_game()
    for loc in game.locations.values():
        dests = list(loc.connections.values())
        for dest in dests:
            assert dest is not None
            assert dest.name in game.locations
        names = [d.name for d in dests]
        assert len(names) == len(set(names)), f"{loc.name} has a duplicate exit"


def test_main_street_spokes_round_trip():
    # The diagonal spokes (northwest/southeast/...) don't auto-reverse, so every
    # spoke is wired by hand; make sure you can walk back from each.
    game = pt.build_game()
    spokes = {
        "north": "Cauldron Point",
        "northwest": "Tentacle Hill",
        "south": "Yum-Yum Candy Factory",
        "southeast": "Pitchfork Farms",
        "southwest": "Mucky-Muck Swamp",
        "east": "Forest of Death",
        "west": "Ghost Train",
    }
    main = game.locations["Main Street"]
    for direction, dest_name in spokes.items():
        dest = main.connections[direction]
        assert dest.name == dest_name
        assert main in dest.connections.values()  # a way back exists


# --- the coin / costume crux -----------------------------------------------


def test_coin_needs_the_hook_and_chewed_gum():
    setup = ["get bag", "take ghost costume", "take hook", "get bubble gum", "out"]
    game, cap = _play(setup + ["use hook on coin"])  # no gum on the hook yet
    assert not pt._is_holding(game.player, "coin")
    assert _said(cap, "stickier")
    _play(["chew gum", "stick gum on hook", "use hook on coin"], game=game)
    assert pt._is_holding(game.player, "coin")


def test_bare_hand_cannot_reach_the_coin():
    game, cap = _play(["get bag", "take ghost costume", "out", "get coin"])
    assert not pt._is_holding(game.player, "coin")
    assert _said(cap, "too big to fit")


def test_you_may_take_only_one_costume():
    game, cap = _play(["take ghost costume", "take pirate costume"])
    assert pt._costume(game.player) == "ghost"
    assert _said(cap, "only one costume")


# --- the candy-lab guard ---------------------------------------------------


def test_guard_blocks_a_non_ghost_but_a_ghost_sneaks_in():
    game, cap = _fresh()
    game.relocate(game.player, game.locations["Yum-Yum Candy Factory"])
    game.do_command("enter candy lab")
    assert game.player.location.name == "Yum-Yum Candy Factory"
    assert _said(cap, "factory is closed")
    pt._wear_costume(game.player, "ghost")
    game.do_command("enter candy lab")
    assert game.player.location.name == "Candy Lab"


def test_showing_the_id_satisfies_the_guard():
    game, _ = _fresh()
    game.relocate(game.player, game.locations["Yum-Yum Candy Factory"])
    game.player.add_to_inventory(things.Item("id badge", "an ID badge", "ID."))
    game.do_command("show id to guard")
    assert game.guard_satisfied
    game.do_command("enter candy lab")
    assert game.player.location.name == "Candy Lab"


# --- the Forest of Death gate ----------------------------------------------


def test_forest_blocks_the_way_until_a_trail_is_marked():
    game, cap = _fresh()
    game.relocate(game.player, game.locations["Forest of Death"])
    game.do_command("east")  # nothing to mark with -> blocked
    assert game.player.location.name == "Forest of Death"
    assert _said(cap, "Nameless")
    game.player.add_to_inventory(things.Item("candy corn", "candy corn", "Corn."))
    game.do_command("mark trail")
    game.do_command("east")
    assert game.player.location.name == "Abandoned Cathedral"


# --- the three pitfalls (each forfeits a +5 bonus) -------------------------


def test_boarding_without_a_fare_gets_you_kicked_off():
    game, cap = _fresh()
    game.relocate(game.player, game.locations["Ghost Train"])
    game.do_command("board train")  # no ghost costume, no coin
    assert game.kicked_off_train
    assert game.player.location.name == "Ghost Train"
    assert _said(cap, "boots you off")


def test_a_ghost_rides_free_and_keeps_the_coin():
    game, _ = _play(_upto("board train"))
    assert game.player.location.name == "Funland"
    assert pt._is_holding(game.player, "coin")  # fare not spent
    assert not game.kicked_off_train


def test_saying_yes_gets_you_kicked_out_of_hell():
    game, cap = _fresh()
    game.relocate(game.player, game.locations["Pumpkin Town Hell"])
    game.do_command("talk to devil")
    game.do_command("yes")  # answered via the posed prompt
    assert game.kicked_out_of_hell
    assert game.player.location.name == "Creepy Catacombs"
    assert _said(cap, "GET OUT")


def test_entering_the_swamp_without_the_cane_is_an_emergency_trip():
    game, cap = _fresh()
    pt._wear_costume(game.player, "ghost")
    game.relocate(game.player, game.locations["Mucky-Muck Swamp"])
    game.do_command("enter swamp")
    assert game.emergency_graveyard
    assert game.player.location.name == "Graveyard"
    assert pt._costume(game.player) == "hobo"  # ruined costume replaced
    assert _said(cap, "molasses")


def test_entering_the_lake_unarmed_is_an_emergency_trip():
    game, cap = _fresh()
    game.relocate(game.player, game.locations["Cauldron Point"])
    game.do_command("enter lake")
    assert game.emergency_graveyard
    assert game.beach_closed
    assert game.player.location.name == "Graveyard"
    assert _said(cap, "tentacle")


def test_eating_pixie_dust_is_an_emergency_trip():
    game, cap = _fresh()
    game.player.add_to_inventory(things.Item("pixie dust", "a vial", "Sugar."))
    game.do_command("eat pixie dust")
    assert game.emergency_graveyard
    assert game.player.location.name == "Graveyard"
    assert _said(cap, "sugar shock")


# --- the lake puzzle solved the intended way -------------------------------


def test_a_pitchfork_turns_the_tentacle_into_gummi_worms():
    game, _ = _fresh()
    game.relocate(game.player, game.locations["Cauldron Point"])
    game.player.add_to_inventory(things.Item("pitchfork", "a pitchfork", "Pointy."))
    game.do_command("enter lake")
    assert pt._is_holding(game.player, "gummi worms")
    assert not game.emergency_graveyard
    assert not game.beach_closed


# --- treats require the bag ------------------------------------------------


def test_treats_score_only_once_you_carry_the_bag():
    # Grab a treat (bubble gum) WITHOUT the bag: it shouldn't score yet.
    game, _ = _play(["take ghost costume", "get bubble gum"])
    assert "bubble_gum" not in game._scored_keys
    game.do_command("get bag")
    game.do_command("look")  # a turn passes; the trigger now scores it
    assert "bubble_gum" in game._scored_keys
