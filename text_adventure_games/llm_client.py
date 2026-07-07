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
import time
import random
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Union

from .enums import LlmProvider
from .usage import RunLog, UsageLedger, record_call

# ---------------------------------------------------------------------------
# Resilience: retry with exponential backoff (issue #260)
# ---------------------------------------------------------------------------
#
# A real-LLM run is call-heavy -- a Penn day is thousands of provider calls -- so
# a transient 429 / 5xx / dropped connection must not abort the whole run. The
# provider SDKs retry internally, but those retries are invisible to the
# UsageLedger. So we set each SDK's own ``max_retries`` to 0 and own the loop
# here, recording every attempt (see the adapters) so retries stay observable in
# the ledger. The SDK's per-call ``timeout`` still guards against a hung socket.

# HTTP statuses worth retrying: request timeout, conflict, and rate limit, plus
# any 5xx server error. Matches the provider SDKs' own retryable set.
_RETRYABLE_STATUS = {408, 409, 429}

# Substrings of provider-SDK exception class names that signal a transient
# failure carrying no HTTP status (connection resets, socket timeouts). Matched
# on the class name so this module needs neither SDK installed -- and so tests
# can raise a lightweight stand-in exception.
_RETRYABLE_NAME_HINTS = (
    "ratelimit",
    "timeout",
    "apiconnection",
    "connection",
    "internalserver",
    "serviceunavailable",
    "overloaded",
)

# Backoff schedule (seconds): delay grows as base * 2**attempt, capped, with
# jitter so 25 agents don't retry in lockstep (a thundering herd).
_RETRY_BASE_DELAY = 0.5
_RETRY_MAX_DELAY = 30.0


def _is_retryable(exc: Exception) -> bool:
    """Return True if *exc* looks like a transient provider error worth retrying.

    Duck-typed so it works without either SDK installed: prefers an HTTP
    ``status_code`` when present (429/408/409 or any 5xx), else matches the
    exception class name against known transient-error types. A plain
    ``RuntimeError`` / ``ValueError`` is treated as non-retryable.
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status in _RETRYABLE_STATUS or status >= 500):
        return True
    name = type(exc).__name__.lower()
    return any(hint in name for hint in _RETRYABLE_NAME_HINTS)


def _retry_after(exc: Exception) -> float | None:
    """Read a ``Retry-After`` header (seconds) off *exc* if the SDK attached one.

    Honors the server's own backoff hint over our computed delay when present.
    Returns None when unavailable or unparseable.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        value = headers.get("retry-after")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _backoff_delay(
    attempt: int,
    base: float = _RETRY_BASE_DELAY,
    cap: float = _RETRY_MAX_DELAY,
    retry_after: float | None = None,
) -> float:
    """Delay before retry *attempt* (0-based): the server's hint if given, else
    exponential backoff (base * 2**attempt) with full jitter, capped at *cap*."""
    if retry_after is not None:
        return min(retry_after, cap)
    return min(base * (2**attempt) + random.uniform(0, base), cap)


def _retry_with_backoff(fn, *, max_retries: int, sleep=time.sleep, on_retry=None):
    """Call *fn* with up to ``max_retries`` retries on transient errors.

    Runs ``max_retries + 1`` attempts total. On a retryable exception with
    attempts remaining, invokes ``on_retry(attempt, exc)`` (used to record the
    failed attempt), sleeps for a backoff delay, then retries. Non-retryable
    errors and the final failure re-raise -- callers keep their existing
    ``except Exception -> None`` graceful-fallback contract.
    """
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt >= max_retries or not _is_retryable(exc):
                raise
            if on_retry is not None:
                on_retry(attempt, exc)
            sleep(_backoff_delay(attempt, retry_after=_retry_after(exc)))
    # Unreachable: the final attempt (attempt == max_retries) either returns its
    # result or re-raises above. Kept explicit so callers get fn()'s type back
    # (not `... | None`) and the loop can't silently fall through to None.
    raise RuntimeError("retry loop exhausted without returning or raising")


