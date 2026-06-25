"""Overlay a recorded mock run onto a chain spec.

A RunLog JSONL (written by :class:`text_adventure_games.usage.RunLog`) has one
``"call"`` line per LLM call. With ``log_prompts=True`` each line also carries
the prompt ``messages`` and the ``response``. This module reads such a log and
works out which chain nodes and edges actually fired -- plus the real
prompt/response behind each -- so the static DAG can be highlighted with a
concrete run.

Mapping is best-effort and deliberately simple (this is a teaching/debug aid):

* **Content match (needs ``log_prompts=True``):** a call is assigned to the node
  whose template, rendered with its sample, shares the longest leading prefix
  with the call's system message. The templates start with distinct static text
  ("You are an NPC...", "You are the parser...", "You are the narrator..."), so
  the prefix length separates a decision call from a parse/narrate call and the
  parse/narrate sub-types from one another.
* **Structural:** ``attempt > 0`` on any call means a reflect-and-retry happened,
  which lights the gate's back-edge to the decision node.

Note: ``prompt_sha256`` hashes the *messages*, not the template, so it is a
replay key -- not a node key -- and is intentionally not used for mapping here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .spec import ChainSpec
from .templates import node_prompt

# A call is only assigned to a node if the common prefix clears this many chars,
# which is enough to separate "You are an NPC" / "the parser" / "the narrator".
_MIN_PREFIX = 12


@dataclass
class Overlay:
    """Which nodes/edges fired in a run, plus the real prompts behind them."""

    provider: str | None = None
    model: str | None = None
    seed: object | None = None
    call_count: int = 0
    has_prompts: bool = False
    fired_nodes: set[str] = field(default_factory=set)
    fired_edges: set[tuple[str, str]] = field(default_factory=set)
    # node id -> list of {turn, actor, attempt, system, user, response}
    actuals: dict[str, list[dict]] = field(default_factory=dict)
    note: str = ""


def load_runlog(path: str | Path) -> list[dict]:
    """Parse a RunLog JSONL file into a list of line dicts (blank lines skipped)."""
    lines = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            lines.append(json.loads(raw))
    return lines


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def _system_text(call: dict) -> str:
    msgs = call.get("messages") or []
    for m in msgs:
        if m.get("role") == "system":
            return m.get("content") or ""
    return (msgs[0].get("content") or "") if msgs else ""


def _user_text(call: dict) -> str:
    msgs = call.get("messages") or []
    for m in reversed(msgs):
        if m.get("role") == "user":
            return m.get("content") or ""
    return ""


def map_to_chain(runlog: list[dict], spec: ChainSpec) -> Overlay:
    """Build an :class:`Overlay` from parsed RunLog lines and a chain spec."""
    header = next((l for l in runlog if l.get("kind") == "run"), {})
    calls = [l for l in runlog if l.get("kind") == "call"]

    ov = Overlay(
        provider=header.get("provider"),
        model=header.get("model"),
        seed=header.get("seed"),
        call_count=len(calls),
    )
    ov.has_prompts = any("messages" in c for c in calls)

    # Render each templated node once for content matching.
    candidates: dict[str, str] = {}
    for n in spec.nodes:
        if not n.template:
            continue
        rendered = node_prompt(n.template, n.example_vars, spec.templates_for(n)).get(
            "rendered"
        )
        if rendered:
            candidates[n.id] = rendered

    gate_ids = {n.id for n in spec.nodes if n.kind == "gate"}
    start_ids = {n.id for n in spec.nodes if n.kind == "start"}
    retry_observed = any((c.get("attempt") or 0) > 0 for c in calls)

    for c in calls:
        if not ov.has_prompts:
            break
        system = _system_text(c)
        best_id, best_len = None, 0
        for node_id, text in candidates.items():
            cp = _common_prefix_len(system, text)
            if cp > best_len:
                best_id, best_len = node_id, cp
        if best_id is None or best_len < _MIN_PREFIX:
            continue
        ov.fired_nodes.add(best_id)
        ov.actuals.setdefault(best_id, []).append(
            {
                "turn": c.get("turn"),
                "actor": c.get("actor"),
                "attempt": c.get("attempt"),
                "system": system,
                "user": _user_text(c),
                "response": c.get("response"),
            }
        )

    # A run that routes a decision always passes through the gate and starts a
    # turn, even though neither is an LLM call.
    decision_fired = any(
        nid in ov.fired_nodes
        for nid in (n.id for n in spec.nodes if n.kind == "decision")
    )
    if decision_fired or ov.fired_nodes:
        ov.fired_nodes |= gate_ids | start_ids

    # An edge lights when both endpoints fired; the retry back-edge also needs a
    # retry to have actually happened (attempt > 0).
    for e in spec.edges:
        if e.source in ov.fired_nodes and e.target in ov.fired_nodes:
            if e.condition == "precondition_failure" and not retry_observed:
                continue
            ov.fired_edges.add((e.source, e.target))

    if not ov.has_prompts:
        ov.note = (
            "RunLog has no prompts (re-run with RunLog(log_prompts=True) to map "
            "calls to nodes)."
        )
    elif not ov.fired_nodes:
        ov.note = "No calls matched this chain's templates."
    return ov
