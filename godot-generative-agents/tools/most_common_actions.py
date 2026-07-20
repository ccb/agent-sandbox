#!/usr/bin/env python3
"""Aggregate GameEvent records into a ranked most-common-actions report (#699).

Reads a run's ``events.jsonl`` (or a baked replay's top-level ``events``
array) -- one bare ``GameEvent.to_primitive()`` dict per record (#467) -- and
emits a **filter -> group -> rank** report: which action agents took most
often, by how many distinct actors, over which turns, with a per-actor mix.

    uv run python godot-generative-agents/tools/most_common_actions.py events.jsonl
    uv run python godot-generative-agents/tools/most_common_actions.py events.jsonl --format json
    uv run python godot-generative-agents/tools/most_common_actions.py penn_replay.json \\
        --out-md most_common.md --out-json most_common.json

This tool is read-only and offline: it never edits its input and has no engine
import (a plain dict reader, matching the other standalone scripts under
``godot-generative-agents/tools/`` and the sibling ``most_wanted_actions.py``,
#623). It is the supply-side mirror of that demand-side (wish) report.

Engine-internal event kinds -- ``EventKind.TRIGGER``/``EventKind.SOUND`` (see
``text_adventure_games/enums.py``), the ``"trigger"``/``"sound"`` action
values the trigger system and ``Game.emit_sound`` write -- are dropped so the
ranking is player/NPC *commands* only. Those two string values are reproduced
here rather than imported (this tool has no engine dependency); if the engine
grows a new non-command EventKind, add it to ``EXCLUDED_KINDS`` below.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Engine-internal GameEvent.action values that are NOT player/NPC commands:
# EventKind.TRIGGER and EventKind.SOUND (text_adventure_games/enums.py),
# reproduced here rather than imported (this tool has no engine dependency).
EXCLUDED_KINDS = frozenset({"trigger", "sound"})


# --- load --------------------------------------------------------------


def load_records(path: str | Path) -> list[dict]:
    """Bare ``GameEvent.to_primitive()`` dicts read from *path*.

    Accepts two shapes, chosen by suffix (not content-sniffed): a ``.jsonl``
    file (one JSON object per line, no wrapper -- a run's ``events.jsonl``),
    or a baked replay ``.json`` whose top-level ``events`` key is a JSON array
    of the same dicts.
    """
    path = Path(path)
    if path.suffix == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data.get("events", [])
    if not isinstance(events, list):
        raise ValueError(f"{path}: top-level 'events' is not a JSON array")
    return events


# --- aggregate: filter -> group -> rank -------------------------------------


@dataclass
class ActionCount:
    """One ranked row: an action verb and who took it."""

    action: str  # the GameEvent.action verb, e.g. "go"
    count: int  # total kept events with this action
    distinct_actors: int  # unique non-null actors who took it
    actor_mix: dict  # actor -> count within this action, keys sorted
    first_turn: int  # min `turn` in the group
    last_turn: int  # max `turn` in the group


@dataclass
class Report:
    """The whole aggregation: ranked rows plus file-wide totals."""

    rows: list  # list[ActionCount], already ranked
    total_actions: int  # kept records the report was built from
    actor_totals: dict  # actor -> count across every kept record, keys sorted


def build_report(records: list[dict]) -> Report:
    """filter -> group -> rank the raw event dicts into a ``Report``.

    Engine-internal kinds (``EXCLUDED_KINDS``) are dropped first. Ranking is
    **count desc**; ties break **distinct-actors desc, then the action verb
    ascending** -- both criteria are part of the sort key itself, so the order
    is fully deterministic and never depends on dict/set iteration order (the
    golden test pins exactly this order).
    """
    kept = [r for r in records if r.get("action") not in EXCLUDED_KINDS]

    groups: dict[str, list[dict]] = {}
    for rec in kept:
        groups.setdefault(rec.get("action", ""), []).append(rec)

    rows = [_row_for(action, recs) for action, recs in groups.items()]
    rows.sort(key=lambda row: (-row.count, -row.distinct_actors, row.action))

    actor_totals = Counter(r.get("actor") for r in kept if r.get("actor"))
    return Report(
        rows=rows,
        total_actions=len(kept),
        actor_totals=dict(sorted(actor_totals.items())),
    )


def _row_for(action: str, recs: list[dict]) -> ActionCount:
    actor_mix = Counter(r.get("actor") for r in recs if r.get("actor"))
    turns = [r.get("turn", 0) for r in recs]
    return ActionCount(
        action=action,
        count=len(recs),
        distinct_actors=len(actor_mix),
        actor_mix=dict(sorted(actor_mix.items())),
        first_turn=min(turns),
        last_turn=max(turns),
    )
