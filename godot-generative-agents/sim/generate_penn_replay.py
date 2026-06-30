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

import yaml

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

# How the Godot viewer (scripts/penn_replay.gd) plays a `chat` transcript back:
# ~DIALOGUE_LINE_STEPS replay steps per line, with the last line fading over
# DIALOGUE_FADE_STEPS. We mirror them here so the conversation injector only fires
# a meeting when the participants stay together long enough for the whole exchange
# to play out on the map (otherwise the bubbles/link would linger after they part).
# Keep in sync with the constants of the same name in penn_replay.gd.
DIALOGUE_LINE_STEPS = 14
DIALOGUE_FADE_STEPS = 2


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


def _rendezvous_clusters(world_map, addresses, spacing=4):
    """For each meeting venue, a tight cluster of a few walkable tiles near its
    centre, all within a couple of `spacing` of each other.

    Routing every participant of a meeting onto one of these (below) makes them
    settle a handful of tiles apart -- comfortably inside the perception radius, so
    a conversation reads as people standing together with a short link, rather than
    at opposite ends of a big room (which the per-side centre routing can leave
    them). Tiles are taken from the venue's own arena, so they're always walkable
    and inside the room.
    """
    clusters: dict = {}
    for address in addresses:
        tiles = [t for t in world_map.tiles_for(address) if not world_map.is_blocked(t)]
        if not tiles:
            continue
        cx = sum(t[0] for t in tiles) / len(tiles)
        cy = sum(t[1] for t in tiles) / len(tiles)
        # The centre tile plus two neighbours offset by `spacing`, each snapped to
        # the nearest real arena tile; de-duplicated but order-preserving.
        wants = [(cx, cy), (cx + spacing, cy), (cx, cy + spacing)]
        cluster: list = []
        for wx, wy in wants:
            t = min(tiles, key=lambda p: (p[0] - wx) ** 2 + (p[1] - wy) ** 2)
            if t not in cluster:
                cluster.append(t)
        if cluster:
            clusters[address] = cluster
    return clusters


def _pin_meeting_rendezvous(world_map, venues):
    """Route each successive arrival at a meeting venue to a distinct tile in its
    rendezvous cluster (round-robin), so participants converge a few tiles apart.

    Wraps whatever ``walk_path`` is already installed (e.g. the centre routing
    above) and only intercepts the venue addresses; every other destination falls
    through unchanged. Any two cluster tiles are within perception range, so it
    doesn't matter which arrival gets which slot -- participants always end up close
    enough to converse. If the cluster tile is somehow unreachable we fall back to
    the underlying routing, so no agent is stranded.
    """
    orig_walk_path = world_map.walk_path
    counts: dict = {address: 0 for address in venues}

    def walk_path(from_tile, address):
        cluster = venues.get(address)
        if cluster:
            target = tuple(cluster[counts[address] % len(cluster)])
            counts[address] += 1
            if tuple(from_tile) == target:
                return []  # already standing on the rendezvous tile
            path = path_finder.path_finder(
                world_map.collision, tuple(from_tile), target, 1
            )
            if path and len(path) > 1:
                return [tuple(t) for t in path[1:]]
        return orig_walk_path(from_tile, address)

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


