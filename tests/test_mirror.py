"""A reflective mirror (engine feature): EXAMINE on an ``is_mirror`` item composes
the looker's live appearance -- their ``appearance`` traits + what they're wearing
-- with a non-descript fallback, instead of canned text that goes stale."""

from text_adventure_games import games, things
from text_adventure_games.actions import things as thing_actions
from text_adventure_games.reporting import CaptureRenderer, Channel


def _world():
    room = things.Location("Hall", "A plain hall.")
    player = things.Character("you", "the looker", "I look.")
    mirror = things.Item("mirror", "a mirror", "A plain mirror.")
    mirror.set_property("is_mirror", True)
    room.add_item(mirror)
    game = games.Game(room, player, characters=[])
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, room, player, mirror, cap


def _said(cap, sub):
    return any(
        sub in t for ch in (Channel.NARRATION, Channel.BLOCKED) for t in cap.texts(ch)
    )


def _examine_mirror(game, player):
    thing_actions.Examine(game, "examine mirror", actor=player)()


def test_reflects_appearance_and_worn():
    game, room, player, mirror, cap = _world()
    player.appearance = {"hair": "Your hair is wild."}
    player.worn["gown"] = things.Item("gown", "a fine gown")
    player.worn["tiara"] = things.Item("tiara", "a tiara")
    _examine_mirror(game, player)
    assert _said(cap, "A plain mirror.")  # the frame description first
    assert _said(cap, "Your hair is wild.")
    assert _said(cap, "You're wearing a fine gown and a tiara.")


def test_reflection_is_live_not_canned():
    game, room, player, mirror, cap = _world()
    player.appearance = {"hair": "Your hair is long."}
    player.appearance["hair"] = "Your hair is short now."  # a later edit
    _examine_mirror(game, player)
    assert _said(cap, "Your hair is short now.")
    assert not _said(cap, "Your hair is long.")


def test_fallback_when_no_traits_or_clothing():
    game, room, player, mirror, cap = _world()
    _examine_mirror(game, player)
    assert _said(cap, "You see yourself and the room reflected back at you")


def test_reflects_room_only_when_flagged():
    game, room, player, mirror, cap = _world()
    mirror.set_property("mirror_reflects_room", True)
    _examine_mirror(game, player)
    assert _said(cap, "Behind you, the Hall is reflected")


def test_appearance_survives_serialization():
    player = things.Character("you", "the looker", "I look.")
    player.appearance = {"hair": "Your hair is wild."}
    restored = things.Character.from_primitive(player.to_primitive())
    assert restored.appearance == {"hair": "Your hair is wild."}
