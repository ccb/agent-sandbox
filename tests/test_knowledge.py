"""Tests for the per-character knowledge / belief layer (issue #45).

Covers four things:

  A. The pure data model (``Belief`` / ``Knowledge`` in ``knowledge.py``).
  B. ``render()`` -- the empty-render guard and the mock-brain authoring rules.
  C. Serialization round-trips (Knowledge alone and via Character save/load).
  D. Integration with ``Game.describe_for``: beliefs are injected, hidden
     things are perception-gated, and one NPC's beliefs stay isolated from
     other characters and from the shared command history.

Run with pytest::

    pytest tests/test_knowledge.py -v
"""

import pytest

from text_adventure_games import games, things
from text_adventure_games.knowledge import Belief, Knowledge
from text_adventure_games.npc import build_npc_context

# Beliefs the demo notebook seeds. Pinned here so the forbidden-substring test
# guards the exact text that ships in knowledge_demo.ipynb.
DEMO_BELIEFS = [
    "The tower door is locked and I hold the only brass key.",
    "The dungeon hides the castle's dark secret.",
    "I am hungry; the guard promised to feed me for guarding the bridge.",
    "The guard murdered me.",
    "The runes on the strange candle can banish me.",
    "My beloved is gone; I weep alone in the tower.",
]

# Substrings the mock ReAct brain (llm_client.py) keys on. A rendered belief
# section becomes part of an NPC's observation, so it must contain none of
# these or it would spoof a mock-brain rule or the _player_present split.
# The mock lowercases the observation, so these are matched case-insensitively.
FORBIDDEN_CI = [
    "inventory",
    "characters here:",
    "growls",
    "snarls",
    "' failed:",
    "last warning",
    "you don't belong here",
    "leave this place, mortal",
    "doesn't have a weapon",
    "eats the fish",
]
# describe_for emits these verbatim (clock AM/PM, the Turn: line); the mock
# brain does not lower() these particular checks, so guard them case-sensitively.
FORBIDDEN_CS = ["AM", "PM", "Turn:"]


# ----------------------------------------------------------------------
# A. Belief / Knowledge data model
# ----------------------------------------------------------------------


def test_belief_defaults():
    b = Belief("I hold the only brass key.")
    assert b.text == "I hold the only brass key."
    assert b.topic is None
    assert b.learned_turn is None


def test_add_appends_and_returns():
    k = Knowledge(owner="guard")
    returned = k.add("The tower door is locked.", topic="door")
    assert returned in k.beliefs
    assert len(k.beliefs) == 1
    assert returned.topic == "door"
    assert returned.learned_turn is None  # prior knowledge: no turn stamp


def test_learn_stamps_turn():
    k = Knowledge()
    b = k.learn("A stranger entered the courtyard.", turn=3, topic="stranger")
    assert b.learned_turn == 3
    assert b.topic == "stranger"
    assert b in k.beliefs


def test_knows_about():
    k = Knowledge()
    k.add("The tower door is locked.", topic="door")
    assert k.knows_about("door") is True
    assert k.knows_about("runes") is False
    # An empty/None topic never matches, even though some beliefs are topicless.
    k.add("A topicless belief.")
    assert k.knows_about(None) is False
    assert k.knows_about("") is False


def test_believes_is_case_insensitive():
    k = Knowledge()
    k.add("I hold the only Brass Key.")
    assert k.believes("brass key") is True
    assert k.believes("BRASS") is True
    assert k.believes("silver") is False


# ----------------------------------------------------------------------
# B. render()
# ----------------------------------------------------------------------


def test_render_empty_is_blank():
    # Load-bearing: an un-seeded character's observation must be unchanged.
    assert Knowledge().render() == ""


def test_render_format():
    k = Knowledge()
    k.add("The tower door is locked.")
    k.add("I hold the only brass key.")
    rendered = k.render()
    assert rendered.startswith("What you know:")
    bullets = [ln for ln in rendered.splitlines() if ln.startswith(" - ")]
    assert len(bullets) == 2  # one bullet per belief
    assert " - The tower door is locked." in rendered


def test_render_avoids_mock_brain_triggers():
    k = Knowledge()
    for text in DEMO_BELIEFS:
        k.add(text)
    rendered = k.render()
    lowered = rendered.lower()
    for bad in FORBIDDEN_CI:
        assert bad not in lowered, f"render leaked mock-brain trigger: {bad!r}"
    for bad in FORBIDDEN_CS:
        assert bad not in rendered, f"render leaked case-sensitive trigger: {bad!r}"


# ----------------------------------------------------------------------
# C. Serialization
# ----------------------------------------------------------------------