def _load_meetings(path):
    """Read the authored `meetings` block from the world YAML (or [] if absent).

    `load_world_data` only returns personas + locations, so we read the file
    ourselves for this Godot-only extra. Each meeting is
    ``{label?, participants: [name...], dialogue: [[speaker, text], ...]}``.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("meetings", []) or []


def _inject_scripted_conversations(replay, meetings, vision_r):
    """Paint authored dialogue into the replay's `chat` field -- proximity-honestly.

    The mock brain never speaks, so the viewer's speech-bubble + conversation-link
    feature would otherwise never fire. For each authored meeting we find the
    longest stretch of the bake where *every* participant is within ``vision_r``
    tiles of each other (the same radius the viewer draws as perception fog), and
    only if that stretch is long enough to play the whole exchange do we write the
    transcript onto each participant's `chat` for that window. The viewer keys the
    bubble/link off `chat`, so a conversation is only ever drawn between agents who
    are genuinely standing together on the map.

    If a meeting's participants never co-locate long enough in this bake, it is
    SKIPPED with a warning rather than faked across the map -- so changing a
    schedule can quietly drop a meeting, and the log says which and why.
    """
    frames = replay["frames"]
    n = len(frames)
    if n == 0:
        return

    def co_located(i, participants):
        pts = []
        for p in participants:
            ent = frames[i].get(p)
            if ent is None:
                return False
            pts.append((ent["x"], ent["y"]))
        for a in range(len(pts)):
            for b in range(a + 1, len(pts)):
                dx, dy = pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]
                if (dx * dx + dy * dy) ** 0.5 > vision_r:
                    return False
        return True

    cast = set(frames[0].keys())
    print(f"Injecting scripted conversations (vision_r={vision_r} tiles):")
    fired = 0
    for m in meetings:
        participants = m.get("participants", [])
        dialogue = [[str(s), str(t)] for s, t in m.get("dialogue", [])]
        label = m.get("label", " + ".join(participants))
        missing = [p for p in participants if p not in cast]
        if len(participants) < 2 or not dialogue or missing:
            print(f"  - SKIP  {label}: bad spec (missing {missing or 'dialogue'}).")
            continue

        # Frames the whole exchange needs to play (incl. the final fade).
        need = len(dialogue) * DIALOGUE_LINE_STEPS + DIALOGUE_FADE_STEPS

        # Longest contiguous run where all participants are mutually within range.
        best_start, best_len, cur_start = -1, 0, None
        for i in range(n):
            if co_located(i, participants):
                cur_start = i if cur_start is None else cur_start
                if i - cur_start + 1 > best_len:
                    best_len, best_start = i - cur_start + 1, cur_start
            else:
                cur_start = None

        if best_len < need:
            print(
                f"  - SKIP  {label}: longest co-located window {best_len} steps "
                f"< {need} needed for {len(dialogue)} lines."
            )
            continue

        start, end = best_start, best_start + need
        # Don't garble a participant who is already mid-conversation in this window.
        clash = any(
            frames[i][p].get("chat") for i in range(start, end) for p in participants
        )
        if clash:
            print(f"  - SKIP  {label}: overlaps another meeting's window.")
            continue

        for i in range(start, end):
            for p in participants:
                frames[i][p]["chat"] = dialogue
        fired += 1
        print(
            f"  - FIRE  {label}: steps {start}-{end} "
            f"({len(participants)} agents, window {best_len} steps)."
        )
    print(f"Injected {fired}/{len(meetings)} meetings.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the Penn replay for Godot.")
    ap.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    personas, locations = load_world_data(WORLD_DATA)
    meetings = _load_meetings(WORLD_DATA)

    world_map = _pin_building_meeting_points(WorldMap(UPENN_DIR))
    # Route each meeting's participants to a tight rendezvous cluster inside its
    # venue, so they settle close enough to converse (the centre routing alone can
    # leave them just out of perception range -- see _rendezvous_clusters).
    addr_of = {loc["name"]: loc.get("address") for loc in locations}
    venue_addrs = {
        addr_of[m["at"]]
        for m in meetings
        if m.get("at") in addr_of and addr_of[m["at"]]
    }
    world_map = _pin_meeting_rendezvous(
        world_map, _rendezvous_clusters(world_map, venue_addrs)
    )

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

    # Light up the viewer's speech-bubble + conversation-link feature with authored
    # dialogue, but only across the frames where the participants are actually
    # standing together (see _inject_scripted_conversations). No-op if the world
    # has no `meetings` block.
    _inject_scripted_conversations(replay, meetings, SMALLVILLE_VISION_R)

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
