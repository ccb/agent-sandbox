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


def test_give_axe_to_smith_sharpens_it_in_place():
    game, _ = _play(
        [
            "out",
            "east",
            "north",
            "take axe",
            "south",
            "west",
            "south",
            "give axe to smith",
        ]
    )
    axe = game.player.inventory.get("axe")
    assert axe is not None and axe.get_property("is_sharp")


def test_drop_penny_in_well_scores_the_wish():
    game, _ = _play(["out", "drop penny in well"])
    assert "penny" not in game.player.inventory
    assert "wish" in game._scored_keys
