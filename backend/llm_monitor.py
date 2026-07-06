"""Terminal monitor for LLM requests: one formatted line per model call.

The live Penn server (``godot-generative-agents/sim/serve_penn.py``) fires real
model calls from inside an asyncio-driven tick loop -- invisible unless you
watch the provider dashboard. This module makes every call observable in the
terminal running the server, as it happens::

     #    7 12:05:02  decide    Diego Torres        t  118  claude-haiku-4-5  in   1088 ( 912w/    0r)  out  102    731ms  $0.001238  Σ $0.021410
     #    8 12:09:44  converse  Sofia Ramirez       t  119  claude-haiku-4-5  in   1322 (   0w/ 1002r)  out   64    598ms  $0.000740  Σ $0.041007

Columns: call number, wall-clock time, cognitive role (decide / converse /
plan / reflect), actor, sim turn, model, input tokens (with the prompt-cache
write/read split), output tokens, latency, this call's cost, and the run's
cumulative cost (always equal to what ``GET /usage`` reports).

Two pieces, both hooked into the engine's existing accounting seam
(``text_adventure_games.usage``) so no engine change is needed:

* :class:`RoleTaggedLedger` -- a write-through *view* of a shared base
  :class:`UsageLedger`. Hand one to each LLM client (``create_llm_client(...,
  ledger=view)``): every record still lands in the base ledger first (so
  ``GET /usage``, the cost kill-switch, and any attached ``RunLog`` are
  untouched), and then the monitor prints it, tagged with the view's role.
* :class:`LlmCallMonitor` -- the formatter/printer. It also keeps a small
  bounded buffer of primitive records (:meth:`LlmCallMonitor.drain`), which the
  live Penn server drains into the event feed after every tick
  (``PennStepper.drain_events``) -- so the Godot viewer's run monitor shows the
  same one-line-per-request log this module prints in the terminal (#398).

Role attribution: the planner and reflector get their own client (and view),
so a static role is exact. The brain client is shared between *decide* and
*converse*, so its view is bound to the client's live ``context`` dict
(:meth:`RoleTaggedLedger.bind_context`) and the two call sites in
``run_simulation.step`` / ``smallville_agents.maybe_converse`` stamp
``{"role": ...}`` into that context along with the actor/turn they already
set. ``record_call`` reads the context synchronously inside the call frame, so
the role the view resolves is always the current call's.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque

from text_adventure_games.usage import CallRecord, UsageLedger

# ANSI codes, used only when color is enabled (see LlmCallMonitor.__init__).
_RESET = "\x1b[0m"
_DIM = "\x1b[2m"
_RED = "\x1b[31m"
_ROLE_COLORS = {
    "decide": "\x1b[36m",  # cyan
    "converse": "\x1b[35m",  # magenta
    "plan": "\x1b[34m",  # blue
    "reflect": "\x1b[32m",  # green
}


class LlmCallMonitor:
    """Format and print one line per LLM call; keep counters for the run.

    ``stream`` defaults to stdout. ``color=None`` auto-detects: on only when
    the stream is a TTY and ``NO_COLOR`` is unset (the same gate the engine's
    terminal renderer uses). ``max_kept`` bounds the buffer :meth:`drain`
    serves -- old records fall off the front, the printed lines are the record
    of record.

    Thread-safety: the live loop runs each tick (and so each call) in a worker
    thread while uvicorn logs from the event loop, so every row goes out as a
    single ``write()`` + ``flush()`` and the counter/buffer mutate under a
    lock. Formatting failures must never break the model call that triggered
    them -- :meth:`RoleTaggedLedger.record` wraps :meth:`on_call` accordingly.
    """

    def __init__(self, stream=None, color: bool | None = None, max_kept: int = 1000):
        self.stream = stream if stream is not None else sys.stdout
        if color is None:
            isatty = getattr(self.stream, "isatty", lambda: False)
            color = bool(isatty()) and not os.environ.get("NO_COLOR")
        self.color = color
        self.calls = 0
        self._kept: deque[dict] = deque(maxlen=max_kept)
        self._lock = threading.Lock()
        self._header_printed = False

    # ------------------------------------------------------------- format

    @staticmethod
    def _fmt_row(n: int, wall: str, role: str, rec: CallRecord, cum_cost: float) -> str:
        """The plain (uncolored) row. Static so tests can pin it directly."""
        u = rec.usage
        actor = (rec.actor or "-")[:18]
        turn = "-" if rec.turn is None else str(rec.turn)
        latency = "-" if rec.latency_ms is None else f"{rec.latency_ms:.0f}ms"
        cost = f"${rec.cost_usd:.6f}"
        return (
            f" #{n:>5} {wall}  {role:<8}  {actor:<18}  t {turn:>4}  "
            f"{u.model:<16}  in {u.total_input_tokens:>6} "
            f"({u.cache_creation_input_tokens:>4}w/{u.cache_read_input_tokens:>5}r)  "
            f"out {u.output_tokens:>4}  {latency:>7}  "
            f"{cost:>10}  Σ ${cum_cost:.6f}"
        )

    def _colorize(self, line: str, role: str, over_budget: bool) -> str:
        """Tint the role token (and the whole line red once over budget)."""
        if over_budget:
            return f"{_RED}{line}{_RESET}"
        tint = _ROLE_COLORS.get(role)
        if tint:
            line = line.replace(f"  {role:<8}  ", f"  {tint}{role:<8}{_RESET}  ", 1)
        return line

    # -------------------------------------------------------------- hooks

    def on_call(self, rec: CallRecord, role: str, base: UsageLedger) -> None:
        """Print one row for *rec* (already stored in *base*) tagged *role*."""
        wall = time.strftime("%H:%M:%S")
        with self._lock:
            self.calls += 1
            n = self.calls
            cum = base.total_cost_usd()
            kept = rec.to_primitive()
            # The extras the printed row has over the raw record -- kept on the
            # buffered copy too, so a viewer can render the same line.
            kept.update(
                {
                    "role": role,
                    "call_no": n,
                    "cum_cost_usd": round(cum, 6),
                    "time": wall,
                }
            )
            self._kept.append(kept)
        line = self._fmt_row(n, wall, role, rec, cum)
        if self.color:
            line = self._colorize(line, role, base.over_budget())
        out = ""
        if not self._header_printed:
            self._header_printed = True
            header = (
                " LLM calls -- one line per model request "
                "(#, time, role, actor, sim turn, model, tokens in (cache w/r), "
                "tokens out, latency, $ this call, Σ $ run):"
            )
            out += (f"{_DIM}{header}{_RESET}" if self.color else header) + "\n"
        # One write + flush per row so lines never shear against uvicorn's logs.
        self.stream.write(out + line + "\n")
        self.stream.flush()

    def drain(self) -> list[dict]:
        """Return (and clear) the buffered primitive records -- the seam the
        live server pumps into the event feed for the viewer's request log."""
        with self._lock:
            kept = list(self._kept)
            self._kept.clear()
        return kept


