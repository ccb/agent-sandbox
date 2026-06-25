"""Run the generative-agents sim on the REAL University of Pennsylvania campus.

This is the the_ville sim (same engine, same mock-driven schedules, same step
loop) pointed at a different world:

  * the map is ``the_upenn`` -- the OSM-derived maze built by
    ``tools/geo/osm_to_ville.py`` (collision = building footprints, sectors =
    named Penn buildings), loaded by :class:`WorldMap`;
  * the cast is ``world_data_upenn.yaml`` -- a few Penn personas whose homes and
    daily schedules are real campus buildings (College Hall, Van Pelt, ...).

Because the mock brain decides from each persona's schedule, this runs offline,
deterministically, and free. It is headless: it proves the agents *walk the real
campus* (pathfinding around building walls between named buildings) and prints a
per-agent route summary. Rendering that walk -- in the Phaser replay or in Godot
-- is the separate next step.

Run it from the ``generative-agents`` directory::

    uv run python -m backend.run_upenn
    uv run python -m backend.run_upenn --steps 600
"""

import argparse
import os

from .build_world import build_world, load_world_data
from .run_simulation import simulate
from .world_map import WorldMap

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_GA_DIR = os.path.dirname(_BACKEND_DIR)

WORLD_DATA = os.path.join(_BACKEND_DIR, "world_data_upenn.yaml")
# The tracked asset tree (setup.sh rsyncs it into the git-ignored frontend/);
# WorldMap only needs the matrix/ folder, so we can read it straight from here.
UPENN_DIR = os.path.join(
    _GA_DIR, "frontend_overrides", "static_dirs", "assets", "the_upenn"
)

# Long enough for an agent to walk a cross-campus route and settle into a couple
# of its scheduled stops (Maya's Stouffer -> Van Pelt leg alone is ~150 tiles).
DEFAULT_STEPS = 400


def _summarize(frames: list[dict], personas: list[dict], world_map: WorldMap) -> None:
    """Print, per persona, the route their sprite actually walked."""
    order = [p["name"] for p in personas]
    print(
        f"\nSimulated {len(frames)} steps on the_upenn "
        f"({world_map.width}x{world_map.height} tiles).\n"
    )
    for name in order:
        tiles = [tuple(f[name]["movement"]) for f in frames]
        start, end = tiles[0], tiles[-1]
        distinct = len(set(tiles))
        # Steps where the sprite actually moved (a tile change) = walking effort.
        moved = sum(1 for a, b in zip(tiles, tiles[1:]) if a != b)
        # The ordered list of distinct activity/destination labels = the journey.
        legs = []
        for f in frames:
            d = f[name]["description"]
            if not legs or legs[-1] != d:
                legs.append(d)
        print(f"== {name} ==")
        print(
            f"   start {start} -> end {end}   "
            f"({moved} tiles walked, {distinct} distinct tiles)"
        )
        for leg in legs:
            print(f"     - {leg}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the agent sim on Penn's campus.")
    ap.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    args = ap.parse_args()

    if not os.path.isdir(os.path.join(UPENN_DIR, "matrix")):
        raise SystemExit(
            f"Penn matrix not found at {UPENN_DIR}/matrix.\n"
            "Generate it: uv run python tools/geo/osm_to_ville.py --area core"
        )

    personas, locations = load_world_data(WORLD_DATA)
    world_map = WorldMap(UPENN_DIR)
    print(
        f"Loaded the_upenn ({world_map.width}x{world_map.height}); "
        f"{len(personas)} personas, {len(locations)} locations."
    )

    # Same simulate() as the_ville, with the Penn cast + builder. No
    # relationships/base-persona seeding (those are the_ville-only assets).
    frames = simulate(
        world_map,
        args.steps,
        personas=personas,
        build_world_fn=lambda wm: build_world(wm, personas, locations),
    )

    _summarize(frames, personas, world_map)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
