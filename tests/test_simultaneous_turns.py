"""Offline tests for the simultaneous turn mode (issue #25).

The gather -> resolve round (``turns.py``, opted into with
``Game(..., turn_mode="simultaneous")``) makes NPC agents decide against the
turn-start snapshot and settles same-turn contention at resolve time. This
suite drives it entirely with ``ScriptedAgent`` — deterministic, offline, no
API key — following the tiny-world fixture style of ``test_agent_layer.py``.

Run with pytest::

    pytest tests/test_simultaneous_turns.py -v
"""

import pytest

from text_adventure_games import games, things
from text_adventure_games.llm_client import MockLlmClient
from text_adventure_games.npc import ScriptedAgent, make_react_behavior
from text_adventure_games.webapp.web_parser import WebParser


class CountingRule:
    """A ScriptedAgent rule that records each observation it is asked about
    and answers from a fixed script (returning None once the script runs out).

    The recorded observations let tests assert *when* an agent was consulted
    (gather vs. resolve-retry) and *what* it saw at each point.
    """

    def __init__(self, replies):
        self.replies = list(replies)
        self.observations = []

    def __call__(self, observation):
        self.observations.append(observation)
        index = len(self.observations) - 1
        if index < len(self.replies):
            return self.replies[index]
        return None


def make_world(turn_mode="simultaneous", with_gem=True):
    """One room holding the player and two NPCs (alice gathered before bob),
    plus an optionally placed gettable gem for contention tests."""
    room = things.Location("Room", "A bare stone room.")
    player = things.Character("player", "the hero", "I act.")
    alice = things.Character("alice", "a quick npc", "I grab things.")
    bob = things.Character("bob", "a sturdy npc", "I grab things.")

    game = games.Game(room, player, characters=[alice, bob], turn_mode=turn_mode)
    room.add_character(alice)
    room.add_character(bob)
    game.set_parser(WebParser(game))

    gem = None
    if with_gem:
        gem = things.Item("gem", "a sparkling gem")
        room.add_item(gem)
    return game, room, player, alice, bob, gem


def action_failed_events(game, actor_name):
    return [
        e for e in game.events if e.actor == actor_name and e.action == "action_failed"
    ]


# ----------------------------------------------------------------------
# Turn-mode plumbing
# ----------------------------------------------------------------------


def test_invalid_turn_mode_raises():
    room = things.Location("Room", "A bare stone room.")
    player = things.Character("player", "the hero", "I act.")
    with pytest.raises(Exception, match="invalid turn_mode"):
        games.Game(room, player, turn_mode="parallel")


def test_sequential_is_the_default_and_still_runs_behaviors():
    game, room, player, alice, bob, gem = make_world(turn_mode="sequential")
    assert game.turn_mode == "sequential"
    # A legacy behavior on the classic end_turn path: proves the default
    # mode's plumbing is untouched by the simultaneous branch.
    alice.set_behavior(lambda c, g: g.parser.parse_command("take gem", actor=c))
    assert game.do_command("look")
    assert "gem" in alice.inventory


# ----------------------------------------------------------------------
# Contention and resolve order
# ----------------------------------------------------------------------


def test_higher_initiative_wins_contested_item_and_loser_retries():
    game, room, player, alice, bob, gem = make_world()
    alice.set_property("initiative", 1)
    bob.set_property("initiative", 5)
    alice_rule = CountingRule(["take gem"])  # retry consults it again -> None
    bob_rule = CountingRule(["take gem"])
    alice.set_agent(ScriptedAgent(alice_rule))
    bob.set_agent(ScriptedAgent(bob_rule))

    assert game.do_command("look")

    # Both decided to take the gem, but bob resolves first and wins.
    assert "gem" in bob.inventory
    assert "gem" not in alice.inventory
    # Alice's reflect-retry fired: a second decide() call whose observation
    # names the failed command and the parser's reason.
    assert len(alice_rule.observations) == 2
    assert "'take gem' failed" in alice_rule.observations[1]
    # The conflict is recorded on the event log.
    assert len(action_failed_events(game, "alice")) == 1
    assert action_failed_events(game, "alice")[0].payload == {"command": "take gem"}


