"""Golden test for the most-common-actions report (#699).

Pins the aggregator's ranking, filtering, and output exactly against a small,
hand-authored ``events_sample.jsonl`` fixture (fixtures/events_sample.jsonl)
of bare ``GameEvent.to_primitive()`` dicts. The fixture exercises, in one
pass:

- ranking several verbs by count desc;
- a count TIE between "wait" and "eat" (3 records each) broken by
  distinct-actors desc -- deliberately set up so alphabetical order and
  file-insertion order both *disagree* with the correct answer: "eat" sorts
  alphabetically before "wait" and its first record appears earlier in the
  file, yet "wait" has 3 distinct actors vs "eat"'s 2, so it must outrank
  "eat" -- an order only the documented `(-count, -distinct_actors, action)`
  sort key produces;
- two engine-internal event kinds ("trigger", "sound") that must be dropped
  from every count, so total_actions and the ranking see commands only;
- a null ``actor`` (a "read" event with no resolvable actor), which counts
  toward its group's record count but not its distinct-actor count, and never
  creates a phantom actor bucket in actor_mix / actor_totals.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(_TOOLS_DIR))

import most_common_actions as mca  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "events_sample.jsonl"


def _load():
    return mca.load_records(FIXTURE)


# --- load_records --------------------------------------------------------


def test_load_records_reads_the_fixture_jsonl():
    records = _load()
    assert len(records) == 13
    assert records[0]["action"] == "go"


def test_load_records_reads_a_baked_replay_json(tmp_path):
    replay = {"schema_version": 1, "events": _load()}
    out = tmp_path / "penn_replay.json"
    out.write_text(json.dumps(replay))
    assert mca.load_records(out) == _load()


def test_load_records_rejects_json_without_an_events_array(tmp_path):
    # A .json that isn't a baked replay (no top-level "events") must fail loud,
    # not silently report zero actions.
    out = tmp_path / "not_a_replay.json"
    out.write_text(json.dumps({"schema_version": 1}))
    with pytest.raises(ValueError):
        mca.load_records(out)


# --- build_report: filter / group / rank / tiebreak ----------------------


def test_report_drops_engine_internal_kinds():
    # The 13-line fixture has 2 engine kinds ("trigger", "sound") that must be
    # dropped, leaving 11 command records across 4 verbs.
    report = mca.build_report(_load())
    assert report.total_actions == 11
    verbs = [row.action for row in report.rows]
    assert "trigger" not in verbs
    assert "sound" not in verbs


def test_report_ranks_by_count_then_distinct_actors_then_action():
    report = mca.build_report(_load())
    assert [row.action for row in report.rows] == ["go", "wait", "eat", "read"]


def test_tie_on_count_is_broken_by_distinct_actors():
    # "eat" sorts alphabetically BEFORE "wait", and its first record appears
    # EARLIER in the fixture -- so an alphabetical-only or insertion-order-only
    # tiebreak would rank it first. distinct-actors-desc overrides both.
    report = mca.build_report(_load())
    wait, eat = report.rows[1], report.rows[2]
    assert wait.action == "wait"
    assert eat.action == "eat"
    assert wait.count == eat.count == 3
    assert wait.distinct_actors == 3
    assert eat.distinct_actors == 2  # fewer distinct actors -> ranks lower
    assert eat.action < wait.action  # despite the alphabetically-earlier key


def test_row_fields_for_the_go_group():
    report = mca.build_report(_load())
    row = report.rows[0]
    assert row.action == "go"
    assert row.count == 4
    assert row.distinct_actors == 3
    assert row.actor_mix == {
        "Diego Torres": 2,
        "Professor Tanaka": 1,
        "Sofia Ramirez": 1,
    }
    assert row.first_turn == 0
    assert row.last_turn == 2


def test_null_actor_counts_the_record_but_not_the_actor():
    report = mca.build_report(_load())
    row = report.rows[3]
    assert row.action == "read"
    assert row.count == 1
    assert row.distinct_actors == 0
    assert row.actor_mix == {}  # a null actor never creates a bucket


def test_actor_totals_exclude_null_and_are_sorted():
    report = mca.build_report(_load())
    assert report.actor_totals == {
        "Diego Torres": 5,
        "Professor Tanaka": 2,
        "Sofia Ramirez": 3,
    }
    # dict == ignores key order; pin the sort explicitly so a dropped sorted()
    # is caught here and not only by the golden-Markdown test.
    assert list(report.actor_totals) == [
        "Diego Torres",
        "Professor Tanaka",
        "Sofia Ramirez",
    ]


# --- golden: exact Markdown + JSON output ---------------------------------

EXPECTED_MARKDOWN = (
    "# Most-Common Actions Report\n"
    "\n"
    "- total actions: 11\n"
    "- distinct actions: 4\n"
    "- actor totals: Diego Torres=5, Professor Tanaka=2, Sofia Ramirez=3\n"
    "\n"
    "| Rank | Action | Count | Actors | Turns | Actor mix |\n"
    "|---|---|---|---|---|---|\n"
    "| 1 | go | 4 | 3 | 0-2 | Diego Torres=2, Professor Tanaka=1, Sofia Ramirez=1 |\n"
    "| 2 | wait | 3 | 3 | 2-6 | Diego Torres=1, Professor Tanaka=1, Sofia Ramirez=1 |\n"
    "| 3 | eat | 3 | 2 | 1-5 | Diego Torres=2, Sofia Ramirez=1 |\n"
    "| 4 | read | 1 | 0 | 7-7 | - |\n"
)

EXPECTED_JSON = {
    "total_actions": 11,
    "actor_totals": {"Diego Torres": 5, "Professor Tanaka": 2, "Sofia Ramirez": 3},
    "actions": 4,
    "rows": [
        {
            "action": "go",
            "count": 4,
            "distinct_actors": 3,
            "actor_mix": {"Diego Torres": 2, "Professor Tanaka": 1, "Sofia Ramirez": 1},
            "first_turn": 0,
            "last_turn": 2,
        },
        {
            "action": "wait",
            "count": 3,
            "distinct_actors": 3,
            "actor_mix": {"Diego Torres": 1, "Professor Tanaka": 1, "Sofia Ramirez": 1},
            "first_turn": 2,
            "last_turn": 6,
        },
        {
            "action": "eat",
            "count": 3,
            "distinct_actors": 2,
            "actor_mix": {"Diego Torres": 2, "Sofia Ramirez": 1},
            "first_turn": 1,
            "last_turn": 5,
        },
        {
            "action": "read",
            "count": 1,
            "distinct_actors": 0,
            "actor_mix": {},
            "first_turn": 7,
            "last_turn": 7,
        },
    ],
}


def test_render_markdown_is_pinned():
    report = mca.build_report(_load())
    assert mca.render_markdown(report) == EXPECTED_MARKDOWN


def test_render_json_is_pinned():
    report = mca.build_report(_load())
    assert mca.render_json(report) == EXPECTED_JSON


# --- _escape_md: Markdown cells survive stray "|" / newlines --------------


def test_escape_md_escapes_pipes_and_newlines():
    assert mca._escape_md("a | b") == "a \\| b"
    assert mca._escape_md("line one\nline two") == "line one line two"


def test_render_markdown_escapes_a_pipe_in_an_actor_name():
    # A hand-built report whose actor name carries a literal "|" -- free-form
    # text that would otherwise add a phantom column to the table row.
    row = mca.ActionCount(
        action="go",
        count=1,
        distinct_actors=1,
        actor_mix={"Od|d Name": 1},
        first_turn=1,
        last_turn=1,
    )
    report = mca.Report(rows=[row], total_actions=1, actor_totals={"Od|d Name": 1})
    md = mca.render_markdown(report)
    lines = md.splitlines()
    header = next(l for l in lines if l.startswith("| Rank |"))
    data_line = next(l for l in lines if l.startswith("| 1 |"))
    # Once escaped "\|" pairs are removed, only real column separators remain,
    # and there must be exactly as many as in the header.
    assert data_line.replace("\\|", "").count("|") == header.count("|")
    assert "Od\\|d Name=1" in data_line


# --- CLI ------------------------------------------------------------------


def test_main_writes_out_md_and_out_json(tmp_path):
    out_md = tmp_path / "report.md"
    out_json = tmp_path / "report.json"
    rc = mca.main([str(FIXTURE), "--out-md", str(out_md), "--out-json", str(out_json)])
    assert rc == 0
    assert out_md.read_text() == EXPECTED_MARKDOWN
    assert json.loads(out_json.read_text()) == EXPECTED_JSON


def test_main_prints_markdown_to_stdout_by_default(capsys):
    rc = mca.main([str(FIXTURE)])
    assert rc == 0
    assert capsys.readouterr().out == EXPECTED_MARKDOWN


def test_main_prints_json_to_stdout_with_format_flag(capsys):
    rc = mca.main([str(FIXTURE), "--format", "json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == EXPECTED_JSON
