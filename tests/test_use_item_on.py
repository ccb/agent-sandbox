"""Tests for the reusable ``USE X ON Y`` pattern (``actions.use_item_on``).

The factory is the engine's answer to the two-object interaction every Parsely
game needs (``USE WAND ON OOZE``, ``HIT MAN WITH KETTLE``, ``THROW JAVELIN AT
DEMON``). These tests build a tiny one-room world and exercise the gate
(item held, target present, optional ``requires``) and the effect/consume/
narration paths.
"""

import pytest

from text_adventure_games import games, things
from text_adventure_games.actions import use_item_on
from text_adventure_games.reporting import CaptureRenderer, Channel


def _world(custom_actions):
    """A single room with the player holding a wand and an ooze (a character)
    and a frozen-able statue (an item) standing in the room."""
    cave = things.Location("Cave", "A dripping cave.")
    player = things.Character("player", "the player", "I explore.")
    ooze = things.Character("ooze", "a green ooze", "I ooze.")
    cave.add_character(ooze)
    wand = things.Item("wand", "an icy wand", "It hums with frost.")
    wand.set_property("gettable", True)
    player.add_to_inventory(wand)
    game = games.Game(cave, player, characters=[ooze], custom_actions=custom_actions)
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, cap


def _said(cap, substring):
    return any(
        substring in t
        for ch in (Channel.NARRATION, Channel.BLOCKED)
        for t in cap.texts(ch)
    )


def test_routes_and_applies_effect_on_a_character_target():
    UseWandOnOoze = use_item_on(
        "use wand on ooze",
        item="wand",
        target="ooze",
        effect=lambda a: a.target.set_property("is_frozen", True),
        success="A beam of frost freezes the ooze solid.",
    )
    game, cap = _world([UseWandOnOoze])

    game.do_command("use wand on ooze")

    assert game.characters["ooze"].get_property("is_frozen") is True
    assert _said(cap, "freezes the ooze solid")


def test_registered_under_its_action_name():
    UseWandOnOoze = use_item_on("use wand on ooze", item="wand", target="ooze")
    game, _ = _world([UseWandOnOoze])
    assert "use wand on ooze" in game.parser.actions


def test_blocks_when_item_not_held():
    UseWandOnOoze = use_item_on(
        "use wand on ooze",
        item="wand",
        target="ooze",
        effect=lambda a: a.target.set_property("is_frozen", True),
    )
    game, cap = _world([UseWandOnOoze])
    # Take the wand away so the actor isn't holding it.
    game.player.discard_item(game.player.inventory["wand"])

    game.do_command("use wand on ooze")

    assert not game.characters["ooze"].get_property("is_frozen")
    assert _said(cap, "aren't holding the wand")


def test_blocks_when_target_absent():
    UseWandOnOoze = use_item_on(
        "use wand on ooze",
        item="wand",
        target="ooze",
        effect=lambda a: a.target.set_property("is_frozen", True),
    )
    game, cap = _world([UseWandOnOoze])
    game.start_at.remove_character(game.characters["ooze"])

    game.do_command("use wand on ooze")

    assert _said(cap, "no ooze here")


def test_requires_gate_blocks_with_its_message():
    # The ooze can only be frozen while it's still wet.
    UseWandOnOoze = use_item_on(
        "use wand on ooze",
        item="wand",
        target="ooze",
        requires=lambda a: (
            None if a.target.get_property("is_wet") else "The ooze has dried up."
        ),
        effect=lambda a: a.target.set_property("is_frozen", True),
    )
    game, cap = _world([UseWandOnOoze])

    game.do_command("use wand on ooze")  # ooze isn't wet -> blocked

    assert not game.characters["ooze"].get_property("is_frozen")
    assert _said(cap, "dried up")

    game.characters["ooze"].set_property("is_wet", True)
    game.do_command("use wand on ooze")  # now it works

    assert game.characters["ooze"].get_property("is_frozen") is True


def test_consume_removes_the_item():
    ThrowJavelin = use_item_on(
        "throw javelin at ooze",
        item="javelin",
        target="ooze",
        verb="throw",
        preposition="at",
        consume=True,
        success="The javelin skewers the ooze.",
    )
    game, cap = _world([ThrowJavelin])
    javelin = things.Item("javelin", "a bronze javelin")
    javelin.set_property("gettable", True)
    game.player.add_to_inventory(javelin)

    game.do_command("throw javelin at ooze")

    assert "javelin" not in game.player.carried_items()
    assert _said(cap, "skewers the ooze")


def test_default_narration_when_no_effect_or_success():
    UseWandOnOoze = use_item_on("use wand on ooze", item="wand", target="ooze")
    game, cap = _world([UseWandOnOoze])

    game.do_command("use wand on ooze")

    assert _said(cap, "uses the wand on the ooze")


def test_targets_an_item_in_the_room():
    UseWandOnStatue = use_item_on(
        "use wand on statue",
        item="wand",
        target="statue",
        effect=lambda a: a.target.set_property("is_frozen", True),
        success="Frost creeps across the statue.",
    )
    game, cap = _world([UseWandOnStatue])
    statue = things.Item("statue", "a stone statue")
    statue.set_property("gettable", False)
    game.start_at.add_item(statue)

    game.do_command("use wand on statue")

    assert game.start_at.items["statue"].get_property("is_frozen") is True
    assert _said(cap, "Frost creeps across the statue")