def test_initiative_ties_fall_back_to_gather_order():
    game, room, player, alice, bob, gem = make_world()
    # Neither has an initiative property; alice was gathered first and the
    # stable sort must keep her ahead of bob.
    alice.set_agent(ScriptedAgent(CountingRule(["take gem"])))
    bob.set_agent(ScriptedAgent(CountingRule(["take gem"])))

    assert game.do_command("look")

    assert "gem" in alice.inventory
    assert "gem" not in bob.inventory


def test_player_resolves_first_and_npcs_decide_against_snapshot():
    game, room, player, alice, bob, gem = make_world()
    alice_rule = CountingRule(["take gem"])
    alice.set_agent(ScriptedAgent(alice_rule))

    # The player grabs the very gem alice is deciding about.
    assert game.do_command("take gem")

    # Player-first resolution: the player has it, alice's command failed.
    assert "gem" in player.inventory
    assert "gem" not in alice.inventory
    assert len(action_failed_events(game, "alice")) == 1
    # Snapshot semantics: alice decided BEFORE the player's command resolved,
    # so her gather observation still listed the gem in the room.
    assert "gem" in alice_rule.observations[0]


# ----------------------------------------------------------------------
# Gather/resolve edge cases
# ----------------------------------------------------------------------


def test_character_killed_between_gather_and_resolve_does_not_act():
    game, room, player, alice, bob, gem = make_world()
    # A high-initiative legacy character who strikes bob down at resolve time,
    # AFTER bob has already gathered his command.
    charlie = things.Character("charlie", "an assassin", "I strike first.")
    game.add_character(charlie)
    room.add_character(charlie)
    charlie.set_property("initiative", 10)
    charlie.set_behavior(lambda c, g: g.characters["bob"].set_property("is_dead", True))
    bob_rule = CountingRule(["take gem"])
    bob.set_agent(ScriptedAgent(bob_rule))

    assert game.do_command("look")

    # Bob gathered an intent (one decide() call) but died before his resolve
    # slot, so his command never ran: the gem is untouched and there is no
    # failure event either — the command wasn't attempted at all.
    assert len(bob_rule.observations) == 1
    assert "gem" in room.items
    assert "gem" not in bob.inventory
    assert action_failed_events(game, "bob") == []


def test_failed_player_command_costs_no_turn_and_discards_intents():
    game, room, player, alice, bob, gem = make_world()
    alice_rule = CountingRule(["take gem"])
    alice.set_agent(ScriptedAgent(alice_rule))
    turn_before = game.turn

    # No exits exist, so the player's command fails its precondition.
    assert not game.do_command("go north")

    assert game.turn == turn_before
    # Alice's gathered intent was discarded: the decision was made (the
    # documented cost of snapshot semantics) but never resolved.
    assert len(alice_rule.observations) == 1
    assert "gem" in room.items
    assert "gem" not in alice.inventory


def test_agent_returning_none_sits_the_round_out():
    game, room, player, alice, bob, gem = make_world()
    alice.set_agent(ScriptedAgent(lambda observation: None))
    turn_before = game.turn

    assert game.do_command("look")

    # The round still advanced, but alice produced no trace and no events.
    assert game.turn == turn_before + 1
    npc_logs = [m for m in game.parser.messages if m["type"] == "npc_log"]
    assert npc_logs == []
    assert [e for e in game.events if e.actor == "alice"] == []
    assert "gem" in room.items


def test_legacy_behavior_only_character_acts_in_simultaneous_mode():
    game, room, player, alice, bob, gem = make_world()
    # No set_agent: alice is driven by the classic set_behavior bridge (a
    # ReAct loop over a mock LLM), which must still act at its resolve slot.
    alice.set_behavior(make_react_behavior(MockLlmClient(["take gem"])))

    assert game.do_command("look")

    assert "gem" in alice.inventory


def test_persona_lazy_adoption_at_gather():
    game, room, player, alice, bob, gem = make_world()
    agent = ScriptedAgent(lambda observation: None)
    assert agent.persona == ""
    alice.set_agent(agent)

    assert game.do_command("look")

    # Parity with make_react_behavior: an agent attached without a persona
    # takes on its character's at the first gather.
    assert agent.persona == alice.persona
