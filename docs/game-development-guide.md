# Extending the engine

The reusable engine models locations, items, characters, actions, blocks, time,
memory, and events independently of the Penn frontend.

For a new grounded action, subclass `Action`, declare its command name, validate
all required state in `check_preconditions()`, and mutate state only in
`apply_effects()`. Add focused tests for success, failure, and ambiguous object
resolution. If an LLM can choose it, update the offered tool schema and verify
that invalid arguments still fail at the engine boundary.

For a new world, write one factory that creates fresh state on every call. Keep
world-specific verbs and fixtures near that application. Share generic mechanics
through `text_adventure_games` rather than copying them. If the world is exposed
through the Penn service's scenario extension point, cover reset, replay, manifest,
and re-run behavior.

For a new prompt, add a `.prompty` template, render it through the shared prompt
loader, document its caller in the adjacent prompt-template README, and pin exact
output in an offline test.

Frontend code consumes snapshots/events and must not become a second authority
for preconditions, clocks, pathfinding, or agent decisions.
