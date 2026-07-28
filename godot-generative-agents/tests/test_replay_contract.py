"""The pinned replay data-contract (#305).

Four families of guarantee:
* the Pydantic models match the pinned field orders (byte-identity, #297);
* the real emitters (the bake, the live meta) produce dicts that validate,
  with ``extra="forbid"`` catching any unpinned field (Task 2);
* ``replay.ts`` mirrors the models field-for-field (Task 3);
* ``live.ts`` mirrors the live HTTP surface the same way (#644) -- the
  ``GET /usage`` payload, the monitor's ``llm_call`` row, and the api.py
  response models -- so the web companion can't silently drift off fields
  the backend serves (the way the run-scoped usage fields went missing).

Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_replay_contract.py -v
"""

import functools
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


def test_meta_locations_optional_for_older_replays():
    # Additive field: a replay baked before #780 has no "locations" and must
    # still validate (no SCHEMA_VERSION bump).
    meta = Meta.model_validate(
        {
            "schema_version": SCHEMA_VERSION,
            "tile_px": 16,
            "width": 245,
            "height": 279,
            "sec_per_step": 10,
            "start": "2023-02-13 08:00:00",
            "vision_r": 8,
            "personas": [],
            "relationships": [],
        }
    )
    assert meta.locations is None


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


def _run_bake(out, *, scenario="penn", steps=None, env=None):
    """Invoke the real generate_penn_replay.py bake, writing to ``out`` (returned).

    ``steps=None`` bakes the scenario's own default budget -- the real bundled
    artifact size; pass a small ``steps`` for shape tests that don't need a full
    run. ``env`` is forwarded to the subprocess (used to pin PYTHONHASHSEED)."""
    cmd = [
        sys.executable,
        str(_SIM_DIR / "generate_penn_replay.py"),
        "--scenario",
        scenario,
        "--out",
        str(out),
        # #752: the bake now persists by default; these contract/byte-identity
        # bakes want only the replay file, never a store row.
        "--no-persist",
    ]
    if steps is not None:
        cmd += ["--steps", str(steps)]
    subprocess.run(cmd, check=True, env=env)
    return out


def _bake_small_replay(tmp_path):
    """Run the real bake (3 mock steps) and return the path to the replay file
    it writes -- shared by shape tests that need a real baked replay, not a copy
    of its dict."""
    return _run_bake(tmp_path / "penn_replay.json", steps=3)


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


def test_baked_meta_carries_sorted_locations(tmp_path):
    out = _bake_small_replay(tmp_path)
    meta = json.loads(out.read_text())["meta"]
    assert meta["locations"] == sorted(meta["locations"])
    # The six buildings, the outdoor hub, and the named interiors (#780 found
    # the world is 18 locations, not the six the issue counted).
    assert "College Hall" in meta["locations"]
    assert "Penn campus" in meta["locations"]
    assert len(meta["locations"]) >= 18


def test_baked_replay_frames_carry_trace(tmp_path):
    # Reuse the same bake helper as test_baked_replay_validates_against_contract.
    out = _bake_small_replay(tmp_path)
    replay = json.loads(out.read_text())
    for frame in replay["frames"]:
        for persona in frame.values():
            assert isinstance(persona["trace"], list)


@pytest.mark.parametrize("scenario", ["penn", "boil"])
def test_bake_is_byte_identical(tmp_path, scenario):
    """#640: the mock bake of the bundled artifact must be deterministic.

    Bake each scenario at its own default step budget -- the real bundled
    artifact size, so a leak that only surfaces once the cast has walked and
    accumulated memories/events is in scope, not just the opening steps -- three
    times under different PYTHONHASHSEEDs and byte-compare. A set/frozenset
    ordering leak into the artifact (the #545 regression class) or any
    random/time/uuid on the bake path makes the bytes differ across seeds; dicts
    serialize insertion-ordered, so they're seed-immune. Three seeds (matching
    #715) keep even a two-element set leak from slipping past a lucky pair. No
    committed golden to maintain."""
    bakes = [
        _run_bake(
            tmp_path / f"{scenario}_{seed}.json",
            scenario=scenario,
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
        ).read_bytes()
        for seed in (0, 1, 2)
    ]
    assert (
        bakes[0] == bakes[1] == bakes[2]
    ), f"{scenario} bake is not byte-identical across PYTHONHASHSEED 0/1/2"


def test_live_meta_validates_against_contract():
    meta = PennStepper(num_steps=2, world=build_penn_world()).meta()
    # Raw-dict check: the model's schema_version default would mask a dropped
    # key, so pin presence AND first position on the emitted dict itself.
    assert next(iter(meta)) == "schema_version"
    validated = Meta.model_validate(meta)
    assert validated.schema_version == SCHEMA_VERSION
    assert validated.steps is None  # a live run doesn't know its length
    assert validated.llm is None  # default stepper runs the mock brain


def test_live_meta_locations_match_the_bake():
    # Baked and live meta must not drift (#297).
    live = PennStepper(num_steps=2, world=build_penn_world()).meta()
    assert live["locations"] == sorted(live["locations"])
    assert Meta.model_validate(live).locations == live["locations"]


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


