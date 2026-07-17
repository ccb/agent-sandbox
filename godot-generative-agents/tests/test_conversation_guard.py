"""maybe_converse: an agent holds at most one conversation per step (#187).

In a room of 3+ settled residents, ``conversation.find_conversation_pairs``
reports *every* eligible pair (A-B, A-C, B-C) and deliberately leaves the pick
to the caller. ``maybe_converse`` must take a matching: once someone has
conversed this step, later pairs that include them are skipped -- otherwise an
agent converses twice in one tick and double-writes its memory / chat frame.

Offline: scripted talkers, a hand-built two-tile game, no assets or brain.
"""

from backend.cognition import maybe_converse
from text_adventure_games.games import Game
from text_adventure_games.npc import ScriptedAgent
from text_adventure_games.things import Character, Location


def _talker(lines, *, done_on_last=True):
    """A ScriptedAgent that says *lines* in order (mirrors test_conversation)."""
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


def _room_of_three():
    """Three co-located, agent-driven residents (+ the player) in one room."""
    here = Location("Plaza", "the plaza")
    player = Character("player", "you", "")
    here.add_character(player)
    # 'a' opens without ending so 'b' gets a turn; every agent could talk.
    agents = {
        "a": _talker(["Hi"], done_on_last=False),
        "b": _talker(["Yo"]),
        "c": _talker(["Hey"]),
    }
    chars: dict = {}
    for nm in ("a", "b", "c"):
        ch = Character(nm, nm, "")
        ch.set_agent(agents[nm])
        here.add_character(ch)
        chars[nm] = ch
    return Game(here, player, characters=list(chars.values())), chars


def test_agent_converses_at_most_once_per_step():
    game, chars = _room_of_three()
    order = ["a", "b", "c"]
    state = {nm: {"performing": True, "path": None, "chat": None} for nm in order}
    frame = {nm: {} for nm in order}

    happened = maybe_converse(game, chars, state, frame, 5, {}, order)

    # Pairs (a,b),(a,c),(b,c) are all eligible; a first-come matching lets exactly
    # one fire and leaves the odd resident out. Without the guard every pair would
    # fire and a/b would each converse twice, clobbering their own chat frame.
    # Conversations are now multi-tick (#371): a<->b's opening line is said this
    # step but "b" hasn't replied with its done-flagged line yet, so nothing has
    # *completed* this step -- the return value counts completions, not starts.
    assert happened == 0
    assert [nm for nm in order if state[nm]["chat"]] == ["a", "b"]
    assert state["c"]["chat"] is None
    # The one meeting that fired is a single a<->b transcript on both cards.
    assert state["a"]["chat"] == state["b"]["chat"]
    assert frame["a"]["chat"] == state["a"]["chat"]
