"""Record and replay LLM calls -- the "cassette" layer for reproducible runs.

Every model call in the engine (agent decisions *and* the LLM parser) goes
through one method: ``LlmClient.chat()`` (see ``llm_client.py``). That single
seam is all we need to make a run reproducible:

- :class:`RecordingClient` wraps a real client, behaves identically, and writes
  each ``(request, response)`` to a JSONL *cassette* as a side effect.
- :class:`ReplayClient` reads a cassette back and serves those responses with no
  network and no API key -- so a recorded run replays offline and for free.

This is the well-trodden "VCR cassette" pattern (vcrpy / betamax), applied to
``chat()`` instead of HTTP. It needs no changes to ``npc.py``, the parser, or any
game -- a recording/replay client is just another ``LlmClient``.

The other source of non-determinism is the engine's own RNG, so this module also
provides :func:`seed_world` to pin it.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import deque

# ---------------------------------------------------------------------------
# Request keying
# ---------------------------------------------------------------------------


def request_key(messages, max_tokens: int = 256, temperature: float = 0.0) -> str:
    """A stable key identifying one ``chat()`` request.

    We hash the *whole* request -- the messages plus the sampling parameters --
    so a replay only matches a byte-identical request. That is exactly what a
    deterministic replay produces: same game build + same seed + the same
    replayed responses lead to the same prompts, so the keys line up. Because of
    that, v1 does no fuzzy normalization; exact matching is correct and simple.

    ``sort_keys=True`` makes the key insensitive to dict ordering in the request
    (defensive -- messages are built in a fixed order today).
    """
    payload = {
        # Future: normalize turn numbers / whitespace in messages here if we
        # ever want a recorded run to match a *similar* (not identical) request.
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


class RecordingClient:
    """Wrap a real :class:`~text_adventure_games.llm_client.LlmClient`.

    Behaves exactly like the client it wraps -- same return value (including
    ``None`` on failure), same token counts -- and, as a side effect, appends
    each ``(request, response)`` to a JSONL cassette at *path*. One ``chat()``
    call writes one line, flushed immediately so a crashed run still leaves a
    usable cassette.
    """

    def __init__(self, inner, path: str):
        self._inner = inner
        self._path = path
        # Truncate any existing cassette so a fresh recording starts clean.
        self._file = open(path, "w", encoding="utf-8")

    def chat(self, messages, max_tokens: int = 256, temperature: float = 0.0):
        response = self._inner.chat(messages, max_tokens, temperature)
        line = {
            "key": request_key(messages, max_tokens, temperature),
            "request": {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            "response": response,  # may be None -- recorded as JSON null
        }
        self._file.write(json.dumps(line, ensure_ascii=False) + "\n")
        self._file.flush()
        return response

    def count_tokens(self, text: str) -> int:
        """Delegate to the wrapped client -- recording is transparent."""
        return self._inner.count_tokens(text)

    def close(self):
        if not self._file.closed:
            self._file.close()

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
    recorded (FIFO per key). A miss -- a request that isn't in the cassette, or
    a key whose recorded responses are all used up -- raises :class:`CassetteMiss`
    when *strict* (the right default for CI), or returns ``None`` otherwise.

    A recorded ``None`` is a real, replayable answer (the wrapped model failed or
    declined), so it is served back as ``None`` -- that is a *hit*, not a miss.
    """

    def __init__(self, path: str, strict: bool = True):
        self._path = path
        self._strict = strict
        # key -> queue of responses, consumed in recorded order.
        self._responses: dict[str, deque] = {}
        with open(path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                entry = json.loads(raw)
                self._responses.setdefault(entry["key"], deque()).append(
                    entry["response"]
                )

    def chat(self, messages, max_tokens: int = 256, temperature: float = 0.0):
        key = request_key(messages, max_tokens, temperature)
        queue = self._responses.get(key)
        if not queue:
            # Either the request was never recorded, or we've already served
            # every recorded response for it (over-consumption). Both mean the
            # replayed run diverged from the recorded one.
            return self._miss(messages)
        return queue.popleft()

    def count_tokens(self, text: str) -> int:
        """A cheap heuristic. Token counts aren't replayed -- nothing in the
        decision path depends on them -- so an estimate is enough to satisfy the
        :class:`LlmClient` protocol."""
        return max(1, len(text) // 4)

    def _miss(self, messages):
        if self._strict:
            preview = messages[-1]["content"][:200] if messages else ""
            raise CassetteMiss(
                f"No recorded response for this request in {self._path!r}. "
                f"The replayed run diverged from the recording. Last message: "
                f"{preview!r}"
            )
        return None


# ---------------------------------------------------------------------------
# Engine determinism
# ---------------------------------------------------------------------------


def seed_world(seed: int) -> None:
    """Pin every engine RNG so a run is reproducible.

    Today that is just the global ``random`` module: the only randomized action
    is ``Smell_Rose`` (``actions/rose.py``), which calls ``random.choice``. Any
    new randomized action must use the global ``random`` too (or be seeded here).

    This pins *randomness only*. It does **not**, on its own, make
    ``Game.to_primitive()`` byte-identical: that dict also depends on canonical
    serialization of set-valued fields (see ``things/base.py``). Reproducing a
    full run means seeding here *and* replaying the LLM (see this module's
    clients).
    """
    random.seed(seed)
