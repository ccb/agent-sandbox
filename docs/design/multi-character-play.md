# Multi-character turns

The engine supports sequential turns and an opt-in simultaneous gather/resolve
mode. Simultaneous mode gathers each agent's intent from the same turn-start
snapshot, then resolves commands in deterministic initiative order. Contention
is settled by the normal precondition gate: a later action can fail because an
earlier action changed the world.

Agents receive their own outcome and may retry according to bounded policy. They
must not observe another agent's private trace or future intent during gathering.
Tests should cover ordering, contention, failure feedback, and serialization.
