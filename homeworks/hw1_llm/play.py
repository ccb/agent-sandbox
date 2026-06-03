"""Action Castle with LLM-driven NPCs (issue #5).

This is a thin wrapper around ``homeworks/hw1_solution`` -- the original game
file is untouched. We build the same world, then rewire the troll, guard, and
ghost with *pure* ReAct behaviors (``make_react_behavior``): there is no
scripted fallback, so every NPC action you see was reasoned by the agent,
routed through the parser, and gated by ``check_preconditions()``. If the LLM
produces nothing usable, the NPC simply does nothing that turn -- which makes
it obvious whether ReAct is actually driving.

(The webapp keeps the more forgiving ``make_hybrid_behavior``, which falls
back to the scripted behaviors on LLM failure.)

Run it from the repo root::

    LLM_PROVIDER=mock python -m homeworks.hw1_llm.play       # free, offline
    LLM_PROVIDER=anthropic python -m homeworks.hw1_llm.play  # a real LLM

The ``mock`` provider is a deterministic stand-in that picks in-character
commands from the same prompts a real model would see (see
``MockReActClient`` in ``text_adventure_games/llm_client.py``), so the whole
loop runs at no cost. Try walking to the drawbridge (``go out``, ``go
north``, ``go east``) and typing ``wait`` a few times: the troll growls,
snarls, then tries ``attack player`` -- which *fails* the precondition check
("troll doesn't have a weapon.") -- reflects on the failure, and retries with
``attack player with club``.
"""

from homeworks.hw1_solution import build_game
from text_adventure_games.llm_client import client_from_env
from text_adventure_games.npc import make_react_behavior

# Goals are sent to the agent in its system message, alongside the persona.
NPC_GOALS = {
    "troll": ["Keep intruders from crossing the drawbridge"],
    "guard": ["Stop strangers from entering the castle"],
    "ghost": ["Drive the living out of the dungeon"],
}


def build_llm_game(llm_client):
    """Build Action Castle with troll/guard/ghost driven purely by ReAct.

    Takes any LlmClient (a real provider, or MockReActClient for free,
    deterministic runs) and returns the game ready to play.
    """
    game = build_game()  # hw1_solution untouched; behaviors overwritten below
    for name, goals in NPC_GOALS.items():
        npc = game.characters[name]
        # The agent's prompt contains its persona but not its name -- tell it
        # who it is, so it (and the mock brain) can act in character.
        npc.persona = f"I am the {name}. {npc.persona}"
        npc.set_behavior(make_react_behavior(llm_client, goals=goals))
    return game


def main():
    llm = client_from_env()
    if llm is None:
        raise SystemExit(
            "Set LLM_PROVIDER to play with LLM-driven NPCs "
            "(try LLM_PROVIDER=mock for a free offline demo)."
        )
    game = build_llm_game(llm)
    game.game_loop()


if __name__ == "__main__":
    main()
