"""#859: analyze_run flags a run missing from sim.db instead of reporting 0.

The two memory counters (#779 relationship seeds, #778 commitments) are the only
numbers analyze_run.py reads from ``sim.db``; everything else comes from the run
directory. Those two sources have different lifetimes: ``sim.db`` is a
git-tracked binary, so a run made in another worktree -- or an artifact PR that
deliberately does not commit the store, like batch 8 (#893) -- leaves a run
directory on disk with no row in the store. Printing ``0 relationship memories
(NONE)`` for such a run reads as a finding about the simulation ("#779 never
fired in a 4320-step run") instead of a gap in the store, and nearly redirected
#826's criterion-1 design once already.

The guard: anything that prints a number should be able to prove it counted
something. When ``SELECT 1 FROM runs WHERE id = ?`` finds nothing, both counters
must say ``n/a (run not in sim.db)`` -- and a run that IS in the store keeps its
honest zero.
"""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

# The tool is deliberately stdlib-only and lives outside any package, so load it
# straight from its file the way an archived copy would be run.
_TOOL = Path(__file__).resolve().parents[1] / "tools" / "analyze_run.py"
_spec = importlib.util.spec_from_file_location("analyze_run", _TOOL)
analyze_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analyze_run)

# Mirrors backend.run_store._SCHEMA (not imported: the tool under test reads the
# database file directly, so the fixture writes the same shape directly).
_SCHEMA = """
CREATE TABLE runs (
  id       TEXT PRIMARY KEY,
  manifest TEXT NOT NULL,
  status   TEXT NOT NULL,
  model    TEXT,
  created  TEXT NOT NULL,
  cost     REAL NOT NULL DEFAULT 0.0,
  steps    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE memories (
  run_id       TEXT NOT NULL,
  agent        TEXT NOT NULL,
  record_id    INTEGER NOT NULL,
  kind         TEXT NOT NULL,
  importance   REAL NOT NULL,
  created_turn INTEGER NOT NULL,
  text         TEXT NOT NULL,
  embedding    BLOB,
  extra        TEXT NOT NULL,
  PRIMARY KEY (run_id, agent, record_id)
);
"""

RUN_ID = "run-20260728-211113-e68900"  # the batch-5 run that surfaced #859


@pytest.fixture
def runs_dir(tmp_path):
    """A run directory on disk whose id is absent from an otherwise-healthy store.

    The store is *not* empty: it holds a different run complete with memory rows,
    so the desync cannot be waved off as "no database yet" -- this is exactly the
    shape the issue reproduced against the real ``runs/sim.db``.
    """
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    (run_dir / "frames.jsonl").write_text(
        '{"Ada": {"act": "reading @ x", "loc": "Hall"}}\n'
        '{"Ada": {"act": "reading @ x", "loc": "Hall"}}\n',
        encoding="utf-8",
    )
    con = sqlite3.connect(tmp_path / "sim.db")
    con.executescript(_SCHEMA)
    con.execute(
        "INSERT INTO runs (id, manifest, status, created) VALUES (?, ?, ?, ?)",
        ("run-other", "{}", "finished", "2026-07-27T18:20:10+00:00"),
    )
    con.execute(
        "INSERT INTO memories (run_id, agent, record_id, kind, importance,"
        " created_turn, text, extra) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("run-other", "Ada", 1, "seed", 0.5, 0, "Ada knows Bo.", '["relationship"]'),
    )
    con.commit()
    con.close()
    return tmp_path


def test_run_absent_from_store_reports_na_not_zero(runs_dir):
    s = analyze_run.summarise(RUN_ID, runs_dir, usage=None)
    # The desync is data, not a footnote: summarise must say the store has no
    # such run, and must NOT fabricate zero counters for it.
    assert s["in_sim_db"] is False
    assert "relationship_memories_total" not in s
    assert "commitment_memories_total" not in s
    out = analyze_run.render(s)
    assert "#779 seeds  n/a (run not in sim.db)" in out
    assert "#778 commit n/a (run not in sim.db)" in out
    assert "0 relationship memories" not in out
    assert "0 commitment memories" not in out


def test_run_present_with_no_memories_keeps_its_honest_zero(runs_dir):
    # Same fixture, but now the run IS in the store (with zero memory rows):
    # a genuine "nothing fired" must still print as 0, not n/a.
    con = sqlite3.connect(runs_dir / "sim.db")
    con.execute(
        "INSERT INTO runs (id, manifest, status, created) VALUES (?, ?, ?, ?)",
        (RUN_ID, "{}", "finished", "2026-07-28T21:11:13+00:00"),
    )
    con.commit()
    con.close()
    s = analyze_run.summarise(RUN_ID, runs_dir, usage=None)
    assert s["in_sim_db"] is True
    assert s["relationship_memories_total"] == 0
    assert s["commitment_memories_total"] == 0
    out = analyze_run.render(s)
    assert "#779 seeds  0 relationship memories (NONE)" in out
    assert "#778 commit 0 commitment memories (none)" in out
    assert "n/a (run not in sim.db)" not in out


def test_memory_counters_still_count_for_a_run_in_the_store(runs_dir):
    # The guard must not disturb the counting path: the other run in the store
    # has one tagged relationship memory, and it still counts.
    run_dir = runs_dir / "run-other"
    run_dir.mkdir()
    (run_dir / "frames.jsonl").write_text(
        '{"Ada": {"act": "reading @ x", "loc": "Hall"}}\n', encoding="utf-8"
    )
    s = analyze_run.summarise("run-other", runs_dir, usage=None)
    assert s["in_sim_db"] is True
    assert s["relationship_memories_total"] == 1
    assert s["relationship_memories"] == {"Ada": 1}
    out = analyze_run.render(s)
    assert "#779 seeds  1 relationship memories" in out
