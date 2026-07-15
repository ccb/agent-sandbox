"""The one configured Penn world, shared by the bake and the live server (#297).

The Penn sim isn't just ``build_world`` over the ``the_upenn`` matrix -- it is
that *plus* three behavioral patches (centre-of-building routing, meeting
rendezvous clustering, perception-gated hearing) that make agents actually
converge and converse. Historically all of that lived inline in
``generate_penn_replay.py::main()``, so a live server rebuilding the world
without them would get a *subtly different Penn* -- agents that never meet,
conversations that never fire -- making live-vs-baked comparison meaningless.

:func:`build_penn_world` is the single factory both entry points import:

* ``generate_penn_replay.py`` -- the offline bake that writes
  ``maps/penn_replay.json`` for the load-once viewer;
* ``serve_penn.py`` -- the live server (#263) that steps the same world over
  ``backend.api``'s live loop (#349/#262).

Everything here is world *setup*; genuinely bake-only work (running
``simulate()`` to completion, the post-hoc conversation injector, writing the
JSON) stays in the generator, and live-only work (the on-the-fly injector, the
stepper) lives in the server.
"""

import os
from dataclasses import dataclass, field
from typing import Callable

import yaml

# Reuse the tested agent engine (not a fork). It's the installed top-level
# `backend` package now, so a plain import works -- no sys.path juggling.
from backend import path_finder
from backend.actions import Activate, Deactivate, DrinkPenn
from backend.build_world import build_world, load_world_data
from backend.world_map import WorldMap
from text_adventure_games.enums import Property
from text_adventure_games.things.items import Item

_SIM_DIR = os.path.dirname(os.path.abspath(__file__))

WORLD_DATA = os.path.join(_SIM_DIR, "world_data_upenn.yaml")
UPENN_DIR = os.path.join(_SIM_DIR, "the_upenn")

# The Penn-local verb set (#300): registered on top of Travel/Act via
# build_world(extra_actions=...). DrinkPenn overrides the engine's "drink".
# Upstreaming these into the engine library is #464.
PENN_EXTRA_ACTIONS = [Activate, Deactivate, DrinkPenn]

# The verb set a Penn brain may choose from (spec §3) -- the engine verbs the
# boil-water scenario wires in, on top of the base travel/perform. Handed to
# attach_agents(extra_action_names=...) by every Penn entry point.
PENN_ACTION_VERBS = ["get", "drink", "activate", "deactivate"]

SEC_PER_STEP = 10  # in-game seconds per step, for a wall-clock label
SIM_START = "2023-02-13 08:00:00"  # matches backend.sim_config default

# How the Godot viewer (scripts/viewer.gd) plays a `chat` transcript back:
# ~DIALOGUE_LINE_STEPS replay steps per line, with the last line fading over
# DIALOGUE_FADE_STEPS. We mirror them here so the conversation injectors (the
# bake's post-hoc one and the live server's on-the-fly one) only fire a meeting
# when the participants stay together long enough for the whole exchange to play
# out on the map (otherwise the bubbles/link would linger after they part).
# Keep in sync with the constants of the same name in viewer.gd.
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
    spot_cursor: dict = {}

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

    def walk_path(from_tile, address, furniture=None):
        # Furniture first (#537): when the arena has seat spots, walk to one
        # of the k nearest to the approach-offset point -- consumed
        # round-robin per address so co-arrivals spread across furniture
        # instead of stacking -- and only fall through to the centroid pick
        # (below) when every candidate is unreachable. Bare arenas
        # (Williams, grounds) have no spots and keep today's behavior.
        # A furniture hint (#559) biases the pick to spots serving that piece
        # (a teacher -> blackboard); no match -> the full spot set, as before.
        spots = getattr(world_map, "furniture_spots", {}).get(address)
        info = centre_of(address)
        if spots and info:
            if furniture:
                types = getattr(world_map, "furniture_spot_type", {})
                matching = [t for t in spots if types.get(t) == furniture]
                if matching:
                    spots = matching
            cx, cy, _tiles = info
            dx, dy = from_tile[0] - cx, from_tile[1] - cy
            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
            tx, ty = cx + dx / dist * offset, cy + dy / dist * offset
            near = sorted(spots, key=lambda t: (t[0] - tx) ** 2 + (t[1] - ty) ** 2)
            near = near[:4]
            n = spot_cursor.get(address, 0)
            spot_cursor[address] = n + 1
            for j in range(len(near)):
                target = near[(n + j) % len(near)]
                if tuple(from_tile) == target:
                    return []
                path = path_finder.path_finder(
                    world_map.collision, tuple(from_tile), target, 1
                )
                if path and len(path) > 1:
                    return [tuple(t) for t in path[1:]]
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

    Note the round-robin ``counts`` live in this closure: the patched
    ``world_map`` is *stateful*, which is why :func:`build_penn_world` hands out
    a fresh one per call (a reused map would give later runs different
    rendezvous slots).
    """
    orig_walk_path = world_map.walk_path
    counts: dict = {address: 0 for address in venues}

    def walk_path(from_tile, address, furniture=None):
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
        return orig_walk_path(from_tile, address, furniture=furniture)

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
    ``{label?, at, participants: [name...], dialogue: [[speaker, text], ...]}``.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("meetings", []) or []


def _load_relationships(path):
    """Read the authored `relationships` block from the world YAML (or [] if absent).

    Another Godot-only extra `load_world_data` doesn't return: the seed social
    graph (who knows whom at t=0) the viewer's social-graph pop-up draws (#252).
    Each edge is ``{a, b, kind, closeness, description}`` -- see the YAML block's
    comment for the authoring contract. Raw here; validated/normalized by
    :func:`relationships_meta` at build time.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("relationships", []) or []


