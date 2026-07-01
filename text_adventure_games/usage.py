"""LLM token-usage accounting and per-run artifacts.

This is the *measure + observe* slice of the LLM cost design
(``docs/design/llm-cost-observability.md``, Pieces 1 and 3). The engine calls a
model once per acting NPC per round; a 25-agent Smallville day is thousands of
calls. Today ``LlmClient.chat()`` / ``call_tool()`` return only the reply text
and throw the response's ``usage`` block away, so nobody can answer "what did
that run cost?" or "which NPC burned the most tokens?". This module fills that
gap with:

* :class:`Usage` -- one provider-agnostic token record per call.
* :class:`CallRecord` -- a priced ``Usage`` plus enough context (actor, turn) to
  attribute it.
* :class:`UsageLedger` -- an append-only log of records with running totals, a
  per-actor rollup, and an optional cost ceiling (``over_budget()``) a driver
  loop can poll as a kill-switch before a runaway live run (issue #183).
* :data:`PRICES` + :func:`price` -- a plain ``$/1M`` token table; unknown models
  warn and cost ``$0`` rather than crashing a run.
* :func:`record_call` -- the one helper the four adapter methods share, so the
  record-building code lives in a single place.
* :class:`RunLog` -- a per-run JSONL artifact (header / one line per call /
  summary), written as a context manager so the summary lands even if the run
  raises.

Accounting is a *side channel*: ``chat()`` keeps returning ``str | None``, the
ledger rides alongside, and the mock providers record a zero-cost :class:`Usage`
so every path here is exercised offline -- no SDK, no network, no API key.

Usage::

    from text_adventure_games.usage import UsageLedger, RunLog

    ledger = UsageLedger()
    client = create_llm_client(config, ledger=ledger)
    ...                                  # run the game
    print(ledger.summary())              # {"total_cost_usd": ..., "by_actor": {...}}

    with RunLog("runs/today.jsonl", provider="anthropic", model="...") as log:
        log.attach(ledger)               # each call streams to disk; summary on close
        ...
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Callable

# ---------------------------------------------------------------------------
# Token usage record
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    """Token usage for one LLM call, normalized across providers.

    Anthropic reports ``input_tokens`` as the *uncached* prompt size and breaks
    out cache writes/reads separately, so the full prompt size is the sum of all
    three input fields (:attr:`total_input_tokens`). OpenAI has no cache fields,
    so they stay zero there.
    """

    provider: str
    model: str
    input_tokens: int = 0  # uncached input, full price
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0  # written to cache (~1.25x input)
    cache_read_input_tokens: int = 0  # served from cache (~0.1x input)

    @property
    def total_input_tokens(self) -> int:
        """Full prompt size = uncached input + cache writes + cache reads."""
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    @classmethod
    def from_openai(cls, model: str, raw) -> "Usage":
        """Map an OpenAI ``response.usage`` (``prompt_tokens`` /
        ``completion_tokens``) onto a :class:`Usage`. ``raw`` may be ``None``."""
        if raw is None:
            return cls(provider="openai", model=model)
        return cls(
            provider="openai",
            model=model,
            input_tokens=int(getattr(raw, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(raw, "completion_tokens", 0) or 0),
        )

    @classmethod
    def from_anthropic(cls, model: str, raw) -> "Usage":
        """Map an Anthropic ``response.usage`` onto a :class:`Usage`. The cache
        fields are read defensively (``getattr``) because they are only present
        when prompt caching is in use. ``raw`` may be ``None``."""
        if raw is None:
            return cls(provider="anthropic", model=model)
        return cls(
            provider="anthropic",
            model=model,
            input_tokens=int(getattr(raw, "input_tokens", 0) or 0),
            output_tokens=int(getattr(raw, "output_tokens", 0) or 0),
            cache_creation_input_tokens=int(
                getattr(raw, "cache_creation_input_tokens", 0) or 0
            ),
            cache_read_input_tokens=int(
                getattr(raw, "cache_read_input_tokens", 0) or 0
            ),
        )

    @classmethod
    def zero(cls, provider: str, model: str) -> "Usage":
        """A zero-token record -- what the mock providers report (free)."""
        return cls(provider=provider, model=model)

    def to_primitive(self) -> dict:
        """JSON-ready dict (mirrors the house ``to_primitive`` convention)."""
        return {
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
        }


@dataclass
class CallRecord:
    """One LLM call: a priced :class:`Usage` plus enough context to attribute
    and (later) replay it. ``attempt`` and ``prompt_sha256`` are unused today but
    are exactly the keys a future record/replay client needs, so they are cheap
    to populate now and expensive to retrofit."""

    usage: Usage
    cost_usd: float
    turn: int | None = None
    actor: str | None = None  # which NPC, when known
    attempt: int | None = None  # retry index (replay seam)
    prompt_sha256: str | None = None  # hash of the messages (replay seam)
    latency_ms: float | None = None

    def to_primitive(self) -> dict:
        """The flattened ``"call"`` line written to a :class:`RunLog`."""
        u = self.usage
        return {
            "kind": "call",
            "turn": self.turn,
            "actor": self.actor,
            "attempt": self.attempt,
            "prompt_sha256": self.prompt_sha256,
            "provider": u.provider,
            "model": u.model,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cache_creation_input_tokens": u.cache_creation_input_tokens,
            "cache_read_input_tokens": u.cache_read_input_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
        }


# A callback invoked for each newly-recorded call: ``(record, messages, response)``.
# :class:`RunLog` installs one so it can stream a line per call to disk; the
# verbose ``messages``/``response`` flow straight through and are never retained.
OnRecord = Callable[[CallRecord, "list[dict] | None", "str | None"], None]


class UsageLedger:
    """Append-only log of :class:`CallRecord`\\ s for one run, with running totals.

    A single ledger can be shared across many clients (e.g. one per Smallville
    persona) so the rollups cover the whole run. Querying the ledger
    (:meth:`summary`, :meth:`totals_by_actor`) is the in-memory path; attaching a
    :class:`RunLog` additionally streams each call to disk.

    Pass ``max_cost_usd`` to arm a cost ceiling / kill-switch (issue #183): the
    ledger never raises -- accounting stays a passive side channel (see
    :func:`record_call`, which must never break a real call) -- so a driver loop
    polls :meth:`over_budget` at a natural boundary (e.g. each sim step) and
    stops before firing the next batch of calls.
    """

    def __init__(self, max_cost_usd: float | None = None) -> None:
        self.records: list[CallRecord] = []
        # Hard cost ceiling in USD, or None (the default) for no ceiling, so
        # existing runs are unchanged. See over_budget() for how it's used.
        self.max_cost_usd = max_cost_usd
        # Optional streaming hook, installed by RunLog.attach(). Kept private so
        # ordinary callers just see record()/summary().
        self._on_record: OnRecord | None = None

    def record(
        self,
        rec: CallRecord,
        *,
        messages: list[dict] | None = None,
        response: str | None = None,
    ) -> None:
        """Append a record and fire the streaming hook, if one is installed."""
        self.records.append(rec)
        if self._on_record is not None:
            self._on_record(rec, messages, response)

    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.records)

    def over_budget(self) -> bool:
        """True once a ceiling is armed and cumulative spend has reached it
        (issue #183). ``>=`` so the run halts the moment the ceiling is hit;
        always False when ``max_cost_usd`` is None, so unbudgeted runs (and the
        free mock brain, which spends $0) are unchanged."""
        return (
            self.max_cost_usd is not None and self.total_cost_usd() >= self.max_cost_usd
        )

    def remaining_budget_usd(self) -> float | None:
        """USD left before the ceiling (clamped at 0), or None when no ceiling
        is armed. A convenience for status lines; :meth:`over_budget` is the
        actual gate."""
        if self.max_cost_usd is None:
            return None
        return max(0.0, self.max_cost_usd - self.total_cost_usd())

    def totals_by_actor(self) -> dict[str, float]:
        """Total cost per actor (NPC). Unattributed calls land under a single
        ``"(unattributed)"`` key rather than being dropped."""
        totals: dict[str, float] = {}
        for r in self.records:
            key = r.actor or "(unattributed)"
            totals[key] = totals.get(key, 0.0) + r.cost_usd
        return totals

    def token_totals(self) -> dict[str, int]:
        """Summed input/output/cache token counts across the whole run."""
        return {
            "input_tokens": sum(r.usage.input_tokens for r in self.records),
            "output_tokens": sum(r.usage.output_tokens for r in self.records),
            "cache_creation_input_tokens": sum(
                r.usage.cache_creation_input_tokens for r in self.records
            ),
            "cache_read_input_tokens": sum(
                r.usage.cache_read_input_tokens for r in self.records
            ),
        }

    def summary(self) -> dict:
        """The run footer: call count, total + per-actor cost, token totals."""
        return {
            "kind": "summary",
            "calls": len(self.records),
            "total_cost_usd": round(self.total_cost_usd(), 6),
            "by_actor": {
                actor: round(cost, 6) for actor, cost in self.totals_by_actor().items()
            },
            **self.token_totals(),
        }


# ---------------------------------------------------------------------------
# Cost table
# ---------------------------------------------------------------------------

# $/1M tokens: (input, output). Cache write costs 1.25x input at the default
# 5-minute TTL (2x at 1 hour); a cache read costs ~0.10x input -- see price().
# Verified against Anthropic's published pricing (2026): Opus 4.x $5/$25,
# Sonnet 4.x $3/$15, Haiku 4.5 $1/$5. These are estimates and drift over time;
# update the table when prices change. Unknown models are priced at $0 with a
# one-time warning rather than crashing a run.
PRICES: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    # Retired default kept so a pinned LLM_MODEL still prices instead of warning.
    "claude-sonnet-4-20250514": (3.00, 15.00),
    # OpenAI (add more as needed)
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    # The offline mock provider is free; listed so default/CI runs don't warn.
    "mock": (0.0, 0.0),
}

# Models we have already warned about, so a thousands-of-calls run warns once.
_PRICE_WARNED: set[str] = set()


def price(model: str, usage: Usage, ttl: str = "5m") -> float:
    """Cost in USD for *usage* at *model*'s prices.

    Cache writes are billed at 1.25x input (5-minute TTL) or 2x (1-hour TTL);
    cache reads at 0.10x input. An unknown model warns once and costs ``$0`` --
    we never crash a run over a missing price.
    """
    if model not in PRICES:
        if model not in _PRICE_WARNED:
            _PRICE_WARNED.add(model)
            print(f"Warning: no price for model {model!r}; counting it as $0.")
        return 0.0
    pin, pout = PRICES[model]
    write_mult = 2.0 if ttl == "1h" else 1.25
    return (
        usage.input_tokens / 1e6 * pin
        + usage.cache_creation_input_tokens / 1e6 * pin * write_mult
        + usage.cache_read_input_tokens / 1e6 * pin * 0.10
        + usage.output_tokens / 1e6 * pout
    )


# ---------------------------------------------------------------------------
# Hashing + the shared record helper
# ---------------------------------------------------------------------------


def prompt_sha256(messages: list[dict]) -> str:
    """A stable hash of the prompt *messages*, for replay keying. ``sort_keys``
    makes it independent of dict ordering so cosmetically-different-but-equal
    prompts hash the same."""
    payload = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_call(
    ledger: UsageLedger | None,
    context: dict | None,
    provider: str,
    model: str,
    raw_usage,
    messages: list[dict] | None,
    response_text: str | None,
    latency_ms: float | None = None,
) -> CallRecord | None:
    """Build a normalized :class:`Usage` from a provider's raw usage object,
    price it, attach attribution from *context* (``actor`` / ``turn`` /
    ``attempt``), append a :class:`CallRecord` to *ledger*, and return it.

    This is the single place the four adapter methods (OpenAI/Anthropic x
    chat/call_tool) share, so the record-building logic isn't copied four times.
    ``raw_usage=None`` yields a zero-cost record -- the mock path. Accounting
    must never break a real call, so any failure here is swallowed with a warning
    and the call still returns its reply.
    """
    if ledger is None:
        return None
    try:
        context = context or {}
        if raw_usage is None:
            usage = Usage.zero(provider, model)
        elif provider == "openai":
            usage = Usage.from_openai(model, raw_usage)
        elif provider == "anthropic":
            usage = Usage.from_anthropic(model, raw_usage)
        else:
            usage = Usage.zero(provider, model)
        rec = CallRecord(
            usage=usage,
            cost_usd=price(model, usage),
            turn=context.get("turn"),
            actor=context.get("actor"),
            attempt=context.get("attempt"),
            prompt_sha256=(prompt_sha256(messages) if messages is not None else None),
            latency_ms=latency_ms,
        )
        ledger.record(rec, messages=messages, response=response_text)
        return rec
    except Exception as e:  # never let accounting break the real call
        print(f"Warning: usage recording failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Run artifact (per-run JSONL log)
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _git_sha() -> str | None:
    """Best-effort short git SHA for the run header; ``None`` if unavailable."""
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


class RunLog:
    """A per-run JSONL artifact: cost analysis *and* a transcript in one file.

    Three kinds of line: a ``run`` header (how to reproduce), one ``call`` line
    per LLM call, and a ``summary`` footer (totals). Use it as a context manager
    so the summary is written on close even if the run raises::

        with RunLog("runs/today.jsonl", provider="mock", model="mock") as log:
            log.attach(ledger)   # call lines stream as they happen
            run_the_sim(...)
        # summary line written here

    Full prompts/responses are included only when ``log_prompts=True``; the
    token/cost numbers are always written.
    """

    def __init__(
        self,
        path: str,
        *,
        seed: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        turn_mode: str | None = None,
        log_prompts: bool = False,
    ) -> None:
        self.path = path
        self.seed = seed
        self.provider = provider
        self.model = model
        self.turn_mode = turn_mode
        self.log_prompts = log_prompts
        self._ledger: UsageLedger | None = None
        self._file = None

    def attach(self, ledger: UsageLedger) -> None:
        """Stream this run's calls to disk and read the summary from *ledger* on
        close. Installs the ledger's streaming hook."""
        self._ledger = ledger
        ledger._on_record = self.log_call

    def __enter__(self) -> "RunLog":
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._file = open(self.path, "w", encoding="utf-8")
        self._write(
            {
                "kind": "run",
                "seed": self.seed,
                "provider": self.provider,
                "model": self.model,
                "turn_mode": self.turn_mode,
                "git_sha": _git_sha(),
                "started_at": _now_iso(),
            }
        )
        return self

    def log_call(
        self,
        rec: CallRecord,
        messages: list[dict] | None = None,
        response: str | None = None,
    ) -> None:
        """Write one ``call`` line. Wired as the ledger's streaming hook by
        :meth:`attach`, but safe to call directly too."""
        if self._file is None:
            return
        line = rec.to_primitive()
        if self.log_prompts:
            line["messages"] = messages
            line["response"] = response
        self._write(line)

    def _write(self, obj: dict) -> None:
        self._file.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._file.flush()

    def __exit__(self, *exc) -> bool:
        try:
            if self._ledger is not None and self._file is not None:
                self._write(self._ledger.summary())
        finally:
            if self._file is not None:
                self._file.close()
                self._file = None
            # Detach so a reused ledger never writes to a closed file. Compare
            # with == (not is): each access to self.log_call is a fresh bound
            # method, but two bound methods of the same instance compare equal.
            if self._ledger is not None and self._ledger._on_record == self.log_call:
                self._ledger._on_record = None
        return False  # don't suppress exceptions
