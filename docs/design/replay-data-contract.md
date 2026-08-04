# Replay data contract

The replay is the durable boundary between Python simulation and viewers. Its
metadata declares a schema version, map dimensions, time mapping, personas,
locations, relationships, configuration, and provenance. Frames contain the
viewer-facing state of each persona; sparse events, traces, and wishes explain
meaningful changes without requiring a client to parse prose.

`backend.contract` defines required fields. `backend.replay_codec` may omit values
that repeat from the preceding frame, but every consumer must observe the same
fattened representation. The Python and TypeScript codecs have mirrored tests.

Contract changes require:

- a deliberate schema-version decision;
- producer and validator updates;
- slim/fatten round-trip tests;
- Godot and web reader updates;
- regeneration and review of the public replay artifact.

Never include API keys, raw provider requests/responses, private cassettes, or
unreviewed personal data in replay metadata or trace fields.
