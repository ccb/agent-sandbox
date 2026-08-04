# Agent architecture

This document describes the shipped Penn simulation, not a roadmap.

## Control flow

```text
Penn YAML + persona library + map matrix
                  │
                  ▼
          build_penn_world()
                  │
       ┌──────────┴──────────┐
       ▼                     ▼
 live PennStepper       replay generator
       │                     │
 HTTP/WebSocket          replay JSON
       └──────────┬──────────┘
                  ▼
          Godot / web viewers
```

`penn_world.py` is the only Penn world factory. Live and baked execution share
its locations, cast, actions, routing patches, clocks, and replay-frame encoder.

## One cognition cycle

1. Perceive the current grounded world and noteworthy events.
2. Retrieve relevant memories and plan context when enabled.
3. Ask the selected brain for a structured action choice.
4. Parse and validate the choice against the offered action/tool schema.
5. Check engine preconditions and apply effects; failed actions remain failures.
6. Record events, outcomes, memories, usage, and viewer trace data.
7. Run bounded conversation, reaction, planning, and reflection seams when due.

The LLM never mutates the world directly. The engine is authoritative and emits
the consequences that later observations contain.

## Brains and determinism

- `mock`: deterministic, key-free schedule behavior used for routine development.
- `scripted`: deterministic client that opens model-gated tool/cassette paths for
  offline integration tests.
- `llm`: Anthropic-backed behavior configured by the Penn YAML and CLI overrides.

Seeds, configuration, scenario, model choices, and usage are included in run
metadata. Cassettes can reproduce model responses locally, but raw cassettes are
private run artifacts and are not part of this public package.

## Memory, plans, and social behavior

Each agent owns an `AgentMemory`. Retrieval combines recency, importance, and
relevance within a token budget. Daily plans decompose into timed stops; the live
loop may revise a plan when progress diverges. Conversations require grounded
co-location/perception and have cooldowns. Reflections summarize accumulated
experience after configured thresholds.

Cognition tools expose bounded recall, knowledge, and plan lookup to the model.
They are optional and metered. Their results inform a choice but do not bypass
action validation.

## Replay and live contract

The backend emits versioned metadata, persona state, events, traces, and wishes.
`replay_codec.py` removes repeated fields for storage and restores them for
consumers. Contract tests validate both the native viewer and browser assumptions.
Schema changes must update producers, codecs, fixtures, readers, and docs together.

## Extension boundary

Generic mechanics belong in `text_adventure_games`; Penn-specific world assembly
belongs in `backend/penn`. Viewers should display backend state, never invent
simulation state. A fork adding another scenario should provide one world factory,
data, tests, and documentation without copying the cognition loop.
