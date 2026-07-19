#!/usr/bin/env python3
"""Aggregate wish records into a ranked most-wanted-actions report (#623).

Reads a run's ``wishes.jsonl`` (or a baked replay's top-level ``wishes``
array) -- the demand-side records #622 produces, one bare
``ActionWish.to_primitive()`` dict per record -- and emits a **normalize ->
group -> rank** report: which desired-but-missing action is wanted most,
by how many distinct agents, under which triggers, with example reasons.

    uv run python godot-generative-agents/tools/most_wanted_actions.py wishes.jsonl
    uv run python godot-generative-agents/tools/most_wanted_actions.py wishes.jsonl --format json
    uv run python godot-generative-agents/tools/most_wanted_actions.py penn_replay.json \\
        --out-md most_wanted.md --out-json most_wanted.json

This tool is read-only and offline: it never edits its input, has no engine
import (a plain dict reader, matching the other standalone scripts under
``godot-generative-agents/tools/``), and does no LLM-assisted paraphrase
clustering -- v1 groups by a simple normalized string only (see
``normalize_desired``); clustering paraphrases like "fill the pot" / "get
water into the pot" together is explicit future work (#623).

``trigger`` is an OPEN set -- today ``proposed`` and ``parse_gap`` (see
``text_adventure_games/wishes.py``), with ``craft_gap`` arriving later. This
tool never hardcodes or whitelists trigger values: whatever appears in the
input is aggregated and reported in the trigger mix.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# --- normalization (v1) -----------------------------------------------------

# A small, closed set of leading verbs worth stripping before grouping: the
# crafting verbs the parser recognizes (mirrors CRAFT_VERBS /
# Craft._strip_verb in text_adventure_games/actions/things.py, reproduced
# here rather than imported -- this tool has no engine dependency) plus
# "propose" itself, in case a `desired` string wasn't already stripped of it
# (the Propose action strips it when it builds the record, but this is a
# defensive, documented normalization step, not a re-derivation of #620/#621).
_LEAD_VERBS = (
    "propose",
    "craft",
    "make",
    "cook",
    "brew",
    "forge",
    "mix",
    "combine",
    "assemble",
    "build",
    "braid",
)
_LEAD_ARTICLES = ("a ", "an ", "the ", "some ")

# Cap on how many distinct example reasons a row carries -- enough to show
# the *variety* of a group's motivations to a world-author without the report
# growing unbounded for a heavily-wished-for action.
_MAX_EXAMPLE_REASONS = 3

# Cap on how many distinct example goals a row carries -- same idea as
# _MAX_EXAMPLE_REASONS, kept as a separate constant because a wish's reason
# and the goal it serves are conceptually different fields that don't have
# to move together, even though both start at 3.
_MAX_EXAMPLE_GOALS = 3


def normalize_desired(desired: str) -> str:
    """The v1 grouping key for a wish's desired-action phrase.

    Deliberately simple STRING normalization, not semantic clustering:
    lowercase, strip outer whitespace, collapse interior whitespace runs to
    one space, then drop at most one leading craft/propose verb and at most
    one leading article -- each only if trivially present as the very first
    token(s). So "propose a bike rack", "A Bike Rack", and "the   bike  rack"
    all normalize to "bike rack"; "get a bike rack built" does not (paraphrase
    clustering is future work, #623 -- this function never attempts it).
    """
    text = " ".join((desired or "").strip().lower().split())
    if not text:
        return text
    first, _, rest = text.partition(" ")
    if first in _LEAD_VERBS and rest:
        text = rest
    for lead in _LEAD_ARTICLES:
        if text.startswith(lead):
            text = text[len(lead) :]
            break
    return text.strip()


# --- load --------------------------------------------------------------


def load_records(path: str | Path) -> list[dict]:
    """Bare ``ActionWish.to_primitive()`` dicts read from *path*.

    Accepts the two #622 shapes, chosen by suffix (not content-sniffed):
    a ``.jsonl`` file (one JSON object per line, no wrapper), or a baked
    replay ``.json`` whose top-level ``wishes`` key is a JSON array of the
    same dicts.
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
    wishes = data.get("wishes", [])
    if not isinstance(wishes, list):
        raise ValueError(f"{path}: top-level 'wishes' is not a JSON array")
    return wishes


# --- aggregate: normalize -> group -> rank ----------------------------------


@dataclass
class ActionDemand:
    """One ranked row: a normalized desired-action group."""

    key: str  # the normalized group key (normalize_desired's output)
    representative: str  # the first (file-order) record's original `desired`
    count: int  # total wish records in the group
    distinct_agents: int  # unique non-null `actor` values in the group
    trigger_mix: dict  # trigger -> count within the group, keys sorted
    example_reasons: list  # up to _MAX_EXAMPLE_REASONS distinct non-empty reasons
    example_goals: list  # up to _MAX_EXAMPLE_GOALS distinct goal strings, flattened
    first_turn: int  # min `turn` in the group
    last_turn: int  # max `turn` in the group


@dataclass
class Report:
    """The whole aggregation: ranked rows plus file-wide totals."""

    rows: list  # list[ActionDemand], already ranked
    total_wishes: int  # len(records) the report was built from
    trigger_totals: dict  # trigger -> count, across every record, keys sorted


def build_report(records: list[dict]) -> Report:
    """normalize -> group -> rank the raw wish dicts into a ``Report``.

    Ranking is **count desc**; ties break **distinct-agents desc, then the
    normalized group key ascending** -- both criteria are part of the sort
    key itself, so the order is fully deterministic and never depends on
    dict/set iteration order (the golden test pins exactly this order).
    """
    groups: dict[str, list[dict]] = {}
    for rec in records:
        key = normalize_desired(rec.get("desired", ""))
        groups.setdefault(key, []).append(rec)

    rows = [_row_for(key, recs) for key, recs in groups.items()]
    rows.sort(key=lambda row: (-row.count, -row.distinct_agents, row.key))

    trigger_totals = Counter(rec.get("trigger", "") for rec in records)
    return Report(
        rows=rows,
        total_wishes=len(records),
        trigger_totals=dict(sorted(trigger_totals.items())),
    )


def _row_for(key: str, recs: list[dict]) -> ActionDemand:
    agents = {r.get("actor") for r in recs if r.get("actor")}
    triggers = Counter(r.get("trigger", "") for r in recs)

    reasons: list[str] = []
    for r in recs:
        reason = (r.get("reason") or "").strip()
        if reason and reason not in reasons:
            reasons.append(reason)
        if len(reasons) >= _MAX_EXAMPLE_REASONS:
            break

    goals: list[str] = []
    for r in recs:
        for g in r.get("goals") or []:
            g = (g or "").strip()
            if g and g not in goals:
                goals.append(g)
            if len(goals) >= _MAX_EXAMPLE_GOALS:
                break
        if len(goals) >= _MAX_EXAMPLE_GOALS:
            break

    turns = [r.get("turn", 0) for r in recs]
    return ActionDemand(
        key=key,
        representative=recs[0].get("desired", ""),
        count=len(recs),
        distinct_agents=len(agents),
        trigger_mix=dict(sorted(triggers.items())),
        example_reasons=reasons,
        example_goals=goals,
        first_turn=min(turns),
        last_turn=max(turns),
    )


# --- render ------------------------------------------------------------


def _escape_md(text: str) -> str:
    """Keep free-text wish content from breaking a Markdown table row."""
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: Report) -> str:
    """The human (world-author) report: a summary + one ranked table."""
    trigger_line = ", ".join(f"{k}={v}" for k, v in report.trigger_totals.items())
    lines = [
        "# Most-Wanted Actions Report",
        "",
        f"- total wishes: {report.total_wishes}",
        f"- distinct groups: {len(report.rows)}",
        f"- trigger mix: {trigger_line}",
        "",
        "| Rank | Desired action | Count | Agents | Turns | Trigger mix |"
        " Example reasons | Goals blocked |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for rank, row in enumerate(report.rows, start=1):
        triggers = ", ".join(f"{k}={v}" for k, v in row.trigger_mix.items())
        reasons = (
            "; ".join(_escape_md(r) for r in row.example_reasons)
            if row.example_reasons
            else "-"
        )
        goals = (
            "; ".join(_escape_md(g) for g in row.example_goals)
            if row.example_goals
            else "-"
        )
        lines.append(
            f"| {rank} | {_escape_md(row.key)}"
            f' (e.g. "{_escape_md(row.representative)}") | {row.count} |'
            f" {row.distinct_agents} | {row.first_turn}-{row.last_turn} |"
            f" {triggers} | {reasons} | {goals} |"
        )
    return "\n".join(lines) + "\n"


def render_json(report: Report) -> dict:
    """The machine report: same data as the Markdown, JSON-ready."""
    return {
        "total_wishes": report.total_wishes,
        "trigger_totals": report.trigger_totals,
        "groups": len(report.rows),
        "rows": [
            {
                "key": row.key,
                "representative": row.representative,
                "count": row.count,
                "distinct_agents": row.distinct_agents,
                "trigger_mix": row.trigger_mix,
                "example_reasons": row.example_reasons,
                "example_goals": row.example_goals,
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
    ap.add_argument("input", type=Path, help="wishes.jsonl, or a baked replay .json")
    ap.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help=(
            "stdout format when neither --out-md nor --out-json is given "
            "(default: md); ignored if either --out-md or --out-json is "
            "given -- in that case nothing prints to stdout except the "
            "'wrote <path>' lines, and both formats are written via their "
            "respective flags regardless of --format"
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