def _load_llm(path):
    """Read the authored `llm` block from the world YAML (or None if absent).

    Another Godot-only extra `load_world_data` doesn't return: the provider/
    model/cost-ceiling settings `serve_penn --brain llm` runs on. ``None``
    (no block) simply means the world declares no LLM configuration."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("llm") or None


@dataclass
class PennWorld:
    """Everything the configured Penn sim is made of, ready to run.

    ``world_map`` carries the routing patches (and their round-robin state --
    see :func:`_pin_meeting_rendezvous`), ``build_world_fn`` bakes in the
    perception gating, ``meetings`` is the authored dialogue script both
    conversation injectors consume, ``llm`` is the world's declared LLM
    settings (the YAML ``llm:`` block; only ``serve_penn --brain llm`` acts
    on it), and ``relationships`` is the validated t=0 seed social graph the
    viewer's social-graph pop-up draws (#252)."""

    world_map: WorldMap
    personas: list
    locations: list
    meetings: list
    build_world_fn: Callable
    llm: dict | None = None
    relationships: list = field(default_factory=list)


def _furnish_boil_water(game) -> None:
    """Stock Houston Hall with the boil-water props (#300).

    The first Item instances in the Penn world: two cups of unboiled water
    (``requires_boiling`` + ``is_boiled: False`` -- drink one and DrinkPenn
    makes you sick), a pot, and two fixed devices. Activating the stove sets
    ``is_on`` and deliberately nothing else -- no heat process exists, so
    nothing in this world can flip ``is_boiled``; that capability gap is the
    point of the self-coding experiment (#299)."""
    hall = game.locations.get("Houston Hall")
    if hall is None:
        return
    sink = Item("sink", "a utility sink", "An old utility sink. The tap runs cloudy.")
    sink.set_property(Property.GETTABLE, False)
    sink.set_property("is_device", True)
    stove = Item(
        "stove", "a small electric stove", "A single coil burner, dusty but working."
    )
    stove.set_property(Property.GETTABLE, False)
    stove.set_property("is_device", True)
    pot = Item("pot", "a cooking pot", "An empty steel pot. It could hold water.")
    for name in ("cup of murky water", "second cup of murky water"):
        cup = Item(name, "a cup of murky water", "Cloudy, untreated tap water.")
        cup.set_property(Property.DRINKABLE, True)
        cup.set_property("requires_boiling", True)
        cup.set_property("is_boiled", False)
        hall.add_item(cup)
    hall.add_item(sink)
    hall.add_item(stove)
    hall.add_item(pot)


def build_penn_world(world_data=WORLD_DATA, upenn_dir=UPENN_DIR) -> PennWorld:
    """Load + patch the Penn world, exactly as the replay bake configures it.

    Every call returns a *fresh* world (fresh ``WorldMap``, fresh patch state),
    because the routing patches are stateful -- a live server's ``reset()``
    must call this again rather than reuse the old map."""
    personas, locations = load_world_data(world_data)
    meetings = _load_meetings(world_data)

    world_map = _pin_building_meeting_points(WorldMap(upenn_dir))
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

    def _build(wm):
        game, characters = build_world(
            wm, personas, locations, extra_actions=PENN_EXTRA_ACTIONS
        )
        _furnish_boil_water(game)
        return _gate_conversations_by_perception((game, characters))

    return PennWorld(
        world_map=world_map,
        personas=personas,
        locations=locations,
        meetings=meetings,
        build_world_fn=_build,
        llm=_load_llm(world_data),
        # Validated once here, so an authoring typo fails the bake / the live
        # server's boot loudly instead of drawing a wrong graph.
        relationships=relationships_meta(personas, _load_relationships(world_data)),
    )


