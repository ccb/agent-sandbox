"""Run the UPenn agent simulation and write a replay the Godot frontend can play.

Godot can't run Python, so (exactly like the Phaser/Django replay) the sim runs
offline here and we dump a compact per-step "replay" JSON; the Godot scene
`scenes/penn_replay.tscn` reads it and animates a sprite per persona walking the
campus map.

The Penn *world* lives next to this script (`world_data_upenn.yaml` + the
`the_upenn/` matrix), so it's self-contained here. The agent *engine* (build the
world, attach mock brains, step the loop, pathfind) is imported from the shared
`backend` package so improvements there flow through automatically.

Run from the repo root (so `uv run` finds the engine env)::

    uv run python godot-generative-agents/sim/generate_penn_replay.py
    uv run python godot-generative-agents/sim/generate_penn_replay.py --steps 600

Writes: godot-generative-agents/maps/penn_replay.json
"""

import argparse
import json
import os

# Reuse the tested agent engine (not a fork). It's the installed top-level
# `backend` package now, so a plain import works -- no sys.path juggling.
from backend.build_world import build_world, load_world_data
from backend.run_simulation import simulate
from backend.world_map import WorldMap

_SIM_DIR = os.path.dirname(os.path.abspath(__file__))
_GODOT_DIR = os.path.dirname(_SIM_DIR)
_REPO = os.path.dirname(_GODOT_DIR)

WORLD_DATA = os.path.join(_SIM_DIR, "world_data_upenn.yaml")
UPENN_DIR = os.path.join(_SIM_DIR, "the_upenn")
OUT_PATH = os.path.join(_GODOT_DIR, "maps", "penn_replay.json")

DEFAULT_STEPS = 400
SEC_PER_STEP = 10  # in-game seconds per step, for a wall-clock label


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the Penn replay for Godot.")
    ap.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    personas, locations = load_world_data(WORLD_DATA)
    world_map = WorldMap(UPENN_DIR)
    print(
        f"Loaded the_upenn ({world_map.width}x{world_map.height}); "
        f"{len(personas)} personas. Simulating {args.steps} steps..."
    )

    frames = simulate(
        world_map,
        args.steps,
        personas=personas,
        build_world_fn=lambda wm: build_world(wm, personas, locations),
    )

    # Compact, Godot-friendly replay: meta + one entry per step per persona.
    order = [p["name"] for p in personas]
    replay = {
        "meta": {
            "tile_px": world_map.tile_size,
            "width": world_map.width,
            "height": world_map.height,
            "steps": len(frames),
            "sec_per_step": SEC_PER_STEP,
            "personas": [{"name": p["name"], "emoji": p["emoji"]} for p in personas],
        },
        "frames": [
            {
                name: {
                    "x": int(f[name]["movement"][0]),
                    "y": int(f[name]["movement"][1]),
                    "act": f[name]["description"],
                    "e": f[name]["pronunciatio"],
                }
                for name in order
            }
            for f in frames
        ],
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(replay, fh, ensure_ascii=False)
    print(
        f"Wrote {os.path.relpath(args.out, _REPO)} "
        f"({len(frames)} steps, {len(order)} personas)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
