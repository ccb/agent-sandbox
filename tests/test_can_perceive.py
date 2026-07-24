"""The character-level perception seam ``Game.can_perceive`` (issue #662).

``perceivable_locations`` decides which *rooms* an agent sees into (issue #80);
``can_perceive`` decides which of the things standing in those rooms it actually
perceives. The default is True -- room granularity, exactly the pre-seam
behavior, so every existing game is unchanged -- and a game whose locations span
real distance (the Godot sim's TiledGame, where one "room" is the whole campus)
overrides it with a tile-distance check.

Both consumers are covered here: ``Game.describe_for`` (the observation text an
agent's brain reads) and ``AgentMemory._perceive_presence`` (the "I see X
nearby." records), because issue #662's bug was the same character leaking
through both.
"""

import pytest

from text_adventure_games import games, things
from text_adventure_games.memory import AgentMemory


@pytest.fixture
def field_world():
    """Player, troll, owl, and an acorn, all standing in one Field."""
    field = things.Location("Field", "An open grassy field.")
    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")
    owl = things.Character("owl", "a watchful owl", "I observe.")
    game = games.Game(field, player, characters=[troll, owl])
    field.add_character(troll)
    field.add_character(owl)
    field.add_item(things.Item("acorn", "a little acorn"))
    return game, player, troll, owl


def _presence_texts(mem):
    return {r.text for r in mem.records if "presence" in r.tags}


def test_default_gate_is_open_for_characters_and_items(field_world):
    game, player, troll, owl = field_world
    acorn = game.locations["Field"].items["acorn"]
    assert game.can_perceive(troll, owl)
    assert game.can_perceive(troll, acorn)


def test_describe_for_lists_everything_with_the_default_gate(field_world):
    game, player, troll, owl = field_world
    obs = game.describe_for(troll)
    assert "owl" in obs
    assert "player" in obs
    assert "acorn" in obs


def test_describe_for_omits_a_character_the_gate_hides(field_world):
    game, player, troll, owl = field_world
    game.can_perceive = lambda observer, thing: thing.name != "owl"
    obs = game.describe_for(troll)
    assert "owl" not in obs
    assert "player" in obs  # only the gated character disappears


def test_describe_for_omits_an_item_the_gate_hides(field_world):
    game, player, troll, owl = field_world
    game.can_perceive = lambda observer, thing: thing.name != "acorn"
    obs = game.describe_for(troll)
    assert "acorn" not in obs
    assert "owl" in obs


def test_presence_memory_respects_the_gate(field_world):
    game, player, troll, owl = field_world
    troll.vision_r = 1
    game.can_perceive = lambda observer, thing: thing.name != "owl"
    mem = AgentMemory(owner="troll")
    mem.perceive(game, troll)
    texts = _presence_texts(mem)
    assert "I see owl nearby." not in texts
    assert "I see player nearby." in texts
    assert "I see acorn nearby." in texts


def test_presence_renotices_a_thing_when_the_gate_reopens(field_world):
    """Walking out of perception range and back is a fresh sighting."""
    game, player, troll, owl = field_world
    troll.vision_r = 1
    in_range = {"player", "owl", "acorn"}
    game.can_perceive = lambda observer, thing: thing.name in in_range
    mem = AgentMemory(owner="troll")
    mem.perceive(game, troll)
    assert "I see owl nearby." in _presence_texts(mem)

    in_range.discard("owl")  # the owl flies out of range...
    mem.perceive(game, troll)
    in_range.add("owl")  # ...and comes back
    added = mem.perceive(game, troll)
    assert any(r.text == "I see owl nearby." for r in added)
