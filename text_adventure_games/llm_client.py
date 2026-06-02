"""Provider-agnostic LLM client abstraction.

Defines a Protocol for LLM interaction and concrete adapters for OpenAI and
Anthropic. Everything works without either SDK installed -- imports are lazy
so the base package has no hard dependency on them.

Usage::

    from text_adventure_games.llm_client import LlmConfig, create_llm_client

    config = LlmConfig(provider="openai", model="gpt-4o-mini")
    client = create_llm_client(config)
    response = client.chat([{"role": "user", "content": "Hello"}])
"""

from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LlmClient(Protocol):
    """Minimal interface for LLM interaction."""

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str | None:
        """Send a chat completion request. Returns text or None on failure."""
        ...

    def count_tokens(self, text: str) -> int:
        """Estimate the number of tokens in *text*."""
        ...


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class LlmConfig:
    """Configuration for creating an LLM client."""

    provider: str  # "openai" or "anthropic"
    api_key: str | None = None  # falls back to env vars
    model: str | None = None  # defaults per provider
    max_output_tokens: int = 256
    max_context_tokens: int = 8000
    base_url: str | None = None  # e.g. Helicone proxy
    verbose: bool = False


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------

_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class OpenAIClient:
    """Wraps the ``openai`` Python SDK (lazy-imported)."""

    def __init__(self, config: LlmConfig):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "The openai package is required. Install with: pip install openai"
            )
        api_key = config.api_key or os.environ.get("OPENAI_API_KEY")
        kwargs: dict = {"api_key": api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = openai.OpenAI(**kwargs)
        self._model = config.model or _DEFAULT_OPENAI_MODEL
        self._verbose = config.verbose
        # Lazy tokenizer
        self._tokenizer = None

    def _get_tokenizer(self):
        if self._tokenizer is None:
            try:
                import tiktoken

                self._tokenizer = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                self._tokenizer = None
        return self._tokenizer

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str | None:
        try:
            if self._verbose:
                print(json.dumps(messages, indent=2))
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0,
                frequency_penalty=0,
                presence_penalty=0,
            )
            return response.choices[0].message.content
        except Exception as e:
            if self._verbose:
                print(f"OpenAI API error: {e}")
            return None

    def count_tokens(self, text: str) -> int:
        tokenizer = self._get_tokenizer()
        if tokenizer is not None:
            return len(tokenizer.encode(text))
        # Fallback heuristic
        return len(text) // 4


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------

_DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"


class AnthropicClient:
    """Wraps the ``anthropic`` Python SDK (lazy-imported)."""

    def __init__(self, config: LlmConfig):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "The anthropic package is required. Install with: pip install anthropic"
            )
        api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = config.model or _DEFAULT_ANTHROPIC_MODEL
        self._verbose = config.verbose

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str | None:
        try:
            # Extract system message for Anthropic's separate system parameter
            system_text = None
            chat_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_text = msg["content"]
                else:
                    content = msg["content"]
                    # Anthropic rejects assistant messages with trailing whitespace
                    if msg["role"] == "assistant":
                        content = content.rstrip()
                    chat_messages.append({"role": msg["role"], "content": content})

            if self._verbose:
                print(json.dumps(messages, indent=2))

            kwargs = {
                "model": self._model,
                "messages": chat_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if system_text:
                kwargs["system"] = system_text

            response = self._client.messages.create(**kwargs)
            return response.content[0].text
        except Exception as e:
            if self._verbose:
                print(f"Anthropic API error: {e}")
            return None

    def count_tokens(self, text: str) -> int:
        # Heuristic: ~4 chars per token
        return len(text) // 4


# ---------------------------------------------------------------------------
# Mock adapter (for offline tests and local development)
# ---------------------------------------------------------------------------


class MockLlmClient:
    """A fake `LlmClient` that returns scripted responses, used to unit-test the agent layer,
      deterministically and for free -- no SDK, no network, no API key.

    The `responses` argument may be either:
    * a list of strings (or `None`) -- returned one per `chat` call
      in order (first-in, first-out). Once the list is exhausted, `chat`
      returns `default`.
    * a callable `(messages, max_tokens, temperature) -> str | None` --
      called to compute the response each time. Use this when a test needs to
      react to the prompt, e.g. to pick one of several numbered options.

    Returning `None` simulates an API failure, which exercises the
    graceful-fallback paths in the parser and the ReAct loop.

    Every call is recorded in `calls` so tests can assert on what was
    sent to the model.

    Example:

        client = MockLlmClient(["go north"])
        client.chat([{"role": "user", "content": "what do you do?"}])  # -> "go north"

        # React to the prompt:
        def pick_first(messages, max_tokens, temperature):
            return "0"
        client = MockLlmClient(pick_first)
    """

    def __init__(self, responses=None, default: str | None = ""):
        if callable(responses):
            self._responder = responses
            self._queue = None
        else:
            self._responder = None
            self._queue = list(responses) if responses is not None else []
        self._default = default
        # A log of every chat() call, for test assertions.
        self.calls: list[dict] = []

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str | None:
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if self._responder is not None:
            return self._responder(messages, max_tokens, temperature)
        if self._queue:
            return self._queue.pop(0)
        return self._default

    def count_tokens(self, text: str) -> int:
        # Heuristic: ~4 chars per token (matches the Anthropic adapter).
        return len(text) // 4


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "openai": OpenAIClient,
    "anthropic": AnthropicClient,
}


def create_llm_client(config: LlmConfig) -> LlmClient:
    """Create an LLM client from a config."""
    provider = config.provider.lower()
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider '{provider}'. Choose from: {list(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[provider](config)


# ---------------------------------------------------------------------------
# Utility: context length limiting (ported from GptParser)
# ---------------------------------------------------------------------------


def limit_context_length(
    messages: list[dict],
    max_tokens: int,
    token_counter,
    max_turns: int = 1000,
) -> list[dict]:
    """Trim *messages* to fit within *max_tokens*, keeping the most recent.

    Args:
        messages: List of ``{"role": ..., "content": ...}`` dicts.
        max_tokens: Maximum total token budget.
        token_counter: A callable ``(str) -> int`` that counts tokens.
        max_turns: Maximum number of messages to keep.

    Returns:
        A (possibly shorter) list of messages, preserving order.
    """
    total_tokens = 0
    limited: list[dict] = []
    for message in reversed(messages):
        msg_tokens = token_counter(message["content"])
        if total_tokens + msg_tokens > max_tokens:
            break
        total_tokens += msg_tokens
        limited.append(message)
        if len(limited) >= max_turns:
            break
    return list(reversed(limited))
