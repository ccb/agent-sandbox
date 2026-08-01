"""Pydantic models enforcing the replay data-contract (#305).

The machine-checkable half of ``backend.contract`` (see its docstring for the
schema prose and the versioning policy). ``extra="forbid"`` everywhere: an
emitter growing an unpinned field must fail the conformance tests loudly --
that is the entire point of pinning. The #304 RunStore and #307 exporter
construct their output through these models; the tests validate what the bake
and the live meta actually emit.

Kept out of ``backend.contract`` so the base-env bake (which has no pydantic)
can import the constants without importing this module.
"""

from pydantic import BaseModel, ConfigDict, Field

from backend.contract import (
    AGENT_FRAME_FIELDS,
    EVENT_STATE_FIELDS,
    MEMORY_RECORD_FIELDS,
    SCHEMA_VERSION,
    WISH_FIELDS,
)


class _ContractModel(BaseModel):
    # extra="forbid": reject unpinned fields. protected_namespaces=(): allow a
    # field literally named "model" (LlmInfo) without pydantic's model_* warning.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class MemoryRecord(_ContractModel):
    """One memory-stream entry. Field order == MEMORY_RECORD_FIELDS."""

    kind: str
    importance: float
    text: str
    created_turn: int


class ScheduleStop(_ContractModel):
    place: str
    activity: str
    emoji: str
    steps: int | None = None  # None = stays put for the rest of the day


class PersonaMeta(_ContractModel):
    """One persona's static detail (penn_world.persona_meta_entry)."""

    name: str
    emoji: str
    persona: str
    home: str
    schedule: list[ScheduleStop]


class RelationshipEdge(_ContractModel):
    """One t=0 seed-graph edge (penn_world.relationships_meta)."""

    a: str
    b: str
    kind: str
    closeness: int = Field(ge=1, le=5)
    description: str


class LlmInfo(_ContractModel):
    """What is driving the cast on a live run (None under the mock brain)."""

    provider: str
    model: str


class EventState(_ContractModel):
    """One GameEvent log entry (#467's run record) — the verbatim shape of
    ``text_adventure_games.events.GameEvent.to_primitive()``. Field order ==
    EVENT_STATE_FIELDS. ``payload`` is event-specific structured detail (e.g. a
    sickness cause) and deliberately stays an open dict."""

    turn: int
    actor: str | None  # world-level stimuli (ambient sound, POST /world/event,
    # the boil arc's `boiled` event) legitimately have no single actor -- the
    # store persists actor=None, so the contract must accept it too (#631).
    action: str
    summary: str
    payload: dict


class WishState(_ContractModel):
    """One ActionWish log entry (#622) — the verbatim shape of
    ``text_adventure_games.wishes.ActionWish.to_primitive()``. Field order ==
    WISH_FIELDS. ``goals``/``scope`` are situation snapshots (incomplete goals,
    item/character names) at wish time; ``meta`` is an open extension point."""

    actor: str | None  # None only if no actor resolved (mirrors EventState)
    turn: int
    location: str | None
    desired: str
    reason: str
    trigger: str
    goals: list[str]
    scope: list[str]
    raw_command: str
    meta: dict


class AgentFrame(_ContractModel):
    """One persona at one step. Field order == AGENT_FRAME_FIELDS (#297).

    In a *written file* (schema 1.1, #941) the optional carry-forward fields
    (reasoning/chat/memories/trace) may be absent when unchanged from the
    same agent's previous frame; ``backend.replay_codec.fatten_frames``
    rehydrates them on read. An absent optional field validates here either
    way, so both slim files and fat in-memory rows conform."""

    x: int
    y: int
    act: str
    e: str
    reasoning: str | None = None
    chat: list[tuple[str, str]] | None = None
    memories: list[MemoryRecord] | None = None
    # Per-decision cognition trace (#359): consults + the terminal action, as
    # compact digests -- e.g. under the mock, a DECIDING frame carries
    # [{"kind":"action","tool":<verb>,"ok":true}]. [] only for a waking /
    # carry-forward frame (no decision made this step); the #163 card
    # renders it. No raw args payload -- digests only.
    trace: list[dict] | None = None


class Meta(_ContractModel):
    """The replay/live ``meta`` blob. One model covers both surfaces: the bake
    knows ``steps`` and has no ``llm``; a live run is the reverse."""

    schema_version: str = SCHEMA_VERSION
    tile_px: int
    width: int
    height: int
    sec_per_step: int
    start: str
    vision_r: int
    personas: list[PersonaMeta]
    relationships: list[RelationshipEdge]
    steps: int | None = None  # bake-only (a live run doesn't know it up front)
    llm: LlmInfo | None = None  # live-only (None in a baked file / under mock)
    locations: list[str] | None = None  # #780: world place names; absent pre-#780


class Replay(_ContractModel):
    """The whole baked file: what #307's exporter emits. (Frame/memory row key
    order is contract-pinned and preserved by ``model_dump()``; meta key order
    is not part of the contract -- readers look meta up by name.)"""

    meta: Meta
    frames: list[dict[str, AgentFrame]]
    memory_streams: dict[str, list[MemoryRecord]] | None = None
    events: list[EventState] | None = None  # the #467 run record; absent pre-#467
    wishes: list[WishState] | None = None  # the #622 demand record; absent pre-#622


# Sanity: the pinned orders and the models can never drift from each other.
assert tuple(AgentFrame.model_fields) == AGENT_FRAME_FIELDS
assert tuple(MemoryRecord.model_fields) == MEMORY_RECORD_FIELDS
assert tuple(EventState.model_fields) == EVENT_STATE_FIELDS
assert tuple(WishState.model_fields) == WISH_FIELDS
