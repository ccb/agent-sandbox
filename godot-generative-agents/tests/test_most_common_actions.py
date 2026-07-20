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
