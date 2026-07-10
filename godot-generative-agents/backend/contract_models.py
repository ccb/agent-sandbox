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
    MEMORY_RECORD_FIELDS,
    SCHEMA_VERSION,
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


class AgentFrame(_ContractModel):
    """One persona at one step. Field order == AGENT_FRAME_FIELDS (#297)."""

    x: int
    y: int
    act: str
    e: str
    reasoning: str | None = None
    chat: list[tuple[str, str]] | None = None
    memories: list[MemoryRecord] | None = None


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


class Replay(_ContractModel):
    """The whole baked file: what #307's exporter emits."""

    meta: Meta
    frames: list[dict[str, AgentFrame]]
    memory_streams: dict[str, list[MemoryRecord]] | None = None


# Sanity: the pinned orders and the models can never drift from each other.
assert tuple(AgentFrame.model_fields) == AGENT_FRAME_FIELDS
assert tuple(MemoryRecord.model_fields) == MEMORY_RECORD_FIELDS
