"""Perception Layer 2 -- senses and probes.

In the dark, sight fails but other senses don't: EXAMINE falls back to the
passive senses (hearing/smell) a thing was tagged with, and the opt-in feel /
listen / smell probes reveal touch/hearing/smell on demand -- the "feel your way
in the dark" mechanism. All opt-in and zero-cost: untagged things and games that
never call enable_senses() behave exactly as before.
"""

from text_adventure_games import games
from text_adventure_games.things import Location, Character, Item
from text_adventure_games.enums import Property
from text_adventure_games.perception import Darkness, Sense


def _lit_torch():
    torch = Item("torch", "a torch", "A burning torch.")
    torch.set_property(Property.IS_LIT, True)
    return torch


def _dark_world(enable_senses=True, player_items=()):
    """A pitch-dark vault: a wind-chime (heard), a statue (felt), a plain urn
    (sight only), and a way north."""
    vault = Location("Vault", "A cold stone vault.")
    vault.obscure(Darkness())
    hall = Location("Hall", "A hall.")
    vault.add_connection("north", hall)

    chime = Item("chime", "a brass wind-chime", "A delicate brass wind-chime.")
    chime.set_property("gettable", False)
    chime.perceptible_by(Sense.HEARING, "A faint silver chiming drifts down.")
    vault.add_item(chime)

    statue = Item("statue", "a stone statue", "A weathered stone figure.")
    statue.set_property("gettable", False)
    statue.perceptible_by(Sense.TOUCH, "Cold, rough stone -- taller than you.")
    vault.add_item(statue)

    urn = Item("urn", "a clay urn", "A plain clay urn.")
    urn.set_property("gettable", False)
    vault.add_item(urn)

    player = Character("you", "the player", "Me.")
    for it in player_items:
        player.add_to_inventory(it)
    game = games.Game(vault, player, characters=[])
    if enable_senses:
        game.enable_senses()
    return game


def _say(game, cmd):
    from text_adventure_games.reporting import CaptureRenderer, Channel

    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.do_command(cmd)
    return " ".join(cap.texts(Channel.NARRATION)).lower()


# --- EXAMINE gated by sight --------------------------------------------------


def test_examine_in_the_dark_falls_back_to_a_heard_thing():
    game = _dark_world()
    out = _say(game, "examine chime")
    assert "silver chiming" in out  # heard, not seen
    assert "wind-chime" not in out  # the visual examine_text is withheld


def test_examine_a_touch_only_thing_in_the_dark_nudges_you_to_feel():
    game = _dark_world()
    out = _say(game, "examine statue")
    assert "too dark" in out
    assert "your hands might do" in out  # touch is active -> a diegetic nudge


def test_examine_a_plain_thing_in_the_dark_is_just_too_dark():
    game = _dark_world()
    out = _say(game, "examine urn")
    assert "too dark" in out
    assert "your hands might do" not in out  # no non-sight sense to offer


def test_examine_with_a_light_uses_the_visual_text():
    game = _dark_world(player_items=[_lit_torch()])
    out = _say(game, "examine statue")
    assert "weathered stone figure" in out  # sight text, exactly as normal
    assert "too dark" not in out


# --- the probes (opt-in) -----------------------------------------------------


def test_probes_are_opt_in():
    off = _dark_world(enable_senses=False)
    assert "feel" not in off.parser.actions
    on = _dark_world(enable_senses=True)
    for verb in ("feel", "listen", "smell"):
        assert verb in on.parser.actions


def test_feel_reveals_a_touch_thing_regardless_of_light():
    game = _dark_world()
    out = _say(game, "feel statue")
    assert "cold, rough stone" in out


def test_feel_around_reveals_exits_and_tactile_fixtures():
    game = _dark_world()
    out = _say(game, "feel")
    assert "a way north" in out  # exits are always feel-able
    assert "stone statue" in out  # the TOUCH fixture, by its noun-phrase


def test_listen_reveals_a_heard_thing():
    game = _dark_world()
    assert "silver chiming" in _say(game, "listen")
    assert "silver chiming" in _say(game, "listen to chime")


def test_smell_of_a_room_with_no_scents():
    game = _dark_world()
    assert "nothing in particular" in _say(game, "smell")
