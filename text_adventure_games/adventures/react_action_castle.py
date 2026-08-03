"""Action Castle fixture with NPCs driven by the engine's pure ReAct loop."""

from text_adventure_games.adventures.action_castle import build_game
from text_adventure_games.npc import make_react_behavior
from text_adventure_games.things.characters import GoalType

NPC_GOALS = {
    "troll": [("Keep intruders from crossing the drawbridge", GoalType.MEDIUM)],
    "guard": [("Stop strangers from entering the castle", GoalType.MEDIUM)],
    "ghost": [("Drive the living out of the dungeon", GoalType.SHORT)],
}


def build_llm_game(llm_client, embedding_client=None):
    """Build Action Castle with troll, guard, and ghost driven by ReAct."""
    game = build_game()
    for name, goals in NPC_GOALS.items():
        npc = game.characters[name]
        npc.persona = f"I am the {name}. {npc.persona}"
        for description, tier in goals:
            npc.add_goal(description, tier)
        npc.set_behavior(
            make_react_behavior(llm_client, embedding_client=embedding_client)
        )
    return game
