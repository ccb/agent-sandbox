"""The pinned replay data-contract (#305): what a Penn replay IS, versioned.

A replay file (``penn_replay.json``, written by ``penn/generate_penn_replay.py``
and played by the Godot viewer) is::

    {
      "meta": {
        "schema_version": "1.0",         # this contract's version
        "tile_px", "width", "height",    # world geometry (ints)
        "sec_per_step",                  # in-game seconds per step (int)
        "start",                         # sim-start wall clock, "YYYY-MM-DD HH:MM:SS"
        "vision_r",                      # perception radius, tiles (int)
        "steps",                         # frame count -- BAKE ONLY (a live run
                                         #   doesn't know it up front)
        "llm",                           # {"provider", "model"} -- LIVE ONLY
                                         #   (None/absent in a baked file & under mock)
        "personas": [                    # penn_world.persona_meta_entry
          {"name", "emoji", "persona", "home",
           "schedule": [{"place", "activity", "emoji", "steps"}]}
        ],
        "relationships": [               # penn_world.relationships_meta
          {"a", "b", "kind", "closeness", "description"}
        ]
      },
      "frames": [ {persona_name: AgentFrame}, ... ],   # one dict per step
      "memory_streams": {persona_name: [MemoryRecord, ...]},
      "events": [EventState, ...]      # the GameEvent run record (#467) --
                                       #   absent from replays baked before it
    }

The live handshake (``GET /live`` -> ``serve_penn.PennStepper.meta()``) serves
the same ``meta`` shape -- the two documented differences are exactly the
``steps`` / ``llm`` optionals above, so baked and live can't drift (#297).

**Versioning:** bump ``SCHEMA_VERSION`` on any breaking change (a field
removed, renamed, or retyped). Additive optional fields do NOT bump it.

**Field order is part of the contract -- for the row shapes only.** The bake's
``json.dump`` serializes insertion order and #297's acceptance is a
byte-identical replay file, so the tuples below pin the exact key order of the
per-step frame rows and memory rows (which any future writer -- the #304 store,
the #307 exporter -- must reproduce; ``model_dump()`` on the matching models
already does). ``meta`` key order is deliberately NOT pinned: the ``Meta``
model's dump order differs from the bake's dict, and every reader looks meta
keys up by name, never by position.

This module is deliberately **stdlib-only**: the offline bake runs in the base
install (no extras), where the Pydantic library does not exist. The enforcing
models live in ``backend.contract_models`` (importable under any extra that
provides it: ``server`` / ``llm`` / ``openai`` / ``anthropic``); the
TypeScript mirror is ``godot-generative-agents/web/src/types/replay.ts``.
"""

SCHEMA_VERSION = "1.0"

# One persona's per-step entry (penn_world.replay_frame_entry), in emitted order.
AGENT_FRAME_FIELDS = ("x", "y", "act", "e", "reasoning", "chat", "memories")

# One memory-stream entry (cognition.memories_for_frame), in emitted order.
MEMORY_RECORD_FIELDS = ("kind", "importance", "text", "created_turn")

# One event-log entry (text_adventure_games.events.GameEvent.to_primitive), in
# emitted order — the run record #467 persists into the replay's "events" key.
EVENT_STATE_FIELDS = ("turn", "actor", "action", "summary", "payload")
