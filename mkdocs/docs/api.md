# API reference

These pages are generated from the engine's own docstrings, so they always match
the installed code. For the conceptual picture, start with the
[design notes](https://github.com/ccb/agent-sandbox/tree/main/docs/design) on
GitHub; this page is the precise reference.

## Game loop

::: text_adventure_games.games.Game
    options:
      heading_level: 3

## Turn modes

The opt-in simultaneous turn mode — agents decide against a turn-start snapshot,
then commands resolve player-first and in initiative order.

::: text_adventure_games.turns
    options:
      heading_level: 3
      members:
        - Intent
        - gather_intents
        - resolve_order
        - run_simultaneous_round

## Agents (the ReAct layer)

::: text_adventure_games.npc.Agent
    options:
      heading_level: 3

::: text_adventure_games.npc.LLMAgent
    options:
      heading_level: 3

::: text_adventure_games.npc.ScriptedAgent
    options:
      heading_level: 3

## LLM client

Provider-agnostic LLM client (OpenAI / Anthropic adapters) plus the deterministic
offline `MockLlmClient` and `client_from_env()` for environment-variable gating.

::: text_adventure_games.llm_client
    options:
      heading_level: 3
      members:
        - LlmClient
        - LlmConfig
        - OpenAIClient
        - AnthropicClient
        - MockLlmClient
        - create_llm_client
        - client_from_env

## World model

The `Thing` hierarchy — locations, items, and characters — and the actions that
operate on them under the precondition/effect gate.

::: text_adventure_games.things.base.Thing
    options:
      heading_level: 3

::: text_adventure_games.actions.base.Action
    options:
      heading_level: 3
