# Custom world authoring

A world fork needs three consistent representations:

1. semantic world data: cast, locations, schedules, relationships, and model defaults;
2. traversable geometry used by backend pathfinding;
3. presentation geometry/assets used by a viewer.

Create one factory that loads these inputs and returns fresh state on every call.
Both live and baked execution must use it. Keep display names stable because
plans, action schemas, replay metadata, and frontend labels use them as grounded
identifiers.

Add world-specific actions beside the world; promote only genuinely reusable
mechanics to `text_adventure_games`. An action must enforce preconditions in code,
not in prompt prose. Include a deterministic mock cast so contributors can run
the complete flow without credentials.

A shipped world should have tests for construction, reachability, schedule place
validity, action grounding, reset/freshness, deterministic replay, and API schema.
If a visual map differs from the pathfinding representation, add an automated
drift gate like Penn's `tools/geo/validate_tmj.py`.

Do not copy external source, personas, maps, or artwork without confirming their
license and attribution. Keep private run artifacts and API keys outside the tree.