def _resilient_create(client, create_fn, *, provider: str, messages: list[dict]):
    """Run *create_fn* (one provider SDK call) with observable retries.

    Wraps only the network call, not the surrounding response parsing (a parse
    error is a bug, not a transient failure). Each failed-then-retried attempt is
    written to the ledger as a zero-cost :class:`~text_adventure_games.usage.CallRecord`
    with its ``attempt`` index set, so ``summary()["calls"]`` counts retries.
    Returns ``(response, latency_ms)`` for the successful attempt; re-raises on
    the final failure or a non-retryable error so the adapter's ``except`` turns
    it into ``None``.
    """
    timing: dict = {}
    attempts = {"n": 0}

    def _do():
        t0 = time.perf_counter()
        response = create_fn()
        timing["latency_ms"] = (time.perf_counter() - t0) * 1000.0
        return response

    def _on_retry(attempt: int, exc: Exception):
        ctx = getattr(client, "context", None)
        if ctx is not None:
            ctx["attempt"] = attempt
        record_call(
            getattr(client, "ledger", None),
            ctx,
            provider,
            getattr(client, "_model", provider),
            None,  # raw_usage: a rejected call bills nothing -> zero-cost record
            messages,
            None,
        )
        attempts["n"] = attempt + 1
        if getattr(client, "_verbose", False):
            print(f"{provider} call failed (attempt {attempt + 1}); retrying: {exc}")

    response = _retry_with_backoff(
        _do,
        max_retries=getattr(client, "_max_retries", 2),
        sleep=getattr(client, "_sleep", time.sleep),
        on_retry=_on_retry,
    )
    # Stamp the successful record with the attempt it landed on (0 = first try).
    ctx = getattr(client, "context", None)
    if ctx is not None:
        ctx["attempt"] = attempts["n"]
    return response, timing["latency_ms"]


def _preflight_key(client, provider: str, key_env: str, live_probe) -> None:
    """Shared key preflight: fail fast up front rather than deep in the loop.

    Always (offline, free): raise a clear ``ValueError`` when no API key is
    resolvable for a real provider. When ``LLM_PREFLIGHT`` is truthy, also run
    *live_probe* -- one cheap authenticated call -- and raise a clear
    ``ValueError`` if it fails, catching a bad/expired key before the run. The
    live check is opt-in so the default path stays offline and spends nothing.
    """
    if not getattr(client, "_api_key", None):
        raise ValueError(
            f"No API key for provider '{provider}'. Set {key_env} or LLM_API_KEY."
        )
    if os.environ.get("LLM_PREFLIGHT", "").lower() in ("1", "true"):
        try:
            live_probe()
        except Exception as e:
            raise ValueError(
                f"{provider} preflight failed -- the API key may be invalid or "
                f"the service unreachable: {e}"
            )


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

    def call_tool(
        self,
        messages: list[dict],
        tool: dict,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> dict | None:
        """Force the model to call the single named *tool* and return its
        arguments as a dict (validated by the provider), or None if tool
        calling is unavailable or no tool call came back."""
        ...

    def count_tokens(self, text: str) -> int:
        """Estimate the number of tokens in *text*."""
        ...

    def preflight(self) -> None:
        """Validate configuration before the run so failures surface up front.

        Real adapters raise a clear ``ValueError`` when no API key is resolvable
        (and, if ``LLM_PREFLIGHT`` is set, on a failed cheap live call). The mock
        is a no-op -- it needs no key and stays offline."""
        ...


# ---------------------------------------------------------------------------
# Normalized tool translation
# ---------------------------------------------------------------------------
#
# A "normalized" tool is a provider-agnostic dict:
#   {"name": str, "description": str, "parameters": <JSON Schema object>}
# These helpers translate it to each provider's wire shape. Keeping the
# translation in one place means tool *schemas* (built elsewhere) never need to
# know which provider is in use.


def _to_openai_tool(tool: dict) -> dict:
    """Translate a normalized tool dict to OpenAI's function-tool shape."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool["parameters"],
        },
    }


def _to_anthropic_tool(tool: dict) -> dict:
    """Translate a normalized tool dict to Anthropic's tool shape."""
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "input_schema": tool["parameters"],
    }