def test_knowledge_round_trip():
    k = Knowledge(owner="guard")
    k.add("The tower door is locked.", topic="door")
    k.learn("A stranger entered.", turn=2)
    restored = Knowledge.from_primitive(k.to_primitive())
    assert restored.owner == "guard"
    assert [b.text for b in restored.beliefs] == [b.text for b in k.beliefs]
    assert restored.beliefs[0].topic == "door"
    assert restored.beliefs[1].learned_turn == 2


def test_character_round_trip_preserves_beliefs():
    c = things.Character("guard", "A castle guard.", "I am the guard.")
    c.add_belief("The tower door is locked.", topic="door")
    c.add_belief("A stranger entered.", learned_turn=4)
    restored = things.Character.from_primitive(c.to_primitive())
    assert [b.text for b in restored.knowledge.beliefs] == [
        "The tower door is locked.",
        "A stranger entered.",
    ]
    assert restored.knowledge.knows_about("door") is True
    assert restored.knowledge.beliefs[1].learned_turn == 4


def test_character_load_without_knowledge_key():
    # Save files written before issue #45 have no "knowledge" key.
    c = things.Character("guard", "A castle guard.", "I am the guard.")
    data = c.to_primitive()
    del data["knowledge"]
    restored = things.Character.from_primitive(data)
    assert restored.knowledge.beliefs == []
    assert restored.knowledge.render() == ""


# ----------------------------------------------------------------------
# D. describe_for integration: injection, isolation, gating
# ----------------------------------------------------------------------


@pytest.fixture
def world():
    """A 2-room world with a player, a guard, and a troll all in the Field."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)

    player = things.Character("player", "a brave adventurer", "I explore.")
    guard = things.Character("guard", "a stern guard", "I am the guard.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")

    game = games.Game(field, player, characters=[guard, troll])
    field.add_character(guard)
    field.add_character(troll)
    return game, player, guard, troll


def test_beliefs_injected_into_describe_for(world):
    game, player, guard, troll = world
    guard.add_belief("The tower door is locked and I hold the only brass key.")
    obs = game.describe_for(guard)
    assert "What you know:" in obs
    assert "brass key" in obs


def test_empty_knowledge_adds_no_section(world):
    game, player, guard, troll = world
    # No beliefs seeded anywhere -> no observation should mention knowledge.
    assert "What you know:" not in game.describe_for(player)
    assert "What you know:" not in game.describe_for(troll)


def test_beliefs_are_isolated_between_characters(world):
    game, player, guard, troll = world
    secret = "Only the troll believes this peculiar fact."
    troll.add_belief(secret)

    assert secret in game.describe_for(troll)
    # One character's beliefs never leak into another's observation.
    assert secret not in game.describe_for(player)
    assert secret not in game.describe_for(guard)


def test_beliefs_not_in_command_history(world):
    game, player, guard, troll = world
    secret = "Only the troll believes this peculiar fact."
    troll.add_belief(secret)

    # Building the troll's context must not write its private beliefs into the
    # shared command history (which other NPCs read as "Recent events:").
    build_npc_context(troll, game)
    history_text = " ".join(e["content"] for e in game.parser.command_history)
    assert secret not in history_text


def test_secret_item_is_perception_gated(world):
    game, player, guard, troll = world
    field = player.location
    candle = things.Item("candle", "a strange candle", "A candle etched with runes.")
    candle.set_property("secret_topic", "runes")
    field.add_item(candle)

    # Nobody knows the topic yet: the candle is hidden from everyone.
    assert "candle" not in game.describe_for(troll)
    assert "candle" not in game.describe_for(guard)

    # The troll learns the topic and now perceives the candle; the guard still
    # cannot see it.
    troll.add_belief("The runes can banish a ghost.", topic="runes")
    assert "candle" in game.describe_for(troll)
    assert "candle" not in game.describe_for(guard)


def test_unflagged_items_always_visible(world):
    game, player, guard, troll = world
    field = player.location
    rock = things.Item("rock", "a plain rock", "An ordinary grey rock.")
    field.add_item(rock)
    # No secret_topic flag -> visible to a character with no knowledge at all.
    assert "rock" in game.describe_for(troll)


def test_secret_character_is_perception_gated(world):
    game, player, guard, troll = world
    field = player.location
    spy = things.Character("spy", "a hidden spy", "I lurk unseen.")
    spy.set_property("secret_topic", "conspiracy")
    field.add_character(spy)

    assert "spy" not in game.describe_for(troll)
    troll.add_belief("There is a conspiracy afoot.", topic="conspiracy")
    assert "spy" in game.describe_for(troll)