class RoleTaggedLedger(UsageLedger):
    """A write-through view of a shared base ledger, tagged with a role.

    Hand one of these to each LLM client as its ``ledger``. Every
    :meth:`record` delegates to the *base* ledger **first** -- accounting
    (``GET /usage``, ``over_budget``, an attached ``RunLog``) can never be lost
    to a formatting bug -- and only then notifies the monitor, swallowing any
    error it raises. The view itself keeps no records and no ceiling: never
    hand a view to anything that sums a ledger; that is the base's job.

    ``role`` is the static tag (exact for the planner/reflector, which own
    their client). For the shared brain client, call :meth:`bind_context` with
    the client's ``context`` dict after construction: the decide/converse call
    sites stamp ``context["role"]`` per call, and the view reads it live --
    falling back to the static tag when no stamp is present (e.g. the mock
    schedule brain's zero-cost records).
    """

    def __init__(
        self,
        base: UsageLedger,
        monitor: LlmCallMonitor,
        role: str,
        context: dict | None = None,
    ):
        super().__init__()
        self._base = base
        self._monitor = monitor
        self._role = role
        self._ctx = context

    def bind_context(self, ctx: dict) -> None:
        """Resolve the role per call from *ctx* (a client's live ``context``)."""
        self._ctx = ctx

    def record(
        self,
        rec: CallRecord,
        *,
        messages: list[dict] | None = None,
        response: str | None = None,
    ) -> None:
        self._base.record(rec, messages=messages, response=response)
        try:
            role = (self._ctx or {}).get("role") or self._role
            self._monitor.on_call(rec, role, self._base)
        except Exception:
            pass  # the printed line is a luxury; the stored record is not
