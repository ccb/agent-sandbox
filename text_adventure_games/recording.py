"""Record and replay LLM calls -- the "cassette" layer for reproducible runs (#197).

Every model call in the engine goes through one Protocol,
:class:`~text_adventure_games.llm_client.LlmClient`, whose three call methods are
``chat`` (free text), ``call_tool`` (force one tool), and ``call_tools`` (offer a
set, model chooses). That small surface is all we need to make a run reproducible:

- :class:`RecordingClient` wraps a real client, behaves identically across all
  three methods, and writes each ``(request, response)`` to a JSONL *cassette* as
  a side effect.
- :class:`ReplayClient` reads a cassette back and serves those responses with no
  network and no API key -- so a recorded run replays offline and for free.

This is the "VCR cassette" pattern (vcrpy / betamax), applied to the client seam
instead of HTTP. It needs no changes to ``npc.py``, the parser, or any game -- a
recording/replay client is just another ``LlmClient``.

PR #61 wrapped only ``chat``; the tool methods (#354-#359) landed afterward, so
this revived version wraps all three and serializes the :class:`ToolCallResult`
that ``call_tools`` returns.

The other source of non-determinism is the engine's own RNG, so this module also
provides :func:`seed_world` to pin it.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
from collections import deque

from .llm_client import ToolCallResult

# ---------------------------------------------------------------------------
# Request keying
# ---------------------------------------------------------------------------


def request_key(
    method: str,
    messages,
    max_tokens: int = 256,
    temperature: float = 0.0,
    tools=None,
    tool_choice=None,
) -> str:
    """A stable key identifying one client request, across all three call methods.

    We hash the *whole* request -- the ``method`` name, the messages, the sampling
    params, and (for tool calls) the offered tools + ``tool_choice`` -- so a replay
    matches only a byte-identical request. That is exactly what a deterministic
    replay produces: same game build + same seed + the same replayed responses lead
    to the same prompts, so the keys line up. Because of that, v1 does no fuzzy
    normalization; exact matching is correct and simple.

    ``method`` is part of the key so a ``chat`` and a ``call_tools`` with a
    coincidentally similar payload can never collide. ``sort_keys=True`` makes the
    key insensitive to dict ordering in the request (defensive -- requests are
    built in a fixed order today).
    """
    payload = {
        # Future: normalize turn numbers / whitespace in messages here if we ever
        # want a recorded run to match a *similar* (not identical) request.
        "method": method,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "tools": tools,
        "tool_choice": tool_choice,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _dump(response):
    """A JSON-serializable form of a response. ``ToolCallResult`` -> a plain dict;
    everything else (``str`` / ``dict`` / ``None``) is already JSON-native."""
    if isinstance(response, ToolCallResult):
        return {"text": response.text, "tool_calls": response.tool_calls}
    return response


def _text_key(text: str) -> str:
    """Stable key for a count_tokens input (recorded and replayed by text)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


class CassetteWriter:
    """One append-only, thread-safe JSONL sink shared by every RecordingClient
    that wraps the clients of a single run (decide, reflect, planner, per-agent).

    A run has ONE cassette but several client instances; opening the same path
    from two RecordingClients in ``"w"`` mode would truncate each other. Sharing
    one writer keeps every call in one file, in call order. The lock guards the
    paid parallel-decide path (#366) where N agent clients write concurrently;
    under the free scripted brain the run is single-threaded, so it is
    uncontended there.
    """

    def __init__(self, path: str):
        self._file = open(path, "w", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, line: dict) -> None:
        text = json.dumps(line, ensure_ascii=False) + "\n"
        with self._lock:
            self._file.write(text)
            self._file.flush()  # a crashed run still leaves a usable cassette

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()