def relationships_meta(personas, relationships):
    """The world YAML's ``relationships`` block -> the ``meta.relationships`` list.

    A sibling of :func:`persona_meta_entry`: the single projection the bake
    (``generate_penn_replay``) and the live server (``serve_penn.meta``) share,
    so the viewer's social-graph pop-up (#252) sees the same seed edges whether
    it's watching a baked file or a live run.

    Validates against the *active* cast and normalizes for determinism: names
    are sorted within each edge, edges are sorted by ``(a, b)``, and the output
    carries exactly ``{a, b, kind, closeness, description}``. Raises
    ``ValueError`` on an unknown name (parked personas' edges must stay
    commented out in the YAML), a self-edge, a duplicate pair, or a
    ``closeness`` outside 1..5 -- authoring mistakes should fail the build,
    not render a misleading graph.
    """
    cast = {p["name"] for p in personas}
    edges = []
    seen_pairs = set()
    for rel in relationships:
        a, b = str(rel.get("a", "")), str(rel.get("b", ""))
        for name in (a, b):
            if name not in cast:
                raise ValueError(
                    f"relationships: {name!r} is not an active persona "
                    f"(cast: {sorted(cast)})"
                )
        if a == b:
            raise ValueError(f"relationships: self-edge on {a!r}")
        pair = tuple(sorted((a, b)))
        if pair in seen_pairs:
            raise ValueError(
                f"relationships: duplicate edge {pair[0]!r} -- {pair[1]!r}"
            )
        seen_pairs.add(pair)
        closeness = int(rel.get("closeness", 1))
        if not 1 <= closeness <= 5:
            raise ValueError(
                f"relationships: closeness {closeness} for {pair[0]!r} -- {pair[1]!r} "
                "must be 1..5"
            )
        edges.append(
            {
                "a": pair[0],
                "b": pair[1],
                "kind": str(rel.get("kind", "")),
                "closeness": closeness,
                "description": str(rel.get("description", "")),
            }
        )
    return sorted(edges, key=lambda e: (e["a"], e["b"]))


def persona_meta_entry(spec):
    """One persona's static detail for the replay/live ``meta.personas`` block.

    The sibling of :func:`replay_frame_entry` -- the single projection the bake
    (``generate_penn_replay``) and the live server (``serve_penn.meta``) share, so
    the persona-inspector "State Details" modal (viewer.gd, issue #408) gets the
    same identity + schedule whether it's watching a baked file or a live run.

    ``name``/``emoji`` drive the sprite + sidebar (they always existed here);
    ``persona``/``home``/``schedule`` are the extra fields the inspector reads.
    Everything is pulled from the *normalized* persona spec (see
    ``build_world._normalize_personas``), so ``schedule`` is always a list of
    ``{place, activity, emoji, steps}`` stops (``steps=None`` => stays put for the
    rest of the day). ``vision_r`` is deliberately NOT here: Penn personas don't
    override it, so it stays a single top-level ``meta`` global.
    """
    return {
        "name": spec["name"],
        "emoji": spec["emoji"],
        "persona": spec.get("persona", ""),
        "home": spec.get("home", ""),
        "schedule": [
            {
                "place": s["place"],
                "activity": s["activity"],
                "emoji": s.get("emoji", spec["emoji"]),
                "steps": s.get("steps"),
            }
            for s in spec.get("schedule", [])
        ],
    }


def replay_frame_entry(raw):
    """One persona's raw ``simulate()``/``step()`` frame -> the replay schema.

    The one mapping the bake, the live server, and the equivalence tests share,
    so the wire contract can't drift between them. KEY ORDER IS PINNED --
    x, y, act, e, reasoning, chat, memories -- because the bake's ``json.dump``
    serializes insertion order and #297's acceptance is a byte-identical
    replay file.

    The Godot canvas reads only x/y/act/e; reasoning/chat/memories are the
    agent-card cognition extras (issue #163). The mock leaves reasoning a stub
    and chat None; a real-LLM run fills them in. `memories` is the small set
    retrieval surfaced for *this* decision (the card's "Memories retrieved"
    shorthand) -- a subset of the run's full memory stream; it populates even
    under the mock since retrieval still runs (the mock only ignores it when
    deciding)."""
    return {
        "x": int(raw["movement"][0]),
        "y": int(raw["movement"][1]),
        "act": raw["description"],
        "e": raw["pronunciatio"],
        "reasoning": raw.get("reasoning"),
        "chat": raw.get("chat"),
        "memories": raw.get("memories"),
    }
