"""Perception Layer 1 -- sight veils gate what a location reveals.

The load-bearing guarantee is *zero-cost*: a location with no veils and a
non-blind observer renders exactly as before (proven by the rest of the suite
staying green). These tests cover the opt-in behaviour and, crucially, that the
player's ``describe`` and an agent's ``describe_for`` share one perception -- so
darkness hides the same things from both.
"""

from text_adventure_games import games
from text_adventure_games.things import Location, Character, Item
from text_adventure_games.enums import Property
from text_adventure_games.perception import Darkness, Fog, Sight, sight_for


def _world():
    """A crypt (with a torch item and an NPC) opening north to a corridor."""
    crypt = Location("Crypt", "A cramped stone crypt.")
    corridor = Location("Corridor", "A long corridor.")
    crypt.add_connection("north", corridor)

    idol = Item("idol", "a jade idol", "A small jade idol rests on a shelf.")
    idol.set_property("gettable", True)
    crypt.add_item(idol)

    ghoul = Character("ghoul", "a ghoul", "A pale ghoul lurks in the corner.")
    crypt.add_character(ghoul)

    player = Character("hero", "the hero", "You, a tomb-robber.")
    crypt.add_character(player)

    game = games.Game(crypt, player, characters=[ghoul])
    return game, crypt, player, ghoul


def _lit_torch():
    torch = Item("torch", "a torch", "A burning torch.")
    torch.set_property(Property.IS_LIT, True)
    return torch


# --- zero-cost default -------------------------------------------------------


def test_a_plain_room_is_seen_clearly_and_fully():
    game, crypt, player, _ = _world()
    assert sight_for(player, crypt)[0] is Sight.CLEAR
    out = game.describe()
    assert "jade idol" in out          # items shown
    assert "Corridor" in out           # exits shown
    assert "ghoul" in out              # characters shown


# --- Darkness ----------------------------------------------------------------


def test_darkness_hides_the_whole_room_from_the_player():
    game, crypt, player, _ = _world()
    crypt.obscure(Darkness())
    out = game.describe()
    assert "pitch dark" in out.lower()
    assert "jade idol" not in out      # contents hidden
    assert "Exits:" not in out         # exits hidden
    assert "ghoul" not in out          # characters hidden


def test_a_lit_light_reveals_a_dark_room():
    game, crypt, player, _ = _world()
    crypt.obscure(Darkness())
    player.add_to_inventory(_lit_torch())
    out = game.describe()
    assert "pitch dark" not in out.lower()
    assert "jade idol" in out
    assert "Corridor" in out


def test_darkness_hides_the_room_from_an_agent_too():
    """The anti-drift guarantee: an NPC observing a dark room via describe_for
    is blinded by the same veil that blinds the player."""
    game, crypt, player, ghoul = _world()
    crypt.obscure(Darkness())
    obs = game.describe_for(ghoul)
    assert "pitch dark" in obs.lower()
    assert "jade idol" not in obs
    assert "Items here:" not in obs
    # ...but the agent still knows its own state -- that's not location perception
    assert "Available actions:" in obs


# --- Fog (DIM) ---------------------------------------------------------------


def test_fog_shows_the_room_and_exits_but_not_its_contents():
    game, crypt, player, _ = _world()
    crypt.obscure(Fog())
    assert sight_for(player, crypt)[0] is Sight.DIM
    out = game.describe()
    assert "Corridor" in out           # exits still shown at DIM
    assert "jade idol" not in out      # contents hidden at DIM
    assert "ghoul" not in out


# --- blindness (observer-side) -----------------------------------------------


def test_a_blind_observer_sees_nothing_even_in_a_plain_room():
    game, crypt, player, _ = _world()
    player.set_property("blind", True)
    assert sight_for(player, crypt)[0] is Sight.NONE
    out = game.describe()
    assert "jade idol" not in out
    assert "Exits:" not in out
