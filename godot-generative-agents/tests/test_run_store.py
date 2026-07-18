"""RunStore unit tests (issue #304). Fully offline; every store lives in tmp_path."""

import json
import re

import pytest

from backend.run_store import RunStore
from backend.sim_config import RetrievalConfig
from text_adventure_games.memory import AgentMemory, MemoryKind, MemoryRecord

MANIFEST = {
    "schema_version": 1,
    "personas": [{"name": "Ada"}],
    "llm": {"provider": "anthropic", "model": "claude-haiku-4-5"},
}


def test_create_get_list_roundtrip(tmp_path):
    store = RunStore(tmp_path / "runs")
    a = store.create_run(MANIFEST, run_id="run-a")
    b = store.create_run(dict(MANIFEST, llm=None), run_id="run-b")
    assert (a, b) == ("run-a", "run-b")
    run = store.get_run("run-a")
    assert run["manifest"] == MANIFEST
    assert run["status"] == "running"
    assert run["model"] == "claude-haiku-4-5"
    assert run["cost"] == 0.0 and run["steps"] == 0
    assert store.get_run("run-b")["model"] is None  # mock brain -> no model
    assert store.get_run("missing") is None
    # Newest first; same-second creations fall back to the id tiebreak.
    assert [r["id"] for r in store.list_runs()] == ["run-b", "run-a"]
    # The on-disk mirrors exist: manifest.json + an empty frames.jsonl.
    assert (tmp_path / "runs" / "run-a" / "frames.jsonl").read_text() == ""
    on_disk = json.loads((tmp_path / "runs" / "run-a" / "manifest.json").read_text())
    assert on_disk == MANIFEST