class RecordingClient:
    """Wrap a real :class:`~text_adventure_games.llm_client.LlmClient`.

    Behaves exactly like the client it wraps -- same return value (including
    ``None`` on failure, and a :class:`ToolCallResult` from ``call_tools``), same
    token counts -- and, as a side effect, appends each ``(request, response)`` to
    a JSONL cassette. One call writes one line, flushed immediately so a crashed
    run still leaves a usable cassette.

    Pass exactly one of *path* (the #197 single-client case -- this client owns
    a private :class:`CassetteWriter`) or *writer* (a #715 whole-run cassette
    shared by several clients, e.g. one per agent).
    """

    def __init__(
        self, inner, path: str | None = None, *, writer: "CassetteWriter | None" = None
    ):
        if (path is None) == (writer is None):
            raise ValueError("RecordingClient needs exactly one of path or writer")
        self._inner = inner
        # Own our writer when handed a path (#197's single-client case); share
        # the caller's when handed one (a whole run's clients -> one cassette, #715).
        self._owns_writer = writer is None
        self._writer = writer if writer is not None else CassetteWriter(path)
        # count_tokens is deterministic per text, so record each distinct text
        # once (#715): without this a repeated single-value fact appends a line
        # every call -- unbounded over a long parallel-decide day -- while the
        # replay map only ever keeps the last. Per-client set, so N per-agent
        # clients sharing one writer stay bounded by N-per-text, not per-call.
        self._counted: set[str] = set()

    @property
    def context(self):
        """Proxy the wrapped client's ``run_tool_loop`` context (round tracking,
        tracing) so a recorded run behaves exactly like an unwrapped one. Returns
        the inner object itself, so the loop's in-place mutations land on it."""
        return getattr(self._inner, "context", None)

    def _write(self, key: str, method: str, request: dict, response) -> None:
        self._writer.write(
            {
                "key": key,
                "method": method,
                "request": request,
                "response": _dump(response),
            }
        )

    def chat(self, messages, max_tokens: int = 256, temperature: float = 0.0):
        response = self._inner.chat(messages, max_tokens, temperature)
        key = request_key("chat", messages, max_tokens, temperature)
        self._write(
            key,
            "chat",
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            response,
        )
        return response

    def call_tool(
        self, messages, tool, max_tokens: int = 256, temperature: float = 0.0
    ):
        response = self._inner.call_tool(messages, tool, max_tokens, temperature)
        key = request_key("call_tool", messages, max_tokens, temperature, tools=tool)
        self._write(
            key,
            "call_tool",
            {
                "messages": messages,
                "tool": tool,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            response,
        )
        return response

    def call_tools(
        self,
        messages,
        tools,
        tool_choice="auto",
        max_tokens: int = 256,
        temperature: float = 0.0,
    ):
        response = self._inner.call_tools(
            messages,
            tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        key = request_key(
            "call_tools",
            messages,
            max_tokens,
            temperature,
            tools=tools,
            tool_choice=tool_choice,
        )
        self._write(
            key,
            "call_tools",
            {
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            response,
        )
        return response

    def count_tokens(self, text: str) -> int:
        n = self._inner.count_tokens(text)
        # Record the count so a replay serves the EXACT value the recorded client
        # returned (#715 follow-up). llm_parser sizes max_tokens from
        # count_tokens("") and that number is hashed into the request key, so a
        # replay that guessed len//4 against a real tokenizer would CassetteMiss.
        # Write each distinct text once -- the count never changes for a text and
        # the replay map keeps only the last, so re-writing it every call is pure
        # cassette bloat.
        key = _text_key(text)
        if key not in self._counted:
            self._counted.add(key)
            self._writer.write({"method": "count_tokens", "text_key": key, "count": n})
        return n

    def preflight(self) -> None:
        """Delegate to the wrapped client."""
        return self._inner.preflight()

    def close(self):
        if self._owns_writer:
            self._writer.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


class CassetteMiss(Exception):
    """Raised by a strict :class:`ReplayClient` when a request isn't recorded."""


class ReplayClient:
    """Serve responses from a cassette recorded by :class:`RecordingClient`.

    No network, no API key -- that's the whole point. Requests are matched by
    :func:`request_key`; identical requests are served in the order they were
    recorded (FIFO per key). A miss -- a request that isn't in the cassette, or a
    key whose recorded responses are all used up -- raises :class:`CassetteMiss`
    when *strict* (the right default for CI), or returns ``None`` otherwise.

    A recorded ``None`` is a real, replayable answer (the wrapped model failed or
    declined), so it is served back as ``None`` -- that is a *hit*, not a miss.
    A ``call_tools`` response is rebuilt into a :class:`ToolCallResult`.
    """

    def __init__(self, path: str, strict: bool = True):
        self._path = path
        self._strict = strict
        # No inner client: run_tool_loop's `getattr(client, "context", None)`
        # sees None and skips round-tracking (metadata only -- not part of any
        # request key, so it never affects a match).
        self.context = None
        # key -> queue of raw responses, consumed in recorded order.
        self._responses: dict[str, deque] = {}
        # text_key -> recorded token count (deterministic per text; a map, not a queue).
        self._token_counts: dict[str, int] = {}
        with open(path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                entry = json.loads(raw)
                if entry.get("method") == "count_tokens":
                    self._token_counts[entry["text_key"]] = entry["count"]
                    continue
                self._responses.setdefault(entry["key"], deque()).append(
                    entry["response"]
                )

    def _lookup(self, key: str, messages):
        queue = self._responses.get(key)
        if not queue:
            # Either never recorded, or every recorded response for this key is
            # used up (over-consumption). Both mean the replay diverged.
            return self._miss(messages)
        return queue.popleft()

    def chat(self, messages, max_tokens: int = 256, temperature: float = 0.0):
        return self._lookup(
            request_key("chat", messages, max_tokens, temperature), messages
        )

    def call_tool(
        self, messages, tool, max_tokens: int = 256, temperature: float = 0.0
    ):
        return self._lookup(
            request_key("call_tool", messages, max_tokens, temperature, tools=tool),
            messages,
        )

    def call_tools(
        self,
        messages,
        tools,
        tool_choice="auto",
        max_tokens: int = 256,
        temperature: float = 0.0,
    ):
        served = self._lookup(
            request_key(
                "call_tools",
                messages,
                max_tokens,
                temperature,
                tools=tools,
                tool_choice=tool_choice,
            ),
            messages,
        )
        # call_tools always recorded either a ToolCallResult dump (a dict) or None,
        # so a dict here unambiguously means "rebuild the ToolCallResult".
        if isinstance(served, dict):
            return ToolCallResult(
                text=served.get("text"), tool_calls=served.get("tool_calls", [])
            )
        return served

    def count_tokens(self, text: str) -> int:
        """Serve the recorded count for a text the recording measured; otherwise
        fall back to the ~4-chars/token estimate the mock/Anthropic clients use.

        Recording the counts (#715) is what makes a run captured with a *real*
        provider tokenizer replay byte-identically: llm_parser hashes
        max_tokens (derived from count_tokens) into the request key, so the
        replayed count must match the recorded one exactly."""
        recorded = self._token_counts.get(_text_key(text))
        if recorded is not None:
            return recorded
        return len(text) // 4

    def preflight(self) -> None:
        """A replay needs no key and never touches the network -- a no-op."""
        return None

    def close(self):
        """No-op: a replay owns no file handle. Present so ReplayClient and
        RecordingClient are lifecycle-interchangeable in a ``with client:`` /
        ``client.close()`` re-run harness (#715 follow-up)."""
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _miss(self, messages):
        if self._strict:
            # Content may be a str (chat) or a list of tool blocks (tool loop),
            # so stringify before slicing -- the diagnostic must never itself
            # raise and mask the real CassetteMiss.
            last = messages[-1].get("content", "") if messages else ""
            preview = str(last)[:200]
            raise CassetteMiss(
                f"No recorded response for this request in {self._path!r}. "
                f"The replayed run diverged from the recording. Last message: {preview!r}"
            )
        return None


# ---------------------------------------------------------------------------
# Engine determinism
# ---------------------------------------------------------------------------


def seed_world(seed: int) -> None:
    """Pin every engine RNG so a run is reproducible.

    Today that is just the global ``random`` module: the only randomized action on
    the shared path is ``Smell_Rose`` (``actions/rose.py``), which calls
    ``random.choice``. Any new randomized action must use the global ``random``
    too (or be seeded here). (Self-contained worlds such as ``vaarn_chargen`` /
    ``tomb_of_nassak_an_rah`` carry their own ``random.Random(seed)`` and are out
    of scope here.)

    This pins *randomness only*. It does not, on its own, make
    ``Game.to_primitive()`` byte-identical: that dict also depends on canonical
    serialization of set-valued fields (``things/base.py`` already sorts
    ``commands``). Reproducing a full run means seeding here *and* replaying the
    LLM (see this module's clients).
    """
    random.seed(seed)
