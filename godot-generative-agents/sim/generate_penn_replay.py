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
from backend import path_finder
from backend.build_world import build_world, load_world_data
from backend.run_simulation import simulate
from backend.smallville_agents import SMALLVILLE_VISION_R
from backend.world_map import WorldMap

_SIM_DIR = os.path.dirname(os.path.abspath(__file__))
_GODOT_DIR = os.path.dirname(_SIM_DIR)
_REPO = os.path.dirname(_GODOT_DIR)

WORLD_DATA = os.path.join(_SIM_DIR, "world_data_upenn.yaml")
UPENN_DIR = os.path.join(_SIM_DIR, "the_upenn")
OUT_PATH = os.path.join(_GODOT_DIR, "maps", "penn_replay.json")

# A full campus day: every persona crosses the (large) map several times AND now
# walks a multi-room circuit inside Van Pelt. At one tile per step a single
# cross-campus leg is ~200 steps, so 400 ended mid-morning -- agents barely reached
# their first building. 1200 lets the whole cast complete its day, including the
# in-library room-to-room movement (Maya's two Van Pelt visits, Ellis's stacks run,
# Diego's gallery circuit). The viewer's playback speed is independent of this.
DEFAULT_STEPS = 1200
SEC_PER_STEP = 10  # in-game seconds per step, for a wall-clock label
SIM_START = "2023-02-13 08:00:00"  # matches gen_agents.sim_config default


def _pin_building_meeting_points(world_map, offset=5.0):
    """Route agents heading into a building toward its *centre* (on the side they
    approach from), instead of the nearest tile of its huge lobby address.

    A building's interior is one big address (Houston Hall's "lobby" is ~2000 tiles
    spanning the whole footprint) and ``walk_path`` aims for the *nearest* such tile
    -- so two residents arriving from opposite sides settle at opposite edges, tens
    of tiles apart, even though the sim counts them co-located. A perception-gated
    conversation between them then renders as a long line across the building.

    Here we wrap ``walk_path`` so each agent walks to a tile a few (`offset`) tiles
    off the building's centre toward where it came from: residents converge near the
    middle -- close enough to read as together (a short conversation link) -- while
    still arriving from their own sides rather than stacking on one tile. The
    interior addressing is untouched (these are ordinary lobby tiles); if the target
    isn't reachable we fall back to the original nearest-tile routing, so no agent
    is ever stranded.
    """
    orig_walk_path = world_map.walk_path
    centres: dict = {}

    def centre_of(address):
        if address not in centres:
            tiles = [
                t for t in world_map.tiles_for(address) if not world_map.is_blocked(t)
            ]
            if tiles:
                cx = sum(t[0] for t in tiles) / len(tiles)
                cy = sum(t[1] for t in tiles) / len(tiles)
                centres[address] = (cx, cy, tiles)
            else:
                centres[address] = None
        return centres[address]

    def walk_path(from_tile, address):
        info = centre_of(address)
        if info:
            cx, cy, tiles = info
            dx, dy = from_tile[0] - cx, from_tile[1] - cy
            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
            # A point `offset` tiles from the centre toward the agent's approach...
            tx, ty = cx + dx / dist * offset, cy + dy / dist * offset
            # ...then the nearest actual lobby tile to it.
            target = min(tiles, key=lambda t: (t[0] - tx) ** 2 + (t[1] - ty) ** 2)
            if tuple(from_tile) != target:
                path = path_finder.path_finder(
                    world_map.collision, tuple(from_tile), target, 1
                )
                if path and len(path) > 1:
                    return [tuple(t) for t in path[1:]]
        return orig_walk_path(from_tile, address)  # target unreachable -> nearest tile

    world_map.walk_path = walk_path
    return world_map


