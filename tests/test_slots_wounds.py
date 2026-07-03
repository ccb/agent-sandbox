"""Vaarn item slots and wounds (slots.py) -- the shared carrying/harm gauge.

Opt-in and zero-cost: with no slot_capacity set, nothing changes (the rest of
the suite is the proof; the first test here is the explicit one). With it set:
GET refuses past the hard max and warns at the encumbered transition; an
encumbered mover clatters (a real sound) and cannot use climb-marked exits;
wounds fill the same slots and kill when they alone fill capacity.
"""

import random

from text_adventure_games import games
from text_adventure_games.things import Location, Character, Item
from text_adventure_games.slots import Wound, roll_wound
from text_adventure_games.reporting import CaptureRenderer, Channel


def _world(capacity=None):
    """A yard strewn with rocks, a cliff exit marked as a climb."""
    yard = Location("Yard", "A yard strewn with rocks.")
    ledge = Location("Ledge", "A high ledge.")
    cave = Location("Cave", "A cave.")
    yard.add_connection("up", ledge)  # the climb
    yard.add_connection("in", cave)  # a walk
    yard.set_property("climb_exits", {"up"})
    for i in range(1, 7):
        rock = Item(f"rock{i}", f"rock number {i}", "A heavy grey rock.")
        rock.set_property("gettable", True)
        rock.set_property("slots", 2)
        yard.add_item(rock)
    pebble = Item("pebble", "a small pebble", "A small blue pebble.")
    pebble.set_property("gettable", True)  # default cost: 1 slot
    yard.add_item(pebble)
    player = Character("you", "the player", "Me.")
    player.slot_capacity = capacity
    game = games.Game(yard, player, characters=[])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, cap


def _texts(cap):
    return " ".join(cap.texts(Channel.NARRATION) + cap.texts(Channel.BLOCKED)).lower()


# --- zero-cost default -------------------------------------------------------


def test_without_capacity_everything_is_unlimited():
    game, cap = _world(capacity=None)
    for i in range(1, 7):
        game.do_command(f"take rock{i}")
    assert len(game.player.inventory) == 6
    assert not game.player.is_encumbered()
    game.do_command("up")  # climbs are unrestricted too
    assert game.player.location.name == "Ledge"


# --- carrying ------------------------------------------------------------------


def test_a_full_pack_is_encumbered_and_capacity_is_a_hard_limit():
    game, cap = _world(capacity=4)
    game.do_command("take rock1")  # 2/4 -- fine
    assert not game.player.is_encumbered()
    game.do_command("take rock2")  # 4/4 -- FULL = encumbered (warned)
    assert game.player.is_encumbered()
    assert "full to the last slot" in _texts(cap)
    game.do_command("take pebble")  # 5 > 4 -- refused outright
    assert "pebble" not in game.player.inventory
    assert "cannot carry another thing" in _texts(cap)


def test_encumbered_cannot_climb_but_can_walk():
    game, cap = _world(capacity=4)
    for i in (1, 2):
        game.do_command(f"take rock{i}")  # 4/4 -- encumbered
    game.do_command("up")
    assert game.player.location.name == "Yard"  # the climb refused
    assert "climb is out of the question" in _texts(cap)
    game.do_command("in")
    assert game.player.location.name == "Cave"  # walking is allowed


def test_dropping_below_capacity_clears_encumbrance_and_the_climb():
    game, cap = _world(capacity=4)
    for i in (1, 2):
        game.do_command(f"take rock{i}")  # 4/4
    game.do_command("drop rock2")  # back to 2/4
    assert not game.player.is_encumbered()
    game.do_command("up")
    assert game.player.location.name == "Ledge"


def test_encumbered_movement_emits_a_clatter():
    game, cap = _world(capacity=4)
    for i in (1, 2):
        game.do_command(f"take rock{i}")  # 4/4 -- encumbered
    game.do_command("in")  # encumbered walk -> a sound event
    assert any(
        "overloaded pack" in (e.payload or {}).get("sound", "") for e in game.events
    )


# --- wounds --------------------------------------------------------------------


def test_wounds_fill_the_same_slots_as_gear():
    game, cap = _world(capacity=4)
    game.do_command("take rock1")  # 2/4
    game.player.add_wound(Wound("Bloody Gash", 1, "It will scar."))
    assert game.player.slots_used() == 3
    game.do_command("take rock2")  # 5 > 4 -- the wound's slot is real
    assert "rock2" not in game.player.inventory
    game.do_command("take pebble")  # 4/4 -- full
    assert game.player.is_encumbered()


def test_a_wound_displaces_random_gear_when_the_pack_is_full():
    game, cap = _world(capacity=4)
    for i in (1, 2):
        game.do_command(f"take rock{i}")  # 4/4 -- full
    fatal, dropped = game.player.add_wound(
        Wound("Bloody Gash", 1, "It will scar."), rng=random.Random(0)
    )
    assert not fatal
    assert len(dropped) == 1  # one 2-slot rock shed -> 3/4
    assert game.player.slots_used() == 3
    assert dropped[0].name in game.player.location.items  # it fell here


def test_wounds_alone_filling_capacity_kill():
    game, cap = _world(capacity=3)
    fatal, _ = game.player.add_wound(Wound("Major Fracture", 2, "..."))
    assert not fatal
    fatal, _ = game.player.add_wound(Wound("Bloody Gash", 1, "..."))  # 3/3 -> fatal
    assert fatal
    assert game.player.get_property("is_dead")


def test_heal_wound_removes_the_most_recent():
    game, cap = _world(capacity=4)
    game.player.add_wound(Wound("Bloody Gash", 1, "..."))
    game.player.add_wound(Wound("Stomach Wound", 1, "..."))
    healed = game.player.heal_wound()
    assert healed.name == "Stomach Wound"
    assert game.player.wound_slots() == 1


# --- the d20 table -------------------------------------------------------------


def test_roll_wound_specials():
    game, cap = _world(capacity=10)
    # 1: a scratch -- no wound.
    _, msgs, fatal = roll_wound(game.player, roll=1)
    assert not fatal and not game.player.wounds and "lucky" in msgs[0].lower()
    # 11: Major Fracture -- 2 slots.
    _, msgs, fatal = roll_wound(game.player, roll=11)
    assert game.player.wound_slots() == 2 and not fatal
    # 2: Damaged Item destroys a random carried item.
    game.do_command("take pebble")
    rng = random.Random(0)
    _, msgs, _ = roll_wound(game.player, roll=2, rng=rng)
    assert "pebble" not in game.player.inventory
    assert "smashed beyond use" in msgs[0]
    # 20: FATALITY.
    _, msgs, fatal = roll_wound(game.player, roll=20)
    assert fatal and game.player.get_property("is_dead")


# --- display ------------------------------------------------------------------


def test_inventory_reports_the_gauge_and_wounds():
    game, cap = _world(capacity=4)
    game.do_command("take rock1")
    game.player.add_wound(
        Wound("Bloody Gash", 1, "It will scar, if you live to own it.")
    )
    game.do_command("inventory")
    out = _texts(cap)
    assert "slots: 3/4" in out
    assert "bloody gash" in out
