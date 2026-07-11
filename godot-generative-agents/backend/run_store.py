"""Durable storage for sim runs (issue #304): the SQLite + JSONL RunStore.

A run today is ephemeral -- the bake dumps ``penn_replay.json`` at the end and
a live day vanishes with the process. This store gives both producers one
durable, zero-infrastructure home (SQLite is stdlib; frames are plain JSONL):

    <root>/
      sim.db                    # runs + memories tables
      <run_id>/
        manifest.json           # mirrors the runs row's manifest column
        frames.jsonl            # line N = the step-N frame (dict[str, AgentFrame])

Producers: ``serve_penn --persist`` (live, per tick) and
``generate_penn_replay --persist`` (bake, post-hoc). Consumers: the #307
live->replay exporter and the #306 run-lifecycle endpoints. Every shape is
pinned by the #305 contract (``backend.contract``); frame writes are checked
structurally here, because the base env has no pydantic -- the pydantic
conformance stays in the tests.

Every operation opens a short-lived sqlite connection: safe from whatever
thread the live loop calls it on, and nothing to share or close.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# godot-generative-agents/runs/ -- the default home for run artifacts
# (git-ignored), resolved relative to this package, never the CWD.
DEFAULT_RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id       TEXT PRIMARY KEY,
  manifest TEXT NOT NULL,
  status   TEXT NOT NULL,
  model    TEXT,
  created  TEXT NOT NULL,
  cost     REAL NOT NULL DEFAULT 0.0,
  steps    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS memories (
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


class RunStore:
    """Run metadata + frames + queryable agent memory under one directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self._db() as con:
            con.executescript(_SCHEMA)

    @contextmanager
    def _db(self):
        # One transaction per operation on a fresh connection: committed on a
        # clean exit, rolled back on an exception, always closed.
        con = sqlite3.connect(self.root / "sim.db")
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    # --- runs ---------------------------------------------------------------

    def create_run(self, manifest: dict, run_id: str | None = None) -> str:
        """Register a run and its directory; returns the id.

        ``manifest`` is the meta()-shaped blob (#305); ``model`` is lifted
        from its ``llm`` entry (None under the mock brain). A caller-supplied
        ``run_id`` (tests, tooling) must be unused.
        """
        if run_id is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            run_id = f"run-{stamp}-{secrets.token_hex(3)}"
        llm = manifest.get("llm")
        model = llm.get("model") if isinstance(llm, dict) else None
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self._db() as con:
                con.execute(
                    "INSERT INTO runs (id, manifest, status, model, created)"
                    " VALUES (?, ?, 'running', ?, ?)",
                    (run_id, json.dumps(manifest, ensure_ascii=False), model, created),
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"run id already exists: {run_id}")
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
        (run_dir / "frames.jsonl").touch()
        return run_id

    def get_run(self, run_id: str) -> dict | None:
        with self._db() as con:
            row = con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return None if row is None else self._run_row(row)

    def list_runs(self) -> list[dict]:
        """All runs, newest first (id breaks same-second ties)."""
        with self._db() as con:
            rows = con.execute(
                "SELECT * FROM runs ORDER BY created DESC, id DESC"
            ).fetchall()
        return [self._run_row(r) for r in rows]

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        cost: float | None = None,
        steps: int | None = None,
    ) -> None:
        """Partial update of the mutable columns; unknown id raises KeyError."""
        sets, vals = [], []
        if status is not None:
            sets.append("status = ?")
            vals.append(status)
        if cost is not None:
            sets.append("cost = ?")
            vals.append(float(cost))
        if steps is not None:
            sets.append("steps = ?")
            vals.append(int(steps))
        if not sets:
            return
        with self._db() as con:
            cur = con.execute(
                "UPDATE runs SET %s WHERE id = ?" % ", ".join(sets), (*vals, run_id)
            )
            if cur.rowcount == 0:
                raise KeyError(f"unknown run id: {run_id}")

    @staticmethod
    def _run_row(row: sqlite3.Row) -> dict:
        run = dict(row)
        run["manifest"] = json.loads(run["manifest"])
        return run
