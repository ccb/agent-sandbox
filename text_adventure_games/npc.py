from __future__ import annotations

"""Compatibility shim. NPC cognition now lives in ``agents.py`` (issue #3).

These factories are retained so existing games keep working; each returns a
``(character, game) -> None`` behavior backed by an Agent. New code should use
``text_adventure_games.agents`` directly.
"""

from .agents import Agent, LLMAgent, ScriptedAgent

__all__ = [
    "Agent",
    "LLMAgent",
    "ScriptedAgent",
    "build_npc_context",
    "make_react_behavior",
    "make_hybrid_behavior",
]


def build_npc_context(character, game) -> str:
    """Back-compat helper: the observation an Agent would build."""
    return Agent().observe(character, game)


def make_react_behavior(llm_client, max_retries=1):
    """Return a behavior callable backed by an LLMAgent."""
    agent = LLMAgent(llm_client, max_retries=max_retries)

    def behavior(character, game):
        agent.take_turn(character, game)

    return behavior


def make_hybrid_behavior(llm_client, scripted_behavior, max_retries=1):
    """Return a behavior callable: LLMAgent with a ScriptedAgent fallback."""
    agent = LLMAgent(
        llm_client,
        fallback=ScriptedAgent(scripted_behavior),
        max_retries=max_retries,
    )

    def behavior(character, game):
        agent.take_turn(character, game)

    return behavior
