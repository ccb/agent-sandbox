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
    MEMORY_RECORD_FIELDS,
    SCHEMA_VERSION,
)
from backend.contract_models import (  # noqa: E402
    AgentFrame,
    MemoryRecord,
    Meta,
    Replay,
)
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


def test_baked_replay_validates_against_contract(tmp_path):
    # Run the REAL bake (3 mock steps) and validate the file it writes -- the
    # emitter itself is under test, not a copy of its dict.
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
    replay = Replay.model_validate(json.loads(out.read_text()))
    assert replay.meta.schema_version == SCHEMA_VERSION
    assert replay.meta.steps == len(replay.frames)
    assert replay.meta.llm is None  # the bake runs the mock brain
    # First key of meta on the wire is the version marker.
    assert next(iter(json.loads(out.read_text())["meta"])) == "schema_version"


def test_live_meta_validates_against_contract():
    meta = PennStepper(num_steps=2, world=build_penn_world()).meta()
    validated = Meta.model_validate(meta)
    assert validated.schema_version == SCHEMA_VERSION
    assert validated.steps is None  # a live run doesn't know its length
    assert validated.llm is None  # default stepper runs the mock brain
