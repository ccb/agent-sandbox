# Pin the replay data-contract (#305, replay shapes only)

First sub-project of the live→replay persistence chain (decided 2026-07-09):
**#305 (this) → #304 (RunStore) → #307 (live-run exporter)**. #304 defines its
`frames.jsonl` lines as "the AgentFrame contract" and #307 exports "against the
pinned #305", so the contract lands first.

## Problem

The backend↔frontend replay schema is implicit and defined on the *frontend*
side: the only written form is `godot-generative-agents/web/src/types/replay.ts`
(TypeScript), which the Python bake (`generate_penn_replay.py`) and the live
handshake (`serve_penn.PennStepper.meta()`) mirror by hand. They have **already
drifted**: the bake emits `meta.start`, `meta.vision_r`, `meta.relationships`,
and persona `persona`/`home`/`schedule` fields that `replay.ts` doesn't declare;
the live meta additionally carries an `llm` key and omits `steps`. Nothing pins
these together, and the #304 store would persist an unpinned shape.

## Scope (decided in brainstorming)

**Replay shapes only** — the pieces the store (#304) and exporter (#307)
consume: `meta`, `AgentFrame`, `MemoryRecord`, and the whole-file `Replay`.

**Deferred** (live-client #263 territory, not needed by the store/exporter):
the event-feed record, the WS hello message, the WorldState-vs-frame
relationship, and the #185 private-cognition allowlist interplay.

**Branch note:** the issue predates #399; the `backend` package now lives under
`godot-generative-agents/`, so this rides `godot-ga-main` per CLAUDE.md (not
`main` as the issue's footer says).

## Design

### 1. `backend/contract.py` — constants, stdlib-only

The bake runs in the **base env** (mock brain, no extras), and `pydantic` is
**not** in the base dependency closure (it arrives only via the
`server`/`llm`/`openai`/`anthropic` extras — verified against `uv.lock`). So the
piece the bake imports must be dependency-free:

- `SCHEMA_VERSION = "1.0"` — bumped on any breaking shape change (field
  removed/renamed/retyped); additive optional fields don't bump it.
- `AGENT_FRAME_FIELDS = ("x", "y", "act", "e", "reasoning", "chat", "memories")`
  — the pinned key order. Order is load-bearing: the bake's `json.dump`
  serializes insertion order and #297's acceptance is a byte-identical replay,
  so the order is part of the contract, not a style choice.
- A module docstring documenting the schema in prose (the human-readable half
  of the contract).

### 2. `backend/contract_models.py` — Pydantic v2 models

Imports `SCHEMA_VERSION`/`AGENT_FRAME_FIELDS` from `contract.py`. Importable
wherever an extra provides pydantic — the live server, the future store (#304)
and exporter (#307), and the test suite (CI installs `--extra server` for the
`godot-generative-agents/tests/` job). The models the rest of the chain emits
against:

- `MemoryRecord`: `kind: str`, `text: str`, `created_turn: int`,
  `importance: float`.
- `ScheduleStop`: `place: str`, `activity: str`, `emoji: str`,
  `steps: int | None` (None = stays for the rest of the day).
- `PersonaMeta`: `name: str`, `emoji: str`, `persona: str`, `home: str`,
  `schedule: list[ScheduleStop]` — mirrors `penn_world.persona_meta_entry`.
- `RelationshipEdge`: `a: str`, `b: str`, `kind: str`, `closeness: int` (1–5),
  `description: str` — exactly what `penn_world.relationships_meta` emits.
- `AgentFrame`: `x: int`, `y: int`, `act: str`, `e: str`,
  `reasoning: str | None = None`, `chat: list[tuple[str, str]] | None = None`,
  `memories: list[MemoryRecord] | None = None` — field order = `AGENT_FRAME_FIELDS`
  (asserted by test).
- `LlmInfo`: `provider: str`, `model: str` — what is driving the cast.
- `Meta`: `schema_version: str`, `tile_px: int`, `width: int`, `height: int`,
  `sec_per_step: int`, `start: str`, `vision_r: int`,
  `personas: list[PersonaMeta]`, `relationships: list[RelationshipEdge]`,
  `steps: int | None = None` (bake knows it; a live run doesn't),
  `llm: LlmInfo | None = None` (live-only; absent/None in a baked file and
  under the mock). One model covers both surfaces — the documented differences
  are exactly these two optionals.
- `Replay`: `meta: Meta`, `frames: list[dict[str, AgentFrame]]`,
  `memory_streams: dict[str, list[MemoryRecord]] | None = None`.

Validation posture: `model_config = ConfigDict(extra="forbid")` — an emitter
growing an unpinned field must fail the conformance test loudly, that being the
entire point of pinning.

### 3. Emitters gain `schema_version` (additive)

- `generate_penn_replay.py`: `"schema_version": SCHEMA_VERSION` first in the
  `meta` dict (imports the stdlib `contract` module only).
- `serve_penn.PennStepper.meta()`: same key, same constant — bake↔live parity
  (#297) is preserved by construction.
- `penn_replay.json` is git-ignored, so no committed-artifact churn; any
  bake↔live meta-equivalence tests are updated in the same change.

### 4. `replay.ts` reconciled to a mirror

Add the missing fields (`ReplayMeta.schema_version?/start/vision_r/
relationships?/llm?`, `Persona.persona/home/schedule` + a `ScheduleStop`
interface, `RelationshipEdge`), marked optional (`?`) where an older baked file
legitimately lacks them. A header comment declares `backend/contract.py` +
`contract_models.py` the source of truth and this file a mirror.

### 5. Tests — `godot-generative-agents/tests/test_replay_contract.py`

- **Conformance:** build the Penn world (mock), run a short `simulate` (a few
  steps), assemble the same dicts the bake writes, and `model_validate` them
  against `Replay`/`Meta`/`AgentFrame` (with `extra="forbid"` doing the real
  work). Also validate a live-shaped `PennStepper.meta()` blob (no `steps`,
  `llm` present-or-None).
- **Field order:** `list(AgentFrame.model_fields) == list(AGENT_FRAME_FIELDS)
  == list(replay_frame_entry(<sample>).keys())` — the byte-identity guard.
- **Lock-step with TS:** parse the interface blocks out of `replay.ts` with a
  small regex and assert each interface's field-name set matches its Pydantic
  twin (`ReplayMeta`↔`Meta`, `Persona`↔`PersonaMeta`, `AgentFrame`,
  `MemoryRecord`, `ScheduleStop`, `RelationshipEdge`) — Python and TS can't
  silently drift again, without needing a TS toolchain in CI.

### 6. Docs

A "Replay data-contract (#305)" section in `godot-generative-agents/backend/README.md`:
where the contract lives, the `schema_version` bump policy, `replay.ts`'s
mirror status, and what #304/#307 build against it.

## What the rest of the chain consumes

- **#304 RunStore:** each `frames.jsonl` line is a dict that validates as
  `dict[str, AgentFrame]`; `memories` rows are `MemoryRecord`s; the run
  manifest embeds `Meta`. The store *constructs* through the models.
- **#307 exporter:** emits a `Replay` and writes `replay.model_dump()`.

## Verification

- `uv run pytest godot-generative-agents/tests/ -q` — the new contract tests
  plus the existing suite (any meta-equivalence tests updated for
  `schema_version`).
- `uv run pytest tests/ -q` — root engine suite untouched.
- `LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --steps 40`
  — the bake still runs **in the base env** (proves the stdlib-only import
  boundary held) and its output validates against `Replay`.
- `black` clean.

## Risks

- **Byte-identity (#297).** Adding `schema_version` changes the bake's output
  vs older bakes — deterministically, and the file is git-ignored; the
  field-order test keeps the frame serialization pinned. Any test that
  snapshots exact meta keys is updated alongside.
- **`extra="forbid"` is strict.** If some emitter carries an undocumented field
  today, the conformance test will surface it during implementation — that's a
  discovery, not a failure; pin it or remove it consciously.
- **Regex-parsing TS** is deliberately shallow (interface field names only).
  It can't check TS types — good enough to catch drift, cheap enough to keep.

## Acceptance

- A versioned, documented contract exists in `backend/` that the bake and the
  live meta emit against, with `replay.ts` reconciled as a mirror.
- Conformance + field-order + TS-lock-step tests pass in CI.
- The mock bake still runs in the base env unchanged (no new base
  dependencies).
- #304 can define `frames.jsonl` as "lines validating against `AgentFrame`"
  by import, not by prose.