@functools.lru_cache(maxsize=None)
def _ts_interface_fields(path: Path = _REPLAY_TS) -> dict[str, set[str]]:
    # Cached: the mirror tests below re-check several interfaces apiece, so
    # each TS file is read and comment-stripped once per session, not per pair.
    src = path.read_text()
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


# ---------------------------------------------------------------- live.ts
# The web companion's OTHER types file mirrors the live HTTP surface (#644).
# Same discipline as replay.ts above -- the TS is a mirror, the backend is the
# definition -- but the sources of truth here are the real wire emitters (the
# ledger summary + /usage extras, the monitor's kept row) and api.py's pydantic
# response models, not backend.contract. FeedRecord and LiveMeta stay unpinned:
# the first is an open envelope (`kind` + per-kind fields), the second a
# derived alias of the already-mirrored ReplayMeta.

_LIVE_TS = _REPO / "godot-generative-agents" / "web" / "src" / "types" / "live.ts"


def _assert_ts_matches(ts_name: str, wire_fields: set[str]) -> None:
    interfaces = _ts_interface_fields(_LIVE_TS)
    assert ts_name in interfaces, f"live.ts is missing interface {ts_name}"
    assert interfaces[ts_name] == wire_fields, (
        f"live.ts {ts_name} drifted from the wire shape: "
        f"ts-only={interfaces[ts_name] - wire_fields}, "
        f"wire-only={wire_fields - interfaces[ts_name]}"
    )


def test_live_ts_usage_summary_mirrors_the_usage_route():
    # GET /usage assembles its payload inline in the route (api.py): the
    # ledger summary, extras added in the route body (available/over_budget +
    # the budget pair when a ceiling is armed), the stepper's run_usage()
    # merge (#526/#569), and a hand-rolled no-ledger fallback shape. A literal
    # re-statement of those extras here couldn't catch the next field added
    # inline in the route body, so drive the REAL route through both branches
    # -- a budget-armed ledger on a run_usage-bearing stepper puts every
    # conditional field on the wire at once -- and mirror the union. live.ts
    # marks the conditionally-present ones optional, but must NAME them all --
    # omitting run_calls/run_cost_usd is exactly how the dashboard fell back
    # to lifetime counters (#644).
    api = pytest.importorskip("backend.api")
    from fastapi.testclient import TestClient

    from text_adventure_games.usage import UsageLedger

    stepper = PennStepper(num_steps=2, world=build_penn_world())
    stepper.ledger = UsageLedger(max_cost_usd=1.0)  # arm the budget pair
    armed_app = api.create_app(stepper.game, stepper=stepper, start_paused=True)
    with TestClient(armed_app) as client:
        armed = client.get("/usage").json()
    with TestClient(api.create_app(stepper.game)) as client:  # no stepper: no ledger
        fallback = client.get("/usage").json()
    # Self-check both branches really fired -- a silently un-armed ledger
    # would narrow the mirror without failing it.
    assert armed["available"] is True and fallback["available"] is False
    assert {"max_cost_usd", "remaining_budget_usd", "run_calls"} <= set(armed)
    _assert_ts_matches("UsageSummary", set(armed) | set(fallback))


def test_live_ts_run_social_mirrors_the_stepper_social_block():
    # The #795 social block is a NESTED object inside run_usage() -- the
    # UsageSummary mirror above only checks that `social` is named, not its
    # shape, so a field added inside it (counted/resumed, #819/#825) could reach
    # the wire without live.ts naming it. That is exactly the drift #644 set out
    # to catch, one level down: pin RunSocial against the real emitter too.
    social = PennStepper(num_steps=2, world=build_penn_world()).run_usage()["social"]
    _assert_ts_matches("RunSocial", set(social))


def test_live_ts_llm_call_record_mirrors_the_monitor_row():
    # The llm_call feed row is the monitor's kept record -- a flattened
    # CallRecord.to_primitive() plus the printed row's extras -- with
    # serve_penn.drain_events stamping kind="llm_call" on the way out. Drive
    # the real monitor so a new CallRecord field (the #359 tool metadata was
    # one) can't reach the wire without live.ts naming it.
    import io

    from backend.llm_monitor import LlmCallMonitor
    from text_adventure_games.usage import CallRecord, Usage, UsageLedger

    monitor = LlmCallMonitor(stream=io.StringIO(), color=False)
    rec = CallRecord(usage=Usage.zero("mock", "mock-model"), cost_usd=0.0)
    monitor.on_call(rec, "decide", UsageLedger())
    (kept,) = monitor.drain()
    wire = dict(kept, kind="llm_call")  # serve_penn.drain_events's stamp
    _assert_ts_matches("LlmCallRecord", set(wire))


def test_live_ts_mirrors_api_response_models():
    # The typed responses (handshake, feed envelope, memory stream) already
    # have pydantic definitions in api.py -- pair them directly, like the
    # replay.ts pairs above. Needs the server extra (fastapi), same skip
    # contract as test_live_seam.py.
    api = pytest.importorskip("backend.api")
    pairs = {
        "LiveStatusResponse": api.LiveStatusResponse,
        "EventsResponse": api.EventsResponse,
        "MemoryStreamResponse": api.MemoryStreamResponse,
    }
    for ts_name, model in pairs.items():
        _assert_ts_matches(ts_name, set(model.model_fields))