def _cacheable_system(system_text: str) -> list[dict]:
    """Wrap the system prompt as a single ``cache_control`` text block (#367).

    An agent's system prompt -- its persona and goals -- is byte-identical across
    the many decision/dialogue calls it makes, so it's the natural prompt-cache
    prefix. Marking it ``ephemeral`` means the shared prefix (Anthropic renders
    ``tools`` then ``system``, so a breakpoint on the system block caches both) is
    written once and re-read at ~0.1x input cost on every subsequent call; the
    ledger already bills ``cache_read_input_tokens`` at that rate (usage.py),
    it just never had a request set ``cache_control`` before.

    Prompt caching is GA -- no beta header. Below a model-dependent minimum prefix
    (Haiku 4.5: 4096 tokens; Sonnet 4.6: 2048) the API *silently* declines to
    cache -- no error, ``cache_creation_input_tokens`` stays 0 -- so this is a
    safe no-op for short personas and a real saving once the prefix is large
    enough (verify via the usage cache fields). A change anywhere in the prefix
    (persona, goals, tools) invalidates it, which is the correct behavior: those
    only change when the agent itself does.
    """
    return [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


# The normalized tool for picking one option from a numbered list (used by the
# LLM parser to resolve intent / item / character / direction). Returning a
# validated integer index replaces scraping a number out of prose.
SELECT_OPTION_TOOL = {
    "name": "select_option",
    "description": "Select the option that best matches the input.",
    "parameters": {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "0-based index of the chosen option",
            },
        },
        "required": ["index"],
    },
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class LlmConfig:
    """Configuration for creating an LLM client."""

    # Accepts an :class:`LlmProvider` member or a plain string ("openai",
    # "anthropic", "mock") -- the two are interchangeable.
    provider: Union[LlmProvider, str]
    api_key: str | None = None  # falls back to env vars
    model: str | None = None  # defaults per provider
    max_output_tokens: int = 256
    max_context_tokens: int = 8000
    base_url: str | None = None  # e.g. Helicone proxy
    verbose: bool = False
    # Resilience (issue #260): retries on transient errors and a per-call socket
    # timeout, both wired into the provider SDK. Defaults suit an unattended bake.
    max_retries: int = 2
    timeout_sec: float = 60.0


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------

_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class OpenAIClient:
    """Wraps the ``openai`` Python SDK (lazy-imported)."""

    def __init__(self, config: LlmConfig, ledger: UsageLedger | None = None):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "The openai package is required. Install with: pip install openai"
            )
        api_key = config.api_key or os.environ.get("OPENAI_API_KEY")
        self._api_key = api_key
        # Per-call socket timeout so a hung request can't block simulate()
        # forever; max_retries=0 hands retry control to _retry_with_backoff so
        # retries stay observable in the ledger (issue #260).
        kwargs: dict = {
            "api_key": api_key,
            "timeout": config.timeout_sec,
            "max_retries": 0,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = openai.OpenAI(**kwargs)
        self._model = config.model or _DEFAULT_OPENAI_MODEL
        self._verbose = config.verbose
        self._max_retries = config.max_retries
        self._timeout = config.timeout_sec
        self._sleep = time.sleep  # injectable in tests to skip real backoff
        # Lazy tokenizer
        self._tokenizer = None
        # Usage accounting (side channel; see usage.py). Defaults to a private
        # ledger so existing callers need not change; pass a shared one to
        # aggregate across clients. `context` carries per-call attribution
        # (actor/turn), set by the caller before each decision.
        self.ledger = ledger or UsageLedger()
        self.context: dict = {}

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
            response, latency_ms = _resilient_create(
                self,
                lambda: self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=0,
                    frequency_penalty=0,
                    presence_penalty=0,
                ),
                provider="openai",
                messages=messages,
            )
            text = response.choices[0].message.content
            record_call(
                getattr(self, "ledger", None),
                getattr(self, "context", {}),
                "openai",
                self._model,
                getattr(response, "usage", None),
                messages,
                text,
                latency_ms,
            )
            return text
        except Exception as e:
            if self._verbose:
                print(f"OpenAI API error: {e}")
            return None

    def call_tool(
        self,
        messages: list[dict],
        tool: dict,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> dict | None:
        try:
            if self._verbose:
                print(json.dumps(messages, indent=2))
            response, latency_ms = _resilient_create(
                self,
                lambda: self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=[_to_openai_tool(tool)],
                    tool_choice={
                        "type": "function",
                        "function": {"name": tool["name"]},
                    },
                ),
                provider="openai",
                messages=messages,
            )
            tool_calls = response.choices[0].message.tool_calls
            args_text = tool_calls[0].function.arguments if tool_calls else None
            record_call(
                getattr(self, "ledger", None),
                getattr(self, "context", {}),
                "openai",
                self._model,
                getattr(response, "usage", None),
                messages,
                args_text,
                latency_ms,
            )
            if not tool_calls:
                return None
            return json.loads(args_text)
        except Exception as e:
            if self._verbose:
                print(f"OpenAI tool-call error: {e}")
            return None

    def count_tokens(self, text: str) -> int:
        tokenizer = self._get_tokenizer()
        if tokenizer is not None:
            return len(tokenizer.encode(text))
        # Fallback heuristic
        return len(text) // 4

    def preflight(self) -> None:
        _preflight_key(
            self,
            "openai",
            "OPENAI_API_KEY",
            live_probe=lambda: self._client.models.list(),
        )


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------

