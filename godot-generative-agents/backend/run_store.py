"""Durable storage for sim runs (issue #304): the SQLite + JSONL RunStore.

A run today is ephemeral -- the bake dumps ``penn_replay.json`` at the end and
a live day vanishes with the process. This store gives both producers one
durable, zero-infrastructure home (SQLite is stdlib; frames are plain JSONL):

    <root>/
      sim.db                    # runs + memories tables
      <run_id>/
        manifest.json           # mirrors the runs row's manifest column
        frames.jsonl            # line N = the step-N frame (dict[str, AgentFrame])
        events.jsonl            # the run's GameEvent log (EventState dicts, #467)

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
import shutil
import sqlite3
import struct
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backend.cognition import memories_for_frame
from backend.contract import AGENT_FRAME_FIELDS, EVENT_STATE_FIELDS
from backend.sim_config import RetrievalConfig
from text_adventure_games.memory import AgentMemory, MemoryRecord

# godot-generative-agents/runs/ -- the default home for run artifacts
# (git-ignored), resolved relative to this package, never the CWD.
DEFAULT_RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"

# Per-agent frame entries must carry these; the rest of the pinned
# AGENT_FRAME_FIELDS tuple (reasoning/chat/memories) is optional (#305).
_FRAME_REQUIRED = ("x", "y", "act", "e")

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

    def delete_run(self, run_id: str) -> None:
        """Remove a run everywhere: its row, its memories, its directory.

        The row is the source of truth, so it and the memories go first in
        one transaction; the directory sweep ignores errors -- a half-removed
        dir can be re-swept, but a lingering row would resurrect the run in
        every listing. Unknown id raises KeyError (the update_run precedent).
        Refusing to delete the CURRENT live run is the API layer's job (409)
        -- the store itself has no notion of "live".
        """
        with self._db() as con:
            cur = con.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            if cur.rowcount == 0:
                raise KeyError(f"unknown run id: {run_id}")
            con.execute("DELETE FROM memories WHERE run_id = ?", (run_id,))
        shutil.rmtree(self.root / run_id, ignore_errors=True)

    # --- frames ---------------------------------------------------------------

    def append_frame(self, run_id: str, step: int, frame: dict) -> None:
        """Append the step-N frame as line N of the run's frames.jsonl.

        ``step`` must equal the current line count -- no gaps, no rewrites --
        so #307 can read ``frames[]`` straight off the file. The frame is
        checked against the pinned #305 fields before anything is written.
        """
        path = self._frames_path(run_id)
        _validate_frame(frame)
        with path.open("r", encoding="utf-8") as fh:
            count = sum(1 for _ in fh)
        if step != count:
            raise ValueError(
                f"{run_id} has {count} frames; expected step {count}, got {step}"
            )
        # One write of the whole line (json + newline): a crash can leave the
        # line absent or torn, never a body without its terminator to confuse
        # the next append's line count.
        with path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(frame, ensure_ascii=False, separators=(",", ":")) + "\n"
            )

    def read_frames(self, run_id: str) -> list[dict]:
        """Every persisted frame, in step order."""
        return self._read_jsonl(self._frames_path(run_id))

    def _frames_path(self, run_id: str) -> Path:
        path = self.root / run_id / "frames.jsonl"
        if not path.exists():
            raise KeyError(f"unknown run id: {run_id}")
        return path

    # --- events ---------------------------------------------------------------

    def append_events(
        self, run_id: str, events: list[dict], *, skip_bad: bool = False
    ) -> list[tuple[dict, str]]:
        """Append ``GameEvent.to_primitive()`` dicts to the run's events.jsonl.

        Unlike frames there is no step == line invariant: a step can log zero
        or many events and each carries its own ``turn`` -- order is append
        order. An empty list is a no-op: a run with no events never grows a
        file.

        The whole batch is serialized in memory first, then written in a
        single ``fh.write`` -- advance-or-nothing. So a record that fails
        validation (#305 EventState, keys only) OR JSON encoding partway
        through the batch can never leave a torn prefix on disk to be
        re-flushed as duplicate lines on the next attempt (#637).

        ``skip_bad=True`` (the live per-tick path) drops each such record and
        returns them as ``(event, reason)`` pairs -- so one malformed record,
        e.g. an evolving-schema field the allowlist rejects, never halts the
        run. The default stays strict: the first bad record raises, exactly as
        before. Returns the dropped records ([] in strict mode).
        """
        path = self._events_path(run_id)
        lines: list[str] = []
        bad: list[tuple[dict, str]] = []
        for event in events:
            try:
                _validate_event(event)
                lines.append(
                    json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                )
            except (ValueError, TypeError) as exc:
                if not skip_bad:
                    raise
                bad.append((event, str(exc)))
        if lines:
            with path.open("a", encoding="utf-8") as fh:
                fh.write("".join(line + "\n" for line in lines))
        return bad

    def read_events(self, run_id: str) -> list[dict]:
        """The run's persisted GameEvent log, in append order ([] when none)."""
        path = self._events_path(run_id)
        if not path.exists():
            return []
        return self._read_jsonl(path)

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        """Parse a JSONL artifact, tolerating a single torn final line left by
        a crash mid-append -- an unterminated body with no trailing newline
        (#637). It is skipped with a warning instead of raising on every
        subsequent read/export. A terminated-but-invalid *interior* line is
        real corruption, not a torn tail, and still raises.
        """
        with path.open("r", encoding="utf-8") as fh:
            raw = fh.readlines()
        out: list[dict] = []
        last = len(raw) - 1
        for i, line in enumerate(raw):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                if i == last and not line.endswith("\n"):
                    warnings.warn(
                        f"{path.name}: ignoring a torn final line "
                        f"({len(line)} chars, no newline) -- crash mid-append?",
                        stacklevel=2,
                    )
                    continue
                raise
        return out

    def _events_path(self, run_id: str) -> Path:
        # Existence-check the run DIR, not the file: unlike frames.jsonl
        # (touch()-ed by create_run), events.jsonl is created lazily on the
        # first append -- an event-less run never has one.
        run_dir = self.root / run_id
        if not run_dir.is_dir():
            raise KeyError(f"unknown run id: {run_id}")
        return run_dir / "events.jsonl"

    # --- memories ---------------------------------------------------------------

    def record_memories(self, run_id: str, agent: str, records: list[dict]) -> None:
        """Persist engine ``MemoryRecord.to_primitive()`` dicts for *agent*.

        Idempotent per record id (INSERT OR IGNORE), so a retried tick or an
        overlapping sync writes each row exactly once. Scoring/projection
        fields become columns; the rest of the record rides ``extra`` so it
        rehydrates losslessly; an embedding (when present) packs to
        little-endian float32s.
        """
        rows = []
        for rec in records:
            emb = rec.get("embedding")
            packed = struct.pack("<%df" % len(emb), *emb) if emb else None
            extra = {
                k: v
                for k, v in rec.items()
                if k
                not in ("id", "kind", "importance", "created_turn", "text", "embedding")
            }
            rows.append(
                (
                    run_id,
                    agent,
                    int(rec["id"]),
                    str(rec["kind"]),
                    float(rec["importance"]),
                    int(rec["created_turn"]),
                    rec["text"],
                    packed,
                    json.dumps(extra, ensure_ascii=False),
                )
            )
        with self._db() as con:
            con.executemany(
                "INSERT OR IGNORE INTO memories"
                " (run_id, agent, record_id, kind, importance, created_turn,"
                "  text, embedding, extra) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    def last_memory_id(self, run_id: str, agent: str) -> int:
        """Highest persisted engine record id for *agent*, or -1 when none --
        the incremental-sync cursor."""
        with self._db() as con:
            row = con.execute(
                "SELECT MAX(record_id) AS m FROM memories"
                " WHERE run_id = ? AND agent = ?",
                (run_id, agent),
            ).fetchone()
        return -1 if row["m"] is None else int(row["m"])

    def memories_for(
        self,
        run_id: str,
        agent: str,
        *,
        kind: str | None = None,
        since_turn: int | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """The lean wire projection (#305 MemoryRecord fields), record order.

        What the #307 exporter writes as ``memory_streams`` and the future
        #306 endpoints serve; matches ``cognition.memory_stream_for_persona``
        exactly (importance rounded to one decimal).
        """
        sql = (
            "SELECT kind, importance, text, created_turn FROM memories"
            " WHERE run_id = ? AND agent = ?"
        )
        vals: list = [run_id, agent]
        if kind is not None:
            sql += " AND kind = ?"
            vals.append(kind)
        if since_turn is not None:
            sql += " AND created_turn >= ?"
            vals.append(int(since_turn))
        sql += " ORDER BY record_id"
        if limit is not None:
            sql += " LIMIT ?"
            vals.append(int(limit))
        with self._db() as con:
            rows = con.execute(sql, vals).fetchall()
        return [
            {
                "kind": r["kind"],
                "importance": round(float(r["importance"]), 1),
                "text": r["text"],
                "created_turn": int(r["created_turn"]),
            }
            for r in rows
        ]

    def query_memories(
        self,
        run_id: str,
        agent: str,
        query: str,
        turn: int,
        *,
        retrieval: RetrievalConfig | None = None,
        embedding_client=None,
    ) -> list[dict]:
        """Top-k memories for *query* at *turn*, scored exactly like the sim.

        Rehydrates the stored rows into engine ``MemoryRecord``s and delegates
        to ``AgentMemory.retrieve`` -- the recency x importance x relevance
        scoring stays defined in one place. ``touch=False``: a store query is
        read-only and never bumps recency. Keyword relevance by default; pass
        an ``embedding_client`` for semantic scoring over stored embeddings.
        Returns lean projections of the winners.
        """
        rc = retrieval if retrieval is not None else RetrievalConfig()
        memory = AgentMemory(owner=agent, embedding_client=embedding_client)
        memory.records = self.hydrated_records(run_id, agent)
        top = memory.retrieve(
            query,
            turn,
            max_records=rc.max_records,
            token_budget=rc.token_budget,
            decay=rc.recency_decay,
            alpha_recency=rc.alpha_recency,
            alpha_importance=rc.alpha_importance,
            alpha_relevance=rc.alpha_relevance,
            touch=False,
        )
        return memories_for_frame(top)

    def hydrated_records(self, run_id: str, agent: str) -> list[MemoryRecord]:
        """``full_records`` rehydrated into live engine ``MemoryRecord``s,
        still ordered by record id -- the one home for ``from_primitive``
        knowledge, shared by ``query_memories``'s scoring and a resumed
        run's memory restore (#543)."""
        return [
            MemoryRecord.from_primitive(rec) for rec in self.full_records(run_id, agent)
        ]

    def full_records(self, run_id: str, agent: str) -> list[dict]:
        """The lossless ``to_primitive()`` dicts back out of columns + extra +
        blob, ordered by record id -- what ``query_memories`` scores over, and
        what a resumed run rehydrates its agents' memory from (#543)."""
        with self._db() as con:
            rows = con.execute(
                "SELECT * FROM memories WHERE run_id = ? AND agent = ?"
                " ORDER BY record_id",
                (run_id, agent),
            ).fetchall()
        records = []
        for row in rows:
            rec = json.loads(row["extra"])
            emb = row["embedding"]
            rec.update(
                {
                    "id": int(row["record_id"]),
                    "kind": row["kind"],
                    "importance": float(row["importance"]),
                    "created_turn": int(row["created_turn"]),
                    "text": row["text"],
                    "embedding": (
                        list(struct.unpack("<%df" % (len(emb) // 4), emb))
                        if emb is not None
                        else None
                    ),
                }
            )
            records.append(rec)
        return records


def _validate_frame(frame: dict) -> None:
    """Structural #305 check: a dict of per-agent entries, pinned fields only.

    The pydantic conformance lives in the tests (contract_models needs
    pydantic, which the base env deliberately lacks); this catches the shape
    mistakes a producer could actually make -- a wrong container, an unpinned
    field, a missing required one -- before they hit disk.
    """
    if not isinstance(frame, dict) or not frame:
        raise ValueError("frame must be a non-empty dict of per-agent entries")
    allowed = set(AGENT_FRAME_FIELDS)
    for name, entry in frame.items():
        if not isinstance(entry, dict):
            raise ValueError(f"frame entry for {name!r} is not a dict")
        unpinned = sorted(set(entry) - allowed)
        if unpinned:
            raise ValueError(
                f"frame entry for {name!r} has unpinned fields: {unpinned}"
            )
        missing = [k for k in _FRAME_REQUIRED if k not in entry]
        if missing:
            raise ValueError(f"frame entry for {name!r} is missing {missing}")


def _validate_event(event: dict) -> None:
    """Structural #305 EventState check: the five pinned fields, keys only.

    Same rationale as ``_validate_frame`` -- and keys only on purpose:
    ``POST /world/event`` records legitimately carry ``actor=None``.
    """
    if not isinstance(event, dict):
        raise ValueError("event must be a dict of EventState fields")
    unpinned = sorted(set(event) - set(EVENT_STATE_FIELDS))
    if unpinned:
        raise ValueError(f"event has unpinned fields: {unpinned}")
    missing = [k for k in EVENT_STATE_FIELDS if k not in event]
    if missing:
        raise ValueError(f"event is missing {missing}")
