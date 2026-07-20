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
    if not isinstance(data, dict) or "events" not in data:
        raise ValueError(f"{path}: no top-level 'events' array (not a baked replay?)")
    events = data["events"]
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
    kept = [r for r in records if r.get("action", "") not in EXCLUDED_KINDS]

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


# --- render ------------------------------------------------------------


def _escape_md(text: str) -> str:
    """Keep free-text (actor names, verbs) from breaking a Markdown row."""
    return text.replace("|", "\\|").replace("\n", " ")


def _fmt_mix(mix: dict) -> str:
    """Render an already-sorted ``name -> count`` mix as ``"a=1, b=2"``."""
    return ", ".join(f"{_escape_md(k)}={v}" for k, v in mix.items())


def render_markdown(report: Report) -> str:
    """The human report: a summary + one ranked table."""
    lines = [
        "# Most-Common Actions Report",
        "",
        f"- total actions: {report.total_actions}",
        f"- distinct actions: {len(report.rows)}",
        f"- actor totals: {_fmt_mix(report.actor_totals) or '-'}",
        "",
        "| Rank | Action | Count | Actors | Turns | Actor mix |",
        "|---|---|---|---|---|---|",
    ]
    for rank, row in enumerate(report.rows, start=1):
        mix = _fmt_mix(row.actor_mix) if row.actor_mix else "-"
        lines.append(
            f"| {rank} | {_escape_md(row.action)} | {row.count} |"
            f" {row.distinct_actors} | {row.first_turn}-{row.last_turn} |"
            f" {mix} |"
        )
    return "\n".join(lines) + "\n"


def render_json(report: Report) -> dict:
    """The machine report: same data as the Markdown, JSON-ready."""
    return {
        "total_actions": report.total_actions,
        "actor_totals": report.actor_totals,
        "actions": len(report.rows),
        "rows": [
            {
                "action": row.action,
                "count": row.count,
                "distinct_actors": row.distinct_actors,
                "actor_mix": row.actor_mix,
                "first_turn": row.first_turn,
                "last_turn": row.last_turn,
            }
            for row in report.rows
        ],
    }


# --- CLI -----------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("input", type=Path, help="events.jsonl, or a baked replay .json")
    ap.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help=(
            "stdout format when neither --out-md nor --out-json is given "
            "(default: md); ignored when either --out-* flag is given -- then "
            "nothing prints to stdout but the 'wrote <path>' lines, and each "
            "report is written only via its own flag"
        ),
    )
    ap.add_argument(
        "--out-md", type=Path, help="write the Markdown report to this path"
    )
    ap.add_argument("--out-json", type=Path, help="write the JSON report to this path")
    args = ap.parse_args(argv)

    records = load_records(args.input)
    report = build_report(records)

    wrote = False
    if args.out_md:
        args.out_md.write_text(render_markdown(report), encoding="utf-8")
        print(f"wrote {args.out_md}")
        wrote = True
    if args.out_json:
        args.out_json.write_text(
            json.dumps(render_json(report), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.out_json}")
        wrote = True

    if not wrote:
        if args.format == "json":
            print(json.dumps(render_json(report), indent=2, ensure_ascii=False))
        else:
            print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