def _gate_conversations_by_perception(built):
    """Make the Penn agents converse only with whoever they can *perceive*.

    The engine already perceives by tile distance (``TiledGame`` overrides
    ``perceivable_locations`` for sight, vision_r=8), but its *hearing* seam
    (``audience_for``) is still room-based by default -- so two residents would
    only talk when in the exact same arena, even when standing far apart on the
    map. We keep that fix in the Godot sim (not the shared engine): override the
    Penn game's ``audience_for`` to reuse its own ``perceivable_locations``, so an
    agent's conversation partners are exactly the residents within its perception
    radius. ``simulate``'s conversation loop reads ``audience_for`` (via
    ``can_converse`` / ``find_conversation_pairs``), so this gates dialogue by
    proximity with no engine change.

    ``build_world`` returns ``(game, characters)``; we patch the game and pass it
    straight through.
    """
    game, characters = built

    def audience_for(speaker, message, target=None):
        audience = []
        for loc in game.perceivable_locations(speaker):
            audience.extend(c for c in loc.characters.values() if c is not speaker)
        return audience

    game.audience_for = audience_for
    return game, characters


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the Penn replay for Godot.")
    ap.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    personas, locations = load_world_data(WORLD_DATA)
    world_map = _pin_building_meeting_points(WorldMap(UPENN_DIR))
    print(
        f"Loaded the_upenn ({world_map.width}x{world_map.height}); "
        f"{len(personas)} personas. Simulating {args.steps} steps..."
    )

    # `simulate` fills this with each persona's *full* memory stream (the same
    # UI-ready dicts the Smallville exporter writes). The agent-info companion
    # panel renders it as a per-agent "memory history" that grows over the
    # replay; the per-frame `reasoning`/`chat` below feed that agent's card.
    # Under the mock brain reasoning is a stub and chat is null, but travel/
    # perform reflections and perception observations still accrue, so the
    # history is populated either way -- it just gets richer with a real model.
    memory_streams: dict = {}
    frames = simulate(
        world_map,
        args.steps,
        personas=personas,
        build_world_fn=lambda wm: _gate_conversations_by_perception(
            build_world(wm, personas, locations)
        ),
        out_memories=memory_streams,
    )

    # Godot-friendly replay: meta + one entry per step per persona. The Godot
    # canvas reads only x/y/act/e; reasoning/chat/memory_streams are extra fields
    # for the React companion panel (Godot ignores keys it doesn't use).
    order = [p["name"] for p in personas]
    replay = {
        "meta": {
            "tile_px": world_map.tile_size,
            "width": world_map.width,
            "height": world_map.height,
            "steps": len(frames),
            "sec_per_step": SEC_PER_STEP,
            "start": SIM_START,
            # Perception radius (tiles) the sim used to gate sight + conversation,
            # so the viewer can draw the matching "perception fog" when tracking an
            # agent. Personas don't override it in world_data_upenn.yaml, so the
            # global default describes every agent.
            "vision_r": SMALLVILLE_VISION_R,
            "personas": [{"name": p["name"], "emoji": p["emoji"]} for p in personas],
        },
        "frames": [
            {
                name: {
                    "x": int(f[name]["movement"][0]),
                    "y": int(f[name]["movement"][1]),
                    "act": f[name]["description"],
                    "e": f[name]["pronunciatio"],
                    # Agent-card cognition (issue #163). The mock leaves reasoning
                    # a stub and chat None; a real-LLM run fills them in. `memories`
                    # is the small set retrieval surfaced for *this* decision (the
                    # card's "Memories retrieved" shorthand) -- a subset of the full
                    # `memory_streams` below; it populates even under the mock since
                    # retrieval still runs (the mock only ignores it when deciding).
                    "reasoning": f[name].get("reasoning"),
                    "chat": f[name].get("chat"),
                    "memories": f[name].get("memories"),
                }
                for name in order
            }
            for f in frames
        ],
        # Per-persona full memory stream: [{kind, importance, text, created_turn}].
        # The panel filters to created_turn <= current step to show history so far.
        "memory_streams": memory_streams,
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