# Default to the cheapest current model: a 25-agent day is thousands of
# low-stakes NPC decisions, so Haiku's price/latency fits. (The previous default,
# claude-sonnet-4-20250514, is past its retirement date.) Override with
# LLM_MODEL / LlmConfig.model.
_DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"


class AnthropicClient:
    """Wraps the ``anthropic`` Python SDK (lazy-imported)."""

    def __init__(self, config: LlmConfig, ledger: UsageLedger | None = None):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "The anthropic package is required. Install with: pip install anthropic"
            )
        api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._api_key = api_key
        # Per-call socket timeout so a hung request can't block simulate()
        # forever; max_retries=0 hands retry control to _retry_with_backoff so
        # retries stay observable in the ledger (issue #260).
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=config.timeout_sec,
            max_retries=0,
        )
        self._model = config.model or _DEFAULT_ANTHROPIC_MODEL
        self._verbose = config.verbose
        self._max_retries = config.max_retries
        self._timeout = config.timeout_sec
        self._sleep = time.sleep  # injectable in tests to skip real backoff
        # Usage accounting (side channel; see usage.py and OpenAIClient.__init__).
        self.ledger = ledger or UsageLedger()
        self.context: dict = {}

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
                kwargs["system"] = _cacheable_system(system_text)

            response, latency_ms = _resilient_create(
                self,
                lambda: self._client.messages.create(**kwargs),
                provider="anthropic",
                messages=messages,
            )
            text = response.content[0].text
            record_call(
                getattr(self, "ledger", None),
                getattr(self, "context", {}),
                "anthropic",
                self._model,
                getattr(response, "usage", None),
                messages,
                text,
                latency_ms,
            )
            return text
        except Exception as e:
            if self._verbose:
                print(f"Anthropic API error: {e}")
            return None

    def call_tool(
        self,
        messages: list[dict],
        tool: dict,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> dict | None:
        try:
            # Same system-message extraction as chat().
            system_text = None
            chat_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_text = msg["content"]
                else:
                    content = msg["content"]
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
                "tools": [_to_anthropic_tool(tool)],
                "tool_choice": {"type": "tool", "name": tool["name"]},
            }
            if system_text:
                kwargs["system"] = _cacheable_system(system_text)

            response, latency_ms = _resilient_create(
                self,
                lambda: self._client.messages.create(**kwargs),
                provider="anthropic",
                messages=messages,
            )
            args = None
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    args = dict(block.input)
                    break
            record_call(
                getattr(self, "ledger", None),
                getattr(self, "context", {}),
                "anthropic",
                self._model,
                getattr(response, "usage", None),
                messages,
                json.dumps(args) if args is not None else None,
                latency_ms,
            )
            return args
        except Exception as e:
            if self._verbose:
                print(f"Anthropic tool-call error: {e}")
            return None

    def count_tokens(self, text: str) -> int:
        # Heuristic: ~4 chars per token
        return len(text) // 4

    def preflight(self) -> None:
        _preflight_key(
            self,
            "anthropic",
            "ANTHROPIC_API_KEY",
            live_probe=lambda: self._client.models.list(),
        )


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

    The `tool_responses` argument is the structured-tool-calling counterpart of
    `responses`: a separate list of dicts (or `None`), or a callable
    `(messages, tool, max_tokens, temperature) -> dict | None`, returned one per
    `call_tool` call. It is kept entirely separate from `responses` so `chat`
    and `call_tool` never consume each other's scripts. It defaults to `None`,
    so `call_tool` returns `None` (the graceful-fallback signal) unless a test
    scripts a reply.

    Every `chat` call is recorded in `calls`, and every `call_tool` call in
    `tool_calls`, so tests can assert on what was sent to the model.

    Example:

        client = MockLlmClient(["go north"])
        client.chat([{"role": "user", "content": "what do you do?"}])  # -> "go north"

        # React to the prompt:
        def pick_first(messages, max_tokens, temperature):
            return "0"
        client = MockLlmClient(pick_first)
    """

    def __init__(
        self,
        responses=None,
        default: str | None = "",
        tool_responses=None,
        ledger: UsageLedger | None = None,
    ):
        # Usage accounting: the mock records a zero-cost Usage on every call, so
        # the accounting path is exercised offline (no SDK, no network).
        self.ledger = ledger or UsageLedger()
        self.context: dict = {}
        if callable(responses):
            self._responder = responses
            self._queue = None
        else:
            self._responder = None
            self._queue = list(responses) if responses is not None else []
        self._default = default
        # A log of every chat() call, for test assertions.
        self.calls: list[dict] = []

        # call_tool() support: scripted structured replies, drawn from a
        # SEPARATE queue/responder so chat() and call_tool() never consume each
        # other's scripts. `tool_responses` may be a list of dicts/None, or a
        # callable (messages, tool, max_tokens, temperature) -> dict | None.
        # Defaults to None, so call_tool() returns None unless a test scripts a
        # reply -- which makes the agent fall back to its chat() path.
        if callable(tool_responses):
            self._tool_responder = tool_responses
            self._tool_queue = None
        else:
            self._tool_responder = None
            self._tool_queue = (
                list(tool_responses) if tool_responses is not None else []
            )
        # A log of every call_tool() call, mirroring `calls`.
        self.tool_calls: list[dict] = []

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
            result = self._responder(messages, max_tokens, temperature)
        elif self._queue:
            result = self._queue.pop(0)
        else:
            result = self._default
        record_call(
            getattr(self, "ledger", None),
            getattr(self, "context", {}),
            "mock",
            "mock",
            None,
            messages,
            result,
        )
        return result

    def call_tool(
        self,
        messages: list[dict],
        tool: dict,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> dict | None:
        self.tool_calls.append(
            {
                "messages": messages,
                "tool": tool,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if self._tool_responder is not None:
            result = self._tool_responder(messages, tool, max_tokens, temperature)
        elif self._tool_queue:
            result = self._tool_queue.pop(0)
        else:
            result = None
        record_call(
            getattr(self, "ledger", None),
            getattr(self, "context", {}),
            "mock",
            "mock",
            None,
            messages,
            json.dumps(result) if result is not None else None,
        )
        return result

    def count_tokens(self, text: str) -> int:
        # Heuristic: ~4 chars per token (matches the Anthropic adapter).
        return len(text) // 4

    def preflight(self) -> None:
        # The mock needs no key and never touches the network -- nothing to check.
        return None


# ---------------------------------------------------------------------------
# Mock ReAct adapter (a fake "brain" that can drive the live game for free)
# ---------------------------------------------------------------------------


def _player_present(observation: str) -> bool:
    """Check whether the player is listed in the observation's
    'Characters here:' section.

    game.describe_for() lists the section as::

        Characters here:
         * The player - ...
        Inventory: ...

    We only look between the two headers, because 'the player' also shows up
    in the 'Recent events:' history even after the player has left the room.
    """
    if "characters here:" not in observation:
        return False
    section = observation.split("characters here:", 1)[1].split("inventory", 1)[0]
    return "the player" in section


def _decision(reasoning: str, command: str) -> str:
    """Format a reply the way ``_DECISION_INSTRUCTION`` asks a real LLM to:
    a labeled Reasoning line, then a labeled Action line."""
    return f"Reasoning: {reasoning}\nAction: {command}"


def _split_decision(text: str) -> tuple[str | None, str | None]:
    """Split a `_decision`-formatted reply ("Reasoning: ...\\nAction: ...")
    back into ``(reasoning, command)``. Used by MockReActClient.call_tool to
    turn the mock brain's labeled string into a structured arguments dict.
    Kept local to llm_client (rather than importing npc._parse_decision) so the
    low-level client layer does not depend on the agent layer."""
    reasoning = None
    command = None
    for raw in text.splitlines():
        line = raw.strip()
        lowered = line.lower()
        if lowered.startswith("reasoning:"):
            reasoning = line.split(":", 1)[1].strip() or None
        elif lowered.startswith("action:"):
            command = line.split(":", 1)[1].strip() or None
    return reasoning, command


def _split_command(command: str, tool: dict) -> tuple[str, str]:
    """Split a flat command ("ghost touch player") into (action, arguments) the
    way the choose_action tool expects. When the tool constrains `action` to a
    known set of verbs (its enum), match the longest verb the command starts
    with -- so multi-word verbs like "ghost touch" stay intact, exactly as a
    real tool-calling model (which can only return an enum value) would. Falls
    back to splitting on the first space when the tool has no enum."""
    enum = (
        tool.get("parameters", {}).get("properties", {}).get("action", {}).get("enum")
    )
    if enum:
        # Longest verb first so "ghost touch" wins over a hypothetical "ghost".
        for verb in sorted(enum, key=len, reverse=True):
            if command == verb or command.startswith(verb + " "):
                return verb, command[len(verb) :].strip()
    head, _, rest = command.partition(" ")
    return head, rest


def _mock_brain_choose(system: str, observation: str) -> str | None:
    """Pick a command for an Action Castle NPC, the way an LLM would.

    This is the 'reasoning' behind :class:`MockReActClient`: an ordered list
    of substring rules over the same two prompts a real model would see --
    the system message (persona + goals) and the observation (location,
    characters present, recent events, and any reflected failure reason).
    First matching rule wins. Replies use the same labeled two-line format a
    real model is instructed to use ("Reasoning: ...\\nAction: ..."), so the
    agent's trace shows *why* each command was chosen. Returns ``None`` (act
    on nothing) when the prompt isn't an NPC decision or the player isn't
    there to menace.

    Each NPC escalates by reading its own past actions in the observation's
    'Recent events:' history -- the mock has no memory between calls, just
    like the real agent (memory is Phase 2).
    """
    system = system.lower()
    observation = observation.lower()

    # Only answer the NPC decision prompt built by LLMAgent. Anything else
    # (e.g. the LLM parser asking for narration) gets None, which the callers
    # treat as a graceful fallback to their non-LLM path.
    if "you are an npc in a text adventure game" not in system:
        return None

    player_here = _player_present(observation)
    # react_behavior's Reflect step appends this line after a failed command.
    reflecting = "' failed:" in observation

    # Who am I? Match the "I am the {name}." prefix that notebooks/hw1_llm
    # adds, or a distinctive phrase from the original Action Castle personas
    # (so the webapp's hybrid NPCs are recognized too).
    # Troll: growl -> snarl -> attack. The first attack deliberately omits
    # the weapon, so check_preconditions() rejects it ("troll doesn't have a
    # weapon.") and the Reflect step feeds the reason back; only then does
    # the troll name its club. This demonstrates the precondition gate.
    if "i am the troll" in system or "guard the drawbridge" in system:
        if not player_here:
            return None
        if "eats the fish" in observation:  # recently fed -> stand down
            return None
        if reflecting and "doesn't have a weapon" in observation:
            return _decision(
                "My attack failed because I never said which weapon to use.",
                "attack player with club",
            )
        if "snarls" in observation:  # already snarled -> time to attack
            return _decision(
                "Growling and snarling didn't drive the intruder off. Attack.",
                "attack player",
            )
        if "growls" in observation:  # already growled -> escalate
            return _decision(
                "My growl didn't scare the intruder off. Escalate.",
                "snarl player",
            )
        return _decision(
            "An intruder is on my drawbridge. Warn them off.",
            "growl player",
        )

    # Guard: warn -> threaten -> attack with sword.
    if "i am the guard" in system or "suspicious of anyone" in system:
        if not player_here:
            return None
        if "last warning" in observation:  # already threatened
            return _decision(
                "The stranger ignored my last warning. Draw my sword.",
                "attack player with sword",
            )
        if "you don't belong here" in observation:  # already warned
            return _decision(
                "The stranger ignored my warning. Make a real threat.",
                "threaten player",
            )
        return _decision(
            "A stranger is in the courtyard. Warn them away from the castle.",
            "warn player",
        )

    # Ghost: haunt once, then the killing touch.
    if "i am the ghost" in system or "i will haunt" in system:
        if not player_here:
            return None
        if "leave this place, mortal" in observation:  # already haunted
            return _decision(
                "The mortal ignored my warning. Stop their heart.",
                "ghost touch player",
            )
        return _decision(
            "A living soul has entered my dungeon. Frighten them away.",
            "haunt player",
        )

    # Persuadable servant: when its master directly asks it to fetch the key,
    # adopting that goal fits its servile persona. This is the issue #46
    # demonstration -- an utterance changing a listener agent's goals. The
    # `already` guard reads the agent's own active goals (rendered into the
    # system message) so it won't re-adopt a goal it already holds.
    if "i am the servant" in system:
        already = "fetch the golden key" in system
        wants = "said to you: please fetch the golden key" in observation
        if wants and not already:
            return _decision(
                "My master asked me directly, and serving is who I am.",
                "adopt goal fetch the golden key",
            )
        return None

    # Stubborn knight: bound by its own oath, it refuses others' requests.
    # Hearing the same plea changes nothing -- persuasion is persona-gated.
    if "i am the stubborn knight" in system:
        return None

    return None  # unknown NPC: safest move is no move


class MockReActClient(MockLlmClient):
    """A free, offline stand-in for an LLM, smart enough to drive the ReAct loop.

    Registered as provider ``"mock"``, so ``LLM_PROVIDER=mock`` runs the real
    game end-to-end with LLM-driven NPCs -- no SDK, no API key, no cost. It is
    *not* a language model: it reads the prompts the agent sends and picks an
    in-character command via :func:`_mock_brain_choose`. Deterministic, so the
    integration tests can rely on it.

    Inherits ``calls`` and ``tool_calls`` recording from
    :class:`MockLlmClient`, so tests can assert on exactly what the agent sent.
    Adds ``decisions``: a log of the brain's actual (non-None) commands,
    appended on whichever route ran -- ``_decide`` or ``call_tool``.
    """

    def __init__(
        self, config: LlmConfig | None = None, ledger: UsageLedger | None = None
    ):
        # create_llm_client() constructs providers as cls(config, ledger=...);
        # tests may also construct this directly with no config.
        super().__init__(responses=self._decide, ledger=ledger)
        self._verbose = bool(config and config.verbose)
        # A log of every actual decision (non-None command) the brain made.
        # This is distinct from the inherited `tool_calls` log, which records
        # *every* `call_tool` invocation (including the silent turns where the
        # brain declines), and from `calls`, which records every `chat` call.
        # Both `_decide` and `call_tool` append here on a non-None command, so
        # `decisions` is accurate regardless of which route the agent took.
        # Tests assert on this to confirm an NPC genuinely chose to act.
        self.decisions: list[dict] = []

    def _decide(self, messages, max_tokens, temperature) -> str | None:
        system = messages[0]["content"] if messages else ""
        observation = messages[-1]["content"] if messages else ""
        command = _mock_brain_choose(system, observation)
        if command is not None:
            self.decisions.append({"command": command, "system": system})
        if self._verbose:
            print(f"[mock-react] -> {command!r}")
        return command

    def call_tool(
        self,
        messages: list[dict],
        tool: dict,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> dict | None:
        """Structured counterpart of `_decide`: pick an in-character command via
        the mock brain, then split it into a choose_action arguments object.
        Returns None for prompts the brain doesn't recognize (the same
        graceful-fallback signal `chat` gives), so LLM_PROVIDER=mock exercises
        the structured path end-to-end and falls back exactly like a real one."""
        self.tool_calls.append(
            {
                "messages": messages,
                "tool": tool,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        system = messages[0]["content"] if messages else ""
        observation = messages[-1]["content"] if messages else ""
        decision = _mock_brain_choose(system, observation)
        result = None
        if decision is not None:
            reasoning, command = _split_decision(decision)
            if command:
                # Record the real decision (mirrors `_decide`), so `decisions`
                # is accurate whether the agent took the structured or chat route.
                self.decisions.append({"command": command, "system": system})
                verb, rest = _split_command(command, tool)
                result = {"reasoning": reasoning, "action": verb, "arguments": rest}
        # Zero-cost usage record (mirrors MockLlmClient.call_tool), so the
        # accounting path is exercised on the structured route too.
        record_call(
            getattr(self, "ledger", None),
            getattr(self, "context", {}),
            "mock",
            "mock",
            None,
            messages,
            json.dumps(result) if result is not None else None,
        )
        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

# Keyed by LlmProvider members; since LlmProvider IS a str, a lookup with the
# raw string "openai" still resolves.
_PROVIDERS = {
    LlmProvider.OPENAI: OpenAIClient,
    LlmProvider.ANTHROPIC: AnthropicClient,
    LlmProvider.MOCK: MockReActClient,
}


def create_llm_client(
    config: LlmConfig, ledger: UsageLedger | None = None
) -> LlmClient:
    """Create an LLM client from a config.

    Pass a shared :class:`~text_adventure_games.usage.UsageLedger` to aggregate
    token/cost accounting across clients; omit it and each client keeps its own.
    """
    provider = str(config.provider).lower()
    if provider not in _PROVIDERS:
        choices = [str(p) for p in _PROVIDERS]
        raise ValueError(f"Unknown provider '{provider}'. Choose from: {choices}")
    return _PROVIDERS[provider](config, ledger=ledger)


def client_from_env(run_log: "RunLog | None" = None) -> LlmClient | None:
    """Create an LLM client from environment variables, or return None.

    Reads ``LLM_PROVIDER`` ("anthropic", "openai", or "mock" -- the free,
    offline stand-in), plus optional ``LLM_API_KEY``, ``LLM_MODEL``,
    ``LLM_BASE_URL``, ``LLM_VERBOSE``, and the resilience knobs
    ``LLM_MAX_RETRIES`` (int, default 2) and ``LLM_API_TIMEOUT_SEC`` (float,
    default 60). Returns ``None`` when no provider is set or the client can't be
    created, so callers can fall back to their non-LLM path.

    Before returning, the client is preflighted: a real provider with no
    resolvable API key fails fast here (returning ``None`` with a clear warning)
    rather than deep inside the run. Set ``LLM_PREFLIGHT=1`` to additionally
    validate the key with one cheap live call.

    When a :class:`~text_adventure_games.usage.RunLog` is passed, the client's
    usage ledger is attached to it so every call streams to the artifact and the
    summary is written on close.
    """
    provider = os.environ.get("LLM_PROVIDER")
    if not provider:
        return None
    try:
        config = LlmConfig(
            provider=provider,
            api_key=os.environ.get("LLM_API_KEY"),
            model=os.environ.get("LLM_MODEL"),
            base_url=os.environ.get("LLM_BASE_URL"),
            verbose=os.environ.get("LLM_VERBOSE", "").lower() in ("1", "true"),
            max_retries=int(os.environ.get("LLM_MAX_RETRIES", LlmConfig.max_retries)),
            timeout_sec=float(
                os.environ.get("LLM_API_TIMEOUT_SEC", LlmConfig.timeout_sec)
            ),
        )
        ledger = UsageLedger()
        client = create_llm_client(config, ledger=ledger)
        # Surface a missing/bad key up front instead of deep in the loop.
        client.preflight()
        if run_log is not None:
            run_log.attach(ledger)
        return client
    except (ImportError, ValueError) as e:
        print(f"Warning: Could not create LLM client: {e}")
        return None


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