def test_create_run_rejects_duplicate_id(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    with pytest.raises(ValueError):
        store.create_run(MANIFEST, run_id="run-a")


def test_default_run_id_shape(tmp_path):
    store = RunStore(tmp_path / "runs")
    run_id = store.create_run(MANIFEST)
    assert re.fullmatch(r"run-\d{8}-\d{6}-[0-9a-f]{6}", run_id)


def test_update_run_partial_and_unknown(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    store.update_run("run-a", status="finished")
    store.update_run("run-a", cost=0.25, steps=40)
    run = store.get_run("run-a")
    assert (run["status"], run["cost"], run["steps"]) == ("finished", 0.25, 40)
    with pytest.raises(KeyError):
        store.update_run("missing", status="reset")


FRAME = {
    "Ada": {
        "x": 1,
        "y": 2,
        "act": "reading @ UPenn:Van Pelt Library:stacks",
        "e": "📖",
        "chat": None,
    }
}


def test_append_and_read_frames_in_order(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    frames = [{"Ada": dict(FRAME["Ada"], x=i)} for i in range(3)]
    for i, frame in enumerate(frames):
        store.append_frame("run-a", i, frame)
    assert store.read_frames("run-a") == frames


def test_append_frame_rejects_gaps_and_unknown_runs(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    with pytest.raises(ValueError):
        store.append_frame("run-a", 1, FRAME)  # next line is step 0
    with pytest.raises(KeyError):
        store.append_frame("missing", 0, FRAME)


def test_append_frame_validates_the_contract_shape(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    with pytest.raises(ValueError):
        store.append_frame("run-a", 0, {"Ada": {"x": 1, "y": 2, "act": "?"}})  # no "e"
    with pytest.raises(ValueError):
        store.append_frame("run-a", 0, {"Ada": dict(FRAME["Ada"], speed=9)})  # unpinned
    with pytest.raises(ValueError):
        store.append_frame("run-a", 0, {"Ada": "not-a-dict"})
    with pytest.raises(ValueError):
        store.append_frame("run-a", 0, {})
    assert store.read_frames("run-a") == []  # nothing hit the disk


EVENT = {
    "turn": 0,
    "actor": "Ada",
    "action": "world_event",
    "summary": "a siren wails",
    "payload": {},
}


def test_append_and_read_events_in_order(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    # No events yet: no file on disk, and read_events is [] -- not an error.
    assert store.read_events("run-a") == []
    assert not (tmp_path / "runs" / "run-a" / "events.jsonl").exists()
    first = [dict(EVENT, turn=0), dict(EVENT, turn=1, actor=None)]  # None: /world/event
    second = [dict(EVENT, turn=2, summary="last call")]
    store.append_events("run-a", first)
    store.append_events("run-a", [])  # a no-op, not an error
    store.append_events("run-a", second)
    assert store.read_events("run-a") == first + second


def test_append_events_validates_and_rejects_unknown_runs(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    with pytest.raises(KeyError):
        store.append_events("missing", [EVENT])
    with pytest.raises(KeyError):
        store.read_events("missing")
    with pytest.raises(ValueError):
        store.append_events("run-a", [{"turn": 0, "actor": "Ada"}])  # missing fields
    with pytest.raises(ValueError):
        store.append_events("run-a", [dict(EVENT, mood="tense")])  # unpinned field
    # A bad event anywhere in the batch keeps the WHOLE batch off disk.
    with pytest.raises(ValueError):
        store.append_events("run-a", [EVENT, "not-a-dict"])
    assert store.read_events("run-a") == []


def test_append_events_skip_bad_drops_the_bad_and_keeps_the_good(tmp_path):
    """The live path (skip_bad=True) must never let one malformed record halt
    the run: bad records are dropped and reported, the good ones still land."""
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    good0 = dict(EVENT, turn=0)
    unpinned = dict(EVENT, turn=1, mood="tense")  # extra field -> validation
    unserializable = dict(EVENT, turn=2, payload={"o": object()})  # bad value
    good3 = dict(EVENT, turn=3, summary="still fine")
    bad = store.append_events(
        "run-a", [good0, unpinned, unserializable, good3], skip_bad=True
    )
    # Only the well-formed events reached disk, in order.
    assert store.read_events("run-a") == [good0, good3]
    # Both malformed records were reported back (with a reason) so the caller
    # can count and log them -- nothing was raised.
    assert [event for event, _reason in bad] == [unpinned, unserializable]


def test_append_events_writes_nothing_when_a_value_wont_serialize(tmp_path):
    """Key-only validation lets a non-JSON value slip through to json.dumps.
    Strict mode must still be advance-or-nothing: a serialize failure partway
    through the batch leaves NO torn prefix behind (the duplicate-on-retry
    mode, #637)."""
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    good = dict(EVENT, turn=0)
    unserializable = dict(EVENT, turn=1, payload={"o": object()})
    with pytest.raises(TypeError):
        store.append_events("run-a", [good, unserializable])
    assert store.read_events("run-a") == []  # the good prefix did NOT leak


def test_reads_tolerate_a_torn_final_line(tmp_path):
    """A crash mid-append can leave a partial last line (no trailing newline).
    read_events/read_frames must skip it and keep serving, not raise on every
    subsequent read/export (#637)."""
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    store.append_events("run-a", [dict(EVENT, turn=0), dict(EVENT, turn=1)])
    with (tmp_path / "runs" / "run-a" / "events.jsonl").open("a") as fh:
        fh.write('{"turn": 2, "actor": "Ada"')  # torn: unterminated, no newline
    assert store.read_events("run-a") == [dict(EVENT, turn=0), dict(EVENT, turn=1)]

    store.append_frame("run-a", 0, FRAME)
    with (tmp_path / "runs" / "run-a" / "frames.jsonl").open("a") as fh:
        fh.write('{"Ada": {"x": 1')  # torn final frame
    assert store.read_frames("run-a") == [FRAME]


def test_reads_still_raise_on_a_corrupt_interior_line(tmp_path):
    """Tolerance is only for the torn TAIL of a crash. A fully terminated but
    non-JSON line in the middle is real corruption and must not be swallowed."""
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    store.append_events("run-a", [dict(EVENT, turn=0)])
    with (tmp_path / "runs" / "run-a" / "events.jsonl").open("a") as fh:
        fh.write("not json at all\n")  # terminated -> an interior line now
    store.append_events("run-a", [dict(EVENT, turn=2)])
    with pytest.raises(json.JSONDecodeError):
        store.read_events("run-a")


def _record(i, text, *, turn=0, kind="observation", importance=3.0, embedding=None):
    return MemoryRecord(
        id=i,
        kind=MemoryKind(kind),
        text=text,
        created_turn=turn,
        last_accessed_turn=turn,
        importance=importance,
        embedding=embedding,
    ).to_primitive()


def test_record_memories_dedup_and_cursor(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    assert store.last_memory_id("run-a", "Ada") == -1
    store.record_memories(
        "run-a", "Ada", [_record(0, "saw a book"), _record(1, "read it")]
    )
    assert store.last_memory_id("run-a", "Ada") == 1
    # Re-sending persisted ids is a no-op (INSERT OR IGNORE).
    store.record_memories(
        "run-a", "Ada", [_record(1, "read it"), _record(2, "shelved it")]
    )
    assert store.last_memory_id("run-a", "Ada") == 2
    assert len(store.memories_for("run-a", "Ada")) == 3


def test_memories_for_projection_and_filters(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    store.record_memories(
        "run-a",
        "Ada",
        [
            _record(0, "waking up", turn=0, importance=3.14),
            _record(1, "planning the day", turn=2, kind="plan"),
            _record(2, "met Diego", turn=5),
        ],
    )
    lean = store.memories_for("run-a", "Ada")
    assert [set(m) for m in lean] == [
        {"kind", "importance", "text", "created_turn"}
    ] * 3
    assert lean[0]["importance"] == 3.1  # rounded like memory_stream_for_persona
    assert [m["text"] for m in store.memories_for("run-a", "Ada", kind="plan")] == [
        "planning the day"
    ]
    assert [m["text"] for m in store.memories_for("run-a", "Ada", since_turn=2)] == [
        "planning the day",
        "met Diego",
    ]
    assert len(store.memories_for("run-a", "Ada", limit=1)) == 1
    assert store.memories_for("run-a", "Diego") == []


def test_embedding_round_trips_losslessly(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    # Values exactly representable as float32, so unpack == input.
    store.record_memories("run-a", "Ada", [_record(0, "x", embedding=[0.5, -1.0, 2.0])])
    (rec,) = store.full_records("run-a", "Ada")
    assert rec["embedding"] == [0.5, -1.0, 2.0]
    assert MemoryRecord.from_primitive(rec).embedding == [0.5, -1.0, 2.0]
    # hydrated_records is exactly that rehydration, as a store read.
    (hydrated,) = store.hydrated_records("run-a", "Ada")
    assert hydrated.to_primitive() == rec


def test_query_memories_matches_engine_retrieve(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    records = [
        _record(0, "grabbed coffee at Houston Hall", turn=0, importance=2.0),
        _record(
            1,
            "planning to read library books all day",
            turn=1,
            kind="plan",
            importance=8.0,
        ),
        _record(2, "walked past College Hall", turn=3, importance=1.0),
        _record(3, "found rare library books in the stacks", turn=6, importance=6.0),
        _record(4, "chatted with Diego about lunch", turn=7, importance=4.0),
    ]
    store.record_memories("run-a", "Ada", records)
    rc = RetrievalConfig(max_records=3)
    engine = AgentMemory(owner="Ada")
    engine.records = [MemoryRecord.from_primitive(r) for r in records]
    expected = [
        r.text
        for r in engine.retrieve(
            "library books",
            10,
            max_records=rc.max_records,
            token_budget=rc.token_budget,
            decay=rc.recency_decay,
            alpha_recency=rc.alpha_recency,
            alpha_importance=rc.alpha_importance,
            alpha_relevance=rc.alpha_relevance,
            touch=False,
        )
    ]
    got = [
        m["text"]
        for m in store.query_memories("run-a", "Ada", "library books", 10, retrieval=rc)
    ]
    assert got == expected and len(got) == 3


def test_delete_run_removes_row_memories_and_dir(tmp_path):
    store = RunStore(tmp_path / "runs")
    store.create_run(MANIFEST, run_id="run-a")
    store.create_run(MANIFEST, run_id="run-b")
    store.append_frame("run-a", 0, FRAME)
    store.record_memories("run-a", "Ada", [_record(0, "saw a book")])
    store.record_memories("run-b", "Ada", [_record(0, "kept")])
    store.delete_run("run-a")
    assert store.get_run("run-a") is None
    assert not (tmp_path / "runs" / "run-a").exists()
    assert store.last_memory_id("run-a", "Ada") == -1  # memories rows gone
    # Nothing else was touched: run-b's row, dir, and memories survive.
    assert store.get_run("run-b") is not None
    assert (tmp_path / "runs" / "run-b" / "frames.jsonl").exists()
    assert store.last_memory_id("run-b", "Ada") == 0
    # Idempotence is NOT silent: a second delete (or an unknown id) raises.
    with pytest.raises(KeyError):
        store.delete_run("run-a")
