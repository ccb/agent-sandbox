# LLM client

Provider-agnostic LLM client (OpenAI / Anthropic adapters) plus the deterministic
offline `MockLlmClient` and `client_from_env()` for environment-variable gating.

::: text_adventure_games.llm_client
    options:
      heading_level: 2
      members:
        - LlmClient
        - LlmConfig
        - OpenAIClient
        - AnthropicClient
        - MockLlmClient
        - create_llm_client
        - client_from_env
