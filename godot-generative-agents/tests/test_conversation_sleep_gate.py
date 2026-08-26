"""maybe_converse must never pair a sleeping character into a conversation
(code review, 2026-08-13). A sleeping character stays `performing=True` with
no path (nothing un-latches it until drives.sleep_accumulation wakes it), so
before this fix it silently qualified for the `settled` proximity-pair scan;
separately, an explicit talk_to request aimed at a sleeping target was never
checked either. Both must now be dropped, the same way a dead resident
already is (mirrors conversation.can_converse's own is_dead check).

Offline: scripted talkers, a hand-built two-tile game, no assets or brain.
Mirrors test_conversation_guard.py's harness.
"""

from backend.cognition import maybe_converse
from text_adventure_games.enums import Property
from text_adventure_games.games import Game
from text_adventure_games.npc import ScriptedAgent
from text_adventure_games.things import Character, Location


def _talker(lines, *, done_on_last=True):
    it = iter(lines)
    agent = ScriptedAgent(lambda _obs: None)
    # maybe_converse reads a.agent.llm_client.context defensively; ScriptedAgent
    # (unlike LLMAgent) has no client, so give it a null one.
    agent.llm_client = None

    def rule(_observation, _partner_name):
        agent.last_dialogue_done = False
        line = next(it, None)
        if line is not None and done_on_last and line == lines[-1]:
            agent.last_dialogue_done = True
        return line

    agent.converse_rule = rule
    return agent


def _room_of_two(*, b_sleeping):
    here = Location("Plaza", "the plaza")
    player = Character("player", "you", "")
    here.add_character(player)
    agents = {"a": _talker(["Hi"], done_on_last=False), "b": _talker(["Yo"])}
    chars = {}
    for nm in ("a", "b"):
        ch = Character(nm, nm, "")
        ch.set_agent(agents[nm])
        here.add_character(ch)
        chars[nm] = ch
    if b_sleeping:
        chars["b"].set_property(Property.IS_SLEEPING, True)
    game = Game(here, player, characters=list(chars.values()))
    return game, chars


def test_sleeping_resident_is_never_paired_into_a_proximity_conversation():
    game, chars = _room_of_two(b_sleeping=True)
    order = ["a", "b"]
    state = {nm: {"performing": True, "path": None, "chat": None} for nm in order}
    frame = {nm: {} for nm in order}

    happened = maybe_converse(game, chars, state, frame, 5, {}, order)

    assert happened == 0
    assert state["a"]["chat"] is None
    assert state["b"]["chat"] is None


def test_talk_request_to_a_sleeping_target_is_dropped():
    game, chars = _room_of_two(b_sleeping=True)
    chars["a"].set_property("talk_request", "b")
    order = ["a", "b"]
    state = {nm: {"performing": True, "path": None, "chat": None} for nm in order}
    frame = {nm: {} for nm in order}

    happened = maybe_converse(game, chars, state, frame, 5, {}, order)

    assert happened == 0
    assert state["a"]["chat"] is None
    assert state["b"]["chat"] is None


def test_awake_residents_still_converse_unaffected():
    # Guard against an over-broad fix: two awake residents must still pair.
    game, chars = _room_of_two(b_sleeping=False)
    order = ["a", "b"]
    state = {nm: {"performing": True, "path": None, "chat": None} for nm in order}
    frame = {nm: {} for nm in order}

    happened = maybe_converse(game, chars, state, frame, 5, {}, order)

    assert happened == 0  # multi-tick: opened, not completed, this step (#371)
    assert state["a"]["chat"] == state["b"]["chat"]
    assert state["a"]["chat"] is not None
