# Agent memory

`AgentMemory` stores typed records for observations, actions, conversations,
plans, and reflections. Retrieval ranks eligible records using weighted recency,
importance, and relevance, then respects record-count and token budgets.

Memory belongs to one agent and must not leak private reasoning between actors.
New record kinds need serialization, retrieval, visibility, and deterministic
tests. Perception decides what can become a memory; memory does not grant access
to unseen world state.

Reflection periodically synthesizes insights from accumulated records. The
result is another attributed memory, not a direct world mutation.
