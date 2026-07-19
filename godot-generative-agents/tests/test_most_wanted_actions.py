"""Golden test for the most-wanted-actions report (#623).

Pins the aggregator's Markdown + JSON output exactly against a small,
hand-authored ``wishes_sample.jsonl`` fixture (fixtures/wishes_sample.jsonl)
built to exercise, in one pass:

- normalization collapsing several distinct raw phrasings (case, outer/inner
  whitespace, a leading "propose"/article) into a single group -- the
  "book a study room" group (5 records, 3 distinct actors, 4 distinct
  reasons -- more than the 3-example cap);
- a count TIE between two groups ("bike rack near the library" and
  "working elevator", 3 records each) broken by distinct-agents desc --
  deliberately set up so alphabetical order and file-insertion order both
  *disagree* with the correct answer: "bike rack..." sorts alphabetically
  before "working elevator" and its first record appears earlier in the
  file, yet "working elevator" has 3 distinct agents vs "bike rack..."'s 2,
  so it must outrank "bike rack..." -- a golden order that can only be
  produced by the documented `(-count, -distinct_agents, key)` sort key,
  not by alphabetical-only or insertion-order tiebreaks (#623 review);
- a null ``actor`` (a parse-gap wish with no resolvable actor), which must
  count toward the group's record count but not its distinct-agent count;
- a mixed, open ``trigger`` vocabulary (``proposed`` and ``parse_gap``),
  aggregated without hardcoding either value.

The fixture's records are hand-authored dicts in the pinned #622
ActionWish.to_primitive() shape -- not literal engine output -- chosen to hit
these cases; a couple (e.g. an unstripped "propose ..." string filed as
trigger="parse_gap") wouldn't arise from the real engine today but are legal
inputs the normalizer must still handle.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(_TOOLS_DIR))

import most_wanted_actions as mwa  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "wishes_sample.jsonl"


def _load():
    return mwa.load_records(FIXTURE)


# --- normalize_desired --------------------------------------------------


def test_normalize_lowercases_strips_and_collapses_whitespace():
    # No leading article/verb here -- isolates case-folding + whitespace
    # handling from the article/verb stripping covered below.
    assert mwa.normalize_desired("  Bike   Rack ") == "bike rack"


def test_normalize_strips_a_leading_propose_verb_then_article():
    assert mwa.normalize_desired("propose a working elevator") == "working elevator"


def test_normalize_strips_a_leading_article_alone():
    assert mwa.normalize_desired("the working elevator") == "working elevator"


def test_normalize_leaves_an_unrecognized_leading_word_alone():
    # "dance" is neither a craft/propose verb nor an article -- untouched.
    assert mwa.normalize_desired("dance with the statue") == "dance with the statue"


def test_normalize_empty_string_stays_empty():
    assert mwa.normalize_desired("") == ""


# --- load_records --------------------------------------------------------


def test_load_records_reads_the_fixture_jsonl():
    records = _load()
    assert len(records) == 12
    assert records[0]["desired"] == "book a study room"


def test_load_records_reads_a_baked_replay_json(tmp_path):
    replay = {"schema_version": 1, "wishes": _load()}
    out = tmp_path / "penn_replay.json"
    out.write_text(json.dumps(replay))
    assert mwa.load_records(out) == _load()


# --- build_report: grouping / ranking / tiebreak --------------------------


def test_report_ranks_by_count_then_distinct_agents_then_key():
    report = mwa.build_report(_load())
    assert [row.key for row in report.rows] == [
        "book a study room",
        "working elevator",
        "bike rack near the library",
        "dance with the statue",
    ]


def test_report_totals():
    report = mwa.build_report(_load())
    assert report.total_wishes == 12
    assert report.trigger_totals == {"parse_gap": 5, "proposed": 7}


def test_row_fields_for_the_study_room_group():
    report = mwa.build_report(_load())
    row = report.rows[0]
    assert row.count == 5
    assert row.distinct_agents == 3
    assert row.trigger_mix == {"parse_gap": 1, "proposed": 4}
    assert row.first_turn == 1
    assert row.last_turn == 12
    assert row.representative == "book a study room"
    # 4 distinct reasons appear across the group; capped at 3, first-seen order.
    assert row.example_reasons == [
        "midterms are coming up",
        "group project needs space",
        "the library is always full",
    ]


def test_tie_on_count_is_broken_by_distinct_agents():
    # "bike rack near the library" sorts alphabetically BEFORE "working
    # elevator", and its first record appears EARLIER in the fixture file --
    # so an alphabetical-only or insertion-order-only tiebreak would rank it
    # first. The distinct-agents-desc tiebreak overrides both: elevator has
    # more distinct agents, so it must rank higher despite its later key and
    # later file position.
    report = mwa.build_report(_load())
    elevator, bike = report.rows[1], report.rows[2]
    assert elevator.key == "working elevator"
    assert bike.key == "bike rack near the library"
    assert elevator.count == bike.count == 3
    assert elevator.distinct_agents == 3
    assert bike.distinct_agents == 2  # fewer distinct agents -> ranks lower
    # despite an alphabetically-earlier, file-earlier key.
    assert bike.key < elevator.key


def test_null_actor_counts_the_record_but_not_the_agent():
    report = mwa.build_report(_load())
    row = report.rows[3]
    assert row.key == "dance with the statue"
    assert row.count == 1
    assert row.distinct_agents == 0
    assert row.example_reasons == []  # its only reason is ""


# --- golden: exact Markdown + JSON output ---------------------------------

EXPECTED_MARKDOWN = (
    "# Most-Wanted Actions Report\n"
    "\n"
    "- total wishes: 12\n"
    "- distinct groups: 4\n"
    "- trigger mix: parse_gap=5, proposed=7\n"
    "\n"
    "| Rank | Desired action | Count | Agents | Turns | Trigger mix | Example reasons |\n"
    "|---|---|---|---|---|---|---|\n"
    '| 1 | book a study room (e.g. "book a study room") | 5 | 3 | 1-12 |'
    " parse_gap=1, proposed=4 | midterms are coming up; group project needs space;"
    " the library is always full |\n"
    '| 2 | working elevator (e.g. "propose a working elevator") | 3 | 3 | 3-10 |'
    " parse_gap=2, proposed=1 | stairs are exhausting |\n"
    '| 3 | bike rack near the library (e.g. "a bike rack near the library") | 3 | 2 | 2-9 |'
    " parse_gap=1, proposed=2 | mine keeps getting stolen; need somewhere safe to lock up |\n"
    '| 4 | dance with the statue (e.g. "dance with the statue") | 1 | 0 | 4-4 |'
    " parse_gap=1 | - |\n"
)

EXPECTED_JSON = {
    "total_wishes": 12,
    "trigger_totals": {"parse_gap": 5, "proposed": 7},
    "groups": 4,
    "rows": [
        {
            "key": "book a study room",
            "representative": "book a study room",
            "count": 5,
            "distinct_agents": 3,
            "trigger_mix": {"parse_gap": 1, "proposed": 4},
            "example_reasons": [
                "midterms are coming up",
                "group project needs space",
                "the library is always full",
            ],
            "first_turn": 1,
            "last_turn": 12,
        },
        {
            "key": "working elevator",
            "representative": "propose a working elevator",
            "count": 3,
            "distinct_agents": 3,
            "trigger_mix": {"parse_gap": 2, "proposed": 1},
            "example_reasons": ["stairs are exhausting"],
            "first_turn": 3,
            "last_turn": 10,
        },
        {
            "key": "bike rack near the library",
            "representative": "a bike rack near the library",
            "count": 3,
            "distinct_agents": 2,
            "trigger_mix": {"parse_gap": 1, "proposed": 2},
            "example_reasons": [
                "mine keeps getting stolen",
                "need somewhere safe to lock up",
            ],
            "first_turn": 2,
            "last_turn": 9,
        },
        {
            "key": "dance with the statue",
            "representative": "dance with the statue",
            "count": 1,
            "distinct_agents": 0,
            "trigger_mix": {"parse_gap": 1},
            "example_reasons": [],
            "first_turn": 4,
            "last_turn": 4,
        },
    ],
}


def test_render_markdown_is_pinned():
    report = mwa.build_report(_load())
    assert mwa.render_markdown(report) == EXPECTED_MARKDOWN


def test_render_json_is_pinned():
    report = mwa.build_report(_load())
    assert mwa.render_json(report) == EXPECTED_JSON


# --- _escape_md: Markdown table cells must survive stray "|" / newlines ----
# (#623 review, Finding 2 -- previously untested)


def test_escape_md_escapes_pipes_and_newlines():
    assert mwa._escape_md("bike rack | station") == "bike rack \\| station"
    assert mwa._escape_md("line one\nline two") == "line one line two"
    assert mwa._escape_md("a | b\nc | d") == "a \\| b c \\| d"


def test_render_markdown_escapes_pipes_and_newlines_in_a_row():
    # A hand-built row (not the fixture) whose key/representative/reason all
    # carry a literal "|" and a newline -- free-form agent/player text that
    # would otherwise break the Markdown table's column count.
    row = mwa.ActionDemand(
        key="fix the | broken\nsign",
        representative="fix the | broken\nsign please",
        count=1,
        distinct_agents=1,
        trigger_mix={"proposed": 1},
        example_reasons=["it's confusing | unsafe\nat night"],
        first_turn=1,
        last_turn=1,
    )
    report = mwa.Report(rows=[row], total_wishes=1, trigger_totals={"proposed": 1})
    md = mwa.render_markdown(report)
    lines = md.splitlines()
    header = next(l for l in lines if l.startswith("| Rank |"))
    data_line = next(l for l in lines if l.startswith("| 1 |"))
    # Escaped content renders inline, not as extra columns or broken rows:
    # once the escaped "\|" occurrences (2 chars each: backslash + pipe) are
    # removed, only the real column-separator "|"s should remain -- and
    # there must be exactly as many of those as in the header.
    unescaped_pipes = data_line.replace("\\|", "").count("|")
    assert unescaped_pipes == header.count("|")
    assert "fix the \\| broken sign" in data_line
    assert "it's confusing \\| unsafe at night" in data_line


# --- CLI: writes both output files -----------------------------------------


def test_main_writes_out_md_and_out_json(tmp_path, capsys):
    out_md = tmp_path / "report.md"
    out_json = tmp_path / "report.json"
    rc = mwa.main([str(FIXTURE), "--out-md", str(out_md), "--out-json", str(out_json)])
    assert rc == 0
    assert out_md.read_text() == EXPECTED_MARKDOWN
    assert json.loads(out_json.read_text()) == EXPECTED_JSON


def test_main_prints_markdown_to_stdout_by_default(capsys):
    rc = mwa.main([str(FIXTURE)])
    assert rc == 0
    assert capsys.readouterr().out == EXPECTED_MARKDOWN


def test_main_prints_json_to_stdout_with_format_flag(capsys):
    rc = mwa.main([str(FIXTURE), "--format", "json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == EXPECTED_JSON
