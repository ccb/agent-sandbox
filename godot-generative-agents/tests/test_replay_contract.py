"""The pinned replay data-contract (#305).

Three families of guarantee:
* the Pydantic models match the pinned field orders (byte-identity, #297);
* the real emitters (the bake, the live meta) produce dicts that validate,
  with ``extra="forbid"`` catching any unpinned field (Task 2);
* ``replay.ts`` mirrors the models field-for-field (Task 3).

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_replay_contract.py -v
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_REPO = Path(__file__).resolve().parents[2]
_SIM_DIR = _REPO / "godot-generative-agents" / "backend" / "penn"
sys.path.insert(0, str(_SIM_DIR))

from backend.contract import (  # noqa: E402
    AGENT_FRAME_FIELDS,
    EVENT_STATE_FIELDS,
    MEMORY_RECORD_FIELDS,
    SCHEMA_VERSION,
    WISH_FIELDS,
)
from backend.contract_models import (  # noqa: E402
    AgentFrame,
    EventState,
    LlmInfo,
    MemoryRecord,
    Meta,
    PersonaMeta,
    RelationshipEdge,
    Replay,
    ScheduleStop,
    WishState,
)
from text_adventure_games.events import GameEvent  # noqa: E402
from text_adventure_games.wishes import ActionWish  # noqa: E402
from penn_world import build_penn_world, replay_frame_entry  # noqa: E402
from serve_penn import PennStepper  # noqa: E402

# A minimal raw frame in the shape simulate()/step() hand to replay_frame_entry.
_SAMPLE_RAW = {
    "movement": [3, 4],
    "description": "reading @ UPenn:Van Pelt Library:Entrance",
    "pronunciatio": "📖",
    "reasoning": None,
    "chat": None,
    "memories": [
        {
            "kind": "observation",
            "importance": 3.0,
            "text": "saw Sofia",
            "created_turn": 2,
        }
    ],
    "trace": [
        {"kind": "recall", "arg": "'coffee'", "hits": 3},
        {"kind": "action", "tool": "read", "ok": True},
    ],
}


def test_contract_constants_are_stdlib_only():
    # The bake imports backend.contract in the BASE env (no extras), where
    # pydantic does not exist. Guard the import boundary at the source level.
    src = (_REPO / "godot-generative-agents" / "backend" / "contract.py").read_text()
    assert "pydantic" not in src, "backend/contract.py must stay stdlib-only"


def test_agent_frame_field_order_pinned():
    # Three-way lock: the constant, the model, and the real emitter all agree.
    # Order is load-bearing -- the bake's json.dump serializes insertion order
    # and #297's acceptance is a byte-identical replay file.
    assert tuple(AgentFrame.model_fields) == AGENT_FRAME_FIELDS
    assert tuple(replay_frame_entry(_SAMPLE_RAW).keys()) == AGENT_FRAME_FIELDS


def test_memory_record_field_order_matches_emitter():
    # memories_for_frame emits kind, importance, text, created_turn -- the model
    # mirrors the emitter so a future model_dump() stays byte-faithful.
    assert tuple(MemoryRecord.model_fields) == MEMORY_RECORD_FIELDS


def test_emitted_frame_validates():
    AgentFrame.model_validate(replay_frame_entry(_SAMPLE_RAW))


def test_unpinned_frame_field_is_rejected():
    bad = dict(replay_frame_entry(_SAMPLE_RAW), mood="pensive")
    with pytest.raises(ValidationError):
        AgentFrame.model_validate(bad)


def test_trace_is_emitted_and_digest_only():
    frame = replay_frame_entry(_SAMPLE_RAW)
    assert frame["trace"] == [
        {"kind": "recall", "arg": "'coffee'", "hits": 3},
        {"kind": "action", "tool": "read", "ok": True},
    ]
    # Absent trace -> empty list, never missing (order-pin stays intact).
    bare = {k: v for k, v in _SAMPLE_RAW.items() if k != "trace"}
    assert replay_frame_entry(bare)["trace"] == []
    # Digest-only: an action entry carries no raw args payload.
    for entry in frame["trace"]:
        assert set(entry) <= {"kind", "arg", "hits", "tool", "ok"}


def test_meta_defaults_cover_both_surfaces():
    # One Meta covers the bake (steps known, llm absent) and the live handshake
    # (steps unknown, llm present-or-None): both optionals default cleanly.
    meta = Meta.model_validate(
        {
            "schema_version": SCHEMA_VERSION,
            "tile_px": 16,
            "width": 245,
            "height": 279,
            "sec_per_step": 10,
            "start": "2023-02-13 08:00:00",
            "vision_r": 8,
            "personas": [
                {
                    "name": "Diego Torres",
                    "emoji": "🎨",
                    "persona": "a painter",
                    "home": "UPenn:Fisher-Hassenfeld",
                    "schedule": [
                        {
                            "place": "UPenn:Van Pelt Library",
                            "activity": "study",
                            "emoji": "📚",
                            "steps": None,
                        }
                    ],
                }
            ],
            "relationships": [
                {
                    "a": "Diego Torres",
                    "b": "Professor Tanaka",
                    "kind": "mentor",
                    "closeness": 4,
                    "description": "advisor",
                }
            ],
        }
    )
    assert meta.steps is None and meta.llm is None


def test_replay_shape_validates():
    frame = replay_frame_entry(_SAMPLE_RAW)
    Replay.model_validate(
        {
            "meta": {
                "schema_version": SCHEMA_VERSION,
                "tile_px": 16,
                "width": 245,
                "height": 279,
                "sec_per_step": 10,
                "start": "2023-02-13 08:00:00",
                "vision_r": 8,
                "personas": [],
                "relationships": [],
                "steps": 1,
            },
            "frames": [{"Diego Torres": frame}],
            "memory_streams": {"Diego Torres": _SAMPLE_RAW["memories"]},
        }
    )


def _bake_small_replay(tmp_path):
    """Run the real bake (3 mock steps) and return the path to the replay file
    it writes -- shared by tests that need a real baked replay, not a copy of
    its dict."""
    out = tmp_path / "penn_replay.json"
    subprocess.run(
        [
            sys.executable,
            str(_SIM_DIR / "generate_penn_replay.py"),
            "--steps",
            "3",
            "--out",
            str(out),
        ],
        check=True,
    )
    return out


def test_baked_replay_validates_against_contract(tmp_path):
    # Run the REAL bake (3 mock steps) and validate the file it writes -- the
    # emitter itself is under test, not a copy of its dict.
    out = _bake_small_replay(tmp_path)
    replay = Replay.model_validate(json.loads(out.read_text()))
    assert replay.meta.schema_version == SCHEMA_VERSION
    assert replay.meta.steps == len(replay.frames)
    assert replay.meta.llm is None  # the bake runs the mock brain
    # First key of meta on the wire is the version marker.
    assert next(iter(json.loads(out.read_text())["meta"])) == "schema_version"


def test_baked_replay_frames_carry_trace(tmp_path):
    # Reuse the same bake helper as test_baked_replay_validates_against_contract.
    out = _bake_small_replay(tmp_path)
    replay = json.loads(out.read_text())
    for frame in replay["frames"]:
        for persona in frame.values():
            assert isinstance(persona["trace"], list)


def _bake_scenario_bytes(tmp_path, scenario, hashseed):
    """Run the REAL bake for one scenario under a fixed PYTHONHASHSEED and return
    the bytes of the replay file it writes. Two bakes of the same scenario at
    *different* hashseeds must be byte-identical (#640): a stray set/frozenset
    ordering leak into the artifact (the #545 regression class) would differ
    between them (dicts serialize insertion-ordered, so they're seed-immune),
    and any random/time/uuid on the bake path would differ between any two runs."""
    out = tmp_path / f"{scenario}_{hashseed}.json"
    subprocess.run(
        [
            sys.executable,
            str(_SIM_DIR / "generate_penn_replay.py"),
            "--scenario",
            scenario,
            "--steps",
            "3",
            "--out",
            str(out),
        ],
        check=True,
        env={**os.environ, "PYTHONHASHSEED": str(hashseed)},
    )
    return out.read_bytes()


@pytest.mark.parametrize("scenario", ["penn", "boil"])
def test_bake_is_byte_identical(tmp_path, scenario):
    # #640: the mock bake must be deterministic. Bake the same scenario twice
    # (default --brain mock) under different PYTHONHASHSEEDs and byte-compare --
    # catches nondeterminism (random/time/uuid) or a set/frozenset ordering leak
    # (iterated into the artifact) directly, with no committed golden to maintain.
    first = _bake_scenario_bytes(tmp_path, scenario, 0)
    second = _bake_scenario_bytes(tmp_path, scenario, 1)
    assert (
        first == second
    ), f"{scenario} bake is not byte-identical across PYTHONHASHSEED 0 vs 1"


def test_live_meta_validates_against_contract():
    meta = PennStepper(num_steps=2, world=build_penn_world()).meta()
    # Raw-dict check: the model's schema_version default would mask a dropped
    # key, so pin presence AND first position on the emitted dict itself.
    assert next(iter(meta)) == "schema_version"
    validated = Meta.model_validate(meta)
    assert validated.schema_version == SCHEMA_VERSION
    assert validated.steps is None  # a live run doesn't know its length
    assert validated.llm is None  # default stepper runs the mock brain


_REPLAY_TS = _REPO / "godot-generative-agents" / "web" / "src" / "types" / "replay.ts"

# TS interface name -> its Pydantic twin. Field-name sets must match exactly
# (optionality/types may differ -- TS marks historically-absent fields with ?).
_TS_PAIRS = {
    "ReplayMeta": Meta,
    "Persona": PersonaMeta,
    "ScheduleStop": ScheduleStop,
    "RelationshipEdge": RelationshipEdge,
    "LlmInfo": LlmInfo,
    "AgentFrame": AgentFrame,
    "MemoryRecord": MemoryRecord,
    "EventState": EventState,
    "WishState": WishState,
    "Replay": Replay,
}


def test_event_state_field_order_matches_emitter():
    # Three-way lock like the frame/memory rows: the constant, the model, and
    # the real emitter (GameEvent.to_primitive) all agree — so the #467 run
    # record ("events" in the replay, kind:"game_event" rows on the live feed)
    # validates against the contract the moment its emitter lands.
    assert tuple(EventState.model_fields) == EVENT_STATE_FIELDS
    sample = GameEvent(3, "Diego Torres", "drink", "felt ill", {"cause": "raw water"})
    assert tuple(sample.to_primitive().keys()) == EVENT_STATE_FIELDS
    EventState.model_validate(sample.to_primitive())


def test_wish_state_field_order_matches_emitter():
    # Same three-way lock, for the #622 demand-signal record: the constant,
    # the model, and the real emitter (ActionWish.to_primitive) all agree —
    # so "wishes" in the replay and kind:"wish" live-feed rows validate the
    # moment their emitter lands.
    assert tuple(WishState.model_fields) == WISH_FIELDS
    sample = ActionWish(
        actor="Diego Torres",
        turn=3,
        location="UPenn:Van Pelt Library",
        desired="a bike rack near the library",
        reason="mine keeps getting stolen",
    )
    assert tuple(sample.to_primitive().keys()) == WISH_FIELDS
    WishState.model_validate(sample.to_primitive())


def test_wish_state_contract_accepts_a_null_actor():
    # Parse-gap wishes (#621) may carry no actor, exactly like world-level
    # GameEvents (#631) -- the contract must accept it.
    sample = ActionWish(actor=None, turn=1, location=None, desired="ring the bell")
    WishState.model_validate(sample.to_primitive())


def _ts_interface_fields() -> dict[str, set[str]]:
    src = _REPLAY_TS.read_text()
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)  # block comments
    src = re.sub(r"//[^\n]*", "", src)  # line comments
    fields = {}
    for name, body in re.findall(r"export interface (\w+)\s*\{(.*?)\n\}", src, re.S):
        fields[name] = set(re.findall(r"^\s*(\w+)\??:", body, re.M))
    return fields


def test_replay_ts_mirrors_contract_models():
    # replay.ts is a MIRROR of the pinned contract, not the definition. This
    # keeps the two in lock-step without a TS toolchain in CI.
    interfaces = _ts_interface_fields()
    for ts_name, model in _TS_PAIRS.items():
        assert ts_name in interfaces, f"replay.ts is missing interface {ts_name}"
        assert interfaces[ts_name] == set(model.model_fields), (
            f"replay.ts {ts_name} drifted from {model.__name__}: "
            f"ts-only={interfaces[ts_name] - set(model.model_fields)}, "
            f"py-only={set(model.model_fields) - interfaces[ts_name]}"
        )
